# gui/tabs/batch_update_tab.py

import os
import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import FileListbox, UIComponents, SettingRow
from ..utils import confirm_and_replace
from ...utils import get_search_resource_dirs


class BatchUpdateTab(TabFrame):
    """批量更新标签页，用于批量处理多个 mod 文件"""

    def __init__(self, *args, **kwargs):
        self.current_file_pairs: list[tuple[Path, Path]] = []
        self.match_strategy_var = tk.StringVar(value='path_id')
        self.workers_var = tk.IntVar(value=min(os.cpu_count() or 4, 8))
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
            height=10,
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
        worker_values = list(range(1, min(cpu_count, 8) + 1))
        self.workers_combo = SettingRow.create_combobox_row(
            option_frame, t("option.max_workers"),
            self.workers_var,
            values=worker_values,
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
        confirm_and_replace(
            file_pairs=self.current_file_pairs,
            create_backup=self.app.create_backup_var.get(),
            log=self.logger.log,
            button_to_disable=self.batch_replace_button,
            master=self.master,
        )

    def run_batch_update_thread(self):
        if not self.mod_file_list:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return
        if not all([self.app.game_resource_dir_var.get(), self.app.output_dir_var.get()]):
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

        output_dir = Path(self.app.output_dir_var.get())
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir)

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
            self.logger.status(t("status.error", error=e))
            return

        self.current_file_pairs = []
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))

        asset_types_to_replace = self.app.get_asset_types()

        crc_setting = self.app.enable_crc_correction_var.get()

        if crc_setting == "auto":
            target_paths, msg = core.find_target_bundles([self.mod_file_list[0]], search_paths)
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
            skip_unchanged=True,
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
