# ui/tabs/asset_extractor_tab.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import os

import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, select_file, select_directory

class AssetExtractorTab(TabFrame):
    def create_widgets(self):
        self.bundle_path: Path | None = None
        
        # 子目录变量
        self.subdir_var: tk.StringVar = tk.StringVar()
        
        # 1. 目标 Bundle 文件
        _, self.bundle_label = UIComponents.create_file_drop_zone(
            self, "目标 Bundle 文件", self.drop_bundle, self.browse_bundle
        )
        
        # 2. 输出目录
        self.output_frame = UIComponents.create_directory_path_entry(
            self, "输出目录", self.subdir_var,
            self.select_output_dir, self.open_output_dir,
            placeholder_text="选择输出子目录"
        )

        # 3. 资源类型选项
        options_frame = tk.LabelFrame(self, text="提取选项", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=10, pady=10)
        options_frame.pack(fill=tk.X, pady=5)
        
        # Spine 降级选项
        spine_downgrade_frame = tk.Frame(options_frame, bg=Theme.FRAME_BG)
        spine_downgrade_frame.pack(fill=tk.X, pady=5)
        
        atlas_downgrade_check = UIComponents.create_checkbutton(
            spine_downgrade_frame, "启用 Spine 降级", self.app.enable_atlas_downgrade_var
        )
        atlas_downgrade_check.pack(side=tk.LEFT, padx=(0, 10))
        
        # Spine 降级版本输入框
        spine_version_label = tk.Label(spine_downgrade_frame, text="目标降级版本:", font=Theme.INPUT_FONT, bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL)
        spine_version_label.pack(side=tk.LEFT, padx=(0, 5))
        
        self.spine_downgrade_version_entry = UIComponents.create_textbox_entry(
            spine_downgrade_frame,
            textvariable=self.app.spine_downgrade_version_var,
            width=10
        )
        self.spine_downgrade_version_entry.pack(side=tk.LEFT)
        self.spine_downgrade_version_entry.pack(side=tk.LEFT)
        
        # 4. 操作按钮
        action_frame = tk.Frame(self)
        action_frame.pack(fill=tk.X, pady=10)
        action_frame.grid_columnconfigure(0, weight=1)

        run_button = UIComponents.create_button(action_frame, "开始提取", self.run_extraction_thread,
                                                 bg_color=Theme.BUTTON_SUCCESS_BG, padx=15, pady=8)
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 0), pady=10)

    def drop_bundle(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件。")
            return
        self.set_file_path('bundle_path', self.bundle_label, Path(event.data.strip('{}')), "目标 Bundle")

    def browse_bundle(self):
        select_file(
            title="选择目标 Bundle 文件",
            callback=lambda path: self.set_file_path('bundle_path', self.bundle_label, path, "目标 Bundle"),
            logger=self.logger.log
        )
    
    def select_output_dir(self):
        """选择输出子目录"""
        # 默认路径为输出目录
        default_dir = Path(self.app.output_dir_var.get())
        if not default_dir.exists():
            default_dir = Path.home()
            
        selected_dir = select_directory(
            var=None,
            title="选择输出子目录",
            logger=self.logger.log
        )
        
        if selected_dir:
            # 计算相对于输出目录的路径
            output_dir = Path(self.app.output_dir_var.get())
            selected_path = Path(selected_dir)
            
            try:
                # 尝试获取相对路径
                rel_path = selected_path.relative_to(output_dir)
                self.subdir_var.set(str(rel_path))
            except ValueError:
                # 如果不是子目录，则使用绝对路径
                self.subdir_var.set(selected_dir)
    
    def open_output_dir(self):
        """打开输出子目录"""
        # 获取子目录名
        subdir_name = self.subdir_var.get().strip()
        if not subdir_name and self.bundle_path:
            subdir_name = self.bundle_path.stem
        
        if subdir_name:
            # 如果是相对路径，则与输出目录组合
            if not Path(subdir_name).is_absolute():
                output_path = Path(self.app.output_dir_var.get()) / subdir_name
            else:
                output_path = Path(subdir_name)
        else:
            output_path = Path(self.app.output_dir_var.get())
            
        if output_path.exists():
            os.startfile(output_path)
        else:
            # 如果目录不存在，询问用户是否要创建
            result = messagebox.askyesno(
                "目录不存在",
                f"输出目录 '{output_path}' 不存在。\n是否要创建此目录？"
            )
            if result:
                try:
                    output_path.mkdir(parents=True, exist_ok=True)
                    os.startfile(output_path)
                except Exception as e:
                    messagebox.showerror("错误", f"创建目录失败: {e}")
            else:
                messagebox.showinfo("提示", "未创建目录。")

    def run_extraction_thread(self):
        if not self.bundle_path:
            messagebox.showerror("错误", "请选择一个目标 Bundle 文件。")
            return
            
        # 检查 Spine 降级选项
        if self.app.enable_atlas_downgrade_var.get():
            atlas_downgrade_path = self.app.atlas_downgrade_path_var.get()
            spine_converter_path = self.app.spine_converter_path_var.get()
            
            if not atlas_downgrade_path or not Path(atlas_downgrade_path).exists():
                messagebox.showerror("错误", "已启用 Spine 降级，但未指定有效的 SpineAtlasDowngrade.exe 路径。")
                return
                
            if not spine_converter_path or not Path(spine_converter_path).exists():
                messagebox.showerror("错误", "已启用 Spine 降级，但未指定有效的 SpineDataConverter.exe 路径。")
                return
            
        output_path = Path(self.app.output_dir_var.get())
        
        # 获取子目录名
        subdir_name = self.subdir_var.get().strip()
        if not subdir_name:
            subdir_name = self.bundle_path.stem
        
        # 如果是相对路径，则与输出目录组合
        if subdir_name and not Path(subdir_name).is_absolute():
            final_output_path = output_path / subdir_name
        elif subdir_name:
            final_output_path = Path(subdir_name)
        else:
            final_output_path = output_path
            
        asset_types = set()
        if self.app.replace_all_var.get():
            asset_types.add("ALL")
        else:
            if self.app.replace_texture2d_var.get(): asset_types.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types.add("Mesh")
        
        if not asset_types:
            messagebox.showwarning("提示", "请至少选择一种要提取的资源类型。\n您可以在设置对话框中配置这些选项。")
            return
            
        # 传递 Spine 降级选项
        enable_atlas_downgrade = self.app.enable_atlas_downgrade_var.get()
        atlas_downgrade_path = self.app.atlas_downgrade_path_var.get() if enable_atlas_downgrade else None
        spine_converter_path = self.app.spine_converter_path_var.get() if enable_atlas_downgrade else None
            
        self.run_in_thread(self.run_extraction, self.bundle_path, final_output_path, asset_types, enable_atlas_downgrade, atlas_downgrade_path, spine_converter_path)

    def run_extraction(self, bundle_path, output_dir, asset_types, enable_atlas_downgrade=False, atlas_downgrade_path=None, spine_converter_path=None):
        self.logger.status("正在提取资源...")
        
        # 创建 SpineDowngradeOptions 对象（如果启用）
        downgrade_options = None
        if enable_atlas_downgrade and atlas_downgrade_path and spine_converter_path:
            # 获取用户输入的版本，如果为空则使用默认值
            target_version = self.app.spine_downgrade_version_var.get().strip()
            if not target_version:
                target_version = "3.8.75"
            
            downgrade_options = processing.SpineDowngradeOptions(
                enabled=True,
                skel_converter_path=Path(spine_converter_path),
                atlas_converter_path=Path(atlas_downgrade_path),
                target_version=target_version
            )
        
        success, message = processing.process_asset_extraction(
            bundle_path=bundle_path,
            output_dir=output_dir,
            asset_types_to_extract=asset_types,
            downgrade_options=downgrade_options,
            log=self.logger.log
        )
        
        if success:
            messagebox.showinfo("成功", message)
        else:
            messagebox.showerror("失败", message)
            
        self.logger.status("提取完成")