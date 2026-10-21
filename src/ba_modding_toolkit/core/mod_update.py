# core/mod_update.py
"""Mod 更新核心流程（单文件 / 批量）"""

import threading
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from ..i18n import t
from ..utils import no_log
from ..models import (
    FilePair, ProgressCallback,
    LogFunc, Patch,
    MatchStrategy, SaveOptions, SkelConvertOptions, AnimCheckOptions,
    AnimDiffMap, ModUpdateResult, BatchUpdateResult, SkelVersionConflict,
    ReplaceAssetType,
)
from ..bundle import Bundle
from ..searching import find_target_bundles


def _format_skel_conflicts(conflicts: list[SkelVersionConflict]) -> str:
    """将 skel 版本冲突列表格式化为终止消息（用于日志与弹窗）"""
    target = conflicts[0].target_version
    major_minor = ".".join(target.split(".")[:2])
    lines = [t("message.spine.version_conflict_header", major_minor=major_minor)]
    lines.extend(
        t("message.spine.version_conflict_item", name=c.name, source=c.source_version or t("common.unknown"))
        for c in conflicts
    )
    lines.append(t("message.spine.version_conflict_hint", major_minor=major_minor))
    return "\n".join(lines)


def process_mod_update(
    source_paths: list[Path],
    target_paths: list[Path],
    output_dir: Path,
    asset_types_to_replace: set[ReplaceAssetType],
    save_options: SaveOptions,
    spine_options: SkelConvertOptions | None = None,
    skip_unchanged: bool = False,
    match_strategy: MatchStrategy = 'path_id',
    anim_check: AnimCheckOptions | None = None,
    log: LogFunc = no_log,
) -> ModUpdateResult:
    """
    自动化Mod更新流程 (N-to-N)。

    处理流程的主要阶段：
    - 资源池化提取：从所有源文件中提取资源到统一字典
    - 按需注入注入：遍历所有目标文件，各自从资源池中提取匹配资源进行替换
    - CRC修正：根据选项决定是否对新生成的文件进行CRC校验修正

    Args:
        source_paths: 源文件路径列表（旧Mod或待移植文件组）
        target_paths: 目标文件路径列表（新版游戏资源文件组）
        output_dir: 输出目录，用于保存生成的更新后文件
        asset_types_to_replace: 需要替换的资源类型集合（如 {"Texture2D", "TextAsset"}）
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        skip_unchanged: 是否跳过未变化的文件
        match_strategy: 匹配策略
        log: 日志记录函数，默认为空函数

    Returns:
        ModUpdateResult: 包含成功标志、状态消息、文件对列表及动画差异信息。
        文件对列表为 (输出文件路径, 原始目标文件路径) 的元组
        如果skip_unchanged=True且所有资源都未变化，message 为 "unchanged"。
    """
    try:
        # 1. 提取资源 (Extraction)
        log(f'\n--- {t("log.section.extracting_patches")} ---')
        patches: Patch = {}
        skel_conflicts: list[SkelVersionConflict] = []

        for src in source_paths:
            src_bundle = Bundle.load(src, log)
            if not src_bundle:
                continue
            patch, conflicts = src_bundle.extract_patch(asset_types_to_replace, match_strategy, spine_options)
            patches.update(patch)
            skel_conflicts.extend(conflicts)

        if skel_conflicts:
            # skel 版本与预设目标版本不兼容：整批终止，不处理任何目标
            msg = _format_skel_conflicts(skel_conflicts)
            log(f"❌ {msg}")
            return ModUpdateResult(False, msg, [])

        if not patches:
            return False, t("message.mod_update.no_assets_extracted"), []

        log(f"  > {t('log.mod_update.pool_built', count=len(patches))}")

        # 2. 按需注入 (Application)
        log(f'\n--- {t("log.section.applying_to_targets")} ---')
        file_pairs: list[FilePair] = []
        total_matched = 0  # 总匹配数（包括跳过的）
        anim_diffs: dict[str, set[str]] = {}

        for tgt in target_paths:
            tgt_bundle = Bundle.load(tgt, log)
            if not tgt_bundle:
                log(f"  ❌ {t('message.load_failed')}: {tgt.name}")
                continue

            result = tgt_bundle.apply_patch(patches, match_strategy, anim_check)
            total_matched += result.matched_count

            # 汇总动画差异
            for name, anims in (result.anim_diffs or {}).items():
                anim_diffs.setdefault(name, set()).update(anims)

            if skip_unchanged and result.applied_count == 0 and result.skipped_count > 0:
                log(f"  ⏭️ {t('log.mod_update.target_unchanged', name=tgt.name, count=result.skipped_count)}")
                continue

            if result.is_success:
                output_path = output_dir / tgt.name
                save_ok, save_message = tgt_bundle.save(output_path, save_options)
                if save_ok:
                    file_pairs.append(FilePair(output_path, tgt))
                    log(f"  ✅ {t('log.mod_update.target_processed', name=tgt.name, applied=result.applied_count)}")
                else:
                    log(f"  ❌ {t('log.file.save_failed', path=output_path, error=save_message)}")
            else:
                log(f"  > {t('log.file.no_changes_made')} ({tgt.name})")

        # 3. 归一化动画差异（按 skel 名排序）
        final_anim_diffs: AnimDiffMap = {k: sorted(v) for k, v in anim_diffs.items()}

        if not file_pairs:
            # 区分：完全没有匹配 vs 匹配了但都被跳过
            if total_matched > 0 and skip_unchanged:
                return ModUpdateResult(True, "all_targets_unchanged", [], final_anim_diffs)
            return ModUpdateResult(False, t("message.mod_update.no_targets_processed"), [], final_anim_diffs)

        return ModUpdateResult(True, t("message.mod_update.success"), file_pairs, final_anim_diffs)

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_processing', error=e)}")
        log(traceback.format_exc())
        return ModUpdateResult(False, t("message.error_during_process", error=e), [])

def _process_single_mod_update(
    mod_path: Path,
    search_paths: list[Path],
    output_dir: Path,
    asset_types_to_replace: set[ReplaceAssetType],
    save_options: SaveOptions,
    spine_options: SkelConvertOptions | None,
    skip_unchanged: bool,
    match_strategy: MatchStrategy,
    anim_check: AnimCheckOptions | None = None,
    log: LogFunc = no_log,
) -> ModUpdateResult:
    """
    处理单个 mod 文件：查找目标 → 执行更新

    Args:
        mod_path: 单个 mod 文件路径
        search_paths: 用于查找新版bundle文件的目录列表
        output_dir: 输出目录
        asset_types_to_replace: 需要替换的资源类型集合
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        skip_unchanged: 是否跳过未变化的文件
        match_strategy: 匹配策略
        anim_check: 动画差异检测选项（启用开关与 SpineViewerCLI 路径）
        log: 日志记录函数

    Returns:
        ModUpdateResult: 包含成功标志、状态消息、文件对列表及动画差异信息。
        - success=True, message="" 表示处理成功且有输出
        - success=True, message="unchanged" 表示内容未变化，无输出
        - success=False, message=错误信息 表示处理失败
    """
    new_bundle_paths, find_message = find_target_bundles([mod_path], search_paths, log)

    if not new_bundle_paths:
        log(f'  ❌ {t("log.search.find_failed", message=find_message)}')
        return ModUpdateResult(False, t("log.search.find_failed", message=find_message), [])

    result = process_mod_update(
        source_paths=[mod_path],
        target_paths=new_bundle_paths,
        output_dir=output_dir,
        asset_types_to_replace=asset_types_to_replace,
        save_options=save_options,
        spine_options=spine_options,
        log=log,
        skip_unchanged=skip_unchanged,
        match_strategy=match_strategy,
        anim_check=anim_check,
    )

    if result.success:
        if result.message in ("unchanged", "all_targets_unchanged"):
            log(f'  ⏭️ {t("log.batch.process_unchanged", filename=mod_path.name)}')
            return ModUpdateResult(True, "unchanged", [], result.anim_diffs)
        else:
            log(f'  ✅ {t("log.batch.process_success", filename=mod_path.name)}')
            return ModUpdateResult(True, "", result.file_pairs, result.anim_diffs)
    else:
        log(f'  ❌ {t("log.batch.process_failed", filename=mod_path.name, message=result.message)}')
        return ModUpdateResult(False, result.message, [], result.anim_diffs)


def process_batch_mod_update(
    mod_file_list: list[Path],
    search_paths: list[Path],
    output_dir: Path,
    asset_types_to_replace: set[ReplaceAssetType],
    save_options: SaveOptions,
    spine_options: SkelConvertOptions | None,
    max_workers: int = 1,
    progress_callback: ProgressCallback | None = None,
    skip_unchanged: bool = False,
    match_strategy: MatchStrategy = 'path_id',
    anim_check: AnimCheckOptions | None = None,
    log: LogFunc = no_log,
) -> BatchUpdateResult:
    """
    执行批量Mod更新的核心逻辑。

    Args:
        mod_file_list: 待更新的旧Mod文件路径列表。
        search_paths: 用于查找新版bundle文件的目录列表。
        output_dir: 输出目录。
        asset_types_to_replace: 需要替换的资源类型集合。
        save_options: 保存和CRC修正的选项。
        spine_options: Spine资源升级的选项。
        max_workers: 并行处理的线程数，默认为1（串行）。
        progress_callback: 进度回调函数，用于更新UI。
                           接收 (已完成数, 总数, 文件名)。
        skip_unchanged: 是否跳过未变化的文件
        match_strategy: 匹配策略，可选 'path_id'、'name_type'、'cont_name_type'
        log: 日志记录函数。

    Returns:
        BatchUpdateResult: 包含成功计数、失败计数、失败任务详情、文件对列表
        （各为 (输出文件路径, 被替换的原始文件路径) 元组）及按 mod 分组的动画差异信息。
    """
    total_files = len(mod_file_list)
    success_count = 0
    fail_count = 0
    unchanged_count = 0
    failed_tasks: list[str] = []
    file_pairs: list[FilePair] = []
    anim_diffs: dict[str, set[str]] = {}

    def record_diff(diff: AnimDiffMap | None) -> None:
        """记录动画差异，按 skel 名合并去重"""
        if not diff:
            return
        for skel, anims in diff.items():
            anim_diffs.setdefault(skel, set()).update(anims)

    log("\n" + "=" * 50)
    log(f"📦 {t('log.batch.start')}")
    log(f"  > {t('log.summary.total_files', count=total_files)}")

    if max_workers <= 1:
        # 串行处理
        for i, old_mod_path in enumerate(mod_file_list):
            current_progress = i + 1
            filename = old_mod_path.name

            if progress_callback:
                progress_callback(current_progress, total_files, filename)

            log("\n" + "=" * 50)
            log(t("status.processing_batch", current=current_progress, total=total_files, filename=filename))

            result: ModUpdateResult = _process_single_mod_update(
                mod_path=old_mod_path,
                search_paths=search_paths,
                output_dir=output_dir,
                asset_types_to_replace=asset_types_to_replace,
                save_options=save_options,
                spine_options=spine_options,
                skip_unchanged=skip_unchanged,
                match_strategy=match_strategy,
                anim_check=anim_check,
                log=log,
            )
            record_diff(result.anim_diffs)

            if result.success:
                if result.message == "unchanged":
                    unchanged_count += 1
                else:
                    success_count += 1
                    file_pairs.extend(result.file_pairs)
            else:
                fail_count += 1
                failed_tasks.append(filename)
    else:
        # 并行处理
        lock = threading.Lock()
        completed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for mod_path in mod_file_list:
                future = executor.submit(
                    _process_single_mod_update,
                    mod_path, search_paths, output_dir,
                    asset_types_to_replace, save_options,
                    spine_options, skip_unchanged,
                    match_strategy, anim_check, log,
                )
                futures[future] = mod_path.name

            for future in as_completed(futures):
                filename = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    with lock:
                        fail_count += 1
                        failed_tasks.append(f"{filename} - {t('message.process_failed', error=e)}")
                        completed += 1
                    log(t("log.batch.process_failed", filename=filename, message=str(e)))
                else:
                    with lock:
                        record_diff(result.anim_diffs)
                        if result.success:
                            if result.message == "unchanged":
                                unchanged_count += 1
                                log(t("log.batch.process_unchanged", filename=filename))
                            else:
                                success_count += 1
                                file_pairs.extend(result.file_pairs)
                                log(t("log.batch.process_success", filename=filename))
                        else:
                            fail_count += 1
                            failed_tasks.append(f"{filename} - {result.message}")
                            log(t("log.batch.process_failed", filename=filename, message=result.message))
                        completed += 1

                if progress_callback:
                    progress_callback(completed, total_files, filename)

    log("\n" + "=" * 50)
    log(f"📊 {t('log.batch.summary', total=total_files, success=success_count, fail=fail_count)}")

    if unchanged_count > 0:
        log(f"⏭️ {t('log.summary.skipped_files', count=unchanged_count)} ({t('log.summary.no_changes')})")

    if file_pairs:
        log(f'\n{t("log.batch.output_files_list", count=len(file_pairs))}')
        for output_path, _ in file_pairs:
            log(f'  - {output_path.name}')

    if failed_tasks:
        log(f'\n❌ {t("log.batch.failed_items_cnt", count=len(failed_tasks))}')
        for task in failed_tasks:
            log(f'  - {task}')

    return BatchUpdateResult(
        success_count=success_count,
        fail_count=fail_count,
        failed_tasks=failed_tasks,
        file_pairs=file_pairs,
        anim_diffs={k: sorted(v) for k, v in anim_diffs.items()},
    )
