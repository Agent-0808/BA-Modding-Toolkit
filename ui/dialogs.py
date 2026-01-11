# ui/dialogs.py

import tkinter as tk
import ttkbootstrap as tb
import tkinter.messagebox as messagebox
from ttkbootstrap.widgets.scrolled import ScrolledFrame
from pathlib import Path
from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from ui.app import App

from i18n import t
from .components import Theme, UIComponents, SettingRow
from .utils import select_file

class SettingsDialog(tb.Toplevel):
    def __init__(self, master, app_instance: "App"):
        super().__init__(master)
        self.app = app_instance

        self._setup_window()

        self.scroll_frame = ScrolledFrame(self, autohide=True)
        self.scroll_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        self.content_area = tb.Frame(self.scroll_frame)
        self.content_area.pack(fill=tk.BOTH, expand=True, padx=(0, 15))

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

    def _create_section(self, title: str) -> tb.Labelframe:
        """
        创建一个带有标题的LabelFrame

        Args:
            title: 分节标题

        Returns:
            创建的LabelFrame组件
        """
        section = tb.Labelframe(
            self.content_area,
            text=title,
            bootstyle="default"
        )
        section.pack(fill=tk.X, pady=(0, 10))
        return section

    def _init_path_settings(self):
        """初始化路径设置"""
        section = self._create_section(t("ui.settings.group_paths"))

        SettingRow.create_path_selector(
            section,
            label=t("ui.label.game_root_dir"),
            path_var=self.app.game_resource_dir_var,
            select_cmd=self.app.select_game_resource_directory,
            open_cmd=self.app.open_game_resource_in_explorer
        )

        SettingRow.create_path_selector(
            section,
            label=t("ui.label.output_dir"),
            path_var=self.app.output_dir_var,
            select_cmd=self.app.select_output_directory,
            open_cmd=self.app.open_output_dir_in_explorer
        )

    def _init_app_settings(self):
        """初始化应用设置"""
        section = self._create_section(t("ui.settings.group_app"))

        SettingRow.create_combobox_row(
            section,
            label=t("ui.label.language"),
            text_var=self.app.language_var,
            values=self.app.available_languages
        )

    def _init_global_options(self):
        """初始化全局选项"""
        section = self._create_section(t("ui.settings.group_global"))

        crc_checkbox = SettingRow.create_switch(
            section,
            label=t("option.crc_correction"),
            variable=self.app.enable_crc_correction_var,
            tooltip="测试文本"
        )

        self.padding_checkbox = SettingRow.create_switch(
            section,
            label=t("option.padding"),
            variable=self.app.enable_padding_var
        )

        SettingRow.create_switch(
            section,
            label=t("option.backup"),
            variable=self.app.create_backup_var
        )

        SettingRow.create_combobox_row(
            section,
            label=t("ui.label.compression_method"),
            text_var=self.app.compression_method_var,
            values=["lzma", "lz4", "original", "none"]
        )

    def _init_asset_options(self):
        """初始化资源替换选项"""
        section = self._create_section(t("ui.settings.group_assets"))

        SettingRow.create_switch(
            section,
            label=t("option.replace_all"),
            variable=self.app.replace_all_var
        )

        SettingRow.create_switch(
            section,
            label=t("option.replace_texture"),
            variable=self.app.replace_texture2d_var
        )

        SettingRow.create_switch(
            section,
            label=t("option.replace_textasset"),
            variable=self.app.replace_textasset_var
        )

        SettingRow.create_switch(
            section,
            label=t("option.replace_mesh"),
            variable=self.app.replace_mesh_var
        )

    def _init_spine_settings(self):
        """初始化Spine设置"""
        section = self._create_section(t("ui.settings.group_spine"))

        SettingRow.create_switch(
            section,
            label=t("option.spine_conversion"),
            variable=self.app.enable_spine_conversion_var
        )

        SettingRow.create_entry_row(
            section,
            label=t("ui.label.target_version"),
            text_var=self.app.target_spine_version_var,
            placeholder_text=t("ui.label.spine_version")
        )

        SettingRow.create_path_selector(
            section,
            label=t("ui.label.skel_converter_path"),
            path_var=self.app.spine_converter_path_var,
            select_cmd=self.select_spine_converter_path
        )

        SettingRow.create_path_selector(
            section,
            label=t("ui.label.atlas_downgrade_path"),
            path_var=self.app.atlas_downgrade_path_var,
            select_cmd=self.select_atlas_downgrade_path
        )

    def _init_footer_buttons(self):
        """初始化底部按钮栏"""
        footer_frame = tb.Frame(self)
        footer_frame.pack(fill=tk.X, padx=15, pady=15)

        footer_frame.columnconfigure(0, weight=1)
        footer_frame.columnconfigure(1, weight=1)
        footer_frame.columnconfigure(2, weight=1)

        save_button = tb.Button(footer_frame, text=t("common.save"), command=self.app.save_current_config, bootstyle="success")
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        load_button = tb.Button(footer_frame, text=t("common.load"), command=self.load_config, bootstyle="warning") 
        load_button.grid(row=0, column=1, sticky="ew", padx=5)

        reset_button = tb.Button(footer_frame, text=t("common.reset"), command=self.reset_to_default, bootstyle="danger")
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
