# ui/tabs/asset_packer_tab.py

import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from i18n import t

import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, replace_file, select_file, select_directory

class AssetPackerTab(TabFrame):
    def create_widgets(self):
        self.bundle_path: Path = None
        self.folder_path: Path = None
        self.final_output_path: Path = None
        
        # 资源文件夹
        _, self.folder_label = UIComponents.create_folder_drop_zone(
            self, t("ui.label.assets_folder_to_pack"), self.drop_folder, self.browse_folder,
            clear_cmd=self.clear_callback('folder_path')
        )

        # 目标 Bundle 文件
        _, self.bundle_label = UIComponents.create_file_drop_zone(
            self, t("ui.label.target_bundle_file"), self.drop_bundle, self.browse_bundle,
            clear_cmd=self.clear_callback('bundle_path')
        )
        
        # 操作按钮区域
        action_button_frame = tk.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        run_button = UIComponents.create_button(action_button_frame, t("action.pack"), self.run_replacement_thread, bg_color=Theme.BUTTON_SUCCESS_BG, padx=15, pady=8)
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=10)
        
        self.replace_button = UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread, bg_color=Theme.BUTTON_DANGER_BG, padx=15, pady=8, state="disabled")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=10)

    def drop_bundle(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("message.invalid_operation"), t("message.drop_single_file"))
            return
        self.set_file_path('bundle_path', self.bundle_label, Path(event.data.strip('{}')), t("ui.label.target_bundle_file"))
    
    def browse_bundle(self):
        select_file(
            title=t("ui.dialog.select", type=t("ui.label.target_bundle_file")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: self.set_file_path('bundle_path', self.bundle_label, path, t("ui.label.target_bundle_file")),
            logger=self.logger.log
        )
    
    def drop_folder(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("message.invalid_operation"), t("message.drop_single_folder"))
            return
        
        # 获取拖放的文件路径并转换为Path对象
        dropped_path = Path(event.data.strip('{}'))
        
        # 检查是否是文件夹
        if not dropped_path.is_dir():
            messagebox.showwarning(t("message.invalid_operation"), t("message.packer.require_folder_with_assets"))
            return
            
        self.set_folder_path('folder_path', self.folder_label, dropped_path, t("ui.label.assets_folder_to_pack"))

    def browse_folder(self):
        folder_path = select_directory(
            var=None,
            title=t("ui.dialog.select", type=t("ui.label.assets_folder_to_pack")),
            logger=self.logger.log
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
        
        # 创建 SaveOptions 和 SpineOptions 对象
        save_options = processing.SaveOptions(
            perform_crc=self.app.enable_crc_correction_var.get(),
            enable_padding=self.app.enable_padding_var.get(),
            compression=self.app.compression_method_var.get()
        )
        
        spine_options = processing.SpineOptions(
            enabled=self.app.enable_spine_conversion_var.get(),
            converter_path=Path(self.app.spine_converter_path_var.get()),
            target_version=self.app.target_spine_version_var.get()
        )
        
        success, message = processing.process_asset_packing(
            target_bundle_path = self.bundle_path,
            asset_folder = self.folder_path,
            output_dir = output_dir,
            save_options = save_options,
            spine_options = spine_options,
            log = self.logger.log
        )
        
        if success:
            generated_bundle_filename = self.bundle_path.name
            self.final_output_path = output_dir / generated_bundle_filename
            
            self.logger.log(t("log.packer.pack_success_path", path=self.final_output_path))
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