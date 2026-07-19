# gui/tabs/batch_update_tab.py

import os
import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ...models import FilePair
from ... import core
from ...searching import get_search_dirs, find_target_bundles, find_target_bundles_remote
from ..components import FileListbox, UIComponents, SettingRow
from ..utils import confirm_and_replace
from .base_tab import TabFrame

class BatchUpdateTab(TabFrame):
    """批量更新标签页，用于批量处理多个 mod 文件"""

    def __init__(self, *args, **kwargs):
        self.current_file_pairs: list[FilePair] = []
        self.match_strategy_var = tk.StringVar(value='path_id')
        self.workers_var = tk.IntVar(value=min(os.cpu_count() or 4, 8))
        self._adb_remote_paths: list[str] = []  # ADB 模式下目标的远程路径
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        self.mod_file_list: list[Path] = []

        # 创建文件列表框
        # 自定义显示格式：文件夹名 / 文件名
        self.batch_file_listbox = FileListbox(
            self,
            t("ui.label.mod_file"),
            self.mod_file_list,
            t("ui.mod_update.placeholder_batch"),
            height=5,
            logger=self.logger,
            display_formatter=lambda p: f"{p.parent.name} / {p.name}"
        )
        self.batch_file_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 匹配策略选择 + 线程数选择
        option_frame = tb.Labelframe(self, text=t("ui.label.options"), padding=10)
        option_frame.pack(fill=tk.X, pady=(5, 0))

        self.strategy_combo = SettingRow.create_combobox_row(
            option_frame, t("option.match_strategy"),
            self.match_strategy_var,
            values=['path_id', 'cont_name_type', 'name_type'],
            tooltip=t("option.match_strategy_info")
        )

        cpu_count = os.cpu_count() or 4
        max_workers = min(cpu_count, 8)
        self.workers_spinbox = SettingRow.create_spinbox_row(
            option_frame, t("option.max_workers"),
            self.workers_var,
            from_=1,
            to=max_workers,
            tooltip=t("option.max_workers_info")
        )

        # 进度条区域
        progress_frame = tb.Frame(self)
        progress_frame.pack(fill=tk.X, pady=(5, 0))

        self.progress_label = tb.Label(progress_frame, text="")
        self.progress_label.pack(fill=tk.X)

        self.progress_bar = tb.Progressbar(
            progress_frame,
            mode="determinate",
            bootstyle="success-striped"
        )
        self.progress_bar.pack(fill=tk.X, pady=(3, 0))

        # 操作按钮区域
        action_button_frame = tb.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        # 运行按钮
        run_button = UIComponents.create_button(
            action_button_frame, text=t("action.start"),
            command=self.run_batch_update_thread, bootstyle="success", style="large"
        )
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # 覆盖原文件按钮
        self.batch_replace_button = UIComponents.create_button(
            action_button_frame,
            text=t("action.replace_original"),
            command=self.batch_replace_original_thread,
            bootstyle="danger",
            state="disabled",
            style="large"
        )
        self.batch_replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def batch_replace_original_thread(self):
        """批量覆盖原文件的线程入口"""
        if self.app.is_adb_mode():
            self._replace_original_adb()
        else:
            confirm_and_replace(
                file_pairs=self.current_file_pairs,
                create_backup=self.app.create_backup_var.get(),
                log=self.logger.log,
                button_to_disable=self.batch_replace_button,
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

        confirm_message = t("message.adb.push_confirm", files=files_list)
        if not messagebox.askyesno(t("common.warning"), confirm_message):
            return

        adb_source = self.app.get_adb_file_source()
        if not adb_source.is_available():
            messagebox.showerror(t("common.error"), t("message.adb.not_connected"))
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

            self.logger.log(t("log.adb.push_start", name=pair.output.name))
            if adb_source.push_file(pair.output, remote_path, self.logger.log):
                self.logger.log(t("log.adb.push_success", name=pair.output.name))
                success_count += 1
            else:
                self.logger.log(t("log.adb.push_failed", path=pair.output.name, error="push failed"))
                fail_count += 1

        self.logger.log(t("log.success_fail", success=success_count, fail=fail_count))
        self.master.after(0, lambda: messagebox.showinfo(
            t("common.tip"),
            t("message.replace_result", success=success_count, fail=fail_count)
        ))
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))
        self.logger.status(t("status.done"))

    def _find_remote_path_for_output(self, pair: FilePair) -> str | None:
        """根据输出文件对找到对应的远程路径"""
        output_name = pair.output.name
        # 在远程路径列表中查找同名文件
        for remote_path in self._adb_remote_paths:
            if Path(remote_path).name == output_name:
                return remote_path
        # 也尝试用 source 名匹配
        source_name = pair.source.name
        for remote_path in self._adb_remote_paths:
            if Path(remote_path).name == source_name:
                return remote_path
        # 最后尝试从缓存 manifest 反查
        adb_source = self.app.get_adb_file_source()
        remote = adb_source.cache.find_remote_path(pair.source)
        if remote:
            return remote
        return None

    def run_batch_update_thread(self):
        if not self.mod_file_list:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return
        if not self.app.is_adb_mode():
            if not all([self.app.get_current_resource_dir(), self.app.output_dir_var.get()]):
                messagebox.showerror(t("common.error"), t("message.missing_paths"))
                return
        else:
            if not self.app.output_dir_var.get():
                messagebox.showerror(t("common.error"), t("message.missing_paths"))
                return
        if not self.app.has_any_asset_type():
            messagebox.showerror(t("common.error"), t("message.missing_asset_type"))
            return

        self.run_in_thread(self._batch_update_worker)

    def _init_progress(self, total: int):
        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = 0
        self.progress_label.config(text=t("status.processing_batch", current=0, total=total, filename=""))

    def _update_progress(self, completed: int, total: int, filename: str):
        self.progress_bar["value"] = completed
        self.progress_label.config(
            text=t("status.processing_batch", current=completed, total=total, filename=filename)
        )
        self.logger.status(t("status.processing_batch", current=completed, total=total, filename=filename))

    def _batch_update_worker(self):
        self.logger.log("\n" + "#"*50)
        self.logger.log(t("log.batch.start"))
        self.logger.status(t("status.batch_starting"))

        output_dir = self.app.get_output_subdir(self.app.OUTPUT_SUBDIR_BUNDLES)

        if self.app.is_adb_mode():
            # ADB 模式：先远程搜索目标，拉取到本地缓存，再使用本地缓存目录搜索
            adb_source = self.app.get_adb_file_source()
            if not adb_source.is_available():
                self.logger.log(t("message.adb.not_connected"))
                return
            # 预搜索：找到所有远程目标并拉取到本地
            search_path_dirs: set[Path] = set()
            for mod_file in self.mod_file_list:
                try:
                    remote_targets, _ = find_target_bundles_remote([mod_file], adb_source, self.logger.log)
                    for remote_path in remote_targets:
                        try:
                            local_path = adb_source.ensure_local(remote_path)
                            search_path_dirs.add(local_path.parent)
                            if remote_path not in self._adb_remote_paths:
                                self._adb_remote_paths.append(remote_path)
                        except RuntimeError as e:
                            self.logger.log(t("log.adb.pull_failed", path=remote_path, error=e))
                except Exception as e:
                    self.logger.log(t("log.adb.pull_failed", path=mod_file.name, error=e))
            search_paths = list(search_path_dirs) if search_path_dirs else []
        else:
            # 本地模式
            base_game_dir = Path(self.app.get_current_resource_dir())
            search_paths = get_search_dirs(base_game_dir)

        self.current_file_pairs = []
        self._adb_remote_paths = []
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))

        asset_types_to_replace = self.app.get_asset_types()

        crc_setting = self.app.enable_crc_correction_var.get()

        if crc_setting == "auto":
            if self.app.is_adb_mode():
                # ADB 模式下使用已拉取的本地缓存文件检查 CRC
                if self._adb_remote_paths:
                    adb_source = self.app.get_adb_file_source()
                    try:
                        local_path = adb_source.ensure_local(self._adb_remote_paths[0])
                        perform_crc = self.app.resolve_crc_setting(local_path)
                    except RuntimeError:
                        perform_crc = self.app.resolve_crc_setting(None)
                else:
                    perform_crc = self.app.resolve_crc_setting(None)
            else:
                target_paths, msg = find_target_bundles([self.mod_file_list[0]], search_paths)
                if not target_paths:
                    self.logger.log(msg)
                    return
                perform_crc = self.app.resolve_crc_setting(target_paths[0])
        else:
            perform_crc = self.app.resolve_crc_setting(None)

        save_options = self.app.build_save_options(perform_crc)
        spine_options = self.app.build_spine_options()

        total = len(self.mod_file_list)
        self.master.after(0, lambda: self._init_progress(total))

        def progress_callback(completed, total, filename):
            self.master.after(0, lambda: self._update_progress(completed, total, filename))

        success_count, fail_count, failed_tasks, file_pairs = core.process_batch_mod_update(
            mod_file_list=self.mod_file_list,
            search_paths=search_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            max_workers=self.workers_var.get(),
            log=self.logger.log,
            progress_callback=progress_callback,
            skip_unchanged=self.app.skip_unchanged_var.get(),
            match_strategy=self.match_strategy_var.get(),
        )

        self.current_file_pairs = file_pairs

        self.logger.log(t("log.batch.summary", total=total, success=success_count, fail=fail_count))

        if failed_tasks:
            self.logger.log(t("log.batch.failed_items_cnt", count=fail_count))
            failed_list = "\n".join([t("log.batch.failed_item", filename=f) for f in failed_tasks])
            self.logger.log(failed_list)

        if self.current_file_pairs:
            self.master.after(0, lambda: self.batch_replace_button.config(state=tk.NORMAL))

        self.logger.status(t("status.done"))
        messagebox.showinfo(t("common.success"), t("message.batch.success", success=success_count, fail=fail_count))
