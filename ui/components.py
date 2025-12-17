# ui/components.py

import tkinter as tk
from tkinterdnd2 import DND_FILES
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
            self.status_widget.config(text=f"{t('ui.status_label')}{message}")
        
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
    def create_drop_zone(parent, title, drop_cmd, browse_cmd, label_text, button_text, search_path_var=None):
        """创建通用的拖放区域组件"""
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

        label = tk.Label(frame, text=label_text, relief=tk.GROOVE, height=4, bg=Theme.MUTED_BG, fg=Theme.TEXT_NORMAL, font=Theme.INPUT_FONT, justify=tk.LEFT)
        label.pack(fill=tk.X, pady=(0, 8))
        label.drop_target_register(DND_FILES)
        label.dnd_bind('<<Drop>>', drop_cmd)
        label.bind('<Configure>', UIComponents._debounce_wraplength)

        button = UIComponents.create_button(frame, button_text, browse_cmd, bg_color=Theme.BUTTON_PRIMARY_BG, style="compact")
        button.pack()
        return frame, label

    @staticmethod
    def create_file_drop_zone(parent, title, drop_cmd, browse_cmd, search_path_var=None):
        """创建文件拖放区域"""
        return UIComponents.create_drop_zone(
            parent, title, drop_cmd, browse_cmd, 
            t("ui.drop_zone.file_hint"), 
            t("action.browse_file"),
            search_path_var
        )

    @staticmethod
    def create_folder_drop_zone(parent, title, drop_cmd, browse_cmd):
        """创建文件夹拖放区域"""
        return UIComponents.create_drop_zone(
            parent, title, drop_cmd, browse_cmd,
            t("ui.drop_zone.folder_hint"),
            t("action.browse_folder")
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

        select_btn = UIComponents.create_button(frame, t("action.select_short"), select_cmd, bg_color=Theme.BUTTON_PRIMARY_BG, width=3, style="compact")
        select_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        if open_button and open_cmd is not None:
            open_btn = UIComponents.create_button(frame, t("action.open_short"), open_cmd, bg_color=Theme.BUTTON_SECONDARY_BG, width=3, style="compact")
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