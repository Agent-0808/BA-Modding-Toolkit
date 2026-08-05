# gui/tabs/tools_tab.py

import tkinter as tk
import ttkbootstrap as tb
from ttkbootstrap.widgets.tooltip import ToolTip
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ..components import UIComponents
from ..windows.report_dialog import ReportDialog
from ..windows.abnormal_check_dialog import AbnormalCheckDialog
from ..windows.backup_dialog import BackupDialog
from .base_tab import TabFrame


class ToolsTab(TabFrame):
    """工具标签页，包含各种批量操作工具"""

    def create_widgets(self):
        # 工具按钮区域
        batch_tools_frame = tb.Labelframe(self, text=t("ui.tools.batch_tools"))
        batch_tools_frame.pack(anchor=tk.CENTER, fill=tk.X)

        # Mod 检测方式说明（悬浮在 ⓘ 图标上显示）
        info_frame = tb.Frame(batch_tools_frame)
        info_frame.pack(anchor=tk.W, padx=30, pady=(10, 0))
        info_icon = UIComponents.create_tooltip_icon(info_frame, t("ui.tools.batch_tools_info"))
        info_icon.pack(side=tk.LEFT)

        button_frame = tb.Frame(batch_tools_frame)
        button_frame.pack(anchor=tk.CENTER, fill=tk.BOTH, expand=True, padx=30)

        # Mod 报告按钮
        report_btn = UIComponents.create_button(
            button_frame,
            text=t("ui.tools.report.title"),
            command=self._open_report_dialog,
            bootstyle="primary",
        )
        report_btn.pack(fill=tk.X, pady=10)
        ToolTip(report_btn, text=t("ui.tools.report.info"), wraplength=400)

        # 修复不正常的用户端按钮
        abnormal_btn = UIComponents.create_button(
            button_frame,
            text=t("ui.tools.abnormal_check.title"),
            command=self._open_abnormal_check_dialog,
            bootstyle="warning",
        )
        abnormal_btn.pack(fill=tk.X, pady=10)
        ToolTip(abnormal_btn, text=t("ui.tools.abnormal_check.info"), wraplength=400)

        # 备份 Mod 按钮
        backup_btn = UIComponents.create_button(
            button_frame,
            text=t("ui.tools.backup.title"),
            command=self._open_backup_dialog,
            bootstyle="info",
        )
        backup_btn.pack(fill=tk.X, pady=10)
        ToolTip(backup_btn, text=t("ui.tools.backup.info"), wraplength=400)

    def _open_report_dialog(self):
        """打开报告生成对话框"""
        dialog = ReportDialog(self.master, self.app)
        self.master.wait_window(dialog)

    def _open_abnormal_check_dialog(self):
        """打开CRC不匹配检测对话框"""
        dialog = AbnormalCheckDialog(self.master, self.app)
        self.master.wait_window(dialog)

    def _open_backup_dialog(self):
        """打开 Mod 备份对话框"""
        dialog = BackupDialog(self.master, self.app)
        self.master.wait_window(dialog)