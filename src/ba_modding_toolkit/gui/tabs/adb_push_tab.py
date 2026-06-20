# gui/tabs/adb_push_tab.py
"""ADB 文件推送 Tab — 将本地文件推送到 Android 设备指定目录"""

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ...adb.paths import get_adb_base_path
from ..base_tab import TabFrame
from ..components import FileListbox, UIComponents


class AdbPushTab(TabFrame):
    """ADB 文件推送页面"""

    def create_widgets(self):
        # 本地文件列表（支持拖放，允许任意文件类型）
        self._file_list: list[Path] = []
        self.file_listbox = FileListbox(
            self,
            title=t("ui.adb_push.local_files"),
            file_list=self._file_list,
            placeholder_text=t("ui.adb_push.placeholder_local"),
            height=10,
            logger=self.logger,
            allowed_suffixes=set(),  # 空集合 = 允许所有文件
        )
        self.file_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        # 目标目录选择
        target_frame = tb.Labelframe(self, text=t("ui.adb_push.target_dir"), padding=(15, 10))
        target_frame.pack(fill=tk.X, pady=(0, 5))

        dir_row = tb.Frame(target_frame)
        dir_row.pack(fill=tk.X)
        dir_row.grid_columnconfigure(0, weight=1)

        self.target_dir_var = tk.StringVar()
        # 预填充区服基础路径
        region = self.app.adb_server_region_var.get()
        base = get_adb_base_path(region)
        if base:
            self.target_dir_var.set(base)

        self.target_entry = UIComponents.create_textbox_entry(
            dir_row, textvariable=self.target_dir_var
        )
        self.target_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        UIComponents.create_button(
            dir_row, t("action.browse"), self._browse_target_dir,
            bootstyle="primary", style="short"
        ).grid(row=0, column=1)

        # 操作按钮
        action_frame = tb.Frame(self)
        action_frame.pack(fill=tk.X, pady=10)
        action_frame.grid_columnconfigure(0, weight=1)

        self.push_button = UIComponents.create_button(
            action_frame, t("ui.adb_push.push"), self._on_push,
            bootstyle="success", style="large"
        )
        self.push_button.grid(row=0, column=0, sticky="ew", padx=5)

    def _browse_target_dir(self):
        """打开 ADB 文件浏览器选择目标目录"""
        if not self.app.is_adb_available():
            messagebox.showerror(t("common.error"), t("adb.device_none"))
            return

        from ..windows.adb_browser import ADBFileBrowser
        adb_source = self.app.get_adb_file_source()
        browser = ADBFileBrowser(
            self.winfo_toplevel(),
            adb_source=adb_source,
            directory_mode=True,
            log=self.logger.log,
        )
        if browser.selected_paths:
            self.target_dir_var.set(browser.selected_paths[0])

    def _on_push(self):
        """推送按钮回调：校验后在线程中执行推送"""
        if not self.app.is_adb_available():
            messagebox.showerror(t("common.error"), t("adb.device_none"))
            return

        files = list(self._file_list)
        if not files:
            messagebox.showwarning(t("common.warning"), t("ui.adb_push.no_local_files"))
            return

        target_dir = self.target_dir_var.get().strip().rstrip("/")
        if not target_dir:
            messagebox.showwarning(t("common.warning"), t("ui.adb_push.no_target_dir"))
            return

        # 确认对话框
        file_names = "\n".join(f.name for f in files)
        confirm_msg = t("adb.push.confirm", files=file_names)
        if not messagebox.askyesno(t("common.tip"), confirm_msg):
            return

        self.push_button.config(state=tk.DISABLED)
        self.run_in_thread(self._push_files, files, target_dir)

    def _push_files(self, files: list[Path], target_dir: str):
        """在后台线程中逐个推送文件"""
        self.logger.log("\n" + "=" * 50)
        self.logger.log(t("ui.adb_push.push_start", dir=target_dir, count=len(files)))
        self.logger.status(t("common.processing"))

        adb_source = self.app.get_adb_file_source()
        success_count = 0
        fail_count = 0

        for f in files:
            remote_path = f"{target_dir}/{f.name}"
            self.logger.log(t("adb.push.start", name=f.name))
            try:
                ok = adb_source.push_file(f, remote_path, log=self.logger.log)
            except Exception as e:
                self.logger.log(t("log.adb.push_failed", path=remote_path, error=e))
                ok = False

            if ok:
                success_count += 1
                self.logger.log(t("adb.push.success", name=f.name))
            else:
                fail_count += 1
                self.logger.log(t("adb.push.failed", name=f.name))

        self.logger.log("-" * 50)
        self.logger.log(t("ui.adb_push.push_summary", success=success_count, fail=fail_count))
        self.logger.status(t("status.done"))

        self.master.after(0, lambda: self.push_button.config(state=tk.NORMAL))

        if fail_count == 0:
            messagebox.showinfo(t("common.success"),
                                t("ui.adb_push.push_summary", success=success_count, fail=fail_count))
        else:
            messagebox.showwarning(t("common.warning"),
                                   t("ui.adb_push.push_summary", success=success_count, fail=fail_count))
