# gui/windows/file_list_window.py

import tkinter as tk
from tkinter import messagebox
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import ttkbootstrap as tb

from ...i18n import t
from ...utils import CRCUtils
from ...naming import parse_filename
from ...searching import scan_bundle_files
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


class FileListWindow(tb.Toplevel):
    """文件列表独立窗口，展示搜索目录下所有 bundle 文件的信息"""

    COLUMNS = [
        {"id": "filename", "text_key": "ui.file_list.column_filename", "width": 300},
        {"id": "directory", "text_key": "ui.file_list.column_directory", "width": 120},
        {"id": "file_size", "text_key": "ui.file_list.column_file_size", "width": 80},
        {"id": "trailing_bytes", "text_key": "ui.file_list.column_trailing_bytes", "width": 80},
        {"id": "trailing_content", "text_key": "ui.file_list.column_trailing_content", "width": 200},
    ]

    def __init__(self, master: tk.Tk, app: "App"):
        super().__init__(master)
        self.app = app

        self._all_items: list[BundleFileInfo] = []
        self._sort_column: str = ""
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
        self.geometry("900x600")
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

        self._show_zero_var = tk.BooleanVar(value=False)
        tb.Checkbutton(
            toolbar,
            text=t("ui.file_list.show_zero_trailing"),
            variable=self._show_zero_var,
            command=self._apply_filter,
        ).pack(side=tk.LEFT, padx=(10, 5))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        search_entry = tb.Entry(toolbar, textvariable=self._search_var, width=20)
        search_entry.pack(side=tk.RIGHT, padx=(5, 0))
        tb.Label(toolbar, text=t("action.filter")).pack(side=tk.RIGHT)

    def _create_treeview(self):
        tree_frame = tb.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        col_ids = [col["id"] for col in self.COLUMNS]

        self.tree = tb.Treeview(
            tree_frame,
            columns=col_ids,
            show="headings",
            selectmode="extended",
            bootstyle="primary",
        )

        for col in self.COLUMNS:
            self.tree.heading(
                col["id"],
                text=t(col["text_key"]),
                command=lambda c=col["id"]: self._sort_by(c),
            )
            self.tree.column(col["id"], width=col["width"], minwidth=50)

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
        self._status_label = tb.Label(
            self, relief=tk.SUNKEN, padding=(5, 2),
            font=Theme.STATUS_BAR_FONT, bootstyle="inverse-bg",
        )
        self._status_label.pack(fill=tk.X, side=tk.BOTTOM)

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
        self.tree.delete(*self.tree.get_children())

        def _scan():
            items = scan_bundle_files(base_dir, self.app.logger.log)
            if not self._closed:
                self.after(0, lambda: self._on_scan_complete(items))

        thread = threading.Thread(target=_scan, daemon=True)
        thread.start()

    def _on_scan_complete(self, items: list[BundleFileInfo]):
        if self._closed:
            return
        self._all_items = items
        self._apply_filter()
        self.app.logger.log(t("ui.file_list.scan_complete"))

    def _apply_filter(self):
        if self._closed:
            return
        self.tree.delete(*self.tree.get_children())

        show_zero = self._show_zero_var.get()
        search_text = self._search_var.get().strip().lower()

        filtered = self._all_items
        if not show_zero:
            filtered = [
                item for item in filtered
                if item.trailing_bytes is None or item.trailing_bytes > 0
            ]
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
        trailing = sum(
            1 for item in self._all_items
            if item.trailing_bytes is not None and item.trailing_bytes > 0
        )
        self._status_label.config(
            text=t("ui.file_list.status_summary", total=total, trailing=trailing)
        )

    def _insert_tree_item(self, idx: int, item: BundleFileInfo):
        trailing_display = str(item.trailing_bytes) if item.trailing_bytes is not None else t("common.unknown")
        parent_dir = item.path.parent.name

        values = (
            item.path.name,
            parent_dir,
            _format_file_size(item.file_size),
            trailing_display,
            _format_hex(item.trailing_content),
        )
        self.tree.insert("", tk.END, iid=str(idx), values=values)

    # -------- 排序 --------

    def _sort_by(self, column: str):
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = False
        self._apply_filter()

    def _sort_items(self, items: list[BundleFileInfo], column: str, reverse: bool) -> list[BundleFileInfo]:
        key_map = {
            "filename": lambda i: i.path.name.lower(),
            "directory": lambda i: i.path.parent.name.lower(),
            "file_size": lambda i: i.file_size,
            "trailing_bytes": lambda i: i.trailing_bytes or 0,
            "trailing_content": lambda i: _format_hex(i.trailing_content),
        }
        key_func = key_map.get(column, lambda i: "")
        return sorted(items, key=key_func, reverse=reverse)

    # -------- 右键菜单 --------

    def _show_context_menu(self, event: tk.Event):
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
        self.tree.selection_set(item_id)
        self._context_menu.post(event.x_root, event.y_root)

    def _get_selected_items(self) -> list[BundleFileInfo]:
        show_zero = self._show_zero_var.get()
        search_text = self._search_var.get().strip().lower()

        filtered = self._all_items
        if not show_zero:
            filtered = [
                item for item in filtered
                if item.trailing_bytes is None or item.trailing_bytes > 0
            ]
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
                actual_crc = CRCUtils.compute_crc32(item.path)
                actual_str = f"{actual_crc:08X}"

                if item.crc_expected:
                    expected_int = int(item.crc_expected)
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
