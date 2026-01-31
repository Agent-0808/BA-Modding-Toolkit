# ui/tabs/asset_extractor_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
import os

from ...i18n import t
from ... import core
from ..base_tab import TabFrame
from ..components import Theme, UIComponents, SettingRow, FileListbox
from ..utils import handle_drop, select_file, select_directory, open_directory

class AssetExtractorTab(TabFrame):
    def create_widgets(self):
        self.bundle_paths: list[Path] = []
        
        # 子目录变量
        self.subdir_var: tk.StringVar = tk.StringVar()
        
        # 目标 Bundle 文件列表
        self.bundle_listbox = FileListbox(
            self,
            title=t("ui.label.bundles_to_extract"),
            file_list=self.bundle_paths,
            placeholder_text=t("ui.extractor.placeholder_bundle"),
            height=5,
            logger=self.logger
        )
        self.bundle_listbox.get_frame().pack(fill=tk.X, pady=(0, 5))
        
        # 输出目录
        self.output_frame = UIComponents.create_directory_path_entry(
            self, t("option.output_dir"), self.subdir_var,
            self.select_output_dir, self.open_output_dir,
            placeholder_text=t("ui.dialog.select", type=t("option.output_dir"))
        )

        # 资源类型选项
        options_frame = tb.Labelframe(self, text=t("ui.label.options"), padding=10)
        options_frame.pack(fill=tk.X, pady=(5,0))
        
        
        # Spine 降级选项
        SettingRow.create_switch(
            options_frame,
            label=t("option.spine_downgrade"),
            variable=self.app.enable_atlas_downgrade_var,
            tooltip=t("option.spine_downgrade_info")
        )
        
        # Spine 降级版本输入框
        SettingRow.create_entry_row(
            options_frame,
            label=t("option.spine_downgrade_target_version"),
            text_var=self.app.spine_downgrade_version_var,
            tooltip=t("option.spine_downgrade_target_version_info")
        )
        
        # Atlas 导出模式
        SettingRow.create_radiobutton_row(
            options_frame,
            label=t("option.atlas_export_mode"),
            text_var=self.app.atlas_export_mode_var,
            values=["atlas", "unpack", "both"],
            tooltip=t("option.atlas_export_mode_info")
        )

        # 操作按钮
        action_frame = tb.Frame(self)
        action_frame.pack(fill=tk.X, pady=10)
        action_frame.grid_columnconfigure(0, weight=1)

        run_button = UIComponents.create_button(action_frame, t("action.extract"), self.run_extraction_thread,
                                                 bootstyle="success", style="large")
        run_button.grid(row=0, column=0, sticky="ew", padx=(0, 0), pady=10)

    def select_output_dir(self):
        """选择输出子目录"""
        # 默认路径为输出目录
        default_dir = Path(self.app.output_dir_var.get())
        if not default_dir.exists():
            default_dir = Path.home()
            
        selected_dir = select_directory(
            var=None,
            title=t("ui.dialog.select", type=t("option.output_dir")),
            log=self.logger.log
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
            
        open_directory(output_path, create_if_not_exist=True)

    def run_extraction_thread(self):
        if not self.bundle_paths:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return
            
        # 检查 Spine 降级选项
        if self.app.enable_atlas_downgrade_var.get():
            spine_converter_path = self.app.spine_converter_path_var.get()
            
            if not spine_converter_path or not Path(spine_converter_path).exists():
                messagebox.showerror(t("common.error"), t("message.spine.missing_converter_tool"))
                return
            
        output_path = Path(self.app.output_dir_var.get())
        
        # 获取子目录名
        subdir_name = self.subdir_var.get().strip()
        if not subdir_name and len(self.bundle_paths) == 1:
            subdir_name = self.bundle_paths[0].stem
        
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
            messagebox.showwarning(t("common.tip"), t("message.missing_asset_type"))
            return
            
        # 传递 Spine 降级选项
        enable_atlas_downgrade = self.app.enable_atlas_downgrade_var.get()
        spine_converter_path = self.app.spine_converter_path_var.get()
        atlas_export_mode = self.app.atlas_export_mode_var.get()
            
        self.run_in_thread(self.run_extraction, self.bundle_paths, final_output_path, asset_types, enable_atlas_downgrade, spine_converter_path, atlas_export_mode)

    def run_extraction(self, bundle_paths: list[Path], output_dir: Path, asset_types: set[str], enable_atlas_downgrade=False, spine_converter_path=None, atlas_export_mode="atlas"):
        self.logger.status(t("log.status.extracting"))
        
        # 创建 SpineOptions 对象
        target_version = self.app.spine_downgrade_version_var.get().strip()
        
        spine_options = core.SpineOptions(
            enabled=enable_atlas_downgrade,
            converter_path=Path(spine_converter_path),
            target_version=target_version
        )
        
        success, message = core.process_asset_extraction(
            bundle_path=bundle_paths,
            output_dir=output_dir,
            asset_types_to_extract=asset_types,
            spine_options=spine_options,
            atlas_export_mode=atlas_export_mode,
            log=self.logger.log
        )
        
        if success:
            messagebox.showinfo(t("common.success"), message)
        else:
            messagebox.showerror(t("common.fail"), message)
            
        self.logger.status(t("log.status.done"))