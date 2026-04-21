# gui/tabs/mod_update_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from enum import IntEnum

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import GroupDropZone, FileListbox, ModeSwitcher, UIComponents
from ..dialogs import FileSelectionDialog
from ..utils import replace_file, replace_files
from ...utils import get_search_resource_dirs

class Mode(IntEnum):
    """Mod更新模式"""
    SINGLE = 0
    BATCH = 1


class ModUpdateTab(TabFrame):
    """一个整合了单个更新和批量更新功能的标签页"""
    def __init__(self, *args, **kwargs):
        self.final_output_paths: list[Path] = []
        self.replaced_source_files: list[Path] = []
        self.current_file_pairs: list[tuple[Path, Path]] = []
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        self.source_paths: list[Path] = []
        self.target_paths: list[Path] = []
        self.mod_file_list: list[Path] = []
        
        # --- 模式切换 ---
        self.mode_var = tk.IntVar(value=Mode.SINGLE)

        self.mode_switcher = ModeSwitcher(
            self,
            self.mode_var,
            [
                (Mode.SINGLE, t("ui.mod_update.mode_single")),
                (Mode.BATCH, t("ui.mod_update.mode_batch"))
            ],
            command=self._switch_view
        )

        # --- 容器框架 ---
        self.single_frame = tb.Frame(self)
        self.batch_frame = tb.Frame(self)
        
        # 创建两种模式的UI
        self._create_single_mode_widgets(self.single_frame)
        self._create_batch_mode_widgets(self.batch_frame)
        
        # 初始化视图
        self._switch_view()

    def _switch_view(self):
        """根据选择的模式显示或隐藏对应的UI框架"""
        if self.mode_var.get() == Mode.SINGLE:
            self.batch_frame.pack_forget()
            self.single_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.single_frame.pack_forget()
            self.batch_frame.pack(fill=tk.BOTH, expand=True)

    # --- 单个更新UI和逻辑 ---
    def _create_single_mode_widgets(self, parent):
        # 1. 源文件组
        self.old_mod_zone = GroupDropZone(
            parent, title=t("ui.label.mod_file"),
            placeholder_text=t("ui.mod_update.placeholder_old"),
            on_files_selected=self.on_old_mod_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            logger=self.logger
        )
        
        # 2. 目标资源文件组
        self.new_mod_zone = GroupDropZone(
            parent, title=t("ui.label.target_resource_bundle"),
            placeholder_text=t("ui.mod_update.placeholder_new"),
            on_files_selected=self.on_new_mod_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            search_path_var=self.app.game_resource_dir_var,
            logger=self.logger
        )

        # 操作按钮区域
        action_button_frame = tb.Frame(parent)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        self.run_button = UIComponents.create_button(action_button_frame, t("action.update"), self.run_update_thread, bootstyle="success", style="large")
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)
        
        self.replace_button = UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread, bootstyle="danger", state="disabled", style="large")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)

    def on_old_mod_selected(self, paths: list[Path]):
        """源文件组选中后的处理"""
        self.source_paths = paths
        self.logger.log(t("log.mod_update.source_files", count=len(paths)))
        for p in paths:
            self.logger.log(f"  - {p.name}")
        self.target_paths = []
        self.new_mod_zone.clear()
        self.run_in_thread(self._find_target_bundles_worker)

    def on_new_mod_selected(self, paths: list[Path]):
        """目标资源文件组选中后的处理"""
        self.target_paths = paths
        self.logger.log(t("log.mod_update.target_files", count=len(paths)))
        for p in paths:
            self.logger.log(f"  - {p.name}")
        self.logger.status(t("status.ready"))

    def _find_target_bundles_worker(self):
        self.new_mod_zone.set_searching()
        self.logger.status(t("status.processing_detailed"))
        
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        found_paths, message = core.find_target_bundles(
            self.source_paths,
            search_paths,
            self.logger.log
        )
        
        self.master.after(0, lambda: self._handle_search_result(found_paths, message))
    
    def _handle_search_result(self, found_paths: list[Path], message: str):
        """处理搜索结果"""
        if not found_paths:
            ui_message = t("ui.mod_update.status_not_found", message=message)
            self.new_mod_zone.set_error(ui_message)
            self.logger.status(t("status.search_not_found"))
        elif len(found_paths) == 1:
            self.target_paths = found_paths
            self.new_mod_zone.set_files(found_paths)
            self.logger.log(t("log.file.loaded", path=found_paths[0]))
            self.logger.status(t("status.ready"))
        else:
            # 多个匹配文件，直接将所有文件设置为目标组
            self.target_paths = found_paths
            self.new_mod_zone.set_files(found_paths)
            self.logger.log(t("message.search.found_multiple_matches", count=len(found_paths)))
            self.logger.status(t("status.ready"))

    def run_update_thread(self):
        if not self.source_paths or not self.target_paths:
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return
        if not self.app.output_dir_var.get():
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return
        
        if not any([self.app.replace_texture2d_var.get(), self.app.replace_textasset_var.get(), self.app.replace_mesh_var.get(), self.app.replace_all_var.get()]):
            messagebox.showerror(t("common.error"), t("message.missing_asset_type"))
            return

        self.run_in_thread(self.run_update)

    def run_update(self):
        self.current_file_pairs = []
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))

        output_dir = Path(self.app.output_dir_var.get())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
            return

        self.logger.log("\n" + "="*50)
        self.logger.log(t("log.mod_update.updating"))
        self.logger.status(t("status.processing_detailed", filename=self.source_paths[0].name))
        
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
            platform, unity_version = core.get_unity_platform_info(self.target_paths[0])
            self.logger.log(t("log.platform_info", platform=platform, version=unity_version))
            perform_crc = platform == "StandaloneWindows64"
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
        
        success, message, file_pairs = core.process_mod_update(
            source_paths=self.source_paths,
            target_paths=self.target_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            log=self.logger.log
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

        if file_pairs:
            self.logger.log(t("log.file.saved", path=file_pairs[0][0]))
            self.logger.log(t("log.replace_original", button=t("action.replace_original")))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.log(t("log.generated_file_not_found"))
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
            messagebox.showinfo(t("common.success"), t("message.process_success"))
        
        self.logger.status(t("status.done"))

    def replace_original_thread(self):
        if not self.current_file_pairs:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return
        
        self.run_in_thread(self.replace_original)

    def replace_original(self):
        if len(self.current_file_pairs) == 1:
            source_file, target_file = self.current_file_pairs[0]
            replace_file(
                source_path=source_file,
                dest_path=target_file,
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=True,
                confirm_message=t("message.confirm_replace_file", path=target_file),
                log=self.logger.log,
            )
        else:
            replace_files(
                file_pairs=self.current_file_pairs,
                create_backup=self.app.create_backup_var.get(),
                ask_confirm=True,
                confirm_message=t("message.confirm_replace_files", count=len(self.current_file_pairs), files="\n".join(f"  {t.name}" for _, t in self.current_file_pairs[:10])),
                log=self.logger.log,
            )

    # --- 批量更新UI和逻辑 ---
    def _create_batch_mode_widgets(self, parent):
        # 创建文件列表框，传入自定义显示格式：文件夹名 / 文件名
        self.batch_file_listbox = FileListbox(
            parent, t("ui.label.mod_file"),
            self.mod_file_list,
            t("ui.mod_update.placeholder_batch"),
            height=10,
            logger=self.logger,
            display_formatter=lambda p: f"{p.parent.name} / {p.name}"
        )
        self.batch_file_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 操作按钮区域
        action_button_frame = tb.Frame(parent)
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
