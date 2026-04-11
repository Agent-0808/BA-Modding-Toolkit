# bundle.py

import traceback
from pathlib import Path

import UnityPy
from UnityPy.files import SerializedFile
from UnityPy.environment import Environment as Env
from PIL import Image

from .i18n import t
from .utils import CRCUtils, SpineUtils, no_log
from .models import (
    AssetKey, AssetContent, AssetType,
    KeyGeneratorFunc, LogFunc, CompressionType, ReplacementResult,
    SaveOptions, SpineOptions,
    REPLACEABLE_ASSET_TYPES
)


class Bundle:
    """
    封装蔚蓝档案 Bundle 文件的业务类。
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
    
    def is_empty(self) -> bool:
        """检查 Bundle 是否为空（不包含任何文件）"""
        return len(self.env.files) == 0
    
    @property
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
    
    @classmethod
    def load(cls, bundle_path: Path, log: LogFunc = no_log) -> 'Bundle | None':
        """
        尝试加载一个 Unity bundle 文件。
        如果直接加载失败，会尝试移除末尾的几个字节后再次加载。
        
        Returns:
            Bundle 实例，如果加载失败则返回 None
        """
        try:
            env = UnityPy.load(str(bundle_path))
            return cls(bundle_path, env, log)
        except Exception:
            pass
        
        try:
            with open(bundle_path, "rb") as f:
                data = f.read()
        except Exception as e:
            log(f'  ❌ {t("log.file.read_in_memory_failed", name=bundle_path.name, error=e)}')
            return None
        
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
        from .core import parse_filename  # 延迟导入避免循环依赖
        
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
                _, _, _, _, crc_str = parse_filename(output_path.name)
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
    
    def apply_replacements(
        self,
        replacement_map: dict[AssetKey, AssetContent],
        key_func: KeyGeneratorFunc
    ) -> ReplacementResult:
        """
        将"替换清单"中的资源应用到当前的 bundle。

        Args:
            replacement_map: 资源替换清单，格式为 { asset_key: content }。
            key_func: 用于从目标环境中的对象生成 asset_key 的函数。

        Returns:
            ReplacementResult: 包含替换结果的数据类，包括实际替换数量、跳过数量、日志和未匹配键。
        """
        replacement_count = 0
        skipped_count = 0
        replaced_assets_log = []
        
        tasks = replacement_map.copy()
        
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
                    
                    replacement_count += 1
                    key_display = str(asset_key)
                    log_message = f"[{obj.type.name}] {resource_name} (key: {key_display})"
                    replaced_assets_log.append(log_message)
            
            except Exception as e:
                resource_name_for_error = obj.peek_name() or t("log.unnamed_resource", type=obj.type.name)
                self.log(f'  ❌ {t("common.error")}: {t("log.replace_resource_failed", name=resource_name_for_error, type=obj.type.name, error=e)}')
                self.log(traceback.format_exc())
        
        return ReplacementResult(
            replaced_count=replacement_count,
            skipped_count=skipped_count,
            replaced_logs=replaced_assets_log,
            unmatched_keys=list(tasks.keys())
        )
    
    def extract_assets_for_migration(
        self,
        asset_types_to_replace: set[str],
        key_func: KeyGeneratorFunc,
        spine_options: SpineOptions | None = None
    ) -> dict[AssetKey, AssetContent]:
        """
        从当前 Bundle 提取资源，生成 replacement_map。
        
        Args:
            asset_types_to_replace: 要替换的资源类型集合（如 {"Texture2D", "TextAsset", "Mesh"} 或 {"ALL"}）
            key_func: 用于生成资源键的函数
            spine_options: Spine 资源升级选项
            
        Returns:
            资源替换清单 { asset_key: content }
        """
        replacement_map: dict[AssetKey, AssetContent] = {}
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
                    replacement_map[asset_key] = content
            except Exception as e:
                self.log(f"  > ⚠️ {t('log.extractor.extraction_failed', name=getattr(data, 'm_Name', 'N/A'), error=e)}")
        
        if replace_all:
            replacement_map["__mode__"] = {"ALL"}
        
        return replacement_map
