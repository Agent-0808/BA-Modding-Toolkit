# gui/windows/adb_browser.py
"""ADB 远程文件浏览器对话框"""

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...adb.file_source import ADBFileSource

from ...i18n import t
from ...utils import no_log
from ..components import Theme, UIComponents


class ADBFileBrowser(tb.Toplevel):
    """ADB 远程文件浏览器对话框

    用于在 ADB 模式下浏览设备文件并选择 bundle 文件。
    基于索引 + GUI 的文件选择器，替代 tkinter 原生文件对话框。
    """

    def __init__(self, master, adb_source: "ADBFileSource",
                 title: str = "", file_types: list[str] | None = None,
                 multiple: bool = True, log=no_log, directory_mode: bool = False):
        super().__init__(master)
        self.withdraw()  # 先隐藏窗口，避免空白闪烁
        self.adb_source = adb_source
        self.file_types = file_types or [".bundle"]
        self.multiple = multiple
        self.log = log
        self.directory_mode = directory_mode  # 目录选择模式
        self.selected_paths: list[str] = []  # 选中的远程路径
        self._current_dir: str = ""
        self._navigation_stack: list[str] = []  # 导航历史
        self._all_items: list[str] = []  # 所有树项的 iid（含被 detach 的）

        self._setup_window(title)
        self._create_widgets()

        # 导航到基础路径（覆盖所有搜索目录的父级）
        base_path = adb_source.get_base_path()
        if base_path:
            self._navigate(base_path)
        else:
            search_dirs = adb_source.get_search_dirs()
            if search_dirs:
                self._navigate(search_dirs[0])

        # 显示窗口
        self.deiconify()

        # 模态
        self.transient(master)
        self.grab_set()
        self.wait_window(self)

    def _setup_window(self, title: str):
        """设置窗口属性"""
        if not title:
            title = t("adb.browser.title_dir") if self.directory_mode else t("adb.browser.title")
        self.title(title)
        self.geometry("800x550")
        self.resizable(True, True)

        # 居中
        self.update_idletasks()
        parent_x = self.master.winfo_rootx()
        parent_y = self.master.winfo_rooty()
        parent_w = self.master.winfo_width()
        parent_h = self.master.winfo_height()
        x = parent_x + (parent_w - 800) // 2
        y = parent_y + (parent_h - 550) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """创建界面组件"""
        # 顶部导航栏
        nav_frame = tb.Frame(self, padding=(10, 5))
        nav_frame.pack(fill=tk.X)

        self._back_btn = UIComponents.create_button(
            nav_frame, text="←", command=self._go_back,
            bootstyle="secondary", style="compact", width=3
        )
        self._back_btn.pack(side=tk.LEFT, padx=(0, 5))

        self._path_var = tk.StringVar()
        self._path_entry = tb.Entry(nav_frame, textvariable=self._path_var,
                                     font=Theme.INPUT_FONT, state="readonly")
        self._path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))

        UIComponents.create_button(
            nav_frame, text=t("adb.browser.refresh"), command=self._refresh,
            bootstyle="secondary", style="compact"
        ).pack(side=tk.RIGHT)

        # 过滤栏
        filter_frame = tb.Frame(self, padding=(10, 0))
        filter_frame.pack(fill=tk.X)

        tb.Label(filter_frame, text="🔍", font=Theme.INPUT_FONT).pack(side=tk.LEFT)
        self._filter_var = tk.StringVar()
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())
        filter_entry = tb.Entry(filter_frame, textvariable=self._filter_var,
                                 font=Theme.INPUT_FONT)
        filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))

        # 文件列表
        list_frame = tb.Frame(self, padding=(10, 5))
        list_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "size", "modified")
        self._tree = tb.Treeview(
            list_frame,
            columns=columns,
            show="headings",
            selectmode="extended" if self.multiple else "browse",
            bootstyle="default"
        )

        self._tree.heading("name", text=t("ui.column.filename"))
        self._tree.heading("size", text=t("ui.column.file_size"))
        self._tree.heading("modified", text=t("ui.column.modified_time"))

        self._tree.column("name", width=400, minwidth=200)
        self._tree.column("size", width=100, minwidth=80, anchor=tk.E)
        self._tree.column("modified", width=150, minwidth=100)

        v_scroll = tb.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=v_scroll.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 双击进入目录或选中文件
        self._tree.bind("<Double-1>", self._on_double_click)

        # 状态栏
        self._status_label = tb.Label(self, text="", font=Theme.INPUT_FONT,
                                       bootstyle="secondary")
        self._status_label.pack(fill=tk.X, padx=10, pady=(0, 5))

        # 底部按钮
        btn_frame = tb.Frame(self, padding=(10, 10))
        btn_frame.pack(fill=tk.X)

        UIComponents.create_button(
            btn_frame, text=t("common.cancel"), command=self._on_cancel,
            bootstyle="secondary"
        ).pack(side=tk.RIGHT, padx=(5, 0))

        UIComponents.create_button(
            btn_frame, text=t("adb.browser.select"), command=self._on_confirm,
            bootstyle="success"
        ).pack(side=tk.RIGHT)

    def _navigate(self, remote_dir: str):
        """导航到指定远程目录"""
        self._current_dir = remote_dir
        self._path_var.set(remote_dir)
        self._status_label.config(text=t("adb.browser.loading"))

        # 删除所有项（包括被 detach 的，get_children 不会返回它们）
        for item_id in self._all_items:
            try:
                self._tree.delete(item_id)
            except tk.TclError:
                pass
        self._all_items = []

        # 清空过滤（会触发 _apply_filter，但此时 _all_items 为空，无副作用）
        self._filter_var.set("")

        try:
            files = self.adb_source.file_index.list_files(remote_dir, log=self.log)
        except Exception as e:
            self._status_label.config(text=t("adb.browser.error", error=e))
            return

        # 排序：目录在前，文件在后
        dirs = sorted([f for f in files if f.is_dir], key=lambda f: f.name)
        files_only = sorted([f for f in files if not f.is_dir], key=lambda f: f.name)

        for d in dirs:
            self._tree.insert("", tk.END, iid=d.path,
                              values=(f"📁 {d.name}", "", ""),
                              tags=("dir",))
            self._all_items.append(d.path)

        for f in files_only:
            size_str = self._format_size(f.size)
            mtime_str = self._format_time(f.modified_time)
            self._tree.insert("", tk.END, iid=f.path,
                              values=(f.name, size_str, mtime_str),
                              tags=("file",))
            self._all_items.append(f.path)

        total = len(dirs) + len(files_only)
        self._status_label.config(text=t("adb.index.found", count=total))

    def _go_back(self):
        """返回上级目录"""
        if self._navigation_stack:
            prev_dir = self._navigation_stack.pop()
            self._navigate(prev_dir)
        elif self._current_dir:
            # 返回上级
            parent = "/".join(self._current_dir.rstrip("/").split("/")[:-1])
            if parent:
                self._navigation_stack.append(self._current_dir)
                self._navigate(parent)

    def _refresh(self):
        """刷新当前目录"""
        self.adb_source.file_index.invalidate(self._current_dir)
        self._navigate(self._current_dir)

    def _on_double_click(self, event):
        """双击事件"""
        selection = self._tree.selection()
        if not selection:
            return

        item_id = selection[0]
        tags = self._tree.item(item_id, "tags")

        if "dir" in tags:
            # 进入子目录
            self._navigation_stack.append(self._current_dir)
            self._navigate(item_id)
        elif not self.directory_mode:
            # 选中文件并确认（目录模式下双击文件不做任何操作）
            self._on_confirm()

    def _apply_filter(self):
        """根据过滤文本筛选显示"""
        filter_text = self._filter_var.get().lower()
        # 遍历所有项（含被 detach 的），否则一旦 detach 就再也无法 re-attach
        for item_id in self._all_items:
            try:
                values = self._tree.item(item_id, "values")
            except tk.TclError:
                continue
            name = values[0] if values else ""
            # 去掉目录图标前缀
            display_name = name.replace("📁 ", "")
            if filter_text and filter_text not in display_name.lower():
                self._tree.detach(item_id)
            else:
                self._tree.move(item_id, "", tk.END)

    def _on_confirm(self):
        """确认选择"""
        # 目录模式：直接选择当前所在目录
        if self.directory_mode:
            if not self._current_dir:
                return
            self.selected_paths = [self._current_dir]
            self.destroy()
            return

        selection = self._tree.selection()
        if not selection:
            messagebox.showinfo(t("common.tip"), t("message.no_file_selected"), parent=self)
            return

        for item_id in selection:
            tags = self._tree.item(item_id, "tags")
            if "dir" in tags:
                continue  # 跳过目录
            self.selected_paths.append(item_id)

        if not self.selected_paths:
            messagebox.showinfo(t("common.tip"), t("message.no_file_selected"), parent=self)
            return

        self.destroy()

    def _on_cancel(self):
        """取消选择"""
        self.selected_paths = []
        self.destroy()

    @staticmethod
    def _format_size(size: int) -> str:
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    @staticmethod
    def _format_time(mtime: float) -> str:
        if mtime <= 0:
            return ""
        from datetime import datetime
        try:
            dt = datetime.fromtimestamp(mtime)
            return dt.strftime("%Y-%m-%d %H:%M")
        except (OSError, ValueError):
            return ""
