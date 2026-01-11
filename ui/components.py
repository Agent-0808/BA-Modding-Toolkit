# ui/components.py

import tkinter as tk
import ttkbootstrap as tb
from tkinterdnd2 import DND_FILES
from pathlib import Path
from typing import Callable, Any

from i18n import t

# --- 日志管理类 ---
class Logger:
    def __init__(self, master, log_widget: tb.Text, status_widget: tb.Label):
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
    MODE_SWITCHER_ACTIVE = '#e0e0e0'
    
    # 侧边栏颜色
    SIDEBAR_BG = '#2c3e50'
    SIDEBAR_BUTTON_BG = '#34495e'
    SIDEBAR_BUTTON_FG = '#ecf0f1'
    SIDEBAR_BUTTON_ACTIVE_BG = '#3498db'
    SIDEBAR_BUTTON_ACTIVE_FG = '#ffffff'

    # 字体
    FRAME_FONT = ("Microsoft YaHei", 11, "bold")
    DROP_ZONE_FONT = ("Microsoft YaHei", 9)
    INPUT_FONT = ("Microsoft YaHei", 9)
    STATUS_BAR_FONT = ("Microsoft YaHei", 9)
    BUTTON_FONT = ("Microsoft YaHei", 10, "bold")
    SIDEBAR_FONT = ("Microsoft YaHei", 9, "bold")
    LOG_FONT = ("SimSun", 9)
    TOOLTIP_FONT = ("Microsoft YaHei", 9)

    # Tooltip 颜色
    TOOLTIP_BG = '#ffffe0'


# --- UI 组件工厂 ---

class UIComponents:
    """一个辅助类，用于创建通用的UI组件，以减少重复代码。"""

    @staticmethod
    def create_textbox_entry(parent, textvariable, width=None, placeholder_text=None, readonly=False):
        """创建统一的文本输入框组件"""
        entry = tb.Entry(
            parent,
            textvariable=textvariable,
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
            
            def on_focus_out(event):
                if not entry.get():
                    entry.insert(0, placeholder_text)
            
            # 初始显示占位符
            if not entry.get():
                entry.insert(0, placeholder_text)
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
        
        return entry

    @staticmethod
    def create_button(parent, text, command, bootstyle="primary", width=None, state=None, padding=None, style=None, **kwargs):
        """
        创建统一的按钮组件

        Args:
            parent: 父组件
            text: 按钮文本
            command: 按钮命令
            bootstyle: ttkbootstrap 样式，可选值: "primary", "success", "warning", "danger", "info", "light-outline" 等
            width: 按钮宽度
            state: 按钮状态，可选值: "normal", "disabled"
            padding: 内边距，默认 (10, 5)
            style: 按钮样式预设，可选值: "compact"（紧凑型，使用较少边距）
            **kwargs: 其他 tb.Button 参数

        Returns:
            创建的按钮组件
        """
        button_kwargs = {
            "command": command,
            "width": width,
            "state": state,
            "bootstyle": bootstyle,
        }

        if style == "compact":
            button_kwargs["padding"] = (2, 2)
        else:
            button_kwargs["padding"] = padding if padding is not None else (10, 5)

        button_kwargs.update(kwargs)

        return tb.Button(parent, text=text, **button_kwargs)

    @staticmethod
    def create_checkbutton(parent, text, variable, command=None):
        """创建复选框组件
        
        Args:
            parent: 父组件
            text: 复选框文本（form_row=True时忽略）
            variable: 变量
            command: 命令回调
            form_row: 是否作为表单行使用（True时不显示文本，文本由外部Label显示）
        """
        checkbutton = tb.Checkbutton(
            parent, 
            text=text, 
            variable=variable,
            command=command,
        )
        return checkbutton

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
        frame = tb.Labelframe(parent, text=title, padding=(15, 12))
        frame.pack(fill=tk.X, pady=(0, 5))

        # 如果提供了 search_path_var，则在拖放区上方添加查找路径输入框
        if search_path_var is not None:
            search_frame = tb.Frame(frame)
            search_frame.pack(fill=tk.X, pady=(0, 8))
            tb.Label(search_frame, text=t("ui.label.search_path")).pack(side=tk.LEFT, padx=(0,5))
            UIComponents.create_textbox_entry(
                search_frame, 
                textvariable=search_path_var,
                placeholder_text=t("ui.label.game_resource_dir"),
                readonly=True
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        # 创建显示区域 Label
        drop_zone = tb.Label(frame, text=label_text, relief="sunken", anchor="center", justify="center", padding=10, font=Theme.DROP_ZONE_FONT, bootstyle="inverse-light")
        drop_zone.pack(fill=tk.X, pady=(0, 8))
        drop_zone.drop_target_register(DND_FILES)
        drop_zone.dnd_bind('<<Drop>>', drop_cmd)
        drop_zone.bind('<Configure>', UIComponents._debounce_wraplength)

        # 按钮容器 (用于并排显示浏览和清除按钮)
        btn_frame = tb.Frame(frame)
        btn_frame.pack(anchor=tk.CENTER)

        # 浏览按钮
        UIComponents.create_button(btn_frame, button_text, browse_cmd, bootstyle="primary", style="compact").pack(side=tk.LEFT, padx=(0, 5))

        # 清除逻辑
        def _handle_clear():
            # 1. 恢复 UI 至初始状态 (文本、背景、字体颜色)
            drop_zone.config(text=label_text)
            # 2. 调用外部清理逻辑 (如果存在)
            if clear_cmd:
                clear_cmd()

        # 清除按钮
        UIComponents.create_button(btn_frame, t("action.clear"), _handle_clear, bootstyle="warning", style="compact").pack(side=tk.LEFT)

        return frame, drop_zone

    @staticmethod
    def create_file_drop_zone(parent, title, drop_cmd, browse_cmd, search_path_var=None, clear_cmd: Callable[[], None] | None = None, label_text: str | None = None):
        """创建文件拖放区域"""
        return UIComponents.create_drop_zone(
            parent, title, drop_cmd, browse_cmd, 
            label_text if label_text is not None else t("ui.drop_zone.file_hint"), 
            t("action.browse_file"),
            search_path_var,
            clear_cmd=clear_cmd
        )

    @staticmethod
    def create_folder_drop_zone(parent, title, drop_cmd, browse_cmd, clear_cmd: Callable[[], None] | None = None, label_text: str | None = None):
        """创建文件夹拖放区域"""
        return UIComponents.create_drop_zone(
            parent, title, drop_cmd, browse_cmd,
            label_text if label_text is not None else t("ui.drop_zone.folder_hint"),
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
            title: 标题（可选，用于向后兼容）
            textvariable: 文本变量
            select_cmd: 选择按钮命令
            open_cmd: 打开按钮命令（可选）
            placeholder_text: 占位符文本（可选）
            open_button: 是否显示"开"按钮，默认为True

        Returns:
            创建的框架组件
        """

        frame = tb.Labelframe(parent, text=title, padding=8)
        frame.pack(fill=tk.X, pady=5)

        entry = UIComponents.create_textbox_entry(frame, textvariable, placeholder_text=placeholder_text)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        select_btn = UIComponents.create_button(frame, t("action.select_short"), select_cmd, bootstyle="primary", style="compact")
        select_btn.pack(side=tk.LEFT, padx=(0, 5))

        if open_button and open_cmd is not None:
            open_btn = UIComponents.create_button(frame, t("action.open_short"), open_cmd, bootstyle="info", style="compact")
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
        
        combobox = tb.Combobox(parent, **combo_kwargs)
        
        # 阻止鼠标滚轮事件,避免滚动时改变选项
        combobox.bind("<MouseWheel>", lambda e: "break")
        
        return combobox

    @staticmethod
    def create_tooltip_icon(parent, text: str) -> tk.Label:
        """
        创建一个带有'ⓘ'符号的Label,鼠标悬停时显示Tooltip
        """
        label = tb.Label(
            parent,
            text="ⓘ",
            font=Theme.TOOLTIP_FONT,
            style="info",
            cursor="question_arrow"
        )
        Tooltip(label, text)
        return label


class SettingRow:
    """设置行组件工厂，用于创建统一风格的设置项"""

    @staticmethod
    def create_container(parent: tk.Widget) -> tb.Frame:
        """创建标准的行容器，带有底部间距"""
        frame = tb.Frame(parent)
        frame.pack(fill=tk.X, padx=5, pady=5)  # 垂直间距，让每一行呼吸感更强
        return frame

    @staticmethod
    def _add_label_area(parent: tb.Frame, text: str, tooltip_text: str | None) -> None:
        """私有辅助：添加左侧标签和提示图标"""
        # 使用 Frame 包裹 Label 和 Tooltip，确保它们靠左紧挨
        left_frame = tb.Frame(parent)
        left_frame.pack(side=tk.LEFT, anchor="w")
        
        lbl = tb.Label(left_frame, text=text)
        lbl.pack(side=tk.LEFT)
        
        if tooltip_text:
            # 复用原本的 Tooltip 逻辑，但图标稍微调小或改色
            tip_label = UIComponents.create_tooltip_icon(left_frame, tooltip_text)
            tip_label.pack(side=tk.LEFT, padx=(5, 0))

    @staticmethod
    def create_switch(
        parent: tk.Widget,
        label: str,
        variable: tk.BooleanVar,
        tooltip: str | None = None,
        command: Callable[[], Any] | None = None
    ) -> tb.Checkbutton:
        """创建开关行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        # 核心改变：使用 success-round-toggle 样式
        # side=RIGHT 确保开关始终在最右侧
        chk = tb.Checkbutton(
            container,
            variable=variable,
            command=command,
            style="success-square-toggle",
            text=""  # 开关本身不需要文字，文字在左侧 Label
        )
        chk.pack(side=tk.RIGHT)
        return chk

    @staticmethod
    def create_path_selector(
        parent: tk.Widget,
        label: str,
        path_var: tk.StringVar,
        select_cmd: Callable[[], None],
        open_cmd: Callable[[], None] | None = None,
        tooltip: str | None = None
    ) -> tb.Frame:
        """创建路径选择行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        # 右侧区域容器
        right_frame = tb.Frame(container)
        right_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        
        # 按钮在最右
        if open_cmd:
            UIComponents.create_button(right_frame, t("action.open_short"), open_cmd, bootstyle="info", style="compact"
            ).pack(side=tk.RIGHT, padx=(5,0))
            
        UIComponents.create_button(right_frame, t("action.select_short"), select_cmd, bootstyle="primary", style="compact"
        ).pack(side=tk.RIGHT, padx=(5,0))
        
        # 输入框填充剩余中间区域
        entry = tb.Entry(right_frame, textvariable=path_var)
        entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)
        
        return container

    @staticmethod
    def create_entry_row(
        parent: tk.Widget,
        label: str,
        text_var: tk.StringVar,
        tooltip: str | None = None,
        placeholder_text: str | None = None
    ) -> tb.Entry:
        """创建输入行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        entry = tb.Entry(container, textvariable=text_var)
        # 使用传统方式实现占位符功能
        if placeholder_text:
            # 初始显示占位符
            if not text_var.get():
                entry.insert(0, placeholder_text)
            
            def on_focus_in(event):
                if entry.get() == placeholder_text:
                    entry.delete(0, tk.END)
            
            def on_focus_out(event):
                if not entry.get():
                    entry.insert(0, placeholder_text)
            
            entry.bind('<FocusIn>', on_focus_in)
            entry.bind('<FocusOut>', on_focus_out)
        
        entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        return entry

    @staticmethod
    def create_combobox_row(
        parent: tk.Widget,
        label: str,
        text_var: tk.StringVar,
        values: list[str],
        tooltip: str | None = None
    ) -> tb.Combobox:
        """创建下拉框行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        combobox = tb.Combobox(container, textvariable=text_var, values=values, width=10)
        combobox.pack(side=tk.RIGHT, padx=(10, 0))
        return combobox

    @staticmethod
    def create_radiobutton_row(
        parent: tk.Widget,
        label: str,
        text_var: tk.StringVar,
        values: list[str] | list[tuple[str, str]],
        tooltip: str | None = None
    ) -> tb.Frame:
        """创建单选按钮行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        right_frame = tb.Frame(container)
        right_frame.pack(side=tk.RIGHT)
        
        for value in values:
            if isinstance(value, tuple):
                value, text = value
            else:
                text = value
            
            tb.Radiobutton(
                right_frame,
                text=text,
                variable=text_var,
                value=value,
                bootstyle="outline-toolbutton"
            ).pack(side=tk.LEFT, padx=3)
        
        return container

    @staticmethod
    def create_button_row(
        parent: tk.Widget,
        label: str,
        button_text: str,
        command: Callable[[], None],
        tooltip: str | None = None,
        bootstyle: str = "info"
    ) -> tb.Frame:
        """创建按钮行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        button = UIComponents.create_button(container, button_text, command, bootstyle=bootstyle, style="compact")
        button.pack(side=tk.RIGHT)
        
        return container


class ModeSwitcher:
    """可复用的模式切换组件，使用Radiobutton实现"""

    def __init__(self, parent, mode_var: tk.StringVar, options: list[tuple[str, str]], command: Callable[[], None] | None = None):
        """
        初始化模式切换组件

        Args:
            parent: 父组件
            mode_var: 模式变量
            options: 选项列表，每个元素为 (value, text) 元组
            command: 模式切换时的回调函数
        """
        self.parent = parent
        self.mode_var = mode_var
        self.options = options
        self.command = command

        self.frame = self._create_widgets()

    def _create_widgets(self) -> tk.Frame:
        """创建组件UI"""
        frame = tb.Frame(self.parent)
        frame.pack(fill=tk.X, pady=(0, 10))

        for value, text in self.options:
            tb.Radiobutton(
                frame, text=text,
                variable=self.mode_var,
                value=value,
                command=self._on_mode_change,
                style="outline-toolbutton"
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        return frame

    def _on_mode_change(self):
        """模式切换回调"""
        if self.command:
            self.command()

    def get_frame(self) -> tk.Frame:
        """获取组件框架"""
        return self.frame


class FileListbox:
    """可复用的文件列表框组件，支持拖放、多选、添加/删除文件等功能"""
    
    def __init__(self, parent, title:str, file_list:list[Path] = [], placeholder_text:str | None = None, height=10, logger=None,
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
        self.frame = tb.Labelframe(
            self.parent, 
            text=title, 
            padding=(15, 12)
        )
        self.frame.columnconfigure(0, weight=1)
        
        # 创建列表框区域
        list_frame = tb.Frame(self.frame)
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
            relief=tk.SUNKEN,
            height=self.height
        )
        
        # 创建滚动条
        v_scrollbar = tb.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.listbox.yview)
        h_scrollbar = tb.Scrollbar(list_frame, orient=tk.HORIZONTAL, command=self.listbox.xview)
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
            bootstyle="primary",
            style="compact"
        ).grid(row=0, column=0, sticky="ew", padx=(0, 5))

        UIComponents.create_button(
            button_frame,
            t("action.add_folder"),
            self._browse_add_folder,
            bootstyle="primary",
            style="compact"
        ).grid(row=0, column=1, sticky="ew", padx=5)

        UIComponents.create_button(
            button_frame,
            t("action.remove_selected"),
            self._remove_selected,
            bootstyle="warning",
            style="compact"
        ).grid(row=0, column=2, sticky="ew", padx=5)

        UIComponents.create_button(
            button_frame,
            t("action.clear_list"),
            self._clear_list,
            bootstyle="danger",
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
    
    def _handle_drop(self, event: tk.Event):
        """处理拖放事件"""
        # tkinterdnd2 返回的events.data有{}的形式也有空格分隔的形式，要用自带的函数处理
        raw_paths = event.widget.tk.splitlist(event.data)
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
        """获取列表框控件,用于直接操作"""
        return self.listbox


class Tooltip:
    """悬浮提示组件,鼠标悬停时显示提示信息"""
    
    def __init__(self, widget, text: str, delay: int = 500):
        """
        初始化悬浮提示
        
        Args:
            widget: 要绑定提示的控件
            text: 提示文本
            delay: 延迟显示时间(毫秒)
        """
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.tip_id = None
        
        self.widget.bind("<Enter>", self._show_tip)
        self.widget.bind("<Leave>", self._hide_tip)
    
    def _show_tip(self, event=None):
        """显示提示框"""
        if self.tip_id:
            self.widget.after_cancel(self.tip_id)
            self.tip_id = None
        
        self.tip_id = self.widget.after(self.delay, self._create_tip_window)
    
    def _hide_tip(self, event=None):
        """隐藏提示框"""
        if self.tip_id:
            self.widget.after_cancel(self.tip_id)
            self.tip_id = None
        
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
    
    def _create_tip_window(self):
        """创建提示窗口"""
        if self.tip_window:
            return
        
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        self.tip_window = tk.Toplevel(self.widget)
        self.tip_window.wm_overrideredirect(True)
        self.tip_window.wm_geometry(f"+{x}+{y}")
        
        label = tb.Label(
            self.tip_window,
            text=self.text,
            justify=tk.LEFT,
            background=Theme.TOOLTIP_BG,
            relief=tk.SOLID,
            borderwidth=1,
            font=Theme.TOOLTIP_FONT,
            padding=(5, 3)
        )
        label.pack(ipadx=1)
