# gui/tabs/tools_tab.py

import tkinter as tk
import ttkbootstrap as tb
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ..components import UIComponents
from ..windows.report_dialog import ReportDialog
from .base_tab import TabFrame


class ToolsTab(TabFrame):
    """工具标签页，包含各种批量操作工具"""

    def create_widgets(self):
        # 工具按钮区域
        button_frame = tb.Frame(self)
        button_frame.pack(anchor=tk.CENTER, fill=tk.BOTH, expand=True)

        # Mod 报告按钮
        report_btn = UIComponents.create_button(
            button_frame,
            text=t("ui.report.title"),
            command=self._open_report_dialog,
            bootstyle="primary",
        )
        report_btn.pack(fill=tk.X, pady=10)

    def _open_report_dialog(self):
        """打开报告生成对话框"""
        dialog = ReportDialog(self.master, self.app)
        self.master.wait_window(dialog)