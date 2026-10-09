# bundle.py

import re
import traceback
from functools import cached_property
from pathlib import Path
from typing import Callable

import UnityPy
from UnityPy.files import File, SerializedFile
from UnityPy.environment import Environment as Env
from PIL import Image

from .i18n import t
from .utils import CRCUtils, no_log, throttle_progress
from .spine import SkelConverter, check_skel_animation_diff
from .naming import RESOURCE_TYPES_NUM, parse_filename
from .models import (
    AssetKey, AssetContent, AssetType, Patch, KeyFunc,
    NameTypeKey, ContNameTypeKey, MatchStrategy, LogFunc,
    CompressionType, PatchResult, ReplaceAssetType,
    SaveOptions, SkelConvertOptions, AnimCheckOptions, ParsedFilename,
    BundleFileInfo, ProgressCallback, SkelVersionConflict,
    RawAssetBytes, REPLACEABLE_ASSET_TYPES
)

# 对象序列化数据中的流式引用 basename（m_StreamData.path / m_Resource.m_Source，如 CAB-xxx.resS）
STREAM_REF_PATTERN = re.compile(rb"[A-Za-z0-9_\-]+\.(?:resS|resource)")


def find_stream_refs(data: bytes) -> set[str]:
    """提取序列化数据中引用的附属流文件名（.resS/.resource）"""
    return {m.decode() for m in STREAM_REF_PATTERN.findall(data)}


def collect_stream_companions(raw: bytes, env_file: File) -> dict[str, bytes] | None:
    """按 raw 内容中的引用 basename 从 bundle 内部文件收集附属流文件

    引用藏在对象 raw 字节内而非序列化引用表，必须按内容匹配收集，
    不能按 bundle 初始文件列表快照（二次提取需携带历史 companion）。

    Returns:
        {basename: 字节}；引用了 bundle 内不存在的文件时返回 None（悬空引用）
    """
    refs = find_stream_refs(raw)
    if not refs:
        return {}
    files = {name: f for name, f in env_file.files.items() if not hasattr(f, "objects")}
    companions: dict[str, bytes] = {}
    for ref in refs:
        entry = files.get(ref)
        if entry is None:
            return None
        companions[ref] = entry.bytes
    return companions


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
        try:
            with open(bundle_path, 'rb') as f:
                # 读取签名 (以 null 结尾)
                signature = bytearray()
                while True:
                    byte = f.read(1)
                    if byte == b'\x00':
                        break
                    signature.extend(byte)
                
                if signature != b'UnityFS':
                    return None
                
                # 读取 version (uint32)
                f.read(4)
                
                # 读取 version_player (以 null 结尾的字符串)
                while f.read(1) != b'\x00':
                    pass
                
                # 读取 version_engine (以 null 结尾的字符串)
                while f.read(1) != b'\x00':
                    pass
                
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
                
                corrected_data = CRCUtils.apply_crc_fix(
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
                    
                    # raw dump 内容（RawAssetBytes）：原样替换整个对象的序列化数据，优先于类型特定分支
                    if isinstance(content, RawAssetBytes):
                        # 附属流文件（companion）随替换写入目标 bundle，使内嵌流引用闭合。
                        # 约束：多份 .resS 并存是设计要求（目标自己的与各代 companion 的分别服务不同对象）；
                        # 任何"清理未使用条目"优化不得将无序列化引用的 .resS 当孤儿删除
                        # 引用内嵌于对象 raw 字节，常规引用分析不可见，误删会破坏已分发的 mod
                        for companion_name, companion_bytes in content.companions.items():
                            if companion_name in self.env.file.files:
                                self.log(f'  > ⚠️ {t("log.replace_companion_exists", name=companion_name)}')
                            else:
                                self.env.file.get_writeable_cab(companion_name).write(companion_bytes)
                        obj.set_raw_data(content)
                    elif obj.type == AssetType.Texture2D:
                        content: Image.Image
                        new_image = content
                        if (data.image.mode == new_image.mode
                                and data.image.size == new_image.size
                                and data.image.tobytes() == new_image.tobytes()):
                            self.log(f'  ⏭️ {t("log.replace_skipped_same_content", type=obj.type.name, name=resource_name)}')
                            skipped_count += 1
                            continue
                        data.image = new_image
                        data.save()
                    elif obj.type == AssetType.TextAsset:
                        content: bytes
                        target_bytes = data.m_Script.encode("utf-8", "surrogateescape")

                        if target_bytes == content:
                            self.log(f'  ⏭️ {t("log.replace_skipped_same_content", type=obj.type.name, name=resource_name)}')
                            skipped_count += 1
                            continue

                        # 就地检测动画差异
                        if anim_check and anim_check.is_valid() and resource_name.lower().endswith('.skel'):
                            self.log(f"  🔍 {t('log.spine.anim_check_comparing', name=resource_name)}")
                            missing_anims = check_skel_animation_diff(
                                source_skel=content,
                                target_skel=target_bytes,
                                viewer_path=anim_check.viewer_path,
                                log=self.log
                            )
                            if missing_anims:
                                anim_diffs[resource_name] = missing_anims
                                self.log(f"  ⚠️ {t('log.spine.anim_check_new_animations', name=resource_name, animations=', '.join(missing_anims))}")
                            else:
                                self.log(f"  ✓ {t('log.spine.anim_check_no_diff', name=resource_name)}")

                        data.m_Script = content.decode("utf-8", "surrogateescape")
                        data.save()
                    else:
                        # raw 类型（AnimationClip/Mesh 等）：内容相同则跳过，避免无效重存
                        if obj.get_raw_data() == content:
                            self.log(f'  ⏭️ {t("log.replace_skipped_same_content", type=obj.type.name, name=resource_name)}')
                            skipped_count += 1
                            continue
                        obj.set_raw_data(content)
                    
                    applied_count += 1
                    self.log(f'  ✅ {t("log.replace_applied", type=obj.type.name, name=resource_name)}')
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
        
        for obj in self.env.objects:
            try:
                data = obj.read()
                
                if obj.type not in REPLACEABLE_ASSET_TYPES:
                    continue
                
                if not replace_all and obj.type.name not in asset_types_to_replace:
                    continue
                
                asset_key = key_func(obj)
                if asset_key is None or not getattr(data, 'm_Name', None):
                    continue
                
                content: AssetContent | None = None
                resource_name: str = data.m_Name
                
                if obj.type == AssetType.Texture2D:
                    content: Image.Image = data.image
                elif obj.type == AssetType.TextAsset:
                    asset_bytes = data.m_Script.encode("utf-8", "surrogateescape")
                    if resource_name.lower().endswith('.skel'):
                        content, conflict = SkelConverter.ensure_version(
                            skel_bytes=asset_bytes,
                            resource_name=resource_name,
                            options=spine_options,
                            log=self.log
                        )
                        if conflict:
                            skel_conflicts.append(conflict)
                            continue
                    else:
                        content: bytes = asset_bytes
                elif replace_all or obj.type.name in asset_types_to_replace:
                    raw = obj.get_raw_data()
                    companions = collect_stream_companions(raw, self.env.file)
                    if companions is None:
                        # 流引用悬空（如历史版本 raw 替换遗留的坏数据）：
                        # 替换会把坏引用带进目标导致资源损坏，拒绝提取该对象
                        self.log(f"  > ⚠️ {t('log.extractor.stream_ref_dangling', name=resource_name)}")
                        continue
                    # 有流引用时附带 companion 随 patch 走，apply 侧写入目标 bundle
                    content: bytes = RawAssetBytes(raw, companions) if companions else raw
                
                if content is not None:
                    patch[asset_key] = content
            except Exception as e:
                self.log(f"  > ⚠️ {t('log.extractor.extraction_failed', name=getattr(data, 'm_Name', 'N/A'), error=e)}")
        
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
    item.crc_actual = CRCUtils.compute_crc32(item.path)


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
