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
from ...models import AssetType, LogFunc
from ...mod_install import AssetInfo, InstallAction, ModGroup
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


@dataclass
class RenderResult:
    """单侧预览渲染结果（流水线产出，缓存与 UI 共用）"""
    image_path: Path | None = None                        # 预览图（无图/失败为 None）
    asset_infos: dict[Path, list[AssetInfo]] = field(default_factory=dict)  # bundle 路径 → 资产级元信息
    error: str = ""                                       # 失败原因（空串为成功）


# 渲染缓存（会话级）：key = 各 bundle 路径+mtime 组合 → 渲染结果，弹窗重复打开时直接复用
_render_cache: dict[str, RenderResult] = {}
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


def _fmt_size(n: int) -> str:
    """字节数 → 人类可读大小"""
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _render_bundles(bundle_paths: list[Path], viewer_path: Path | None, log: LogFunc) -> RenderResult:
    """解包 + 渲染单侧预览（后台线程调用，禁止 tk 操作）

    逐 bundle 提取 Texture2D/TextAsset 以建立资产级元信息；含 skel 且 SpineViewer
    可用时渲染 Spine 预览，否则回退为最大 Texture2D 导出图。
    """
    result = RenderResult()
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            all_textassets: list[Path] = []
            all_textures: list[Path] = []

            # 逐文件提取（子目录隔离同名资源），建立 路径 → 资产元信息 归属
            for bundle in bundle_paths:
                extract_dir = work_dir / bundle.stem
                extract_dir.mkdir(parents=True, exist_ok=True)  # 提取函数不自行建目录
                extracted = _extract_assets_from_bundle(
                    [bundle], extract_dir, {"TextAsset", "Texture2D"}, log,
                )
                infos: list[AssetInfo] = []
                for png in extracted[AssetType.Texture2D]:
                    try:
                        with PILImage.open(png) as im:
                            detail = f"{im.width}×{im.height}"
                    except Exception:
                        detail = ""
                    infos.append(AssetInfo(name=png.stem, type="Texture2D", detail=detail))
                    all_textures.append(png)
                for txt in extracted[AssetType.TextAsset]:
                    all_textassets.append(txt)  # 全部收集（.atlas 渲染时须与 skel 同目录）
                    if txt.suffix == ".skel":
                        version = get_skel_version(txt, log) or "?"
                        infos.append(AssetInfo(name=txt.name, type="TextAsset", detail=f"spine {version}"))
                result.asset_infos[bundle] = infos

            # 汇总渲染目录：skel/atlas/texture 须位于同一目录 SpineViewer 才能正确渲染
            # （目标 bundle 可能拆分存放，逐 bundle 子目录会导致找不到 atlas 而渲染出黑图）
            render_dir = work_dir / "_render"
            render_dir.mkdir()
            for asset_file in [*all_textassets, *all_textures]:
                shutil.copy2(asset_file, render_dir / asset_file.name)

            # 缓存输出目录（key 哈希隔离）
            out_dir = _get_cache_dir() / hashlib.md5(_cache_key(bundle_paths).encode()).hexdigest()
            out_dir.mkdir(parents=True, exist_ok=True)

            # Spine 类：渲染第一支 skel
            skel = next((f for f in render_dir.glob("*.skel")), None)
            if skel is not None and viewer_path is not None and viewer_path.exists():
                output_path = out_dir / "preview.png"
                ok, msg = SpineViewer.render_preview(
                    skel_path=skel,
                    output_path=output_path,
                    viewer_path=viewer_path,
                    render_options=RENDER_PRESET_LOW,
                    log=log,
                )
                if ok:
                    result.image_path = output_path
                else:
                    result.error = msg

            # 回退/纯贴图：取最大 Texture2D 导出图作预览
            if result.image_path is None and all_textures:
                biggest = max(all_textures, key=lambda p: p.stat().st_size)
                fallback = out_dir / "texture.png"
                PILImage.open(biggest).convert("RGBA").save(fallback)
                result.image_path = fallback

    except Exception as e:
        result.error = str(e)
    return result


class ModInstallDialog(StoppableDialog):
    """Mod 安装确认弹窗：左右翻页逐组决策（安装/跳过），确认后交由 Tab 执行

    打开后全部组的渲染任务按组顺序入队后台处理（§4.3），页面随时可进；
    未完成时预览区显示"渲染中..."，完成后经 after() 贴图并填充元信息树
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

        self._results: dict[tuple[int, str], RenderResult] = {}   # (组索引, current/new) → 渲染结果
        self._photo_refs: dict[tuple[int, str], ImageTk.PhotoImage] = {}  # 防止 PhotoImage 被回收
        self._task_queue: Queue[tuple[int, str, list[Path]]] = Queue()

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

    # --- 渲染流水线（§4.3：全量入队、后台依次处理、不做按页预取） ---

    def _start_pipeline(self):
        """构建渲染任务队列并启动后台线程；渲染开关关闭时不启动（§4.4 纯元信息展示）"""
        if not self.app.mod_install_render_preview_var.get():
            return
        for i, group in enumerate(self.groups):
            # 当前侧：DIRECT_REPLACE 的同名文件 + UPDATE 的搜索目标（均来自游戏目录）
            current_paths = [f.existing_path for f in group.files if f.existing_path is not None]
            current_paths += [p for p in group.target_paths if p not in current_paths]
            if current_paths:
                self._task_queue.put((i, "current", current_paths))
            self._task_queue.put((i, "new", [f.mod_path for f in group.files]))

        if self._task_queue.empty():
            return
        self.set_task_running(True)
        Thread(target=self._pipeline_worker, daemon=True).start()

    def _pipeline_worker(self):
        """后台依次消费任务队列；窗口关闭（should_stop）时停止后续任务"""
        viewer_str = self.app.spine_viewer_path_var.get().strip()
        viewer_path = Path(viewer_str) if viewer_str else None

        while not self._task_queue.empty() and not self.should_stop():
            group_index, side, bundle_paths = self._task_queue.get()
            cache_key = _cache_key(bundle_paths)
            result = _render_cache.get(cache_key)
            if result is None:
                result = _render_bundles(bundle_paths, viewer_path, self.app.logger.log)
                _render_cache[cache_key] = result
            if self.should_stop():
                break
            self.after(0, self._apply_result, group_index, side, result)

        self.after(0, lambda: self.set_task_running(False))

    def _apply_result(self, group_index: int, side: str, result: RenderResult):
        """主线程回调：缓存结果 + 贴图 + 填充元信息树"""
        if not self.winfo_exists():
            return
        self._results[(group_index, side)] = result
        group = self.groups[group_index]

        # 资产级元信息写回对应文件计划（仅 mod 侧；当前侧仅用于预览，§5）
        if side == "new":
            for f in group.files:
                infos = result.asset_infos.get(f.mod_path)
                if infos:
                    f.asset_infos = infos

        if group_index == self.current_index:
            self._refresh_preview(side, result)
            self._rebuild_meta_tree(group)

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
        for side, label in zip(("current", "new"), self.preview_labels):
            result = self._results.get((self.current_index, side))
            if result is not None:
                self._refresh_preview(side, result)
            else:
                waiting = self.app.mod_install_render_preview_var.get() and not self._task_queue.empty()
                label.configure(image="", text=t(
                    "ui.mod_install.preview_rendering" if waiting else "ui.mod_install.preview_none"
                ))

        # 决策单选（不可安装组禁用"安装此组"）
        decision = self.decision_vars[self.current_index]
        self.decision_var.set(decision.get())
        installable = self._installable(group)
        self.install_radio.configure(state=tk.NORMAL if installable else tk.DISABLED)

        self._rebuild_meta_tree(group)
        self._update_confirm_text()

    def _refresh_preview(self, side: str, result: RenderResult):
        """单侧预览刷新：贴图或显示占位文本（PhotoImage 须在主线程创建）"""
        label = self.preview_labels[0 if side == "current" else 1]
        if result.image_path is not None and result.image_path.exists():
            try:
                with PILImage.open(result.image_path) as im:
                    im.thumbnail((400, 280))
                    photo = ImageTk.PhotoImage(im)
                self._photo_refs[(self.current_index, side)] = photo
                label.configure(image=photo, text="")
                return
            except Exception:
                pass  # 图片读取失败按无预览处理
        text_key = "ui.mod_install.preview_failed" if result.error else "ui.mod_install.preview_none"
        label.configure(image="", text=t(text_key))

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

            # 资产级信息（流水线产出后追加）
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
