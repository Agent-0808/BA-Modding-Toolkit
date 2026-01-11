# ui/app.py

import tkinter as tk
from tkinter import ttk, messagebox
import ttkbootstrap as tb
from pathlib import Path
from ttkbootstrap.widgets.scrolled import ScrolledText 

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
        
        # Spine 3.8 文件名修正选项
        self.enable_spine38_namefix_var = tk.BooleanVar()
        
        # 语言设置
        self.language_var = tk.StringVar(value="zh-CN")
        self.available_languages = i18n_manager.get_available_languages()
        
        # 设置默认值
        self._set_default_values()

    def create_widgets(self):
        # 使用grid布局确保status_widget固定在底部
        self.master.grid_rowconfigure(0, weight=1)  # 主内容区域可扩展
        self.master.grid_columnconfigure(0, weight=1)  # 主内容区域可扩展
        
        # 创建主内容框架
        main_frame = tb.Frame(self.master)
        main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        
        # 主内容框架也使用grid布局
        main_frame.grid_rowconfigure(1, weight=1)  # notebook区域可扩展
        main_frame.grid_columnconfigure(0, weight=1)
        
        # 使用可拖动的 PanedWindow 作为主内容区域
        paned_window = ttk.PanedWindow(main_frame, orient="vertical", bootstyle="secondary")
        paned_window.grid(row=1, column=0, sticky="nsew")

        # 上方控制面板
        top_frame = tb.Frame(paned_window)
        paned_window.add(top_frame, weight=1)

        # 下方日志区域
        log_panel_frame = tb.Frame(paned_window)
        paned_window.add(log_panel_frame, weight=0)

        # 顶部框架，用于放置设置按钮
        header_buttons_frame = tb.Frame(top_frame)
        header_buttons_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 使用grid布局让按钮横向拉伸填满
        settings_button = UIComponents.create_button(header_buttons_frame, t("ui.settings.title"), self.open_settings_dialog, bg_color=Theme.BUTTON_WARNING_BG)
        settings_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        environment_button = UIComponents.create_button(header_buttons_frame, t("action.environment"), self.show_environment_info, bg_color=Theme.BUTTON_SECONDARY_BG)
        environment_button.grid(row=0, column=1, sticky="ew")
        
        # 设置列权重，让按钮均匀拉伸
        header_buttons_frame.columnconfigure(0, weight=1)
        header_buttons_frame.columnconfigure(1, weight=1)
        header_buttons_frame.rowconfigure(0, weight=1)  # 确保按钮垂直居中

        # 创建日志区域（需要在侧边栏之前创建，因为侧边栏会创建Tab，Tab需要logger）
        self.log_text = self.create_log_area(log_panel_frame)

        # 底部状态栏 - 固定在窗口底部
        self.status_label = tb.Label(self.master, relief=tk.SUNKEN, padding=(5,0),
                                     font=Theme.STATUS_BAR_FONT, bootstyle="inverse-bg")
        self.status_label.grid(row=1, column=0, sticky="ew", padx=0, pady=0)  # 使用grid固定在底部，无边距
        
        self.logger = Logger(self.master, self.log_text, self.status_label)
        
        # 创建侧边栏导航布局（logger创建后才能创建Tab）
        self.create_sidebar_layout(top_frame)
        
        # 在logger创建后记录配置加载信息
        language = self.language_var.get()
        self.logger.log(t("log.config.loaded"))
        self.logger.log(t("log.config.language", language=language))

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

    
    def create_sidebar_layout(self, parent):
        """创建侧边栏导航布局：左侧按钮，右侧内容区域"""
        # 清空父容器的布局配置
        parent.pack_propagate(False)
        
        # 左侧侧边栏 - 使用ttk.Frame并设置bootstyle="dark"实现深色背景
        self.sidebar_frame = ttk.Frame(parent, bootstyle="dark", width=120)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)  # 固定宽度
        
        # 右侧内容区域
        self.content_frame = tk.Frame(parent, bg=Theme.WINDOW_BG)
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.content_frame.pack_propagate(False)
        
        # 创建所有Tab页面
        self.populate_tabs()
        
        # 创建侧边栏按钮
        self.create_sidebar_buttons()
        
        # 默认显示第一个Tab
        if self.tabs:
            self.show_tab(self.tabs[0])
    
    def populate_tabs(self):
        """创建并添加所有的Tab页面到内容区域。"""
        self.tabs = []
        self.tab_buttons = []
        
        # 创建Tab页面
        mod_update_tab = ModUpdateTab(self.content_frame, self)
        crc_tool_tab = CrcToolTab(self.content_frame, self)
        asset_packer_tab = AssetPackerTab(self.content_frame, self)
        asset_extractor_tab = AssetExtractorTab(self.content_frame, self)
        jp_gb_conversion_tab = JpGbConversionTab(self.content_frame, self)
        
        self.tabs.extend([
            (mod_update_tab, t("ui.tabs.mod_update")),
            (crc_tool_tab, t("ui.tabs.crc_tool")),
            (asset_packer_tab, t("ui.tabs.asset_packer")),
            (asset_extractor_tab, t("ui.tabs.asset_extractor")),
            (jp_gb_conversion_tab, t("ui.tabs.jp_gb_convert"))
        ])
        
        # 将所有Tab放置在content_frame的同一位置
        for tab, _ in self.tabs:
            tab.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_sidebar_buttons(self):
        """创建侧边栏导航按钮"""
        for tab, title in self.tabs:
            btn = UIComponents.create_button(
                self.sidebar_frame,
                text=title,
                command=lambda t=tab: self.show_tab(t),
                # 初始样式设为 secondary 或 light-outline，使其在深色背景上可见
                bootstyle="light-outline" 
            )
            # 增加 ipadx/ipady 让按钮看起来更饱满
            btn.pack(fill=tk.X, padx=5, pady=2) 
            self.tab_buttons.append((btn, tab))
    
    def show_tab(self, tab_to_show):
        """显示指定的Tab页面"""
        # 如果传入的是元组，提取tab对象
        if isinstance(tab_to_show, tuple):
            tab_to_show = tab_to_show[0]
        
        # 隐藏所有Tab
        for tab, _ in self.tabs:
            tab.pack_forget()
        
        # 显示目标Tab
        tab_to_show.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # 更新按钮样式
        for btn, tab in self.tab_buttons:
            if tab == tab_to_show:
                btn.config(bootstyle="primary")  # 激活状态使用更亮的样式
            else:
                btn.config(bootstyle="secondary")  # 非激活状态使用稍浅样式，比侧边栏背景稍浅
    
    def create_log_area(self, parent):
        """
        创建日志区域，使用自定义的深色风格
        """
        # 创建外层容器（带标题的边框）
        log_frame = ttk.Labelframe(
            parent, 
            text=t("ui.log_area"), 
            bootstyle="default",
            padding=2
        )
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=0)

        # 使用 ttkbootstrap 的 ScrolledText (带自动隐藏的滚动条)
        st = ScrolledText(
            log_frame,
            padding=5,
            height=8,
            autohide=True,            # 自动隐藏滚动条
            bootstyle="round" # 滚动条样式
        )
        st.pack(fill=tk.BOTH, expand=True)

        # 这里直接操作 st.text (内部的 Text 组件) 来修改颜色
        st.text.configure(
            font=Theme.LOG_FONT,
            background=Theme.LOG_BG,
            foreground=Theme.LOG_FG,
            selectbackground="#3a5a7a",      # 选中时的背景色
            insertbackground=Theme.LOG_FG,        # 光标颜色
            state=tk.DISABLED                # 初始设为不可编辑
        )

        # 保存引用以防被垃圾回收（虽然在 pack 后通常不需要）
        self.log_scrolled_wrapper = st

        # 返回内部的 Text 组件，这样你现有的 Logger 类无需修改即可直接使用
        return st.text