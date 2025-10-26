# ui/app.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import os

from utils import get_environment_info
from .components import Theme, Logger
from .utils import ConfigManager
from .dialogs import SettingsDialog
from .tabs import ModUpdateTab, CrcToolTab, AssetPackerTab

class App(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.setup_main_window()
        self.config_manager = ConfigManager()
        self.init_shared_variables()
        self.create_widgets()
        self.load_config_on_startup()  # 启动时加载配置
        self.logger.status("准备就绪")

    def setup_main_window(self):
        self.master.title("BA Modding Toolkit")
        self.master.geometry("600x789")
        self.master.configure(bg=Theme.WINDOW_BG)

    def _set_default_values(self):
        """设置所有共享变量的默认值。"""
        # 尝试定位游戏根目录
        game_root_dir = Path(r"C:\Program Files (x86)\Steam\steamapps\common\BlueArchive")
        self.game_resource_dir_var.set(str(game_root_dir))
        self.auto_detect_subdirs_var.set(True)
        
        # 共享变量
        self.output_dir_var.set(str(Path.cwd() / "output"))
        self.enable_padding_var.set(False)
        self.enable_crc_correction_var.set(True)
        self.create_backup_var.set(True)
        self.compression_method_var.set("lzma")
        
        # 一键更新的资源类型选项
        self.replace_texture2d_var.set(True)
        self.replace_textasset_var.set(True)
        self.replace_mesh_var.set(True)
        self.replace_all_var.set(False)
        
        # Spine 转换器选项
        self.spine_converter_path_var.set("")
        self.enable_spine_conversion_var.set(False)
        self.target_spine_version_var.set("4.2.33")

    def init_shared_variables(self):
        """初始化所有Tabs共享的变量。"""
        # 创建变量
        self.game_resource_dir_var = tk.StringVar()
        self.auto_detect_subdirs_var = tk.BooleanVar()
        self.output_dir_var = tk.StringVar()
        self.enable_padding_var = tk.BooleanVar()
        self.enable_crc_correction_var = tk.BooleanVar()
        self.create_backup_var = tk.BooleanVar()
        self.compression_method_var = tk.StringVar()
        self.replace_texture2d_var = tk.BooleanVar()
        self.replace_textasset_var = tk.BooleanVar()
        self.replace_mesh_var = tk.BooleanVar()
        self.replace_all_var = tk.BooleanVar()
        
        # Spine 转换器选项
        self.spine_converter_path_var = tk.StringVar()
        self.enable_spine_conversion_var = tk.BooleanVar()
        self.target_spine_version_var = tk.StringVar()  # 添加目标Spine版本变量
        
        # 设置默认值
        self._set_default_values()

    def create_widgets(self):
        # 使用可拖动的 PanedWindow 替换固定的 grid 布局
        paned_window = ttk.PanedWindow(self.master, orient=tk.VERTICAL)
        paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 上方控制面板
        top_frame = tk.Frame(paned_window, bg=Theme.WINDOW_BG)
        paned_window.add(top_frame, weight=1)

        # 下方日志区域
        bottom_frame = tk.Frame(paned_window, bg=Theme.WINDOW_BG)
        paned_window.add(bottom_frame, weight=1)

        # 顶部框架，用于放置设置按钮
        top_controls_frame = tk.Frame(top_frame, bg=Theme.WINDOW_BG)
        top_controls_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 使用grid布局让按钮横向拉伸填满
        settings_button = tk.Button(top_controls_frame, text="Settings", command=self.open_settings_dialog,
                                    font=Theme.BUTTON_FONT, bg=Theme.BUTTON_WARNING_BG, fg=Theme.BUTTON_FG,
                                    relief=tk.FLAT)
        settings_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        environment_button = tk.Button(top_controls_frame, text="Env", command=self.show_environment_info, 
                                       font=Theme.BUTTON_FONT, bg=Theme.BUTTON_SECONDARY_BG, fg=Theme.BUTTON_FG, 
                                       relief=tk.FLAT)
        environment_button.grid(row=0, column=1, sticky="ew")
        
        # 设置列权重，让按钮均匀拉伸
        top_controls_frame.columnconfigure(0, weight=1)
        top_controls_frame.columnconfigure(1, weight=1)

        self.notebook = self.create_notebook(top_frame)
        
        # 创建日志区域
        self.log_text = self.create_log_area(bottom_frame)

        # 底部状态栏
        self.status_label = tk.Label(self.master, text="", bd=1, relief=tk.SUNKEN, anchor=tk.W,
                                     font=Theme.INPUT_FONT, bg=Theme.STATUS_BAR_BG, fg=Theme.STATUS_BAR_FG, padx=10)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.logger = Logger(self.master, self.log_text, self.status_label)
        
        # 将 logger 和共享变量传递给 Tabs
        self.populate_notebook()

    def open_settings_dialog(self):
        """打开高级设置对话框"""
        dialog = SettingsDialog(self.master, self)
        self.master.wait_window(dialog) # 等待对话框关闭

    # --- 共享目录选择和打开的方法 ---
    def _select_directory(self, var, title):
        try:
            current_path = Path(var.get())
            if not current_path.is_dir(): current_path = Path.home()
            selected_dir = filedialog.askdirectory(title=title, initialdir=str(current_path))
            if selected_dir:
                var.set(str(Path(selected_dir)))
                self.logger.log(f"已更新目录: {selected_dir}")
        except Exception as e:
            messagebox.showerror("错误", f"选择目录时发生错误:\n{e}")
            
    def _open_directory_in_explorer(self, path_str, create_if_not_exist=False):
        try:
            path = Path(path_str)
            if not path.is_dir():
                if create_if_not_exist:
                    if messagebox.askyesno("提示", f"目录不存在:\n{path}\n\n是否要创建它？"):
                        path.mkdir(parents=True, exist_ok=True)
                    else: return
                else:
                    messagebox.showwarning("警告", f"路径不存在或不是一个文件夹:\n{path}")
                    return
            os.startfile(str(path))
            self.logger.log(f"已在资源管理器中打开目录: {path}")
        except Exception as e:
            messagebox.showerror("错误", f"打开资源管理器时发生错误:\n{e}")

    def show_environment_info(self):
        """显示环境信息"""
        self.logger.log(get_environment_info())

    def select_game_resource_directory(self):
        # 根据复选框状态决定对话框标题
        if self.auto_detect_subdirs_var.get():
            title = "选择游戏根目录"
        else:
            title = "选择自定义资源目录"
        self._select_directory(self.game_resource_dir_var, title)
        
    def open_game_resource_in_explorer(self):
        self._open_directory_in_explorer(self.game_resource_dir_var.get())

    def select_output_directory(self):
        self._select_directory(self.output_dir_var, "选择输出目录")

    def open_output_dir_in_explorer(self):
        self._open_directory_in_explorer(self.output_dir_var.get(), create_if_not_exist=True)
    
    def load_config_on_startup(self):
        """应用启动时自动加载配置"""
        if self.config_manager.load_config(self):
            self.logger.log("配置加载成功")
        else:
            self.logger.log("未找到配置文件，使用默认设置")
    
    def save_current_config(self):
        """保存当前配置到文件"""
        if self.config_manager.save_config(self):
            self.logger.log("配置保存成功")
            messagebox.showinfo("成功", "配置已保存到 config.ini")
        else:
            self.logger.log("配置保存失败")
            messagebox.showerror("错误", "配置保存失败")
    # --- 方法结束 ---
    
    def create_notebook(self, parent):
        style = ttk.Style()
        # 自定义Notebook样式以匹配主题
        style.configure("TNotebook", background=Theme.WINDOW_BG, borderwidth=0)
        style.configure("TNotebook.Tab", 
                        font=Theme.BUTTON_FONT, 
                        padding=[10, 5],
                        background=Theme.MUTED_BG,
                        foreground=Theme.TEXT_NORMAL)
        style.map("TNotebook.Tab",
                  background=[("selected", Theme.FRAME_BG)],
                  foreground=[("selected", Theme.TEXT_TITLE)])

        notebook = ttk.Notebook(parent, style="TNotebook")
        notebook.pack(fill=tk.BOTH, expand=True)
        return notebook

    def create_log_area(self, parent):
        log_frame = tk.LabelFrame(parent, text="Log", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, pady=2)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=0) # 日志区不需要顶部pady

        log_text = tk.Text(log_frame, wrap=tk.WORD, bg=Theme.LOG_BG, fg=Theme.LOG_FG, font=Theme.LOG_FONT, relief=tk.FLAT, bd=0, padx=5, pady=5, insertbackground=Theme.LOG_FG, height=10) #添加 height 参数
        scrollbar = tk.Scrollbar(log_frame, orient=tk.VERTICAL, command=log_text.yview)
        log_text.configure(yscrollcommand=scrollbar.set)
        
        log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        log_text.config(state=tk.DISABLED)
        return log_text

    def populate_notebook(self):
        """创建并添加所有的Tab页面到Notebook。"""
        # 传递给所有标签页的共享参数字典
        shared_args = {
            'game_resource_dir_var': self.game_resource_dir_var,
            'output_dir_var': self.output_dir_var,
            'enable_padding_var': self.enable_padding_var,
            'enable_crc_correction_var': self.enable_crc_correction_var,
            'create_backup_var': self.create_backup_var,
            'replace_texture2d_var': self.replace_texture2d_var,
            'replace_textasset_var': self.replace_textasset_var,
            'replace_mesh_var': self.replace_mesh_var,
            'replace_all_var': self.replace_all_var,
            'compression_method_var': self.compression_method_var,
            'auto_detect_subdirs_var': self.auto_detect_subdirs_var,
            'enable_spine_conversion_var': self.enable_spine_conversion_var,
            'spine_converter_path_var': self.spine_converter_path_var,
            'target_spine_version_var': self.target_spine_version_var,
        }

        # Tab: Mod 更新
        combined_update_tab = ModUpdateTab(self.notebook, self.logger, **shared_args)
        self.notebook.add(combined_update_tab, text="Mod 更新")

        # Tab: CRC 工具
        crc_tab = CrcToolTab(self.notebook, self.logger, 
                             game_resource_dir_var=self.game_resource_dir_var,
                             enable_padding_var=self.enable_padding_var,
                             create_backup_var=self.create_backup_var,
                             auto_detect_subdirs_var=self.auto_detect_subdirs_var)
        self.notebook.add(crc_tab, text="CRC 修正工具")

        # Tab: 资源打包
        asset_tab = AssetPackerTab(self.notebook, self.logger, 
                                    output_dir_var=self.output_dir_var,
                                    enable_padding_var=self.enable_padding_var,
                                    enable_crc_correction_var=self.enable_crc_correction_var,
                                    create_backup_var=self.create_backup_var,
                                    compression_method_var=self.compression_method_var,
                                    enable_spine_conversion_var=self.enable_spine_conversion_var,
                                    spine_converter_path_var=self.spine_converter_path_var,
                                    target_spine_version_var=self.target_spine_version_var)
        self.notebook.add(asset_tab, text="资源打包")

        # TODO: Bundle 解包工具
        
        # TODO: 国际服/日服转换工具
