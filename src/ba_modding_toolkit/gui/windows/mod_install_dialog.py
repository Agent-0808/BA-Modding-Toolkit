# gui/windows/mod_install_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...mod_install import InstallAction, ModGroup
from ..components import UIComponents
from .base import StoppableDialog

# 组/文件动作 → 元信息"安装方式"展示键
_ACTION_KEYS = {
    InstallAction.DIRECT_REPLACE: "ui.mod_install.action_direct_replace",
    InstallAction.UPDATE: "ui.mod_install.action_update",
    InstallAction.NOT_FOUND: "ui.mod_install.action_not_found",
    InstallAction.ERROR: "ui.mod_install.action_error",
    InstallAction.MIXED: "ui.mod_install.action_mixed",
}


def _fmt_size(n: int) -> str:
    """字节数 → 人类可读大小"""
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


class ModInstallDialog(StoppableDialog):
    """Mod 安装确认弹窗：左右翻页逐组决策（安装/跳过），确认后交由 Tab 执行

    预览区在阶段3仅显示占位文本，后台渲染流水线（阶段4）就绪后经 master.after() 贴图
    """

    def __init__(self, master, app_instance: "App", groups: list[ModGroup]):
        super().__init__(master)
        self.app = app_instance
        self.groups = groups
        # 每组决策：True=安装；不可安装组（NOT_FOUND/ERROR）默认跳过且安装项禁用
        self.decision_vars = [
            tk.BooleanVar(value=self._installable(g)) for g in groups
        ]
        self.current_index = 0
        self.confirmed = False  # True = 用户点击确认，Tab 据此收集决策执行

        self._setup_window()
        self._create_widgets()
        self.show_group(0)

    # --- 构建界面 ---

    def _setup_window(self):
        self.title(t("ui.mod_install.dialog_title"))
        self.geometry("900x720")
        self.app.setup_icon(self)
        self.transient(self.master)

    def _create_widgets(self):
        main_frame = tb.Frame(self, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 1. 顶部导航：上一组 / 跳转列表 / 下一组
        nav_frame = tb.Frame(main_frame)
        nav_frame.pack(fill=tk.X, pady=(0, 5))

        self.prev_button = UIComponents.create_button(
            nav_frame, t("ui.mod_install.prev_group"),
            self._prev_group, bootstyle="secondary", width=10
        )
        self.prev_button.pack(side=tk.LEFT)

        self.jump_combo = tb.Combobox(nav_frame, state="readonly")
        self.jump_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.jump_combo.bind("<<ComboboxSelected>>", self._on_jump_selected)

        self.next_button = UIComponents.create_button(
            nav_frame, t("ui.mod_install.next_group"),
            self._next_group, bootstyle="secondary", width=10
        )
        self.next_button.pack(side=tk.RIGHT)

        # 2. 标题：core（角色名） · category
        self.title_label = tb.Label(main_frame, font=("", 12, "bold"), anchor=tk.CENTER)
        self.title_label.pack(fill=tk.X, pady=(0, 5))

        # 3. 预览区：当前（游戏目录） / 安装后（mod） 左右并排
        preview_frame = tb.Frame(main_frame)
        preview_frame.pack(fill=tk.X, pady=(0, 5))
        preview_frame.grid_columnconfigure((0, 1), weight=1)

        self.preview_labels: list[tb.Label] = []
        for col, key in enumerate(("ui.mod_install.preview_current", "ui.mod_install.preview_new")):
            lf = tb.Labelframe(preview_frame, text=t(key), padding=5)
            lf.grid(row=0, column=col, sticky="nsew", padx=(0, 5) if col == 0 else (5, 0))
            label = tb.Label(lf, text=t("ui.mod_install.preview_none"), anchor=tk.CENTER)
            label.configure(width=40)
            label.pack(fill=tk.BOTH, expand=True)
            self.preview_labels.append(label)

        # 4. 元信息区（Treeview 树形：文件 → 目标/属性 → 资产）
        meta_frame = tb.Labelframe(main_frame, text=t("ui.mod_install.meta_title"), padding=5)
        meta_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.meta_tree = tb.Treeview(meta_frame, show="tree", selectmode="none")
        meta_scroll = tb.Scrollbar(meta_frame, orient=tk.VERTICAL, command=self.meta_tree.yview)
        self.meta_tree.configure(yscrollcommand=meta_scroll.set)
        self.meta_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        meta_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 5. 决策区：安装此组 / 跳过（绑定当前页组的决策变量）
        decision_frame = tb.Frame(main_frame)
        decision_frame.pack(fill=tk.X, pady=(0, 5))

        self.decision_var = tk.BooleanVar(value=True)  # 当前页的临时绑定，切页时写入 decision_vars
        self.install_radio = tb.Radiobutton(
            decision_frame, text=t("ui.mod_install.decision_install"),
            variable=self.decision_var, value=True,
            command=self._on_decision_change,
        )
        self.install_radio.pack(side=tk.LEFT, padx=(0, 20))
        self.skip_radio = tb.Radiobutton(
            decision_frame, text=t("ui.mod_install.decision_skip"),
            variable=self.decision_var, value=False,
            command=self._on_decision_change,
        )
        self.skip_radio.pack(side=tk.LEFT)

        # 6. 底部按钮：确认安装（N/M） / 取消
        bottom_frame = tb.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)
        bottom_frame.grid_columnconfigure((0, 1), weight=1)

        self.confirm_button = UIComponents.create_button(
            bottom_frame, "", self._on_confirm,
            bootstyle="success", style="large"
        )
        self.confirm_button.grid(row=0, column=0, sticky="ew", padx=(0, 5))

        cancel_button = UIComponents.create_button(
            bottom_frame, t("common.cancel"), self.destroy,
            bootstyle="secondary", style="large"
        )
        cancel_button.grid(row=0, column=1, sticky="ew", padx=(5, 0))

    # --- 页面切换与刷新 ---

    @staticmethod
    def _installable(group: ModGroup) -> bool:
        """组是否可安装（NOT_FOUND/ERROR 不可安装）"""
        return group.group_action in (
            InstallAction.DIRECT_REPLACE, InstallAction.UPDATE, InstallAction.MIXED,
        )

    def _group_display(self, group: ModGroup) -> str:
        """跳转列表项展示：core（角色名）"""
        field = self.app.character_name_field_var.get()
        char_name = self.app.char_map.lookup(group.core, field) or ""
        return f"{group.core}（{char_name}）" if char_name else group.core

    def _decision_mark(self, index: int) -> str:
        """跳转列表的决策标记：✔ 安装 / ✘ 跳过 / – 不可安装"""
        if not self._installable(self.groups[index]):
            return "–"
        return "✔" if self.decision_vars[index].get() else "✘"

    def _refresh_jump_list(self):
        values = [
            f"{self._decision_mark(i)} {self._group_display(g)}"
            for i, g in enumerate(self.groups)
        ]
        self.jump_combo.configure(values=values)
        self.jump_combo.set(values[self.current_index])

    def show_group(self, index: int):
        """切换到指定组页面"""
        self.current_index = max(0, min(index, len(self.groups) - 1))
        group = self.groups[self.current_index]

        self._refresh_jump_list()
        self.prev_button.configure(state=tk.NORMAL if self.current_index > 0 else tk.DISABLED)
        self.next_button.configure(
            state=tk.NORMAL if self.current_index < len(self.groups) - 1 else tk.DISABLED
        )

        # 标题：core（角色名） · category
        title = self._group_display(group)
        if group.category:
            title += f" · {group.category}"
        self.title_label.configure(text=title)

        # 预览区（阶段3占位；阶段4渲染流水线就绪后替换）
        for label in self.preview_labels:
            label.configure(text=t("ui.mod_install.preview_none"), image="")

        # 决策单选（不可安装组禁用"安装此组"）
        decision = self.decision_vars[self.current_index]
        self.decision_var.set(decision.get())
        installable = self._installable(group)
        self.install_radio.configure(state=tk.NORMAL if installable else tk.DISABLED)

        self._rebuild_meta_tree(group)
        self._update_confirm_text()

    def _rebuild_meta_tree(self, group: ModGroup):
        """重建元信息树：mod 文件 → 目标/属性 → 资产（流水线动态填充）"""
        self.meta_tree.delete(*self.meta_tree.get_children())
        root = self.meta_tree.insert("", tk.END, text=self._group_display(group), open=True)

        for f in group.files:
            node = self.meta_tree.insert(
                root, tk.END, text=f"📦 {f.mod_path.name}", open=True,
            )
            action_text = t(_ACTION_KEYS.get(f.action, "ui.mod_install.action_error"))
            if f.action == InstallAction.DIRECT_REPLACE and f.existing_path is not None:
                detail = f"↔ {f.existing_path.name} · {action_text}"
                if f.need_crc_fix:
                    detail += f" · {t('ui.mod_install.need_crc_fix')}"
                detail += f" · {t('ui.mod_install.meta_size', mod_size=_fmt_size(f.mod_path.stat().st_size), existing_size=_fmt_size(f.existing_path.stat().st_size))}"
                self.meta_tree.insert(node, tk.END, text=detail)
            elif f.action == InstallAction.UPDATE and group.target_paths:
                self.meta_tree.insert(node, tk.END, text=f"{action_text}")
                for target in group.target_paths:
                    self.meta_tree.insert(node, tk.END, text=f"→ {target.name}")
            else:
                text = action_text
                if f.note:
                    text += f" · {f.note}"
                self.meta_tree.insert(node, tk.END, text=text)

            # 资产级信息（阶段3为空，流水线产出后追加）
            for info in f.asset_infos:
                self.meta_tree.insert(node, tk.END, text=f"[{info.type}] {info.name} — {info.detail}")

    def _update_confirm_text(self):
        install_count = sum(1 for i, g in enumerate(self.groups)
                            if self._installable(g) and self.decision_vars[i].get())
        self.confirm_button.configure(text=t(
            "ui.mod_install.confirm_install",
            install=install_count, total=len(self.groups),
        ))

    # --- 事件回调 ---

    def _prev_group(self):
        self.show_group(self.current_index - 1)

    def _next_group(self):
        self.show_group(self.current_index + 1)

    def _on_jump_selected(self, _event=None):
        index = self.jump_combo.current()
        if index >= 0:
            self.show_group(index)

    def _on_decision_change(self):
        """决策变更：写回当前组 + 刷新跳转列表标记与确认按钮统计"""
        self.decision_vars[self.current_index].set(self.decision_var.get())
        self._refresh_jump_list()
        self._update_confirm_text()

    def _on_confirm(self):
        installable = [i for i, g in enumerate(self.groups) if self._installable(g)]
        if not any(self.decision_vars[i].get() for i in installable):
            messagebox.showwarning(
                t("common.warning"),
                t("message.mod_install.nothing_selected"),
                parent=self,
            )
            return
        self.confirmed = True
        self.destroy()
