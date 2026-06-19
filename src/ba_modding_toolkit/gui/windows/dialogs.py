# gui/windows/dialogs.py

import tkinter as tk
import ttkbootstrap as tb
import tkinter.messagebox as messagebox
import urllib.request
import webbrowser
from ttkbootstrap.widgets.scrolled import ScrolledFrame
from pathlib import Path
from typing import TYPE_CHECKING, Callable
if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...models import FileType
from ...utils import get_environment_info
from ..components import Theme, UIComponents, SettingRow
from ..utils import select_file

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
        self._init_adb_settings()
        self._init_global_options()
        self._init_asset_options()
        self._init_spine_settings()

        self._init_footer_buttons()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.settings.title"))
        self.geometry("700x888")
        # 设置窗口图标
        self.app.setup_icon(self)

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

        SettingRow.create_entry_row(
            section,
            label=t("option.game_dir_android_global"),
            text_var=self.app.game_dir_android_global_var,
            tooltip=t("option.game_dir_android_global_info"),
            expand=True
        )

        SettingRow.create_entry_row(
            section,
            label=t("option.game_dir_android_japan"),
            text_var=self.app.game_dir_android_japan_var,
            tooltip=t("option.game_dir_android_japan_info"),
            expand=True
        )

    def _init_adb_settings(self):
        """初始化 ADB 设置"""
        section = self._create_section(t("adb.settings.title"))

        # ADB 路径
        SettingRow.create_path_selector(
            section,
            label=t("adb.path"),
            path_var=self.app.adb_path_var,
            select_cmd=self._select_adb_path,
            tooltip=t("adb.path_info"),
            status_check=self._check_adb_available
        )

        # ADB 检测按钮
        SettingRow.create_button_row(
            section,
            label=t("adb.detect"),
            button_text=t("adb.detect"),
            command=self._detect_adb,
            bootstyle="info"
        )

        # 设备选择
        device_container = SettingRow.create_container(section)
        SettingRow._add_label_area(device_container, t("adb.device"), None)

        right_frame = tb.Frame(device_container)
        right_frame.pack(side=tk.RIGHT)

        UIComponents.create_button(
            right_frame,
            text=t("adb.device_refresh"),
            command=self._refresh_devices,
            bootstyle="secondary",
            style="compact"
        ).pack(side=tk.RIGHT, padx=(5, 0))

        self._device_combo = tb.Combobox(
            right_frame,
            textvariable=self.app.adb_device_var,
            values=[],
            state="readonly",
            width=30
        )
        self._device_combo.pack(side=tk.RIGHT, padx=(0, 5))

        # 设备状态标签
        self._device_status_label = tb.Label(section, text="", font=Theme.INPUT_FONT)
        self._device_status_label.pack(fill=tk.X, padx=5, pady=(0, 5))

        # 区服选择
        SettingRow.create_combobox_row(
            section,
            label=t("adb.server_region"),
            text_var=self.app.adb_server_region_var,
            values=["global", "japan"],
            tooltip=t("adb.server_region_info")
        )

        # 缓存路径
        SettingRow.create_path_selector(
            section,
            label=t("adb.cache_dir"),
            path_var=self.app.adb_cache_dir_var,
            select_cmd=self._select_adb_cache_dir,
            open_cmd=self._open_adb_cache_dir,
            tooltip=t("adb.cache_dir_info")
        )

        # 缓存大小 + 清理按钮
        cache_container = SettingRow.create_container(section)
        SettingRow._add_label_area(cache_container, t("adb.cache_title"), None)

        self._cache_size_label = tb.Label(cache_container, text="", font=Theme.INPUT_FONT)
        self._cache_size_label.pack(side=tk.RIGHT, padx=(10, 0))

        UIComponents.create_button(
            cache_container,
            text=t("adb.clear_cache"),
            command=self._clear_adb_cache,
            bootstyle="warning",
            style="compact"
        ).pack(side=tk.RIGHT)

        # 初始化状态
        self._update_adb_status()

    def _select_adb_path(self):
        """选择 ADB 可执行文件路径"""
        select_file(
            title=t("ui.dialog.select", type="ADB"),
            file_types=[FileType.EXECUTABLE, FileType.ALL],
            callback=lambda path: (
                self.app.adb_path_var.set(str(path)),
                self.app.logger.log(t("log.file.loaded", path=path)),
                self._update_adb_status()
            ),
            log=self.app.logger.log
        )

    def _check_adb_available(self) -> bool:
        """检查 ADB 是否可用"""
        adb_path = self.app.adb_path_var.get()
        if not adb_path:
            return False
        if adb_path == "adb":
            # 系统PATH中的adb，尝试运行检测
            try:
                manager = self.app.get_adb_manager()
                success, _ = manager.detect_adb()
                return success
            except Exception:
                return False
        return Path(adb_path).is_file()

    def _detect_adb(self):
        """检测 ADB 是否可用"""
        self.app.refresh_adb_connection()
        manager = self.app.get_adb_manager()
        success, info = manager.detect_adb()
        if success:
            self.app.logger.log(t("adb.detect_success", version=info))
            self._update_adb_status()
            messagebox.showinfo(t("common.success"), t("adb.detect_success", version=info), parent=self)
        else:
            self.app.logger.log(t("adb.detect_failed"))
            messagebox.showerror(t("common.error"), t("adb.detect_failed"), parent=self)

    def _refresh_devices(self):
        """刷新设备列表"""
        self.app.refresh_adb_connection()
        manager = self.app.get_adb_manager()
        devices = manager.get_devices()

        # 更新下拉框
        display_values = [d.display_name for d in devices]
        self._device_combo.config(values=display_values)

        if devices:
            # 自动选择第一个就绪的设备
            for d in devices:
                if d.is_ready:
                    self.app.adb_device_var.set(d.serial)
                    manager.select_device(d.serial)
                    self._device_status_label.config(
                        text=t("adb.device_connected"),
                        bootstyle="success"
                    )
                    return
            # 没有就绪设备
            first = devices[0]
            self._device_status_label.config(
                text=t("adb.device_unauthorized") if first.state == "unauthorized" else t("adb.device_offline"),
                bootstyle="warning"
            )
        else:
            self.app.adb_device_var.set("")
            self._device_status_label.config(
                text=t("adb.device_none"),
                bootstyle="danger"
            )

    def _update_adb_status(self):
        """更新 ADB 状态显示"""
        self._update_cache_size()
        # 尝试刷新设备列表
        try:
            self._refresh_devices()
        except Exception:
            self._device_status_label.config(
                text=t("adb.device_none"),
                bootstyle="danger"
            )

    def _select_adb_cache_dir(self):
        """选择 ADB 缓存目录"""
        from ..utils import select_directory
        select_directory(
            var=self.app.adb_cache_dir_var,
            title=t("ui.dialog.select", type=t("adb.cache_dir")),
            log=self.app.logger.log
        )

    def _open_adb_cache_dir(self):
        """打开 ADB 缓存目录"""
        cache_dir = self.app.adb_cache_dir_var.get()
        if cache_dir:
            open_directory(cache_dir, self.app.logger.log, create_if_not_exist=True)
        else:
            # 打开默认缓存目录
            default_dir = self.app.exe_dir / "adb_cache"
            default_dir.mkdir(parents=True, exist_ok=True)
            open_directory(default_dir, self.app.logger.log)

    def _update_cache_size(self):
        """更新缓存大小显示"""
        try:
            cache = self.app.get_adb_cache()
            size_display = cache.get_cache_size_display()
            self._cache_size_label.config(text=t("adb.cache_size", size=size_display))
        except Exception:
            self._cache_size_label.config(text="")

    def _clear_adb_cache(self):
        """清理 ADB 缓存"""
        if not messagebox.askyesno(t("common.warning"), t("adb.clear_cache_confirm"), parent=self):
            return
        try:
            cache = self.app.get_adb_cache()
            success, freed = cache.clear_cache()
            if success:
                self.app.logger.log(t("adb.clear_cache_done", size=freed))
                self._update_cache_size()
                messagebox.showinfo(t("common.success"), t("adb.clear_cache_done", size=freed), parent=self)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.process_failed", error=e), parent=self)

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
            label=t("ui.label.github"),
            button_text=t("action.open"),
            command=lambda: webbrowser.open("https://github.com/Agent-0808/BA-Modding-Toolkit"),
            bootstyle="info"
        )

        SettingRow.create_button_row(
            section,
            label=t("ui.label.environment"),
            button_text=t("action.print"),
            command=self.print_environment_info,
            bootstyle="info"
        )

    def _init_global_options(self):
        """初始化保存选项"""
        section = self._create_section(t("ui.settings.group_save"))

        SettingRow.create_radiobutton_row(
            section,
            label=t("option.crc_correction"),
            text_var=self.app.enable_crc_correction_var,
            values=[("auto", t("common.auto")), ("true", t("common.on")), ("false", t("common.off"))],
            tooltip=t("option.crc_correction_info"),
            command=self._on_crc_changed
        )

        self.extra_bytes_entry = SettingRow.create_entry_row(
            section,
            label=t("option.extra_bytes"),
            text_var=self.app.extra_bytes_var,
            tooltip=t("option.extra_bytes_info")
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

        SettingRow.create_switch(
            section,
            label=t("option.skip_unchanged"),
            variable=self.app.skip_unchanged_var,
            tooltip=t("option.skip_unchanged_info")
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

        # Spine 转换器路径设置
        SettingRow.create_path_selector(
            section,
            label=t("option.skel_converter_path"),
            path_var=self.app.spine_converter_path_var,
            select_cmd=self.select_spine_converter_path,
            tooltip=t("option.skel_converter_path_info"),
            download_guide_cmd=self.app.show_spine_converter_download_guide,
            status_check=lambda: Path(self.app.spine_converter_path_var.get()).is_file()
        )

        SettingRow.create_switch(
            section,
            label=t("option.spine_conversion"),
            variable=self.app.enable_spine_conversion_var,
            tooltip=t("option.spine_conversion_info"),
            app=self.app,
            on_click_disabled=self.app.show_spine_converter_not_configured
        )

        SettingRow.create_entry_row(
            section,
            label=t("option.spine_target_version"),
            text_var=self.app.target_spine_version_var,
            tooltip=t("option.spine_target_version_info"),
            app=self.app,
            on_click_disabled=self.app.show_spine_converter_not_configured
        )

        tb.Separator(section).pack(fill=tk.X, padx=5, pady=5)

        # SpineViewerCLI 路径设置
        SettingRow.create_path_selector(
            section,
            label=t("option.spine_viewer_path"),
            path_var=self.app.spine_viewer_path_var,
            select_cmd=self.select_spine_viewer_path,
            tooltip=t("option.spine_viewer_path_info"),
            download_guide_cmd=self.app.show_spine_viewer_download_guide,
            status_check=lambda: Path(self.app.spine_viewer_path_var.get()).is_file()
        )

        tb.Separator(section).pack(fill=tk.X, padx=5, pady=5)

        # 角色ID映射表
        SettingRow.create_path_selector(
            section,
            label=t("option.character_id_map"),
            path_var=self.app.bacii_map_path_var,
            select_cmd=self.select_character_map_path,
            open_cmd=None,
            tooltip=t("option.character_id_map_info"),
            download_guide_cmd=self.download_BACII_map,
            status_check=lambda: Path(self.app.bacii_map_path_var.get()).is_file()
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
            self.extra_bytes_entry.config(state=tk.NORMAL)
        else:
            self.extra_bytes_entry.config(state=tk.DISABLED)

    def _on_language_changed(self, event):
        """语言选项变化时的处理"""
        if messagebox.askyesno(t("common.tip"), t("message.config.language_changed"), parent=self):
            self.app.save_current_config()
            self.destroy()
            self.master.quit()

    def load_config(self):
        """加载配置文件并更新UI"""
        if self.app.config_manager.load_config(self.app):
            self.app.logger.log(t("log.config.loaded"))
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
            file_types=[FileType.EXECUTABLE, FileType.ALL],
            callback=lambda path: (
                self.app.spine_converter_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.skel_converter_set", path=path))
            ),
            log=self.app.logger.log
        )

    def select_spine_viewer_path(self):
        """选择SpineViewerCLI路径"""
        select_file(
            title=t("ui.dialog.select", type=t("file_type.spine_viewer")),
            file_types=[FileType.EXECUTABLE, FileType.ALL],
            callback=lambda path: (
                self.app.spine_viewer_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.spine_viewer_set", path=path))
            ),
            log=self.app.logger.log
        )

    def select_character_map_path(self):
        """选择角色ID映射表路径"""
        select_file(
            title=t("ui.dialog.select", type=t("option.character_id_map")),
            file_types=[FileType.CSV, FileType.ALL],
            callback=lambda path: (
                self.app.bacii_map_path_var.set(str(path)),
                self.app.logger.log(t("log.spine.character_map_set", path=path))
            ),
            log=self.app.logger.log
        )

    def download_BACII_map(self):
        """下载角色ID映射表"""
        url = "https://agent-0808.github.io/BA-characters-internal-id/data/students_data.csv"
        # 下载到 exe 同级目录下的 Addons 子目录
        save_path = self.app.exe_dir / "Addons" / "BA-Characters-Internal-ID.csv"

        if not messagebox.askyesno(
            t("common.3rd_party"),
            t("message.download_confirm", url=url, path=save_path),
            parent=self
        ):
            return

        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, save_path)
            self.app.bacii_map_path_var.set(str(save_path))
            self.app.logger.log(t("log.file.downloaded", path=save_path))
            messagebox.showinfo(t("common.success"), t("message.save_success"), parent=self)
        except Exception as e:
            self.app.logger.log(t("log.error_detail", error=e))
            messagebox.showerror(t("common.error"), t("message.save_error", error=e), parent=self)

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
