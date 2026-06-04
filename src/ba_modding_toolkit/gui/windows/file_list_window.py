# gui/windows/file_list_window.py

import tkinter as tk
from tkinter import messagebox
import threading
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Callable
from enum import Enum

import ttkbootstrap as tb
from ttkbootstrap.widgets.tableview import Tableview as TBTableview

from ...i18n import t
from ...utils import CRCUtils
from ...naming import parse_filename
from ...searching import list_bundle_files
from ...bundle import analyze_bundles, BUNDLE_ANALYZERS
from ...models import BundleFileInfo
from ...core import render_spine_preview_from_bundle
from ..components import Theme, UIComponents
from ..utils import open_directory, select_directory

if TYPE_CHECKING:
    from ..app import App


def _format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    else:
        return f"{size / (1024 * 1024):.1f} MB"


def _format_hex(data: bytes | None) -> str:
    if data is None:
        return ""
    return " ".join(f"{b:02X}" for b in data)


def _format_time(mtime: float) -> str:
    if mtime <= 0:
        return ""
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


_UNSET = "—"


class ColumnId(Enum):
    """Tableview 列索引"""
    filename = 0
    directory = 1
    file_size = 2
    modified_time = 3
    trailing_bytes = 4
    trailing_content = 5
    core = 6
    res_type = 7
    crc = 8
    crc_actual = 9
    _path = 10  # 隐藏列，用于 iid


class ColumnDef(NamedTuple):
    """Tableview 列定义"""
    id: ColumnId
    text: str
    width: int
    default_visible: bool = True


COLUMNS: list[ColumnDef] = [
    ColumnDef(ColumnId.filename, t("ui.file_list.column.filename"), 500),
    ColumnDef(ColumnId.directory, t("ui.file_list.column.directory"), 80),
    ColumnDef(ColumnId.file_size, t("ui.file_list.column.file_size"), 80),
    ColumnDef(ColumnId.modified_time, t("ui.file_list.column.modified_time"), 100),
    ColumnDef(ColumnId.trailing_bytes, t("ui.file_list.column.trailing_bytes"), 80, default_visible=False),
    ColumnDef(ColumnId.trailing_content, t("ui.file_list.column.trailing_content"), 150, default_visible=False),
    ColumnDef(ColumnId.core, t("ui.file_list.column.core"), 150, default_visible=False),
    ColumnDef(ColumnId.res_type, t("ui.file_list.column.res_type"), 80, default_visible=False),
    ColumnDef(ColumnId.crc, t("ui.file_list.column.crc"), 80, default_visible=False),
    ColumnDef(ColumnId.crc_actual, t("ui.file_list.column.crc_actual"), 80, default_visible=False),
]

class AnalyzerOption(NamedTuple):
    """分析器选项定义"""
    key: str
    text: str

ANALYZER_OPTIONS: list[AnalyzerOption] = [
    AnalyzerOption("trailing", t("ui.file_list.analyze_trailing")),
    AnalyzerOption("naming", t("ui.file_list.analyze_naming")),
    AnalyzerOption("crc", t("ui.file_list.analyze_crc")),
]

ANALYZER_TO_COLUMNS: dict[str, list[ColumnId]] = {
    "trailing": [ColumnId.trailing_bytes, ColumnId.trailing_content],
    "naming": [ColumnId.core, ColumnId.res_type],
    "crc": [ColumnId.crc, ColumnId.crc_actual],
}

FILTERS: dict[str, tuple[str, Callable[[BundleFileInfo], bool]]] = {
    """要排除的文件类型，返回 True 表示排除"""
    "trailing_zero": (t("ui.file_list.filter.trailing_zero"), lambda item: item.trailing_bytes == 0),
    "crc_match": (t("ui.file_list.filter.crc_match"), lambda item: item.crc_actual is not None and item.parsed_name and item.crc_actual == int(item.parsed_name.crc or 0)),
    "crc_mismatch": (t("ui.file_list.filter.crc_mismatch"), lambda item: item.crc_actual is not None and item.parsed_name and item.crc_actual != int(item.parsed_name.crc or 0)),
}

# 批量选中操作符定义
SELECT_OPERATORS: list[tuple[str, str]] = [
    ("contains", t("ui.file_list.op.contains")),
    ("equals", t("ui.file_list.op.equals")),
    ("starts_with", t("ui.file_list.op.starts_with")),
    ("ends_with", t("ui.file_list.op.ends_with")),
    ("regex", t("ui.file_list.op.regex")),
]


class BatchSelectDialog(tb.Toplevel):
    """批量选中条件对话框（从表头右键菜单调用，已知目标列）"""

    def __init__(self, master, column_id: ColumnId, column_name: str):
        super().__init__(master)
        self.column_id = column_id
        self.column_name = column_name
        self._result: tuple[str, str, bool, bool] | None = None  # (操作符, 值, 是否反选, 是否筛选)

        self._setup_window()
        self._create_widgets()

        self.wait_visibility()
        self.grab_set()

    def _setup_window(self):
        self.title(t("ui.file_list.select.dialog_title"))
        self.geometry("350x170")
        self.transient(self.master)
        self.resizable(False, False)

    def _create_widgets(self):
        main_frame = tb.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 显示目标列名称
        tb.Label(
            main_frame,
            text=f"{t('ui.file_list.select.column')}: {self.column_name}",
            bootstyle="info"
        ).pack(fill=tk.X, pady=(0, 5))

        # 操作符选择
        row1 = tb.Frame(main_frame)
        row1.pack(fill=tk.X, pady=(0, 5))

        tb.Label(row1, text=t("ui.file_list.select.operator")).pack(side=tk.LEFT, padx=(0, 5))
        self._operator_var = tk.StringVar()
        operator_values = [op[1] for op in SELECT_OPERATORS]
        operator_combo = tb.Combobox(
            row1, textvariable=self._operator_var,
            values=operator_values, width=15, state="readonly",
        )
        operator_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if operator_values:
            operator_combo.set(operator_values[0])

        # 值输入 + 反选勾选框
        row2 = tb.Frame(main_frame)
        row2.pack(fill=tk.X, pady=(0, 5))

        tb.Label(row2, text=t("ui.file_list.select.value")).pack(side=tk.LEFT, padx=(0, 5))
        self._value_var = tk.StringVar()
        value_entry = tb.Entry(row2, textvariable=self._value_var, width=20)
        value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))

        self._invert_var = tk.BooleanVar(value=False)
        tb.Checkbutton(row2, text=t("ui.file_list.select.invert"), variable=self._invert_var).pack(side=tk.LEFT)

        # 按钮
        btn_frame = tb.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))

        UIComponents.create_button(
            btn_frame, t("ui.file_list.select.action"),
            lambda: self._on_submit(filter_rows=False),
            bootstyle="primary", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        UIComponents.create_button(
            btn_frame, t("ui.file_list.select.action_filter"),
            lambda: self._on_submit(filter_rows=True),
            bootstyle="success", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        UIComponents.create_button(
            btn_frame, t("common.cancel"),
            self._on_cancel, bootstyle="secondary", style="compact"
        ).pack(side=tk.RIGHT)

    def _get_operator_key(self) -> str | None:
        """根据选择的操作符文本获取操作符键"""
        selected_text = self._operator_var.get()
        for key, text in SELECT_OPERATORS:
            if text == selected_text:
                return key
        return None

    def _on_submit(self, filter_rows: bool):
        """提交选择"""
        operator_key = self._get_operator_key()
        value = self._value_var.get()
        invert = self._invert_var.get()

        if operator_key and value:
            self._result = (operator_key, value, invert, filter_rows)
            self.grab_release()
            self.destroy()

    def _on_cancel(self):
        """取消"""
        self._result = None
        self.grab_release()
        self.destroy()

    def get_result(self) -> tuple[str, str, bool, bool] | None:
        """返回 (操作符, 值, 是否反选, 是否筛选) 或 None"""
        return self._result


class FileListWindow(tb.Toplevel):
    """文件列表独立窗口，展示搜索目录下所有 bundle 文件的信息"""

    def __init__(self, master: tk.Tk, app: "App"):
        super().__init__(master)
        self.app = app

        self._all_items: list[BundleFileInfo] = []
        self._items_by_path: dict[str, BundleFileInfo] = {}
        self._closed: bool = False

        self.ctx_list: list[tuple[str, Callable[[], None]]] = [
            (t("action.analyze"), self._ctx_analyze),
            (t("action.open_in_explorer"), self._ctx_open_in_explorer),
            (t("action.copy_filename"), self._ctx_copy_filename),
            (t("action.check_crc"), self._ctx_check_crc),
            (t("action.render_preview"), self._ctx_render_preview),
        ]

        self._setup_window()
        self._create_toolbar()
        self._create_status_bar()
        self._create_tableview()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.after(100, self._refresh)

    def _setup_window(self):
        self.title(t("ui.file_list.window_title"))
        self.geometry("1200x600")
        self.transient(self.master)

        icon_path = self.app.root_path / "assets" / "eligma.ico"
        if icon_path.exists():
            self.iconbitmap(icon_path)

    def _create_toolbar(self):
        toolbar_container = tb.Frame(self)
        toolbar_container.pack(fill=tk.X)

        row1 = tb.Frame(toolbar_container, padding=5)
        row1.pack(fill=tk.X)

        self._dir_var = tk.StringVar(value=self.app.game_resource_dir_var.get())

        dir_entry = tb.Entry(row1, textvariable=self._dir_var, width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        UIComponents.create_button(
            row1, t("action.select"),
            self._select_directory, bootstyle="primary", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        UIComponents.create_button(
            row1, t("action.refresh"),
            self._refresh, bootstyle="success", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        row2 = tb.Frame(toolbar_container, padding=5)
        row2.pack(fill=tk.X)

        tb.Label(row2, text=t("ui.file_list.analyze_label")).pack(side=tk.LEFT, padx=(0, 5))

        self._analyzer_vars: dict[str, tk.BooleanVar] = {}
        for opt in ANALYZER_OPTIONS:
            var = tk.BooleanVar(value=False)
            self._analyzer_vars[opt.key] = var
            tb.Checkbutton(
                row2, text=opt.text,
                variable=var,
            ).pack(side=tk.LEFT, padx=(0, 5))

        UIComponents.create_button(
            row2, t("action.analyze"),
            self._analyze, bootstyle="warning", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 10))

        tb.Label(row2, text=t("ui.file_list.filter_label")).pack(side=tk.LEFT, padx=(0, 5))

        self._filter_var = tk.StringVar(value="")
        filter_options = [""] + [label for key, (label, _) in FILTERS.items()]
        filter_combo = tb.Combobox(
            row2, textvariable=self._filter_var,
            values=filter_options, width=20, state="readonly",
        )
        filter_combo.pack(side=tk.LEFT, padx=(0, 5))
        filter_combo.bind("<<ComboboxSelected>>", self._apply_filter)

    def _create_tableview(self):
        coldata = [
            {"text": col.text, "width": col.width, "stretch": False}
            for col in COLUMNS
        ] + [
            {"text": "_path", "width": 0, "stretch": False, "minwidth": 0}
        ]

        colors = tb.Style().colors
        self.table = TBTableview(
            master=self,
            coldata=coldata,
            rowdata=[],
            paginated=True,
            pagesize=1000,
            searchable=True,
            yscrollbar=True,
            autoalign=True,
            autofit=False,
            bootstyle="primary",
            stripecolor=(colors.light, None),
            height=15,
            disable_right_click=False,
            iid_field="_path",
        )
        self.table.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # 替换内置滚动条为 ttkbootstrap 风格
        if hasattr(self.table, 'ybar'):
            ybar_master = self.table.ybar.master
            
            # 暂时解除 view 的 pack 布局，以便重新调整装箱顺序
            self.table.view.pack_forget()
            
            self.table.ybar.destroy()
            self.table.ybar = tb.Scrollbar(
                ybar_master, command=self.table.view.yview, orient=tk.VERTICAL,
            )
            
            # 先 pack 滚动条（抢占右侧固定宽度）
            self.table.ybar.pack(fill=tk.Y, side=tk.RIGHT)
            
            # 再重新 pack view（占满左侧剩余的全部空间）
            self.table.view.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
            
            self.table.view.configure(yscrollcommand=self.table.ybar.set)

        if hasattr(self.table, 'hbar'):
            self.table.hbar.destroy()
            self.table.hbar = tb.Scrollbar(
                self.table.hbar.master, command=self.table.view.xview, orient=tk.HORIZONTAL,
            )
            self.table.hbar.pack(fill=tk.X)
            self.table.view.configure(xscrollcommand=self.table.hbar.set)

        # 默认隐藏非默认可见列和 _path 列
        for i, col in enumerate(COLUMNS):
            if not col.default_visible:
                self.table.get_column(index=i, visible=False).hide()
        self.table.get_column(index=len(COLUMNS), visible=False).hide()

        # monkey-patch reset_column_filters 以确保 _path 列在重置过滤器后仍保持隐藏
        # "Show All" 会显示所有业务列，但不应暴露技术列 _path
        _orig_reset_column_filters = self.table.reset_column_filters
        def _patched_reset_column_filters(*args, **kwargs):
            _orig_reset_column_filters(*args, **kwargs)
            self.table.get_column(index=len(COLUMNS), visible=False).hide()
        self.table.reset_column_filters = _patched_reset_column_filters

        # 在内置右键菜单中追加应用专属操作
        cell_menu = self.table._rightclickmenu_cell
        cell_menu.add_separator()
        for label, command in self.ctx_list:
            cell_menu.add_command(label=label, command=command)

        # 在表头右键菜单中添加批量选中入口
        # 存储当前右键点击的列索引
        self._header_click_column: int | None = None

        # 绑定右键事件，在菜单弹出前捕获列索引
        self.table.view.bind("<Button-3>", self._capture_header_column, add="+")

        if hasattr(self.table, '_rightclickmenu_head'):
            head_menu = self.table._rightclickmenu_head
            head_menu.add_separator()
            head_menu.add_command(
                label=t("ui.file_list.select"),
                command=self._on_header_select
            )

    def _capture_header_column(self, event):
        """在右键菜单弹出前捕获点击的列索引"""
        region = self.table.view.identify_region(event.x, event.y)
        if region == "heading":
            column_id = self.table.view.identify_column(event.x)
            # column_id 格式为 "#1", "#2" 等，转换为索引
            if column_id:
                self._header_click_column = int(column_id.replace("#", "")) - 1

    def _on_header_select(self):
        """从表头右键菜单调用批量选中"""
        column_index = self._header_click_column

        if column_index is None or column_index >= len(COLUMNS):
            return

        col_def = COLUMNS[column_index]
        self._show_select_dialog(col_def.id, col_def.text)

    def _create_status_bar(self):
        status_frame = tb.Frame(self)
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self._progress = tb.Progressbar(
            status_frame, mode="determinate", length=200, bootstyle="primary",
        )
        self._progress.pack(side=tk.LEFT, padx=(5, 0), pady=2)

        self._status_label = tb.Label(
            status_frame, relief=tk.SUNKEN, padding=(5, 2),
            font=Theme.STATUS_BAR_FONT, bootstyle="inverse-bg",
        )
        self._status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

    # -------- 数据操作 --------

    def _select_directory(self):
        select_directory(self._dir_var, t("option.game_root_dir"), self.app.logger.log)

    def _refresh(self):
        dir_str = self._dir_var.get().strip()
        if not dir_str:
            messagebox.showwarning(t("common.warning"), t("ui.file_list.no_dirs_found"))
            return

        base_dir = Path(dir_str)
        if not base_dir.is_dir():
            messagebox.showwarning(t("common.warning"), t("ui.file_list.no_dirs_found"))
            return

        self._status_label.config(text=t("ui.file_list.scanning"))
        self._progress["value"] = 0
        self.table.delete_rows()

        def _scan():
            items = list_bundle_files(base_dir)
            if not self._closed:
                self.after(0, lambda: self._on_scan_complete(items))

        thread = threading.Thread(target=_scan, daemon=True)
        thread.start()

    def _analyze(self):
        if not self._all_items:
            return

        analyzer_names = [
            key for key, var in self._analyzer_vars.items() if var.get()
        ]
        if not analyzer_names:
            messagebox.showinfo(t("action.analyze"), t("ui.file_list.no_analyzer_selected"))
            return

        self._status_label.config(text=t("ui.file_list.analyzing"))
        self._progress["value"] = 0

        def _on_progress(done: int, total: int, filename: str):
            if self._closed:
                return
            self.after(0, lambda: self._update_progress(done, total, filename))

        def _run():
            analyze_bundles(self._all_items, analyzer_names, progress_callback=_on_progress)
            if not self._closed:
                self.after(0, self._on_analyze_complete)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _update_progress(self, done: int, total: int, filename: str):
        if self._closed:
            return
        if total > 0:
            self._progress["value"] = done / total * 100
        self._status_label.config(
            text=t("ui.file_list.analyzing_progress", done=done, total=total, filename=filename)
        )

    def _build_row_values(self, item: BundleFileInfo) -> list:
        trailing_display = (
            str(item.trailing_bytes) if item.trailing_bytes is not None else _UNSET
        )
        trailing_content_display = (
            _format_hex(item.trailing_content) if item.trailing_content is not None else _UNSET
        )
        core_display = item.parsed_name.core if item.parsed_name else _UNSET
        res_type_display = item.parsed_name.res_type if item.parsed_name and item.parsed_name.res_type else _UNSET
        crc_display = (
            f"{int(item.parsed_name.crc):08X}" if item.parsed_name and item.parsed_name.crc else _UNSET
        )
        crc_actual_display = (
            f"{item.crc_actual:08X}" if item.crc_actual is not None else _UNSET
        )

        parent_dir = item.path.parent
        display_dir = parent_dir.parent if parent_dir.name in ["Windows", "Android"] else parent_dir

        return [
            item.path.name,
            display_dir.name,
            _format_file_size(item.file_size),
            _format_time(item.modified_time),
            trailing_display,
            trailing_content_display,
            core_display,
            res_type_display,
            crc_display,
            crc_actual_display,
            str(item.path),
        ]

    def _on_scan_complete(self, items: list[BundleFileInfo]):
        if self._closed:
            return
        self._progress["value"] = 0
        self._status_label.config(text=t("ui.file_list.scan_complete"))
        self._all_items = items
        self._items_by_path = {str(item.path): item for item in items}

        rowdata = [self._build_row_values(item) for item in items]
        self.table.delete_rows()
        if rowdata:
            self.table.insert_rows('end', rowdata)
            self.table.goto_first_page()

        self.app.logger.log(t("ui.file_list.scan_complete"))

    def _on_analyze_complete(self):
        if self._closed:
            return
        self._progress["value"] = 0
        self._status_label.config(text=t("ui.file_list.analyze_complete"))
        for row in self.table.tablerows:
            path = row.values[ColumnId._path.value]
            item = self._items_by_path.get(path)
            if item:
                row.values = self._build_row_values(item)

        for analyzer_key in self._analyzer_vars:
            if self._analyzer_vars[analyzer_key].get():
                for col_id in ANALYZER_TO_COLUMNS.get(analyzer_key, []):
                    self.table.get_column(index=col_id.value, visible=False).show()

        self.app.logger.log(t("ui.file_list.analyze_complete"))

    def _apply_filter(self, event=None):
        selected_label = self._filter_var.get()
        if not selected_label:
            self.table.reset_row_filters()
            return

        filter_func = None
        for key, (label, func) in FILTERS.items():
            if label == selected_label:
                filter_func = func
                break

        if filter_func is None:
            return

        self.table._filtered = True
        self.table.tablerows_filtered.clear()
        self.table.unload_table_data()

        for row in self.table.tablerows:
            path = row.values[ColumnId._path.value]
            item = self._items_by_path.get(path)
            if item and not filter_func(item):
                self.table.tablerows_filtered.append(row)

        self.table._rowindex.set(0)
        self.table.load_table_data()

    def _show_select_dialog(self, column_id: ColumnId, column_name: str):
        """显示批量选中对话框"""
        dialog = BatchSelectDialog(self, column_id, column_name)
        self.wait_window(dialog)

        result = dialog.get_result()
        if result is None:
            return

        operator, value, invert, do_filter = result

        # 执行批量选中
        self._apply_select(column_id, operator, value, invert, do_filter)

    def _apply_select(self, column_id: ColumnId, operator: str, value: str, invert: bool, do_filter: bool):
        """根据条件批量选中行"""
        matched_iids = []
        all_iids = []

        # 只处理当前可见的行（分页模式下其他行被 detach）
        for row in self.table.tablerows_visible:
            iid = row.iid
            all_iids.append(iid)
            cell_value = str(row.values[column_id.value])
            if self._match_condition(cell_value, operator, value):
                matched_iids.append(iid)

        # 如果反选，选中不匹配的行
        if invert:
            selected_iids = [iid for iid in all_iids if iid not in matched_iids]
        else:
            selected_iids = matched_iids

        if selected_iids:
            self.table.view.selection_set(selected_iids)
            if do_filter:
                self.table.filter_to_selected_rows()
            self._status_label.config(text=t("ui.file_list.select.matched", count=len(selected_iids)))
        else:
            messagebox.showinfo(t("common.tip"), t("ui.file_list.select.no_match"))

    def _match_condition(self, cell_value: str, operator: str, pattern: str) -> bool:
        """判断单元格值是否匹配条件"""
        if operator == "contains":
            return pattern.lower() in cell_value.lower()
        elif operator == "equals":
            return cell_value == pattern
        elif operator == "starts_with":
            return cell_value.lower().startswith(pattern.lower())
        elif operator == "ends_with":
            return cell_value.lower().endswith(pattern.lower())
        elif operator == "regex":
            try:
                return re.search(pattern, cell_value) is not None
            except re.error:
                return False
        return False

    # -------- 右键菜单操作 --------

    def _get_selected_items(self) -> list[BundleFileInfo]:
        selected_iids = self.table.view.selection()
        return [
            self._items_by_path[iid]
            for iid in selected_iids
            if iid in self._items_by_path
        ]

    def _ctx_open_in_explorer(self):
        items = self._get_selected_items()
        for item in items:
            open_directory(item.path.parent, self.app.logger.log)

    def _ctx_copy_filename(self):
        items = self._get_selected_items()
        if items:
            text = "\n".join(item.path.name for item in items)
            self.clipboard_clear()
            self.clipboard_append(text)

    def _ctx_analyze(self):
        items = self._get_selected_items()
        if not items:
            return

        self._status_label.config(text=t("ui.file_list.analyzing"))
        self._progress["value"] = 0

        def _on_progress(done: int, total: int, filename: str):
            if self._closed:
                return
            self.after(0, lambda: self._update_progress(done, total, filename))

        def _run():
            analyze_bundles(items, ["trailing", "naming", "crc"], progress_callback=_on_progress)
            if not self._closed:
                self.after(0, self._ctx_analyze_complete)

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _ctx_analyze_complete(self):
        if self._closed:
            return
        self._progress["value"] = 0
        self._status_label.config(text=t("ui.file_list.analyze_complete"))

        for item in self._get_selected_items():
            row = self.table.get_row(iid=str(item.path))
            if row:
                row.values = self._build_row_values(item)

        for col_id in ANALYZER_TO_COLUMNS.get("trailing", []) + ANALYZER_TO_COLUMNS.get("naming", []) + ANALYZER_TO_COLUMNS.get("crc", []):
            self.table.get_column(index=col_id.value, visible=False).show()

        self.app.logger.log(t("ui.file_list.analyze_complete"))

    def _ctx_check_crc(self):
        items = self._get_selected_items()
        if not items:
            return

        results = []
        for item in items:
            try:
                if item.parsed_name is None:
                    item.parsed_name = parse_filename(item.path.name)

                if item.crc_actual is None:
                    item.crc_actual = CRCUtils.compute_crc32(item.path)

                row = self.table.get_row(iid=str(item.path))
                if row:
                    row.values = self._build_row_values(item)

                actual_str = f"{item.crc_actual:08X}"
                expected_crc = item.parsed_name.crc if item.parsed_name else ""
                if expected_crc:
                    expected_int = int(expected_crc)
                    expected_str = f"{expected_int:08X}"
                    if item.crc_actual == expected_int:
                        results.append(t("ui.file_list.crc_match", expected=expected_str, actual=actual_str))
                    else:
                        results.append(t("ui.file_list.crc_mismatch", expected=expected_str, actual=actual_str))
                else:
                    results.append(t("ui.file_list.crc_no_filename_crc", actual=actual_str))
            except Exception as e:
                results.append(f"{item.path.name}: {t('common.error')} - {e}")

        for col_id in ANALYZER_TO_COLUMNS.get("crc", []):
            self.table.get_column(index=col_id.value, visible=False).show()

        messagebox.showinfo(t("action.check_crc"), "\n\n".join(results))

    def _ctx_render_preview(self):
        """渲染选中 bundle 文件的 Spine 预览图"""
        items = self._get_selected_items()
        if not items:
            return

        # 检查 SpineViewerCLI 路径
        viewer_path_str = self.app.spine_viewer_path_var.get().strip()
        if not viewer_path_str:
            messagebox.showwarning(
                t("common.warning"),
                t("message.3rd_party.spine_viewer_required")
            )
            return

        viewer_path = Path(viewer_path_str)
        if not viewer_path.exists():
            messagebox.showwarning(
                t("common.warning"),
                t("log.file.not_exist", path=viewer_path)
            )
            return

        # 获取输出目录
        output_dir_str = self.app.output_dir_var.get().strip()
        if not output_dir_str:
            messagebox.showwarning(
                t("common.warning"),
                t("message.output_dir_not_set")
            )
            return

        output_dir = Path(output_dir_str)

        # 准备 bundle 路径列表
        bundle_paths = [item.path for item in items]

        self._status_label.config(text=t("status.processing"))
        self._progress["value"] = 0

        def _run():
            success, message = render_spine_preview_from_bundle(
                bundle_path=bundle_paths,
                output_dir=output_dir,
                viewer_path=viewer_path,
                log=self.app.logger.log
            )
            if not self._closed:
                self.after(0, lambda: self._on_render_preview_complete(success, message))

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    def _on_render_preview_complete(self, success: bool, message: str):
        """渲染预览图完成"""
        if self._closed:
            return

        self._progress["value"] = 0
        self._status_label.config(text=t("status.done") if success else t("status.failed"))

        if success:
            messagebox.showinfo(t("action.render_preview"), message)
        else:
            messagebox.showerror(t("common.error"), message)

    # -------- 生命周期 --------

    def _on_close(self):
        self._closed = True
        if hasattr(self.app, '_file_list_window'):
            self.app._file_list_window = None
        self.destroy()
