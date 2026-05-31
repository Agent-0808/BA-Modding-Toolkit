# gui/windows/file_list_window.py

import tkinter as tk
from tkinter import messagebox
import threading
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple
from enum import Enum

import ttkbootstrap as tb

from ...i18n import t
from ...utils import CRCUtils
from ...naming import parse_filename
from ...searching import list_bundle_files
from ...bundle import analyze_bundles, BUNDLE_ANALYZERS
from ...models import BundleFileInfo
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
    """TreeView 列 ID"""
    filename = "filename"
    directory = "directory"
    file_size = "file_size"
    modified_time = "modified_time"
    trailing_bytes = "trailing_bytes"
    trailing_content = "trailing_content"
    core = "core"
    res_type = "res_type"
    crc = "crc"
    crc_actual = "crc_actual"


class ColumnDef(NamedTuple):
    """TreeView 列定义"""
    id: ColumnId
    text: str
    width: int


class AnalyzerOption(NamedTuple):
    """分析器选项定义"""
    key: str
    text: str


COLUMNS: list[ColumnDef] = [
    ColumnDef(ColumnId.filename, t("ui.file_list.column_filename"), 300),
    ColumnDef(ColumnId.directory, t("ui.file_list.column_directory"), 80),
    ColumnDef(ColumnId.file_size, t("ui.file_list.column_file_size"), 40),
    ColumnDef(ColumnId.modified_time, t("ui.file_list.column_modified_time"), 80),
    ColumnDef(ColumnId.trailing_bytes, t("ui.file_list.column_trailing_bytes"), 20),
    ColumnDef(ColumnId.trailing_content, t("ui.file_list.column_trailing_content"), 80),
    ColumnDef(ColumnId.core, t("ui.file_list.column_core"), 150),
    ColumnDef(ColumnId.res_type, t("ui.file_list.column_res_type"), 40),
    ColumnDef(ColumnId.crc, t("ui.file_list.column_crc"), 60),
    ColumnDef(ColumnId.crc_actual, t("ui.file_list.column_crc_actual"), 60),
]

ANALYZER_OPTIONS: list[AnalyzerOption] = [
    AnalyzerOption("trailing", t("ui.file_list.analyze_trailing")),
    AnalyzerOption("naming", t("ui.file_list.analyze_naming")),
    AnalyzerOption("crc", t("ui.file_list.analyze_crc")),
]


def _get_sort_key(item: BundleFileInfo, column: ColumnId):
    """获取排序 key"""
    if column == ColumnId.filename:
        return item.path.name.lower()
    if column == ColumnId.directory:
        return item.path.parent.name.lower()
    if column == ColumnId.file_size:
        return item.file_size
    if column == ColumnId.modified_time:
        return item.modified_time
    if column == ColumnId.trailing_bytes:
        return item.trailing_bytes if item.trailing_bytes is not None else -1
    if column == ColumnId.trailing_content:
        return _format_hex(item.trailing_content) if item.trailing_content else ""
    if column == ColumnId.core:
        return item.parsed_name.core.lower() if item.parsed_name else ""
    if column == ColumnId.res_type:
        return item.parsed_name.res_type.lower() if item.parsed_name and item.parsed_name.res_type else ""
    if column == ColumnId.crc:
        return int(item.parsed_name.crc) if item.parsed_name and item.parsed_name.crc else -1
    if column == ColumnId.crc_actual:
        return item.crc_actual if item.crc_actual is not None else -1
    return ""


class FileListWindow(tb.Toplevel):
    """文件列表独立窗口，展示搜索目录下所有 bundle 文件的信息"""

    def __init__(self, master: tk.Tk, app: "App"):
        super().__init__(master)
        self.app = app

        self._all_items: list[BundleFileInfo] = []
        self._sort_column: ColumnId | None = None
        self._sort_reverse: bool = False
        self._closed: bool = False

        self._setup_window()
        self._create_toolbar()
        self._create_treeview()
        self._create_status_bar()
        self._create_context_menu()

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
        toolbar = tb.Frame(self, padding=5)
        toolbar.pack(fill=tk.X)

        self._dir_var = tk.StringVar(value=self.app.game_resource_dir_var.get())

        dir_entry = tb.Entry(toolbar, textvariable=self._dir_var, width=50)
        dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        UIComponents.create_button(
            toolbar, t("action.select"),
            self._select_directory, bootstyle="primary", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        UIComponents.create_button(
            toolbar, t("action.refresh"),
            self._refresh, bootstyle="success", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        tb.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self._analyzer_vars: dict[str, tk.BooleanVar] = {}
        for opt in ANALYZER_OPTIONS:
            var = tk.BooleanVar(value=False)
            self._analyzer_vars[opt.key] = var
            tb.Checkbutton(
                toolbar, text=opt.text,
                variable=var,
            ).pack(side=tk.LEFT, padx=(0, 5))

        UIComponents.create_button(
            toolbar, t("action.analyze"),
            self._analyze, bootstyle="warning", style="compact"
        ).pack(side=tk.LEFT, padx=(0, 5))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = tb.Entry(toolbar, textvariable=self._search_var, width=20)
        search_entry.pack(side=tk.RIGHT, padx=(5, 0))
        tb.Label(toolbar, text=t("action.filter")).pack(side=tk.RIGHT)

    def _create_treeview(self):
        tree_frame = tb.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        col_ids = [col.id.value for col in COLUMNS]

        self.tree = tb.Treeview(
            tree_frame,
            columns=col_ids,
            show="headings",
            selectmode="extended",
            bootstyle="primary",
        )

        for col in COLUMNS:
            self.tree.heading(
                col.id.value,
                text=col.text,
                command=lambda c=col.id: self._sort_by(c),
            )
            self.tree.column(col.id.value, width=col.width, minwidth=20)

        vsb = tb.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = tb.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<Button-3>", self._show_context_menu)

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

    def _create_context_menu(self):
        self._context_menu = tk.Menu(self, tearoff=0)
        self._context_menu.add_command(
            label=t("action.open_in_explorer"),
            command=self._ctx_open_in_explorer,
        )
        self._context_menu.add_command(
            label=t("action.copy_filename"),
            command=self._ctx_copy_filename,
        )
        self._context_menu.add_separator()
        self._context_menu.add_command(
            label=t("action.check_crc"),
            command=self._ctx_check_crc,
        )

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
        self.tree.delete(*self.tree.get_children())

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

    def _on_scan_complete(self, items: list[BundleFileInfo]):
        if self._closed:
            return
        self._progress["value"] = 0
        self._all_items = items
        self._apply_filter()
        self.app.logger.log(t("ui.file_list.scan_complete"))

    def _on_analyze_complete(self):
        if self._closed:
            return
        self._progress["value"] = 0
        self._apply_filter()
        self.app.logger.log(t("ui.file_list.analyze_complete"))

    def _apply_filter(self):
        if self._closed:
            return
        self.tree.delete(*self.tree.get_children())

        search_text = self._search_var.get().strip().lower()

        filtered = self._all_items
        if search_text:
            filtered = [
                item for item in filtered
                if search_text in item.path.name.lower()
            ]

        if self._sort_column:
            filtered = self._sort_items(filtered, self._sort_column, self._sort_reverse)

        for idx, item in enumerate(filtered):
            self._insert_tree_item(idx, item)

        total = len(self._all_items)
        self._status_label.config(
            text=t("ui.file_list.status_summary", total=total)
        )

    def _insert_tree_item(self, idx: int, item: BundleFileInfo):
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

        values = (
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
        )
        self.tree.insert("", tk.END, iid=str(idx), values=values)

    # -------- 排序 --------

    def _sort_by(self, column: ColumnId):
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._apply_filter()

    def _sort_items(self, items: list[BundleFileInfo], column: ColumnId, reverse: bool) -> list[BundleFileInfo]:
        return sorted(items, key=lambda i: _get_sort_key(i, column), reverse=reverse)

    # -------- 右键菜单 --------

    def _show_context_menu(self, event: tk.Event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        self._context_menu.post(event.x_root, event.y_root)

    def _get_selected_items(self) -> list[BundleFileInfo]:
        search_text = self._search_var.get().strip().lower()

        filtered = self._all_items
        if search_text:
            filtered = [
                item for item in filtered
                if search_text in item.path.name.lower()
            ]

        if self._sort_column:
            filtered = self._sort_items(filtered, self._sort_column, self._sort_reverse)

        selected = []
        for item_id in self.tree.selection():
            idx = int(item_id)
            if 0 <= idx < len(filtered):
                selected.append(filtered[idx])
        return selected

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

    def _ctx_check_crc(self):
        items = self._get_selected_items()
        if not items:
            return

        results = []
        for item in items:
            try:
                actual_crc = item.crc_actual
                if actual_crc is None:
                    actual_crc = CRCUtils.compute_crc32(item.path)
                actual_str = f"{actual_crc:08X}"

                expected_crc = item.parsed_name.crc if item.parsed_name else ""
                if expected_crc:
                    expected_int = int(expected_crc)
                    expected_str = f"{expected_int:08X}"
                    if actual_crc == expected_int:
                        results.append(t("ui.file_list.crc_match", expected=expected_str, actual=actual_str))
                    else:
                        results.append(t("ui.file_list.crc_mismatch", expected=expected_str, actual=actual_str))
                else:
                    results.append(t("ui.file_list.crc_no_filename_crc", actual=actual_str))
            except Exception as e:
                results.append(f"{item.path.name}: {t('common.error')} - {e}")

        messagebox.showinfo(t("action.check_crc"), "\n\n".join(results))

    # -------- 生命周期 --------

    def _on_close(self):
        self._closed = True
        if hasattr(self.app, '_file_list_window'):
            self.app._file_list_window = None
        self.destroy()
