# ui/dialogs.py

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from ui.app import App

from i18n import t
from .components import Theme, UIComponents, ScrollableFrame
from .utils import select_file

class SettingsDialog(tk.Toplevel):
    def __init__(self, master, app_instance: "App"):
        super().__init__(master)
        self.app = app_instance

        self._setup_window()

        self.scroll_frame = ScrollableFrame(self)
        self.scroll_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        self.content_area = self.scroll_frame.viewport

        self._init_path_settings()
        self._init_app_settings()
        self._init_global_options()
        self._init_asset_options()
        self._init_spine_settings()

        self._init_footer_buttons()

        self._setup_variable_traces()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.settings.title"))
        self.geometry("600x700")
        self.configure(bg=Theme.WINDOW_BG)
        self.transient(self.master)

    def _create_section(self, title: str) -> tk.LabelFrame:
        """
        创建一个带有标题的LabelFrame

        Args:
            title: 分节标题

        Returns:
            创建的LabelFrame组件
        """
        section = tk.LabelFrame(
            self.content_area,
            text=title,
            font=Theme.FRAME_FONT,
            fg=Theme.TEXT_TITLE,
            bg=Theme.FRAME_BG,
            padx=15,
            pady=12
        )
        section.pack(fill=tk.X, pady=(0, 10))
        return section

    def _add_form_row(self, parent: tk.Widget, widget: tk.Widget, label: str | None = None, tooltip: str | None = None) -> None:
        """
        核心布局函数: 使用 Grid 布局实现 Label(Col 0) | Widget(Col 1) | Tooltip(Col 2)

        Args:
            parent: 父容器
            widget: 控件
            label: 标签文本
            tooltip: 可选的提示文本
        """
        current_row = parent.grid_size()[1]

        if label:
            label_widget = tk.Label(parent, text=label, font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL, width=20, anchor="w")
            label_widget.grid(row=current_row, column=0, sticky="w", padx=(0, 10), pady=5)

        widget.grid(row=current_row, column=1, sticky="ew", padx=5, pady=5)

        if tooltip:
            tooltip_icon = UIComponents.create_tooltip_icon(parent, tooltip)
            tooltip_icon.grid(row=current_row, column=2, padx=(5, 0), pady=5)

        parent.columnconfigure(1, weight=1)

    def _add_path_selector_row(self, parent: tk.Widget, label: str, variable: tk.StringVar, action: Callable[[], None], open_cmd: Callable[[], None] | None = None, tooltip: str | None = None) -> None:
        """
        专门用于路径选择的复合行构建

        Args:
            parent: 父容器
            label: 标签文本
            variable: 路径变量
            action: 选择路径的回调函数
            open_cmd: 打开路径的回调函数（可选）
            tooltip: 可选的提示文本
        """
        path_widget = UIComponents.create_path_entry(parent, None, variable, action, open_cmd, None, True, form_row=True)
        self._add_form_row(parent, path_widget, label, tooltip)

    def _init_path_settings(self):
        """初始化路径设置"""
        section = self._create_section(t("ui.settings.group_paths"))

        self._add_path_selector_row(
            section,
            t("ui.label.game_root_dir"),
            self.app.game_resource_dir_var,
            self.app.select_game_resource_directory,
            self.app.open_game_resource_in_explorer
        )

        self._add_path_selector_row(
            section,
            t("ui.label.output_dir"),
            self.app.output_dir_var,
            self.app.select_output_directory,
            self.app.open_output_dir_in_explorer
        )

    def _init_app_settings(self):
        """初始化应用设置"""
        section = self._create_section(t("ui.settings.group_app"))

        language_combo = UIComponents.create_combobox(section, self.app.language_var, self.app.available_languages, width=10)
        language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)
        self._add_form_row(section, language_combo, t("ui.label.language"))

    def _init_global_options(self):
        """初始化全局选项"""
        section = self._create_section(t("ui.settings.group_global"))

        crc_checkbox = UIComponents.create_checkbutton(section, t("option.crc_correction"), self.app.enable_crc_correction_var, form_row=True)
        self._add_form_row(section, crc_checkbox, t("option.crc_correction"), "测试文本")

        self.padding_checkbox = UIComponents.create_checkbutton(section, t("option.padding"), self.app.enable_padding_var, form_row=True)
        self._add_form_row(section, self.padding_checkbox, t("option.padding"))

        backup_checkbox = UIComponents.create_checkbutton(section, t("option.backup"), self.app.create_backup_var, form_row=True)
        self._add_form_row(section, backup_checkbox, t("option.backup"))

        compression_combo = UIComponents.create_combobox(section, self.app.compression_method_var, ["lzma", "lz4", "original", "none"], width=10)
        self._add_form_row(section, compression_combo, t("ui.label.compression_method"))

    def _init_asset_options(self):
        """初始化资源替换选项"""
        section = self._create_section(t("ui.settings.group_assets"))

        replace_all_checkbox = UIComponents.create_checkbutton(section, t("option.replace_all"), self.app.replace_all_var, form_row=True)
        self._add_form_row(section, replace_all_checkbox, t("option.replace_all"))

        replace_texture_checkbox = UIComponents.create_checkbutton(section, t("option.replace_texture"), self.app.replace_texture2d_var, form_row=True)
        self._add_form_row(section, replace_texture_checkbox, t("option.replace_texture"))

        replace_textasset_checkbox = UIComponents.create_checkbutton(section, t("option.replace_textasset"), self.app.replace_textasset_var, form_row=True)
        self._add_form_row(section, replace_textasset_checkbox, t("option.replace_textasset"))

        replace_mesh_checkbox = UIComponents.create_checkbutton(section, t("option.replace_mesh"), self.app.replace_mesh_var, form_row=True)
        self._add_form_row(section, replace_mesh_checkbox, t("option.replace_mesh"))

    def _init_spine_settings(self):
        """初始化Spine设置"""
        section = self._create_section(t("ui.settings.group_spine"))

        spine_conversion_checkbox = UIComponents.create_checkbutton(section, t("option.spine_conversion"), self.app.enable_spine_conversion_var, form_row=True)
        self._add_form_row(section, spine_conversion_checkbox, t("option.spine_conversion"))

        spine_version_entry = UIComponents.create_textbox_entry(section, self.app.target_spine_version_var, placeholder_text=t("ui.label.spine_version"))
        self._add_form_row(section, spine_version_entry, t("ui.label.target_version"))

        self._add_path_selector_row(
            section,
            t("ui.label.skel_converter_path"),
            self.app.spine_converter_path_var,
            self.select_spine_converter_path
        )

        self._add_path_selector_row(
            section,
            t("ui.label.atlas_downgrade_path"),
            self.app.atlas_downgrade_path_var,
            self.select_atlas_downgrade_path
        )

    def _init_footer_buttons(self):
        """初始化底部按钮栏"""
        footer_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        footer_frame.pack(fill=tk.X, padx=15, pady=15)

        footer_frame.columnconfigure(0, weight=1)
        footer_frame.columnconfigure(1, weight=1)
        footer_frame.columnconfigure(2, weight=1)

        save_button = UIComponents.create_button(footer_frame, t("common.save"), self.app.save_current_config, bg_color=Theme.BUTTON_SUCCESS_BG)
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        load_button = UIComponents.create_button(footer_frame, t("common.load"), self.load_config, bg_color=Theme.BUTTON_WARNING_BG)
        load_button.grid(row=0, column=1, sticky="ew", padx=5)

        reset_button = UIComponents.create_button(footer_frame, t("common.reset"), self.reset_to_default, bg_color=Theme.BUTTON_DANGER_BG)
        reset_button.grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _setup_variable_traces(self):
        """设置变量变化监听"""
        self.app.enable_crc_correction_var.trace_add("write", self._on_crc_change)

    def _on_crc_change(self, *args):
        """CRC修正复选框状态变化时的处理"""
        if self.app.enable_crc_correction_var.get():
            self.padding_checkbox.config(state=tk.NORMAL)
        else:
            self.app.enable_padding_var.set(False)
            self.padding_checkbox.config(state=tk.DISABLED)

    def load_config(self):
        """加载配置文件并更新UI"""
        if self.app.config_manager.load_config(self.app):
            self.app.logger.log(t("log.status.ready"))
            messagebox.showinfo(t("common.success"), t("message.config.loaded"))
        else:
            self.app.logger.log(t("log.config.load_failed"))
            messagebox.showerror(t("common.error"), t("message.config.load_failed"))

    def reset_to_default(self):
        """重置为默认设置"""
        if messagebox.askyesno(t("common.tip"), t("message.confirm_reset_settings")):
            self.app._set_default_values()
            self.app.logger.log(t("log.config.reset"))

    def select_spine_converter_path(self):
        """选择Spine转换器路径"""
        select_file(
            title=t("ui.dialog.select", type=t("file_type.skel_converter")),
            filetypes=[(t("file_type.executable"), "*.exe"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: (
                self.app.spine_converter_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.skel_converter_set", path=path))
            ),
            logger=self.app.logger.log
        )

    def select_atlas_downgrade_path(self):
        """选择SpineAtlasDowngrade.exe路径"""
        select_file(
            title=t("ui.dialog.select", type=t("file_type.atlas_downgrade")),
            filetypes=[(t("file_type.executable"), "*.exe"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: (
                self.app.atlas_downgrade_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.atlas_downgrade_set", path=path))
            ),
            logger=self.app.logger.log
        )

    def _on_language_changed(self, event=None):
        """语言选择改变时的处理"""
        selected_language = self.app.language_var.get()
        self.app.logger.log(t("log.config.language_changed", language=selected_language))
        
        # 弹出确认对话框
        if messagebox.askyesno(
            t("common.tip"),
            t("message.config.language_changed"),
            parent=self
        ):
            # 保存配置
            self.app.save_current_config()
            # 关闭程序
            self.master.destroy()