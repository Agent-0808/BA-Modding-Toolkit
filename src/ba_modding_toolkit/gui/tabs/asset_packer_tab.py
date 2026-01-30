# ui/tabs/asset_packer_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import Theme, UIComponents, SettingRow
from ..utils import handle_drop, replace_file, select_file, select_directory

class AssetPackerTab(TabFrame):
    def create_widgets(self):
        self.bundle_path: Path = None
        self.folder_path: Path = None
        self.final_output_path: Path = None
        
        # 资源文件夹
        _, self.folder_label = UIComponents.create_folder_drop_zone(
            self, t("ui.label.assets_folder_to_pack"), self.drop_folder, self.browse_folder,
            clear_cmd=self.clear_callback('folder_path'),
            label_text=t("ui.packer.placeholder_assets")
        )

        # 目标 Bundle 文件
        _, self.bundle_label = UIComponents.create_file_drop_zone(
            self, t("ui.label.target_bundle_file"), self.drop_bundle, self.browse_bundle,
            clear_cmd=self.clear_callback('bundle_path'),
            label_text=t("ui.packer.placeholder_bundle")
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

    def drop_bundle(self, event):
        handle_drop(event, callback=lambda path: self.set_file_path('bundle_path', self.bundle_label, path, t("ui.label.target_bundle_file")))
    
    def browse_bundle(self):
        select_file(
            title=t("ui.dialog.select", type=t("ui.label.target_bundle_file")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: self.set_file_path('bundle_path', self.bundle_label, path, t("ui.label.target_bundle_file")),
            log=self.logger.log
        )
    
    def drop_folder(self, event):
        def validate_folder(path: Path) -> bool:
            if not path.is_dir():
                messagebox.showwarning(t("message.invalid_operation"), t("message.packer.require_folder_with_assets"))
                return False
            return True
        
        handle_drop(event, callback=lambda path: self.set_folder_path('folder_path', self.folder_label, path, t("ui.label.assets_folder_to_pack")), error_message=t("message.drop_single_folder"), validation_callback=validate_folder)

    def browse_folder(self):
        folder_path = select_directory(
            var=None,
            title=t("ui.dialog.select", type=t("ui.label.assets_folder_to_pack")),
            log=self.logger.log
        )
        if folder_path:
            self.set_folder_path('folder_path', self.folder_label, Path(folder_path), t("ui.label.assets_folder_to_pack"))

    def run_replacement_thread(self):
        if not all([self.bundle_path, self.folder_path, self.app.output_dir_var.get()]):
            messagebox.showerror(t("common.error"), t("message.packer.missing_paths"))
            return
        self.run_in_thread(self.run_replacement)

    # 因为打包资源的操作在原理上是替换目标Bundle内的资源，因此这个函数先保留这个名字
    def run_replacement(self):
        self.final_output_path = None
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
        
        crc_setting = self.app.enable_crc_correction_var.get()
        perform_crc = False
        
        if crc_setting == "auto":
            platform, unity_version = core.get_unity_platform_info(self.bundle_path)
            self.logger.log(t("log.platform_info", platform=platform, version=unity_version))
            perform_crc = platform == "StandaloneWindows64"
        elif crc_setting == "true":
            perform_crc = True
        
        # 创建 SaveOptions 和 SpineOptions 对象
        save_options = core.SaveOptions(
            perform_crc=perform_crc,
            enable_padding=self.app.enable_padding_var.get(),
            compression=self.app.compression_method_var.get()
        )
        
        spine_options = core.SpineOptions(
            enabled=self.app.enable_spine_conversion_var.get(),
            converter_path=Path(self.app.spine_converter_path_var.get()),
            target_version=self.app.target_spine_version_var.get()
        )
        
        success, message = core.process_asset_packing(
            target_bundle_path = self.bundle_path,
            asset_folder = self.folder_path,
            output_dir = output_dir,
            save_options = save_options,
            spine_options = spine_options,
            enable_rename_fix = self.app.enable_spine38_namefix_var.get(),
            enable_bleed = self.app.enable_bleed_var.get(),
            log = self.logger.log
        )
        
        if success:
            generated_bundle_filename = self.bundle_path.name
            self.final_output_path = output_dir / generated_bundle_filename
            
            self.logger.log(f'✅ {t("log.packer.pack_success_path", path=self.final_output_path)}')
            self.logger.log(t("log.replace_original", button=t('action.replace_original')))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            messagebox.showerror(t("common.fail"), message)
        
        self.logger.status(t("log.status.done"))

    def replace_original_thread(self):
        """启动替换原始游戏文件的线程"""
        if not self.final_output_path or not self.final_output_path.exists():
            messagebox.showerror(t("common.error"), t("message.packer.generated_file_not_found_for_replace"))
            return
        if not self.bundle_path or not self.bundle_path.exists():
            messagebox.showerror(t("common.error"), t("message.file_not_found", path=self.bundle_path))
            return
        
        self.run_in_thread(self.replace_original)

    def replace_original(self):
        """执行实际的文件替换操作（在线程中）"""
        target_file = self.bundle_path
        source_file = self.final_output_path
        
        success = replace_file(
            source_path=source_file,
            dest_path=target_file,
            create_backup=self.app.create_backup_var.get(),
            ask_confirm=True,
            confirm_message=t("message.confirm_replace_file", path=self.bundle_path.name),
            log=self.logger.log,
        )