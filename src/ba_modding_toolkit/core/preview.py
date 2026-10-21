# core/preview.py
"""Spine 预览图渲染（单任务 / 批量 / 全量）"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
import tempfile

from ..i18n import t
from ..utils import no_log, throttle_progress
from ..spine import SpineViewer, RenderOptions, RENDER_PRESET_HIGH, RENDER_PRESET_LOW
from ..models import LogFunc, ProgressCallback
from ..naming import parse_filename
from ..searching import list_bundle_files
from .extraction import extract_assets_from_bundle, AssetType

# 渲染分类（仅 Spine 资源）
RENDER_CATEGORIES = {"spinecharacters", "spinelobbies", "spinebackground"}


def render_spine_preview_from_bundle(
    bundle_path: Path | list[Path],
    output_dir: Path,
    viewer_path: Path,
    output_filename: str | None = None,
    render_options: RenderOptions = RENDER_PRESET_HIGH,
    log: LogFunc = no_log,
) -> tuple[bool, str, list[Path]]:
    """
    从 bundle 文件渲染 Spine 预览图。

    Args:
        bundle_path: bundle 文件路径（单个或列表）
        output_dir: 输出目录
        viewer_path: SpineViewerCLI 路径
        output_filename: 输出文件名（不含扩展名），用于自定义命名。None 则使用 skel 文件名
        render_options: 渲染参数（默认高画质）
        log: 日志记录函数

    Returns:
        tuple[bool, str, list[Path]]: (是否成功, 状态消息, 渲染输出的文件路径列表)
    """

    # 统一处理为列表
    bundle_paths = [bundle_path] if isinstance(bundle_path, Path) else bundle_path

    if not viewer_path.exists():
        msg = t("log.file.not_exist", path=viewer_path)
        log(f'❌ {msg}')
        return False, msg, []

    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        work_dir = Path(temp_dir)
        log(f'  > {t("log.extractor.using_temp_dir", path=work_dir)}')

        # 阶段 1: 提取资源
        log(f'\n--- {t("log.section.extract_to_temp")} ---')
        extracted_files = extract_assets_from_bundle(
            bundle_paths, work_dir, {"TextAsset", "Texture2D"}, log
        )

        # 获取 skel 文件
        skel_files = [f for f in extracted_files[AssetType.TextAsset] if f.suffix == '.skel']

        if not skel_files:
            msg = t("log.spine.no_skel_found")
            log(f'⚠️ {msg}')
            return False, msg, []

        # 阶段 2: 渲染预览图
        log(f'\n--- {t("log.section.render_preview")} ---')
        success_count = 0
        rendered_paths: list[Path] = []

        for idx, skel_path in enumerate(skel_files):
            # 确定输出文件名
            if output_filename:
                # 如果指定了输出文件名，多个 skel 时添加后缀
                if len(skel_files) > 1:
                    filename = f"{output_filename}_{idx}"
                else:
                    filename = output_filename
            else:
                filename = skel_path.stem

            output_path = output_dir / f"{filename}.png"

            # 渲染预览图
            skel_success, msg = SpineViewer.render_preview(
                skel_path=skel_path,
                output_path=output_path,
                viewer_path=viewer_path,
                render_options=render_options,
                log=log
            )

            if skel_success:
                success_count += 1
                rendered_paths.append(output_path)

        if success_count > 0:
            msg = t("log.spine.preview_complete", count=success_count)
            log(f'\n✓ {msg}')
            return True, msg, rendered_paths
        else:
            msg = t("log.spine.preview_failed")
            log(f'\n❌ {msg}')
            return False, msg, []


@dataclass
class RenderTask:
    """单个预览渲染任务"""
    name: str                                  # 输出文件名（prefix，需唯一）
    files: list[Path]                          # 首选 bundle 文件
    fallback_files: list[Path] | None = None   # 渲染失败时的回退文件（None 表示不回退）


def _render_task(
    task: RenderTask,
    output_dir: Path,
    viewer_path: Path,
    render_options: RenderOptions,
    log: LogFunc,
) -> tuple[bool, list[Path]]:
    """执行单个渲染任务：首选文件失败且有回退文件时重试一次"""
    success, _, rendered_paths = render_spine_preview_from_bundle(
        bundle_path=task.files,
        output_dir=output_dir,
        viewer_path=viewer_path,
        output_filename=task.name,
        render_options=render_options,
        log=log,
    )

    # 失败时尝试包含所有同 prefix 的文件（可能有原始 skel/atlas）
    if not success and task.fallback_files and task.fallback_files != task.files:
        log(f"  > {t('log.report.render_retry', prefix=task.name)}")
        success, _, rendered_paths = render_spine_preview_from_bundle(
            bundle_path=task.fallback_files,
            output_dir=output_dir,
            viewer_path=viewer_path,
            output_filename=task.name,
            render_options=render_options,
            log=log,
        )

    return success, rendered_paths


def render_spine_previews_batch(
    tasks: list[RenderTask],
    output_dir: Path,
    viewer_path: Path,
    render_options: RenderOptions = RENDER_PRESET_LOW,
    log: LogFunc = no_log,
    progress_callback: ProgressCallback | None = None,
    max_workers: int = 1,
) -> dict[str, list[Path]]:
    """
    批量渲染预览图（单路径实现，max_workers=1 时顺序执行）。

    每个任务调用外部 SpineViewerCLI 子进程，子进程调用会释放 GIL，
    多线程可获得真实并行收益；但渲染本身吃 CPU/GPU/内存，线程数建议 1~4。

    Args:
        tasks: 渲染任务列表（name 需唯一，作为输出文件名）
        output_dir: 输出目录
        viewer_path: SpineViewerCLI 路径
        render_options: 渲染参数
        log: 日志函数
        progress_callback: 进度回调（按任务推进，任务完成后调用）
        max_workers: 并行线程数

    Returns:
        dict[str, list[Path]]: 成功任务名 → 渲染输出的文件路径列表
    """
    results: dict[str, list[Path]] = {}
    total = len(tasks)
    completed = 0

    output_dir.mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as executor:
        futures = {
            executor.submit(_render_task, task, output_dir, viewer_path, render_options, log): task
            for task in tasks
        }
        # 计数与进度更新只在主线程（本循环）中进行，无需加锁
        for future in as_completed(futures):
            task = futures[future]
            try:
                success, rendered_paths = future.result()
            except Exception as e:
                success, rendered_paths = False, []
                log(t("log.batch.process_failed", filename=task.name, message=str(e)))

            if success:
                results[task.name] = rendered_paths

            completed += 1
            if progress_callback:
                progress_callback(completed, total, task.name)

    return results


def render_all_spine_previews(
    game_dir: Path,
    output_dir: Path,
    viewer_path: Path,
    render_options: RenderOptions = RENDER_PRESET_LOW,
    render_categories: set[str] = RENDER_CATEGORIES,
    log: LogFunc = no_log,
    progress_callback: ProgressCallback | None = None,
    max_workers: int = 1,
) -> tuple[int, int]:
    """
    批量渲染游戏目录下全部 Spine 资源的预览图（不限 Mod 文件）。

    按 parse_filename 解析出的 category 筛选（默认 RENDER_CATEGORIES），
    再按 prefix 聚合后逐组渲染（同组 bundle 合并，保证 skel/atlas/texture 完整）。

    Args:
        game_dir: 游戏资源目录
        output_dir: 预览图输出目录
        viewer_path: SpineViewerCLI 路径
        render_options: 渲染参数（默认低画质）
        render_categories: 需要渲染的分类集合（默认 RENDER_CATEGORIES）
        log: 日志函数
        progress_callback: 进度回调函数（按 prefix 组推进）
        max_workers: 并行渲染线程数

    Returns:
        tuple[int, int]: (渲染成功的组数, 总组数)
    """
    log(f"--- {t('log.batch_preview.scan_start')} ---")

    # 节流进度回调，避免海量文件时的高频 GUI 更新
    if progress_callback:
        progress_callback = throttle_progress(progress_callback)

    # 1. 扫描 bundle 文件
    items = list_bundle_files(game_dir)
    if not items:
        log(f"⚠️ {t('message.no_bundle_found')}")
        return 0, 0

    log(f"{t('log.report.bundle_count', count=len(items))}")

    # 2. 解析文件名，筛选 Spine 分类并按 prefix 聚合
    grouped: dict[str, list[Path]] = {}
    for item in items:
        parsed = parse_filename(item.path.name)
        if parsed.category in render_categories and parsed.prefix:
            grouped.setdefault(parsed.prefix, []).append(item.path)

    if not grouped:
        log(f"⚠️ {t('log.batch_preview.no_spine_found')}")
        return 0, 0

    prefixes = sorted(grouped)
    total = len(prefixes)
    log(f"{t('log.batch_preview.group_count', count=total)}")

    # 3. 批量渲染（文件名 = prefix，重复渲染自动覆盖）
    output_dir.mkdir(parents=True, exist_ok=True)

    # 重置进度条（渲染阶段）
    if progress_callback:
        progress_callback(0, total, "")

    tasks = [RenderTask(prefix, grouped[prefix]) for prefix in prefixes]
    results = render_spine_previews_batch(
        tasks=tasks,
        output_dir=output_dir,
        viewer_path=viewer_path,
        render_options=render_options,
        log=log,
        progress_callback=progress_callback,
        max_workers=max_workers,
    )

    log(f"{t('log.batch_preview.render_count', count=len(results), total=total)}")
    return len(results), total
