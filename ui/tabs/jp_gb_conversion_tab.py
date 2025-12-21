# ui/tabs/jp_gb_conversion_tab.py

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from i18n import t
import processing
from ui.base_tab import TabFrame
from ui.components import Theme, UIComponents, FileListbox
from ui.utils import is_multiple_drop, select_file
from utils import get_search_resource_dirs

class JpGbConversionTab(TabFrame):
    """日服与国际服格式互相转换的标签页"""

    def create_widgets(self):
        # 文件路径变量
        self.global_bundle_path: Path | None = None
        
        # --- 转换模式选择 ---
        mode_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        mode_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.mode_var = tk.StringVar(value="jp_to_global")
        
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

        ttk.Radiobutton(mode_frame, text=t("ui.jp_gb_convert.mode_jp_to_gb"), variable=self.mode_var,
                       value="jp_to_global", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Radiobutton(mode_frame, text=t("ui.jp_gb_convert.mode_gb_to_jp"), variable=self.mode_var,
                       value="global_to_jp", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- 文件输入区域 ---
        self.file_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        self.file_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 3))
        
        # 1. 国际服 Bundle 文件 (单文件拖放区)
        self.global_frame, self.global_label = UIComponents.create_file_drop_zone(
            self.file_frame, t("ui.jp_gb_convert.role_global_source"), 
            self.drop_global_bundle, self.browse_global_bundle,
            clear_cmd=self.clear_callback('global_bundle_path')
        )

        # 2. 日服 Bundle 文件列表 (FileListbox，支持多文件)
        self.jp_files_listbox = FileListbox(
            self.file_frame, 
            title=t("ui.jp_gb_convert.role_jp_source"), 
            file_list=[], 
            placeholder_text=t("ui.jp_gb_convert.placeholder_jp_files"),
            height=3,
            logger=self.logger
        )
        self.jp_files_listbox.get_frame().pack(fill=tk.BOTH, expand=True)
        
        # --- 选项设置区域 ---
        options_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        options_frame.pack(fill=tk.X)
        
        # 自动搜索开关
        UIComponents.create_checkbutton(
            options_frame,
            text=t("option.auto_search"),
            variable=self.app.auto_search_var
        ).pack(side=tk.LEFT, padx=5)
        
        # --- 操作按钮 ---
        action_button_frame = tk.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=2)
        
        self.run_button = UIComponents.create_button(
            action_button_frame, t("action.convert"),
            self.run_conversion_thread,
            bg_color=Theme.BUTTON_SUCCESS_BG,
            style="short"
        )
        self.run_button.pack(fill=tk.X)
        
        # 初始化视图标签
        self._switch_view()
    
    def _switch_view(self):
        """根据选择的模式更新UI文案"""
        if self.mode_var.get() == "jp_to_global":
            self.global_frame.config(text=t("ui.jp_gb_convert.role_global_target"))
            self.jp_files_listbox.get_frame().config(text=t("ui.jp_gb_convert.role_jp_source"))
        else:
            self.global_frame.config(text=t("ui.jp_gb_convert.role_global_source"))
            self.jp_files_listbox.get_frame().config(text=t("ui.jp_gb_convert.role_jp_target"))

    # --- 国际服文件处理 ---
    def drop_global_bundle(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning(t("message.invalid_operation"), t("message.drop_single_file"))
            return
        path = Path(event.data.strip('{}'))
        callback = lambda: self._auto_find_jp_files() if self.app.auto_search_var.get() else None
        self.set_file_path('global_bundle_path', self.global_label, path, t("ui.jp_gb_convert.global_bundle"), callback=callback)
    
    def browse_global_bundle(self):
        select_file(
            title=t("ui.dialog.select", type=t("ui.jp_gb_convert.global_bundle")),
            callback=lambda path: self.set_file_path(
                'global_bundle_path', self.global_label, path, t("ui.jp_gb_convert.global_bundle"), 
                callback=lambda: self._auto_find_jp_files() if self.app.auto_search_var.get() else None
            ),
            logger=self.logger.log
        )

    # --- 自动搜索逻辑 ---
    def _auto_find_jp_files(self):
        """当指定了 Global 文件后，自动在资源目录查找所有匹配的 JP 文件"""
        if not self.app.game_resource_dir_var.get():
            self.logger.log(t("log.jp_convert.auto_search_no_game_dir"))
            return
        if not self.global_bundle_path:
            return
            
        self.run_in_thread(self._find_worker)

    def _find_worker(self):
        self.logger.status(t("log.status.searching"))
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        game_search_dirs = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        jp_files = processing.find_all_jp_counterparts(
            self.global_bundle_path, game_search_dirs, self.logger.log
        )
        
        if jp_files:
            # 线程安全更新列表
            self.master.after(0, lambda: self._update_jp_listbox(jp_files))
            self.logger.status(t("log.status.ready"))
        else:
            self.logger.status(t("log.status.search_not_found"))

    def _update_jp_listbox(self, files: list[Path]):
        self.jp_files_listbox._clear_list()
        self.jp_files_listbox.add_files(files)
        self.logger.log(t("log.search.found_count", count=len(files)))

    # --- 核心转换流程 ---
    def run_conversion_thread(self):
        self.run_in_thread(self.run_conversion)
    
    def run_conversion(self):
        # 1. 验证输入
        output_dir = Path(self.app.output_dir_var.get())
        jp_files = self.jp_files_listbox.file_list
        
        if not self.global_bundle_path:
            messagebox.showerror(t("common.error"), t("message.no_file_selected"))
            return
        if not jp_files:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror(t("common.error"), t("message.create_output_dir_error", error=e))
            return
        
        # 2. 准备选项
        save_options = processing.SaveOptions(
            perform_crc=self.app.enable_crc_correction_var.get(),
            enable_padding=self.app.enable_padding_var.get(),
            compression=self.app.compression_method_var.get()
        )
        
        # 3. 调用处理函数
        self.logger.status(t("common.processing"))
        if self.mode_var.get() == "jp_to_global":
            success, message = processing.process_jp_to_global_conversion(
                global_bundle_path=self.global_bundle_path,
                jp_bundle_paths=jp_files,
                output_dir=output_dir,
                save_options=save_options,
                log=self.logger.log
            )
        else:
            success, message = processing.process_global_to_jp_conversion(
                global_bundle_path=self.global_bundle_path,
                jp_template_paths=jp_files,
                output_dir=output_dir,
                save_options=save_options,
                log=self.logger.log
            )
        
        # 4. 结果反馈
        if success:
            self.logger.status(t("log.status.done"))
            messagebox.showinfo(t("common.success"), message)
        else:
            self.logger.status(t("log.status.failed"))
            messagebox.showerror(t("common.fail"), message)