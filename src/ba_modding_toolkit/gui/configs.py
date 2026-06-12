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
    """获取默认游戏目录"""
    ba_path = get_BA_path()
    if ba_path:
        return str(Path(ba_path))
    return r"C:\Program Files (x86)\Steam\steamapps\common\BlueArchive"


def _get_default_output_dir() -> str:
    """获取默认输出目录"""
    return str(Path.cwd() / "output")


class ConfigMixin:
    """配置项定义 Mixin"""
    
    # Directories
    game_resource_dir_var: Annotated[tk.StringVar, ConfigMeta("Directories", _get_default_game_dir)]
    
    # AppSettings
    language_var: Annotated[tk.StringVar, ConfigMeta("AppSettings", "")]
    output_dir_var: Annotated[tk.StringVar, ConfigMeta("AppSettings", _get_default_output_dir)]
    character_name_field_var: Annotated[tk.StringVar, ConfigMeta("AppSettings", "full_name")]
    
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
    unpack_atlas_var: Annotated[tk.BooleanVar, ConfigMeta("SpineDowngrade", False)]

    # SpineViewer
    spine_viewer_path_var: Annotated[tk.StringVar, ConfigMeta("SpineViewer", "")]

    # Tabs
    enable_spine38_namefix_var: Annotated[tk.BooleanVar, ConfigMeta("Tabs", False)]
    enable_bleed_var: Annotated[tk.BooleanVar, ConfigMeta("Tabs", False)]


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
                default = meta.default() if callable(meta.default) else meta.default
                var.set(group_data.get(key, default))
            
            return True
        except Exception as e:
            print(t("message.process_failed", error=e))
            return False
