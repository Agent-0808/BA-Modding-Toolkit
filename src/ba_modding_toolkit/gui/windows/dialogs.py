# gui/windows/dialogs.py

import tkinter as tk
import ttkbootstrap as tb
import tkinter.messagebox as messagebox
import threading
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
from ...naming import CharacterInternalIDMap
from ..components import Theme, UIComponents, SettingRow
from ..utils import select_file, select_directory, open_directory

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
        self._init_saving_options()
        self._init_asset_options()
        self._init_spine_settings()

        self._init_footer_buttons()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.settings.title"))
        self.geometry("800x1000")
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

        # 文件来源选择（使用本地化显示文本）
        file_source_values = [
            ("windows_global", t("option.file_source_windows_global")),
            ("windows_japan", t("option.file_source_windows_japan")),
            ("adb_global", t("option.file_source_adb_global")),
            ("adb_japan", t("option.file_source_adb_japan")),
        ]
        SettingRow.create_combobox_row(
            section,
            label=t("option.file_source"),
            text_var=self.app.file_source_var,
            values=file_source_values,
            tooltip=t("option.file_source_info")
        )
        # 保存之前的文件来源值，用于回退
        self._prev_file_source = self.app.file_source_var.get()
        # 监听文件来源变化，切换到ADB时检查可用性
        self.app.file_source_var.trace_add("write", self._on_file_source_changed)

        # 路径配置区域
        path_config_frame = tb.Frame(section)
        path_config_frame.pack(fill=tk.X, pady=(5, 0))

        # Windows 国际服路径
        SettingRow.create_path_selector(
            path_config_frame,
            label=t("option.game_dir_windows_global"),
            path_var=self.app.game_resource_dir_var,
            select_cmd=self.app.select_game_resource_directory,
            open_cmd=self.app.open_game_resource_in_explorer,
            tooltip=t("option.game_dir_windows_global_info")
        )

        # Windows 日服路径
        SettingRow.create_path_selector(
            path_config_frame,
            label=t("option.game_dir_windows_japan"),
            path_var=self.app.game_resource_dir_japan_var,
            select_cmd=self._select_game_resource_directory_japan,
            open_cmd=self._open_game_resource_japan_in_explorer,
            tooltip=t("option.game_dir_windows_japan_info")
        )

        # ADB 国际服路径
        SettingRow.create_path_selector(
            path_config_frame,
            label=t("option.game_dir_android_global"),
            path_var=self.app.game_dir_android_global_var,
            select_cmd=self._select_android_global_dir,
            tooltip=t("option.game_dir_android_global_info"),
        )

        # ADB 日服路径
        SettingRow.create_path_selector(
            path_config_frame,
            label=t("option.game_dir_android_japan"),
            path_var=self.app.game_dir_android_japan_var,
            select_cmd=self._select_android_japan_dir,
            tooltip=t("option.game_dir_android_japan_info"),
        )

    def _on_file_source_changed(self, *args):
        """文件来源变化时的处理"""
        source = self.app.file_source_var.get()
        # 切换到ADB模式时检查ADB可用性
        if source.startswith("adb_"):
            adb_source = self.app.get_adb_file_source()
            if not adb_source.is_available():
                from tkinter import messagebox
                messagebox.showwarning(t("common.warning"), t("message.adb.not_connected"))
                # 回退到之前的设置
                self.app.file_source_var.set(self._prev_file_source)
                return
        self._prev_file_source = source
        # 发送事件通知各tab更新
        self.app.event_generate("<<FileSourceChanged>>")

    def _select_game_resource_directory_japan(self):
        """选择日服游戏资源目录"""
        select_directory(self.app.game_resource_dir_japan_var, t("option.game_dir_windows_japan"), self.app.logger.log)

    def _open_game_resource_japan_in_explorer(self):
        """打开日服游戏资源目录"""
        open_directory(self.app.game_resource_dir_japan_var.get(), self.app.logger.log)

    def _select_android_global_dir(self):
        """通过 ADB 浏览器选择国际服 Android 目录"""
        self._select_android_dir("global", self.app.game_dir_android_global_var)

    def _select_android_japan_dir(self):
        """通过 ADB 浏览器选择日服 Android 目录"""
        self._select_android_dir("japan", self.app.game_dir_android_japan_var)

    def _select_android_dir(self, region: str, path_var: tk.StringVar):
        """打开 ADB 文件浏览器选择 Android 设备上的资源目录"""
        if not self.app.is_adb_available():
            messagebox.showwarning(t("common.warning"), t("message.adb.not_connected"), parent=self)
            return
        from .adb_browser import ADBFileBrowser
        adb_source = self.app.get_adb_file_source(server_region=region)
        browser = ADBFileBrowser(
            self,
            adb_source=adb_source,
            directory_mode=True,
            log=self.app.logger.log,
        )
        if browser.selected_paths:
            path_var.set(browser.selected_paths[0])

    def _init_adb_settings(self):
        """初始化 ADB 设置"""
        section = self._create_section(t("ui.settings.group_adb"))

        # ADB 路径 + 检测按钮
        SettingRow.create_path_selector(
            section,
            label=t("option.adb_path"),
            path_var=self.app.adb_path_var,
            select_cmd=self._select_adb_path,
            tooltip=t("option.adb_path_info"),
            download_guide_cmd=self.app.show_adb_download_guide,
            status_check=self._check_adb_available,
            extra_button=(t("action.detect"), self._detect_adb, "info")
        )

        # 设备选择
        device_container = SettingRow.create_container(section)
        SettingRow._add_label_area(device_container, t("ui.settings.adb.device"), None)

        right_frame = tb.Frame(device_container)
        right_frame.pack(side=tk.RIGHT)

        UIComponents.create_button(
            right_frame,
            text=t("action.refresh"),
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

        # 缓存路径
        SettingRow.create_path_selector(
            section,
            label=t("option.adb_cache_dir"),
            path_var=self.app.adb_cache_dir_var,
            select_cmd=self._select_adb_cache_dir,
            open_cmd=self._open_adb_cache_dir,
            tooltip=t("option.adb_cache_dir_info")
        )

        # 缓存大小 + 清理按钮
        cache_container = SettingRow.create_container(section)
        SettingRow._add_label_area(cache_container, t("ui.label.adb_cache"), None)

        UIComponents.create_button(
            cache_container,
            text=t("action.clear_cache"),
            command=self._clear_adb_cache,
            bootstyle="warning",
            style="compact"
        ).pack(side=tk.RIGHT)

        self._cache_size_label = tb.Label(cache_container, text="", font=Theme.INPUT_FONT)
        self._cache_size_label.pack(side=tk.RIGHT, padx=(0, 10))

        # 初始化状态显示（不主动检测ADB，等用户点击刷新按钮）
        self._device_status_label.config(text="")

    def _select_adb_path(self):
        """选择 ADB 可执行文件路径"""
        select_file(
            title=t("ui.dialog.select", type="ADB"),
            file_types=[FileType.EXECUTABLE, FileType.ALL],
            callback=lambda path: (
                self.app.adb_path_var.set(str(path)),
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
            self.app.logger.log(t("message.adb.detect_success", version=info))
            self._update_adb_status()
            messagebox.showinfo(t("common.success"), t("message.adb.detect_success", version=info), parent=self)
        else:
            self.app.logger.log(t("message.adb.detect_failed"))
            messagebox.showerror(t("common.error"), t("message.adb.detect_failed"), parent=self)

    def _refresh_devices(self):
        """刷新设备列表（异步执行）"""
        # 显示正在检测状态
        self._device_status_label.config(
            text=t("ui.settings.adb.detecting"),
            bootstyle="info"
        )
        # 更新缓存大小（在主线程中执行）
        self._update_cache_size()

        # 启动后台线程执行ADB检测
        thread = threading.Thread(target=self._fetch_devices_bg, daemon=True)
        thread.start()

    def _fetch_devices_bg(self):
        """后台线程：获取设备列表"""
        try:
            self.app.refresh_adb_connection()
            manager = self.app.get_adb_manager()
            devices = manager.get_devices()
            # 使用 after 在主线程中更新UI
            self.after(0, lambda: self._update_devices_ui(devices, manager))
        except Exception:
            # 检测失败，在主线程中更新状态
            self.after(0, lambda: self._device_status_label.config(
                text=t("message.adb.not_connected"),
                bootstyle="danger"
            ))

    def _update_devices_ui(self, devices, manager):
        """主线程：更新设备列表UI"""
        if not self.winfo_exists():
            return

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
                        text=t("ui.settings.adb.device_connected"),
                        bootstyle="success"
                    )
                    return
            # 没有就绪设备
            first = devices[0]
            self._device_status_label.config(
                text=t("ui.settings.adb.device_unauthorized") if first.state == "unauthorized" else t("ui.settings.adb.device_offline"),
                bootstyle="warning"
            )
        else:
            self.app.adb_device_var.set("")
            self._device_status_label.config(
                text=t("message.adb.not_connected"),
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
                text=t("message.adb.not_connected"),
                bootstyle="danger"
            )

    def _select_adb_cache_dir(self):
        """选择 ADB 缓存目录"""

        select_directory(
            var=self.app.adb_cache_dir_var,
            title=t("ui.dialog.select", type=t("option.adb_cache_dir")),
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
            self._cache_size_label.config(text=t("ui.settings.adb.cache_size", size=size_display))
        except Exception:
            self._cache_size_label.config(text="")

    def _clear_adb_cache(self):
        """清理 ADB 缓存"""
        if not messagebox.askyesno(t("common.warning"), t("message.adb.clear_cache_confirm"), parent=self):
            return
        try:
            cache = self.app.get_adb_cache()
            success, freed = cache.clear_cache()
            if success:
                self.app.logger.log(t("message.adb.clear_cache_done", size=freed))
                self._update_cache_size()
                messagebox.showinfo(t("common.success"), t("message.adb.clear_cache_done", size=freed), parent=self)
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

    def _init_saving_options(self):
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

        # 角色名称字段选择
        SettingRow.create_combobox_row(
            section,
            label=t("option.character_name_field"),
            text_var=self.app.character_name_field_var,
            values=CharacterInternalIDMap.NAME_FIELDS,
            tooltip=t("option.character_name_field_info")
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
