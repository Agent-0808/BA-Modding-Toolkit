# ui/tabs/mod_update_tab.py

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinterdnd2 import DND_FILES
from pathlib import Path

from i18n import t
import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents, FileListbox
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
            parent, t("ui.label.mod_file"), self.drop_old_mod, self.browse_old_mod,
            clear_cmd=self.clear_callback('old_mod_path')
        )
        
        # 2. 新版游戏资源文件
        new_mod_frame, self.new_mod_label = UIComponents.create_file_drop_zone(
            parent, t("ui.label.target_resource_bundle"), self.drop_new_mod, self.browse_new_mod,
            search_path_var=self.app.game_resource_dir_var,
            clear_cmd=self.clear_callback('new_mod_path')
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
        self.set_file_path('old_mod_path', self.old_mod_label, path, t("ui.label.mod_file"), callback=self.auto_find_new_bundle)

    def browse_old_mod(self):
        select_file(
            title=t("ui.dialog.select", type=t("ui.label.mod_file")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            callback=lambda path: self.set_file_path('old_mod_path', self.old_mod_label, path, t("ui.label.mod_file"), callback=self.auto_find_new_bundle),
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
            title=t("ui.dialog.select", type=t("ui.label.target_resource_bundle")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
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
            self.logger.status(t("log.status.ready"))
        else:
            short_message = message.split('。')[0]
            ui_message = t("ui.mod_update.status_not_found", message=short_message)
            self.new_mod_label.config(text=ui_message, fg=Theme.COLOR_ERROR)
            self.logger.status(t("log.status.search_not_found"))

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
        self.logger.log(t("log.mod_update.updating"))
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
            self.logger.log(t("log.replace_original", button=t("action.replace_original")))
            self.master.after(0, lambda: self.replace_button.config(state=tk.NORMAL))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.log(t("log.generated_file_not_found"))
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
            # 创建文件列表框，传入自定义显示格式：文件夹名 / 文件名
            self.batch_file_listbox = FileListbox(
                parent,
                t("ui.label.mod_file"),
                self.mod_file_list,
                t("ui.mod_update.placeholder_batch"),
                height=10,
                logger=self.logger,
                display_formatter=lambda p: f"{p.parent.name} / {p.name}"
            )
            self.batch_file_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(0, 10))
            
            run_button = tk.Button(parent, text=t("action.start"), command=self.run_batch_update_thread, font=Theme.BUTTON_FONT, bg=Theme.BUTTON_SUCCESS_BG, fg=Theme.BUTTON_FG, relief=tk.FLAT, padx=15, pady=8)
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
        self.logger.log(t("log.mod_update.batch_start"))
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
        
        self.logger.log(t("log.mod_update.batch_summary", total=total_files, success=success_count, fail=fail_count))

        if failed_tasks:
            self.logger.log(t("log.mod_update.failed_items_cnt", count=fail_count))
            failed_list = "\n".join([t("log.mod_update.failed_item", filename=f) for f in failed_tasks])
            self.logger.log(failed_list)

        self.logger.status(t("log.status.done"))

    # 设置文件路径的通用方法
    def set_file_path(self, attr_name: str, label: tk.Label, path: Path, label_text: str, callback=None):
        """设置文件路径并更新标签显示"""
        setattr(self, attr_name, path)
        label.config(text=f"{label_text}: {path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(t("log.file.loaded", path=path))
        self.logger.status(t("log.status.ready"))
        if callback:
            callback()