# core/packing.py
"""资源打包（替换）核心流程"""

import traceback
from pathlib import Path
import shutil
import tempfile
from PIL import Image

from ..i18n import t
from ..utils import bleed_image, no_log
from ..spine import (
    SkelConverter,
    check_legacy_rename_needed, normalize_legacy_assets,
)
from ..models import (
    NameTypeKey, FilePair,
    AssetKey, AssetContent, AssetType, Patch,
    LogFunc, RawAssetBytes,
    SaveOptions, SkelConvertOptions, AnimCheckOptions,
    SkelVersionConflict,
)
from ..asset import find_stream_refs
from ..bundle import Bundle
from ..naming import DUMP_FILE_EXTENSIONS, DUMP_TYPE_EXTENSIONS, parse_typed_dump_name
from .mod_update import _format_skel_conflicts


def _log_anim_diff_report(anim_diffs: dict[str, list[str]], log: LogFunc) -> None:
    """输出动画缺失警告报告（仅在有差异时输出）"""
    if not anim_diffs:
        return
    log("\n" + "!" * 50)
    log(t("log.spine.anim_diff_title"))
    for name, anims in anim_diffs.items():
        log(f"   - {name} ({t('log.spine.anim_diff_item_count', count=len(anims))})")
        log(f"     {t('log.spine.anim_diff_missing_list', animations=', '.join(anims))}")
    log(t("log.spine.anim_diff_hint"))
    log("!" * 50)


def process_asset_packing(
    target_bundle_path: list[Path],
    assets: list[Path],
    output_dir: Path,
    save_options: SaveOptions,
    spine_options: SkelConvertOptions | None = None,
    enable_rename_fix: bool | None = False,
    enable_bleed: bool | None = False,
    skip_unchanged: bool = True,
    anim_check: AnimCheckOptions | None = None,
    log: LogFunc = no_log,
) -> tuple[bool, str, list[FilePair]]:
    """
    从指定文件夹或文件列表中，将同名的资源打包到一个或多个目标 Bundle 中。
    支持 .png, .skel, .atlas 以及带类型标记的 dump 文件（.dat或 .bytes）。
    - .png 文件将替换同名的 Texture2D 资源 (文件名不含后缀)。
    - .skel 和 .atlas 文件将替换同名的 TextAsset 资源 (文件名含后缀)。
    - .{type}.bytes / .{type}.dat dump 文件将替换同名的对应类型资源，
      如 {name}.mesh.bytes / {name}.mesh.dat 替换 Mesh，{name}.animationclip.dat 替换 AnimationClip。
    可选地升级 Spine 动画的 Skel 资源版本。
    可选地对 PNG 文件进行 Bleed 处理。
    此函数将生成的文件保存在工作目录中，以便后续进行"覆盖原文件"操作。
    因为打包资源的操作在原理上是替换目标Bundle内的资源，因此里面可能有混用打包和替换的叫法。
    返回 (是否成功, 状态消息, (输出路径, 原始目标路径) 列表) 的元组。

    Args:
        target_bundle_path: 目标Bundle文件的路径列表
        assets: 包含待打包资源的文件夹或文件路径列表
        output_dir: 输出目录，用于保存生成的更新后文件
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        enable_rename_fix: 是否启用旧版 Spine 3 文件名修正
        enable_bleed: 是否对 PNG 文件进行 Bleed 处理
        skip_unchanged: 是否跳过未变化的文件
        log: 日志记录函数，默认为空函数
    """
    bundle_paths = list(target_bundle_path)
    asset_paths = list(assets)
    temp_asset_folder = None
    try:
        # 1. 从所有资源路径中收集输入文件
        patch: Patch = {}
        skel_conflicts: list[SkelVersionConflict] = []
        supported_extensions = {".png", ".skel", ".atlas"} | DUMP_FILE_EXTENSIONS
        input_files: list[Path] = []

        for asset_path in asset_paths:
            if asset_path.is_dir():
                for f in asset_path.iterdir():
                    if f.is_file() and f.suffix.lower() in supported_extensions:
                        input_files.append(f)
            elif asset_path.is_file() and asset_path.suffix.lower() in supported_extensions:
                input_files.append(asset_path)

        if enable_rename_fix and input_files:
            # 从目标 Bundle 中提取 Texture2D 名称作为重命名参考
            bundle_png_names: set[str] = set()
            for bp in bundle_paths:
                bundle = Bundle.load(bp)
                if bundle:
                    for key in bundle.get_asset_keys(asset_types={AssetType.Texture2D}):
                        if isinstance(key, NameTypeKey) and key.name:
                            bundle_png_names.add(key.name)

            if bundle_png_names:
                # 将所有文件复制到临时目录
                temp_dir = tempfile.mkdtemp(prefix="asset_pack_")
                temp_path = Path(temp_dir)
                for f in input_files:
                    shutil.copy2(f, temp_path / f.name)

                # 检测是否需要重命名
                if check_legacy_rename_needed(temp_path, bundle_png_names):
                    log(t('log.spine.legacy_rename_detected'))
                    temp_asset_folder = normalize_legacy_assets(temp_path, bundle_png_names, log)
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    input_files = [f for f in temp_asset_folder.iterdir()
                                  if f.is_file() and f.suffix.lower() in supported_extensions]
                else:
                    # 不需要重命名，直接使用临时目录
                    input_files = [f for f in temp_path.iterdir()
                                  if f.is_file() and f.suffix.lower() in supported_extensions]

        if not input_files:
            msg = t("message.packer.no_supported_files_found", extensions=', '.join(supported_extensions))
            log(f"⚠️ {t('common.warning')}: {msg}")
            return False, msg, []

        for file_path in input_files:
            asset_key: AssetKey
            content: AssetContent
            suffix: str = file_path.suffix.lower()
            if suffix == ".png":
                asset_key = NameTypeKey(file_path.stem, AssetType.Texture2D.name)
                content = Image.open(file_path).convert("RGBA")
                if enable_bleed:
                    content = bleed_image(content)
                    log(f"  > {t('log.packer.bleed_processed', name=file_path.stem)}")
            elif suffix in {".skel", ".atlas"}:
                asset_key = NameTypeKey(file_path.name, AssetType.TextAsset.name)
                with open(file_path, "rb") as f:
                    content = f.read()

                if file_path.suffix.lower() == '.skel':
                    content, conflict = SkelConverter.ensure_version(
                        skel_bytes=content,
                        resource_name=asset_key.name,
                        options=spine_options,
                        log=log
                    )
                    if conflict:
                        skel_conflicts.append(conflict)
                        continue
            elif suffix in DUMP_FILE_EXTENSIONS:
                parsed = parse_typed_dump_name(file_path.name)
                if parsed is None:
                    supported_dump = ', '.join(
                        f'{{name}}.{ext}{file_ext}'
                        for ext in DUMP_TYPE_EXTENSIONS for file_ext in DUMP_FILE_EXTENSIONS
                    )
                    raise ValueError(
                        f"Cannot determine asset type from '{file_path.name}'. "
                        f"Dump files must be named as: {supported_dump}"
                    )
                resource_name, asset_type = parsed
                asset_key = NameTypeKey(resource_name, asset_type)
                with open(file_path, "rb") as f:
                    # 标记为 raw dump 内容，apply_patch 走 set_raw_data 原样替换
                    raw = f.read()
                    if find_stream_refs(raw):
                        # dump 脱离了源 bundle，无 companion 可携带，流引用必然悬空
                        raise ValueError(
                            f"Dump file '{file_path.name}' contains .resS/.resource stream refs "
                            f"and cannot be packed standalone. Export it from its source bundle "
                            f"with the companion fix, or use a bundle as the mod source."
                        )
                    content = RawAssetBytes(raw)
            else:
                raise TypeError(f"Unsupported suffix: {suffix}")
            patch[asset_key] = content

        if skel_conflicts:
            # skel 版本与预设目标版本不兼容：终止流程，不处理任何目标 Bundle（详情见失败消息）
            log(f'❌ {t("log.spine.version_conflict_rejected", count=len(skel_conflicts))}')
            msg = _format_skel_conflicts(skel_conflicts)
            return False, msg, []

        original_tasks_count = len(patch)
        log(t("log.packer.found_files_to_process", count=original_tasks_count))

        # 预构建原始文件名映射（用于未匹配文件日志）
        original_filenames: dict[NameTypeKey, str] = {}
        for f in input_files:
            s = f.suffix.lower()
            if s == '.png':
                original_filenames[NameTypeKey(f.stem, AssetType.Texture2D.name)] = f.name
            elif s in {'.skel', '.atlas'}:
                original_filenames[NameTypeKey(f.name, AssetType.TextAsset.name)] = f.name
            elif s in DUMP_FILE_EXTENSIONS:
                parsed = parse_typed_dump_name(f.name)
                if parsed:
                    original_filenames[NameTypeKey(parsed[0], parsed[1].name)] = f.name

        strategy_name = 'name_type'

        # 2. 对每个目标 Bundle 应用替换并保存
        file_pairs: list[FilePair] = []
        success_count = 0
        all_matched_keys: set[AssetKey] = set()
        anim_diffs: dict[str, set[str]] = {}

        for i, bundle_path in enumerate(bundle_paths):
            if len(bundle_paths) > 1:
                log(f"--- [{i + 1}/{len(bundle_paths)}] {bundle_path.name} ---")

            target_bundle = Bundle.load(bundle_path, log)
            if not target_bundle:
                log(f"⚠️ {t('message.packer.load_target_bundle_failed')}: {bundle_path.name}")
                continue

            result = target_bundle.apply_patch(patch, strategy_name, anim_check)

            # 汇总动画差异
            for name, anims in (result.anim_diffs or {}).items():
                anim_diffs.setdefault(name, set()).update(anims)

            # 判断是否应该保存此 bundle
            should_save = result.is_success or not skip_unchanged

            if not should_save:
                log(f"⚠️ {t('common.warning')}: {t('log.packer.no_assets_packed')} ({bundle_path.name})")
                continue

            if result.is_success:
                log(f"✅ {t('log.packer.strategy_success', strategy=strategy_name, count=result.applied_count)}:")
                for item in result.applied_logs:
                    log(f"  - {item}")
                log(f'{t("log.packer.packing_complete", success=result.applied_count, total=original_tasks_count)}')
            else:
                # skip_unchanged=False 但没有匹配资源，保存未修改的 bundle
                log(f"⏭️ {t('log.packer.no_changes_saved', name=bundle_path.name)}")

            all_matched_keys.update(result.matched_keys)

            output_path = output_dir / bundle_path.name
            save_ok, save_message = target_bundle.save(output_path, save_options)

            if not save_ok:
                log(f"⚠️ {save_message}")
                continue

            log(t("log.file.saved", path=output_path))
            file_pairs.append(FilePair(output_path, bundle_path))
            success_count += 1

        # 3. 汇总输出所有bundle都未匹配的资源
        never_matched_keys = set(patch.keys()) - all_matched_keys
        if never_matched_keys:
            log(f"⚠️ {t('common.warning')}: {t('log.packer.unmatched_files_warning')}:")
            for key in sorted(never_matched_keys):
                log(f"  - {original_filenames.get(key, key)} ({t('log.packer.attempted_match', key=str(key))})")

        # 3. 输出动画缺失警告报告
        _log_anim_diff_report({k: sorted(v) for k, v in anim_diffs.items()}, log)

        if not file_pairs:
            return False, t("message.packer.no_matching_assets_to_pack"), []

        return True, t("message.packer.process_complete", count=success_count, button=t("action.replace_original")), file_pairs

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_detail', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e), []
    finally:
        if temp_asset_folder:
            try:
                shutil.rmtree(temp_asset_folder)
            except Exception:
                pass
