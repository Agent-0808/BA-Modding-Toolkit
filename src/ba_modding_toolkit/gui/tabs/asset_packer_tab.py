# gui/tabs/asset_packer_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ...models import FileType
from ... import core
from ...searching import search_core, get_search_dirs
from ..base_tab import TabFrame
from ..components import DropZone, SettingRow, UIComponents, FileListbox
from ..utils import confirm_and_replace

class AssetPackerTab(TabFrame):
    def create_widgets(self):
        self.bundle_paths: list[Path] = []
        self.asset_paths: list[Path] = []
        self.current_file_pairs: list[tuple[Path, Path]] = []
        
        # 资源文件列表
        self.assets_listbox = FileListbox(
            self, title=t("ui.label.assets_to_pack"),
            file_list=self.asset_paths,
            placeholder_text=t("ui.packer.placeholder_assets"),
            height=5,
            allowed_suffixes={".png", ".skel", ".atlas", ".bytes"},
            logger=self.logger,
            on_files_added=self._on_assets_added
        )
        self.assets_listbox.get_frame().pack(fill=tk.X, pady=(0, 10))

        # 目标 Bundle 文件
        self.bundle_zone = DropZone(
            self, title=t("ui.label.target_bundle_file"),
            placeholder_text=t("ui.packer.placeholder_bundle"),
            on_files_selected=self.on_bundles_selected,
            file_types=[FileType.BUNDLE, FileType.ALL],
            logger=self.logger
        )
        
        # 旧版 Spine 文件名修正选项
        options_frame = tb.Labelframe(self, text=t("ui.label.options"), padding=10)
        options_frame.pack(fill=tk.X, pady=(5, 0))
        
        SettingRow.create_switch(
            options_frame,
            label=t("option.enable_spine38_name_fix"),
            variable=self.app.enable_spine38_namefix_var,
            tooltip=t("option.enable_spine38_name_fix_info")
        )
        
        SettingRow.create_switch(
            options_frame,
            label=t("option.enable_bleed"),
            variable=self.app.enable_bleed_var,
            tooltip=t("option.enable_bleed_info")
        )

        # 操作按钮区域
        action_button_frame = tb.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        run_button = UIComponents.create_button(action_button_frame, t("action.pack"), self.run_replacement_thread, bootstyle="success", style="large")
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=10)
        
        self.replace_button = UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread, bootstyle="danger", state="disabled", style="large")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=10)

    def on_bundles_selected(self, paths: list[Path]):
        """Bundle 文件选中后的处理"""
        self.bundle_paths = paths
        self.logger.log(t("log.file.selected_num", count=len(paths)))
        for p in paths:
            self.logger.log(f"  - {p.name}")
        self.logger.status(t("status.ready"))

    def _on_assets_added(self, added_paths: list[Path]):
        """资源文件添加回调：从空到有资源时自动搜索对应 bundle"""
        # 当添加后长度等于本次添加数量时，说明添加前列表为空
        if len(self.asset_paths) == len(added_paths):
            self.run_in_thread(self._auto_search_target_bundles)

    def _auto_search_target_bundles(self):
        """在后台线程中搜索匹配的 bundle，结果通过 after 回主线程填充"""
        self.master.after(0, lambda: self.bundle_zone.set_searching())
        self.logger.status(t("status.processing_detailed"))

        search_dirs = get_search_dirs(Path(self.app.game_resource_dir_var.get()))
        candidates, _ = search_core(self.asset_paths[0], search_dirs, self.logger.log)

        self.master.after(0, lambda: self._handle_search_result(candidates))

    def _handle_search_result(self, found_paths: list[Path]):
        """处理自动搜索结果"""
        if not found_paths:
            self.bundle_zone.set_error(t("message.search.no_matching_files_in_dir"))
            self.logger.status(t("status.search_not_found"))
        elif len(found_paths) == 1:
            self.bundle_paths = found_paths
            self.bundle_zone.set_files(found_paths)
            self.logger.log(t("log.file.loaded", path=found_paths[0]))
            self.logger.status(t("status.ready"))
        else:
            self.bundle_paths = found_paths
            self.bundle_zone.set_files(found_paths)
            self.logger.log(t("message.search.found_multiple_matches", count=len(found_paths)))
            self.logger.status(t("status.ready"))

    def run_replacement_thread(self):
        if not all([self.bundle_paths, self.asset_paths, self.app.output_dir_var.get()]):
            messagebox.showerror(t("common.error"), t("message.packer.missing_paths"))
            return
        self.run_in_thread(self.run_replacement)

    # 因为打包资源的操作在原理上是替换目标Bundle内的资源，因此这个函数先保留这个名字
    def run_replacement(self):
        self.current_file_pairs = []
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))

        output_dir = Path(self.app.output_dir_var.get())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.create_dir_failed_detail", path=output_dir, error=e))
            return

        self.logger.log("\n" + "="*50)
        self.logger.log(t("log.packer.start_packing"))
        self.logger.status(t("common.processing"))
        
        perform_crc = self.app.resolve_crc_setting(self.bundle_paths[0])
        
        # 创建 SaveOptions 和 SpineOptions 对象
        save_options = self.app.build_save_options(perform_crc)

        spine_options = self.app.build_spine_options()
        
        success, message, file_pairs = core.process_asset_packing(
            target_bundle_path = self.bundle_paths,
            assets = self.asset_paths,
            output_dir = output_dir,
            save_options = save_options,
            spine_options = spine_options,
            enable_rename_fix = self.app.enable_spine38_namefix_var.get(),
            enable_bleed = self.app.enable_bleed_var.get(),
            log = self.logger.log
        )
        
        self.current_file_pairs = file_pairs
        
        if success:
            self.logger.log(f'✅ {t("log.packer.pack_success_path", path=output_dir)}')
            self.logger.log(t("log.replace_original", button=t('action.replace_original')))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            messagebox.showerror(t("common.fail"), message)
        
        self.logger.status(t("status.done"))

    def replace_original_thread(self):
        confirm_and_replace(
            file_pairs=self.current_file_pairs,
            create_backup=self.app.create_backup_var.get(),
            log=self.logger.log,
            button_to_disable=self.replace_button,
            master=self.master,
        )