# ui/tabs/mod_update_tab.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinterdnd2 import DND_FILES
from pathlib import Path

from i18n import t
import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents
from ui.utils import is_multiple_drop, replace_file, select_file, select_directory
from utils import get_search_resource_dirs

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

        ttk.Radiobutton(mode_frame, text=t("ui.mod_update.mode_single"), variable=self.mode_var, value="single", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Radiobutton(mode_frame, text=t("ui.mod_update.mode_batch"), variable=self.mode_var, value="batch", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)

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
            parent, t("label.mod_file"), self.drop_old_mod, self.browse_old_mod
        )
        
        # 2. 新版游戏资源文件
        new_mod_frame, self.new_mod_label = UIComponents.create_file_drop_zone(
            parent, t("label.target_resource_bundle"), self.drop_new_mod, self.browse_new_mod,
            search_path_var=self.app.game_resource_dir_var
        )
        self.new_mod_label.config(text=t("ui.mod_update.placeholder_new"))

        # 操作按钮区域
        action_button_frame = tk.Frame(parent)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        self.run_button = UIComponents.create_button(action_button_frame, t("action.update"), self.run_update_thread, bg_color=Theme.BUTTON_SUCCESS_BG, padx=15, pady=8)
        self.run_button.grid(row=0, column=0, sticky="ew", padx=(0, 5), pady=2)
        
        self.replace_button = UIComponents.create_button(action_button_frame, t("action.replace_original"), self.replace_original_thread, bg_color=Theme.BUTTON_DANGER_BG, padx=15, pady=8, state="disabled")
        self.replace_button.grid(row=0, column=1, sticky="ew", padx=(5, 0), pady=2)

    def drop_old_mod(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("common.warning"), t("message.drop_single_file"))
            return
        path = Path(event.data.strip('{}'))
        self.set_file_path('old_mod_path', self.old_mod_label, path, t("label.mod_file"), callback=self.auto_find_new_bundle)

    def browse_old_mod(self):
        select_file(
            title=t("ui.dialog.select", type=t("label.mod_file")),
            filetypes=[(t("file.bundle"), "*.bundle"), (t("file.all_files"), "*.*")],
            callback=lambda path: self.set_file_path('old_mod_path', self.old_mod_label, path, t("label.mod_file"), callback=self.auto_find_new_bundle),
            logger=self.logger.log
        )

    def drop_new_mod(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("common.warning"), t("message.drop_single_file"))
            return
        path = Path(event.data.strip('{}'))
        self.set_new_mod_file(path)

    def browse_new_mod(self):
        select_file(
            title=t("ui.dialog.select", type=t("label.target_resource_bundle")),
            filetypes=[(t("file.bundle"), "*.bundle"), (t("file.all_files"), "*.*")],
            callback=self.set_new_mod_file,
            logger=self.logger.log
        )
            
    def set_new_mod_file(self, path: Path):
        self.new_mod_path = path
        self.new_mod_label.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(t("log.file.loaded", path=path))
        self.logger.status(t("log.status.ready"))

    def auto_find_new_bundle(self):
        if not all([self.old_mod_path, self.app.game_resource_dir_var.get()]):
            self.new_mod_label.config(text=t("ui.mod_update.warn_need_guide"), fg=Theme.COLOR_WARNING)
            messagebox.showwarning(t("common.tip"), t("message.missing_paths"))
            return
        self.run_in_thread(self._find_new_bundle_worker)
        
    def _find_new_bundle_worker(self):
        self.new_mod_label.config(text=t("ui.mod_update.status_searching"), fg=Theme.COLOR_WARNING)
        self.logger.status(t("log.status.processing_detailed"))
        
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        found_path, message = processing.find_new_bundle_path(
            self.old_mod_path,
            search_paths,
            self.logger.log
        )
        
        if found_path:
            self.master.after(0, self.set_new_mod_file, found_path)
        else:
            short_message = message.split('。')[0]
            ui_message = t("ui.mod_update.status_not_found", message=short_message)
            self.new_mod_label.config(text=ui_message, fg=Theme.COLOR_ERROR)
            self.logger.status(t("log.status.ready"))

    def run_update_thread(self):
        if not all([self.old_mod_path, self.new_mod_path, self.app.game_resource_dir_var.get(), self.app.output_dir_var.get()]):
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
        self.logger.log(t("message.updating"))
        self.logger.status(t("log.status.processing_detailed", filename=self.old_mod_path.name))
        
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
            messagebox.showerror(t("common.error"), message)
            return

        generated_bundle_filename = self.new_mod_path.name
        self.final_output_path = output_dir / generated_bundle_filename
        
        if self.final_output_path.exists():
            self.logger.log(t("log.file.saved", path=self.final_output_path))
            self.logger.log(t("message.replace_original", button=t("action.replace_original")))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.log(t("message.generated_file_not_found"))
            self.master.after(0, lambda: self.replace_button.config(state=tk.DISABLED))
            messagebox.showinfo(t("common.success"), t("message.process_success"))
        
        self.logger.status(t("log.status.done"))

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
        input_frame = tk.LabelFrame(parent, text=t("label.mod_file"), font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=12)
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
        self.file_listbox.insert(tk.END, t("ui.mod_update.placeholder_batch"))
        
        button_frame = tk.Frame(input_frame, bg=Theme.FRAME_BG)
        button_frame.grid(row=1, column=0, sticky="ew")
        button_frame.columnconfigure((0, 1, 2, 3), weight=1)

        tk.Button(button_frame, text=t("action.add_files"), command=self.browse_add_files, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_PRIMARY_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        tk.Button(button_frame, text=t("action.add_folder"), command=self.browse_add_folder, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_PRIMARY_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=1, sticky="ew", padx=5)
        tk.Button(button_frame, text=t("action.remove_selected"), command=self.remove_selected_files, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_WARNING_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=2, sticky="ew", padx=5)
        tk.Button(button_frame, text=t("action.clear_list"), command=self.clear_list, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_DANGER_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT).grid(row=0, column=3, sticky="ew", padx=(5, 0))

        run_button = tk.Button(parent, text=t("action.start"), command=self.run_batch_update_thread, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_SUCCESS_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT, padx=15, pady=8)
        run_button.pack(fill=tk.X, pady=5)

    def _add_files_to_list(self, file_paths: list[Path]):
        # 第一次添加文件时，清除提示文本
        if len(self.mod_file_list) == 0 and self.file_listbox.size() > 0:
            # 检查列表中是否包含提示文本
            if self.file_listbox.get(0) == t("ui.mod_update.placeholder_batch"):
                self.file_listbox.delete(0, tk.END)
        
        added_count = 0
        for path in file_paths:
            if path not in self.mod_file_list:
                self.mod_file_list.append(path)
                self.file_listbox.insert(tk.END, f"{path.parent.name} / {path.name}")
                added_count += 1
        if added_count > 0:
            self.logger.log(t("log.batch.added", count=added_count))
            self.logger.status(t("log.status.ready"))

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
        select_file(
            title=t("ui.dialog.add", type=t("file.bundle")),
            filetypes=[(t("file.bundle"), "*.bundle"), (t("file.all_files"), "*.*")],
            multiple=True,
            callback=self._add_files_to_list,
            logger=self.logger.log
        )

    def browse_add_folder(self):
        folder_path = select_directory(
            title=t("ui.dialog.add", type=t("file.folder")),
            logger=self.logger.log
        )
        if folder_path:
            path = Path(folder_path)
            bundle_files = sorted(path.glob('*.bundle'))
            if bundle_files:
                self._add_files_to_list(bundle_files)
            else:
                messagebox.showinfo(t("common.tip"), t("message.no_bundles_in_folder"))

    def remove_selected_files(self):
        selected_indices = self.file_listbox.curselection()
        if not selected_indices:
            messagebox.showinfo(t("common.tip"), t("message.file_not_selected"))
            return

        for index in sorted(selected_indices, reverse=True):
            self.file_listbox.delete(index)
            del self.mod_file_list[index]
        
        removed_count = len(selected_indices)
        self.logger.log(t("log.batch.removed", count=removed_count))
        self.logger.status(t("log.status.ready"))

    def clear_list(self):
        self.mod_file_list.clear()
        self.file_listbox.delete(0, tk.END)
        # 恢复提示文本
        self.file_listbox.insert(tk.END, t("ui.mod_update.placeholder_batch"))
        
        self.logger.log(t("log.batch.cleared"))
        self.logger.status(t("log.status.ready"))

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
        self.logger.status(t("log.status.batch_starting"))

        # 1. 准备参数
        output_dir = Path(self.app.output_dir_var.get())
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        search_paths = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())
        
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.process_failed", error=e))
            self.logger.status(t("log.status.error", error=e))
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
            self.logger.status(t("log.status.processing_batch", current=current, total=total, filename=filename))

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
        summary_message = t("message.batch_summary", total=total_files, success=success_count, fail=fail_count)
        
        self.logger.log("\n" + "#"*50)
        self.logger.log(summary_message)
        if failed_tasks:
            self.logger.log(t("log.batch.failed_items_cnt", count=fail_count))
            for task in failed_tasks:
                self.logger.log(f"- {task}")
        self.logger.log("\n" + "#"*50)
        
        self.logger.status(t("log.status.done"))
        messagebox.showinfo(t("common.result"), summary_message)
