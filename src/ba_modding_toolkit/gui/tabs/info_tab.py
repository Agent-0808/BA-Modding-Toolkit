# ui/tabs/info_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ... import core
from ...utils import CRCUtils, is_bundle_file, get_search_resource_dirs
from ..base_tab import TabFrame
from ..components import UIComponents
from ..utils import handle_drop, replace_file, select_file


class InfoTab(TabFrame):
    """信息查看工具页"""

    def create_widgets(self):
        self.bundle_path: Path | None = None
        self.found_bundle_path: Path | None = None
        self.bundle_info: dict = {}

        # 拖放区
        self._create_drop_zone()

        # 原文件显示区
        self._create_original_file_display()

        # 操作按钮区
        self._create_action_buttons()

    def _create_drop_zone(self):
        """创建文件拖放区"""
        _, self.drop_label = UIComponents.create_file_drop_zone(
            self,
            t("ui.info.drop_zone_title"),
            self._on_drop,
            self._browse_file,
            clear_cmd=self._clear_bundle,
            label_text=t("ui.info.drop_hint")
        )

    def _clear_bundle(self):
        """清除已加载的 Bundle"""
        self.bundle_path = None
        self.found_bundle_path = None
        self.bundle_info = {}

        # 禁用按钮
        self.replace_btn.config(state="disabled")
        self.view_assets_btn.config(state="disabled")
        self.open_folder_btn.config(state="disabled")

        # 清空原文件显示
        self.original_label.config(text=t("ui.info.not_found"), bootstyle="secondary")

        self.logger.log("Cleared")

    def _create_original_file_display(self):
        """创建原文件显示区（只读）"""
        original_frame = tb.Labelframe(self, text=t("ui.info.original_file"), padding=10)
        original_frame.pack(fill=tk.X, pady=(0, 10))

        self.original_label = tb.Label(
            original_frame,
            text=t("ui.info.not_found"),
            font=("Consolas", 10),
            bootstyle="secondary",
            wraplength=400,
            justify=tk.LEFT
        )
        self.original_label.pack(fill=tk.X)

        # 打开文件夹按钮
        self.open_folder_btn = UIComponents.create_button(
            original_frame,
            t("action.open_folder"),
            self._open_original_folder,
            bootstyle="info",
            state="disabled"
        )
        self.open_folder_btn.pack(anchor=tk.CENTER, pady=(5, 0))

        # 绑定窗口大小变化事件，自动调整换行宽度
        original_frame.bind('<Configure>', self._on_original_frame_configure)

    def _on_original_frame_configure(self, event: tk.Event):
        """原文件显示区大小变化时调整标签换行宽度"""
        # 留出边距
        new_wraplength = event.width - 30
        if new_wraplength > 0:
            self.original_label.config(wraplength=new_wraplength)

    def _create_action_buttons(self):
        """创建操作按钮区"""
        self.action_frame = tb.Labelframe(self, text=t("ui.info.actions"), padding=10)
        self.action_frame.pack(fill=tk.X, pady=(0, 10))

        btn_frame = tb.Frame(self.action_frame)
        btn_frame.pack()

        # 覆盖原文件
        self.replace_btn = UIComponents.create_button(
            btn_frame, t("action.replace_original"),
            self._replace_original_thread, bootstyle="danger", state="disabled"
        )
        self.replace_btn.pack(side=tk.LEFT, padx=5)

        # 查看资源列表
        self.view_assets_btn = UIComponents.create_button(
            btn_frame, t("ui.info.view_assets"),
            self._view_assets, bootstyle="secondary", state="disabled"
        )
        self.view_assets_btn.pack(side=tk.LEFT, padx=5)

    def _on_drop(self, event):
        """处理拖放事件"""
        handle_drop(event, callback=self._load_bundle)

    def _browse_file(self):
        """浏览选择文件"""
        select_file(
            title=t("ui.dialog.select", type=t("file_type.bundle")),
            filetypes=[(t("file_type.bundle"), "*.bundle"), (t("file_type.all_files"), "*.*")],
            callback=self._load_bundle,
            log=self.logger.log
        )

    def _load_bundle(self, path: Path):
        """加载 Bundle 文件"""
        if not path.exists():
            messagebox.showerror(t("common.error"), t("message.file_not_found", path=path))
            return

        # 检查是否为 Bundle
        if not is_bundle_file(path):
            messagebox.showerror(t("common.error"), t("message.not_bundle_file"))
            return

        self.bundle_path = path
        self.drop_label.config(text=path.name, bootstyle="success")

        # 在后台线程中加载
        self.run_in_thread(self._load_bundle_worker, path)

    def _load_bundle_worker(self, path: Path):
        """后台加载 Bundle 信息"""
        try:
            # 获取基础信息
            platform, unity_version = core.get_unity_platform_info(path)

            # 计算 CRC32
            with open(path, "rb") as f:
                crc32 = CRCUtils.compute_crc32(f.read())

            # 加载 Bundle 获取资源列表
            env = core.load_bundle(path, self.logger.log)
            assets = []
            if env:
                for obj in env.objects:
                    assets.append({
                        "type": obj.type.name,
                        "name": obj.peek_name() or "",
                        "path_id": obj.path_id
                    })

            # 保存信息
            self.bundle_info = {
                "filename": path.name,
                "filesize": self._format_file_size(path.stat().st_size),
                "unity_version": unity_version,
                "platform": platform,
                "crc32": f"{crc32:08X}",
                "assets": assets
            }

            # 更新 UI
            self.master.after(0, self._update_ui_with_info)

        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror(
                t("common.error"), t("message.error_during_process", error=e)
            ))

    def _update_ui_with_info(self):
        """使用加载的信息更新 UI"""
        info = self.bundle_info

        # 输出信息到 log
        self.logger.log(f"Bundle: {info['filename']}")
        self.logger.log(f"  Size: {info['filesize']}")
        self.logger.log(f"  Unity: {info['unity_version']}")
        self.logger.log(f"  Platform: {info['platform']}")
        self.logger.log(f"  CRC32: {info['crc32']}")

        # 启用按钮
        self.replace_btn.config(state="disabled")  # 需要先查找才能替换
        self.view_assets_btn.config(state="normal")

        self.logger.log(f"Loaded: {info['filename']}")
        self.logger.status(t("log.status.ready"))

        # 自动查找原文件
        self.run_in_thread(self._auto_find_original)

    def _auto_find_original(self):
        """自动查找同名原文件"""
        if not self.bundle_path:
            return

        game_dir_str = self.app.game_resource_dir_var.get()
        if not game_dir_str:
            self.master.after(0, lambda: self.original_label.config(
                text=t("ui.info.not_found"), bootstyle="warning"
            ))
            return

        base_game_dir = Path(game_dir_str)
        search_dirs = get_search_resource_dirs(base_game_dir, self.app.auto_detect_subdirs_var.get())

        found = False
        for directory in search_dirs:
            if not directory.is_dir():
                continue
            candidate = directory / self.bundle_path.name
            if candidate.exists():
                self.found_bundle_path = candidate
                self.master.after(0, lambda: self._on_original_found(candidate))
                found = True
                break

        if not found:
            self.master.after(0, lambda: self.original_label.config(
                text=t("ui.info.not_found"), bootstyle="warning"
            ))

    def _on_original_found(self, path: Path):
        """找到原文件后的回调"""
        self.replace_btn.config(state="normal")
        self.open_folder_btn.config(state="normal")
        self.original_label.config(text=str(path), bootstyle="success")
        self.logger.log(f"Found original: {path}")

    def _open_original_folder(self):
        """打开原文件所在文件夹"""
        if not self.found_bundle_path:
            return
        import subprocess
        subprocess.run(["explorer", "/select,", str(self.found_bundle_path)])

    def _replace_original_thread(self):
        """后台执行覆盖原文件"""
        if not self.found_bundle_path or not self.bundle_path:
            return

        self.replace_btn.config(state="disabled")
        self.run_in_thread(self._replace_original_worker)

    def _replace_original_worker(self):
        """覆盖原文件的工作线程"""
        success = replace_file(
            source_path=self.bundle_path,
            dest_path=self.found_bundle_path,
            create_backup=self.app.create_backup_var.get(),
            ask_confirm=True,
            log=self.logger.log
        )

        self.master.after(0, lambda: self.replace_btn.config(state="normal" if success else "normal"))

    def _view_assets(self):
        """查看资源列表 - 输出到 log"""
        if not self.bundle_info or not self.bundle_info.get("assets"):
            return

        assets = self.bundle_info["assets"]
        self.logger.log(f"Assets ({len(assets)} total):")
        for asset in assets[:100]:  # 最多显示100个
            self.logger.log(f"  [{asset['type']}] {asset['name']} (ID: {asset['path_id']})")
        if len(assets) > 100:
            self.logger.log(f"  ... and {len(assets) - 100} more")

    @staticmethod
    def _format_file_size(size: int) -> str:
        """格式化文件大小"""
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.2f} {unit}"
            size /= 1024
        return f"{size:.2f} TB"
