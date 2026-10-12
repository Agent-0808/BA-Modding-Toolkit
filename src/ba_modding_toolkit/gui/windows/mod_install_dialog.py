# gui/windows/mod_install_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from queue import Queue
from threading import Thread
import hashlib
import shutil
import tempfile

from PIL import Image as PILImage
from PIL import ImageTk

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...utils import no_log
from ...models import AssetType, LogFunc
from ...mod_install import InstallAction, ModGroup
from ...spine import RENDER_PRESET_LOW, SpineViewer, get_skel_version
from ...core import _extract_assets_from_bundle
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


@dataclass
class _SideAsset:
    """单侧提取出的一个资产（临时目录内的产物，仅流水线内使用）"""
    fname: str     # 提取文件名（含扩展名）
    type: str      # Texture2D / TextAsset
    detail: str    # "2220×3540" / "spine 4.2.33 · 45.6 KB"
    path: Path


@dataclass
class GroupRenderResult:
    """单个组的渲染流水线产出（缓存与 UI 共用，不含临时目录内的路径）"""
    current_image: Path | None = None  # 当前侧预览图
    new_image: Path | None = None      # 安装后侧预览图
    # 目标 bundle → 同名资产前后描述对比（仅列出描述有变化的，如贴图分辨率 / spine 版本）
    matched: dict[Path, list[tuple[str, str, str, str]]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)   # current/new → 渲染失败原因


# 渲染缓存（会话级）：key = 组内全部 bundle 路径+mtime 组合 → 流水线产出，弹窗重复打开时直接复用
_render_cache: dict[str, GroupRenderResult] = {}
_cache_dir: Path | None = None


def _get_cache_dir() -> Path:
    """渲染结果缓存目录（会话内惰性创建于系统临时目录）"""
    global _cache_dir
    if _cache_dir is None:
        _cache_dir = Path(tempfile.mkdtemp(prefix="ba_mod_install_preview_"))
    return _cache_dir


def _cache_key(bundle_paths: list[Path]) -> str:
    """缓存键：文件路径 + mtime（内容变更自动失效）"""
    return "|".join(f"{p}:{int(p.stat().st_mtime)}" for p in bundle_paths)


def _extract_bundle_assets(bundle: Path, extract_dir: Path, log: LogFunc) -> list[_SideAsset]:
    """构建单 bundle 的资产描述（子目录隔离同名资源）

    仅提取渲染所需的 Texture2D/TextAsset；Mesh/AnimationClip 不参与预览，
    是否有实际变化由执行阶段的 skip_unchanged 判定
    """
    extract_dir.mkdir(parents=True, exist_ok=True)  # _extract_assets_from_bundle 不自建目录
    extracted = _extract_assets_from_bundle([bundle], extract_dir, {"TextAsset", "Texture2D"}, log)
    assets: list[_SideAsset] = []
    for png in extracted[AssetType.Texture2D]:
        try:
            with PILImage.open(png) as im:
                detail = f"{im.width}×{im.height}"
        except Exception:
            detail = ""
        assets.append(_SideAsset(png.name, "Texture2D", detail, png))
    for txt in extracted[AssetType.TextAsset]:
        size = _fmt_size(txt.stat().st_size)
        if txt.suffix == ".skel":
            version = get_skel_version(txt, no_log) or "?"
            detail = f"spine {version} · {size}"
        else:
            detail = size  # atlas 等其他 TextAsset
        assets.append(_SideAsset(txt.name, "TextAsset", detail, txt))
    return assets


def _render_side(
    assets: list[_SideAsset],
    render_dir: Path,
    out_path: Path,
    viewer_path: Path | None,
    log: LogFunc,
) -> Path | None:
    """渲染单侧预览图：skel/atlas/texture 须位于同一目录（返回 None = 无图/失败）"""
    render_dir.mkdir(exist_ok=True)
    for a in assets:
        if a.type in ("Texture2D", "TextAsset"):  # 元数据型资产（Mesh 等）无文件，不参与渲染
            shutil.copy2(a.path, render_dir / a.fname)

    skel = next((f for f in render_dir.glob("*.skel")), None)
    if skel is not None:
        if viewer_path is None or not viewer_path.exists():
            return None
        ok, _msg = SpineViewer.render_preview(
            skel_path=skel,
            output_path=out_path,
            viewer_path=viewer_path,
            render_options=RENDER_PRESET_LOW,
            log=log,
        )
        return out_path if ok else None

    # 纯贴图回退：取最大 Texture2D 导出图
    textures = [a for a in assets if a.type == "Texture2D"]
    if textures:
        biggest = max(textures, key=lambda a: a.path.stat().st_size)
        PILImage.open(biggest.path).convert("RGBA").save(out_path)
        return out_path
    return None


def _process_group(group: ModGroup, viewer_path: Path | None, log: LogFunc) -> GroupRenderResult:
    """组级流水线：两侧解包 → 资产哈希对比 → 双侧渲染（后台线程调用，禁止 tk 操作）

    mod 侧资产按组池化后与每个目标 bundle 逐一对比（不做文件级精确配对，
    提供 assets 的 mod 文件本身即资产池，1 对多或 1 对 1 均可）。
    """
    result = GroupRenderResult()
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)

            # 目标侧：DIRECT_REPLACE 的同名文件 + UPDATE 的搜索目标（去重）
            target_paths: list[Path] = []
            for f in group.files:
                if f.existing_path is not None and f.existing_path not in target_paths:
                    target_paths.append(f.existing_path)
            for p in group.target_paths:
                if p not in target_paths:
                    target_paths.append(p)

            # 两侧逐 bundle 提取（子目录隔离同名资源）
            target_assets: dict[Path, list[_SideAsset]] = {}
            mod_assets: list[_SideAsset] = []
            for p in target_paths:
                target_assets[p] = _extract_bundle_assets(p, work_dir / "cur" / p.stem, log)
            for f in group.files:
                mod_assets.extend(
                    _extract_bundle_assets(f.mod_path, work_dir / "new" / f.mod_path.stem, log)
                )

            # mod 侧资产池（同名取后提取者）
            mod_pool: dict[str, _SideAsset] = {a.fname: a for a in mod_assets}

            # 渲染输出目录（缓存键 md5 隔离各组的 current.png/new.png）
            out_dir = _get_cache_dir() / hashlib.md5(_cache_key(
                [p for p in target_paths] + [f.mod_path for f in group.files]
            ).encode()).hexdigest()
            out_dir.mkdir(parents=True, exist_ok=True)

            # 同名同类型资产前后描述对比（仅列出描述有变化的，如贴图分辨率 / spine 版本）
            for target, before_list in target_assets.items():
                rows: list[tuple[str, str, str, str]] = []
                for a in before_list:
                    b = mod_pool.get(a.fname)
                    if b is not None and a.type == b.type and a.detail and a.detail != b.detail:
                        rows.append((a.type, a.fname, a.detail, b.detail))
                if rows:
                    result.matched[target] = rows

            # 双侧渲染（每侧汇总到同一目录，保证 skel/atlas/texture 完整）
            current_image = _render_side(
                [a for assets in target_assets.values() for a in assets],
                work_dir / "cur_render", out_dir / "current.png", viewer_path, log,
            )
            if current_image is None:
                result.errors["current"] = t("log.spine.preview_failed")
            result.current_image = current_image

            new_image = _render_side(
                mod_assets, work_dir / "new_render", out_dir / "new.png", viewer_path, log,
            )
            if new_image is None:
                result.errors["new"] = t("log.spine.preview_failed")
            result.new_image = new_image

    except Exception as e:
        result.errors["current"] = str(e)
        result.errors["new"] = str(e)
    return result


class ModInstallDialog(StoppableDialog):
    """Mod 安装确认弹窗：左右翻页逐组决策（安装/跳过），确认后交由 Tab 执行

    打开后全部组按组顺序入队后台流水线（§4.3），页面随时可进；未完成时预览区
    显示"渲染中..."，完成后经 after() 贴图并填充元信息树（含资产前后对比）
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

        self._results: dict[int, GroupRenderResult] = {}          # 组索引 → 流水线产出
        self._photo_refs: dict[tuple[int, str], ImageTk.PhotoImage] = {}  # 防止 PhotoImage 被回收
        self._task_queue: Queue[tuple[int, ModGroup]] = Queue()

        self._setup_window()
        self._create_widgets()
        self.show_group(0)
        self._start_pipeline()

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

        # 4. 元信息区（Treeview 树形：目标 bundle → 来源 mod → 资产对比）
        meta_frame = tb.Labelframe(main_frame, text=t("ui.mod_install.meta_title"), padding=5)
        meta_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self.meta_tree = tb.Treeview(meta_frame, show="tree", selectmode="browse")
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

    # --- 渲染流水线（§4.3：全量入队、后台依次处理、不做按页预取） ---

    def _start_pipeline(self):
        """构建组级任务队列并启动后台线程；渲染开关关闭时不启动（§4.4 纯元信息展示）"""
        if not self.app.mod_install_render_preview_var.get():
            return
        for i, group in enumerate(self.groups):
            self._task_queue.put((i, group))

        if self._task_queue.empty():
            return
        self.set_task_running(True)
        Thread(target=self._pipeline_worker, daemon=True).start()

    def _pipeline_worker(self):
        """后台依次消费任务队列；窗口关闭（should_stop）时停止后续任务"""
        viewer_str = self.app.spine_viewer_path_var.get().strip()
        viewer_path = Path(viewer_str) if viewer_str else None

        while not self._task_queue.empty() and not self.should_stop():
            group_index, group = self._task_queue.get()
            key = _cache_key(
                [f.mod_path for f in group.files]
                + [f.existing_path for f in group.files if f.existing_path is not None]
                + list(group.target_paths)
            )
            result = _render_cache.get(key)
            if result is None:
                result = _process_group(group, viewer_path, self.app.logger.log)
                _render_cache[key] = result
            if self.should_stop():
                break
            self.after(0, self._apply_result, group_index, result)

        self.after(0, lambda: self.set_task_running(False))

    def _apply_result(self, group_index: int, result: GroupRenderResult):
        """主线程回调：缓存结果 + 刷新当前页"""
        if not self.winfo_exists():
            return
        self._results[group_index] = result

        if group_index == self.current_index:
            self._refresh_previews(result)
            self._rebuild_meta_tree(self.groups[group_index])

    # --- 页面切换与刷新 ---

    @staticmethod
    def _installable(group: ModGroup) -> bool:
        """组是否可安装（NOT_FOUND/ERROR 不可安装）"""
        return group.group_action in (
            InstallAction.DIRECT_REPLACE, InstallAction.UPDATE, InstallAction.MIXED,
        )

    def _group_display(self, group: ModGroup) -> str:
        """跳转列表项展示：core（角色名）"""
        char_field = self.app.character_name_field_var.get()
        char_name = self.app.char_map.lookup(group.core, char_field) or ""
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

        # 预览区：已有结果显示贴图，否则按流水线状态显示占位文本
        result = self._results.get(self.current_index)
        if result is not None:
            self._refresh_previews(result)
        else:
            waiting = self.app.mod_install_render_preview_var.get() and not self._task_queue.empty()
            text_key = "ui.mod_install.preview_rendering" if waiting else "ui.mod_install.preview_none"
            for label in self.preview_labels:
                label.configure(image="", text=t(text_key))

        # 决策单选（不可安装组禁用"安装此组"）
        decision = self.decision_vars[self.current_index]
        self.decision_var.set(decision.get())
        installable = self._installable(group)
        self.install_radio.configure(state=tk.NORMAL if installable else tk.DISABLED)

        self._rebuild_meta_tree(group)
        self._update_confirm_text()

    def _refresh_previews(self, result: GroupRenderResult):
        """双侧预览刷新为整组渲染图（PhotoImage 须在主线程创建）"""
        for side, image in (("current", result.current_image), ("new", result.new_image)):
            label = self.preview_labels[0 if side == "current" else 1]
            if image is not None and image.exists():
                try:
                    with PILImage.open(image) as im:
                        im.thumbnail((400, 280))
                        photo = ImageTk.PhotoImage(im)
                    self._photo_refs[(self.current_index, side)] = photo
                    label.configure(image=photo, text="")
                    continue
                except Exception:
                    pass  # 图片读取失败按无预览处理
            text_key = (
                "ui.mod_install.preview_failed" if side in result.errors
                else "ui.mod_install.preview_none"
            )
            label.configure(image="", text=t(text_key))

    def _rebuild_meta_tree(self, group: ModGroup):
        """重建元信息树：目标 bundle（只列一次）→ 同名资产前后描述对比"""
        self.meta_tree.delete(*self.meta_tree.get_children())
        root = self.meta_tree.insert("", tk.END, text=self._group_display(group), open=True)

        # 目标节点：DIRECT_REPLACE 的同名文件 + UPDATE 的搜索目标（均只出现一次）
        target_nodes: dict[Path, str] = {}  # 目标路径 → 树节点 id
        for f in group.files:
            if f.existing_path is None or f.existing_path in target_nodes:
                continue
            detail = t(_ACTION_KEYS[f.action])
            if f.need_crc_fix:
                detail += f" · {t('ui.mod_install.need_crc_fix')}"
            detail += f" · {t('ui.mod_install.meta_size', mod_size=_fmt_size(f.mod_path.stat().st_size), existing_size=_fmt_size(f.existing_path.stat().st_size))}"
            node = self.meta_tree.insert(
                root, tk.END, text=f"📦 {f.existing_path.name} · {detail}", open=True,
            )
            target_nodes[f.existing_path] = node
        for target in group.target_paths:
            if target in target_nodes:
                continue
            node = self.meta_tree.insert(
                root, tk.END,
                text=f"📦 {target.name} · {t(_ACTION_KEYS[InstallAction.UPDATE])}",
                open=True,
            )
            target_nodes[target] = node

        # NOT_FOUND/ERROR 文件（无目标可对比）
        for f in group.files:
            if f.action in (InstallAction.NOT_FOUND, InstallAction.ERROR):
                text = t(_ACTION_KEYS[f.action])
                if f.note:
                    text += f" · {f.note}"
                self.meta_tree.insert(root, tk.END, text=f"📦 {f.mod_path.name} · {text}")

        # 同名资产前后描述对比（流水线产出后追加：贴图分辨率 / spine 版本等）
        result = self._results.get(self.current_index)
        if result is not None:
            for target, rows in result.matched.items():
                node = target_nodes.get(target)
                if node is None:
                    continue
                for type_name, fname, before, after in rows:
                    self.meta_tree.insert(
                        node, tk.END, text=f"[{type_name}] {fname} — {before} → {after}",
                    )

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
