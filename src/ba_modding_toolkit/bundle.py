# bundle.py

import struct
import traceback
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable

import UnityPy
from UnityPy.files import SerializedFile
from UnityPy.files.BundleFile import ArchiveFlags, ArchiveFlagsOld
from UnityPy.environment import Environment as Env
from UnityPy.helpers import CompressionHelper

from .asset import ApplyContext, ExtractContext, apply_asset, extract_asset
from .i18n import t
from .utils import apply_crc_fix, compute_crc32, no_log, throttle_progress
from .naming import RESOURCE_TYPES_NUM, parse_filename, ParsedFilename
from .models import (
    AssetKey, AssetContent, AssetType, Patch, KeyFunc,
    NameTypeKey, ContNameTypeKey, MatchStrategy, LogFunc,
    CompressionType, PatchResult, ReplaceAssetType,
    SaveOptions, SkelConvertOptions, AnimCheckOptions,
    ProgressCallback, SkelVersionConflict,
    RawAssetBytes, REPLACEABLE_ASSET_TYPES
)


@dataclass
class BundleFileInfo:
    """扫描结果中单个 bundle 文件的信息"""
    path: Path
    file_size: int
    modified_time: float = 0.0
    trailing_bytes: int | None = None
    trailing_content: bytes | None = None
    parsed_name: ParsedFilename | None = None
    crc_actual: int | None = None
    # ADB 支持
    local_cache_path: Path | None = None  # ADB 模式下的本地缓存路径
    source: str = "local"                  # "local" | "adb"

    @property
    def effective_path(self) -> Path:
        """获取实际用于文件操作的本地路径"""
        return self.local_cache_path if self.local_cache_path is not None else self.path


# 流式引用辅助（STREAM_REF_* / find_stream_refs / rewrite_stream_ref_prefixes /
# collect_stream_companions / install_raw_content）已迁移至 asset.py


# -------- 轻量 CAB 名解析（不解压数据块） --------

def _read_cstring(f) -> bytes:
    """读取以 null 结尾的字符串（读到 EOF 返回已读部分）"""
    out = bytearray()
    while True:
        byte = f.read(1)
        if not byte or byte == b'\x00':
            return bytes(out)
        out.extend(byte)


def _parse_engine_version(version_str: bytes) -> tuple[int, ...]:
    """把引擎版本字符串（如 b'2022.3.55f1'）解析为数字元组，失败返回空元组"""
    parts: list[int] = []
    for token in version_str.decode("ascii", "ignore").split("."):
        digits = ""
        for ch in token:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def get_cab_names(bundle_path: Path) -> set[str] | None:
    """
    仅解析 UnityFS 头部与 blockinfo，返回内部文件名集合（如 {"CAB-xxx"}）。

    内部文件名表位于 blockinfo（通常仅几百字节），无需像 Bundle.load 那样
    解压全部数据块——全目录 CAB 扫描因此从分钟级降到秒级。
    含 4 字节 CRC 修正尾的原版/产物文件均可正确解析（定位用头部 size 字段）。

    Returns:
        内部文件名集合；加密包/未知格式/损坏文件返回 None（调用方回退 Bundle.load）
    """
    try:
        with open(bundle_path, 'rb') as f:
            signature = _read_cstring(f)
            if signature != b'UnityFS':
                return None

            version = struct.unpack(">I", f.read(4))[0]
            _version_player = _read_cstring(f)
            version_engine = _read_cstring(f)
            size = struct.unpack(">q", f.read(8))[0]
            compressed_size, uncompressed_size, flags_value = struct.unpack(">III", f.read(12))

            # 与 UnityPy read_fs 一致：按引擎版本区分新旧 flags 语义
            engine_version = _parse_engine_version(version_engine)
            use_old_flags = (
                engine_version < (2020,)
                or (engine_version[0] == 2020 and engine_version < (2020, 3, 34))
                or (engine_version[0] == 2021 and engine_version < (2021, 3, 2))
                or (engine_version[0] == 2022 and engine_version < (2022, 1, 1))
            )
            flags: ArchiveFlagsOld | ArchiveFlags = ArchiveFlagsOld(flags_value) if use_old_flags else ArchiveFlags(flags_value)

            # 加密包无法离线解析 blockinfo
            if flags & flags.UsesAssetBundleEncryption:
                return None

            if flags & ArchiveFlags.BlocksInfoAtTheEnd:
                # 定位以头部 size 字段为准，避开 mod 产物尾部的 CRC 修正字节
                f.seek(size - compressed_size)
            else:
                # 头部版本 7+（及 2019.4.15+）的 blockinfo 起 16 字节对齐
                if version >= 7 or engine_version >= (2019, 4, 15):
                    f.seek((f.tell() + 15) & ~15)
            blocks_info = f.read(compressed_size)

        compression = flags_value & ArchiveFlags.CompressionTypeMask
        if compression == 0:
            data = blocks_info
        elif compression == 1:
            # UnityFS 的 blockinfo LZMA 流不含 8 字节 size 头，须按 offset=5 解压
            # （与 UnityPy read_fs 的 DECOMPRESSION_MAP 一致；True 语义仅适用于 UnityWeb 数据）
            data = CompressionHelper.decompress_lzma(blocks_info)
        elif compression in (2, 3):  # lz4 / lz4hc
            data = CompressionHelper.decompress_lz4(blocks_info, uncompressed_size)
        else:
            return None

        # blockinfo 布局：hash(16B) + 块表（每条 u32+u32+u16=10B）+ 节点表（{offset: i64, size: i64, flags: u32, name: cstring}）
        pos = 16
        blocks_count = struct.unpack_from(">i", data, pos)[0]
        pos += 4 + blocks_count * 10
        nodes_count = struct.unpack_from(">i", data, pos)[0]
        pos += 4
        names: set[str] = set()
        for _ in range(nodes_count):
            pos += 20  # offset + size + flags
            end = data.index(b'\x00', pos)
            names.add(data[pos:end].decode("utf-8", "replace"))
            pos = end + 1
        return names

    except Exception:
        return None


class Bundle:
    """
    封装 Bundle 文件的业务类。
    包含了底层的 UnityPy Environment 以及所有业务相关操作（加载、保存、替换、提取等）。
    """
    
    def __init__(self, path: Path, env: Env, log: LogFunc = no_log):
        self.path = path
        self.env = env
        self.log = log
    
    @property
    def name(self) -> str:
        """快捷获取文件名"""
        return self.path.name
    
    @cached_property
    def parsed_name(self) -> ParsedFilename:
        """获取解析后的文件名信息（带缓存）"""
        return parse_filename(self.name)

    @property
    def crc(self) -> str:
        """从文件名获取 CRC32 值"""
        return self.parsed_name.crc

    @property
    def core_name(self) -> str:
        """从文件名获取核心名称"""
        return self.parsed_name.core

    @property
    def res_type(self) -> str | None:
        """从文件名获取资源类型"""
        return self.parsed_name.res_type
    
    def need_crc(self) -> bool:
        """
        判断是否需要执行 CRC 修正。
        当前需要修正的为国际服+Windows平台
        条件：资源类型不是列表中的类型（日服），且目标平台为 StandaloneWindows64
        """

        # if self.res_type in JP_RES_TYPES:
        #     return False
        
        # 牛魔的为什么新版国际服的也用textures而不是003了？？？

        platform_name, _ = self.platform_info
        return platform_name == "StandaloneWindows64"

    def is_empty(self) -> bool:
        """检查 Bundle 是否为空（不包含任何文件）"""
        return len(self.env.files) == 0
    
    # -------- 匹配策略相关 --------
    
    @staticmethod
    def _get_key_func(strategy: MatchStrategy) -> KeyFunc:
        """根据匹配策略名获取对应的键生成函数。"""
        if strategy == 'path_id':
            return lambda obj: obj.path_id
        elif strategy == 'name_type':
            return lambda obj: NameTypeKey(obj.peek_name(), obj.type.name)
        elif strategy == 'cont_name_type':
            return lambda obj: ContNameTypeKey(obj.container, obj.peek_name(), obj.type.name)
        raise ValueError(f"Unknown match strategy: {strategy}")
    
    def get_asset_keys(
        self,
        strategy: MatchStrategy = 'name_type',
        asset_types: set[AssetType] | None = None,
    ) -> set[AssetKey]:
        """
        根据匹配策略获取资源键集合，用于指纹比对或匹配。

        Args:
            strategy: 匹配策略 ('path_id', 'name_type', 'cont_name_type')
            asset_types: 资源类型过滤，None 表示不过滤

        Returns:
            资源键集合
        """
        key_func = self._get_key_func(strategy)
        keys: set[AssetKey] = set()
        for obj in self.env.objects:
            if asset_types and obj.type not in asset_types:
                continue
            key = key_func(obj)
            if key is not None:
                keys.add(key)
        return keys
    
    @cached_property
    def platform_info(self) -> tuple[str, str]:
        """
        获取 Bundle 文件的平台信息和 Unity 版本。
        
        Returns:
            tuple[str, str]: (平台名称, Unity版本) 的元组
                             如果找不到则返回 ("UnknownPlatform", "Unknown")
        """
        for file_obj in self.env.files.values():
            for inner_obj in file_obj.files.values():
                if isinstance(inner_obj, SerializedFile) and hasattr(inner_obj, 'target_platform'):
                    return inner_obj.target_platform.name, inner_obj.unity_version
        
        return "UnknownPlatform", "Unknown"
    
    @staticmethod
    def get_trailing_bytes(bundle_path: Path) -> int | None:
        """
        快速检测 UnityFS bundle 文件尾部添加的额外字节数。
        
        通过读取文件头中的 size 字段与实际文件大小比较，
        可以在不解压的情况下判断是否需要移除尾部字节。
        
        Args:
            bundle_path: bundle 文件路径
            
        Returns:
            int: 需要移除的尾部字节数（0 表示无需移除）
            None: 读取失败
        """
        def read_cstring(f) -> bytes | None:
            """读取以 null 结尾的字符串；EOF 视为无效文件返回 None"""
            out = bytearray()
            while True:
                byte = f.read(1)
                if byte == b'\x00':
                    return bytes(out)
                if not byte:
                    return None
                out.extend(byte)

        try:
            with open(bundle_path, 'rb') as f:
                # 读取签名 (以 null 结尾)
                signature = read_cstring(f)
                if signature is None or signature != b'UnityFS':
                    return None

                # 读取 version (uint32)
                f.read(4)

                # 读取 version_player 与 version_engine (以 null 结尾的字符串)
                if read_cstring(f) is None or read_cstring(f) is None:
                    return None

                # 读取 size (int64, big-endian)
                size_bytes = f.read(8)
                if len(size_bytes) != 8:
                    return None
                
                recorded_size = int.from_bytes(size_bytes, 'big')
                
                # 获取实际文件大小
                actual_size = bundle_path.stat().st_size
                
                # 计算差值
                trailing_bytes = actual_size - recorded_size
                
                # 如果实际大小小于记录大小，说明文件损坏
                if trailing_bytes < 0:
                    return None
                
                return trailing_bytes
                
        except Exception:
            return None
    
    @staticmethod
    def get_trailing_content(bundle_path: Path, trailing_size: int, max_bytes: int = 64) -> bytes | None:
        """
        读取 bundle 文件尾部的字节内容。

        Args:
            bundle_path: bundle 文件路径
            trailing_size: 尾部字节数（由 get_trailing_bytes 返回）
            max_bytes: 最大读取字节数，超出截断

        Returns:
            尾部字节内容，读取失败返回 None
        """
        try:
            read_size = min(trailing_size, max_bytes)
            with open(bundle_path, 'rb') as f:
                f.seek(-read_size, 2)
                return f.read(read_size)
        except Exception:
            return None
    
    @classmethod
    def load(cls, bundle_path: Path, log: LogFunc = no_log) -> 'Bundle | None':
        """
        尝试加载一个 Unity bundle 文件。
        使用快速检测尾部字节的方式优化加载流程。
        
        Returns:
            Bundle 实例，如果加载失败则返回 None
        """
        if not bundle_path.exists():
            log(f'❌ {t("log.file.not_exist", path=bundle_path)}')
            return None
        
        # 快速检测尾部字节数
        trailing = cls.get_trailing_bytes(bundle_path)
        
        if trailing is None:
            log(f'❌ {t("log.file.load_failed", path=bundle_path)}')
            return None
        
        # 尝试加载
        try:
            if trailing == 0:
                env = UnityPy.load(str(bundle_path))
            else:
                data = bundle_path.read_bytes()[:-trailing]
                env = UnityPy.load(data)
            return cls(bundle_path, env, log)
        except Exception:
            pass
        
        # 如果精确检测后加载失败，尝试 fallback 方式
        try:
            data = bundle_path.read_bytes()
        except Exception as e:
            log(f'  ❌ {t("log.file.read_in_memory_failed", name=bundle_path.name, error=e)}')
            return None
        
        # TODO: 支持用户指定输入
        bytes_to_remove = [4, 8, 12]
        
        for bytes_num in bytes_to_remove:
            if len(data) > bytes_num:
                try:
                    trimmed_data = data[:-bytes_num]
                    env = UnityPy.load(trimmed_data)
                    return cls(bundle_path, env, log)
                except Exception:
                    pass
        
        log(f'❌ {t("log.file.load_failed", path=bundle_path)}')
        return None
    
    @classmethod
    def check_need_crc(cls, bundle_path: Path, log: LogFunc = no_log) -> bool:
        """
        检查指定的 bundle 文件是否需要 CRC 修正。
        适用于只需要判断 CRC 需求而不需要进一步操作的场景。
        """
        bundle = cls.load(bundle_path)
        if bundle is None:
            return False
        
        platform, unity_version = bundle.platform_info
        log(t("log.platform_info", platform=platform, version=unity_version))

        return bundle.need_crc()

    @classmethod
    def check_crc_match(cls, bundle_path: Path) -> bool:
        """
        检查 bundle 实际 CRC 是否已与文件名中的 CRC 一致（一致则无需修正重存）。
        仅需文件名解析与整文件 CRC 计算，无需加载 bundle。
        """
        crc_str = parse_filename(bundle_path.name).crc
        if not crc_str or not crc_str.isdigit():
            return False
        return compute_crc32(bundle_path) == int(crc_str)

    @classmethod
    def list_asset_names(
        cls,
        bundle_path: Path,
        asset_types: set[AssetType],
        log: LogFunc = no_log,
    ) -> set[tuple[str, str]]:
        """
        枚举 bundle 内指定类型资产的 (名字, 类型名) 集合。

        供替换范围展示等场景：仅取名不解码内容，peek_name 惰性取名
        避免反序列化对象数据（如网格顶点），失败时回退 read()。
        """
        bundle = cls.load(bundle_path, log=log)
        if bundle is None:
            return set()
        env = bundle.env

        out: set[tuple[str, str]] = set()
        for obj in env.objects:
            if obj.type not in asset_types:
                continue
            name: str | None = None
            try:
                name = obj.peek_name()
            except Exception:
                try:
                    name = obj.read().m_Name
                except Exception:
                    continue
            if name:
                out.add((name, obj.type.name))
        return out

    def compress(self, compression: CompressionType = "none") -> bytes:
        """
        从 UnityPy.Environment 对象生成 bundle 文件的字节数据。
        
        Args:
            compression: 压缩方式
                - "lzma": 使用 LZMA 压缩
                - "lz4": 使用 LZ4 压缩
                - "original": 保留原始压缩方式
                - "none": 不进行压缩
        """
        if not compression or compression == "none":
            packer = ""
        elif compression == "original":
            packer = "original"
        elif compression == "lz4":
            # UnityPy "lz4" uses 0xC2 (BlocksInfoAtTheEnd); use 0x42 so CRC tail is safe.
            packer = (0x42, 2)
        elif compression == "lzma":
            packer = "lzma"
        else:
            raise ValueError(f"Unsupported compression: {compression}")

        return self.env.file.save(packer=packer)
    
    def save(self, output_path: Path, save_options: SaveOptions) -> tuple[bool, str]:
        """
        生成压缩bundle数据，根据需要执行CRC修正，并最终保存到文件。
        CRC修正使用输出文件名中提取的目标CRC值。

        Returns:
            tuple(bool, str): (是否成功, 状态消息) 的元组。
        """
        try:
            compression_map = {
                "lzma": t("log.compression.lzma"),
                "lz4": t("log.compression.lz4"),
                "none": t("log.compression.none"),
                "original": t("log.compression.original")
            }
            compression_str = compression_map.get(save_options.compression, save_options.compression.upper())
            crc_status_str = t("common.on") if save_options.perform_crc else t("common.off")
            self.log(f"  > {t('log.file.saving_bundle_prefix')} [{t('log.file.compression_method', compression=compression_str)}] [{t('log.file.crc_correction', crc_status=crc_status_str)}]")
            
            compressed_data = self.compress(save_options.compression)
            
            final_data = compressed_data
            success_message = t("message.save_success")
            
            if save_options.perform_crc:
                crc_str = parse_filename(output_path.name).crc
                if not crc_str or not crc_str.isdigit():
                    return False, t("message.crc.correction_failed_file_not_generated", name=output_path.name)
                target_crc = int(crc_str)
                
                if save_options.extra_bytes:
                    compressed_data += save_options.extra_bytes
                
                corrected_data = apply_crc_fix(
                    compressed_data, target_crc
                )
                
                if not corrected_data:
                    return False, t("message.crc.correction_failed_file_not_generated", name=output_path.name)
                
                final_data = corrected_data
            
            with open(output_path, "wb") as f:
                f.write(final_data)
            success_message = t("message.save_success")
            
            return True, success_message
        
        except Exception as e:
            self.log(f'❌ {t("log.file.save_failed", path=output_path, error=e)}')
            self.log(traceback.format_exc())
            return False, t("message.save_error", error=e)
    
    def apply_patch(
        self,
        patch: Patch,
        match_strategy: MatchStrategy = 'path_id',
        anim_check: AnimCheckOptions | None = None,
    ) -> PatchResult:
        """
        将补丁中的资源应用到当前的 bundle。

        Args:
            patch: 资源补丁，格式为 { asset_key: content }。
            match_strategy: 匹配策略，用于从目标环境中的对象生成 asset_key。
            anim_check: 动画差异检测选项（启用开关与 SpineViewerCLI 路径）

        Returns:
            PatchResult: 包含修改结果的数据类，包括实际修改数量、跳过数量、日志和未匹配键。
        """
        key_func = self._get_key_func(match_strategy)
        applied_count = 0
        skipped_count = 0
        applied_assets_log = []
        matched_keys: list[AssetKey] = []
        anim_diffs: dict[str, list[str]] = {}
        ctx = ApplyContext(env=self.env, anim_check=anim_check, log=self.log)
        
        tasks = patch.copy()
        
        for obj in self.env.objects:
            if not tasks:
                break
            
            try:
                data = obj.read()
                asset_key = key_func(obj)
                
                if asset_key is None:
                    continue
                
                if obj.type not in REPLACEABLE_ASSET_TYPES:
                    continue
                
                if asset_key in tasks:
                    content: AssetContent = tasks.pop(asset_key)
                    matched_keys.append(asset_key)
                    resource_name = getattr(data, 'm_Name', t("log.unnamed_resource", type=obj.type.name))
                    
                    # 各资产类型的替换语义见 asset.apply_asset
                    outcome = apply_asset(obj, content, ctx)
                    if not outcome.applied:
                        self.log(f'  ⏭️ {t("log.replace_skipped_same_content", type=obj.type.name, name=resource_name)}')
                        skipped_count += 1
                        continue
                    
                    if outcome.missing_anims:
                        anim_diffs[resource_name] = outcome.missing_anims
                    
                    applied_count += 1
                    # 有 companion 随行时在成功行内追加，便于排查流式资源丢失类问题
                    companion_note = (
                        f" ({t('log.replace_companion_attached', names=', '.join(content.companions))})"
                        if isinstance(content, RawAssetBytes) and content.companions else ""
                    )
                    self.log(f'  ✅ {t("log.replace_applied", type=obj.type.name, name=resource_name)}{companion_note}')
                    key_display = str(asset_key)
                    log_message = f"[{obj.type.name}] {resource_name} (key: {key_display})"
                    applied_assets_log.append(log_message)

            except Exception as e:
                resource_name_for_error = obj.peek_name() or t("log.unnamed_resource", type=obj.type.name)
                self.log(f'  ❌ {t("common.error")}: {t("log.replace_resource_failed", name=resource_name_for_error, type=obj.type.name, error=e)}')
                self.log(traceback.format_exc())
        
        return PatchResult(
            applied_count=applied_count,
            skipped_count=skipped_count,
            applied_logs=applied_assets_log,
            unmatched_keys=list(tasks.keys()),
            matched_keys=matched_keys,
            anim_diffs=anim_diffs,
        )
    
    def extract_patch(
        self,
        asset_types_to_replace: set[ReplaceAssetType],
        match_strategy: MatchStrategy = 'path_id',
        spine_options: SkelConvertOptions | None = None
    ) -> tuple[Patch, list[SkelVersionConflict]]:
        """
        从当前 Bundle 提取资源，生成补丁。
        
        Args:
            asset_types_to_replace: 要替换的资源类型集合（如 {"Texture2D", "TextAsset", "Mesh"} 或 {"ALL"}）
            match_strategy: 匹配策略，用于生成资源键
            spine_options: Spine 资源版本检测与转换选项
            
        Returns:
            (资源补丁 { asset_key: content }, skel 版本冲突列表)
        """
        key_func = self._get_key_func(match_strategy)
        patch: Patch = {}
        skel_conflicts: list[SkelVersionConflict] = []
        replace_all = "ALL" in asset_types_to_replace
        ctx = ExtractContext(env_file=self.env.file, spine_options=spine_options, log=self.log)
        
        for obj in self.env.objects:
            try:
                if obj.type not in REPLACEABLE_ASSET_TYPES:
                    continue
                
                if not replace_all and obj.type.name not in asset_types_to_replace:
                    continue
                
                asset_key = key_func(obj)
                if asset_key is None:
                    continue

                # 各资产类型的提取语义见 asset.extract_asset
                content, conflicts = extract_asset(obj, ctx)
                skel_conflicts.extend(conflicts)
                if content is not None:
                    patch[asset_key] = content
            except Exception as e:
                self.log(f"  > ⚠️ {t('log.extractor.extraction_failed', name=obj.peek_name() or 'N/A', error=e)}")
        
        if replace_all:
            patch["__mode__"] = {"ALL"}

        return patch, skel_conflicts


# -------- Bundle 分析器 --------

BundleAnalyzer = Callable[[BundleFileInfo], None]


def analyze_trailing(item: BundleFileInfo) -> None:
    """分析尾部字节"""
    trailing = Bundle.get_trailing_bytes(item.path)
    content = None
    if trailing is not None and trailing > 0:
        content = Bundle.get_trailing_content(item.path, trailing)
    item.trailing_bytes = trailing
    item.trailing_content = content


def analyze_naming(item: BundleFileInfo) -> None:
    """分析文件名"""
    item.parsed_name = parse_filename(item.path.name)


def analyze_crc(item: BundleFileInfo) -> None:
    """计算实际 CRC32"""
    item.crc_actual = compute_crc32(item.path)


BUNDLE_ANALYZERS: dict[str, BundleAnalyzer] = {
    "trailing": analyze_trailing,
    "naming": analyze_naming,
    "crc": analyze_crc,
}


def analyze_bundles(
    items: list[BundleFileInfo],
    analyzer_names: list[str],
    progress_callback: ProgressCallback | None = None,
) -> None:
    """
    对已有的 BundleFileInfo 列表运行指定的分析器，原地修改。

    Args:
        items: 待分析的 BundleFileInfo 列表
        analyzer_names: 要运行的分析器名称列表（对应 BUNDLE_ANALYZERS 的 key）
        progress_callback: 进度回调函数，接收 (已完成数, 总数, 文件名)
    """
    analyzers = [
        BUNDLE_ANALYZERS[name]
        for name in analyzer_names
        if name in BUNDLE_ANALYZERS
    ]
    if not analyzers:
        return

    total = len(items)
    # 节流进度回调，避免海量文件时的高频 GUI 更新
    if progress_callback:
        progress_callback = throttle_progress(progress_callback)
    for i, item in enumerate(items):
        for analyzer in analyzers:
            analyzer(item)
        progress_callback(i + 1, total, item.path.name)


# 需要补充备份 textassets 的 Spine 相关分类（立绘 / 记忆大厅 / Spine 背景）
SPINE_MOD_CATEGORIES = {"spinecharacters", "spinelobbies", "spinebackground"}

# 同 prefix 候选的 res_type 初筛：JP 格式的 textassets + 现代格式的数字编码（类型需从内容判断）
_TEXTASSET_CANDIDATE_RES_TYPES = {"textassets"} | RESOURCE_TYPES_NUM


def find_textasset_companions(
    mod_files: list[Path],
    items: list[BundleFileInfo],
    game_dir: Path,
    log: LogFunc = no_log,
    should_stop: Callable[[], bool] | None = None,
) -> list[Path]:
    """查找需要随 mod 一并补充备份的 textassets bundle。

    直接修改 png 的 spine mod 不会改动对应的 textassets bundle（无 trailing bytes，
    不会被 trailing 检测识别为 mod），但游戏更新后新版 textassets 会与已修改的贴图
    失配（atlas 切分信息存于 textassets 中）。备份当前的 textassets 后，重新打包
    一次即可恢复。

    以 prefix 对 mod 文件聚类：组内不含 textassets 类型的 mod 文件、且分类属于
    Spine 相关时，在游戏主目录中查找同 prefix 且实际包含 TextAsset 资产的 bundle，
    纳入备份列表。

    Args:
        mod_files: 已检测出的 mod 文件路径列表
        items: 全量 bundle 扫描结果（候选查找来源）
        game_dir: 游戏资源主目录（仅在该目录范围内查找）
        log: 日志记录函数
        should_stop: 可选的停止检查函数，返回 True 时中止查找

    Returns:
        需要补充备份的 textassets bundle 路径列表
    """
    # 1. 按 prefix 聚类 mod 文件
    grouped: dict[str, list[ParsedFilename]] = {}
    for path in mod_files:
        parsed = parse_filename(path.name)
        grouped.setdefault(parsed.prefix, []).append(parsed)

    mod_set = set(mod_files)

    # 2. 一次遍历建立 prefix → 候选 索引（仅游戏主目录、非 mod 文件，res_type 初筛），
    #    避免逐组重复解析全部文件名
    candidates_by_prefix: dict[str, list[tuple[Path, ParsedFilename]]] = {}
    for item in items:
        path = item.path
        if path in mod_set or not path.is_relative_to(game_dir):
            continue
        parsed = parse_filename(path.name)
        if parsed.res_type not in _TEXTASSET_CANDIDATE_RES_TYPES:
            continue
        candidates_by_prefix.setdefault(parsed.prefix, []).append((path, parsed))

    companions: list[Path] = []
    for prefix, parsed_list in grouped.items():
        if should_stop and should_stop():
            break
        # 组内已有 textassets 类型的 mod 文件则无需补充
        if any(p.res_type == "textassets" for p in parsed_list):
            continue
        # 仅处理 Spine 相关分类
        if not any(p.category in SPINE_MOD_CATEGORIES for p in parsed_list):
            continue

        for path, parsed in candidates_by_prefix.get(prefix, ()):
            if should_stop and should_stop():
                return companions

            # 3. JP 命名格式的文件名已明确标注 textassets，直接纳入（避免逐个完整加载）
            #    数字编码格式无法从文件名判断类型，才加载内容确认包含 TextAsset 资产
            if parsed.res_type != "textassets":
                log(t("log.backup.companion_checking", filename=path.name))
                bundle = Bundle.load(path, log)
                if bundle is None:
                    continue
                if not any(obj.type == AssetType.TextAsset for obj in bundle.env.objects):
                    continue
                log(t("log.backup.companion_matched", filename=path.name))

            companions.append(path)

    return companions
