# ui/tabs/asset_packer_tab.py

import tkinter as tk
from tkinter import messagebox, filedialog
from pathlib import Path

import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, replace_file

class AssetPackerTab(TabFrame):
    def create_widgets(self):
        self.bundle_path: Path = None
        self.folder_path: Path = None
        self.final_output_path: Path = None
        
        # 资源文件夹
        _, self.folder_label = UIComponents.create_folder_drop_zone(
            self, "待打包资源文件夹", self.drop_folder, self.browse_folder
        )

        # 目标 Bundle 文件
        _, self.bundle_label = UIComponents.create_file_drop_zone(
            self, "目标 Bundle 文件", self.drop_bundle, self.browse_bundle
        )
        
        # 4. 操作按钮区域
        action_button_frame = tk.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        run_button = UIComponents.create_button(action_button_frame, "开始打包", self.run_replacement_thread,
                                                 bg_color=Theme.BUTTON_SUCCESS_BG, padx=15, pady=8)
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=10)
        
        self.replace_button = UIComponents.create_button(action_button_frame, "覆盖原文件", self.replace_original_thread,
                                                        bg_color=Theme.BUTTON_DANGER_BG, padx=15, pady=8, state="disabled")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=10)

    def drop_bundle(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件。")
            return
        self.set_file_path('bundle_path', self.bundle_label, Path(event.data.strip('{}')), "目标 Bundle")
    def browse_bundle(self):
        p = filedialog.askopenfilename(title="选择目标 Bundle 文件")
        if p: self.set_file_path('bundle_path', self.bundle_label, Path(p), "目标 Bundle")
    
    def drop_folder(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件夹。")
            return
        
        # 获取拖放的文件路径并转换为Path对象
        dropped_path = Path(event.data.strip('{}'))
        
        # 检查是否是文件夹
        if not dropped_path.is_dir():
            messagebox.showwarning("操作无效", "请输入包含了要打包的资源文件的文件夹。")
            return
            
        self.set_folder_path('folder_path', self.folder_label, dropped_path, "待打包资源文件夹")
    def browse_folder(self):
        p = filedialog.askdirectory(title="选择待打包资源文件夹")
        if p: self.set_folder_path('folder_path', self.folder_label, Path(p), "待打包资源文件夹")

    def run_replacement_thread(self):
        if not all([self.bundle_path, self.folder_path, self.app.output_dir_var.get()]):
            messagebox.showerror("错误", "请确保已选择目标 Bundle、待打包资源文件夹，并在全局设置中指定了输出目录。")
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
            messagebox.showerror("错误", f"无法创建输出目录:\n{output_dir}\n\n错误详情: {e}")
            return

        self.logger.log("\n" + "="*50)
        self.logger.log("开始从资源文件夹打包...")
        self.logger.status("正在处理中，请稍候...")
        
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
            
            if self.final_output_path.exists():
                self.logger.log(f"✅ 打包成功。最终文件路径: {self.final_output_path}")
                self.logger.log(f"现在可以点击 '覆盖原文件' 按钮来应用更改。")
                self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
                messagebox.showinfo("成功", message)
            else:
                self.logger.log(f"⚠️ 警告: 打包成功，但无法找到生成的 Bundle 文件。请在 '{output_dir}' 目录中查找。")
                self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
                messagebox.showinfo("成功 (路径未知)", message + "\n\n⚠️ 警告：无法自动找到生成的文件，请在输出目录中手动查找。")
        else:
            messagebox.showerror("失败", message)
        
        self.logger.status("处理完成")

    def replace_original_thread(self):
        """启动替换原始游戏文件的线程"""
        if not self.final_output_path or not self.final_output_path.exists():
            messagebox.showerror("错误", "找不到已生成的替换文件。\n请先成功执行一次'生成替换文件'。")
            return
        if not self.bundle_path or not self.bundle_path.exists():
            messagebox.showerror("错误", "找不到原始目标文件路径。\n请确保在开始前已正确指定目标文件。")
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
            confirm_message=f"此操作将覆盖原始文件:\n\n{self.bundle_path.name}\n\n"
                            "如果要继续，请确保已备份原始文件，或是在全局设置中开启备份功能。\n\n确定要继续吗？",
            log=self.logger.log,
        )