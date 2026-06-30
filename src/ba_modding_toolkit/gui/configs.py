# gui/configs.py

import tkinter as tk
from pathlib import Path
from dataclasses import dataclass
from typing import Annotated, Any, TYPE_CHECKING
import toml

if TYPE_CHECKING:
    from .app import App

from ..utils import get_BA_path
from ..i18n import t


@dataclass
class ConfigMeta:
    """配置项元数据"""
    group: str           # TOML 中的 [Section]
    default: Any         # 默认值或返回默认值的函数
    key: str | None = None  # TOML 中的键名，默认取变量名去掉 _var
    depends_on: str | None = None  # 依赖的变量名（如 "spine_converter_path_var"）


def _get_default_game_dir() -> str:
    """获取默认游戏目录（国际服）"""
    return get_BA_path("global") or ""


def _get_default_game_dir_japan() -> str:
    """获取默认游戏目录（日服）"""
    return get_BA_path("japan") or ""


def _get_default_file_source() -> str:
    """获取默认文件源"""
    if get_BA_path("global"):
        return "windows_global"
    if get_BA_path("japan"):
        return "windows_japan"
    return "windows_global"


def _get_default_output_dir() -> str:
    """获取默认输出目录"""
    return str(Path.cwd() / "output")

def _get_default_adb_cache_dir() -> str:
    """获取默认ADB缓存目录"""
    return str(Path.cwd() / "adb_cache")


def _get_default_android_global_dir() -> str:
    """获取默认 Android 国际服目录"""
    return "/storage/emulated/0/Android/data/com.nexon.bluearchive/files/PUB/Resource/"


def _get_default_android_japan_dir() -> str:
    """获取默认 Android 日服目录"""
    return "/storage/emulated/0/Android/data/com.Yostar JP.BlueArchive/files/"


class ConfigMixin:
    """配置项定义 Mixin"""
    
    # Directories
    file_source_var: Annotated[tk.StringVar, ConfigMeta("Directories", _get_default_file_source)]
    game_resource_dir_var: Annotated[tk.StringVar, ConfigMeta("Directories", _get_default_game_dir)]
    game_resource_dir_japan_var: Annotated[tk.StringVar, ConfigMeta("Directories", _get_default_game_dir_japan)]
    game_dir_android_global_var: Annotated[tk.StringVar, ConfigMeta("Directories", _get_default_android_global_dir)]
    game_dir_android_japan_var: Annotated[tk.StringVar, ConfigMeta("Directories", _get_default_android_japan_dir)]
    
    # AppSettings
    language_var: Annotated[tk.StringVar, ConfigMeta("AppSettings", "")]
    output_dir_var: Annotated[tk.StringVar, ConfigMeta("AppSettings", _get_default_output_dir)]
    
    # SaveOptions (原 GlobalOptions)
    extra_bytes_var: Annotated[tk.StringVar, ConfigMeta("SaveOptions", "0x08080808")]
    enable_crc_correction_var: Annotated[tk.StringVar, ConfigMeta("SaveOptions", "auto")]
    create_backup_var: Annotated[tk.BooleanVar, ConfigMeta("SaveOptions", True)]
    compression_method_var: Annotated[tk.StringVar, ConfigMeta("SaveOptions", "lzma")]
    skip_unchanged_var: Annotated[tk.BooleanVar, ConfigMeta("SaveOptions", True)]
    
    # ResourceTypes
    replace_texture2d_var: Annotated[tk.BooleanVar, ConfigMeta("ResourceTypes", True)]
    replace_textasset_var: Annotated[tk.BooleanVar, ConfigMeta("ResourceTypes", True)]
    replace_mesh_var: Annotated[tk.BooleanVar, ConfigMeta("ResourceTypes", True)]
    replace_all_var: Annotated[tk.BooleanVar, ConfigMeta("ResourceTypes", False)]
    
    # SpineConverter
    spine_converter_path_var: Annotated[tk.StringVar, ConfigMeta("SpineConverter", "")]
    enable_spine_conversion_var: Annotated[tk.BooleanVar, ConfigMeta("SpineConverter", False, depends_on="spine_converter_path_var")]
    target_spine_version_var: Annotated[tk.StringVar, ConfigMeta("SpineConverter", "4.2.33", depends_on="spine_converter_path_var")]
    
    # SpineDowngrade
    enable_atlas_downgrade_var: Annotated[tk.BooleanVar, ConfigMeta("SpineDowngrade", False, depends_on="spine_converter_path_var")]
    spine_downgrade_version_var: Annotated[tk.StringVar, ConfigMeta("SpineDowngrade", "3.8.75", depends_on="spine_converter_path_var")]

    # SpineViewer
    spine_viewer_path_var: Annotated[tk.StringVar, ConfigMeta("SpineViewer", "")]

    # CharacterMap
    bacii_map_path_var: Annotated[tk.StringVar, ConfigMeta("BACIIMap", "")]
    character_name_field_var: Annotated[tk.StringVar, ConfigMeta("BACIIMap", "full_name")]

    # Tabs
    enable_spine38_namefix_var: Annotated[tk.BooleanVar, ConfigMeta("Tabs", False)]
    enable_bleed_var: Annotated[tk.BooleanVar, ConfigMeta("Tabs", False)]
    unpack_atlas_var: Annotated[tk.BooleanVar, ConfigMeta("Tabs", False)]

    # ADB
    adb_path_var: Annotated[tk.StringVar, ConfigMeta("ADB", "adb")]
    adb_device_var: Annotated[tk.StringVar, ConfigMeta("ADB", "")]
    adb_cache_dir_var: Annotated[tk.StringVar, ConfigMeta("ADB", _get_default_adb_cache_dir)]


class ConfigManager:
    """配置管理类，负责保存和读取应用设置到config.toml文件"""
    
    def __init__(self, config_file="config.toml"):
        self.config_file = Path(config_file)
        
    def save_config(self, app: "App"):
        """保存当前应用配置到文件"""
        try:
            data: dict[str, dict] = {}
            for var_name, meta in app._config_specs.items():
                if meta.group not in data:
                    data[meta.group] = {}
                var = getattr(app, var_name)
                key = meta.key or var_name.removesuffix("_var")
                data[meta.group][key] = var.get()
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                toml.dump(data, f)
            return True
        except Exception as e:
            print(t("log.config.save_failed", error=e))
            return False
    
    def load_config(self, app: "App"):
        """从文件加载配置到应用实例"""
        try:
            if not self.config_file.exists():
                return False
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                data = toml.load(f)
            
            for var_name, meta in app._config_specs.items():
                group_data = data.get(meta.group, {})
                key = meta.key or var_name.removesuffix("_var")
                var = getattr(app, var_name)
                if key in group_data:
                    var.set(group_data[key])
                elif callable(meta.default):
                    var.set(meta.default())
                else:
                    var.set(meta.default)
            
            return True
        except Exception as e:
            print(t("message.process_failed", error=e))
            return False
