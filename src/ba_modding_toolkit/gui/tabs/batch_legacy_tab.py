# gui/tabs/batch_legacy_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ...utils import get_search_resource_dirs
from ..base_tab import TabFrame
from ..components import FileListbox, UIComponents
from ..utils import replace_file, replace_files


class BatchLegacyTab(TabFrame):
    """批量处理旧版标签页，用于批量将旧版文件转换为新版国际服格式"""

    def __init__(self, *args, **kwargs):
        self.final_output_paths: list[Path] = []
        self.replaced_source_files: list[Path] = []
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        self.legacy_file_list: list[Path] = []

        # 批量处理文件列表
        self.batch_file_listbox = FileListbox(
            self,
            title=t("ui.label.mod_file"),
            file_list=self.legacy_file_list,
            placeholder_text=t("ui.mod_update.placeholder_batch"),
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
            action_button_frame,
            text=t("action.start"),
            command=self.run_conversion_thread,
            bootstyle="success",
            style="large"
        )
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # 替换原文件按钮
        self.batch_replace_button = UIComponents.create_button(
            action_button_frame,
            text=t("action.replace_original"),
            command=self.replace_original_thread,
            bootstyle="danger",
            state="disabled",
            style="large"
        )
        self.batch_replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    def replace_original_thread(self):
        """覆盖原文件的线程入口"""
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
            self.run_in_thread(self.replace_original)

    def replace_original(self):
        """实际的覆盖逻辑"""
        target_files = self.replaced_source_files

        # 只有一个文件时，使用 replace_file
        if len(self.final_output_paths) == 1 and len(target_files) >= 1:
            success = replace_file(
                source_path=self.final_output_paths[0],
                dest_path=target_files[0],
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=False,  # 已经在上一步确认过了
                log=self.logger.log,
            )

            # 更新状态栏
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
                ask_confirm=False,  # 已经在上一步确认过了
                log=self.logger.log,
            )

            self.logger.status(t("status.done"))

        # 覆盖完成后禁用按钮
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))

    def run_conversion_thread(self):
        """转换按钮的线程入口"""
        self.run_in_thread(self._run_batch_conversion)

    def _run_batch_conversion(self):
        """批量处理旧版到新版国际服的转换"""
        output_dir = Path(self.app.output_dir_var.get())

        if not self.legacy_file_list:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.log(f'❌ {t("message.create_dir_failed_detail",path=output_dir, error=e)}')
            return

        # 重置输出文件路径列表和按钮状态
        self.final_output_paths = []
        self.replaced_source_files = []
        self.master.after(0, lambda: self.batch_replace_button.config(state=tk.DISABLED))

        # 准备选项
        crc_setting = self.app.enable_crc_correction_var.get()
        perform_crc = False

        if crc_setting == "auto":
            target_bundle = self.legacy_file_list[0]
            platform, unity_version = core.get_unity_platform_info(target_bundle)
            self.logger.log(t("log.platform_info", platform=platform, version=unity_version))
            perform_crc = (platform == "StandaloneWindows64")
        elif crc_setting == "true":
            perform_crc = True

        save_options = core.SaveOptions(
            perform_crc=perform_crc,
            extra_bytes=self.app.get_extra_bytes(),
            compression=self.app.compression_method_var.get()
        )

        # 从设置页获取资源类型
        asset_types_to_replace = set()
        if self.app.replace_all_var.get():
            asset_types_to_replace = {"ALL"}
        else:
            if self.app.replace_texture2d_var.get(): asset_types_to_replace.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types_to_replace.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types_to_replace.add("Mesh")

        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        self.logger.status(t("common.processing"))

        # 调用批量处理函数
        success_count, fail_count, failed_tasks, file_pairs = core.process_batch_legacy_batch(
            legacy_file_list=self.legacy_file_list,
            search_paths=search_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            log=self.logger.log,
            progress_callback=lambda current, total, filename: self.logger.status(
                t("status.processing_batch", current=current, total=total, filename=filename)
            ),
            skip_unchanged=True
        )

        # 记录输出文件路径和被替换的原始文件路径
        self.final_output_paths = [pair[0] for pair in file_pairs]
        self.replaced_source_files = [pair[1] for pair in file_pairs]

        total_files = len(self.legacy_file_list)
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
