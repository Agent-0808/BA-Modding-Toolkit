# core/extraction.py
"""资源提取核心流程"""

import traceback
from pathlib import Path
import shutil
import tempfile

from ..i18n import t
from ..utils import no_log
from ..spine import (
    SkelConverter, atlas_downgrade, unpack_atlas,
)
from ..models import (
    AssetType, LogFunc,
    SkelConvertOptions,
    REPLACEABLE_ASSET_TYPES
)
from ..bundle import Bundle, find_stream_refs

# 提取器支持的资源类型（公开提取接口默认全量提取）
EXTRACTABLE_ASSET_TYPES = {"Texture2D", "TextAsset", "Mesh", "AnimationClip"}


def extract_assets_from_bundle(
    bundle_paths: list[Path],
    work_dir: Path,
    asset_types_to_extract: set[str],
    log: LogFunc = no_log,
) -> dict[AssetType, list[Path]]:
    """
    从 bundle 文件提取指定类型的资源到工作目录。

    Args:
        bundle_paths: bundle 文件路径列表
        work_dir: 工作目录（临时目录）
        asset_types_to_extract: 需要提取的资源类型名称集合（字符串形式）
        log: 日志记录函数

    Returns:
        dict[AssetType, list[Path]]: 按类型分类的提取文件路径字典
            例如: {AssetType.TextAsset: [...], AssetType.Texture2D: [...], AssetType.Mesh: [...]}
    """
    extracted_files: dict[AssetType, list[Path]] = {
        AssetType.TextAsset: [],
        AssetType.Texture2D: [],
        AssetType.Mesh: [],
        AssetType.AnimationClip: []
    }

    for bundle_file in bundle_paths:
        bundle = Bundle.load(bundle_file, log)
        if not bundle:
            continue

        for obj in bundle.env.objects:
            if obj.type.name not in asset_types_to_extract:
                continue
            if obj.type not in REPLACEABLE_ASSET_TYPES:
                continue

            try:
                data = obj.read()
                resource_name: str = getattr(data, 'm_Name', None)
                if not resource_name:
                    log(f"  > {t('log.extractor.skipping_unnamed', type=obj.type.name)}")
                    continue

                dest_path = None

                if obj.type == AssetType.TextAsset:
                    dest_path = work_dir / resource_name
                    asset_bytes = data.m_Script.encode("utf-8", "surrogateescape")
                    dest_path.write_bytes(asset_bytes)
                elif obj.type == AssetType.Texture2D:
                    dest_path = work_dir / f"{resource_name}.png"
                    data.image.convert("RGBA").save(dest_path)
                elif obj.type in (AssetType.Mesh, AssetType.AnimationClip):
                    # raw dump 导出；含流式引用（.resS）的数据脱离源 bundle 后无法重打包，跳过并告警
                    raw = obj.get_raw_data()
                    if find_stream_refs(raw):
                        log(f"  > ⚠️ {t('log.extractor.stream_ref_export_unsupported', name=resource_name)}")
                        continue
                    ext = "mesh.dat" if obj.type == AssetType.Mesh else "animationclip.dat"
                    dest_path = work_dir / f"{resource_name}.{ext}"
                    dest_path.write_bytes(raw)

                if dest_path:
                    log(f"  - {dest_path.name}")
                    if obj.type in extracted_files:
                        extracted_files[obj.type].append(dest_path)

            except Exception as e:
                log(f"  ❌ {t('log.extractor.extraction_failed', name=getattr(data, 'm_Name', 'N/A'), error=e)}")

    return extracted_files


def process_asset_extraction(
    bundle_path: Path | list[Path],
    output_dir: Path,
    spine_options: SkelConvertOptions | None = None,
    enable_unpack_atlas: bool = False,
    scale_atlas: bool = False,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    从指定的 Bundle 文件中提取全部支持的资源类型到输出目录（见 EXTRACTABLE_ASSET_TYPES）。
    支持 Texture2D (保存为 .png)、TextAsset (按原名保存)、Mesh (.mesh.bytes)、AnimationClip (.animationclip.dat)。
    如果启用了Spine降级选项，将自动处理Spine 4.x到3.8的降级。

    Args:
        bundle_path: 目标 Bundle 文件的路径，可以是单个 Path 或 Path 列表。
        output_dir: 提取资源的保存目录。
        spine_options: Spine资源转换的选项。
        unpack_atlas: 是否解包Atlas为单独的PNG帧（同时保留原文件）。
        log: 日志记录函数。

    Returns:
        一个元组 (是否成功, 状态消息)。
    """
    try:
        # 统一处理为列表
        bundle_paths = [bundle_path] if isinstance(bundle_path, Path) else bundle_path

        log("\n" + "="*50)
        if len(bundle_paths) == 1:
            log(t("log.extractor.starting_extraction", filename=bundle_paths[0].name))
        else:
            log(t("log.extractor.starting_extraction_num", num=len(bundle_paths)))
            for bp in bundle_paths:
                log(f"  - {bp.name}")
        log(t("log.extractor.extraction_types", types=', '.join(sorted(EXTRACTABLE_ASSET_TYPES))))
        log(f"{t('option.output_dir')}: {output_dir}")

        output_dir.mkdir(parents=True, exist_ok=True)
        downgrade_enabled = spine_options and spine_options.is_valid()

        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            log(f"  > {t('log.extractor.using_temp_dir', path=work_dir)}")

            # ========== 阶段 1: 提取资源 ==========
            log(f'\n--- {t("log.section.extract_to_temp")} ---')
            extracted_files = extract_assets_from_bundle(
                bundle_paths, work_dir, EXTRACTABLE_ASSET_TYPES, log
            )

            # 统计提取数量
            extraction_count = sum(len(files) for files in extracted_files.values())

            if extraction_count == 0:
                msg = t("message.extractor.no_assets_found")
                log(f"⚠️ {msg}")
                return True, msg

            # ========== 阶段 2: 处理资源 ==========

            # 2.1 Spine降级处理
            if downgrade_enabled:
                log(f'\n--- {t("log.section.process_spine_downgrade")} ---')

                # 降级所有 skel 文件（直接覆盖到工作目录）
                for skel_path in work_dir.glob("*.skel"):
                    log(f"  > {t('log.extractor.processing_file', name=skel_path.name)}")
                    SkelConverter.downgrade(
                        skel_path, work_dir,
                        spine_options.converter_path, spine_options.target_version, log
                    )

                # 降级所有 atlas 文件（直接覆盖到工作目录）
                for atlas_path in work_dir.glob("*.atlas"):
                    log(f"  > {t('log.extractor.processing_file', name=atlas_path.name)}")
                    atlas_downgrade(atlas_path, work_dir, scale_atlas, log)

            # 2.2 Atlas解包处理
            if enable_unpack_atlas:
                log(f'\n--- {t("log.section.process_atlas_unpack")} ---')

                for atlas_path in work_dir.glob("*.atlas"):
                    unpack_atlas(atlas_path, output_dir, log)

            # ========== 阶段 3: 输出文件 ==========
            # 将工作目录中剩余的文件复制到输出目录
            remaining_files = list(work_dir.iterdir())
            if remaining_files:
                log(f'\n--- {t("log.section.move_to_output")} ---')
                for item in remaining_files:
                    shutil.copy2(item, output_dir / item.name)
                    log(f"  - {item.name}")

        total_files_extracted = len(list(output_dir.iterdir()))
        success_msg = t("message.extractor.extraction_complete", count=total_files_extracted)
        log(f"\n🎉 {success_msg}")
        return True, success_msg

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_detail', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e)
