# gui/windows/backup_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import filedialog, messagebox
from pathlib import Path
from typing import TYPE_CHECKING
from threading import Thread
import shutil
import subprocess

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...searching import list_bundle_files
from ...bundle import analyze_trailing
from ...utils import throttle_progress
from ..utils import select_directory
from ..components import SettingRow, UIComponents
from .base import StoppableDialog


class BackupDialog(StoppableDialog):
    """Mod 备份对话框"""

    def __init__(self, master, app_instance: "App"):
        super().__init__(master)
        self.app = app_instance

        self._setup_window()
        self._create_widgets()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.tools.backup.title"))
        self.geometry("800x200")
        self.app.setup_icon(self)
        self.transient(self.master)

    def _create_widgets(self):
        """创建界面组件"""
        main_frame = tb.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 备份路径选择
        SettingRow.create_path_selector(
            main_frame,
            label=t("option.backup_path"),
            path_var=self.app.mod_backup_path_var,
            select_cmd=self._select_backup_path,
            tooltip=t("option.backup_path_info"),
        )

        # 进度区域
        progress_frame = tb.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(20, 10))

        self.progress_bar = tb.Progressbar(
            progress_frame,
            mode="determinate",
            bootstyle="success-striped"
        )
        self.progress_bar.pack(fill=tk.X)

        # 按钮区域
        button_frame = tb.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        # 开始备份按钮
        self.backup_button = UIComponents.create_button(
            button_frame,
            text=t("action.start_backup"),
            command=self._start_backup,
            bootstyle="success"
        )
        self.backup_button.pack(anchor=tk.CENTER)

    def _select_backup_path(self):
        """选择备份路径"""
        select_directory(
            self.app.mod_backup_path_var,
            t("option.backup_path"),
            self.app.logger.log
        )

    def _update_progress(self, current: int, total: int, filename: str):
        """更新进度"""
        if not self.winfo_exists():
            return

        try:
            self.progress_bar["maximum"] = total
            self.progress_bar["value"] = current
            self.app.logger.status(
                t("status.processing_batch", current=current, total=total, filename=filename)
            )
            self.update_idletasks()
        except tk.TclError:
            pass

    def _start_backup(self):
        """开始备份"""
        # 检查游戏目录
        game_dir = self.app.get_current_resource_dir()
        if not game_dir:
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return

        game_path = Path(game_dir)
        if not game_path.is_dir():
            messagebox.showerror(t("common.error"), t("message.dir_not_found", path=game_dir))
            return

        # 检查备份路径
        backup_path_str = self.app.mod_backup_path_var.get().strip()
        if not backup_path_str:
            messagebox.showerror(t("common.error"), t("message.backup.path_required"))
            return

        backup_path = Path(backup_path_str)

        # 如果备份目录已存在，询问是否清空
        if backup_path.exists():
            if not messagebox.askyesno(
                t("common.warning"),
                t("message.backup.clear_confirm")
            ):
                return
            shutil.rmtree(backup_path)
            backup_path.mkdir(parents=True)

        # 标记任务开始
        self.set_task_running(True)
        self.backup_button.config(state=tk.DISABLED)

        # 在线程中运行
        def run():
            self._run_backup(game_path, backup_path)
            self.after(0, lambda: self._on_complete(backup_path))

        Thread(target=run, daemon=True).start()

    def _run_backup(self, game_path: Path, backup_path: Path):
        """运行备份"""
        # 1. 扫描 bundle 文件
        self.app.logger.log(t("log.backup.start"))
        items = list_bundle_files(game_path)
        if not items:
            self.after(0, lambda: self.app.logger.status(t("message.no_bundle_found")))
            self.set_task_running(False)
            self.after(0, lambda: self.backup_button.config(state=tk.NORMAL))
            return

        # 2. 分析尾部字节，过滤 mod 文件
        mod_files: list[Path] = []
        total = len(items)
        # 节流进度更新，避免海量文件时的高频 GUI 更新
        update_progress = throttle_progress(
            lambda cur, tot, name: self.after(0, lambda: self._update_progress(cur, tot, name))
        )
        for i, item in enumerate(items):
            if self.should_stop():
                return

            analyze_trailing(item)

            # 更新进度
            update_progress(i + 1, total, item.path.name)

            # 判断是否是 mod（尾部字节 > 0）
            if item.trailing_bytes and item.trailing_bytes > 0:
                mod_files.append(item.path)

        if not mod_files:
            self.after(0, lambda: self.app.logger.status(t("message.backup.no_mod_found")))
            self.set_task_running(False)
            self.after(0, lambda: self.backup_button.config(state=tk.NORMAL))
            return

        self.app.logger.log(t("log.backup.found_mods", count=len(mod_files)))

        # 3. 复制 mod 文件到备份目录
        mod_total = len(mod_files)
        for i, source_path in enumerate(mod_files):
            if self.should_stop():
                return

            # 计算相对路径（相对于游戏目录）
            try:
                rel_path = source_path.relative_to(game_path)
            except ValueError:
                # 如果文件不在游戏目录下（如其他搜索目录），使用文件名
                rel_path = Path(source_path.name)

            # 在备份目录下创建相同目录结构
            dest_path = backup_path / rel_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # 复制文件（保留元数据）
            shutil.copy2(source_path, dest_path)

            # 记录日志
            self.app.logger.log(
                t("log.backup.copying", current=i + 1, total=mod_total, filename=rel_path.name)
            )

            # 更新进度
            self.after(0, lambda idx=i+1, tot=mod_total, name=rel_path.name:
                      self._update_progress(idx, tot, name))

        # 标记完成
        self.app.logger.log(t("log.backup.done", count=mod_total))
        self._backup_count = mod_total
        self.set_task_running(False)
        self.after(0, lambda: self.backup_button.config(state=tk.NORMAL))

    def _on_complete(self, backup_path: Path):
        """完成回调"""
        # 检查窗口是否还存在
        if not self.winfo_exists():
            return

        count = getattr(self, '_backup_count', 0)
        self.app.logger.status(t("status.done"))

        # 询问是否打开备份目录
        if messagebox.askyesno(
            t("common.success"),
            t("message.backup.open_prompt", count=count)
        ):
            subprocess.run(["explorer", str(backup_path)])

        # 关闭对话框
        self.destroy()
