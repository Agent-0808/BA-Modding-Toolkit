# core.py

import traceback
from pathlib import Path
import shutil
import re
import tempfile
from typing import Callable
from UnityPy.environment import Environment as Env
from PIL import Image

from .i18n import t
from .utils import SpineUtils, ImageUtils, no_log
from .models import (
    NameTypeKey, ContNameTypeKey, 
    AssetKey, AssetContent, AssetType,
    KeyGeneratorFunc, LogFunc, ReplacementResult,
    MATCH_STRATEGIES, SaveOptions, SpineOptions,
    REPLACEABLE_ASSET_TYPES
)
from .bundle import Bundle

# ====== 读取与保存相关 ======

def get_unity_platform_info(input: Path | Env) -> tuple[str, str]:
    """
    获取 Bundle 文件的平台信息和 Unity 版本。
    
    Returns:
        tuple[str, str]: (平台名称, Unity版本) 的元组
                         如果找不到则返回 ("UnknownPlatform", "Unknown")
    """
    if isinstance(input, Path):
        bundle = Bundle.load(input)
        return bundle.platform_info if bundle else ("UnknownPlatform", "Unknown")
    elif isinstance(input, Env):
        temp_bundle = Bundle(Path("temp"), input)
        return temp_bundle.platform_info
    else:
        raise ValueError("input 必须是 Path 或 UnityPy.Environment 类型")

# ====== 寻找对应文件 ======

def get_filename_prefix(filename: str, log: LogFunc = no_log) -> tuple[str | None, str]:
    """
    从旧版Mod文件名中提取用于搜索新版文件的前缀。
    返回 (前缀字符串, 状态消息) 的元组。
    """
    # 1. 通过日期模式确定文件名位置
    date_match = re.search(r'\d{4}-\d{2}-\d{2}', filename)
    if not date_match:
        msg = t("message.search.date_pattern_not_found", filename=filename)
        log(f'  > {t("common.fail")}: {msg}')
        return None, msg

    # 2. 向前查找可能的日服额外文件名部分
    prefix_end_index = date_match.start()
    before_date = filename[:prefix_end_index].removesuffix('-')
    # 例如在 "...-textures-YYYY-MM-DD..." 中的 "textures"

    parts = before_date.split('-')
    last_part = parts[-1] if parts else ''
    
    # 检查最后一个部分是否是日服版额外的资源类型
    resource_types = {
        'textures', 'assets', 'textassets', 'materials',
        "animationclip", "audio", "meshes", "prefabs", "timelines"
    }
    
    if last_part.lower() in resource_types:
        # 如果找到了资源类型，则前缀不应该包含这个部分
        search_prefix = before_date.removesuffix(f'-{last_part}') + '-'
    else:
        search_prefix = filename[:prefix_end_index]

    return search_prefix, t("message.search.prefix_extracted")

# -------- 文件名解析常量 --------

REMOVE_SUFFIX = [
    r"[-_]mxdependency",  # 匹配 -mxdependency 或 _mxdependency
    r"[-_]mxload",        # 匹配 -mxload 或 _mxload
    r"-\d{4}-\d{2}-\d{2}" # 匹配日期格式 (如 -2024-11-18)，作为最后的保底
]

FIXED_PREFIX = [
    "assets-_mx-",
]

def extract_core_filename(filename: str) -> str:
    """
    文件名核心提取函数
    复用 parse_filename 的逻辑，只返回 core 部分
    """
    _, core, _, _, _ = parse_filename(filename)
    return core

def parse_filename(filename: str) -> tuple[str | None, str, str | None, str, str]:
    """
    解析文件名，提取各个组成部分。

    Args:
        filename: 文件名字符串

    Returns:
        tuple: (category, core, type, date, crc32)
        - category: 资源分类 (如 spinecharacters)，可能为 None
        - core: 核心名称 (如 ch0296_spr)，必须有值
        - type: 资源类型 (如 textassets)，可能为 None
        - date: 日期字符串 (YYYY-MM-DD)
        - crc32: CRC32 校验码
    """
    # 提取 CRC32
    crc = ""
    match_crc = re.search(r'_(\d+)\.[^.]+$', filename)
    if match_crc:
        crc = match_crc.group(1)

    # 提取 Date
    date = ""
    match_date = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
    if match_date:
        date = match_date.group(1)

    # 提取 Type
    res_type = None
    # 匹配 -mxdependency-xxx 或 _mxload-xxx
    match_type = re.search(r'[-_](?:mxdependency|mxload)-([a-zA-Z0-9]+)', filename)
    if match_type:
        res_type = match_type.group(1)
        # 如果提取出的 type 是年份，说明实际上没有 type，而是直接接了日期
        if re.match(r'^\d{4}$', res_type):
            res_type = None

    # 提取 Core（从后往前，找到 _mxdependency 或 _mxload 之前的部分）
    core = ""

    # 找到最早的 _mxdependency 或 _mxload 位置
    mx_match = re.search(r'[-_](?:mxdependency|mxload)', filename)
    if mx_match:
        # Core 是这之前的部分
        core_part = filename[:mx_match.start()]
    else:
        # 如果没找到，尝试用日期作为分隔
        date_match = re.search(r'-\d{4}-\d{2}-\d{2}', filename)
        if date_match:
            core_part = filename[:date_match.start()]
        else:
            # 最后的保底：去除扩展名
            core_part = filename.rsplit('.', 1)[0]

    # 去除固定前缀 (如 assets-_mx-)
    for prefix in FIXED_PREFIX:
        if core_part.startswith(prefix):
            core_part = core_part[len(prefix):]
            break

    core = core_part.strip('-_')

    # 提取 Category
    category = None

    if core:
        # 尝试从 core 中分离 category
        parts = core.split('-', 1)
        if len(parts) > 1:
            category = parts[0]
            core = parts[1]

    return (category, core, res_type, date, crc)


def find_new_bundle_path(
    old_mod_path: Path,
    game_resource_dir: Path | list[Path],
    log: LogFunc = no_log,
) -> tuple[list[Path], str]:
    """
    根据旧版Mod文件，在游戏资源目录中智能查找对应的新版文件。
    
    Returns:
        tuple[list[Path], str]: (找到的路径列表, 状态消息)
    """
    if not old_mod_path.exists():
        return [], t("message.search.check_file_exists", path=old_mod_path)

    log(t("log.search.searching_for_file", name=old_mod_path.name))

    # 1. 提取文件名前缀
    if not (prefix_info := get_filename_prefix(str(old_mod_path.name), log))[0]:
        return None, prefix_info[1]
    
    prefix, _ = prefix_info
    log(f"  > {t('log.search.file_prefix', prefix=prefix)}")
    extension = '.bundle'
    extension_backup = '.backup'

    # 2. 收集所有候选文件
    search_dirs = [game_resource_dir] if isinstance(game_resource_dir, Path) else game_resource_dir
    
    candidates = [
        file for dir in search_dirs 
        if dir.exists() and dir.is_dir()
        for file in dir.iterdir()
        if file.is_file() and file.name.startswith(prefix) and file.suffix != extension_backup
    ]
    
    if not candidates:
        msg = t("message.search.no_matching_files_in_dir")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg
    log(f"  > {t('log.search.found_candidates', count=len(candidates))}")

    # 3. 分析旧Mod的关键资源特征
    # 定义用于识别的资源类型
    comparable_types = {AssetType.Texture2D, AssetType.TextAsset, AssetType.Mesh}
    
    old_bundle = Bundle.load(old_mod_path, log)
    if not old_bundle:
        msg = t("message.search.load_old_mod_failed")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    # 使用标准策略生成 Key，保持一致性
    key_func = MATCH_STRATEGIES['name_type']
    
    # 仅提取 Key，不读取数据
    # 使用 set 推导式构建指纹
    old_assets_fingerprint = {
        key_func(obj)
        for obj in old_bundle.env.objects
        if obj.type in comparable_types
    }

    if not old_assets_fingerprint:
        msg = t("message.search.no_comparable_assets")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg

    log(f"  > {t('log.search.old_mod_asset_count', count=len(old_assets_fingerprint))}")

    # 4. 遍历候选文件进行指纹比对，收集所有匹配的文件
    matched_paths = []
    for candidate_path in candidates:
        log(f"  - {t('log.search.checking_candidate', name=candidate_path.name)}")
        
        candidate_bundle = Bundle.load(candidate_path, log)
        if not candidate_bundle:
            continue
        
        # 检查新包中是否有匹配的资源
        has_match = False
        for obj in candidate_bundle.env.objects:
            if obj.type in comparable_types:
                candidate_key = key_func(obj)
                if candidate_key in old_assets_fingerprint:
                    has_match = True
                    break
        
        if has_match:
            matched_paths.append(candidate_path)
            msg = t("message.search.new_file_confirmed", name=candidate_path.name)
            log(f"  ✅ {msg}")
    
    if not matched_paths:
        msg = t("message.search.no_matching_asset_found")
        log(f'  > {t("common.fail")}: {msg}')
        return [], msg
    
    msg = t("message.search.found_multiple_matches", count=len(matched_paths))
    log(f"  > {msg}")
    return matched_paths, msg

# ====== 资源处理相关 ======

def process_asset_packing(
    target_bundle_path: Path,
    asset_folder: Path,
    output_dir: Path,
    save_options: SaveOptions,
    spine_options: SpineOptions | None = None,
    enable_rename_fix: bool | None = False,
    enable_bleed: bool | None = False,
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    从指定文件夹中，将同名的资源打包到指定的 Bundle 中。
    支持 .png, .skel, .atlas 文件。
    - .png 文件将替换同名的 Texture2D 资源 (文件名不含后缀)。
    - .skel 和 .atlas 文件将替换同名的 TextAsset 资源 (文件名含后缀)。
    可选地升级 Spine 动画的 Skel 资源版本。
    可选地对 PNG 文件进行 Bleed 处理。
    此函数将生成的文件保存在工作目录中，以便后续进行"覆盖原文件"操作。
    因为打包资源的操作在原理上是替换目标Bundle内的资源，因此里面可能有混用打包和替换的叫法。
    返回 (是否成功, 状态消息) 的元组。
    
    Args:
        target_bundle_path: 目标Bundle文件的路径
        asset_folder: 包含待打包资源的文件夹路径
        output_dir: 输出目录，用于保存生成的更新后文件
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        enable_rename_fix: 是否启用旧版 Spine 3.8 文件名修正
        enable_bleed: 是否对 PNG 文件进行 Bleed 处理
        log: 日志记录函数，默认为空函数
    """
    temp_asset_folder = None
    try:
        if enable_rename_fix:
            temp_asset_folder = SpineUtils.normalize_legacy_spine_assets(asset_folder, log)
            asset_folder = temp_asset_folder

        target_bundle = Bundle.load(target_bundle_path, log)
        if not target_bundle:
            return False, t("message.packer.load_target_bundle_failed")
        
        # 1. 从文件夹构建"替换清单"
        replacement_map: dict[AssetKey, AssetContent] = {}
        supported_extensions = {".png", ".skel", ".atlas"}
        input_files = [f for f in asset_folder.iterdir() if f.is_file() and f.suffix.lower() in supported_extensions]

        if not input_files:
            msg = t("message.packer.no_supported_files_found", extensions=', '.join(supported_extensions))
            log(f"⚠️ {t('common.warning')}: {msg}")
            return False, msg

        for file_path in input_files:
            asset_key: AssetKey
            content: AssetContent
            suffix: str = file_path.suffix.lower()
            if suffix == ".png":
                asset_key = NameTypeKey(file_path.stem, AssetType.Texture2D.name)
                content = Image.open(file_path).convert("RGBA")
                if enable_bleed:
                    content = ImageUtils.bleed_image(content)
                    log(f"  > {t('log.packer.bleed_processed', name=file_path.stem)}")
            elif suffix in {".skel", ".atlas"}:
                asset_key = NameTypeKey(file_path.name, AssetType.TextAsset.name)
                with open(file_path, "rb") as f:
                    content = f.read()
                
                if file_path.suffix.lower() == '.skel':
                    content = SpineUtils.handle_skel_upgrade(
                        skel_bytes=content,
                        resource_name=asset_key.name,
                        enabled=spine_options.enabled if spine_options else False,
                        converter_path=spine_options.converter_path if spine_options else None,
                        target_version=spine_options.target_version if spine_options else None,
                        log=log
                    )
            else:
                raise TypeError(f"Unsupported suffix: {suffix}")
            replacement_map[asset_key] = content
        
        original_tasks_count = len(replacement_map)
        log(t("log.packer.found_files_to_process", count=original_tasks_count))

        # 2. 应用替换
        strategy_name = 'name_type'
        key_func = MATCH_STRATEGIES[strategy_name]
        result = target_bundle.apply_replacements(replacement_map, key_func)

        if not result.is_success:
            log(f"⚠️ {t('common.warning')}: {t('log.packer.no_assets_packed')}")
            log(t("log.packer.check_files_and_bundle"))
            return False, t("message.packer.no_matching_assets_to_pack")
        
        log(f"✅ {t('log.migration.strategy_success', name=strategy_name, count=result.replaced_count)}:")
        for item in result.replaced_logs:
            log(f"  - {item}")

        log(f'\n{t("log.packer.packing_complete", success=result.replaced_count, total=original_tasks_count)}')

        # 报告未被打包的文件
        if result.unmatched_keys:
            log(f"⚠️ {t('common.warning')}: {t('log.packer.unmatched_files_warning')}:")
            # 为了找到原始文件名，我们需要反向查找
            original_filenames = {
                NameTypeKey(f.stem, AssetType.Texture2D.name): f.name for f in input_files if f.suffix.lower() == '.png'
            }
            original_filenames.update({
                NameTypeKey(f.name, AssetType.TextAsset.name): f.name for f in input_files if f.suffix.lower() in {'.skel', '.atlas'}
            })
            for key in sorted(result.unmatched_keys):
                if isinstance(key, NameTypeKey):
                    key_display = f"[{key.type}] {key.name}"
                else:
                    key_display = str(key)
                log(f"  - {original_filenames.get(key, key)} ({t('log.packer.attempted_match', key=key_display)})")

        # 3. 保存
        output_path = output_dir / target_bundle_path.name
        save_ok, save_message = target_bundle.save(output_path, save_options)

        if not save_ok:
            return False, save_message

        log(t("log.file.saved", path=output_path))
        return True, t("message.packer.process_complete", count=result.replaced_count, button=t("action.replace_original"))

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_detail', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e)
    finally:
        if temp_asset_folder:
            try:
                shutil.rmtree(temp_asset_folder)
            except Exception:
                pass

def process_asset_extraction(
    bundle_path: Path | list[Path],
    output_dir: Path,
    asset_types_to_extract: set[str],
    spine_options: SpineOptions | None = None,
    atlas_export_mode: str = "atlas",
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    从指定的 Bundle 文件中提取选定类型的资源到输出目录。
    支持 Texture2D (保存为 .png) 和 TextAsset (按原名保存)。
    如果启用了Spine降级选项，将自动处理Spine 4.x到3.8的降级。
    支持Atlas导出模式：atlas（保留原文件）、unpack（解包为PNG帧）、both（两者皆有）。

    Args:
        bundle_path: 目标 Bundle 文件的路径，可以是单个 Path 或 Path 列表。
        output_dir: 提取资源的保存目录。
        asset_types_to_extract: 需要提取的资源类型集合 (如 {"Texture2D", "TextAsset"})。
        spine_options: Spine资源转换的选项。
        atlas_export_mode: Atlas导出模式，可选值："atlas"、"unpack"、"both"。
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
        log(t("log.extractor.extraction_types", types=', '.join(asset_types_to_extract)))
        log(f"{t('option.output_dir')}: {output_dir}")

        output_dir.mkdir(parents=True, exist_ok=True)
        downgrade_enabled = spine_options and spine_options.is_valid()

        with tempfile.TemporaryDirectory() as temp_dir:
            work_dir = Path(temp_dir)
            log(f"  > {t('log.extractor.using_temp_dir', path=work_dir)}")

            # ========== 阶段 1: 提取资源 ==========
            log(f'\n--- {t("log.section.extract_to_temp")} ---')
            extraction_count = 0
            
            for bundle_file in bundle_paths:
                bundle = Bundle.load(bundle_file, log)
                if not bundle:
                    continue
                
                for obj in bundle.env.objects:
                    if obj.type.name not in asset_types_to_extract:
                        continue
                    # 确保类型在白名单中
                    if obj.type not in REPLACEABLE_ASSET_TYPES:
                        continue
                    try:
                        data = obj.read()
                        resource_name: str = getattr(data, 'm_Name', None)
                        if not resource_name:
                            log(f"  > {t('log.extractor.skipping_unnamed', type=obj.type.name)}")
                            continue

                        if obj.type == AssetType.TextAsset:
                            dest_path = work_dir / resource_name
                            asset_bytes = data.m_Script.encode("utf-8", "surrogateescape")
                            dest_path.write_bytes(asset_bytes)
                        elif obj.type == AssetType.Texture2D:
                            dest_path = work_dir / f"{resource_name}.png"
                            data.image.convert("RGBA").save(dest_path)
                        
                        log(f"  - {dest_path.name}")
                        extraction_count += 1
                    except Exception as e:
                        log(f"  ❌ {t('log.extractor.extraction_failed', name=getattr(data, 'm_Name', 'N/A'), error=e)}")

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
                    SpineUtils.process_skel_downgrade(
                        skel_path, work_dir,
                        spine_options.converter_path, spine_options.target_version, log
                    )

                # 降级所有 atlas 文件（直接覆盖到工作目录）
                for atlas_path in work_dir.glob("*.atlas"):
                    log(f"  > {t('log.extractor.processing_file', name=atlas_path.name)}")
                    SpineUtils.process_atlas_downgrade(atlas_path, work_dir, log)

            # 2.2 Atlas解包处理
            if atlas_export_mode in ("unpack", "both"):
                log(f'\n--- {t("log.section.process_atlas_unpack")} ---')

                for atlas_path in work_dir.glob("*.atlas"):
                    SpineUtils.unpack_atlas_frames(atlas_path, output_dir, log)

                    # unpack模式下删除atlas和png（只保留解包后的帧）
                    if atlas_export_mode == "unpack":
                        atlas_path.unlink(missing_ok=True)
                        png_path = work_dir / f"{atlas_path.stem}.png"
                        png_path.unlink(missing_ok=True)

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

def _migrate_bundle_assets(
    old_bundle_path: Path,
    new_bundle_path: Path,
    asset_types_to_replace: set[str],
    spine_options: SpineOptions | None = None,
    log: LogFunc = no_log,
) -> tuple[Bundle | None, ReplacementResult]:
    """
    执行asset迁移的核心替换逻辑。
    返回一个元组 (modified_bundle, result)，如果失败则 modified_bundle 为 None。
    """
    # 1. 加载 bundles
    log(t("log.migration.extracting_from_old_bundle", types=', '.join(asset_types_to_replace)))
    old_bundle = Bundle.load(old_bundle_path, log)
    if not old_bundle:
        return None, ReplacementResult(0, 0, [], [])
    
    log(t("log.migration.loading_new_bundle"))
    new_bundle = Bundle.load(new_bundle_path, log)
    if not new_bundle:
        return None, ReplacementResult(0, 0, [], [])

    # 定义匹配策略
    strategies: list[tuple[str, KeyGeneratorFunc]] = [
        ('path_id', MATCH_STRATEGIES['path_id']),
        ('cont_name_type', MATCH_STRATEGIES['cont_name_type']),
        ('name_type', MATCH_STRATEGIES['name_type']),
        # ('container', MATCH_STRATEGIES['container']),
        # 因为多个Mesh可能共享同一个Container，所以这个策略很可能失效，因此不使用
    ]

    for name, key_func in strategies:
        log(f'\n{t("log.migration.trying_strategy", name=name)}')
        
        # 2. 根据当前策略从旧版 bundle 构建"替换清单"
        log(f'  > {t("log.migration.extracting_from_old_bundle_simple")}')
        old_assets_map = old_bundle.extract_assets_for_migration(
            asset_types_to_replace, key_func, spine_options
        )
        
        if not old_assets_map:
            log(f"  > ⚠️ {t('common.warning')}: {t('log.migration.strategy_no_assets_found', name=name)}")
            continue

        log(f'  > {t("log.migration.extraction_complete", name=name, count=len(old_assets_map))}')

        # 3. 根据当前策略应用替换
        log(f'  > {t("log.migration.writing_to_new_bundle")}')
        
        result = new_bundle.apply_replacements(old_assets_map, key_func)
        
        # 4. 如果当前策略成功匹配了至少一个资源，就结束
        if result.is_success:
            log(f"\n✅ {t('log.migration.strategy_success', name=name, count=result.replaced_count)}:")
            for item in result.replaced_logs:
                log(f"  - {item}")
            return new_bundle, result

        log(f'  > {t("log.migration.strategy_no_match", name=name)}')

    # 5. 所有策略都失败了
    log(f"\n⚠️ {t('common.warning')}: {t('log.migration.all_strategies_failed', types=', '.join(asset_types_to_replace))}")
    return None, ReplacementResult(0, 0, [], [])

def process_mod_update(
    old_mod_path: Path,
    new_bundle_path: Path,
    output_dir: Path,
    asset_types_to_replace: set[str],
    save_options: SaveOptions,
    spine_options: SpineOptions | None = None,
    log: LogFunc = no_log,
    skip_unchanged: bool = False,
) -> tuple[bool, str]:
    """
    自动化Mod更新流程。
    
    该函数是Mod更新工具的核心处理函数，负责将旧版Mod中的资源替换到新版游戏资源中，
    并可选地进行CRC校验修正以确保文件兼容性。
    
    处理流程的主要阶段：
    - asset迁移：将旧版Mod中的指定类型资源替换到新版资源文件中
        - 支持替换Texture2D、TextAsset、Mesh等资源类型
        - 可选地升级Spine动画资源的Skel版本
    - CRC修正：根据选项决定是否对新生成的文件进行CRC校验修正
    
    Args:
        old_mod_path: 旧版Mod文件的路径
        new_bundle_path: 新版游戏资源文件的路径
        output_dir: 输出目录，用于保存生成的更新后文件
        asset_types_to_replace: 需要替换的资源类型集合（如 {"Texture2D", "TextAsset"}）
        save_options: 保存和CRC修正的选项
        spine_options: Spine资源升级的选项
        log: 日志记录函数，默认为空函数
        skip_unchanged: 是否跳过未变化的文件
    
    Returns:
        tuple[bool, str]: (是否成功, 状态消息) 的元组
        如果skip_unchanged=True且所有资源都未变化，返回 (True, "unchanged")
    """
    try:
        log("="*50)
        log(f'  > {t("log.mod_update.using_old_mod", name=old_mod_path.name)}')
        log(f'  > {t("log.mod_update.using_new_resource", name=new_bundle_path.name)}')

        # 进行asset迁移
        log(f'\n--- {t("log.section.asset_migration")} ---')
        modified_bundle, result = _migrate_bundle_assets(
            old_bundle_path=old_mod_path, 
            new_bundle_path=new_bundle_path, 
            asset_types_to_replace=asset_types_to_replace, 
            spine_options=spine_options,
            log = log
        )

        if not modified_bundle:
            return False, t("message.mod_update.migration_failed")
        if not result.is_success:
            return False, t("message.mod_update.no_matching_assets_to_replace")
        
        # 检查是否所有匹配的资源都未变化（只有skipped，没有实际替换）
        if skip_unchanged and result.replaced_count == 0 and result.skipped_count > 0:
            log(f'  > ⏭️ {t("log.mod_update.all_resources_unchanged", count=result.skipped_count)}')
            return True, "unchanged"
        
        log(f'  > {t("log.mod_update.migration_complete", count=result.replaced_count)}')
        
        # 保存和修正文件
        output_path = output_dir / new_bundle_path.name
        save_ok, save_message = modified_bundle.save(output_path, save_options)

        if not save_ok:
            return False, save_message

        log(t("log.file.saved", path=output_path))
        log(f"\n🎉 {t('log.mod_update.all_processes_complete')}")
        return True, t("message.mod_update.success")

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.error_processing', error=e)}")
        log(traceback.format_exc())
        return False, t("message.error_during_process", error=e)

def process_batch_mod_update(
    mod_file_list: list[Path],
    search_paths: list[Path],
    output_dir: Path,
    asset_types_to_replace: set[str],
    save_options: SaveOptions,
    spine_options: SpineOptions | None,
    log: LogFunc = no_log,
    progress_callback: Callable[[int, int, str], None] | None = None,
    skip_unchanged: bool = False,
) -> tuple[int, int, list[str], list[tuple[Path, Path]]]:
    """
    执行批量Mod更新的核心逻辑。

    Args:
        mod_file_list: 待更新的旧Mod文件路径列表。
        search_paths: 用于查找新版bundle文件的目录列表。
        output_dir: 输出目录。
        asset_types_to_replace: 需要替换的资源类型集合。
        save_options: 保存和CRC修正的选项。
        spine_options: Spine资源升级的选项。
        log: 日志记录函数。
        progress_callback: 进度回调函数，用于更新UI。
                           接收 (当前索引, 总数, 文件名)。
        skip_unchanged: 是否跳过未变化的文件

    Returns:
        tuple[int, int, list[str], list[tuple[Path, Path]]]: 
            (成功计数, 失败计数, 失败任务详情列表, (输出文件路径, 被替换的原始文件路径) 元组列表)
    """
    total_files = len(mod_file_list)
    success_count = 0
    fail_count = 0
    failed_tasks = []
    file_pairs: list[tuple[Path, Path]] = []

    # 遍历每个旧Mod文件
    for i, old_mod_path in enumerate(mod_file_list):
        current_progress = i + 1
        filename = old_mod_path.name
        
        if progress_callback:
            progress_callback(current_progress, total_files, filename)

        log("\n" + "=" * 50)
        log(t("status.processing_batch", current=current_progress, total=total_files, filename=filename))

        new_bundle_paths, find_message = find_new_bundle_path(old_mod_path, search_paths, log)

        if not new_bundle_paths:
            log(f'❌ {t("log.search.find_failed", message=find_message)}')
            fail_count += 1
            failed_tasks.append(f"{filename} - {t('log.search.find_failed', message=find_message)}")
            continue

        # 使用第一个匹配的文件
        new_bundle_path = new_bundle_paths[0]

        # 执行Mod更新处理
        success, process_message = process_mod_update(
            old_mod_path=old_mod_path,
            new_bundle_path=new_bundle_path,
            output_dir=output_dir,
            asset_types_to_replace=asset_types_to_replace,
            save_options=save_options,
            spine_options=spine_options,
            log=log,
            skip_unchanged=skip_unchanged
        )

        if success:
            if process_message == "unchanged":
                # 资源未变化，不生成输出文件
                log(f'⏭️ {t("log.batch.process_unchanged", filename=filename)}')
            else:
                log(f'✅ {t("log.batch.process_success", filename=filename)}')
                success_count += 1
                # 记录输出文件路径和被替换的原始文件路径（封装成tuple）
                output_path = output_dir / new_bundle_path.name
                if output_path.exists():
                    file_pairs.append((output_path, new_bundle_path))
        else:
            log(f'❌ {t("log.batch.process_failed", filename=filename, message=process_message)}')
            fail_count += 1
            failed_tasks.append(f"{filename} - {process_message}")

    # 打印输出文件列表（不包括跳过的）
    if file_pairs:
        log(f'\n{t("log.batch.output_files_list", count=len(file_pairs))}')
        for output_path, _ in file_pairs:
            log(f'  - {output_path.name}')

    return success_count, fail_count, failed_tasks, file_pairs


def process_batch_legacy_batch(
    legacy_file_list: list[Path],
    search_paths: list[Path],
    output_dir: Path,
    asset_types_to_replace: set[str],
    save_options: SaveOptions,
    log: LogFunc = no_log,
    progress_callback: Callable[[int, int, str], None] | None = None,
    skip_unchanged: bool = False,
) -> tuple[int, int, list[str], list[tuple[Path, Path]]]:
    """
    执行批量旧版国际服到新版国际服转换的核心逻辑。

    Args:
        legacy_file_list: 待转换的旧版国际服文件路径列表。
        search_paths: 用于查找新版bundle文件的目录列表。
        output_dir: 输出目录。
        asset_types_to_replace: 需要替换的资源类型集合。
        save_options: 保存和CRC修正的选项。
        log: 日志记录函数。
        progress_callback: 进度回调函数，用于更新UI。
                           接收 (当前索引, 总数, 文件名)。
        skip_unchanged: 是否跳过未变化的文件

    Returns:
        tuple[int, int, list[str], list[tuple[Path, Path]]]: 
            (成功计数, 失败计数, 失败任务详情列表, (输出文件路径, 被替换的原始文件路径) 元组列表)
    """
    total_files = len(legacy_file_list)
    success_count = 0
    fail_count = 0
    failed_tasks = []
    file_pairs: list[tuple[Path, Path]] = []

    # 遍历每个旧版国际服文件
    for i, legacy_file_path in enumerate(legacy_file_list):
        current_progress = i + 1
        filename = legacy_file_path.name
        
        if progress_callback:
            progress_callback(current_progress, total_files, filename)

        log("\n" + "=" * 50)
        log(t("status.processing_batch", current=current_progress, total=total_files, filename=filename))

        new_global_files = find_all_jp_counterparts(legacy_file_path, search_paths, log)

        if not new_global_files:
            log(f'❌ {t("log.search.no_found")}')
            fail_count += 1
            failed_tasks.append(f"{filename} - {t('log.search.no_found')}")
            continue

        # 执行转换处理
        success, process_message, replaced_files = process_global_to_jp_conversion(
            global_bundle_path=legacy_file_path,
            jp_template_paths=new_global_files,
            output_dir=output_dir,
            save_options=save_options,
            asset_types_to_replace=asset_types_to_replace,
            log=log,
            skip_unchanged=skip_unchanged
        )

        if success:
            if skip_unchanged and not replaced_files:
                # 没有文件被实际替换（全部被跳过）
                log(f'⏭️ {t("log.batch.process_unchanged", filename=filename)}')
            else:
                log(f'✅ {t("log.batch.process_success", filename=filename)}')
                success_count += 1
                # 记录输出文件路径和被替换的原始文件路径（封装成tuple）
                for src_file in replaced_files:
                    output_path = output_dir / src_file.name
                    if output_path.exists():
                        file_pairs.append((output_path, src_file))
        else:
            log(f'❌ {t("log.batch.process_failed", filename=filename, message=process_message)}')
            fail_count += 1
            failed_tasks.append(f"{filename} - {process_message}")

    # 打印输出文件列表（不包括跳过的）
    if file_pairs:
        log(f'\n{t("log.batch.output_files_list", count=len(file_pairs))}')
        for output_path, _ in file_pairs:
            log(f'  - {output_path.name}')

    return success_count, fail_count, failed_tasks, file_pairs

# ====== 日服处理相关 ======

def find_all_jp_counterparts(
    global_bundle_path: Path,
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> list[Path]:
    """
    根据国际服bundle文件，查找所有相关的日服 bundle 文件。
    日服文件通常包含额外的类型标识（如 -materials-, -timelines- 等）。

    Args:
        global_bundle_path: 国际服bundle文件的路径。
        search_dirs: 用于查找的目录列表。
        log: 日志记录函数。

    Returns:
        找到的日服文件路径列表。
    """
    log(t("log.jp_convert.searching_jp_counterparts", name=global_bundle_path.name))

    # 1. 从国际服文件名提取前缀
    prefix, prefix_message = get_filename_prefix(global_bundle_path.name, log)
    if not prefix:
        log(f'  > ❌ {t("log.search.find_failed")}: {prefix_message}')
        return []
    
    log(f"  > {t('log.search.file_prefix', prefix=prefix)}")

    jp_files: list[Path] = []
    seen_names = set()

    # 2. 在搜索目录中查找匹配前缀的所有文件
    for search_dir in search_dirs:
        if not (search_dir.exists() and search_dir.is_dir()):
            continue
        
        for file_path in search_dir.iterdir():
            # 排除自身
            if file_path.name == global_bundle_path.name:
                continue
                
            # 检查文件是否以通用前缀开头，且是 bundle 文件
            if file_path.is_file() and file_path.name.startswith(prefix) and file_path.suffix == '.bundle':
                if file_path.name not in seen_names:
                    jp_files.append(file_path)
                    seen_names.add(file_path.name)
                    log(f"  > {t('log.jp_convert.found_match', path=file_path.name)}")

    return jp_files

def process_jp_to_global_conversion(
    global_bundle_path: Path,
    jp_bundle_paths: list[Path],
    output_dir: Path,
    save_options: SaveOptions,
    asset_types_to_replace: set[str],
    log: LogFunc = no_log,
) -> tuple[bool, str]:
    """
    处理日服转国际服的转换。
    
    将日服多个资源bundle中的资源，替换到国际服的基础bundle文件中对应的部分。
    此过程只替换同名同类型的现有资源，不添加新资源。
    
    Args:
        global_bundle_path: 国际服bundle文件路径（作为基础）
        jp_bundle_paths: 日服bundle文件路径列表
        output_dir: 输出目录
        save_options: 保存和CRC修正的选项
        log: 日志记录函数
    
    Returns:
        tuple[bool, str]: (是否成功, 状态消息) 的元组
    """
    try:
        log("="*50)
        log(t("log.jp_convert.starting_jp_to_global"))
        log(f'  > {t("log.jp_convert.global_base_file", name=global_bundle_path.name)}')
        log(f'  > {t("log.jp_convert.jp_files_count", count=len(jp_bundle_paths))}')
        
        # 1. 从所有日服包中构建一个完整的"替换清单"
        log(f'\n--- {t("log.section.extracting_from_jp")} ---')
        replacement_map: dict[AssetKey, AssetContent] = {}
        strategy_name = 'cont_name_type'
        key_func = MATCH_STRATEGIES[strategy_name]

        total_files = len(jp_bundle_paths)
        for i, jp_path in enumerate(jp_bundle_paths, 1):
            log(t("log.processing_filename_with_progress", current=i, total=total_files, name=jp_path.name))
            jp_bundle = Bundle.load(jp_path, log)
            if not jp_bundle:
                log(f"    > ⚠️ {t('message.load_failed')}: {jp_path.name}")
                continue
            
            jp_assets = jp_bundle.extract_assets_for_migration(
                asset_types_to_replace, key_func, None
            )
            replacement_map.update(jp_assets)

        if not replacement_map:
            msg = t("message.jp_convert.no_assets_in_source")
            log(f"  > ⚠️ {msg}")
            return False, msg
        
        log(f"  > {t('log.jp_convert.extracted_count_from_jp', count=len(replacement_map))}")

        # 2. 加载国际服 base 并应用替换
        log(f'\n--- {t("log.section.applying_to_global")} ---')
        global_bundle = Bundle.load(global_bundle_path, log)
        if not global_bundle:
            return False, t("message.jp_convert.load_global_failed")
        
        result = global_bundle.apply_replacements(replacement_map, key_func)
        
        if not result.is_success:
            log(f"  > ⚠️ {t('log.jp_convert.no_assets_replaced')}")
            return False, t("message.jp_convert.no_assets_matched")
            
        log(f"\n✅ {t('log.migration.strategy_success', name=strategy_name, count=result.replaced_count)}:")
        for item in result.replaced_logs:
            log(f"  - {item}")
        
        # 3. 保存最终文件
        output_path = output_dir / global_bundle_path.name
        save_ok, save_message = global_bundle.save(output_path, save_options)
        
        if not save_ok:
            return False, save_message
        
        log(f"  ✅ {t('log.file.saved', path=output_path)}")
        log(f"\n🎉 {t('log.jp_convert.jp_to_global_complete')}")
        return True, t("message.jp_convert.jp_to_global_success", asset_count=result.replaced_count)
        
    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.jp_convert.error_jp_to_global', error=e)}")
        log(traceback.format_exc())
        return False, t("message.jp_convert.conversion_error", error=e)
        
def process_global_to_jp_conversion(
    global_bundle_path: Path,
    jp_template_paths: list[Path],
    output_dir: Path,
    save_options: SaveOptions,
    asset_types_to_replace: set[str],
    log: LogFunc = no_log,
    skip_unchanged: bool = False,
) -> tuple[bool, str, list[Path]]:
    """
    处理国际服转日服的转换。

    将一个国际服格式的bundle文件，使用多个日服bundle作为模板，
    将国际服的资源分发替换到对应的日服文件中。
    只替换模板中已存在的同名同类型资源。

    Args:
        global_bundle_path: 待转换的国际服bundle文件路径。
        jp_template_paths: 日服bundle文件路径列表（用作模板）。
        output_dir: 输出目录。
        save_options: 保存选项。
        asset_types_to_replace: 要替换的资源类型集合。
        log: 日志记录函数。
        skip_unchanged: 是否跳过未变化的文件

    Returns:
        tuple[bool, str, list[Path]]: (是否成功, 状态消息, 被替换的原始文件路径列表) 的元组
    """
    try:
        log("="*50)
        log(t("log.jp_convert.starting_global_to_jp"))
        log(f'  > {t("log.jp_convert.global_source_file", name=global_bundle_path.name)}')
        log(f'  > {t("log.jp_convert.jp_files_count", count=len(jp_template_paths))}')
        
        global_bundle = Bundle.load(global_bundle_path, log)
        if not global_bundle:
            return False, t("message.jp_convert.load_global_source_failed")
        
        log(f'\n--- {t("log.section.extracting_from_global")} ---')

        # 定义匹配策略
        strategies: list[tuple[str, KeyGeneratorFunc]] = [
            ('path_id', MATCH_STRATEGIES['path_id']),
            ('cont_name_type', MATCH_STRATEGIES['cont_name_type']),
            ('name_type', MATCH_STRATEGIES['name_type']),
        ]

        success_count = 0
        total_changes = 0
        total_files = len(jp_template_paths)
        replaced_files: list[Path] = []  # 记录被成功替换的原始文件路径

        # 2. 按顺序尝试每种策略
        for strategy_name, key_func in strategies:
            log(f'\n{t("log.migration.trying_strategy", name=strategy_name)}')

            source_replacement_map = global_bundle.extract_assets_for_migration(
                asset_types_to_replace, key_func, None
            )

            if not source_replacement_map:
                log(f"  > ⚠️ {t('common.warning')}: {t('log.migration.strategy_no_assets_found', name=strategy_name)}")
                continue

            log(f"  > {t('log.jp_convert.extracted_count', count=len(source_replacement_map))}")

            strategy_success = False
            strategy_total_changes = 0

            # 3. 遍历每个日服模板文件进行处理
            for i, jp_template_path in enumerate(jp_template_paths, 1):
                log(t("log.processing_filename_with_progress", current=i, total=total_files, name=jp_template_path.name))

                template_bundle = Bundle.load(jp_template_path, log)
                if not template_bundle:
                    log(f"  > ❌ {t('message.load_failed')}: {jp_template_path.name}")
                    continue

                result = template_bundle.apply_replacements(source_replacement_map, key_func)

                if result.is_success:
                    # 检查是否所有匹配的资源都未变化（只有skipped，没有实际替换）
                    if skip_unchanged and result.replaced_count == 0 and result.skipped_count > 0:
                        log(f"⏭️ {t('log.jp_convert.file_unchanged', name=jp_template_path.name, count=result.skipped_count)}")
                        # 跳过也算作策略成功，避免继续尝试其他策略
                        strategy_success = True
                    else:
                        log(f"✅ {t('log.migration.strategy_success', name=strategy_name, count=result.replaced_count)}")
                        for item in result.replaced_logs:
                            log(f"  - {item}")

                        output_path = output_dir / jp_template_path.name
                        save_ok, save_msg = template_bundle.save(output_path, save_options)
                        if save_ok:
                            log(f"  ✅ {t('log.file.saved', path=output_path)}")
                            success_count += 1
                            total_changes += result.replaced_count
                            strategy_success = True
                            strategy_total_changes += result.replaced_count
                            replaced_files.append(jp_template_path)  # 记录被替换的原始文件
                        else:
                            log(f"  ❌ {t('log.file.save_failed', path=output_path, error=save_msg)}")
                else:
                    log(f"  > {t('log.file.no_changes_made')}")

            # 如果当前策略成功替换了至少一个资源，就结束
            if strategy_success:
                if strategy_total_changes == 0:
                    # 所有文件都被跳过
                    log(f"\n⏭️ {t('log.migration.strategy_skipped_unchanged', name=strategy_name)}")
                else:
                    log(f"\n✅ {t('log.migration.strategy_success', name=strategy_name, count=strategy_total_changes)}")
                break

        log(f'\n--- {t("log.section.conversion_complete")} ---')
        log(f"{t('log.jp_convert.global_to_jp_complete')}")
        return True, t("message.jp_convert.global_to_jp_success",bundle_count=success_count, asset_count=total_changes), replaced_files

    except Exception as e:
        log(f"\n❌ {t('common.error')}: {t('log.jp_convert.error_global_to_jp', error=e)}")
        log(traceback.format_exc())
        return False, t("message.jp_convert.conversion_error", error=e), []