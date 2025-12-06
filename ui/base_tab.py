# ui/base_tab.py

import tkinter as tk
from tkinter import ttk
from pathlib import Path
import threading
from typing import Callable, TYPE_CHECKING

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
        self.logger.log(f"已加载 {file_type_name}: {path.name}")
        self.logger.status(f"已加载 {file_type_name}")
        if callback:
            callback()

    def set_folder_path(self, path_var_name: str, label_widget: tk.Widget, path: Path, folder_type_name: str):
        setattr(self, path_var_name, path)
        label_widget.config(text=f"{path.name}", fg=Theme.COLOR_SUCCESS)
        self.logger.log(f"已加载 {folder_type_name}: {path.name}")
        self.logger.status(f"已加载 {folder_type_name}")

    def get_game_search_dirs(self, base_game_dir: Path, auto_detect_subdirs: bool) -> list[Path]:
        if auto_detect_subdirs:
            suffixes = ["",
                "BlueArchive_Data/StreamingAssets/PUB/Resource/GameData/Windows",
                "BlueArchive_Data/StreamingAssets/PUB/Resource/Preload/Windows",
"GameData/Windows",
                "Preload/Windows",
"GameData/Android",
                "Preload/Android",
                ]
            return [base_game_dir / suffix for suffix in suffixes]
        else:
            return [base_game_dir]