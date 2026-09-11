# gui/windows/batch_preview_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from typing import TYPE_CHECKING
from threading import Thread

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...spine import RENDER_PRESET_HIGH, RENDER_PRESET_LOW
from ...report import render_all_spine_previews
from ..components import SettingRow, UIComponents
from ..utils import open_directory
from .base import StoppableDialog


class BatchRenderDialog(StoppableDialog):
    """批量渲染 Spine 预览图对话框（作用于全部 Spine 资源，不限 Mod）"""

    def __init__(self, master, app_instance: "App"):
        super().__init__(master)
        self.app = app_instance

        # 游戏资源目录（仅对话框内使用，不保存配置），默认为当前游戏目录
        self.game_dir_var: tk.StringVar = tk.StringVar(
            value=self.app.get_current_resource_dir() or ""
        )

        # 渲染分类开关（对应 report.py 的 RENDER_CATEGORIES，仅对话框内使用，不保存配置）
        self.render_characters_var: tk.BooleanVar = tk.BooleanVar(value=True)
        self.render_lobbies_var: tk.BooleanVar = tk.BooleanVar(value=True)
        self.render_background_var: tk.BooleanVar = tk.BooleanVar(value=True)

        self._setup_window()
        self._create_widgets()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.tools.batch_preview.title"))
        self.geometry("800x400")
        self.app.setup_icon(self)
        self.transient(self.master)

    def _create_widgets(self):
        """创建界面组件"""
        main_frame = tb.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 选项区域
        options_frame = tb.Labelframe(main_frame, text=t("ui.label.options"), padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # 预览渲染预设选择
        SettingRow.create_path_selector(
            parent=options_frame,
            label=t("ui.tools.batch_preview.game_dir"),
            path_var=self.game_dir_var,
        )

        SettingRow.create_combobox_row(
            options_frame,
            label=t("option.report_render_preset"),
            text_var=self.app.report_render_preset_var,
            values=[
                ("low", t("option.report_render_preset_low")),
                ("high", t("option.report_render_preset_high"))
            ],
            tooltip=t("option.report_render_preset_info"),
        )

        render_option_sep = tb.Separator(options_frame)
        render_option_sep.pack(fill=tk.X, pady=10)

        # 渲染分类开关（对应 report.py 的 RENDER_CATEGORIES）
        SettingRow.create_switch(
            options_frame,
            label=t("option.render_characters"),
            variable=self.render_characters_var,
            tooltip=t("option.render_characters_info")
        )

        SettingRow.create_switch(
            options_frame,
            label=t("option.render_lobbies"),
            variable=self.render_lobbies_var,
            tooltip=t("option.render_lobbies_info")
        )

        SettingRow.create_switch(
            options_frame,
            label=t("option.render_background"),
            variable=self.render_background_var,
            tooltip=t("option.render_background_info")
        )

        # 进度区域
        progress_frame = tb.Frame(main_frame)
        progress_frame.pack(fill=tk.X, pady=(0, 10))

        self.progress_bar = tb.Progressbar(
            progress_frame,
            mode="determinate",
            bootstyle="success-striped"
        )
        self.progress_bar.pack(fill=tk.X, pady=10)

        # 按钮区域
        button_frame = tb.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)

        # 渲染按钮
        render_btn = UIComponents.create_button(
            button_frame,
            text=t("action.generate"),
            command=self._start_render,
            bootstyle="success"
        )
        render_btn.pack(anchor=tk.CENTER)

    def _show_spine_viewer_not_configured(self):
        """显示 SpineViewer 未配置的提示"""
        messagebox.showwarning(
            t("common.warning"),
            t("message.3rd_party.spine_viewer_required")
        )

    def _update_progress(self, current: int, total: int, filename: str):
        """更新进度"""
        # 检查窗口是否还存在
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
            # 窗口已被销毁，忽略更新
            pass

    def _start_render(self):
        """开始批量渲染"""


        # 检查 SpineViewer
        viewer_path_str = self.app.spine_viewer_path_var.get().strip()
        if not viewer_path_str:
            self._show_spine_viewer_not_configured()
            return
        viewer_path = Path(viewer_path_str)
        if not viewer_path.exists():
            messagebox.showerror(t("common.error"), t("message.file_not_found", path=viewer_path_str))
            return

        # 输出目录（固定 output/batch_preview/，文件名 = prefix，重复渲染自动覆盖）
        output_dir = self.app.get_output_subdir(self.app.OUTPUT_SUBDIR_BATCH_PREVIEW)

        # 标记任务开始
        self.set_task_running(True)

        # 预览渲染预设
        preset_map = {"low": RENDER_PRESET_LOW, "high": RENDER_PRESET_HIGH}
        render_options = preset_map.get(self.app.report_render_preset_var.get(), RENDER_PRESET_LOW)

        # 收集需要渲染的分类（对应 report.py 的 RENDER_CATEGORIES）
        render_categories: set[str] = set()
        if self.render_characters_var.get():
            render_categories.add("spinecharacters")
        if self.render_lobbies_var.get():
            render_categories.add("spinelobbies")
        if self.render_background_var.get():
            render_categories.add("spinebackground")

        if not render_categories:
            messagebox.showwarning(t("common.warning"), t("message.batch_preview.no_category"))
            return

        # 在线程中运行
        def run():
            rendered, total = render_all_spine_previews(
                game_dir=Path(self.game_dir_var.get()),
                output_dir=output_dir,
                viewer_path=viewer_path,
                render_options=render_options,
                render_categories=render_categories,
                log=self.app.logger.log,
                progress_callback=self._update_progress,
                max_workers=self.app.max_workers_var.get(),
            )

            self.after(0, lambda: self._on_complete(rendered, total, output_dir))

        Thread(target=run, daemon=True).start()

    def _on_complete(self, rendered: int, total: int, output_dir: Path):
        """完成回调"""
        # 标记任务结束
        self.set_task_running(False)

        # 检查窗口是否还存在
        if not self.winfo_exists():
            return

        if total > 0:
            self.app.logger.status(t("status.done"))

            # 询问是否打开输出目录
            if messagebox.askyesno(t("common.success"), t("message.batch_preview_open_prompt", rendered=rendered, total=total)):
                open_directory(output_dir)

            # 关闭对话框
            self.destroy()
        else:
            self.app.logger.status(t("status.failed"))
