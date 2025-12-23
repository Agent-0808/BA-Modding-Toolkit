# ui/components.py

import tkinter as tk
from tkinterdnd2 import DND_FILES
from pathlib import Path
from typing import Callable

from i18n import t

# --- 日志管理类 ---
class Logger:
    def __init__(self, master, log_widget: tk.Text, status_widget: tk.Label):
        self.master = master
        self.log_widget = log_widget
        self.status_widget = status_widget

    def log(self, message: str) -> None:
        """线程安全地向日志区域添加消息"""
        def _update_log() -> None:
            self.log_widget.config(state=tk.NORMAL)
            self.log_widget.insert(tk.END, message + "\n")
            self.log_widget.see(tk.END)
            self.log_widget.config(state=tk.DISABLED)
        
        self.master.after(0, _update_log)

    def status(self, message: str) -> None:
        """线程安全地更新状态栏消息"""
        def _update_status() -> None:
            # 使用固定格式更新状态，避免布局变化
            status_text = f"{t('ui.status_label')}{message}"
            self.status_widget.config(text=status_text)
            # 确保状态栏保持固定高度
            self.status_widget.update_idletasks()
        
        self.master.after(0, _update_status)

    def clear(self) -> None:
        """清空日志区域"""
        def _clear_log() -> None:
            self.log_widget.config(state=tk.NORMAL)
            self.log_widget.delete('1.0', tk.END)
            self.log_widget.config(state=tk.DISABLED)
        
        self.master.after(0, _clear_log)

# --- 主题与颜色管理 ---

class Theme:
    """集中管理应用的所有颜色，确保UI风格统一。"""
    # 背景色
    WINDOW_BG = '#f0f2f5'
    FRAME_BG = '#ffffff'
    INPUT_BG = '#ecf0f1'
    MUTED_BG = '#e9ecef' # 用于拖放区等不活跃背景

    # 文本颜色
    TEXT_TITLE = '#080808'
    TEXT_NORMAL = '#34495e'
    TEXT_LIGHT = '#ffffff'
    
    # 按钮颜色 (背景/前景)
    BUTTON_PRIMARY_BG = '#3498db'
    BUTTON_SECONDARY_BG = '#9b59b6'
    BUTTON_ACCENT_BG = '#8e44ad'
    BUTTON_SUCCESS_BG = '#27ae60'
    BUTTON_WARNING_BG = '#f39c12'
    BUTTON_DANGER_BG = '#e74c3c'
    BUTTON_FG = TEXT_LIGHT

    # 状态颜色 (用于文本提示)
    COLOR_SUCCESS = '#27ae60'
    COLOR_WARNING = '#e67e22'
    COLOR_ERROR = '#e74c3c'

    # 特殊组件颜色
    LOG_BG = '#2c3e50'
    LOG_FG = '#ecf0f1'
    STATUS_BAR_BG = '#34495e'
    STATUS_BAR_FG = '#ecf0f1'

    # 字体
    FRAME_FONT = ("Microsoft YaHei", 11, "bold")
    INPUT_FONT = ("Microsoft YaHei", 9)
    BUTTON_FONT = ("Microsoft YaHei", 10, "bold")
    LOG_FONT = ("SimSun", 9)


# --- UI 组件工厂 ---

class UIComponents:
    """一个辅助类，用于创建通用的UI组件，以减少重复代码。"""

    @staticmethod
    def create_textbox_entry(parent, textvariable, width=None, placeholder_text=None, readonly=False):
        """创建统一的文本输入框组件"""
        entry = tk.Entry(
            parent, 
            textvariable=textvariable, 
            font=Theme.INPUT_FONT, 
            bg=Theme.INPUT_BG, 
            fg=Theme.TEXT_NORMAL, 
            relief=tk.SUNKEN, 
            bd=1,
            width=width
        )
        
        # 如果设置为只读，设置状态为readonly
        if readonly:
            entry.config(state='readonly')
        
        # 如果有占位符文本，添加占位符功能
        if placeholder_text:
            def on_focus_in(event):
                if entry.get() == placeholder_text:
                    entry.delete(0, tk.END)
                    entry.config(fg=Theme.TEXT_NORMAL)
            
            def on_focus_out(event):
                if not entry.get():
                    entry.insert(0, placeholder_text)
                    entry.config(fg=Theme.TEXT_NORMAL)
            
            # 初始显示占位符
            if not entry.get():
                entry.insert(0, placeholder_text)
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
        
        return entry

    @staticmethod
    def create_button(parent, text, command, bg_color=None, width=None, state=None, style=None, **kwargs):
        """
        创建统一的按钮组件
        
        Args:
            parent: 父组件
            text: 按钮文本
            command: 按钮命令
            bg_color: 按钮背景色，直接使用Theme下的颜色，如Theme.BUTTON_PRIMARY_BG
            width: 按钮宽度
            state: 按钮状态，可选值: "normal", "disabled", "active"
            style: 按钮样式预设，可选值: "compact"（紧凑型，用于浏览文件按钮）
            **kwargs: 其他tk.Button参数
            
        Returns:
            创建的按钮组件
        """
        # 设置默认参数
        button_kwargs = {
            "font": Theme.BUTTON_FONT,
            "bg": bg_color if bg_color is not None else Theme.BUTTON_PRIMARY_BG,
            "fg": Theme.BUTTON_FG,
            "relief": tk.FLAT,
            "padx": 10,
            "pady": 5
        }
        
        # 根据样式预设调整参数
        if style == "compact":
            # 紧凑型样式，用于浏览文件按钮和路径选择按钮
            button_kwargs["padx"] = 2
            button_kwargs["pady"] = 2
            button_kwargs["font"] = Theme.INPUT_FONT  # 使用较小的字体
        elif style == "short":
            button_kwargs["pady"] = 2
        
        # 添加可选参数
        if width is not None:
            button_kwargs["width"] = width
        if state is not None:
            button_kwargs["state"] = state
            
        # 合并用户提供的参数
        button_kwargs.update(kwargs)
        
        # 创建并返回按钮
        return tk.Button(parent, text=text, command=command, **button_kwargs)

    @staticmethod
    def create_checkbutton(parent, text, variable):
        """创建复选框组件"""
        return tk.Checkbutton(
            parent, 
            text=text, 
            variable=variable,
            font=Theme.INPUT_FONT, 
            bg=Theme.FRAME_BG, 
            fg=Theme.TEXT_NORMAL, 
            selectcolor=Theme.INPUT_BG,
            relief=tk.FLAT
        )

    @staticmethod
    def _debounce_wraplength(event: tk.Event) -> None:
        """
        防抖处理函数，用于更新标签的 wraplength。
        只在窗口大小调整停止后执行。
        """
        widget = event.widget
        # 如果之前已经设置了定时器，先取消它
        if hasattr(widget, "_debounce_timer"):
            widget.after_cancel(widget._debounce_timer)
        
        # 设置一个新的定时器，在指定时间后执行更新操作
        widget._debounce_timer = widget.after(500, lambda: widget.config(wraplength=widget.winfo_width() - 10))

    @staticmethod
    def create_drop_zone(parent, title, drop_cmd, browse_cmd, label_text, button_text, search_path_var=None, clear_cmd: Callable[[], None] | None = None):
        """
        创建通用的拖放区域组件
        
        Args:
            parent: 父组件
            title: 标题
            drop_cmd: 拖放回调
            browse_cmd: 浏览按钮回调
            label_text: 初始提示文本
            button_text: 浏览按钮文本
            search_path_var: (可选) 搜索路径变量
            clear_cmd: (可选) 清除按钮回调。点击清除按钮时，UI会自动恢复初始状态，并调用此函数清理外部变量。
        """
        frame = tk.LabelFrame(parent, text=title, font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=15, pady=12)
        frame.pack(fill=tk.X, pady=(0, 5))

        # 如果提供了 search_path_var，则在拖放区上方添加查找路径输入框
        if search_path_var is not None:
            search_frame = tk.Frame(frame, bg=Theme.FRAME_BG)
            search_frame.pack(fill=tk.X, pady=(0, 8))
            tk.Label(search_frame, text=t("ui.label.search_path"), bg=Theme.FRAME_BG, fg=Theme.TEXT_NORMAL).pack(side=tk.LEFT, padx=(0,5))
            UIComponents.create_textbox_entry(
                search_frame, 
                textvariable=search_path_var,
                placeholder_text=t("ui.label.game_resource_dir"),
                readonly=True
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 创建显示区域 Label
        label = tk.Label(frame, text=label_text, relief=tk.GROOVE, height=3, bg=Theme.MUTED_BG, fg=Theme.TEXT_NORMAL, font=Theme.INPUT_FONT, justify=tk.LEFT)
        label.pack(fill=tk.X, pady=(0, 8))
        label.drop_target_register(DND_FILES)
        label.dnd_bind('<<Drop>>', drop_cmd)
        label.bind('<Configure>', UIComponents._debounce_wraplength)

        # 按钮容器 (用于并排显示浏览和清除按钮)
        btn_frame = tk.Frame(frame, bg=Theme.FRAME_BG)
        btn_frame.pack(anchor=tk.CENTER)

        # 浏览按钮
        UIComponents.create_button(btn_frame, button_text, browse_cmd, bg_color=Theme.BUTTON_PRIMARY_BG, style="compact").pack(side=tk.LEFT, padx=(0, 5))

        # 清除逻辑
        def _handle_clear():
            # 1. 恢复 UI 至初始状态 (文本、背景、字体颜色)
            label.config(text=label_text, bg=Theme.MUTED_BG, fg=Theme.TEXT_NORMAL)
            # 2. 调用外部清理逻辑 (如果存在)
            if clear_cmd:
                clear_cmd()

        # 清除按钮
        UIComponents.create_button(btn_frame, t("action.clear"), _handle_clear, bg_color=Theme.BUTTON_WARNING_BG, style="compact").pack(side=tk.LEFT)

        return frame, label

    @staticmethod
    def create_file_drop_zone(parent, title, drop_cmd, browse_cmd, search_path_var=None, clear_cmd: Callable[[], None] | None = None):
        """创建文件拖放区域"""
        return UIComponents.create_drop_zone(
            parent, title, drop_cmd, browse_cmd, 
            t("ui.drop_zone.file_hint"), 
            t("action.browse_file"),
            search_path_var,
            clear_cmd=clear_cmd
        )

    @staticmethod
    def create_folder_drop_zone(parent, title, drop_cmd, browse_cmd, clear_cmd: Callable[[], None] | None = None):
        """创建文件夹拖放区域"""
        return UIComponents.create_drop_zone(
            parent, title, drop_cmd, browse_cmd,
            t("ui.drop_zone.folder_hint"),
            t("action.browse_folder"),
            search_path_var=None,
            clear_cmd=clear_cmd
        )

    @staticmethod
    def create_path_entry(parent, title, textvariable, select_cmd, open_cmd=None, placeholder_text=None, open_button=True):
        """
        创建路径输入框组件
        
        Args:
            parent: 父组件
            title: 标题
            textvariable: 文本变量
            select_cmd: 选择按钮命令
            open_cmd: 打开按钮命令（可选）
            placeholder_text: 占位符文本（可选）
            show_open_button: 是否显示"开"按钮，默认为True
            
        Returns:
            创建的框架组件
        """
        frame = tk.LabelFrame(parent, text=title, font=Theme.FRAME_FONT, fg=Theme.TEXT_TITLE, bg=Theme.FRAME_BG, padx=8, pady=8)
        frame.pack(fill=tk.X, pady=5)

        entry = UIComponents.create_textbox_entry(frame, textvariable, placeholder_text=placeholder_text)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=3)

        select_btn = UIComponents.create_button(frame, t("action.select_short"), select_cmd, bg_color=Theme.BUTTON_PRIMARY_BG, style="compact")
        select_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        if open_button and open_cmd is not None:
            open_btn = UIComponents.create_button(frame, t("action.open_short"), open_cmd, bg_color=Theme.BUTTON_SECONDARY_BG, style="compact")
            open_btn.pack(side=tk.LEFT)
            
        return frame

    # 保留原函数作为向后兼容的包装器
    @staticmethod
    def create_directory_path_entry(parent, title, textvariable, select_cmd, open_cmd, placeholder_text=None):
        """创建目录路径输入框组件（向后兼容）"""
        return UIComponents.create_path_entry(parent, title, textvariable, select_cmd, open_cmd, placeholder_text, open_button=True)

    @staticmethod
    def create_file_path_entry(parent, title, textvariable, select_cmd):
        """创建文件路径输入框组件（向后兼容）"""
        return UIComponents.create_path_entry(parent, title, textvariable, select_cmd, None, None, open_button=False)

    @staticmethod
    def create_combobox(parent, textvariable, values, state="readonly", width=None, font=None, **kwargs):
        """
        创建统一的下拉框组件
        
        Args:
            parent: 父组件
            textvariable: 文本变量
            values: 选项值列表
            state: 下拉框状态，默认为"readonly"
            width: 宽度
            font: 字体，默认为Theme.INPUT_FONT
            **kwargs: 其他ttk.Combobox参数
            
        Returns:
            创建的下拉框组件
        """
        import tkinter.ttk as ttk
        
        # 设置默认字体
        if font is None:
            font = Theme.INPUT_FONT
            
        combo_kwargs = {
            "textvariable": textvariable,
            "values": values,
            "state": state,
            "font": font
        }
        
        if width is not None:
            combo_kwargs["width"] = width
            
        # 合并其他参数
        combo_kwargs.update(kwargs)
        
        return ttk.Combobox(parent, **combo_kwargs)


class FileListbox:
    """可复用的文件列表框组件，支持拖放、多选、添加/删除文件等功能"""
    
    def __init__(self, parent, title:str, file_list:list[Path], placeholder_text:str, height=10, logger=None,
    display_formatter: Callable[[Path], str] | None = None, 
    on_files_added: Callable[[list[Path]], None] | None = None
    ):
        """
        初始化文件列表框组件
        
        Args:
            parent: 父组件
            title: 框架标题
            file_list: 存储文件路径的列表
            placeholder_text: 占位符文本
            height: 列表框高度
            logger: 日志记录器
            display_formatter: 可选的文件名显示格式化函数 (Path -> str)。如果不提供，默认显示文件名。
            on_files_added: 可选的文件添加回调函数，当文件被添加时调用
        """
        self.parent = parent
        self.file_list: list[Path] = file_list
        self.placeholder_text = placeholder_text
        self.height = height
        self.logger = logger
        self.display_formatter = display_formatter
        self.on_files_added = on_files_added
        
        self._create_widgets(title)
        
    def _create_widgets(self, title):
        """创建组件UI"""
        # 创建框架
        self.frame = tk.LabelFrame(
            self.parent, 
            text=title, 
            font=Theme.FRAME_FONT, 
            fg=Theme.TEXT_TITLE, 
            bg=Theme.FRAME_BG, 
            padx=15, 
            pady=12
        )
        self.frame.columnconfigure(0, weight=1)
        
        # 创建列表框区域
        list_frame = tk.Frame(self.frame, bg=Theme.FRAME_BG)
        list_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        self.frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        
        # 创建列表框
        self.listbox = tk.Listbox(
            list_frame, 
            font=Theme.INPUT_FONT, 
            bg=Theme.INPUT_BG, 
            fg=Theme.TEXT_NORMAL, 
            selectmode=tk.EXTENDED, 
            height=self.height
        )
        
        # 创建滚动条
        v_scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        h_scrollbar = tk.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.listbox.xview)
        self.listbox.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # 布局
        self.listbox.grid(row=0, column=0, sticky="nsew")
        v_scrollbar.grid(row=0, column=1, sticky="ns")
        h_scrollbar.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        
        # 注册拖放
        self.listbox.drop_target_register(DND_FILES)
        self.listbox.dnd_bind('<<Drop>>', self._handle_drop)
        
        # 添加占位符
        self._add_placeholder()
        
        # 创建按钮区域
        button_frame = tk.Frame(self.frame, bg=Theme.FRAME_BG)
        button_frame.grid(row=1, column=0, sticky="ew")
        button_frame.columnconfigure((0, 1, 2, 3), weight=1)
        
        # 创建按钮
        UIComponents.create_button(
            button_frame, 
            t("action.add_files"), 
            self._browse_add_files, 
            bg_color=Theme.BUTTON_PRIMARY_BG,
            style="compact"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        
        UIComponents.create_button(
            button_frame, 
            t("action.add_folder"), 
            self._browse_add_folder, 
            bg_color=Theme.BUTTON_PRIMARY_BG,
            style="compact"
        ).grid(row=0, column=1, sticky="ew", padx=5)
        
        UIComponents.create_button(
            button_frame, 
            t("action.remove_selected"), 
            self._remove_selected, 
            bg_color=Theme.BUTTON_WARNING_BG,
            style="compact"
        ).grid(row=0, column=2, sticky="ew", padx=5)
        
        UIComponents.create_button(
            button_frame, 
            t("action.clear_list"), 
            self._clear_list, 
            bg_color=Theme.BUTTON_DANGER_BG,
            style="compact"
        ).grid(row=0, column=3, sticky="ew", padx=(5, 0))
    
    def _add_placeholder(self):
        """添加占位符文本"""
        if not self.file_list and self.listbox.size() == 0:
            self.listbox.insert(tk.END, self.placeholder_text)
    
    def _remove_placeholder(self):
        """移除占位符文本"""
        if self.listbox.size() > 0:
            first_item = self.listbox.get(0)
            if first_item == self.placeholder_text:
                self.listbox.delete(0)
    
    def _get_file_index_by_listbox_index(self, listbox_index: int) -> int | None:
        """
        根据listbox中的索引获取在file_list中的对应索引
        """
        # 检查这个索引是否对应占位符
        if self.listbox.get(listbox_index) == self.placeholder_text:
            return None
        
        # 计算在file_list中的真实索引
        # 需要统计在listbox中前面有多少个真实文件（跳过占位符）
        real_file_count = 0
        for i in range(listbox_index):
            if self.listbox.get(i) != self.placeholder_text:
                real_file_count += 1
        
        return real_file_count if real_file_count < len(self.file_list) else None
    
    def add_files(self, paths: list[Path]):
        """
        添加文件到列表
        
        Args:
            paths: 文件路径列表
        """
        # 移除占位符
        self._remove_placeholder()
        
        added_count = 0
        added_paths = []  # 记录实际添加的文件路径
        for path in paths:
            if path not in self.file_list:
                self.file_list.append(path)
                added_paths.append(path)  # 记录新添加的文件
                
                # 格式化显示文本
                if self.display_formatter:
                    display_text = self.display_formatter(path)
                else:
                    display_text = path.name
                
                self.listbox.insert(tk.END, display_text)
                added_count += 1
        
        if added_count > 0:
            if self.logger:
                self.logger.log(t('log.file.added_count', count=added_count))
            
            # 调用回调函数
            if self.on_files_added:
                self.on_files_added(added_paths)
    
    def _handle_drop(self, event):
        """处理拖放事件"""

        raw_paths = event.data.strip('{}').split('} {')
        paths_to_add = []
        
        for p_str in raw_paths:
            path = Path(p_str)
            if path.is_dir():
                # 如果是目录，添加目录下的所有.bundle文件
                paths_to_add.extend(sorted(path.glob('*.bundle')))
            elif path.is_file() and path.suffix == '.bundle':
                # 如果是.bundle文件，直接添加
                paths_to_add.append(path)
        
        if paths_to_add:
            self.add_files(paths_to_add)
    
    def _browse_add_files(self):
        """浏览添加文件"""
        from ui.utils import select_file
        
        select_file(
            title=t("action.add_files"),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            multiple=True,
            callback=lambda paths: self.add_files(paths),
            logger=self.logger.log if self.logger else None
        )
    
    def _browse_add_folder(self):
        """浏览添加文件夹"""
        from ui.utils import select_directory
        
        folder = select_directory(
            title = t("action.add_folder"),
            logger = self.logger.log if self.logger else None
            )

        if folder:
            path = Path(folder)
            files = sorted(path.glob("*.bundle"))
            if files:
                self.add_files(files)
                if self.logger:
                    self.logger.log(t('log.file.added_count', count=len(files)))
            else:
                if self.logger:
                    self.logger.log(t('log.file.no_files_found_in_folder', type=".bundle"))
    
    def _remove_selected(self):
        """移除选中的文件"""
        selection = self.listbox.curselection()
        if not selection:
            return
        
        # 检查是否选中了占位符
        items_to_remove = []
        for index in selection:
            item_text = self.listbox.get(index)
            if item_text == self.placeholder_text:
                # 如果是占位符，只从listbox删除，不从file_list删除
                self.listbox.delete(index)
            else:
                # 如果是真实文件，需要同时从listbox和file_list删除
                # 计算在file_list中的对应索引（需要跳過占位符）
                file_index = self._get_file_index_by_listbox_index(index)
                if file_index is not None and file_index < len(self.file_list):
                    items_to_remove.append((index, file_index))
        
        # 从后往前删除真实文件，避免索引问题
        for listbox_index, file_index in sorted(items_to_remove, reverse=True):
            self.listbox.delete(listbox_index)
            if file_index < len(self.file_list):
                del self.file_list[file_index]
        
        # 如果列表为空，添加占位符
        if not self.file_list and self.listbox.size() == 0:
            self._add_placeholder()
        
        if self.logger:
            self.logger.log(t('log.file.removed_count', count=len(items_to_remove)))
    
    def _clear_list(self):
        """清空列表"""
        self.file_list.clear()
        self.listbox.delete(0, tk.END)
        self._add_placeholder()
        
        if self.logger:
            self.logger.log(t('log.file.list_cleared'))
    
    def get_frame(self):
        """获取组件框架，用于布局"""
        return self.frame
    
    def get_listbox(self):
        """获取列表框控件，用于直接操作"""
        return self.listbox