# ui/app.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import os

from utils import get_environment_info
from ui.components import Theme, Logger, UIComponents
from ui.utils import ConfigManager, open_directory, select_directory
from ui.dialogs import SettingsDialog
from ui.tabs import ModUpdateTab, CrcToolTab, AssetPackerTab, AssetExtractorTab, JpGbConversionTab
from i18n import i18n_manager, t, get_system_language

class App(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.setup_main_window()
        self.config_manager = ConfigManager()
        self.init_shared_variables()
        # 在创建UI组件前加载配置，确保语言设置正确
        self.load_config_on_startup()  # 启动时加载配置
        self.create_widgets()
        self.logger.status(t("log.status.ready"))

    def setup_main_window(self):
        self.master.title(t("ui.app_title"))
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
        
        # JP/GB转换自动搜索选项
        self.auto_search_var.set(True)
        
        # 一键更新的资源类型选项
        self.replace_texture2d_var.set(True)
        self.replace_textasset_var.set(True)
        self.replace_mesh_var.set(True)
        self.replace_all_var.set(False)
        
        # Spine 转换器选项
        self.spine_converter_path_var.set("")
        self.enable_spine_conversion_var.set(False)
        self.target_spine_version_var.set("4.2.33")
        
        # Spine 降级选项
        self.enable_atlas_downgrade_var.set(False)
        self.atlas_downgrade_path_var.set("")
        self.spine_downgrade_version_var.set("3.8.75")  # 设置默认值

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
        # JP/GB转换自动搜索选项
        self.auto_search_var = tk.BooleanVar()
        # 一键更新的资源类型选项
        self.replace_texture2d_var = tk.BooleanVar()
        self.replace_textasset_var = tk.BooleanVar()
        self.replace_mesh_var = tk.BooleanVar()
        self.replace_all_var = tk.BooleanVar()
        
        # Spine 转换器选项
        self.spine_converter_path_var = tk.StringVar()
        self.enable_spine_conversion_var = tk.BooleanVar()
        self.target_spine_version_var = tk.StringVar()  # 添加目标Spine版本变量
        
        # Spine 降级选项
        self.enable_atlas_downgrade_var = tk.BooleanVar()
        self.atlas_downgrade_path_var = tk.StringVar()
        self.spine_downgrade_version_var = tk.StringVar()  # 添加Spine降级版本变量
        
        # 语言设置
        self.language_var = tk.StringVar(value="zh-CN")
        
        # 设置默认值
        self._set_default_values()

    def create_widgets(self):
        # 使用grid布局确保status_widget固定在底部
        self.master.grid_rowconfigure(0, weight=1)  # 主内容区域可扩展
        self.master.grid_columnconfigure(0, weight=1)  # 主内容区域可扩展
        
        # 创建主内容框架
        main_frame = tk.Frame(self.master, bg=Theme.WINDOW_BG)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # 主内容框架也使用grid布局
        main_frame.grid_rowconfigure(1, weight=1)  # notebook区域可扩展
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 使用可拖动的 PanedWindow 作为主内容区域
        paned_window = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned_window.grid(row=1, column=0, sticky="nsew")

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
        settings_button = UIComponents.create_button(top_controls_frame, t("ui.settings.title"), self.open_settings_dialog, bg_color=Theme.BUTTON_WARNING_BG)
        settings_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        environment_button = UIComponents.create_button(top_controls_frame, t("action.environment"), self.show_environment_info, bg_color=Theme.BUTTON_SECONDARY_BG)
        environment_button.grid(row=0, column=1, sticky="ew")
        
        # 设置列权重，让按钮均匀拉伸
        top_controls_frame.columnconfigure(0, weight=1)
        top_controls_frame.columnconfigure(1, weight=1)
        top_controls_frame.rowconfigure(0, weight=1)  # 确保按钮垂直居中

        self.notebook = self.create_notebook(top_frame)
        
        # 创建日志区域
        self.log_text = self.create_log_area(bottom_frame)

        # 底部状态栏 - 固定在窗口底部
        self.status_label = tk.Label(self.master, text="", bd=1, relief=tk.SUNKEN, anchor=tk.W,
                                     font=Theme.INPUT_FONT, bg=Theme.STATUS_BAR_BG, fg=Theme.STATUS_BAR_FG, padx=10,
                                     height=1)  # 固定高度，确保不会被子组件挤压
        self.status_label.grid(row=1, column=0, sticky="ew", padx=0, pady=0)  # 使用grid固定在底部，无边距
        
        self.logger = Logger(self.master, self.log_text, self.status_label)
        
        # 在logger创建后记录配置加载信息
        language = self.language_var.get()
        self.logger.log(t("log.config.loaded"))
        self.logger.log(t("log.config.language", language=language))
        
        # 将 logger 和共享变量传递给 Tabs
        self.populate_notebook()
        
        # 绑定窗口大小变化事件，确保布局正确
        self.master.bind('<Configure>', self._on_window_configure)
    
    def _on_window_configure(self, event):
        """处理窗口大小变化事件"""
        # 确保状态栏始终可见
        if event.widget == self.master:
            # 可以在这里添加额外的布局调整逻辑
            pass

    def open_settings_dialog(self):
        """打开高级设置对话框"""
        dialog = SettingsDialog(self.master, self)
        self.master.wait_window(dialog) # 等待对话框关闭

    def show_environment_info(self):
        """显示环境信息"""
        self.logger.log(get_environment_info())

    def select_game_resource_directory(self):
        # 根据复选框状态决定对话框标题
        if self.auto_detect_subdirs_var.get():
            title = t("ui.label.game_root_dir")
        else:
            title = t("ui.label.custom_resource_dir")
        select_directory(self.game_resource_dir_var, title, self.logger.log)
        
    def open_game_resource_in_explorer(self):
        open_directory(self.game_resource_dir_var.get(), self.logger.log)

    def select_output_directory(self):
        select_directory(self.output_dir_var, t("ui.label.output_dir"), self.logger.log)

    def open_output_dir_in_explorer(self):
        open_directory(self.output_dir_var.get(), self.logger.log, create_if_not_exist=True)

    
    def load_config_on_startup(self):
        """应用启动时自动加载配置"""
        config_loaded = self.config_manager.load_config(self)
        
        # 如果没有配置文件，根据系统语言检测设置默认语言
        if not config_loaded:
            system_lang = get_system_language()
            # 如果系统语言是中文，使用zh-CN，否则使用debug模式
            if system_lang and (system_lang.startswith("zh-")):
                default_language = "zh-CN"
            else:
                default_language = "debug"
            
            self.language_var.set(default_language)
            print(f"未找到配置文件，根据系统语言检测使用默认语言: {default_language}")
        
        # 设置语言
        language = self.language_var.get()
        i18n_manager.set_language(language)
        
        # 此时logger可能还未创建，使用print作为临时日志
        if config_loaded:
            print(f"配置加载成功，语言设置为: {language}")
    
    def save_current_config(self):
        """保存当前配置到文件"""
        if self.config_manager.save_config(self):
            self.logger.log(t("log.config.saved"))
            messagebox.showinfo(t("common.success"), t("message.config.saved"))
        else:
            self.logger.log(t("log.config.save_failed"))
            messagebox.showerror(t("common.error"), t("message.config.save_failed"))
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
        log_frame = tk.LabelFrame(parent, text=t("ui.log_area"), font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, pady=2)
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
        self.notebook.add(ModUpdateTab(self.notebook, self), text=t("ui.tabs.mod_update"))
        self.notebook.add(CrcToolTab(self.notebook, self), text=t("ui.tabs.crc_tool"))
        self.notebook.add(AssetPackerTab(self.notebook, self), text=t("ui.tabs.asset_packer"))
        self.notebook.add(AssetExtractorTab(self.notebook, self), text=t("ui.tabs.asset_extractor"))
        self.notebook.add(JpGbConversionTab(self.notebook, self), text=t("ui.tabs.jp_gb_convert"))