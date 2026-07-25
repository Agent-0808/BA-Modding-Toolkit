# gui/windows/base.py

import ttkbootstrap as tb
from tkinter import messagebox
from threading import Event
from ...i18n import t


class StoppableDialog(tb.Toplevel):
    """支持后台任务停止的对话框基类"""

    def __init__(self, master):
        super().__init__(master)
        self._stop_event = Event()
        self._task_running = False  # 任务运行状态
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """窗口关闭时的处理：检查任务状态并确认"""
        if self._task_running:
            # 任务正在运行，提示用户确认
            if not messagebox.askyesno(
                t("common.warning"),
                t("message.task_running_close_confirm"),
                parent=self
            ):
                return  # 用户取消关闭

        # 发送停止信号并销毁窗口
        self._stop_event.set()
        self.destroy()

    def should_stop(self) -> bool:
        """检查是否应该停止"""
        return self._stop_event.is_set()

    def reset_stop_event(self):
        """重置停止事件（用于开始新任务）"""
        self._stop_event.clear()

    def set_task_running(self, running: bool):
        """设置任务运行状态

        Args:
            running: True 表示任务开始，False 表示任务结束
        """
        self._task_running = running