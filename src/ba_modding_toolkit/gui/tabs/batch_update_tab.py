# gui/tabs/batch_update_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ...bundle import Bundle
from ..base_tab import TabFrame
from ..components import FileListbox, UIComponents, SettingRow
from ..utils import confirm_and_replace
from ...utils import get_search_resource_dirs


class BatchUpdateTab(TabFrame):
    """批量更新标签页，用于批量处理多个 mod 文件"""

    def __init__(self, *args, **kwargs):
        self.current_file_pairs: list[tuple[Path, Path]] = []
        self.match_strategy_var = tk.StringVar(value='path_id')
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
        if not any([self.app.replace_texture2d_var.get(), self.app.replace_textasset_var.get(), self.app.replace_mesh_var.get(), self.app.replace_all_var.get()]):
            messagebox.showerror(t("common.error"), t("message.missing_asset_type"))
            return

        self.run_in_thread(self._batch_update_worker)

    def _batch_update_worker(self):
        self.logger.log("\n" + "#"*50)
        self.logger.log(t("log.batch.start"))
        self.logger.status(t("status.batch_starting"))

        output_dir = Path(self.app.output_dir_var.get())
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
            self.logger.status(t("status.error", error=e))
            return

        # 重置输出文件路径列表和按钮状态
        self.current_file_pairs = []
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))

        asset_types_to_replace = set()
        if self.app.replace_all_var.get():
            asset_types_to_replace = {"ALL"}
        else:
            if self.app.replace_texture2d_var.get(): asset_types_to_replace.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types_to_replace.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types_to_replace.add("Mesh")

        crc_setting = self.app.enable_crc_correction_var.get()
        perform_crc = False

        if crc_setting == "auto":
            perform_crc = Bundle.check_need_crc(self.mod_file_list[0], log=self.logger.log)
        elif crc_setting == "true":
            perform_crc = True

        save_options = core.SaveOptions(
            perform_crc=perform_crc,
            extra_bytes=self.app.get_extra_bytes(),
            compression=self.app.compression_method_var.get()
        )

        spine_options = core.SpineOptions(
            enabled=self.app.enable_spine_conversion_var.get(),
            converter_path=Path(self.app.spine_converter_path_var.get()),
            target_version=self.app.target_spine_version_var.get()
        )

        # 更新UI状态的回调函数
        def progress_callback(current, total, filename):
            self.logger.status(t("status.processing_batch", current=current, total=total, filename=filename))

        success_count, fail_count, failed_tasks, file_pairs = core.process_batch_mod_update(
            mod_file_list=self.mod_file_list,
            search_paths=search_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            log=self.logger.log,
            progress_callback=progress_callback,
            skip_unchanged=True,
            match_strategy=self.match_strategy_var.get()
        )

        self.current_file_pairs = file_pairs

        total_files = len(self.mod_file_list)

        self.logger.log(t("log.batch.summary", total=total_files, success=success_count, fail=fail_count))

        if failed_tasks:
            self.logger.log(t("log.batch.failed_items_cnt", count=fail_count))
            failed_list = "\n".join([t("log.batch.failed_item", filename=f) for f in failed_tasks])
            self.logger.log(failed_list)

        # 如果有成功处理的文件，启用覆盖按钮
        if self.current_file_pairs:
            self.master.after(0, lambda: self.batch_replace_button.config(state=tk.NORMAL))

        self.logger.status(t("status.done"))
        messagebox.showinfo(t("common.success"), t("message.batch.success", success=success_count, fail=fail_count))
