# gui/components.py

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.widgets.tooltip import ToolTip
from tkinterdnd2 import DND_FILES
from pathlib import Path
from typing import Callable, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .app import App

from .utils import select_file, select_directory, open_directory, build_filetypes
from ..i18n import t
from ..naming import parse_filename
from ..models import FileType

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
    """集中管理原生Tkinter组件的颜色和字体
        不包含ttkbootstrap组件"""
    # 背景色
    INPUT_BG = '#ecf0f1'

    # 文本颜色
    TEXT_NORMAL = '#34495e'

    # 特殊组件颜色
    LOG_BG = '#2c3e50'
    LOG_FG = '#ecf0f1'
    LOG_SELECTED = '#3a5a7a'

    # 字体
    DROP_ZONE_FONT = ("Microsoft YaHei", 9)
    INPUT_FONT = ("Microsoft YaHei", 9)
    STATUS_BAR_FONT = ("Microsoft YaHei", 9)
    LOG_FONT = ("Consolas", 9)
    TOOLTIP_FONT = ("Microsoft YaHei", 9)


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
        elif style == "short":
            button_kwargs["padding"] = (10, 3)
        elif style == "large":
            button_kwargs["padding"] = (15, 6)
        else:
            button_kwargs["padding"] = padding if padding is not None else (10, 5)

        button_kwargs.update(kwargs)

        return tb.Button(parent, text=text, **button_kwargs)

    @staticmethod
    def create_checkbutton(parent, text, variable, command=None):
        """创建复选框组件"""
        checkbutton = tb.Checkbutton(
            parent, 
            text=text, 
            variable=variable,
            command=command,
        )
        return checkbutton

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

        select_btn = UIComponents.create_button(frame, t("action.select"), select_cmd, bootstyle="primary", style="compact")
        select_btn.pack(side=tk.LEFT, padx=(0, 5))

        if open_button and open_cmd is not None:
            open_btn = UIComponents.create_button(frame, t("action.open"), open_cmd, bootstyle="info", style="compact")
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
    def create_tooltip_icon(parent, text: str) -> tb.Label:
        """
        创建一个带有'ⓘ'符号的Label,鼠标悬停时显示Tooltip
        """
        label = tb.Label(
            parent,
            text="ⓘ",
            style="info",
            cursor="question_arrow"
        )
        ToolTip(label, text=text, padding=5, wraplength=600)
        return label

class DropZone(tb.Labelframe):
    """拖放区域组件，支持多文件拖放"""

    def __init__(
        self, parent,
        title: str, placeholder_text: str,
        app: "App",
        on_files_selected: Callable[[list[Path] | Path], None] | None = None,
        file_types: list[FileType | str] = [FileType.BUNDLE, FileType.ALL],
        search_path_var=None,
        clear_cmd: Callable[[], None] | None = None,
        allow_folder: bool = False,
        allow_multiple: bool = True,
        logger: Logger | None = None,
        **kwargs
    ):
        super().__init__(parent, text=title, padding=(15, 12), **kwargs)
        self.pack(fill=tk.X, pady=(0, 5))

        self.placeholder_text = placeholder_text
        self._on_files_selected = on_files_selected
        self._clear_cmd = clear_cmd
        self._allow_folder = allow_folder
        self._allow_multiple = allow_multiple
        self._logger = logger
        self._paths: list[Path] = []
        self._open_btn = None  # "打开"按钮引用
        self._clear_btn = None  # "清除"按钮引用
        self._app = app  # App 引用（ADB 模式需要）
        self._adb_remote_paths: list[str] = []  # ADB 模式下的远程路径
        
        # 内部存储：转换为 tkinter 需要的 tuple 格式
        self._tk_filetypes: list[tuple[str, str]] = build_filetypes(file_types)
        self._allowed_extensions: set[str] = set(file_types) - {FileType.ALL}

        if search_path_var is not None:
            search_frame = tb.Frame(self)
            search_frame.pack(fill=tk.X, pady=(0, 8))
            tb.Label(search_frame, text=t("ui.label.search_path")).pack(side=tk.LEFT, padx=(0, 5))
            UIComponents.create_textbox_entry(
                search_frame,
                textvariable=search_path_var,
                readonly=True
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.label = tb.Label(
            self, text=placeholder_text,
            relief="sunken",
            anchor="center",
            justify="center",
            padding=10,
            font=Theme.DROP_ZONE_FONT,
            bootstyle="inverse-light"
        )
        self.label.pack(fill=tk.X, pady=(0, 8))
        self.label.drop_target_register(DND_FILES)
        self.label.dnd_bind('<<Drop>>', self._handle_drop)
        self.label.bind('<Configure>', self._debounce_wraplength)

        btn_frame = tb.Frame(self)
        btn_frame.pack(anchor=tk.CENTER)

        button_text = t("action.browse_folder") if allow_folder else t("action.browse_file")
        UIComponents.create_button(btn_frame, button_text, self._handle_browse, bootstyle="primary", style="short").pack(side=tk.LEFT, padx=(0, 5))

        self._open_btn = UIComponents.create_button(btn_frame, t("action.open"), self._handle_open_directory, bootstyle="info", style="short", state=tk.DISABLED)
        self._open_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._clear_btn = UIComponents.create_button(btn_frame, t("action.clear"), self.clear, bootstyle="warning", style="short", state=tk.DISABLED)
        self._clear_btn.pack(side=tk.LEFT)

    @property
    def paths(self) -> list[Path]:
        """当前选中的路径列表"""
        return self._paths

    @property
    def path(self) -> Path | None:
        """兼容旧接口，返回第一个路径"""
        return self._paths[0] if self._paths else None

    def set_files(self, paths: list[Path] | Path) -> None:
        """设置文件列表，支持单Path或Path列表"""
        # 统一转换为列表
        if isinstance(paths, Path):
            paths = [paths]
        
        # 当不允许多文件时，检查路径数量
        if not self._allow_multiple and len(paths) > 1:
            raise ValueError(f"DropZone does not allow multiple files, but got {len(paths)} paths")
        
        self._paths = paths
        if paths:
            self._update_display()
        self._update_btn_state()
        
        # 触发回调
        if self._on_files_selected:
            if self._allow_multiple:
                self._on_files_selected(paths)
            else:
                self._on_files_selected(paths[0])

    def _is_valid_file(self, path: Path) -> bool:
        """检查是否是有效的文件（根据 filetypes 参数）"""
        if not path.is_file():
            return False
        
        # 检查后缀名
        suffix = path.suffix
        if suffix in self._allowed_extensions:
            return True
        
        # 特殊处理 .bundle.backup（后缀是 .backup，但实际是 bundle）
        if FileType.BUNDLE_BACKUP in self._allowed_extensions and suffix == '.backup':
            stem_suffix = Path(path.stem).suffix
            return stem_suffix == '.bundle'
        
        return False

    def _update_display(self) -> None:
        """根据当前文件列表更新 UI 显示"""
        if not self._paths:
            return
        
        if self._allow_multiple:
            parsed = parse_filename(self._paths[0].name)
            res_types = [parse_filename(p.name).res_type or "base" for p in self._paths]
            type_str = ", ".join(sorted(set(res_types)))

            # 查找角色名（如果映射表可用）
            field = self._app.character_name_field_var.get()
            char_name = self._app.char_map.lookup(parsed.core, field) or ""

            # 格式化显示文本（逐个拼接）
            ui_text = parsed.core
            if char_name:
                ui_text += f"（{char_name}）"
            ui_text += f"\n({t('ui.drop_zone.contains', count=len(self._paths), types=type_str)})"

            self.set_success(ui_text)
        else:
            self.set_success(self._paths[0].name)

    def set_success(self, text: str | None = None) -> None:
        """设置成功状态（绿色）"""
        self.label.config(text=text, bootstyle="success")

    def set_warning(self, text: str | None = None) -> None:
        """设置警告状态（黄色）"""
        self.label.config(text=text, bootstyle="warning")

    def set_error(self, text: str | None = None) -> None:
        """设置错误状态（红色）"""
        self.label.config(text=text, bootstyle="danger")

    def set_searching(self, text: str | None = None) -> None:
        """设置搜索中状态"""
        self.label.config(text=text or t("ui.drop_zone.searching"), bootstyle="warning")

    def clear(self) -> None:
        """清除状态，恢复初始状态，并调用外部清理回调"""
        self._paths = []
        self.label.config(text=self.placeholder_text, bootstyle="inverse-light")
        self._update_btn_state()
        if self._clear_cmd:
            self._clear_cmd()

    def _handle_open_directory(self) -> None:
        """打开选中文件所在的目录"""
        if not self._paths:
            return

        directory = self._paths[0].parent
        open_directory(directory, log=self._logger.log if self._logger else None)

    def _update_btn_state(self) -> None:
        """更新"打开"和"清除"按钮的启用/禁用状态"""
        state = tk.NORMAL if self._paths else tk.DISABLED
        if self._open_btn:
            self._open_btn.config(state=state)
        if self._clear_btn:
            self._clear_btn.config(state=state)

    def _handle_drop(self, event: tk.Event) -> None:
        """内部处理拖放事件，支持多文件和文件夹"""
        raw_paths = event.widget.tk.splitlist(event.data)
        paths_to_add = []
        
        for p_str in raw_paths:
            path = Path(p_str.strip('{}'))
            if self._allow_folder and path.is_dir():
                paths_to_add.append(path)
            elif self._is_valid_file(path):
                paths_to_add.append(path)
        
        if not paths_to_add:
            return
        
        if not self._allow_multiple and len(paths_to_add) > 1:
            self.clear()
            self.set_warning(t("ui.drop_zone.multiple_files_rejected"))
            return
        
        self.set_files(paths_to_add[:1] if not self._allow_multiple else paths_to_add)

    def _handle_browse(self) -> None:
        """内部处理浏览按钮，支持多文件选择"""
        # ADB 模式
        if self._is_adb_mode():
            self._browse_adb()
            return

        # 本地模式
        if self._allow_folder:
            path = select_directory(
                title=t("ui.dialog.select", type=self.cget("text")),
                log=self._logger.log if self._logger else None
            )
            if path:
                dir_path = Path(path)
                bundle_files = sorted(f for f in dir_path.iterdir() if self._is_valid_file(f))
                if bundle_files:
                    self.set_files(bundle_files[:1] if not self._allow_multiple else bundle_files)
        else:
            select_file(
                title=t("ui.dialog.select", type=self.cget("text")),
                file_types=self._tk_filetypes,
                multiple=self._allow_multiple,
                callback=self._handle_browse_callback,
                log=self._logger.log if self._logger else None
            )

    def _is_adb_mode(self) -> bool:
        """检查是否为 ADB 模式"""
        if self._app is not None:
            return self._app.is_adb_mode()
        return False

    def _browse_adb(self) -> None:
        """ADB 模式下的浏览操作"""
        if not self._app:
            return
        from .windows.adb_browser import ADBFileBrowser
        adb_source = self._app.get_adb_file_source()
        if not adb_source.is_available():
            from tkinter import messagebox
            messagebox.showerror(t("common.error"), t("message.adb.not_connected"))
            return

        browser = ADBFileBrowser(
            self.winfo_toplevel(),
            adb_source=adb_source,
            multiple=self._allow_multiple,
            log=self._logger.log if self._logger else None
        )

        if browser.selected_paths:
            # 将远程路径缓存到本地
            local_paths: list[Path] = []
            self._adb_remote_paths = browser.selected_paths
            for remote_path in browser.selected_paths:
                try:
                    local_path = adb_source.ensure_local(remote_path)
                    local_paths.append(local_path)
                except Exception as e:
                    if self._logger:
                        self._logger.log(t("log.adb.pull_failed", path=remote_path, error=e))
            if local_paths:
                self.set_files(local_paths[:1] if not self._allow_multiple else local_paths)

    @property
    def adb_remote_paths(self) -> list[str]:
        """获取 ADB 模式下的远程路径列表"""
        return self._adb_remote_paths

    def _handle_browse_callback(self, paths: list[Path]) -> None:
        """浏览选择后的回调处理"""
        if paths:
            self.set_files(paths)

    @staticmethod
    def _debounce_wraplength(event: tk.Event) -> None:
        """防抖处理函数，用于更新标签的 wraplength"""
        widget = event.widget
        if hasattr(widget, "_debounce_timer"):
            widget.after_cancel(widget._debounce_timer)
        widget._debounce_timer = widget.after(500,
            lambda: widget.config(wraplength=widget.winfo_width() - 10))


class SettingRow:
    """设置行组件工厂，用于创建统一风格的设置项"""

    @staticmethod
    def create_container(parent: tk.Widget) -> tb.Frame:
        """创建标准的行容器，带有底部间距"""
        frame = tb.Frame(parent)
        frame.pack(fill=tk.X, padx=5, pady=4)  # 垂直间距，让每一行呼吸感更强
        return frame

    @staticmethod
    def _add_label_area(parent: tb.Frame, text: str, tooltip_text: str | None, status_check: Callable[[], bool] | None = None) -> Callable[[], None] | None:
        """私有辅助：添加左侧标签和提示图标

        Args:
            status_check: 可选的状态检查函数，返回 True 表示已配置（绿色指示器）

        Returns:
            如果提供了 status_check，返回一个刷新指示器状态的函数；否则返回 None
        """
        # 使用 Frame 包裹 Label 和 Tooltip，确保它们靠左紧挨
        left_frame = tb.Frame(parent)
        left_frame.pack(side=tk.LEFT, anchor="w")
        
        lbl = tb.Label(left_frame, text=text)
        lbl.pack(side=tk.LEFT)

        refresh_fn = None

        if status_check:
            indicator = tb.Label(left_frame, text="●", font=("", 8))
            indicator.pack(side=tk.LEFT, padx=(5, 0))

            def _refresh():
                if not indicator.winfo_exists():
                    return
                color = "green" if status_check() else "gray"
                indicator.config(foreground=color)

            refresh_fn = _refresh
            _refresh()

        if tooltip_text:
            # 复用原本的 Tooltip 逻辑，但图标稍微调小或改色
            tip_label = UIComponents.create_tooltip_icon(left_frame, tooltip_text)
            tip_label.pack(side=tk.LEFT, padx=(5, 0))

        return refresh_fn

    @staticmethod
    def _setup_dependency(
        widget: tk.Widget,
        app: "App",
        depends_on: str,
        on_disabled: Callable[[], None],
        on_enabled: Callable[[], None],
        parent: tk.Widget,
        on_click_disabled: Callable[[tk.Widget], None] | None = None
    ) -> None:
        """设置依赖管理：当依赖无效时禁用控件，点击时显示下载引导"""
        def update_status():
            # 检查控件是否仍然存在（对话框关闭后 widget 可能已销毁）
            if not widget.winfo_exists():
                return

            available = app.check_dependency(depends_on)
            if not available:
                on_disabled()
                if on_click_disabled:
                    widget.bind('<Button-1>', lambda e: on_click_disabled(parent))
            else:
                on_enabled()
                widget.unbind('<Button-1>')
        
        dep_var = getattr(app, depends_on)
        dep_var.trace_add('write', lambda *_: update_status())
        update_status()

    @staticmethod
    def create_switch(
        parent: tk.Widget,
        label: str,
        variable: tk.BooleanVar,
        tooltip: str | None = None,
        command: Callable[[], Any] | None = None,
        app: "App | None" = None,
        depends_on: str | None = None,
        on_click_disabled: Callable[[tk.Widget], None] | None = None
    ) -> tb.Checkbutton:
        """创建开关行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        chk = tb.Checkbutton(
            container,
            variable=variable,
            command=command,
            style="success-square-toggle",
            text=""
        )
        chk.pack(side=tk.RIGHT)
        
        # 自动从 variable 推导 depends_on（如果未手动指定）
        if app and depends_on is None:
            depends_on = app.get_depends_on_from_var(variable)
        
        if app and depends_on:
            SettingRow._setup_dependency(
                chk, app, depends_on,
                on_disabled=lambda: (chk.config(state=tk.DISABLED), variable.set(False)),
                on_enabled=lambda: chk.config(state=tk.NORMAL),
                parent=parent,
                on_click_disabled=on_click_disabled
            )
        
        return chk

    @staticmethod
    def create_path_selector(
        parent: tk.Widget,
        label: str,
        path_var: tk.StringVar,
        select_cmd: Callable[[], None],
        open_cmd: Callable[[], None] | None = None,
        tooltip: str | None = None,
        download_guide_cmd: Callable[[tk.Widget | None], None] | None = None,
        status_check: Callable[[], bool] | None = None,
        extra_button: tuple[str, Callable[[], None], str] | None = None
    ) -> tb.Frame:
        """创建路径选择行

        Args:
            parent: 父组件
            label: 标签文本
            path_var: 路径变量
            select_cmd: 选择路径命令
            open_cmd: 打开路径命令（可选）
            tooltip: 提示文本（可选）
            download_guide_cmd: 下载引导命令（可选），接收顶层窗口作为参数
            status_check: 状态检查函数（可选），返回 True 显示绿色指示器
            extra_button: 额外按钮 (text, command, bootstyle)（可选）
        """
        container = SettingRow.create_container(parent)
        refresh_indicator = SettingRow._add_label_area(container, label, tooltip, status_check)
        
        # 右侧区域容器
        right_frame = tb.Frame(container)
        right_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(50, 0))

        # 额外按钮
        if extra_button:
            text, cmd, style = extra_button
            UIComponents.create_button(
                right_frame,
                text,
                cmd,
                bootstyle=style,
                style="compact"
            ).pack(side=tk.RIGHT, padx=(5, 0))

        # 下载按钮（如果提供了下载引导命令）
        if download_guide_cmd:
            # 获取顶层窗口作为 parent 传递给下载引导命令
            toplevel = parent.winfo_toplevel()
            UIComponents.create_button(
                right_frame,
                t("action.download"),
                lambda: download_guide_cmd(toplevel),
                bootstyle="warning",
                style="compact"
            ).pack(side=tk.RIGHT, padx=(5, 0))
        
        # 打开按钮
        if open_cmd:
            UIComponents.create_button(
                right_frame,
                t("action.open"),
                open_cmd,
                bootstyle="info",
                style="compact"
            ).pack(side=tk.RIGHT, padx=(5, 0))
        
        # 选择按钮
        UIComponents.create_button(
            right_frame,
            t("action.select"),
            select_cmd,
            bootstyle="primary",
            style="compact"
        ).pack(side=tk.RIGHT, padx=(5, 0))
        
        # 输入框填充剩余中间区域
        entry = tb.Entry(right_frame, textvariable=path_var)
        entry.pack(side=tk.RIGHT, fill=tk.X, expand=True)

        # 路径变化时刷新状态指示器
        if refresh_indicator:
            path_var.trace_add('write', lambda *_: refresh_indicator())

        return container

    @staticmethod
    def create_entry_row(
        parent: tk.Widget,
        label: str,
        text_var: tk.StringVar,
        tooltip: str | None = None,
        placeholder_text: str | None = None,
        expand: bool = False,
        app: "App | None" = None,
        depends_on: str | None = None,
        on_click_disabled: Callable[[tk.Widget], None] | None = None
    ) -> tb.Entry:
        """创建输入行，支持依赖管理和点击提示
        
        Args:
            on_click_disabled: 点击禁用控件时的回调
        """
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        
        entry = tb.Entry(container, textvariable=text_var, width = 10)
        if placeholder_text:
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
        
        if expand:
            entry.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        else:
            entry.pack(side=tk.RIGHT, padx=(10, 0))
        
        # 自动从 variable 推导 depends_on（如果未手动指定）
        if app and depends_on is None:
            depends_on = app.get_depends_on_from_var(text_var)
        
        if app and depends_on:
            SettingRow._setup_dependency(
                entry, app, depends_on,
                on_disabled=lambda: entry.config(state=tk.DISABLED),
                on_enabled=lambda: entry.config(state=tk.NORMAL),
                parent=parent,
                on_click_disabled=on_click_disabled
            )
        
        return entry

    @staticmethod
    def create_combobox_row(
        parent: tk.Widget,
        label: str,
        text_var: tk.StringVar,
        values: list[str] | list[tuple[str, str]],
        tooltip: str | None = None,
        width: int | None = None,
    ) -> tb.Combobox:
        """创建下拉框行

        Args:
            values: 选项列表。可以是纯字符串列表，或 (实际值, 显示值) 元组列表。
                    使用元组时，combobox 显示本地化文本，但 text_var 存储原始值。
        """
        # 处理 values 格式：支持 (value, display) 元组
        if values and isinstance(values[0], tuple):
            actual_values = [v[0] for v in values]
            display_values = [v[1] for v in values]
            value_to_display = dict(values)
            display_to_value = {d: v for v, d in values}
        else:
            actual_values = values
            display_values = values
            value_to_display = None
            display_to_value = None

        if width is None:
            width = max((len(str(v)) for v in display_values), default=0) + 2

        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)

        # 如果有映射，需要创建一个临时变量来存储显示值
        if value_to_display:
            # 创建显示值变量
            display_var = tk.StringVar()
            # 初始化显示值
            current_actual = text_var.get()
            if current_actual in value_to_display:
                display_var.set(value_to_display[current_actual])

            combobox = tb.Combobox(container, textvariable=display_var, values=display_values, width=width)
            combobox.pack(side=tk.RIGHT, padx=(10, 0))

            # 当选择改变时，同步实际值
            def _on_select(event):
                selected_display = display_var.get()
                if selected_display in display_to_value:
                    text_var.set(display_to_value[selected_display])

            combobox.bind("<<ComboboxSelected>>", _on_select)

            # 当实际值改变时（如加载配置），同步显示值
            def _sync_display(*args):
                actual = text_var.get()
                if actual in value_to_display:
                    display_var.set(value_to_display[actual])

            text_var.trace_add("write", _sync_display)

            return combobox
        else:
            # 无映射，直接使用 text_var
            combobox = tb.Combobox(container, textvariable=text_var, values=values, width=width)
            combobox.pack(side=tk.RIGHT, padx=(10, 0))
            return combobox

    @staticmethod
    def create_radiobutton_row(
        parent: tk.Widget,
        label: str,
        text_var: tk.StringVar,
        values: list[str] | list[tuple[str, str]],
        tooltip: str | None = None,
        command: Callable[[], None] | None = None
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
                bootstyle="outline-toolbutton",
                command=command
            ).pack(side=tk.LEFT, padx=3)
        
        return container

    @staticmethod
    def create_spinbox_row(
        parent: tk.Widget,
        label: str,
        int_var: tk.IntVar,
        from_: int = 1,
        to: int = 8,
        tooltip: str | None = None,
        width: int | None = None,
    ) -> tb.Spinbox:
        """创建数值选择器行"""
        container = SettingRow.create_container(parent)
        SettingRow._add_label_area(container, label, tooltip)
        if width is None:
            width = len(str(to)) + 2

        spinbox = tb.Spinbox(
            container,
            from_=from_, to=to,
            textvariable=int_var,
            width=width,
        )
        spinbox.pack(side=tk.RIGHT, padx=(10, 0))
        return spinbox

    @staticmethod
    def create_button_row(
        parent: tk.Widget,
        label: str,
        button_text: str,
        command: Callable[[], None],
        tooltip: str | None = None,
        bootstyle: str = "info",
        status_check: Callable[[], bool] | None = None
    ) -> tb.Frame:
        """创建按钮行"""
        container = SettingRow.create_container(parent)
        refresh_indicator = SettingRow._add_label_area(container, label, tooltip, status_check)

        button = UIComponents.create_button(container, button_text, command, bootstyle=bootstyle, style="compact")
        button.pack(side=tk.RIGHT)

        # 保存刷新函数，供外部调用
        if refresh_indicator:
            container._refresh_indicator = refresh_indicator

        return container


class ModeSwitcher:
    """可复用的模式切换组件，使用Radiobutton实现"""

    def __init__(self, parent, mode_var: tk.Variable, options: list[tuple[str | int, str]], command: Callable[[], None] | None = None):
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

    def _create_widgets(self) -> tb.Frame:
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
            ).pack(side=tk.LEFT, fill=tk.X, padx=2, expand=True)

        return frame

    def _on_mode_change(self):
        """模式切换回调"""
        if self.command:
            self.command()

    def get_frame(self) -> tb.Frame:
        """获取组件框架"""
        return self.frame


class FileListbox:
    """可复用的文件列表框组件，支持拖放、多选、添加/删除文件等功能"""
    
    def __init__(self, parent, title:str, file_list:list[Path] = [], placeholder_text:str | None = None, height=10, logger: Logger | None = None,
    display_formatter: Callable[[Path], str] | None = None, 
    on_files_added: Callable[[list[Path]], None] | None = None,
    allowed_suffixes: set[str] = {".bundle"}
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
            allowed_suffixes: 允许的文件后缀集合，默认仅 .bundle
        """
        self.parent = parent
        self.file_list: list[Path] = file_list
        self.placeholder_text = placeholder_text
        self.height = height
        self.logger: Logger = logger
        self.display_formatter = display_formatter
        self.on_files_added = on_files_added
        self.allowed_suffixes = allowed_suffixes
        
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
        button_frame = tb.Frame(self.frame)
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
        suffixes = self.allowed_suffixes
        paths_to_add = []

        for p_str in raw_paths:
            path = Path(p_str)
            if path.is_dir():
                if suffixes:
                    for suf in suffixes:
                        paths_to_add.extend(sorted(path.glob(f'*{suf}')))
                else:
                    # 空后缀集合：接受目录下所有文件
                    paths_to_add.extend(sorted(p for p in path.iterdir() if p.is_file()))
            elif path.is_file() and (not suffixes or path.suffix.lower() in suffixes):
                paths_to_add.append(path)

        if paths_to_add:
            self.add_files(paths_to_add)

    def _browse_add_files(self):
        """浏览添加文件"""
        if self.allowed_suffixes:
            ft = [(f"*{s}", f"*{s}") for s in sorted(self.allowed_suffixes)]
            ft.append((t("file_type.all_files"), "*.*"))
        else:
            ft = [(t("file_type.all_files"), "*.*")]
        select_file(
            title=t("action.add_files"),
            file_types=ft,
            multiple=True,
            callback=lambda paths: self.add_files(paths),
            log=self.logger.log if self.logger else None
        )

    def _browse_add_folder(self):
        """浏览添加文件夹"""
        folder = select_directory(
            title = t("action.add_folder"),
            log = self.logger.log if self.logger else None
            )

        if folder:
            path = Path(folder)
            files: list[Path] = []
            if self.allowed_suffixes:
                for suf in self.allowed_suffixes:
                    files.extend(sorted(path.glob(f'*{suf}')))
            else:
                # 空后缀集合：接受目录下所有文件
                files.extend(sorted(p for p in path.iterdir() if p.is_file()))
            if files:
                self.add_files(files)
                if self.logger:
                    self.logger.log(t('log.file.added_count', count=len(files)))
            else:
                if self.logger:
                    if self.allowed_suffixes:
                        self.logger.log(t('log.file.no_files_found_in_folder', type=', '.join(sorted(self.allowed_suffixes))))
                    else:
                        self.logger.log(t('log.file.no_files_found_in_folder', type='*'))
    
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
