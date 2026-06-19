# gui/tabs/mod_update_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ...models import FileType, FilePair
from ... import core
from ...searching import get_search_dirs, find_target_bundles, find_target_bundles_remote
from ..base_tab import TabFrame
from ..components import DropZone, UIComponents, SettingRow, ModeSwitcher
from ..utils import confirm_and_replace


class ModUpdateTab(TabFrame):
    """Mod更新标签页，用于单个mod文件的更新"""

    def __init__(self, *args, **kwargs):
        self.source_paths: list[Path] = []
        self.target_paths: list[Path] = []
        self.current_file_pairs: list[FilePair] = []
        self.match_strategy_var = tk.StringVar(value='path_id')
        self.resource_source_var = tk.StringVar(value='local')  # "local" | "adb"
        self._adb_remote_target_paths: list[str] = []  # ADB 模式下目标的远程路径
        self._search_path_var = None  # 延迟初始化，在 create_widgets 中绑定
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        # 1. 源文件组
        self.old_mod_zone = DropZone(
            self, title=t("ui.label.mod_file"),
            placeholder_text=t("ui.mod_update.placeholder_old"),
            on_files_selected=self.on_old_mod_selected,
            file_types=[FileType.BUNDLE, FileType.BUNDLE_BACKUP, FileType.ALL],
            logger=self.logger
        )

        # 2. 资源来源切换 + 目标资源文件组
        source_frame = tb.Frame(self)
        source_frame.pack(fill=tk.X, pady=(0, 2))

        self._source_switcher = ModeSwitcher(
            source_frame,
            mode_var=self.resource_source_var,
            options=[
                ("local", t("resource_source.windows")),
                ("adb", t("resource_source.android")),
            ],
            command=self._on_resource_source_changed
        )

        self._search_path_var = tk.StringVar(value=self.app.game_resource_dir_var.get())

        self.new_mod_zone = DropZone(
            self, title=t("ui.label.target_resource_bundle"),
            placeholder_text=t("ui.mod_update.placeholder_new"),
            on_files_selected=self.on_new_mod_selected,
            file_types=[FileType.BUNDLE, FileType.ALL],
            search_path_var=self._search_path_var,
            logger=self.logger,
            resource_source_var=self.resource_source_var,
            app=self.app,
        )

        # 匹配策略选择
        strategy_frame = tb.Labelframe(self, text=t("ui.label.options"), padding=10)
        strategy_frame.pack(fill=tk.X, pady=(5, 0))

        self.strategy_combo = SettingRow.create_combobox_row(
            strategy_frame, t("option.match_strategy"),
            self.match_strategy_var,
            values=['path_id', 'cont_name_type', 'name_type'],
            tooltip=t("option.match_strategy_info")
        )

        # 操作按钮区域
        action_button_frame = tb.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        self.run_button = UIComponents.create_button(action_button_frame, t("action.update"), self.run_update_thread, bootstyle="success", style="large")
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)

        self.replace_button = UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread, bootstyle="danger", state="disabled", style="large")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)

    def _on_resource_source_changed(self):
        """资源来源切换时的处理"""
        self.target_paths = []
        self._adb_remote_target_paths = []
        self.new_mod_zone.clear()

        if self.resource_source_var.get() == "adb":
            # 检查 ADB 设备是否在线
            adb_source = self.app.get_adb_file_source()
            if not adb_source.is_available():
                from tkinter import messagebox
                messagebox.showwarning(t("common.warning"), t("adb.not_connected"))
                self.resource_source_var.set("local")
                return
            # 使用配置中的 Android 目录，若为空则使用 ADB 默认路径
            region = self.app.adb_server_region_var.get()
            if region == "japan":
                android_dir = self.app.game_dir_android_japan_var.get()
            else:
                android_dir = self.app.game_dir_android_global_var.get()
            if not android_dir:
                android_dir = adb_source.get_base_path() or ""
            self._search_path_var.set(android_dir)
        else:
            # 恢复 Windows 游戏目录
            self._search_path_var.set(self.app.game_resource_dir_var.get())

    def on_old_mod_selected(self, paths: list[Path]):
        """源文件组选中后的处理"""
        self.source_paths = paths
        self.logger.log(t("log.file.selected_num", count=len(paths)))
        for p in paths:
            self.logger.log(f"  - {p.name}")
        self.target_paths = []
        self._adb_remote_target_paths = []
        self.new_mod_zone.clear()
        self.run_in_thread(self._find_target_bundles_worker)

    def on_new_mod_selected(self, paths: list[Path]):
        """目标资源文件组选中后的处理"""
        self.target_paths = paths
        # 保存 ADB 远程路径（如果有）
        if self.resource_source_var.get() == "adb":
            self._adb_remote_target_paths = self.new_mod_zone.adb_remote_paths
        else:
            self._adb_remote_target_paths = []
        self.logger.log(t("log.file.selected_num", count=len(paths)))
        for p in paths:
            self.logger.log(f"  - {p.name}")
        self.logger.status(t("status.ready"))

    def _find_target_bundles_worker(self):
        self.new_mod_zone.set_searching()
        self.logger.status(t("status.processing_detailed"))

        if self.resource_source_var.get() == "adb":
            self._find_target_bundles_adb_worker()
        else:
            self._find_target_bundles_local_worker()

    def _find_target_bundles_local_worker(self):
        """本地模式搜索目标文件"""
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_dirs(base_game_dir)

        found_paths, message = find_target_bundles(
            self.source_paths,
            search_paths,
            self.logger.log
        )

        self.master.after(0, lambda: self._handle_search_result(found_paths, message))

    def _find_target_bundles_adb_worker(self):
        """ADB 模式搜索目标文件"""
        adb_source = self.app.get_adb_file_source()
        if not adb_source.is_available():
            self.master.after(0, lambda: self.new_mod_zone.set_error(t("adb.device_none")))
            return

        found_remote_paths, message = find_target_bundles_remote(
            self.source_paths,
            adb_source,
            self.logger.log
        )

        if not found_remote_paths:
            self.master.after(0, lambda: self._handle_search_result([], message))
            return

        # 将远程路径缓存到本地
        local_paths: list[Path] = []
        for remote_path in found_remote_paths:
            try:
                local_path = adb_source.ensure_local(remote_path)
                local_paths.append(local_path)
            except Exception as e:
                self.logger.log(t("log.adb.pull_failed", path=remote_path, error=e))

        self._adb_remote_target_paths = found_remote_paths
        self.master.after(0, lambda: self._handle_search_result(local_paths, message))

    def _handle_search_result(self, found_paths: list[Path], message: str):
        """处理搜索结果"""
        if not found_paths:
            ui_message = t("ui.mod_update.status_not_found", message=message)
            self.new_mod_zone.set_error(ui_message)
            self.logger.status(t("status.search_not_found"))
        elif len(found_paths) == 1:
            self.new_mod_zone.set_files(found_paths)
        else:
            # 多个匹配文件，直接将所有文件设置为目标组
            self.new_mod_zone.set_files(found_paths)

    def run_update_thread(self):
        if not self.source_paths or not self.target_paths:
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return
        if not self.app.output_dir_var.get():
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return

        if not self.app.has_any_asset_type():
            messagebox.showerror(t("common.error"), t("message.missing_asset_type"))
            return

        self.run_in_thread(self.run_update)

    def run_update(self):
        self.current_file_pairs = []
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))

        self.logger.log("\n" + "="*50)
        self.logger.log(t("log.mod_update.updating"))
        self.logger.log(f"  > {t('log.mod_update.source_files', count=len(self.source_paths))}")
        for src in self.source_paths:
            self.logger.log(f"    - {src.name}")
        self.logger.log(f"  > {t('log.mod_update.target_files', count=len(self.target_paths))}")
        for tgt in self.target_paths:
            self.logger.log(f"    - {tgt.name}")
        self.logger.status(t("status.processing_detailed", filename=self.source_paths[0].name))

        output_dir = self.app.get_output_subdir(self.app.OUTPUT_SUBDIR_BUNDLES)
        asset_types_to_replace = self.app.get_asset_types()
        perform_crc = self.app.resolve_crc_setting(self.target_paths[0])
        save_options = self.app.build_save_options(perform_crc)
        spine_options = self.app.build_spine_options()

        success, message, file_pairs = core.process_mod_update(
            source_paths=self.source_paths,
            target_paths=self.target_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            match_strategy=self.match_strategy_var.get(),
            skip_unchanged=self.app.skip_unchanged_var.get(),
            log=self.logger.log,
        )

        self.current_file_pairs = file_pairs

        if not success:
            messagebox.showerror(t("common.error"), message)
            return

        # 处理所有目标都被跳过的情况
        if message == "all_targets_unchanged":
            self.logger.log(t("log.mod_update.all_targets_unchanged"))
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
            messagebox.showinfo(t("common.success"), t("message.mod_update.all_targets_unchanged"))
            self.logger.status(t("status.done"))
            return

        # 输出处理总结
        self.logger.log(f'\n--- {t("log.summary.title")} ---')
        self.logger.log(f"✅ {t('log.summary.output_files', count=len(file_pairs))}")
        for pair in file_pairs:
            self.logger.log(f"  - {pair.source.name}")
        self.logger.log(f'\n🎉 {t("log.mod_update.all_processes_complete", count=len(file_pairs))}')

        if file_pairs:
            self.logger.log(t("log.replace_original", button=t("action.replace_original")))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.log(t("log.generated_file_not_found"))
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
            messagebox.showinfo(t("common.success"), t("message.process_success"))

        self.logger.status(t("status.done"))

    def replace_original_thread(self):
        """替换原文件（支持 ADB 推送）"""
        if self.resource_source_var.get() == "adb":
            self._replace_original_adb()
        else:
            confirm_and_replace(
                file_pairs=self.current_file_pairs,
                create_backup=self.app.create_backup_var.get(),
                log=self.logger.log,
                button_to_disable=self.replace_button,
                master=self.master,
            )

    def _replace_original_adb(self):
        """ADB 模式下的替换原文件（推送到设备）"""
        if not self.current_file_pairs:
            return

        # 构建确认消息
        files_list = "\n".join([f"  {pair.source.name}" for pair in self.current_file_pairs[:10]])
        if len(self.current_file_pairs) > 10:
            files_list += f"\n{t('message.and_more_files', count=len(self.current_file_pairs) - 10)}"

        confirm_message = t("adb.push.confirm", files=files_list)
        if not messagebox.askyesno(t("common.warning"), confirm_message):
            return

        adb_source = self.app.get_adb_file_source()
        if not adb_source.is_available():
            messagebox.showerror(t("common.error"), t("adb.device_none"))
            return

        self.run_in_thread(self._push_files_worker, adb_source)

    def _push_files_worker(self, adb_source):
        """后台推送文件到设备"""
        success_count = 0
        fail_count = 0

        for pair in self.current_file_pairs:
            # 查找对应的远程路径
            remote_path = self._find_remote_path_for_output(pair)
            if not remote_path:
                self.logger.log(t("log.adb.push_failed", path=pair.output.name, error="remote path not found"))
                fail_count += 1
                continue

            self.logger.log(t("adb.push.start", name=pair.output.name))
            if adb_source.push_file(pair.output, remote_path, self.logger.log):
                self.logger.log(t("adb.push.success", name=pair.output.name))
                success_count += 1
            else:
                self.logger.log(t("adb.push.failed", name=pair.output.name))
                fail_count += 1

        self.logger.log(t("log.success_fail", success=success_count, fail=fail_count))
        self.master.after(0, lambda: messagebox.showinfo(
            t("common.tip"),
            t("message.replace_result", success=success_count, fail=fail_count)
        ))
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
        self.logger.status(t("status.done"))

    def _find_remote_path_for_output(self, pair: FilePair) -> str | None:
        """根据输出文件对找到对应的远程路径"""
        output_name = pair.output.name
        # 在远程路径列表中查找同名文件
        for remote_path in self._adb_remote_target_paths:
            if Path(remote_path).name == output_name:
                return remote_path
        # 也尝试用 source 名匹配
        source_name = pair.source.name
        for remote_path in self._adb_remote_target_paths:
            if Path(remote_path).name == source_name:
                return remote_path
        # 最后尝试从缓存 manifest 反查
        adb_source = self.app.get_adb_file_source()
        remote = adb_source.cache.find_remote_path(pair.source)
        if remote:
            return remote
        return None
