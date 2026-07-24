# gui/windows/report_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING
from threading import Thread
import subprocess

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...report import generate_mod_report
from ..components import SettingRow, UIComponents
from .base import StoppableDialog


class ReportDialog(StoppableDialog):
    """报告生成对话框"""

    def __init__(self, master, app_instance: "App"):
        super().__init__(master)
        self.app = app_instance

        self._setup_window()
        self._create_widgets()

    def _setup_window(self):
        """设置窗口基本属性"""
        self.title(t("ui.report.title"))
        self.geometry("500x250")
        self.app.setup_icon(self)
        self.transient(self.master)

    def _create_widgets(self):
        """创建界面组件"""
        main_frame = tb.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 选项区域
        options_frame = tb.Labelframe(main_frame, text=t("common.options"), padding=10)
        options_frame.pack(fill=tk.X, pady=(0, 10))

        # Spine 预览开关
        SettingRow.create_switch(
            options_frame,
            label=t("option.enable_spine_preview"),
            variable=self.app.enable_spine_preview_var,
            tooltip=t("option.enable_spine_preview_info"),
            app=self.app,
            on_click_disabled=self._show_spine_viewer_not_configured
        )

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

        # 按钮区域
        button_frame = tb.Frame(main_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        # 生成按钮
        generate_btn = UIComponents.create_button(
            button_frame,
            text=t("action.generate"),
            command=self._generate_report,
            bootstyle="success"
        )
        generate_btn.pack(anchor=tk.CENTER)

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

        self.progress_bar["maximum"] = total
        self.progress_bar["value"] = current
        self.progress_label.config(
            text=t("status.processing_batch", current=current, total=total, filename=filename)
        )
        self.update_idletasks()

    def _generate_report(self):
        """生成报告"""

        # 检查游戏目录
        game_dir = self.app.get_current_resource_dir()
        if not game_dir:
            messagebox.showerror(t("common.error"), t("message.missing_paths"))
            return

        game_path = Path(game_dir)
        if not game_path.is_dir():
            messagebox.showerror(t("common.error"), t("message.dir_not_found", path=game_dir))
            return

        # 检查 SpineViewer（如果启用渲染）
        viewer_path = None
        enable_render = self.app.enable_spine_preview_var.get()
        if enable_render:
            viewer_path_str = self.app.spine_viewer_path_var.get().strip()
            if not viewer_path_str:
                messagebox.showerror(t("common.error"), t("message.3rd_party.spine_viewer_required"))
                return
            viewer_path = Path(viewer_path_str)
            if not viewer_path.exists():
                messagebox.showerror(t("common.error"), t("message.file_not_found", path=viewer_path_str))
                return

        # 输出目录
        output_dir = self.app.get_output_subdir(self.app.OUTPUT_SUBDIR_PREVIEW)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"mod_report_{timestamp}.md"

        # 在线程中运行
        def run():
            success, message = generate_mod_report(
                game_dir=game_path,
                output_path=output_path,
                char_map=self.app.char_map,
                char_name_field=self.app.character_name_field_var.get(),
                enable_render=enable_render,
                viewer_path=viewer_path,
                log=self.app.logger.log,
                progress_callback=self._update_progress,
            )

            self.after(0, lambda: self._on_complete(success, message, output_path))

        Thread(target=run, daemon=True).start()

    def _on_complete(self, success: bool, message: str, output_path: Path):
        """完成回调"""
        # 检查窗口是否还存在
        if not self.winfo_exists():
            return

        if success:
            self.progress_label.config(text=t("status.done"))

            # 询问是否打开报告
            if messagebox.askyesno(t("common.success"), t("message.report_open_prompt")):
                subprocess.run(["explorer", str(output_path)])

            # 关闭对话框
            self.destroy()
        else:
            self.progress_label.config(text=t("status.failed"))