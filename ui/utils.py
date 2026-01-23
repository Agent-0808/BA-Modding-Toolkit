# ui/utils.py

import sys
import subprocess
import os
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import shutil
import toml
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from ui.app import App

from utils import no_log
from i18n import t

def is_multiple_drop(data: str) -> bool:
    """
    检查拖放事件的数据是否包含多个文件路径。
    多个文件的 event.data 通常是 '{path1} {path2}' 的形式。
    """
    return '} {' in data

def handle_drop(event: tk.Event, 
                callback: Callable[[Path], None],
                allow_multiple: bool = False,
                error_title: str = None,
                error_message: str = None,
                validation_callback: Callable[[Path], bool] | None = None) -> bool:
    """
    通用的拖放事件处理函数
    
    Args:
        event: 拖放事件对象
        callback: 处理单个文件路径的回调函数，接收Path对象
        allow_multiple: 是否允许多个文件，默认为False
        error_title: 错误提示标题，默认为"message.invalid_operation"
        error_message: 错误提示消息，默认为"message.drop_single_file"
        validation_callback: 自定义验证函数，接收Path对象，返回bool表示是否有效
    
    Returns:
        是否成功处理（False表示因多文件限制或验证失败而未处理）
    """
    if is_multiple_drop(event.data):
        if not allow_multiple:
            messagebox.showwarning(
                error_title or t("message.invalid_operation"), 
                error_message or t("message.drop_single_file")
            )
            return False
        else:
            paths = [Path(p) for p in event.widget.tk.splitlist(event.data)]
            for path in paths:
                if validation_callback and not validation_callback(path):
                    return False
                callback(path)
            return True
    
    path = Path(event.data.strip('{}'))
    if validation_callback and not validation_callback(path):
        return False
    callback(path)
    return True

def open_directory(path: str | Path, log = no_log, create_if_not_exist: bool = False) -> None:
    """
    打开文件资源管理器。
    
    Args:
        path: 要打开的目录路径
        log: 日志函数，用于记录操作
        create_if_not_exist: 如果目录不存在，是否提示创建
    """
    
    try:
        path_obj = Path(path).resolve()
        if not path_obj.is_dir():
            if create_if_not_exist:
                if messagebox.askyesno(t("common.tip"), t("message.dir_not_found_create", path=path_obj)):
                    path_obj.mkdir(parents=True, exist_ok=True)
                else: 
                    return
            else:
                messagebox.showwarning(t("common.warning"), t("message.path_invalid", path=path_obj))
                return
        
        # 检测是否为 WSL 环境
        is_wsl = False
        if sys.platform == 'linux':
            try:
                with open('/proc/version', 'r') as f:
                    if 'microsoft' in f.read().lower():
                        is_wsl = True
            except Exception:
                pass

        # --- 打开目录 ---
        if sys.platform == 'win32':
            os.startfile(str(path_obj))
            
        elif is_wsl:
            # WSL 环境：先转换路径，再调用 Explorer
            try:
                # 使用 wslpath -w 将 Linux 路径转换为 Windows 路径
                result = subprocess.run(
                    ['wslpath', '-w', str(path_obj)], 
                    capture_output=True, text=True, check=True
                )
                windows_path = result.stdout.strip()

                subprocess.run(['explorer.exe', windows_path])
                path_obj = Path(windows_path)  # 更新路径为Windows路径
                
            except subprocess.CalledProcessError as e:
                log(t("log.process_failed", error=e))
                messagebox.showerror(t("common.error"), t("message.cannot_open_explorer", error=e))
                return
            
        else:
            # Linux/macOS
            try:
                if sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', str(path_obj)], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', str(path_obj)], check=True)
                
            except (subprocess.CalledProcessError, FileNotFoundError):
                messagebox.showinfo(t("common.tip"), t("message.open_manually", path=path_obj))
                return
        
        # 统一记录成功打开目录的日志
        log(t("log.file.directory_opened", path=path_obj))
                
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))

def replace_file(source_path: Path, 
                    dest_path: Path, 
                    create_backup: bool = True, 
                    ask_confirm: bool = True,
                    confirm_message: str = "",
                    log = no_log, 
                ) -> bool: 
    """ 
    安全地替换文件，包含确认、备份和日志记录功能。 
    返回操作是否成功。 
    """ 
    if not source_path or not source_path.exists(): 
        messagebox.showerror(t("common.error"), t("message.file_not_found", path=source_path)) 
        return False 
    if not dest_path or not dest_path.exists(): 
        messagebox.showerror(t("common.error"), t("message.file_not_found", path=dest_path)) 
        return False 
    if source_path == dest_path: 
        messagebox.showerror(t("common.error"), t("message.same_file")) 
        return False

    if ask_confirm and not messagebox.askyesno(t("common.warning"), confirm_message): 
        return False 

    try: 
        if create_backup: 
            backup_path = dest_path.with_suffix(dest_path.suffix + '.backup') 
            
            try:
                shutil.copy2(dest_path, backup_path) 
            except Exception as e:
                log(t("log.file.backup_failed", error=e)) 
                messagebox.showerror(t("common.error"), t("message.process_failed", error=e)) 
                return False
            log(t("log.file.backed_up", path=backup_path)) 
        
        log(t("log.file.overwritten", path=dest_path)) 
        shutil.copy2(source_path, dest_path) 
        
        log(t("log.status.done")) 
        messagebox.showinfo(t("common.success"), t("message.process_success")) 
        return True 

    except Exception as e: 
        log(t("log.process_failed", error=e)) 

        messagebox.showerror(t("common.error"), t("message.process_failed", error=e)) 
        return False 

def select_directory(var: tk.Variable = None, title="", log=no_log):
    """
    选择目录并更新变量或返回路径
    
    Args:
        var: tkinter变量，用于存储选择的目录路径，如果为None则直接返回路径
        title: 目录选择对话框的标题
        log: 日志函数，用于记录操作
        
    Returns:
        如果var为None，返回选择的目录路径字符串，否则返回None
    """
    try:
        initial_dir = str(Path.home())
        if var is not None:
            current_path = Path(var.get())
            if current_path.is_dir(): 
                initial_dir = str(current_path)
                
        selected_dir = filedialog.askdirectory(title=title, initialdir=initial_dir)
        if selected_dir:
            if var is not None:
                var.set(str(Path(selected_dir)))
                log(t("log.file.loaded", path=selected_dir))
                return None
            else:
                log(t("log.file.loaded", path=selected_dir))
                return selected_dir
        return None
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
        return None

def select_file(title: str, 
                filetypes: list[tuple[str, str]] | None = None, 
                multiple: bool = False,
                callback: Callable[[Path | list[Path]], None] | None = None,
                log = no_log) -> Path | list[Path] | None:
    """
    统一的文件选择对话框函数
    
    Args:
        title: 对话框标题
        filetypes: 文件类型过滤器，如 [("Bundle文件", "*.bundle"), ("所有文件", "*.*")]
        multiple: 是否支持多选
        callback: 选择文件后的回调函数，接收Path或Path列表作为参数
        log: 日志函数，用于记录操作
        
    Returns:
        单选时返回Path或None，多选时返回Path列表或空列表
    """
    try:
        if filetypes is None:
            filetypes = [(t("file_type.all_files"), "*.*")]
            
        if multiple:
            filepaths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
            if filepaths:
                paths = [Path(p) for p in filepaths]
                log(t("log.file.loaded", path=f"{len(paths)} files"))
                if callback:
                    callback(paths)
                return paths
            return []
        else:
            filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
            if filepath:
                path = Path(filepath)
                log(t("log.file.loaded", path=path))
                if callback:
                    callback(path)
                return path
            return None
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
        return [] if multiple else None



# --- 配置管理类 ---

class ConfigManager:
    """配置管理类，负责保存和读取应用设置到config.toml文件"""
    
    def __init__(self, config_file="config.toml"):
        self.config_file = Path(config_file)
        
    def save_config(self, app: "App"):
        """保存当前应用配置到文件"""
        try:
            data = {
                "Directories": {
                    "game_resource_dir": app.game_resource_dir_var.get(),
                    "auto_detect_subdirs": app.auto_detect_subdirs_var.get(),
                    "auto_search": app.auto_search_var.get()
                },
                "AppSettings": {
                    "language": app.language_var.get(),
                    "output_dir": app.output_dir_var.get()
                },
                "GlobalOptions": {
                    "enable_padding": app.enable_padding_var.get(),
                    "enable_crc_correction": app.enable_crc_correction_var.get(),
                    "create_backup": app.create_backup_var.get(),
                    "compression_method": app.compression_method_var.get()
                },
                "ResourceTypes": {
                    "replace_texture2d": app.replace_texture2d_var.get(),
                    "replace_textasset": app.replace_textasset_var.get(),
                    "replace_mesh": app.replace_mesh_var.get(),
                    "replace_all": app.replace_all_var.get()
                },
                "SpineConverter": {
                    "enable_spine_conversion": app.enable_spine_conversion_var.get(),
                    "spine_converter_path": app.spine_converter_path_var.get(),
                    "target_spine_version": app.target_spine_version_var.get()
                },
                "SpineDowngrade": {
                    "enable_atlas_downgrade": app.enable_atlas_downgrade_var.get(),
                    "atlas_downgrade_path": app.atlas_downgrade_path_var.get(),
                    "spine_downgrade_version": app.spine_downgrade_version_var.get()
                },
                "Tabs": {
                    "enable_spine38_namefix": app.enable_spine38_namefix_var.get(),
                    "enable_bleed": app.enable_bleed_var.get()
                }
            }
            
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
            
            dirs: dict[str] = data.get("Directories", {})
            app.game_resource_dir_var.set(dirs.get("game_resource_dir", ""))
            app.auto_detect_subdirs_var.set(dirs.get("auto_detect_subdirs", False))
            app.auto_search_var.set(dirs.get("auto_search", False))
            
            app_settings = data.get("AppSettings", {})
            if not hasattr(app, 'language_var'):
                app.language_var = tk.StringVar()
            app.language_var.set(app_settings.get("language", ""))
            app.output_dir_var.set(app_settings.get("output_dir", ""))
            
            global_options = data.get("GlobalOptions", {})
            app.enable_padding_var.set(global_options.get("enable_padding", False))
            app.enable_crc_correction_var.set(global_options.get("enable_crc_correction", "auto"))
            app.create_backup_var.set(global_options.get("create_backup", False))
            app.compression_method_var.set(global_options.get("compression_method", ""))
            
            resource_types = data.get("ResourceTypes", {})
            app.replace_texture2d_var.set(resource_types.get("replace_texture2d", False))
            app.replace_textasset_var.set(resource_types.get("replace_textasset", False))
            app.replace_mesh_var.set(resource_types.get("replace_mesh", False))
            app.replace_all_var.set(resource_types.get("replace_all", False))
            
            spine_converter = data.get("SpineConverter", {})
            app.enable_spine_conversion_var.set(spine_converter.get("enable_spine_conversion", False))
            app.spine_converter_path_var.set(spine_converter.get("spine_converter_path", ""))
            app.target_spine_version_var.set(spine_converter.get("target_spine_version", ""))
            
            spine_downgrade = data.get("SpineDowngrade", {})
            app.enable_atlas_downgrade_var.set(spine_downgrade.get("enable_atlas_downgrade", False))
            app.atlas_downgrade_path_var.set(spine_downgrade.get("atlas_downgrade_path", ""))
            app.spine_downgrade_version_var.set(spine_downgrade.get("spine_downgrade_version", ""))
            
            tabs = data.get("Tabs", {})
            app.enable_spine38_namefix_var.set(tabs.get("enable_spine38_namefix", False))
            app.enable_bleed_var.set(tabs.get("enable_bleed", False))
            
            return True
        except Exception as e:
            print(t("message.process_failed", error=e))
            return False