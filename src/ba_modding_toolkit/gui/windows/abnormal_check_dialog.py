# gui/windows/abnormal_check_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.widgets.tableview import Tableview as TBTableview
from tkinter import messagebox
from pathlib import Path
from typing import TYPE_CHECKING
from threading import Thread
from dataclasses import dataclass

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...searching import list_bundle_files
from ...naming import parse_filename
from ...utils import CRCUtils
from ...bundle import analyze_trailing, analyze_naming
from .base import StoppableDialog


@dataclass
class MismatchItem:
    """CRC不匹配的文件信息"""
    path: Path
    filename: str
    char_name: str | None
    target_crc: int
    actual_crc: int


class AbnormalCheckDialog(StoppableDialog):
    """检测并修复CRC不匹配的bundle文件"""

    def __init__(self, master, app_instance: "App"):
        super().__init__(master)
        self.app = app_instance

        self._mismatch_items: list[MismatchItem] = []

        self._setup_window()
        self._create_widgets()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.abnormal_check.title"))
        self.geometry("1200x400")
        self.app.setup_icon(self)
        self.transient(self.master)

    def _create_widgets(self):
        """创建界面组件"""
        main_frame = tb.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 进度区域
        progress_frame = tb.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_label = tb.Label(progress_frame, text="")
        self.progress_label.pack(fill=tk.X)

        self.progress_bar = tb.Progressbar(
            progress_frame,
            mode="determinate",
            bootstyle="success-striped"
        )
        self.progress_bar.pack(fill=tk.X, pady=(5, 0))

        # 结果列表区域
        list_frame = tb.Labelframe(main_frame, text=t("ui.abnormal_check.result_list"), padding=10)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Tableview
        coldata = [
            {"text": t("ui.abnormal_check.column_filename"), "width": 700, "stretch": True},
            {"text": t("ui.abnormal_check.column_char_name"), "width": 200, "stretch": True},
            {"text": t("ui.abnormal_check.column_target_crc"), "width": 100, "stretch": False},
            {"text": t("ui.abnormal_check.column_actual_crc"), "width": 100, "stretch": False},
        ]

        colors = tb.Style().colors
        self.table = TBTableview(
            master=list_frame,
            coldata=coldata,
            rowdata=[],
            yscrollbar=True,
            autofit=False,
            bootstyle="primary",
            stripecolor=(colors.light, None),
            height=5,
        )
        self.table.pack(fill=tk.BOTH, expand=True)

        # 按钮区域
        button_frame = tb.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X)

        # 开始扫描按钮
        self.scan_button = tb.Button(
            button_frame,
            text=t("action.detect"),
            command=self._start_scan,
            bootstyle="primary"
        )
        self.scan_button.pack(side=tk.LEFT, padx=5)

        # 修复全部按钮
        self.fix_button = tb.Button(
            button_frame,
            text=t("action.fix_all"),
            command=self._fix_all,
            bootstyle="success",
            state=tk.DISABLED
        )
        self.fix_button.pack(side=tk.LEFT, padx=5)

    def _update_progress(self, current: int, total: int, filename: str):
        """更新进度"""
        # 检查窗口是否还存在
        if not self.winfo_exists():
            return

        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = current
        self.progress_label.config(
            text=t("status.processing_batch", current=current, total=total, filename=filename)
        )
        self.update_idletasks()

    def _start_scan(self):
        """开始扫描"""
        # 检查游戏目录
        game_dir = self.app.get_current_resource_dir()
        if not game_dir:
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return

        game_path = Path(game_dir)
        if not game_path.is_dir():
            messagebox.showerror(t("common.error"), t("message.dir_not_found", path=game_dir))
            return

        # 禁用按钮
        self.scan_button.config(state=tk.DISABLED)
        self.fix_button.config(state=tk.DISABLED)

        # 清空列表
        self.table.delete_rows()
        self._mismatch_items.clear()

        # 在线程中运行
        def run():
            self._scan_files(game_path)
            self.after(0, self._on_scan_complete)

        Thread(target=run, daemon=True).start()

    def _scan_files(self, game_dir: Path):
        """扫描文件"""
        # 1. 扫描 bundle 文件
        items = list_bundle_files(game_dir)
        if not items:
            self.after(0, lambda: self.progress_label.config(text=t("log.report.no_bundle_found")))
            return

        # 2. 分析每个文件
        total = len(items)
        for i, item in enumerate(items):
            # 检查停止信号
            if self.should_stop():
                return

            analyze_trailing(item)
            analyze_naming(item)

            # 更新进度
            self.after(0, lambda idx=i, tot=total, name=item.path.name:
                      self._update_progress(idx + 1, tot, name))

            # 检查 CRC 是否匹配
            if item.parsed_name and item.parsed_name.crc:
                try:
                    target_crc = int(item.parsed_name.crc)
                    actual_crc = CRCUtils.compute_crc32(item.path)

                    if target_crc != actual_crc:
                        # 获取角色名
                        char_name = None
                        if self.app.char_map and item.parsed_name.core:
                            char_name = self.app.char_map.lookup(
                                item.parsed_name.core,
                                self.app.character_name_field_var.get()
                            )

                        # 添加到列表
                        mismatch = MismatchItem(
                            path=item.path,
                            filename=item.path.name,
                            char_name=char_name,
                            target_crc=target_crc,
                            actual_crc=actual_crc
                        )
                        self._mismatch_items.append(mismatch)
                except (ValueError, OSError):
                    # 解析CRC失败或计算CRC失败，跳过
                    pass

    def _on_scan_complete(self):
        """扫描完成"""
        # 检查窗口是否还存在
        if not self.winfo_exists():
            return

        count = len(self._mismatch_items)

        # 更新日志
        self.app.logger.log(t("log.abnormal_check.found_count", count=count))

        # 填充 Tableview
        if count > 0:
            rowdata = [
                [item.filename, item.char_name or "-", str(item.target_crc), str(item.actual_crc)]
                for item in self._mismatch_items
            ]
            self.table.insert_rows('end', rowdata)
            self.table.autofit_columns()

        # 更新UI状态
        self.progress_label.config(text=t("status.done"))
        self.scan_button.config(state=tk.NORMAL)

        if count > 0:
            self.fix_button.config(state=tk.NORMAL)
        else:
            messagebox.showinfo(t("common.success"), t("message.abnormal_check.no_mismatch"))

    def _fix_all(self):
        """修复全部"""
        count = len(self._mismatch_items)
        if count == 0:
            return

        # 确认
        if not messagebox.askyesno(
            t("common.warning"),
            t("message.abnormal_check.confirm_fix", count=count)
        ):
            return

        # 禁用按钮
        self.scan_button.config(state=tk.DISABLED)
        self.fix_button.config(state=tk.DISABLED)

        # 在线程中运行
        def run():
            self._fix_files()
            self.after(0, self._on_fix_complete)

        Thread(target=run, daemon=True).start()

    def _fix_files(self):
        """修复文件"""
        extra_bytes = self.app.get_extra_bytes()

        for i, item in enumerate(self._mismatch_items):
            # 检查停止信号
            if self.should_stop():
                return

            # 更新进度
            self.after(0, lambda idx=i, tot=len(self._mismatch_items), name=item.filename:
                      self._update_progress(idx + 1, tot, filename=t("log.abnormal_check.fixing", filename=name)))

            try:
                # 修复 CRC
                success = CRCUtils.manipulate_file_crc(
                    item.path,
                    item.target_crc,
                    extra_bytes
                )

                if success:
                    # 验证修复结果
                    actual_crc = CRCUtils.compute_crc32(item.path)
                    if actual_crc == item.target_crc:
                        self.app.logger.log(t("log.abnormal_check.fix_success", filename=item.filename))
                    else:
                        self.app.logger.log(t("log.abnormal_check.fix_verify_failed", filename=item.filename))
                else:
                    self.app.logger.log(t("log.abnormal_check.fix_failed", filename=item.filename))
            except Exception as e:
                self.app.logger.log(t("log.abnormal_check.fix_error", filename=item.filename, error=str(e)))

    def _on_fix_complete(self):
        """修复完成"""
        # 检查窗口是否还存在
        if not self.winfo_exists():
            return

        self.progress_label.config(text=t("status.done"))
        self.scan_button.config(state=tk.NORMAL)

        messagebox.showinfo(t("common.success"), t("message.abnormal_check.fix_complete"))