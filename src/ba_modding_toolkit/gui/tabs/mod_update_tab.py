# gui/tabs/mod_update_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import GroupDropZone, UIComponents
from ..utils import replace_file, replace_files
from ...utils import get_search_resource_dirs


class ModUpdateTab(TabFrame):
    """Mod更新标签页，用于单个mod文件的更新"""

    def __init__(self, *args, **kwargs):
        self.source_paths: list[Path] = []
        self.target_paths: list[Path] = []
        self.current_file_pairs: list[tuple[Path, Path]] = []
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        # 1. 源文件组
        self.old_mod_zone = GroupDropZone(
            self, title=t("ui.label.mod_file"),
            placeholder_text=t("ui.mod_update.placeholder_old"),
            on_files_selected=self.on_old_mod_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            logger=self.logger
        )
        
        # 2. 目标资源文件组
        self.new_mod_zone = GroupDropZone(
            self, title=t("ui.label.target_resource_bundle"),
            placeholder_text=t("ui.mod_update.placeholder_new"),
            on_files_selected=self.on_new_mod_selected,
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            search_path_var=self.app.game_resource_dir_var,
            logger=self.logger
        )

        # 操作按钮区域
        action_button_frame = tb.Frame(self)
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
