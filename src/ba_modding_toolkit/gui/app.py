# gui/app.py

import sys
import tkinter as tk
from tkinter import messagebox
from typing import get_type_hints
import ttkbootstrap as tb
from pathlib import Path
from ttkbootstrap.widgets.scrolled import ScrolledText 

from ..i18n import i18n_manager, t, get_system_language, get_locale_dir
from ..utils import get_environment_info, get_BA_path, parse_hex_bytes
from ..models import SaveOptions, SpineOptions
from ..bundle import Bundle
from .components import Theme, Logger, UIComponents
from .utils import open_directory, select_directory
from .configs import ConfigManager, ConfigMeta, ConfigMixin
from .windows import SettingsDialog, FileListWindow
from .base_tab import TabFrame
from .tabs import *

class App(tb.Frame, ConfigMixin):
    def __init__(self, master: tk.Tk):
        super().__init__(master)
        self.master: tk.Tk = master
        self.setup_main_window()
        self.config_manager = ConfigManager(self.exe_dir / "config.toml")
        self.init_shared_variables()
        # 在创建UI组件前加载配置，确保语言设置正确
        self.load_config_on_startup()  # 启动时加载配置
        self.create_widgets()
        self.logger.status(t("status.ready"))

    def setup_main_window(self):
        self.master.title(t("ui.app_title"))
        self.master.geometry("700x888")

        # 设置路径
        if "__compiled__" in globals() and hasattr(__compiled__, "containing_dir"):
            # 打包环境（nuitka onefile）
            # __compiled__.containing_dir 为原始 exe 所在目录
            self.exe_dir = Path(__compiled__.containing_dir).resolve()
            # root_path: nuitka 解压的资源目录（temp 目录下）
            self.root_path = Path(sys.executable).parent / "ba_modding_toolkit"
        else:
            # 开发环境
            # exe_dir: 项目根目录 BA-Modding-Toolkit/
            self.exe_dir = Path(__file__).parents[3]
            # root_path：src/ba_modding_toolkit/
            self.root_path = Path(__file__).parents[1]

        # 设置窗口图标
        print(f"exe_dir: {self.exe_dir}")
        print(f"root_path: {self.root_path}")
        self.setup_icon(self.master)

    def setup_icon(self, window: tk.Toplevel):
        """设置窗口图标"""
        icon_path = self.root_path / "assets" / "eligma.ico"
        if icon_path.exists():
            window.iconbitmap(icon_path)

    def init_shared_variables(self):
        """初始化所有配置变量 - 通过 Annotated 类型提示自动处理"""
        self._config_specs: dict[str, ConfigMeta] = {}
        
        hints = get_type_hints(self.__class__, include_extras=True)
        for var_name, hint in hints.items():
            if not hasattr(hint, '__metadata__'):
                continue
            
            var_type = hint.__origin__
            meta: ConfigMeta = hint.__metadata__[0]
            
            var_instance = var_type()
            setattr(self, var_name, var_instance)
            self._config_specs[var_name] = meta
            
            default = meta.default() if callable(meta.default) else meta.default
            var_instance.set(default)
        
        # 特殊处理：语言设置
        self.language_var.set(i18n_manager.lang)
        self.available_languages = i18n_manager.get_available_languages()

    def _set_default_values(self):
        """重置所有配置变量为默认值"""
        hints = get_type_hints(self.__class__, include_extras=True)
        for var_name, hint in hints.items():
            if not hasattr(hint, '__metadata__'):
                continue

            meta: ConfigMeta = hint.__metadata__[0]
            var = getattr(self, var_name)
            default = meta.default() if callable(meta.default) else meta.default
            var.set(default)

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
        paned_window = tb.Panedwindow(main_frame, orient="vertical", bootstyle="secondary")
        paned_window.grid(row=1, column=0, sticky="nsew")

        # 上方控制面板
        top_frame = tb.Frame(paned_window)
        paned_window.add(top_frame, weight=1)

        # 下方日志区域
        log_panel_frame = tb.Frame(paned_window)
        paned_window.add(log_panel_frame, weight=0)

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
        
        # 检查语言文件是否存在
        locales_dir = get_locale_dir()
        lang_path = locales_dir / f"{language}.json"
        if not lang_path.exists():
            self.logger.log(t("log.config.language_missing", language=language))

    def open_settings_dialog(self):
        """打开高级设置对话框"""
        dialog = SettingsDialog(self.master, self)
        self.master.wait_window(dialog) # 等待对话框关闭

    def open_file_list_window(self):
        """打开文件列表窗口"""
        if hasattr(self, '_file_list_window') and self._file_list_window and self._file_list_window.winfo_exists():
            self._file_list_window.focus()
            return
        self._file_list_window = FileListWindow(self.master, self)

    def show_environment_info(self):
        """显示环境信息"""
        self.logger.log(get_environment_info())

    def get_extra_bytes(self) -> bytes | None:
        """获取用户输入的 extra_bytes 配置值"""
        return parse_hex_bytes(self.extra_bytes_var.get())

    def get_asset_types(self) -> set[str]:
        """从当前替换选项构建资源类型集合"""
        if self.replace_all_var.get():
            return {"ALL"}
        asset_types: set[str] = set()
        if self.replace_texture2d_var.get():
            asset_types.add("Texture2D")
        if self.replace_textasset_var.get():
            asset_types.add("TextAsset")
        if self.replace_mesh_var.get():
            asset_types.add("Mesh")
        return asset_types

    def has_any_asset_type(self) -> bool:
        """是否至少选择了一种资源类型"""
        return bool(self.get_asset_types())

    def build_save_options(self, perform_crc: bool = True) -> SaveOptions:
        """从全局配置构建 SaveOptions"""
        return SaveOptions(
            perform_crc=perform_crc,
            extra_bytes=self.get_extra_bytes(),
            compression=self.compression_method_var.get()
        )

    def resolve_crc_setting(self, target_path: Path | None) -> bool:
        """根据全局CRC配置和目标文件，判断是否需要CRC修正"""
        crc_setting = self.enable_crc_correction_var.get()
        if crc_setting == "true":
            return True
        if crc_setting == "false":
            return False
        if target_path is None:
            return False
        return Bundle.check_need_crc(target_path, log=self.logger.log)

    def build_spine_options(self, upgrade_mode: bool = True) -> SpineOptions:
        """从全局配置构建 SpineOptions

        Args:
            upgrade: True 为升级模式，False 为降级模式
        """

        if upgrade_mode:
            return SpineOptions(
                enabled=self.enable_spine_conversion_var.get(),
                converter_path=Path(self.spine_converter_path_var.get()),
                target_version=self.target_spine_version_var.get()
            )
        else:
            return SpineOptions(
                enabled=self.enable_atlas_downgrade_var.get(),
                converter_path=Path(self.spine_converter_path_var.get()),
                target_version=self.spine_downgrade_version_var.get().strip()
            )

    def is_spine_converter_available(self) -> bool:
        """检查SpineConverter程序路径是否有效"""
        path = self.spine_converter_path_var.get()
        if not path:
            return False
        return Path(path).exists()

    def check_dependency(self, depends_on: str) -> bool:
        """检查依赖条件是否满足"""
        if depends_on == "spine_converter_path_var":
            return self.is_spine_converter_available()
        return True

    def get_depends_on_from_var(self, variable: tk.Variable) -> str | None:
        """从变量对象自动推导其依赖项"""
        for var_name, meta in self._config_specs.items():
            if getattr(self, var_name) == variable:
                return meta.depends_on
        return None

    def show_download_guide(self, program_name: str, url: str, parent: tk.Widget | None = None) -> None:
        """显示通用下载引导对话框"""
        result = messagebox.askyesno(
            t("common.3rd_party"),
            t("message.3rd_party.download_guide",
              program=program_name,
              url=url),
            parent=parent or self.master
        )
        if result:
            import webbrowser
            webbrowser.open(url)

    def show_spine_converter_not_configured(self, parent: tk.Widget | None = None) -> None:
        """显示SpineConverter未配置提示"""
        messagebox.showinfo(
            t("common.tip"),
            t("message.3rd_party.skel_converter_not_configured"),
            parent=parent or self.master
        )

    def show_spine_converter_download_guide(self, parent: tk.Widget | None = None) -> None:
        """显示SpineConverter下载引导对话框"""
        self.show_download_guide(
            "SpineSkeletonDataConverter",
            "https://github.com/wang606/SpineSkeletonDataConverter",
            parent
        )

    def show_spine_viewer_download_guide(self):
        """显示SpineViewer下载引导对话框"""
        self.show_download_guide(
            "SpineViewerCLI",
            "https://github.com/ww-rm/SpineViewer",
            parent=self
        )


    def select_game_resource_directory(self):
        select_directory(self.game_resource_dir_var, t("option.game_root_dir"), self.logger.log)
        
    def open_game_resource_in_explorer(self):
        open_directory(self.game_resource_dir_var.get(), self.logger.log)

    def select_output_directory(self):
        select_directory(self.output_dir_var, t("option.output_dir"), self.logger.log)

    def open_output_dir_in_explorer(self):
        open_directory(self.output_dir_var.get(), self.logger.log, create_if_not_exist=True)

    # 输出子目录常量
    OUTPUT_SUBDIR_BUNDLES = "bundles"
    OUTPUT_SUBDIR_EXTRACT = "extract"
    OUTPUT_SUBDIR_PREVIEW = "preview"

    def get_output_subdir(self, subdir: str) -> Path:
        """获取输出目录下的子目录路径，自动创建"""
        path = Path(self.output_dir_var.get()) / subdir
        path.mkdir(parents=True, exist_ok=True)
        return path

    
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
                default_language = "en-US"
            
            self.language_var.set(default_language)
            print(f"未找到配置文件，根据系统语言检测使用默认语言: {default_language}")
            
            # 尝试从注册表检测 Blue Archive 游戏路径
            ba_path = get_BA_path()
            if ba_path:
                self.game_resource_dir_var.set(ba_path)
                print(f"从注册表检测到 Blue Archive 安装路径: {ba_path}")
        
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
        
        # 左侧侧边栏 - 使用Frame并设置bootstyle="dark"实现深色背景
        self.sidebar_frame = tb.Frame(parent, bootstyle="dark", width=160)
        self.sidebar_frame.pack(side=tk.LEFT, fill=tk.Y)
        self.sidebar_frame.pack_propagate(False)  # 固定宽度
        
        # 右侧内容区域
        self.content_frame = tb.Frame(parent)
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
        self.tabs: list[tuple[TabFrame, str]] = []

        # 创建Tab页面
        mod_update_tab = ModUpdateTab(self.content_frame, self)
        batch_update_tab = BatchUpdateTab(self.content_frame, self)
        batch_legacy_tab = BatchLegacyTab(self.content_frame, self)
        crc_tool_tab = CrcToolTab(self.content_frame, self)
        asset_packer_tab = AssetPackerTab(self.content_frame, self)
        asset_extractor_tab = AssetExtractorTab(self.content_frame, self)
        legacy_conversion_tab = LegacyConversionTab(self.content_frame, self)
        
        self.tabs.extend([
            (mod_update_tab, t("ui.tabs.mod_update")),
            (batch_update_tab, t("ui.tabs.batch_update")),
            (crc_tool_tab, t("ui.tabs.crc_tool")),
            (asset_packer_tab, t("ui.tabs.asset_packer")),
            (asset_extractor_tab, t("ui.tabs.asset_extractor")),
            (legacy_conversion_tab, t("ui.tabs.legacy_conversion")),
            (batch_legacy_tab, t("ui.tabs.batch_legacy")),
        ])
        
        # 将所有Tab放置在content_frame的同一位置
        for tab, _ in self.tabs:
            tab.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def create_sidebar_buttons(self):
        """创建侧边栏导航按钮"""
        self.tab_buttons: list[tuple[tb.Button, TabFrame]] = []
        for tab, title in self.tabs:
            btn = UIComponents.create_button(
                self.sidebar_frame,
                text=title,
                command=lambda t=tab: self.show_tab(t),
                bootstyle="secondary",
                padding=(0, 5)
            )
            # 增加 ipadx/ipady 让按钮看起来更饱满
            btn.pack(fill=tk.X, padx=5, pady=(5,0)) 
            self.tab_buttons.append((btn, tab))
        
        # 添加分隔线
        separator = tb.Separator(self.sidebar_frame, bootstyle="secondary")
        separator.pack(fill=tk.X, padx=5, pady=(10,5))
        
        # 文件列表按钮（独立窗口）
        file_list_btn = UIComponents.create_button(
            self.sidebar_frame,
            text=t("ui.tabs.file_list"),
            command=self.open_file_list_window,
            bootstyle="secondary"
        )
        file_list_btn.pack(fill=tk.X, padx=5, pady=(5,0))

        # 添加分隔线
        separator = tb.Separator(self.sidebar_frame, bootstyle="secondary")
        separator.pack(fill=tk.X, padx=5, pady=(10,5))

        # 在底部添加设置按钮
        settings_btn = UIComponents.create_button(
            self.sidebar_frame,
            text=t("ui.settings.button_text"),
            command=self.open_settings_dialog,
            bootstyle="info"
        )
        settings_btn.pack(fill=tk.X, padx=5, pady=(5,0))
    
    def show_tab(self, tab_to_show):
        """显示指定的Tab页面"""
        # 如果传入的是元组，提取tab对象
        if isinstance(tab_to_show, tuple):
            tab_to_show = tab_to_show[0]
        assert(isinstance(tab_to_show, TabFrame))

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
        log_frame = tb.Labelframe(
            parent, 
            text=t("ui.log_area"), 
            bootstyle="default",
            padding=(5, 0)
        )
        log_frame.pack(fill=tk.BOTH, expand=True)

        # 使用 ttkbootstrap 的 ScrolledText (带自动隐藏的滚动条)
        st = ScrolledText(
            log_frame,
            padding=0,
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
            selectbackground=Theme.LOG_SELECTED, # 选中时的背景色
            insertbackground=Theme.LOG_FG,  # 光标颜色
            state=tk.DISABLED,              # 初始设为不可编辑
            spacing1=2,                     # 段前间距（像素）
        )

        # 保存引用以防被垃圾回收（虽然在 pack 后通常不需要）
        self.log_scrolled_wrapper = st

        # 返回内部的 Text 组件，这样你现有的 Logger 类无需修改即可直接使用
        return st.text