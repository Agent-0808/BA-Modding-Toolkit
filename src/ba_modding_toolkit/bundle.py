# bundle.py

import traceback
from functools import cached_property
from pathlib import Path

import UnityPy
from UnityPy.files import SerializedFile
from UnityPy.environment import Environment as Env
from PIL import Image

from .i18n import t
from .utils import CRCUtils, SpineUtils, no_log
from .naming import parse_filename
from .models import (
    AssetKey, AssetContent, AssetType, Patch, KeyFunc,
    NameTypeKey, ContNameTypeKey, MatchStrategy, LogFunc,
    CompressionType, PatchResult,
    SaveOptions, SpineOptions, ParsedFilename,
    REPLACEABLE_ASSET_TYPES
)


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
        save_kwargs = {}
        if compression == "original":
            pass
        elif compression == "none":
            save_kwargs['packer'] = ""
        else:
            save_kwargs['packer'] = compression
        
        return self.env.file.save(**save_kwargs)
    
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
        match_strategy: MatchStrategy = 'path_id'
    ) -> PatchResult:
        """
        将补丁中的资源应用到当前的 bundle。

        Args:
            patch: 资源补丁，格式为 { asset_key: content }。
            match_strategy: 匹配策略，用于从目标环境中的对象生成 asset_key。

        Returns:
            PatchResult: 包含修改结果的数据类，包括实际修改数量、跳过数量、日志和未匹配键。
        """
        key_func = self._get_key_func(match_strategy)
        applied_count = 0
        skipped_count = 0
        applied_assets_log = []
        matched_keys: list[AssetKey] = []
        
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
                    
                    if obj.type == AssetType.Texture2D:
                        content: Image.Image
                        new_image = content
                        if data.image.tobytes() == new_image.tobytes():
                            self.log(f'  ⏭️ {t("log.replace_skipped_same_content", type=obj.type.name, name=resource_name)}')
                            skipped_count += 1
                            continue
                        data.image = new_image
                        data.save()
                    elif obj.type == AssetType.TextAsset:
                        content: bytes
                        new_script = content.decode("utf-8", "surrogateescape")
                        if data.m_Script == new_script:
                            self.log(f'  ⏭️ {t("log.replace_skipped_same_content", type=obj.type.name, name=resource_name)}')
                            skipped_count += 1
                            continue
                        data.m_Script = new_script
                        data.save()
                    else:
                        obj.set_raw_data(content)
                    
                    applied_count += 1
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
            matched_keys=matched_keys
        )
    
    def extract_patch(
        self,
        asset_types_to_replace: set[str],
        match_strategy: MatchStrategy = 'path_id',
        spine_options: SpineOptions | None = None
    ) -> Patch:
        """
        从当前 Bundle 提取资源，生成补丁。
        
        Args:
            asset_types_to_replace: 要替换的资源类型集合（如 {"Texture2D", "TextAsset", "Mesh"} 或 {"ALL"}）
            match_strategy: 匹配策略，用于生成资源键
            spine_options: Spine 资源升级选项
            
        Returns:
            资源补丁 { asset_key: content }
        """
        key_func = self._get_key_func(match_strategy)
        patch: Patch = {}
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
                        content: bytes = SpineUtils.handle_skel_upgrade(
                            skel_bytes=asset_bytes,
                            resource_name=resource_name,
                            enabled=spine_options.enabled if spine_options else False,
                            converter_path=spine_options.converter_path if spine_options else None,
                            target_version=spine_options.target_version if spine_options else None,
                            log=self.log
                        )
                    else:
                        content: bytes = asset_bytes
                elif replace_all or obj.type.name in asset_types_to_replace:
                    content: bytes = obj.get_raw_data()
                
                if content is not None:
                    patch[asset_key] = content
            except Exception as e:
                self.log(f"  > ⚠️ {t('log.extractor.extraction_failed', name=getattr(data, 'm_Name', 'N/A'), error=e)}")
        
        if replace_all:
            patch["__mode__"] = {"ALL"}
        
        return patch
