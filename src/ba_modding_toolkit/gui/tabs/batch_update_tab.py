# gui/tabs/batch_update_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import FileListbox, UIComponents
from ..utils import replace_file, replace_files
from ...utils import get_search_resource_dirs


class BatchUpdateTab(TabFrame):
    """批量更新标签页，用于批量处理多个 mod 文件"""

    def __init__(self, *args, **kwargs):
        self.final_output_paths: list[Path] = []
        self.replaced_source_files: list[Path] = []
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
        if not self.final_output_paths:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return

        target_files = self.replaced_source_files
        if not target_files:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return

        # 检查输出文件是否存在
        for output_path in self.final_output_paths:
            if not output_path.exists():
                messagebox.showerror(t("common.error"), t("message.file_not_found", path=output_path))
                return

        # 在主线程中显示确认对话框
        files_to_replace = []
        for i, output_path in enumerate(self.final_output_paths):
            if i < len(target_files):
                target_file = target_files[i]
                files_to_replace.append(f"  {target_file.name}")

        # 限制显示数量，最多显示10项
        max_display = 10
        if len(files_to_replace) > max_display:
            displayed_files = files_to_replace[:max_display]
            remaining_count = len(files_to_replace) - max_display
            files_list = "\n".join(displayed_files) + f"\n{t('message.and_more_files', count=remaining_count)}"
        else:
            files_list = "\n".join(files_to_replace)

        confirm_message = t("message.confirm_replace_files", count=len(files_to_replace), files=files_list)

        # 显示确认对话框，如果用户确认则执行覆盖
        if messagebox.askyesno(t("common.warning"), confirm_message):
            self.run_in_thread(self.batch_replace_original)

    def batch_replace_original(self):
        """实际的批量覆盖逻辑"""
        target_files = self.replaced_source_files

        # 只有一个文件时，使用 replace_file
        if len(self.final_output_paths) == 1 and len(target_files) >= 1:
            success = replace_file(
                source_path=self.final_output_paths[0],
                dest_path=target_files[0],
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=False,
                log=self.logger.log,
            )

            if success:
                self.logger.status(t("status.done"))
            else:
                self.logger.status(t("status.failed"))
        else:
            # 多个文件时，使用 replace_files
            file_pairs: list[tuple[Path, Path]] = []
            for i, output_path in enumerate(self.final_output_paths):
                if i < len(target_files):
                    file_pairs.append((output_path, target_files[i]))

            success_count, fail_count = replace_files(
                file_pairs=file_pairs,
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=False,
                log=self.logger.log,
            )

            self.logger.status(t("status.done"))

        # 覆盖完成后禁用按钮
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))

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
        self.final_output_paths = []
        self.replaced_source_files = []
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
            perform_crc = True
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
            skip_unchanged=True
        )

        # 记录输出文件路径和被替换的原始文件路径
        self.final_output_paths = [pair[0] for pair in file_pairs]
        self.replaced_source_files = [pair[1] for pair in file_pairs]

        total_files = len(self.mod_file_list)

        self.logger.log(t("log.batch.summary", total=total_files, success=success_count, fail=fail_count))

        if failed_tasks:
            self.logger.log(t("log.batch.failed_items_cnt", count=fail_count))
            failed_list = "\n".join([t("log.batch.failed_item", filename=f) for f in failed_tasks])
            self.logger.log(failed_list)

        # 如果有成功处理的文件，启用覆盖按钮
        if self.final_output_paths:
            self.master.after(0, lambda: self.batch_replace_button.config(state=tk.NORMAL))

        self.logger.status(t("status.done"))
        messagebox.showinfo(t("common.success"), t("message.batch.success", success=success_count, fail=fail_count))
