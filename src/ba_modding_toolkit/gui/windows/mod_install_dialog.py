# gui/windows/mod_install_dialog.py

import tkinter as tk
import ttkbootstrap as tb
from tkinter import messagebox
from pathlib import Path
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from enum import StrEnum
from queue import Queue
from threading import Thread
import hashlib
import shutil
import tempfile

from PIL import Image as PILImage

if TYPE_CHECKING:
    from ..app import App

from ...i18n import t
from ...utils import no_log
from ...models import AnimCheckOptions, AssetType, LogFunc
from ...bundle import Bundle
from ...mod_install import InstallAction, ModGroup
from ...spine import RENDER_PRESET_HIGH, SpineViewer, get_skel_version, check_skel_animation_diff
from ...core import _extract_assets_from_bundle
from ..components import UIComponents, ZoomableCanvas
from .base import StoppableDialog

# 组/文件动作 → 元信息"安装方式"展示键
_ACTION_KEYS = {
    InstallAction.DIRECT_REPLACE: "ui.mod_install.action_direct_replace",
    InstallAction.UPDATE: "ui.mod_install.action_update",
    InstallAction.NOT_FOUND: "ui.mod_install.action_not_found",
    InstallAction.ERROR: "ui.mod_install.action_error",
    InstallAction.MIXED: "ui.mod_install.action_mixed",
}


class _RowTag(StrEnum):
    """元信息树资产行的状态标签（Treeview tag，用于整行着色）"""
    DIFF = "diff"        # 内容哈希有差异（前后描述对比 / 内容有变化）
    SAME = "same"        # 内容哈希一致（无变化）
    REPLACE = "replace"  # 将被替换（Mesh/AnimationClip 交集）


_ROW_TAG_COLORS: dict[_RowTag, str] = {
    _RowTag.DIFF: "#e67e22",     # 橙：有差异
    _RowTag.SAME: "#95a5a6",     # 灰：无变化
    _RowTag.REPLACE: "#3498db",  # 蓝：将被替换
}


def _fmt_size(n: int) -> str:
    """字节数 → 人类可读大小"""
    if n >= 1024 * 1024:
        return f"{n / 1024 / 1024:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _sha(path: Path) -> str:
    """文件内容短哈希（提取产物已在磁盘上，仅用于前后一致性展示判定）"""
    return hashlib.sha1(path.read_bytes()).hexdigest()[:12]


@dataclass
class _SideAsset:
    """单侧提取出的一个资产（临时目录内的产物，仅流水线内使用）"""
    fname: str     # 提取文件名（含扩展名）
    type: str      # Texture2D / TextAsset
    detail: str    # "2220×3540" / "spine 4.2.33"（skel 行省略 size 段，动画差异在行组装时追加）
    sha: str       # 内容短哈希（detail 相同但内容有差异时仍能列出）
    path: Path


@dataclass
class GroupRenderResult:
    """单个组的渲染流水线产出（缓存与 UI 共用，不含临时目录内的路径）"""
    current_image: Path | None = None  # 当前侧预览图
    new_image: Path | None = None      # 安装后侧预览图
    # 目标 bundle → 资产级行 (文本, 状态标签)，流水线产出即展示文本
    matched: dict[Path, list[tuple[str, _RowTag]]] = field(default_factory=dict)
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
        assets.append(_SideAsset(png.name, "Texture2D", detail, _sha(png), png))
    for txt in extracted[AssetType.TextAsset]:
        if txt.suffix == ".skel":
            # size 段信息量低（一位小数，字节级差异也显示相同大小），省略
            detail = f"spine {get_skel_version(txt, no_log) or '?'}"
        else:
            detail = _fmt_size(txt.stat().st_size)  # atlas 等其他 TextAsset
        assets.append(_SideAsset(txt.name, "TextAsset", detail, _sha(txt), txt))
    return assets


def _render_side(
    assets: list[_SideAsset],
    render_dir: Path,
    out_path: Path,
    viewer_path: Path | None,
    log: LogFunc,
) -> tuple[Path | None, str | None]:
    """渲染单侧预览图：skel/atlas/texture 须位于同一目录

    Returns:
        tuple[Path | None, str | None]: (预览图路径, 失败原因)；无图或未配置 viewer 时原因可能为 None
    """
    render_dir.mkdir(exist_ok=True)
    for a in assets:
        if a.type in ("Texture2D", "TextAsset"):  # 元数据型资产（Mesh 等）无文件，不参与渲染
            shutil.copy2(a.path, render_dir / a.fname)

    skel = next((f for f in render_dir.glob("*.skel")), None)
    if skel is not None:
        if viewer_path is None or not viewer_path.exists():
            return None, None
        ok, msg = SpineViewer.render_preview(
            skel_path=skel,
            output_path=out_path,
            viewer_path=viewer_path,
            render_options=RENDER_PRESET_HIGH,  # 高画质：耗时与低画质接近，临时文件体积可忽略
            log=log,
        )
        return (out_path if ok else None), (None if ok else msg)

    # 纯贴图回退：取最大 Texture2D 导出图
    textures = [a for a in assets if a.type == "Texture2D"]
    if textures:
        biggest = max(textures, key=lambda a: a.path.stat().st_size)
        PILImage.open(biggest.path).convert("RGBA").save(out_path)
        return out_path, None
    return None, None


def _process_group(
    group: ModGroup, viewer_path: Path | None, anim_check: AnimCheckOptions, log: LogFunc,
) -> GroupRenderResult:
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

            # 同名同类型资产全部列出（UPDATE 下 apply_patch 只替换两侧交集），
            # 内容哈希有差异的行标注前后变化，无差异的标注"无变化"
            # Mesh/AnimationClip 不提取，仅枚举两侧交集并列出"将被替换"
            _non_preview_types = {AssetType.Mesh, AssetType.AnimationClip}
            non_preview_mod: set[tuple[str, str]] = set()
            for f in group.files:
                non_preview_mod |= Bundle.list_asset_names(f.mod_path, _non_preview_types)
            for target, before_list in target_assets.items():
                # (类型名, 名字, 展示文本, 标签)：先收集再按"类型→名字"统一排序
                rows: list[tuple[str, str, str, _RowTag]] = []
                for a in before_list:
                    b = mod_pool.get(a.fname)
                    if b is None or a.type != b.type:
                        continue
                    if a.sha != b.sha:
                        if a.detail != b.detail:
                            detail = f"{a.detail} → {b.detail}"
                        else:
                            detail = f"{a.detail} · {t('ui.mod_install.diff_content_changed')}"
                        # skel 行预检动画差异（缺失动画是执行阶段最常见的警告来源，提前可见）
                        if a.fname.endswith(".skel") and anim_check.is_valid():
                            missing = check_skel_animation_diff(b.path, a.path, anim_check.viewer_path, log)
                            if missing:
                                detail += f" · {t('ui.mod_install.diff_missing_anims', count=len(missing))}"
                        rows.append((a.type, a.fname, f"[{a.type}] {a.fname} — {detail}", _RowTag.DIFF))
                    else:
                        rows.append((a.type, a.fname, (
                            f"[{a.type}] {a.fname} — {a.detail} · "
                            f"{t('ui.mod_install.diff_unchanged')}"
                        ), _RowTag.SAME))
                non_preview_target = Bundle.list_asset_names(target, _non_preview_types)
                for name, type_name in non_preview_target & non_preview_mod:
                    rows.append((type_name, name, f"[{type_name}] {name} — {t('ui.mod_install.diff_will_replace')}", _RowTag.REPLACE))
                rows.sort(key=lambda r: (r[0], r[1]))
                result.matched[target] = [(text, tag) for _, _, text, tag in rows]

            # 双侧渲染（每侧汇总到同一目录，保证 skel/atlas/texture 完整）
            current_image, err = _render_side(
                [a for assets in target_assets.values() for a in assets],
                work_dir / "cur_render", out_dir / "current.png", viewer_path, log,
            )
            if current_image is None:
                result.errors["current"] = err or t("ui.mod_install.preview_failed")
            result.current_image = current_image

            new_image, err = _render_side(
                mod_assets, work_dir / "new_render", out_dir / "new.png", viewer_path, log,
            )
            if new_image is None:
                result.errors["new"] = err or t("ui.mod_install.preview_failed")
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
        self._render_done = 0                                     # 已完成渲染的组数（进度展示）
        self._task_queue: Queue[tuple[int, ModGroup]] = Queue()

        self._setup_window()
        self._create_widgets()
        self.show_group(0)
        self._start_pipeline()

    # --- 构建界面 ---

    def _setup_window(self):
        self.title(t("ui.mod_install.dialog_title"))
        self.geometry("900x1000")
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

        # 渲染进度条（流水线启动时才显示）
        self.progress_bar = tb.Progressbar(main_frame, mode="determinate")

        self.next_button = UIComponents.create_button(
            nav_frame, t("ui.mod_install.next_group"),
            self._next_group, bootstyle="secondary", width=10
        )
        self.next_button.pack(side=tk.RIGHT)

        # 2. 标题：prefix（+ 疑似已安装标记）
        self.title_label = tb.Label(main_frame, font=("", 12, "bold"), anchor=tk.CENTER)
        self.title_label.pack(fill=tk.X, pady=(0, 5))

        # 3. 预览区：当前（游戏目录） / 安装后（mod） 左右并排（滚轮缩放、拖拽平移）
        preview_frame = tb.Frame(main_frame)
        preview_frame.pack(fill=tk.X, pady=(0, 5))
        preview_frame.grid_columnconfigure((0, 1), weight=1)

        self.preview_canvases: list[ZoomableCanvas] = []
        for col, key in enumerate(("ui.mod_install.preview_current", "ui.mod_install.preview_new")):
            lf = tb.Labelframe(preview_frame, text=t(key), padding=5)
            lf.grid(row=0, column=col, sticky="nsew", padx=(0, 5) if col == 0 else (5, 0))
            canvas = ZoomableCanvas(lf, width=400, height=500)
            canvas.pack(fill=tk.BOTH, expand=True)
            self.preview_canvases.append(canvas)

        # 4. 底部锚定：决策区与确认按钮自下而上排列，元信息区不抢占剩余空间
        # （side=BOTTOM 先打包者贴底，故先确认按钮后决策区）
        bottom_frame = tb.Frame(main_frame)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)
        # uniform 使两列严格等宽（不随文本长度偏移）
        bottom_frame.grid_columnconfigure((0, 1), weight=1, uniform="bottom")

        decision_frame = tb.Frame(main_frame)
        decision_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(0, 5))

        # 5. 元信息区（Treeview 树形：目标 bundle → 来源 mod → 资产对比，行数随内容自适应）
        meta_frame = tb.Labelframe(main_frame, text=t("ui.mod_install.meta_title"), padding=5)
        meta_frame.pack(fill=tk.X, pady=(0, 5))

        self.meta_tree = tb.Treeview(meta_frame, show="tree", selectmode="browse")
        # 资产行状态整行着色
        for tag, color in _ROW_TAG_COLORS.items():
            self.meta_tree.tag_configure(tag, foreground=color)
        meta_scroll = tb.Scrollbar(meta_frame, orient=tk.VERTICAL, command=self.meta_tree.yview)
        self.meta_tree.configure(yscrollcommand=meta_scroll.set)
        self.meta_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        meta_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 6. 决策区：安装此组 / 跳过（大按钮式单选，选中侧蓝色高亮，绑定当前页组的决策变量）
        self.decision_var = tk.BooleanVar(value=True)  # 当前页的临时绑定，切页时写入 decision_vars
        # uniform 使两列严格等宽（不随文本长度偏移）
        decision_frame.grid_columnconfigure((0, 1), weight=1, uniform="decision")
        self.install_radio = tb.Radiobutton(
            decision_frame, text=f"✔ {t('ui.mod_install.decision_install')}",
            variable=self.decision_var, value=True,
            command=self._on_decision_change,
            bootstyle="outline-toolbutton",
        )
        self.install_radio.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.skip_radio = tb.Radiobutton(
            decision_frame, text=f"✘ {t('ui.mod_install.decision_skip')}",
            variable=self.decision_var, value=False,
            command=self._on_decision_change,
            bootstyle="outline-toolbutton",
        )
        self.skip_radio.grid(row=0, column=1, sticky="ew")

        # 7. 底部按钮：确认安装（N/M） / 取消
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
        # 进度条 + 主窗口状态（渲染在后台逐组进行，进度在 _apply_result 回调中推进）
        self.progress_bar.configure(maximum=len(self.groups), value=0)
        self.progress_bar.pack(fill=tk.X, pady=(0, 5))
        self.app.logger.status(t("status.render_progress", done=0, total=len(self.groups)))
        self.set_task_running(True)
        Thread(target=self._pipeline_worker, daemon=True).start()

    def _pipeline_worker(self):
        """后台依次消费任务队列；窗口关闭（should_stop）时停止后续任务"""
        viewer_str = self.app.spine_viewer_path_var.get().strip()
        viewer_path = Path(viewer_str) if viewer_str else None
        anim_check = self.app.build_anim_check_options()

        while not self._task_queue.empty() and not self.should_stop():
            group_index, group = self._task_queue.get()
            key = _cache_key(
                [f.mod_path for f in group.files]
                + [f.existing_path for f in group.files if f.existing_path is not None]
                + list(group.target_paths)
            )
            result = _render_cache.get(key)
            if result is None:
                result = _process_group(group, viewer_path, anim_check, self.app.logger.log)
                _render_cache[key] = result
            if self.should_stop():
                break
            self.after(0, self._apply_result, group_index, result)

        self.after(0, lambda: self.set_task_running(False))

    def _apply_result(self, group_index: int, result: GroupRenderResult):
        """主线程回调：缓存结果 + 推进渲染进度 + 刷新当前页"""
        if not self.winfo_exists():
            return
        self._results[group_index] = result

        # 渲染进度：弹窗内进度条 + 主窗口状态栏
        total = len(self.groups)
        self._render_done += 1
        self.progress_bar.configure(value=self._render_done)
        self.app.logger.status(t("status.render_progress", done=self._render_done, total=total))
        if self._render_done >= total:
            self.progress_bar.pack_forget()
            self.app.logger.status(t("status.done"))

        if group_index == self.current_index:
            self._refresh_previews(result)
            self._rebuild_meta_tree(self.groups[group_index])
            # 「疑似已安装」标记依赖流水线产出，结果到达后刷新标题与跳转列表
            self._refresh_title()
            self._refresh_jump_list()

    # --- 页面切换与刷新 ---

    @staticmethod
    def _installable(group: ModGroup) -> bool:
        """组是否可安装（NOT_FOUND/ERROR 不可安装）"""
        return group.group_action in (
            InstallAction.DIRECT_REPLACE, InstallAction.UPDATE, InstallAction.MIXED,
        )

    def _group_display(self, group: ModGroup) -> str:
        """跳转列表项/页面标题展示：[category] 角色名 (core)"""
        char_field = self.app.character_name_field_var.get()
        char_name = self.app.char_map.lookup(group.core, char_field) or ""
        name = f"{char_name} ({group.core})" if char_name else group.core
        return f"[{group.category}] {name}" if group.category else name

    def _decision_mark(self, index: int) -> str:
        """跳转列表的决策标记：✔ 安装 / ✘ 跳过 / – 不可安装"""
        if not self._installable(self.groups[index]):
            return "–"
        return "✔" if self.decision_vars[index].get() else "✘"

    def _likely_installed(self, index: int) -> bool:
        """「疑似已安装」：流水线产出的全部资产对比行均为无变化（Mesh/AnimationClip
        未参与哈希对比，权威判定仍在执行阶段的 skip_unchanged）"""
        result = self._results.get(index)
        if result is None or not result.matched:
            return False
        rows = [tag for rows_ in result.matched.values() for _, tag in rows_]
        return bool(rows) and all(tag == _RowTag.SAME for tag in rows)

    def _refresh_title(self):
        """标题：prefix（+ 疑似已安装标记）"""
        title = self.groups[self.current_index].prefix or self.groups[self.current_index].core
        if self._likely_installed(self.current_index):
            title += f" · {t('ui.mod_install.likely_installed')}"
        self.title_label.configure(text=title)

    def _refresh_jump_list(self):
        values = [
            f"{self._decision_mark(i)} {self._group_display(g)}"
            + (" ≈" if self._likely_installed(i) else "")  # 疑似已安装标记
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

        # 标题：prefix（+ 疑似已安装标记）
        self._refresh_title()

        # 预览区：已有结果显示贴图，否则按流水线状态显示占位文本
        result = self._results.get(self.current_index)
        if result is not None:
            self._refresh_previews(result)
        else:
            waiting = self.app.mod_install_render_preview_var.get() and not self._task_queue.empty()
            text_key = "ui.mod_install.preview_rendering" if waiting else "ui.mod_install.preview_none"
            for canvas in self.preview_canvases:
                canvas.set_image(None, t(text_key))

        # 决策单选（不可安装组禁用"安装此组"）
        decision = self.decision_vars[self.current_index]
        self.decision_var.set(decision.get())
        installable = self._installable(group)
        self.install_radio.configure(state=tk.NORMAL if installable else tk.DISABLED)

        self._rebuild_meta_tree(group)
        self._update_confirm_text()

    def _refresh_previews(self, result: GroupRenderResult):
        """双侧预览刷新为整组渲染图（缩放平移由 ZoomableCanvas 处理，仅主线程调用）"""
        for side, image in (("current", result.current_image), ("new", result.new_image)):
            canvas = self.preview_canvases[0 if side == "current" else 1]
            path = image if image is not None and image.exists() else None
            # 失败时优先显示真实原因（msg 已本地化），无原因时回退到通用占位
            placeholder = result.errors.get(side) or t("ui.mod_install.preview_none")
            canvas.set_image(path, placeholder)

    def _rebuild_meta_tree(self, group: ModGroup):
        """重建元信息树：目标 bundle（只列一次）→ 同名资产前后描述对比"""
        self.meta_tree.delete(*self.meta_tree.get_children())
        # 根节点与页面标题一致，用 prefix（category 仅保留在跳转下拉）
        root = self.meta_tree.insert("", tk.END, text=group.prefix or group.core, open=True)

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

        # 同名资产前后对比 / 将被替换（流水线产出后追加的 (行文本, 状态标签)）
        result = self._results.get(self.current_index)
        if result is not None:
            for target, rows in result.matched.items():
                node = target_nodes.get(target)
                if node is None:
                    continue
                for text, tag in rows:
                    self.meta_tree.insert(node, tk.END, text=text, tags=(tag,))

        # 行数随内容自适应（上限 20 行，超出走滚动条；下方留白由布局让出）
        def _visible_rows(item: str) -> int:
            count = 0
            for child in self.meta_tree.get_children(item):
                count += 1 + _visible_rows(child)
            return count
        self.meta_tree.configure(height=max(1, min(1 + _visible_rows(root), 20)))

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
