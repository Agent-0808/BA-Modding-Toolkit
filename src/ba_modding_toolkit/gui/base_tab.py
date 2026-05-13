# gui/base_tab.py

import ttkbootstrap as tb
import threading
from typing import Callable, TYPE_CHECKING
if TYPE_CHECKING:
    from .app import App

class TabFrame(tb.Frame):
    """所有Tab页面的基类，提供通用功能和结构。"""
    def __init__(self, parent: tb.Frame, app: "App"):
        super().__init__(parent)
        self.app = app
        self.logger = app.logger
        self.create_widgets()

    def create_widgets(self):
        raise NotImplementedError("子类必须实现 create_widgets 方法")

    def run_in_thread(self, target: Callable, *args):
        thread = threading.Thread(target=target, args=args)
        thread.daemon = True
        thread.start()
