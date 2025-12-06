# ui/tabs/mod_update_tab.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinterdnd2 import DND_FILES
from pathlib import Path

import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, replace_file

class ModUpdateTab(TabFrame):
    """一个整合了单个更新和批量更新功能的标签页"""
    def create_widgets(self):
        # --- 共享变量 ---
        # 单个更新
        self.old_mod_path: Path | None = None
        self.new_mod_path: Path | None = None
        self.final_output_path: Path | None = None
        # 批量更新
        self.mod_file_list: list[Path] = []
        
        # --- 模式切换 ---
        mode_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.mode_var = tk.StringVar(value="single")
        
        style = ttk.Style()
        style.configure("Toolbutton",
                        background=Theme.MUTED_BG,
                        foreground=Theme.TEXT_NORMAL,
                        font=Theme.BUTTON_FONT,
                        padding=(10, 5),
                        borderwidth=1,
                        relief=tk.FLAT)
        style.map("Toolbutton",
                  background=[('selected', Theme.FRAME_BG), ('active', '#e0e0e0')],
                  relief=[('selected', tk.GROOVE)])

        ttk.Radiobutton(mode_frame, text="单个更新", variable=self.mode_var, value="single", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Radiobutton(mode_frame, text="批量更新", variable=self.mode_var, value="batch", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- 容器框架 ---
        self.single_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        self.batch_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        
        # 创建两种模式的UI
        self._create_single_mode_widgets(self.single_frame)
        self._create_batch_mode_widgets(self.batch_frame)
        
        # 初始化视图
        self._switch_view()

    def _switch_view(self):
        """根据选择的模式显示或隐藏对应的UI框架"""
        if self.mode_var.get() == "single":
            self.batch_frame.pack_forget()
            self.single_frame.pack(fill=tk.BOTH, expand=True)
        else:
            self.single_frame.pack_forget()
            self.batch_frame.pack(fill=tk.BOTH, expand=True)

    # --- 单个更新UI和逻辑 ---
    def _create_single_mode_widgets(self, parent):
        # 1. 旧版 Mod 文件
        _, self.old_mod_label = UIComponents.create_file_drop_zone(
            parent, "旧版 Mod Bundle", self.drop_old_mod, self.browse_old_mod
        )
        
        # 2. 新版游戏资源文件
        new_mod_frame, self.new_mod_label = UIComponents.create_file_drop_zone(
            parent, "目标 Bundle 文件", self.drop_new_mod, self.browse_new_mod,
            search_path_var=self.app.game_resource_dir_var
        )
        self.new_mod_label.config(text="拖入旧版Mod后将自动查找目标资源\n或手动拖放/浏览文件")

        # 操作按钮区域
        action_button_frame = tk.Frame(parent)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        self.run_button = UIComponents.create_button(action_button_frame, "开始更新", self.run_update_thread, bg_color=Theme.BUTTON_SUCCESS_BG, padx=15, pady=8)
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)
        
        self.replace_button = UIComponents.create_button(action_button_frame, "覆盖原文件", self.replace_original_thread, bg_color=Theme.BUTTON_DANGER_BG, padx=15, pady=8, state="disabled")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)

    def drop_old_mod(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件。")
            return
        path = Path(event.data.strip('{}'))
        self.set_file_path('old_mod_path', self.old_mod_label, path, "旧版 Mod", callback=self.auto_find_new_bundle)

    def browse_old_mod(self):
        p = filedialog.askopenfilename(title="选择旧版 Mod Bundle")
        if p:
            self.set_file_path('old_mod_path', self.old_mod_label, Path(p), "旧版 Mod", callback=self.auto_find_new_bundle)

    def drop_new_mod(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "请一次只拖放一个文件。")
            return
        path = Path(event.data.strip('{}'))
        self.set_new_mod_file(path)

    def browse_new_mod(self):
        p = filedialog.askopenfilename(title="选择目标资源 Bundle")
        if p:
            self.set_new_mod_file(Path(p))
            
    def set_new_mod_file(self, path: Path):
        self.new_mod_path = path
        self.new_mod_label.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(f"已加载目标资源: {path}")
        self.logger.status("已加载目标资源")

    def auto_find_new_bundle(self):
        if not all([self.old_mod_path, self.app.game_resource_dir_var.get()]):
            self.new_mod_label.config(text="⚠️ 请先选择旧版Mod并设置游戏资源目录", fg=Theme.COLOR_WARNING)
            messagebox.showwarning("提示", "请先选择旧版Mod文件，并设置游戏资源目录，才能进行自动查找。")
            return
        self.run_in_thread(self._find_new_bundle_worker)
        
    def _find_new_bundle_worker(self):
        self.new_mod_label.config(text="正在搜索新版资源...", fg=Theme.COLOR_WARNING)
        self.logger.status("正在搜索新版资源...")
        
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = self.get_game_search_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        found_path, message = processing.find_new_bundle_path(
            self.old_mod_path,
            search_paths,
            self.logger.log
        )
        
        if found_path:
            self.master.after(0, self.set_new_mod_file, found_path)
        else:
            short_message = message.split('。')[0]
            ui_message = f"❌ 未找到资源: {short_message}"
            self.new_mod_label.config(text=ui_message, fg=Theme.COLOR_ERROR)
            self.logger.status("未找到匹配的目标资源")

    def run_update_thread(self):
        if not all([self.old_mod_path, self.new_mod_path, self.app.game_resource_dir_var.get(), self.app.output_dir_var.get()]):
            messagebox.showerror("错误", "请确保已分别指定旧版Mod、目标资源 Bundle，并设置了游戏资源目录和输出目录。")
            return
        
        if not any([self.app.replace_texture2d_var.get(), self.app.replace_textasset_var.get(), self.app.replace_mesh_var.get(), self.app.replace_all_var.get()]):
            messagebox.showerror("错误", "请至少选择一种要替换的资源类型（如 Texture2D）。")
            return

        self.run_in_thread(self.run_update)

    def run_update(self):
        self.final_output_path = None
        self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))

        output_dir = Path(self.app.output_dir_var.get())
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出目录:\n{output_dir}\n\n错误详情: {e}")
            return

        self.logger.log("\n" + "="*50)
        self.logger.log("开始更新 Mod...")
        self.logger.status("正在处理中，请稍候...")
        
        asset_types_to_replace = set()
        if self.app.replace_all_var.get():
            asset_types_to_replace = {"ALL"}
        else:
            if self.app.replace_texture2d_var.get(): asset_types_to_replace.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types_to_replace.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types_to_replace.add("Mesh")
        
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
        
        success, message = processing.process_mod_update(
            old_mod_path = self.old_mod_path,
            new_bundle_path = self.new_mod_path,
            output_dir = output_dir,
            asset_types_to_replace = asset_types_to_replace,
            save_options = save_options,
            spine_options = spine_options,
            log = self.logger.log
        )
        
        if not success:
            messagebox.showerror("失败", message)
            return

        generated_bundle_filename = self.new_mod_path.name
        self.final_output_path = output_dir / generated_bundle_filename
        
        if self.final_output_path.exists():
            self.logger.log(f"✅ 更新成功。最终文件路径: {self.final_output_path}")
            self.logger.log(f"现在可以点击 '覆盖游戏原文件' 按钮来应用 Mod。")
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo("成功", message)
        else:
            self.logger.log(f"⚠️ 警告: 更新成功，但无法找到生成的 Mod 文件。请在 '{output_dir}' 目录中查找。")
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
            messagebox.showinfo("成功 (路径未知)", message + "\n\n⚠️ 警告：无法自动找到生成的 Mod 文件，请在输出目录中手动查找。")
        
        self.logger.status("处理完成")

    def replace_original_thread(self):
        if not self.final_output_path or not self.final_output_path.exists():
            messagebox.showerror("错误", "找不到已生成的 Mod 文件。\n请先成功执行一次'更新'。")
            return
        if not self.new_mod_path or not self.new_mod_path.exists():
            messagebox.showerror("错误", "找不到原始游戏资源文件路径。\n请确保在更新前已正确指定目标资源 Bundle。")
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
            confirm_message=f"此操作将覆盖资源目录中的原始文件:\n\n{self.new_mod_path}\n\n"
                            "如果要继续，请确保已备份原始文件，或是在全局设置中开启备份功能。\n\n确定要继续吗？",
            log=self.logger.log,
        )

    # --- 批量更新UI和逻辑 ---
    def _create_batch_mode_widgets(self, parent):
        input_frame = tk.LabelFrame(parent, text="输入 Mod 文件/文件夹", font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=12)
        input_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        input_frame.columnconfigure(0, weight=1)

        # 直接创建Listbox作为拖放区域
        list_frame = tk.Frame(input_frame, bg=Theme.FRAME_BG)
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        input_frame.rowconfigure(0, weight=1) # 让列表框区域可以伸缩
        list_frame.columnconfigure(0, weight=1)
        
        self.file_listbox = tk.Listbox(list_frame, font=Theme.INPUT_FONT, bg=Theme.INPUT_BG, fg=Theme.TEXT_NORMAL, selectmode=tk.EXTENDED, height=10)
        
        v_scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.file_listbox.yview)
        h_scrollbar = tk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.file_listbox.xview)
        self.file_listbox.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        self.file_listbox.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        
        # 将Listbox注册为拖放目标
        self.file_listbox.drop_target_register(DND_FILES)
        self.file_listbox.dnd_bind('<<Drop>>', self.drop_mods)
        
        # 添加提示文本
        self.file_listbox.insert(tk.END, "将文件或文件夹拖放到此处")
        self.file_listbox.insert(tk.END, "Drag & Drop bundle files or a folder to update")
        
        button_frame = tk.Frame(input_frame, bg=Theme.FRAME_BG)
        button_frame.grid(row=1, column=0, sticky="ew")
        button_frame.columnconfigure((0, 1, 2, 3), weight=1)

        tk.Button(button_frame, text="添加文件", command=self.browse_add_files, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_PRIMARY_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        tk.Button(button_frame, text="添加文件夹", command=self.browse_add_folder, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_PRIMARY_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=1, sticky="ew", padx=5)
        tk.Button(button_frame, text="移除选中", command=self.remove_selected_files, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_WARNING_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=2, sticky="ew", padx=5)
        tk.Button(button_frame, text="清空列表", command=self.clear_list, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_DANGER_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=3, sticky="ew", padx=(5, 0))

        run_button = tk.Button(parent, text="开始批量更新", command=self.run_batch_update_thread, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_SUCCESS_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT, padx=15, pady=8)
        run_button.pack(fill=tk.X, pady=5)

    def _add_files_to_list(self, file_paths: list[Path]):
        # 第一次添加文件时，清除提示文本
        if len(self.mod_file_list) == 0 and self.file_listbox.size() > 0:
            # 检查列表中是否包含提示文本
            if self.file_listbox.get(0) == "将文件或文件夹拖放到此处":
                self.file_listbox.delete(0, tk.END)
        
        added_count = 0
        for path in file_paths:
            if path not in self.mod_file_list:
                self.mod_file_list.append(path)
                self.file_listbox.insert(tk.END, f"{path.parent.name} / {path.name}")
                added_count += 1
        if added_count > 0:
            self.logger.log(f"已向处理列表添加 {added_count} 个文件。")
            self.logger.status(f"当前列表有 {len(self.mod_file_list)} 个文件待处理。")

    def drop_mods(self, event):
        raw_paths = event.data.strip('{}').split('} {')
        
        paths_to_add = []
        for p_str in raw_paths:
            path = Path(p_str)
            if path.is_dir():
                paths_to_add.extend(sorted(path.glob('*.bundle')))
            elif path.is_file():
                paths_to_add.append(path)
        
        if paths_to_add:
            self._add_files_to_list(paths_to_add)

    def browse_add_files(self):
        filepaths = filedialog.askopenfilenames(title="选择一个或多个 Mod Bundle 文件")
        if filepaths:
            self._add_files_to_list([Path(p) for p in filepaths])

    def browse_add_folder(self):
        folder_path = filedialog.askdirectory(title="选择包含 Mod Bundle 文件的文件夹")
        if folder_path:
            path = Path(folder_path)
            bundle_files = sorted(path.glob('*.bundle'))
            if bundle_files:
                self._add_files_to_list(bundle_files)
            else:
                messagebox.showinfo("提示", "在该文件夹中没有找到任何 .bundle 文件。")

    def remove_selected_files(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showinfo("提示", "没有选中任何文件。")
            return

        for index in sorted(selected_indices, reverse=True):
            self.file_listbox.delete(index)
            del self.mod_file_list[index]
        
        removed_count = len(selected_indices)
        self.logger.log(f"已从处理列表移除 {removed_count} 个文件。")
        self.logger.status(f"当前列表有 {len(self.mod_file_list)} 个文件待处理。")

    def clear_list(self):
        self.mod_file_list.clear()
        self.file_listbox.delete(0, tk.END)
        # 恢复提示文本
        self.file_listbox.insert(tk.END, "将文件或文件夹拖放到此处")
        self.file_listbox.insert(tk.END, "Drag & Drop bundle files or a folder to update")
        
        self.logger.log("已清空处理列表。")
        self.logger.status("准备就绪")

    def run_batch_update_thread(self):
        if not self.mod_file_list:
            messagebox.showerror("错误", "处理列表为空，请先添加 Mod 文件。")
            return
        if not all([self.app.game_resource_dir_var.get(), self.app.output_dir_var.get()]):
            messagebox.showerror("错误", "请确保在全局设置中已指定游戏资源目录和输出目录。")
            return
        if not any([self.app.replace_texture2d_var.get(), self.app.replace_textasset_var.get(), self.app.replace_mesh_var.get(), self.app.replace_all_var.get()]):
            messagebox.showerror("错误", "请至少选择一种要替换的资源类型（如 Texture2D）。")
            return
        
        self.run_in_thread(self._batch_update_worker)

    def _batch_update_worker(self):
        self.logger.log("\n" + "#"*50)
        self.logger.log("🚀 开始批量更新 Mod...")
        self.logger.status("正在批量处理中...")

        # 1. 准备参数
        output_dir = Path(self.app.output_dir_var.get())
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = self.get_game_search_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出目录:\n{output_dir}\n\n错误详情: {e}")
            self.logger.status("处理失败")
            return

        asset_types_to_replace = set()
        if self.app.replace_all_var.get():
            asset_types_to_replace = {"ALL"}
        else:
            if self.app.replace_texture2d_var.get(): asset_types_to_replace.add("Texture2D")
            if self.app.replace_textasset_var.get(): asset_types_to_replace.add("TextAsset")
            if self.app.replace_mesh_var.get(): asset_types_to_replace.add("Mesh")

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

        # 更新UI状态的回调函数
        def progress_callback(current, total, filename):
            self.logger.status(f"正在处理 ({current}/{total}): {filename}")

        # 2. 调用核心处理函数
        success_count, fail_count, failed_tasks = processing.process_batch_mod_update(
            mod_file_list=self.mod_file_list,
            search_paths=search_paths,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            log=self.logger.log,
            progress_callback=progress_callback
        )
        
        # 3. 处理结果并更新UI
        total_files = len(self.mod_file_list)
        summary_message = f"批量处理完成！\n\n总计: {total_files} 个文件\n成功: {success_count} 个\n失败: {fail_count} 个"
        
        self.logger.log("\n" + "#"*50)
        self.logger.log(summary_message)
        if failed_tasks:
            self.logger.log(f"\n\n失败的更新任务:")
            for task in failed_tasks:
                self.logger.log(f"- {task}")
        self.logger.log("\n" + "#"*50)
        
        self.logger.status("批量处理完成")
        messagebox.showinfo("批量处理完成", summary_message)