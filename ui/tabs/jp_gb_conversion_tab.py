# ui/tabs/jp_gb_conversion_tab.py

import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

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

        ttk.Radiobutton(mode_frame, text="JP -> Global (合并多文件)", variable=self.mode_var,
                       value="jp_to_global", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Radiobutton(mode_frame, text="Global -> JP (拆分到模板)", variable=self.mode_var,
                       value="global_to_jp", command=self._switch_view, style="Toolbutton").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # --- 文件输入区域 ---
        self.file_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        self.file_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # 1. 国际服 Bundle 文件 (单文件拖放区)
        self.global_frame, self.global_label = UIComponents.create_file_drop_zone(
            self.file_frame, "Global Bundle 文件", 
            self.drop_global_bundle, self.browse_global_bundle
        )

        # 2. 日服 Bundle 文件列表 (FileListbox，支持多文件)
        self.jp_files_listbox = FileListbox(
            self.file_frame, 
            title="JP Bundle 文件列表", 
            file_list=[], 
            placeholder_text="拖放所有相关的日服文件 (textures, assets, materials, timelines...) 到此处",
            height=3,
            logger=self.logger
        )
        self.jp_files_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # --- 选项设置区域 ---
        options_frame = tk.Frame(self, bg=Theme.WINDOW_BG)
        options_frame.pack(fill=tk.X)
        
        # 自动搜索开关
        UIComponents.create_checkbutton(
            options_frame,
            text="添加 Global 文件时自动搜索所有 JP 关联文件",
            variable=self.app.auto_search_var
        ).pack(side=tk.LEFT, padx=5)
        
        # --- 操作按钮 ---
        action_button_frame = tk.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=2)
        
        self.run_button = UIComponents.create_button(
            action_button_frame, "开始转换",
            self.run_conversion_thread,
            bg_color=Theme.BUTTON_SUCCESS_BG,
            padx=15, pady=3
        )
        self.run_button.pack(fill=tk.X)
        
        # 初始化视图标签
        self._switch_view()
    
    def _switch_view(self):
        """根据选择的模式更新UI文案"""
        if self.mode_var.get() == "jp_to_global":
            self.global_frame.config(text="Global Bundle (模板)")
            self.jp_files_listbox.get_frame().config(text="JP Bundles (源文件)")
        else:
            self.global_frame.config(text="Global Bundle (源文件)")
            self.jp_files_listbox.get_frame().config(text="JP Bundles (模板)")

    # --- 国际服文件处理 ---
    def drop_global_bundle(self, event):
        if is_multiple_drop(event.data):
            messagebox.showwarning("操作无效", "此处请一次只拖放一个 Global 文件。")
            return
        path = Path(event.data.strip('{}'))
        callback = lambda: self._auto_find_jp_files() if self.app.auto_search_var.get() else None
        self.set_file_path('global_bundle_path', self.global_label, path, "Global Bundle", callback=callback)
    
    def browse_global_bundle(self):
        select_file(
            title="选择 Global Bundle 文件",
            callback=lambda path: self.set_file_path(
                'global_bundle_path', self.global_label, path, "Global Bundle", 
                callback=lambda: self._auto_find_jp_files() if self.app.auto_search_var.get() else None
            ),
            logger=self.logger.log
        )

    # --- 自动搜索逻辑 ---
    def _auto_find_jp_files(self):
        """当指定了 Global 文件后，自动在资源目录查找所有匹配的 JP 文件"""
        if not self.app.game_resource_dir_var.get():
            self.logger.log("⚠️ 自动查找失败：未设置游戏资源目录。")
            return
        if not self.global_bundle_path:
            return
            
        self.run_in_thread(self._find_worker)

    def _find_worker(self):
        self.logger.status("正在自动查找所有日服关联文件...")
        base_game_dir = Path(self.app.game_resource_dir_var.get())
        game_search_dirs = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        jp_files = processing.find_all_jp_counterparts(
            self.global_bundle_path, game_search_dirs, self.logger.log
        )
        
        if jp_files:
            # 线程安全更新列表
            self.master.after(0, lambda: self._update_jp_listbox(jp_files))
        else:
            self.logger.log("  > ❌ 未能找到该 Global 文件的日服对应版本。")
        self.logger.status("自动查找完成")

    def _update_jp_listbox(self, files: list[Path]):
        self.jp_files_listbox._clear_list()
        self.jp_files_listbox.add_files(files)
        self.logger.log(f"  > 已自动匹配到 {len(files)} 个日服文件。")

    # --- 核心转换流程 ---
    def run_conversion_thread(self):
        self.run_in_thread(self.run_conversion)
    
    def run_conversion(self):
        # 1. 验证输入
        output_dir = Path(self.app.output_dir_var.get())
        jp_files = self.jp_files_listbox.file_list
        
        if not self.global_bundle_path:
            messagebox.showerror("错误", "请选择 Global Bundle 文件。")
            return
        if not jp_files:
            messagebox.showerror("错误", "日服文件列表不能为空。")
            return

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            messagebox.showerror("错误", f"无法创建输出目录: {e}")
            return
        
        # 2. 准备选项
        save_options = processing.SaveOptions(
            perform_crc=self.app.enable_crc_correction_var.get(),
            enable_padding=self.app.enable_padding_var.get(),
            compression=self.app.compression_method_var.get()
        )
        
        # 3. 调用处理函数
        self.logger.status("正在转换中...")
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
            self.logger.status("转换成功")
            messagebox.showinfo("成功", message)
        else:
            self.logger.status("转换失败")
            messagebox.showerror("失败", message)