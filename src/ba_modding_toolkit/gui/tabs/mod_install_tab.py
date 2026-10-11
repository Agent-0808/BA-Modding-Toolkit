# gui/tabs/mod_install_tab.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path

from ...i18n import t
from ...mod_install import InstallAction, ModGroup, plan_mod_install
from ...searching import get_search_dirs
from ..components import FileListbox, UIComponents, SettingRow
from ..windows.mod_install_dialog import ModInstallDialog
from .base_tab import TabFrame


class ModInstallTab(TabFrame):
    """Mod安装标签页：批量分析 Mod 与游戏目录的关系，逐组确认后一次性安装"""

    def __init__(self, *args, **kwargs):
        self.mod_file_list: list[Path] = []
        self.groups: list[ModGroup] = []  # 最近一次分析结果（决策粒度为组）
        self.match_strategy_var = tk.StringVar(value='cont_name_type')
        self._plan_running = False  # 防止并发重复分析
        super().__init__(*args, **kwargs)

    def create_widgets(self):
        # 1. Mod 文件列表（拖入后自动分析）
        self.mod_file_listbox = FileListbox(
            self,
            t("ui.label.mod_file"),
            self.mod_file_list,
            t("ui.mod_install.placeholder"),
            height=6,
            logger=self.logger,
            display_formatter=lambda p: f"{p.parent.name} / {p.name}",
            on_files_added=self._on_files_added,
        )
        self.mod_file_listbox.get_frame().pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # 2. 选项区（匹配策略供执行阶段使用）
        option_frame = tb.Labelframe(self, text=t("ui.label.options"), padding=10)
        option_frame.pack(fill=tk.X, pady=(5, 0))

        self.strategy_combo = SettingRow.create_combobox_row(
            option_frame, t("option.match_strategy"),
            self.match_strategy_var,
            values=['path_id', 'cont_name_type', 'name_type'],
            tooltip=t("option.match_strategy_info")
        )

        # 3. 操作按钮区域
        action_button_frame = tb.Frame(self)
        action_button_frame.pack(fill=tk.X, pady=10)
        action_button_frame.grid_columnconfigure((0, 1), weight=1)

        self.analyze_button = UIComponents.create_button(
            action_button_frame, t("action.analyze"),
            self.run_plan_thread, bootstyle="info", style="large"
        )
        self.analyze_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        # 查看详情主按钮：打开确认弹窗（逐组决策与执行在弹窗内完成）
        self.install_button = UIComponents.create_button(
            action_button_frame, t("ui.mod_install.view_details"),
            self._open_confirm_dialog, bootstyle="success",
            state="disabled", style="large"
        )
        self.install_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    # --- 分析（plan） ---

    def _on_files_added(self, added_paths: list[Path]):
        """文件添加后自动分析"""
        self.run_plan_thread()

    def run_plan_thread(self):
        """分析入口（线程安全：分析进行中忽略重复触发）"""
        if self._plan_running:
            return
        if not self.mod_file_list:
            messagebox.showerror(t("common.error"), t("message.list_empty"))
            return
        if self.app.is_adb_mode():
            messagebox.showwarning(t("common.warning"), t("message.mod_install.adb_unsupported"))
            return
        if not self.app.get_current_resource_dir():
            messagebox.showerror(t("common.error"), t("message.mod_install.no_game_dir"))
            return

        self._plan_running = True
        self.analyze_button.config(state=tk.DISABLED)
        self.run_in_thread(self._plan_worker)

    def _plan_worker(self):
        """后台分析：聚类分组 + 判定各组与游戏目录的关系（纯读不写盘）"""
        self.logger.status(t("status.processing_detailed"))
        game_dir = Path(self.app.get_current_resource_dir())
        self.groups = plan_mod_install(
            mod_paths=list(self.mod_file_list),
            game_resource_dir=get_search_dirs(game_dir),
            log=self.logger.log,
        )
        self._plan_running = False
        self.master.after(0, lambda: self.analyze_button.config(state=tk.NORMAL))
        if self.groups:
            self.master.after(0, lambda: self.install_button.config(state=tk.NORMAL))
        self.logger.status(t("status.done"))

    def _open_confirm_dialog(self):
        """打开确认弹窗，收集逐组决策后执行安装（执行逻辑见 _execute_install）"""
        if self._plan_running or not self.groups:
            return
        dialog = ModInstallDialog(self, self.app, self.groups)
        self.wait_window(dialog)
        if not dialog.confirmed:
            return

        selected = [
            group for group, var in zip(self.groups, dialog.decision_vars)
            if var.get() and dialog._installable(group)
        ]
        if not selected:
            return
        self._execute_install(selected)

    def _execute_install(self, selected_groups: list[ModGroup]):
        """执行安装（阶段5接入 execute_mod_install，当前仅记录决策）"""
        self.logger.log(t("log.mod_install.execute_start", count=len(selected_groups)))
