# gui/tabs/mod_update_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from enum import IntEnum

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import DropZone, FileListbox, ModeSwitcher, UIComponents
from ..dialogs import FileSelectionDialog
from ..utils import replace_file
from ...utils import get_search_resource_dirs

class Mode(IntEnum):
    """Mod更新模式"""
    SINGLE = 0
    BATCH = 1


class ModUpdateTab(TabFrame):
    """一个整合了单个更新和批量更新功能的标签页"""
    def create_widgets(self):
        self.final_output_path: Path | None = None
        self.new_mod_path: Path | None = None
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
        # 1. 旧版 Mod 文件
        self.old_mod_zone = DropZone(
            parent, title=t("ui.label.mod_file"),
            placeholder_text=t("ui.mod_update.placeholder_old"),
            on_file_selected=self.on_old_mod_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            logger=self.logger
        )
        
        # 2. 新版游戏资源文件
        self.new_mod_zone = DropZone(
            parent, title=t("ui.label.target_resource_bundle"),
            placeholder_text=t("ui.mod_update.placeholder_new"),
            on_file_selected=self.on_new_mod_selected,
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

    def on_old_mod_selected(self, path: Path):
        """旧版 Mod 文件选中后的处理"""
        self.logger.log(t("log.file.loaded", path=path))
        self.new_mod_path = None
        self.new_mod_zone.clear()
        self.run_in_thread(self._find_new_bundle_worker)

    def on_new_mod_selected(self, path: Path):
        """新版资源文件选中后的处理"""
        self.new_mod_path = path
        self.new_mod_zone.set_success(path.name)
        self.logger.log(t("log.file.loaded", path=path))
        self.logger.status(t("status.ready"))

    def _find_new_bundle_worker(self):
        self.new_mod_zone.set_searching()
        self.logger.status(t("status.processing_detailed"))
        
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        found_paths, message = core.find_new_bundle_path(
            self.old_mod_zone.path,
            search_paths,
            self.logger.log
        )
        
        self.master.after(0, lambda: self._handle_search_result(found_paths, message))
    
    def _handle_search_result(self, found_paths: list[Path], message: str):
        """处理搜索结果"""
        if not found_paths:
            # 没有找到匹配文件
            ui_message = t("ui.mod_update.status_not_found", message=message)
            self.new_mod_zone.set_error(ui_message)
            self.logger.status(t("status.search_not_found"))
        elif len(found_paths) == 1:
            self.on_new_mod_selected(found_paths[0])
        else:
            # 多个匹配文件，弹出选择对话框
            dialog = FileSelectionDialog(
                self.master,
                title=t("ui.dialog.select_file"),
                candidates=found_paths,
                message=t("ui.dialog.multiple_matches_found", count=len(found_paths)),
                display_formatter=lambda p: f"{p.parent.name} / {p.name}"
            )
            
            selected_path = dialog.get_selected_path()
            if selected_path:
                self.on_new_mod_selected(selected_path)
            else:
                # 用户取消了选择
                ui_message = t("ui.mod_update.status_not_found", message=t("ui.dialog.selection_cancelled"))
                self.new_mod_zone.set_warning(ui_message)
                self.logger.status(t("status.search_not_found"))

    def run_update_thread(self):
        if not all([self.old_mod_zone.path, self.new_mod_path, self.app.game_resource_dir_var.get(), self.app.output_dir_var.get()]):
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return
        
        if not any([self.app.replace_texture2d_var.get(), self.app.replace_textasset_var.get(), self.app.replace_mesh_var.get(), self.app.replace_all_var.get()]):
            messagebox.showerror(t("common.error"), t("message.missing_asset_type"))
            return

        self.run_in_thread(self.run_update)

    def run_update(self):
        self.final_output_path = None
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))

        output_dir = Path(self.app.output_dir_var.get())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
            return

        self.logger.log("\n" + "="*50)
        self.logger.log(t("log.mod_update.updating"))
        self.logger.status(t("status.processing_detailed", filename=self.old_mod_zone.path.name))
        
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
            platform, unity_version = core.get_unity_platform_info(self.new_mod_path)
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
        
        success, message = core.process_mod_update(
            old_mod_path = self.old_mod_zone.path,
            new_bundle_path = self.new_mod_path,
            output_dir = output_dir,
            asset_types_to_replace = asset_types_to_replace,
            save_options = save_options,
            spine_options = spine_options,
            log = self.logger.log
        )
        
        if not success:
            messagebox.showerror(t("common.error"), message)
            return

        generated_bundle_filename = self.new_mod_path.name
        self.final_output_path = output_dir / generated_bundle_filename
        
        if self.final_output_path.exists():
            self.logger.log(t("log.file.saved", path=self.final_output_path))
            self.logger.log(t("log.replace_original", button=t("action.replace_original")))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.log(t("log.generated_file_not_found"))
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
            messagebox.showinfo(t("common.success"), t("message.process_success"))
        
        self.logger.status(t("status.done"))

    def replace_original_thread(self):
        if not self.final_output_path or not self.final_output_path.exists():
            messagebox.showerror(t("common.error"), t("message.file_not_found", path=self.final_output_path))
            return
        if not self.new_mod_path or not self.new_mod_path.exists():
            messagebox.showerror(t("common.error"), t("message.file_not_found", path=self.new_mod_path))
            return
        
        self.run_in_thread(self.replace_original)

    def replace_original(self):
        target_file = self.new_mod_path
        source_file = self.final_output_path
        
        replace_file(
            source_path=source_file,
            dest_path=target_file,
            create_backup=self.app.create_backup_var.get(),
            ask_confirm=True,
            confirm_message=t("message.confirm_replace_file", path=self.new_mod_path),
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
        
        run_button = UIComponents.create_button(parent, text=t("action.start"), 
            command=self.run_batch_update_thread, bootstyle="success", style="large")
        run_button.pack(fill=tk.X, pady=5)

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

        success_count, fail_count, failed_tasks = core.process_batch_mod_update(
            mod_file_list=self.mod_file_list,
            search_paths=search_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            log=self.logger.log,
            progress_callback=progress_callback
        )
        
        total_files = len(self.mod_file_list)
        
        self.logger.log(t("log.batch.summary", total=total_files, success=success_count, fail=fail_count))

        if failed_tasks:
            self.logger.log(t("log.batch.failed_items_cnt", count=fail_count))
            failed_list = "\n".join([t("log.batch.failed_item", filename=f) for f in failed_tasks])
            self.logger.log(failed_list)

        self.logger.status(t("status.done"))
        messagebox.showinfo(t("common.success"), t("message.batch.success", success=success_count, fail=fail_count))