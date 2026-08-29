# gui/windows/preview_window.py

import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING

import ttkbootstrap as tb
from PIL import Image, ImageTk
from ttkbootstrap.widgets.scrolled import ScrolledFrame

from ...i18n import t
from ..utils import open_in_os, reveal_in_explorer
from .base import StoppableDialog

if TYPE_CHECKING:
    from ..app import App


class PreviewWindow(StoppableDialog):
    """预览图查看窗口：纵向滚动展示多张图片"""

    # 缩略图最大边长（像素）
    MAX_THUMBNAIL_SIZE = 512

    def __init__(self, master, app_instance: "App", image_paths: list[Path]):
        super().__init__(master)
        self.app = app_instance
        self._photos: list[ImageTk.PhotoImage] = []  # 保持引用防止图片被 GC

        self.title(t("action.render_preview"))
        # 多图时固定尺寸滚动浏览；单图时不调用 geometry，让窗口高度自适应图片
        if len(image_paths) > 1:
            self.geometry("520x680")
        self.app.setup_icon(self)
        self.transient(master)

        # 底部提示（先于内容区打包，保证始终可见）
        tb.Label(self, text=t("ui.preview.double_click_hint"), bootstyle="secondary").pack(
            side=tk.BOTTOM, pady=(0, 5))

        # 多图时用滚动容器 + 固定窗口尺寸；单图用普通 Frame 承载（Frame 会传播子组件尺寸，
        # ScrolledFrame 内部的 Canvas 不会，导致窗口高度无法自适应）
        if len(image_paths) > 1:
            self.geometry("520x680")
            container: tb.Frame = ScrolledFrame(self, autohide=True, padding=10)
        else:
            container = tb.Frame(self, padding=10)
        container.pack(fill=tk.BOTH, expand=True)

        for path in image_paths:
            name_label = tb.Label(container, text=path.name, bootstyle="primary")
            name_label.pack(anchor=tk.W, pady=(8, 2))

            photo = self._load_thumbnail(path)
            if photo is None:
                continue
            self._photos.append(photo)
            image_label = tb.Label(container, image=photo)
            image_label.pack()

            # 双击文件名在文件管理器中定位文件，双击图片用系统默认看图工具打开
            name_label.configure(cursor="hand2")
            name_label.bind("<Double-Button-1>", lambda e, p=path: reveal_in_explorer(p))
            image_label.configure(cursor="hand2")
            image_label.bind("<Double-Button-1>", lambda e, p=path: open_in_os(p))

    def _load_thumbnail(self, path: Path) -> ImageTk.PhotoImage | None:
        """加载图片并缩放到预览尺寸"""
        try:
            with Image.open(path) as image:
                image.thumbnail((self.MAX_THUMBNAIL_SIZE, self.MAX_THUMBNAIL_SIZE))
                return ImageTk.PhotoImage(image)
        except OSError:
            return None
