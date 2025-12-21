# ui/utils.py

import sys
import subprocess
import os
import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path
import shutil
import configparser
from typing import Callable

from utils import no_log
from i18n import t

def is_multiple_drop(data: str) -> bool:
    """
    检查拖放事件的数据是否包含多个文件路径。
    多个文件的 event.data 通常是 '{path1} {path2}' 的形式。
    """
    return '} {' in data

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
        backup_message = "" 
        if create_backup: 
            backup_path = dest_path.with_suffix(dest_path.suffix + '.backup') 
            log(t("log.file.backed_up", path=backup_path)) 
            shutil.copy2(dest_path, backup_path) 
            backup_message = t("message.file_not_found", path=backup_path)
        
        log(t("log.file.overwritten", path=dest_path)) 
        shutil.copy2(source_path, dest_path) 
        
        log(t("log.status.done")) 
        messagebox.showinfo(t("common.success"), t("message.process_success")) 
        return True 

    except Exception as e: 
        log(t("log.process_failed", error=e)) 

        messagebox.showerror(t("common.error"), t("message.process_failed", error=e)) 
        return False 

def select_directory(var: tk.Variable = None, title="", logger=no_log):
    """
    选择目录并更新变量或返回路径
    
    Args:
        var: tkinter变量，用于存储选择的目录路径，如果为None则直接返回路径
        title: 目录选择对话框的标题
        logger: 日志函数，用于记录操作
        
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
                logger(t("log.file.loaded", path=selected_dir))
                return None
            else:
                logger(t("log.file.loaded", path=selected_dir))
                return selected_dir
        return None
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
        return None

def select_file(title: str, 
                filetypes: list[tuple[str, str]] | None = None, 
                multiple: bool = False,
                callback: Callable[[Path | list[Path]], None] | None = None,
                logger = no_log) -> Path | list[Path] | None:
    """
    统一的文件选择对话框函数
    
    Args:
        title: 对话框标题
        filetypes: 文件类型过滤器，如 [("Bundle文件", "*.bundle"), ("所有文件", "*.*")]
        multiple: 是否支持多选
        callback: 选择文件后的回调函数，接收Path或Path列表作为参数
        logger: 日志函数，用于记录操作
        
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
                logger(t("log.file.loaded", path=f"{len(paths)} files"))
                if callback:
                    callback(paths)
                return paths
            return []
        else:
            filepath = filedialog.askopenfilename(title=title, filetypes=filetypes)
            if filepath:
                path = Path(filepath)
                logger(t("log.file.loaded", path=path))
                if callback:
                    callback(path)
                return path
            return None
    except Exception as e:
        messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
        return [] if multiple else None



# --- 配置管理类 ---

class ConfigManager:
    """配置管理类，负责保存和读取应用设置到config.ini文件"""
    
    def __init__(self, config_file="config.ini"):
        self.config_file = Path(config_file)
        self.config = configparser.ConfigParser()
        
    def save_config(self, app_instance):
        """保存当前应用配置到文件"""
        try:
            # 清空现有配置
            self.config.clear()
            
            # 添加目录设置
            self.config['Directories'] = {
                'game_resource_dir': app_instance.game_resource_dir_var.get(),
                'output_dir': app_instance.output_dir_var.get(),
                'auto_detect_subdirs': str(app_instance.auto_detect_subdirs_var.get())
            }
            
            # 添加全局选项
            self.config['GlobalOptions'] = {
                'enable_padding': str(app_instance.enable_padding_var.get()),
                'enable_crc_correction': str(app_instance.enable_crc_correction_var.get()),
                'create_backup': str(app_instance.create_backup_var.get()),
                'compression_method': app_instance.compression_method_var.get(),
                'auto_search': str(app_instance.auto_search_var.get())
            }
            
            # 添加资源类型选项
            self.config['ResourceTypes'] = {
                'replace_texture2d': str(app_instance.replace_texture2d_var.get()),
                'replace_textasset': str(app_instance.replace_textasset_var.get()),
                'replace_mesh': str(app_instance.replace_mesh_var.get()),
                'replace_all': str(app_instance.replace_all_var.get())
            }
            
            # 添加Spine转换器选项
            self.config['SpineConverter'] = {
                'enable_spine_conversion': str(app_instance.enable_spine_conversion_var.get()),
                'spine_converter_path': app_instance.spine_converter_path_var.get(),
                'target_spine_version': app_instance.target_spine_version_var.get()
            }
            
            # 添加Spine降级选项
            self.config['SpineDowngrade'] = {
                'enable_atlas_downgrade': str(app_instance.enable_atlas_downgrade_var.get()),
                'atlas_downgrade_path': app_instance.atlas_downgrade_path_var.get(),
                'spine_downgrade_version': app_instance.spine_downgrade_version_var.get()
            }
            
            # 添加语言设置
            self.config['Language'] = {
                'language': app_instance.language_var.get()
            }
            
            # 写入文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
                
            return True
        except Exception as e:
            print(t("log.config.save_failed", error=e))
            return False
    
    def load_config(self, app_instance):
        """从文件加载配置到应用实例"""
        try:
            if not self.config_file.exists():
                return False
                
            self.config.read(self.config_file, encoding='utf-8')
            
            # 加载目录设置
            if 'Directories' in self.config:
                if 'game_resource_dir' in self.config['Directories']:
                    app_instance.game_resource_dir_var.set(self.config['Directories']['game_resource_dir'])
                if 'output_dir' in self.config['Directories']:
                    app_instance.output_dir_var.set(self.config['Directories']['output_dir'])
                if 'auto_detect_subdirs' in self.config['Directories']:
                    app_instance.auto_detect_subdirs_var.set(self.config['Directories']['auto_detect_subdirs'].lower() == 'true')
            
            # 加载全局选项
            if 'GlobalOptions' in self.config:
                if 'enable_padding' in self.config['GlobalOptions']:
                    app_instance.enable_padding_var.set(self.config['GlobalOptions']['enable_padding'].lower() == 'true')
                if 'enable_crc_correction' in self.config['GlobalOptions']:
                    app_instance.enable_crc_correction_var.set(self.config['GlobalOptions']['enable_crc_correction'].lower() == 'true')
                if 'create_backup' in self.config['GlobalOptions']:
                    app_instance.create_backup_var.set(self.config['GlobalOptions']['create_backup'].lower() == 'true')
                if 'compression_method' in self.config['GlobalOptions']:
                    app_instance.compression_method_var.set(self.config['GlobalOptions']['compression_method'])
                if 'auto_search' in self.config['GlobalOptions']:
                    app_instance.auto_search_var.set(self.config['GlobalOptions']['auto_search'].lower() == 'true')
            
            # 加载资源类型选项
            if 'ResourceTypes' in self.config:
                if 'replace_texture2d' in self.config['ResourceTypes']:
                    app_instance.replace_texture2d_var.set(self.config['ResourceTypes']['replace_texture2d'].lower() == 'true')
                if 'replace_textasset' in self.config['ResourceTypes']:
                    app_instance.replace_textasset_var.set(self.config['ResourceTypes']['replace_textasset'].lower() == 'true')
                if 'replace_mesh' in self.config['ResourceTypes']:
                    app_instance.replace_mesh_var.set(self.config['ResourceTypes']['replace_mesh'].lower() == 'true')
                if 'replace_all' in self.config['ResourceTypes']:
                    app_instance.replace_all_var.set(self.config['ResourceTypes']['replace_all'].lower() == 'true')
            
            # 加载Spine转换器选项
            if 'SpineConverter' in self.config:
                if 'spine_converter_path' in self.config['SpineConverter']:
                    app_instance.spine_converter_path_var.set(self.config['SpineConverter']['spine_converter_path'])
                if 'enable_spine_conversion' in self.config['SpineConverter']:
                    app_instance.enable_spine_conversion_var.set(self.config['SpineConverter']['enable_spine_conversion'].lower() == 'true')
                if 'target_spine_version' in self.config['SpineConverter']:
                    app_instance.target_spine_version_var.set(self.config['SpineConverter']['target_spine_version'])
            
            # 加载Spine降级选项
            if 'SpineDowngrade' in self.config:
                if 'atlas_downgrade_path' in self.config['SpineDowngrade']:
                    app_instance.atlas_downgrade_path_var.set(self.config['SpineDowngrade']['atlas_downgrade_path'])
                if 'enable_atlas_downgrade' in self.config['SpineDowngrade']:
                    app_instance.enable_atlas_downgrade_var.set(self.config['SpineDowngrade']['enable_atlas_downgrade'].lower() == 'true')
                if 'spine_downgrade_version' in self.config['SpineDowngrade']:
                    app_instance.spine_downgrade_version_var.set(self.config['SpineDowngrade']['spine_downgrade_version'])
            
            # 加载语言设置
            if 'Language' in self.config and 'language' in self.config['Language']:
                # 如果language_var不存在，创建它
                if not hasattr(app_instance, 'language_var'):
                    import tkinter as tk
                    app_instance.language_var = tk.StringVar()
                app_instance.language_var.set(self.config['Language']['language'])
            
            return True
        except Exception as e:
            print(t("message.process_failed", error=e))
            return False