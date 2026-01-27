# ui/dialogs.py

import tkinter as tk
import ttkbootstrap as tb
import tkinter.messagebox as messagebox
from ttkbootstrap.widgets.scrolled import ScrolledFrame
from pathlib import Path
from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from .app import App

from ..i18n import t
from ..utils import get_environment_info
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

        self._init_app_settings()
        self._init_path_settings()
        self._init_global_options()
        self._init_asset_options()
        self._init_spine_settings()

        self._init_footer_buttons()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.settings.title"))
        self.geometry("600x700")
        # 设置窗口图标
        icon_path = self.app.root_path / "assets" / "eligma.ico"
        if icon_path.exists():
            self.iconbitmap(icon_path)

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
            label=t("option.game_root_dir"),
            path_var=self.app.game_resource_dir_var,
            select_cmd=self.app.select_game_resource_directory,
            open_cmd=self.app.open_game_resource_in_explorer,
            tooltip=t("option.game_root_dir_info")
        )

    def _init_app_settings(self):
        """初始化应用设置"""
        section = self._create_section(t("ui.settings.group_app"))

        self.language_combo = SettingRow.create_combobox_row(
            section,
            label=t("option.language"),
            text_var=self.app.language_var,
            values=self.app.available_languages,
            tooltip=t("option.language_info")
        )
        self.language_combo.bind("<<ComboboxSelected>>", self._on_language_changed)

        SettingRow.create_path_selector(
            section,
            label=t("option.output_dir"),
            path_var=self.app.output_dir_var,
            select_cmd=self.app.select_output_directory,
            open_cmd=self.app.open_output_dir_in_explorer,
            tooltip=t("option.output_dir_info")
        )

        SettingRow.create_button_row(
            section,
            label=t("ui.label.environment"),
            button_text=t("action.print"),
            command=self.print_environment_info,
            bootstyle="info"
        )

    def _init_global_options(self):
        """初始化全局选项"""
        section = self._create_section(t("ui.settings.group_global"))

        SettingRow.create_radiobutton_row(
            section,
            label=t("option.crc_correction"),
            text_var=self.app.enable_crc_correction_var,
            values=[("auto", t("common.auto")), ("true", t("common.on")), ("false", t("common.off"))],
            tooltip=t("option.crc_correction_info"),
            command=self._on_crc_changed
        )

        self.padding_checkbox = SettingRow.create_switch(
            section,
            label=t("option.padding"),
            variable=self.app.enable_padding_var,
            tooltip=t("option.padding_info")
        )

        SettingRow.create_switch(
            section,
            label=t("option.backup"),
            variable=self.app.create_backup_var,
            tooltip=t("option.backup_info")
        )

        SettingRow.create_radiobutton_row(
            section,
            label=t("option.compression_method"),
            text_var=self.app.compression_method_var,
            values=["lzma", "lz4", "original", "none"],
            tooltip=t("option.compression_method_info")
        )

    def _init_asset_options(self):
        """初始化资源替换选项"""
        section = self._create_section(t("ui.settings.group_assets"))

        SettingRow.create_switch(
            section,
            label=t("option.replace_all"),
            variable=self.app.replace_all_var,
            tooltip=t("option.replace_all_info")
        )

        SettingRow.create_switch(
            section,
            label=t("option.replace_texture"),
            variable=self.app.replace_texture2d_var,
            tooltip=t("option.replace_texture_info")
        )

        SettingRow.create_switch(
            section,
            label=t("option.replace_textasset"),
            variable=self.app.replace_textasset_var,
            tooltip=t("option.replace_textasset_info")
        )

        SettingRow.create_switch(
            section,
            label=t("option.replace_mesh"),
            variable=self.app.replace_mesh_var,
            tooltip=t("option.replace_mesh_info")
        )

    def _init_spine_settings(self):
        """初始化Spine设置"""
        section = self._create_section(t("ui.settings.group_spine"))

        SettingRow.create_switch(
            section,
            label=t("option.spine_conversion"),
            variable=self.app.enable_spine_conversion_var,
            tooltip=t("option.spine_conversion_info")
        )

        SettingRow.create_entry_row(
            section,
            label=t("option.spine_target_version"),
            text_var=self.app.target_spine_version_var,
            placeholder_text=t("ui.label.spine_version"),
            tooltip=t("option.spine_target_version_info")
        )

        SettingRow.create_path_selector(
            section,
            label=t("option.skel_converter_path"),
            path_var=self.app.spine_converter_path_var,
            select_cmd=self.select_spine_converter_path,
            tooltip=t("option.skel_converter_path_info")
        )

    def _init_footer_buttons(self):
        """初始化底部按钮栏"""
        footer_frame = tb.Frame(self)
        footer_frame.pack(fill=tk.X, padx=15, pady=15)

        footer_frame.columnconfigure(0, weight=1)
        footer_frame.columnconfigure(1, weight=1)
        footer_frame.columnconfigure(2, weight=1)

        save_button = UIComponents.create_button(footer_frame, text=t("action.save"), command=self.app.save_current_config, bootstyle="success")
        save_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        load_button = UIComponents.create_button(footer_frame, text=t("action.load"), command=self.load_config, bootstyle="warning") 
        load_button.grid(row=0, column=1, sticky="ew", padx=5)

        reset_button = UIComponents.create_button(footer_frame, text=t("action.reset"), command=self.reset_to_default, bootstyle="danger")
        reset_button.grid(row=0, column=2, sticky="ew", padx=(5, 0))

    def _on_crc_changed(self):
        """CRC修正选项状态变化时的处理"""
        if not self.winfo_exists():
            return
        crc_value = self.app.enable_crc_correction_var.get()
        if crc_value in ["auto", "true"]:
            self.padding_checkbox.config(state=tk.NORMAL)
        else:
            self.app.enable_padding_var.set(False)
            self.padding_checkbox.config(state=tk.DISABLED)

    def _on_language_changed(self, event):
        """语言选项变化时的处理"""
        if messagebox.askyesno(t("common.tip"), t("message.config.language_changed"), parent=self):
            self.app.save_current_config()
            self.destroy()
            self.master.quit()

    def load_config(self):
        """加载配置文件并更新UI"""
        if self.app.config_manager.load_config(self.app):
            self.app.logger.log(t("log.status.ready"))
            messagebox.showinfo(t("common.success"), t("message.config.loaded"))
        else:
            self.app.logger.log(t("log.config.load_failed"))
            messagebox.showerror(t("common.error"), t("message.config.load_failed"), parent=self)

    def reset_to_default(self):
        """重置为默认设置"""
        if messagebox.askyesno(t("common.tip"), t("message.confirm_reset_settings"), parent=self):
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
            log=self.app.logger.log
        )

    def print_environment_info(self):
        """打印环境信息"""
        self.app.logger.log(get_environment_info())


class FileSelectionDialog(tb.Toplevel):
    """文件选择对话框，用于从多个候选文件中选择一个"""
    
    def __init__(self, master, title: str, candidates: list[Path], message: str = "", display_formatter: Callable[[Path], str] | None = None):
        """
        初始化文件选择对话框
        
        Args:
            master: 父窗口
            title: 对话框标题
            candidates: 候选文件路径列表
            message: 提示消息
            display_formatter: 可选的文件名显示格式化函数 (Path -> str)。如果不提供，默认显示完整路径。
        """
        super().__init__(master)
        self.title(title)
        self.candidates = candidates
        self.display_formatter = display_formatter
        self.selected_path: Path | None = None
        self.result_var = tk.BooleanVar(value=False)
        
        self._setup_window()
        self._create_widgets(message)
        
        # 设置为模态窗口
        self.transient(master)
        self.grab_set()
        
        # 等待窗口关闭
        self.wait_window(self)
    
    def _setup_window(self):
        """设置窗口基本属性"""
        self.geometry("800x200")
        self.resizable(True, True)
        
        # 获取父窗口位置并计算对话框位置
        self.update_idletasks()
        parent_x = self.master.winfo_rootx()
        parent_y = self.master.winfo_rooty()
        parent_width = self.master.winfo_width()
        parent_height = self.master.winfo_height()
        
        # 对话框在父窗口中心显示
        x = parent_x + (parent_width - self.winfo_width()) // 2
        y = parent_y + (parent_height - self.winfo_height()) // 2
        
        self.geometry(f"+{x}+{y}")
    
    def _create_widgets(self, message: str):
        """创建对话框组件"""
        # 主容器
        main_frame = tb.Frame(self, padding=(15, 15))
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 提示消息
        if message:
            msg_label = tb.Label(
                main_frame,
                text=message,
                font=Theme.INPUT_FONT,
                wraplength=550,
                justify=tk.LEFT
            )
            msg_label.pack(fill=tk.X, pady=(0, 10))
        
        # 文件列表框
        list_frame = tb.Frame(main_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.listbox = tk.Listbox(
            list_frame,
            font=Theme.INPUT_FONT,
            bg=Theme.INPUT_BG,
            fg=Theme.TEXT_NORMAL,
            selectmode=tk.SINGLE,
            relief=tk.SUNKEN,
            height=4
        )
        
        # 滚动条
        v_scrollbar = tb.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=v_scrollbar.set)
        
        # 布局
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # 填充候选文件
        for candidate in self.candidates:
            if self.display_formatter:
                display_text = self.display_formatter(candidate)
            else:
                display_text = str(candidate)
            self.listbox.insert(tk.END, display_text)
        
        # 默认选中第一个
        if self.candidates:
            self.listbox.selection_set(0)
            self.listbox.activate(0)
        
        # 双击确认
        self.listbox.bind("<Double-Button-1>", lambda e: self._on_confirm())
        
        # 按钮区域
        button_frame = tb.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        UIComponents.create_button(
            button_frame,
            t("common.ok"),
            self._on_confirm,
            bootstyle="success"
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        UIComponents.create_button(
            button_frame,
            t("common.cancel"),
            self._on_cancel,
            bootstyle="secondary"
        ).pack(side=tk.RIGHT)
    
    def _on_confirm(self):
        """确认选择"""
        selection = self.listbox.curselection()
        if selection:
            index = selection[0]
            if 0 <= index < len(self.candidates):
                self.selected_path = self.candidates[index]
                self.result_var.set(True)
        self.destroy()
    
    def _on_cancel(self):
        """取消选择"""
        self.selected_path = None
        self.result_var.set(False)
        self.destroy()
    
    def get_selected_path(self) -> Path | None:
        """获取用户选择的路径"""
        return self.selected_path
