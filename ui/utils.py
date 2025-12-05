# ui/utils.py

import tkinter as tk
from tkinter import messagebox
from pathlib import Path
import shutil
import configparser

from utils import no_log

def is_multiple_drop(data: str) -> bool:
    """
    检查拖放事件的数据是否包含多个文件路径。
    多个文件的 event.data 通常是 '{path1} {path2}' 的形式。
    """
    return '} {' in data

def open_directory(path: str | Path, log = no_log) -> None:
    """
    打开文件资源管理器。
    
    Args:
        path: 要打开的目录路径
        log: 日志函数，用于记录操作
    """
    import sys
    import subprocess
    import os
    from pathlib import Path
    from tkinter import messagebox
    
    try:
        path_obj = Path(path).resolve()
        if not path_obj.is_dir():
            messagebox.showwarning("警告", f"路径不存在或不是一个文件夹:\n{path_obj}")
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
            log(f"已打开目录: {path_obj}")
            
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
                log(f"已在 Windows 中打开目录: {windows_path}")
                
            except subprocess.CalledProcessError as e:
                log(f"WSL 路径转换或打开失败: {e}")
                messagebox.showerror("错误", f"无法在 Windows 中打开路径:\n{e}")
            
        else:
            # Linux/macOS
            try:
                if sys.platform == 'darwin':  # macOS
                    subprocess.run(['open', str(path_obj)], check=True)
                else:  # Linux
                    subprocess.run(['xdg-open', str(path_obj)], check=True)
                log(f"已打开目录: {path_obj}")
                
            except (subprocess.CalledProcessError, FileNotFoundError):
                messagebox.showinfo("提示", f"请手动打开目录:\n{path_obj}")
                
    except Exception as e:
        messagebox.showerror("错误", f"打开目录时发生错误:\n{e}")

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
        messagebox.showerror("错误", f"源文件不存在:\n{source_path}") 
        return False 
    if not dest_path or not dest_path.exists(): 
        messagebox.showerror("错误", f"目标文件不存在:\n{dest_path}") 
        return False 
    if source_path == dest_path: 
        messagebox.showerror("错误", "源文件和目标文件不能相同！") 
        return False

    if ask_confirm and not messagebox.askyesno("警告", confirm_message): 
        return False 

    try: 
        backup_message = "" 
        if create_backup: 
            backup_path = dest_path.with_suffix(dest_path.suffix + '.backup') 
            log(f"  > 正在备份原始文件到: {backup_path.name}") 
            shutil.copy2(dest_path, backup_path) 
            backup_message = f"\n\n原始文件备份至:\n{backup_path.name}" 
        
        log(f"  > 正在用 '{source_path.name}' 覆盖 '{dest_path.name}'...") 
        shutil.copy2(source_path, dest_path) 
        
        log("✅ 文件已成功覆盖！") 
        messagebox.showinfo("成功", f"文件已成功覆盖！{backup_message}") 
        return True 

    except Exception as e: 
        log(f"❌ 文件覆盖失败: {e}") 

        messagebox.showerror("错误", f"文件覆盖过程中发生错误:\n{e}") 
        return False 

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
            
            # 写入文件
            with open(self.config_file, 'w', encoding='utf-8') as f:
                self.config.write(f)
                
            return True
        except Exception as e:
            print(f"保存配置时出错: {e}")
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
            
            return True
        except Exception as e:
            print(f"加载配置时出错: {e}")
            return False