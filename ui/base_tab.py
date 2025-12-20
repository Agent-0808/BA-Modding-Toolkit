# ui/base_tab.py

import tkinter as tk
from tkinter import ttk
from pathlib import Path
import threading
from typing import Callable, TYPE_CHECKING

from i18n import t
from .components import Theme

if TYPE_CHECKING:
    from ui.app import App

class TabFrame(ttk.Frame):
    """所有Tab页面的基类，提供通用功能和结构。"""
    def __init__(self, parent: ttk.Notebook, app: 'App'):
        super().__init__(parent, padding=10)
        self.app = app
        self.logger = app.logger
        self.create_widgets()

    def create_widgets(self):
        raise NotImplementedError("子类必须实现 create_widgets 方法")

    def run_in_thread(self, target: Callable, *args):
        thread = threading.Thread(target=target, args=args)
        thread.daemon = True
        thread.start()

    def set_file_path(self, path_var_name: str, label_widget: tk.Widget, path: Path, file_type_name: str, callback: Callable[[], None] | None = None):
        setattr(self, path_var_name, path)
        label_widget.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(t("log.file.loaded_type", type=file_type_name, name=path.name))
        self.logger.status(t("log.status.loaded", type=file_type_name))
        if callback:
            callback()

    def set_folder_path(self, path_var_name: str, label_widget: tk.Widget, path: Path, folder_type_name: str):
        setattr(self, path_var_name, path)
        label_widget.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(t("log.file.loaded_type", type=folder_type_name, name=path.name))
        self.logger.status(t("log.status.loaded", type=folder_type_name))

    def clear_callback(self, attr_name: str, default_value = None, log_msg: str | None = None) -> Callable[[], None]:
        def _clear_action():
            # 重置属性值
            setattr(self, attr_name, default_value)
            
            # 如果提供了日志消息，则记录
            if log_msg:
                self.logger.log(log_msg)
                
        return _clear_action