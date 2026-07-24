# gui/windows/base.py

import ttkbootstrap as tb
from threading import Event


class StoppableDialog(tb.Toplevel):
    """支持后台任务停止的对话框基类"""

    def __init__(self, master):
        super().__init__(master)
        self._stop_event = Event()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _on_close(self):
        """窗口关闭时停止后台任务"""
        self._stop_event.set()
        self.destroy()

    def should_stop(self) -> bool:
        """检查是否应该停止"""
        return self._stop_event.is_set()

    def reset_stop_event(self):
        """重置停止事件（用于开始新任务）"""
        self._stop_event.clear()