# cli/handlers.py
import logging
import shutil
import sys
from pathlib import Path

from .taps import UpdateTap, PackTap, CrcTap, EnvTap, ExtractTap, SplitTap, MergeTap, BatchUpdateTap, BatchLegacyTap
from ..core import (
    find_new_bundle_path,
    find_all_jp_counterparts,
    SaveOptions,
    SpineOptions,
    process_mod_update,
    process_asset_packing,
    process_asset_extraction,
    process_modern_to_legacy_conversion,
    process_legacy_to_modern_conversion,
    process_batch_mod_update,
    process_batch_legacy_batch,
)
from ..models import SaveOptions, SpineOptions
from ..utils import get_environment_info, CRCUtils, get_BA_path, get_search_resource_dirs, parse_hex_bytes
from ..naming import parse_filename

class Logger:
    """日志记录器基类。"""

    def log(self, message: str) -> None:
        raise NotImplementedError


class CLILogger(Logger):
    """CLI 日志记录器，输出到控制台。"""

    def __init__(self) -> None:
        log = logging.getLogger('cli')
        if not log.handlers:
            log.setLevel(logging.INFO)
            handler = logging.StreamHandler(sys.stdout)
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            log.addHandler(handler)
        self._log = log

    def log(self, message: str) -> None:
        self._log.info(message)


class NullLogger(Logger):
    """空日志记录器，什么都不做。"""

    def log(self, message: str) -> None:
        pass


# 全局 NullLogger 实例，作为默认参数使用
NULL_LOGGER = NullLogger()


def setup_cli_logger() -> Logger:
    """配置一个简单的日志记录器，将日志输出到控制台。"""
    return CLILogger()


def handle_update(args: UpdateTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'update' 命令的逻辑。"""
    logger.log("--- Start Mod Update ---")

    old_mod_path = Path(args.old)
    output_dir = Path(args.output_dir)

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定资源目录：优先使用 --resource-dir，否则自动搜寻
    resource_dir = args.resource_dir or get_BA_path()

    new_bundle_path: Path | None = None
    if args.target:
        new_bundle_path = Path(args.target)
    elif resource_dir:
        logger.log(f"Searching target bundle in '{resource_dir}'...")
        resource_path = Path(resource_dir)
        if not resource_path.is_dir():
            logger.log(f"❌ Error: Game resource directory '{resource_path}' does not exist or is not a directory.")
            return

        found_paths, message = find_new_bundle_path(old_mod_path, get_search_resource_dirs(resource_path), logger.log)
        if not found_paths:
            logger.log(f"❌ Auto-search failed: {message}")
            return
        new_bundle_path = found_paths[0]

    if not new_bundle_path:
        logger.log("❌ Error: Must provide '--target' or '--resource-dir' to determine the target resource file.")
        return

    asset_types = set(args.asset_types)
    logger.log(f"Specified asset replacement types: {', '.join(asset_types)}")

    save_options = SaveOptions(
        perform_crc=not args.no_crc,
        extra_bytes=parse_hex_bytes(args.extra_bytes),
        compression=args.compression
    )

    spine_options = SpineOptions(
        enabled=args.enable_spine_conversion,
        converter_path=Path(args.spine_converter_path) if args.spine_converter_path else None,
        target_version=args.target_spine_version or None,
    )

    # 调用核心处理函数
    success, message = process_mod_update(
        old_mod_path=old_mod_path,
        new_bundle_path=new_bundle_path,
        output_dir=output_dir,
        asset_types_to_replace=asset_types,
        save_options=save_options,
        spine_options=spine_options,
        log=logger.log
    )

    logger.log("\n" + "="*50)
    if success:
        logger.log(f"✅ Operation Successful: {message}")
    else:
        logger.log(f"❌ Operation Failed: {message}")


def handle_batch_update(args: BatchUpdateTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'batch-update' 命令的逻辑。"""
    logger.log("--- Start Batch Mod Update ---")

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    # 验证输入目录
    if not input_dir.is_dir():
        logger.log(f"❌ Error: Input directory '{input_dir}' does not exist or is not a directory.")
        return

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定资源目录
    resource_dir = args.resource_dir or get_BA_path()
    if not resource_dir:
        logger.log("❌ Error: Cannot find game resource directory. Please provide --resource-dir.")
        return

    resource_path = Path(resource_dir)
    if not resource_path.is_dir():
        logger.log(f"❌ Error: Game resource directory '{resource_path}' does not exist or is not a directory.")
        return

    # 获取搜索路径
    search_paths = get_search_resource_dirs(resource_path)
    logger.log(f"Searching for new bundles in '{resource_path}'...")

    # 收集输入目录中的所有.bundle文件
    mod_file_list = list(input_dir.glob("*.bundle"))
    if not mod_file_list:
        logger.log(f"❌ Error: No .bundle files found in input directory '{input_dir}'.")
        return

    logger.log(f"Found {len(mod_file_list)} bundle file(s) to process:")
    for f in mod_file_list:
        logger.log(f"  - {f.name}")

    # 处理资源类型
    asset_types = set(args.asset_types)
    if 'ALL' in asset_types:
        asset_types = {'ALL'}
    logger.log(f"Specified asset replacement types: {', '.join(asset_types)}")

    # 创建保存选项
    save_options = SaveOptions(
        perform_crc=not args.no_crc,
        extra_bytes=parse_hex_bytes(args.extra_bytes),
        compression=args.compression
    )

    # 创建Spine选项
    spine_options = SpineOptions(
        enabled=args.enable_spine_conversion,
        converter_path=Path(args.spine_converter_path) if args.spine_converter_path else None,
        target_version=args.target_spine_version or None,
    )

    callback_log = lambda current, total, filename: logger.log(
            f"[{current}/{total}] Processing: {filename}"
        )

    # 调用批量处理函数
    success_count, fail_count, failed_tasks, file_pairs = process_batch_mod_update(
        mod_file_list=mod_file_list,
        search_paths=search_paths,
        output_dir=output_dir,
        asset_types_to_replace=asset_types,
        save_options=save_options,
        spine_options=spine_options,
        log=logger.log,
        progress_callback=callback_log,
        skip_unchanged=True
    )

    # 输出结果摘要
    logger.log("\n" + "="*50)
    logger.log(f"Batch Update Summary:")
    logger.log(f"  Total files: {len(mod_file_list)}")
    logger.log(f"  Successful: {success_count}")
    logger.log(f"  Failed: {fail_count}")

    if file_pairs:
        logger.log(f"\n✅ Output files ({len(file_pairs)}):")
        for output_path, _ in file_pairs:
            logger.log(f"  - {output_path.name}")

    if failed_tasks:
        logger.log(f"\n❌ Failed tasks:")
        for task in failed_tasks:
            logger.log(f"  - {task}")

    logger.log("="*50)


def _get_modern_files(args: SplitTap | MergeTap, logger) -> list[Path] | None:
    """获取modern files列表，优先使用直接指定的文件，其次使用智能搜索。

    Args:
        args: 命令参数
        logger: 日志记录器

    Returns:
        modern文件路径列表，出错时返回None
    """
    # 优先使用直接指定的文件列表
    if args.modern_files:
        files = [Path(f) for f in args.modern_files]
        valid_files = []
        for f in files:
            if f.is_file():
                valid_files.append(f)
            else:
                logger.log(f"❌ Error: Modern file not found: {f}")
        if not valid_files:
            logger.log("❌ Error: No valid modern files provided.")
            return None
        logger.log(f"Using {len(valid_files)} specified modern file(s)")
        for f in valid_files:
            logger.log(f"  - {f.name}")
        return valid_files

    # 其次使用智能搜索（基于文件名前缀匹配）
    if args.resource_dir:
        dir_path = Path(args.resource_dir)
        if not dir_path.is_dir():
            logger.log(f"❌ Error: Resource directory not found: {dir_path}")
            return None
        # 使用 find_all_jp_counterparts 智能查找相关文件
        files = find_all_jp_counterparts(
            global_bundle_path=Path(args.legacy),
            search_dirs=[dir_path],
            log=logger.log
        )
        if not files:
            logger.log(f"❌ Error: No matching modern files found in: {dir_path}")
            return None
        logger.log(f"Found {len(files)} matching modern file(s) in directory: {dir_path}")
        for f in files:
            logger.log(f"  - {f.name}")
        return files

    logger.log("❌ Error: Must provide either --modern-files or --resource-dir")
    return None


def handle_split(args: SplitTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'split' 命令的逻辑。

    将legacy bundle中的资源拆分到多个modern bundle中（一分多）。
    对应core.process_global_to_jp_conversion。
    """
    logger.log("--- Start Split Operation ---")

    legacy_path = Path(args.legacy)
    output_dir = Path(args.output_dir)

    # 验证legacy bundle存在
    if not legacy_path.is_file():
        logger.log(f"❌ Error: Legacy bundle file '{legacy_path}' does not exist.")
        return

    # 获取modern files
    modern_files = _get_modern_files(args, logger)
    if modern_files is None:
        return

    # 确保输出目录存在
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.log(f"❌ Error: Failed to create output directory: {e}")
        return

    # 处理资源类型
    asset_types = set(args.asset_types)
    if 'ALL' in asset_types:
        asset_types = {'Texture2D', 'TextAsset', 'Mesh'}
    logger.log(f"Specified asset replacement types: {', '.join(asset_types)}")

    # 创建SaveOptions
    save_options = SaveOptions(
        perform_crc=not args.no_crc,
        extra_bytes=parse_hex_bytes(args.extra_bytes),
        compression=args.compression
    )

    # 调用核心处理函数 (split = global_to_jp = 一分多)
    logger.log(f"\nSplitting assets from '{legacy_path.name}' to {len(modern_files)} modern file(s)...")
    success, message, replaced_files = process_legacy_to_modern_conversion(
        legacy_bundle_path=legacy_path,
        modern_bundle_paths=modern_files,
        output_dir=output_dir,
        save_options=save_options,
        asset_types_to_replace=asset_types,
        log=logger.log,
        skip_unchanged=True
    )

    logger.log("\n" + "="*50)
    if success:
        logger.log(f"✅ Operation Successful: {message}")
    else:
        logger.log(f"❌ Operation Failed: {message}")


def handle_merge(args: MergeTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'merge' 命令的逻辑。

    将多个modern bundle中的资源合并到legacy bundle中（多并一）。
    对应core.process_jp_to_global_conversion。
    """
    logger.log("--- Start Merge Operation ---")

    legacy_path = Path(args.legacy)
    output_dir = Path(args.output_dir)

    # 验证legacy bundle存在
    if not legacy_path.is_file():
        logger.log(f"❌ Error: Legacy bundle file '{legacy_path}' does not exist.")
        return

    # 获取modern files
    modern_files = _get_modern_files(args, logger)
    if modern_files is None:
        return

    # 确保输出目录存在
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.log(f"❌ Error: Failed to create output directory: {e}")
        return

    # 处理资源类型
    asset_types = set(args.asset_types)
    if 'ALL' in asset_types:
        asset_types = {'Texture2D', 'TextAsset', 'Mesh'}
    logger.log(f"Specified asset replacement types: {', '.join(asset_types)}")

    # 创建SaveOptions
    save_options = SaveOptions(
        perform_crc=not args.no_crc,
        extra_bytes=parse_hex_bytes(args.extra_bytes),
        compression=args.compression
    )

    # 调用核心处理函数 (merge = jp_to_global = 多并一)
    logger.log(f"\nMerging assets from {len(modern_files)} modern file(s) into '{legacy_path.name}'...")
    success, message = process_modern_to_legacy_conversion(
        legacy_bundle_path=legacy_path,
        modern_bundle_paths=modern_files,
        output_dir=output_dir,
        save_options=save_options,
        asset_types_to_replace=asset_types,
        log=logger.log
    )

    logger.log("\n" + "="*50)
    if success:
        logger.log(f"✅ Operation Successful: {message}")
    else:
        logger.log(f"❌ Operation Failed: {message}")


def handle_batch_legacy(args: BatchLegacyTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'batch-legacy' 命令的逻辑。"""
    logger.log("--- Start Batch Legacy Conversion ---")

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    # 验证输入目录
    if not input_dir.is_dir():
        logger.log(f"❌ Error: Input directory '{input_dir}' does not exist or is not a directory.")
        return

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 确定资源目录
    resource_dir = args.resource_dir or get_BA_path()
    if not resource_dir:
        logger.log("❌ Error: Cannot find game resource directory. Please provide --resource-dir.")
        return

    resource_path = Path(resource_dir)
    if not resource_path.is_dir():
        logger.log(f"❌ Error: Game resource directory '{resource_path}' does not exist or is not a directory.")
        return

    # 获取搜索路径
    search_paths = get_search_resource_dirs(resource_path)
    logger.log(f"Searching for modern bundles in '{resource_path}'...")

    # 收集输入目录中的所有.bundle文件
    legacy_file_list = list(input_dir.glob("*.bundle"))
    if not legacy_file_list:
        logger.log(f"❌ Error: No .bundle files found in input directory '{input_dir}'.")
        return

    logger.log(f"Found {len(legacy_file_list)} legacy bundle file(s) to convert:")
    for f in legacy_file_list:
        logger.log(f"  - {f.name}")

    # 处理资源类型
    asset_types = set(args.asset_types)
    logger.log(f"Specified asset replacement types: {', '.join(asset_types)}")

    # 创建保存选项
    save_options = SaveOptions(
        perform_crc=not args.no_crc,
        extra_bytes=parse_hex_bytes(args.extra_bytes),
        compression=args.compression
    )

    callback_log = lambda current, total, filename: logger.log(
            f"[{current}/{total}] Processing: {filename}"
        )

    # 调用批量处理函数
    success_count, fail_count, failed_tasks, file_pairs = process_batch_legacy_batch(
        legacy_file_list=legacy_file_list,
        search_paths=search_paths,
        output_dir=output_dir,
        asset_types_to_replace=asset_types,
        save_options=save_options,
        log=logger.log,
        progress_callback=callback_log,
        skip_unchanged=True
    )

    # 输出结果摘要
    logger.log("\n" + "="*50)
    logger.log(f"Batch Legacy Conversion Summary:")
    logger.log(f"  Total files: {len(legacy_file_list)}")
    logger.log(f"  Successful: {success_count}")
    logger.log(f"  Failed: {fail_count}")

    if file_pairs:
        logger.log(f"\n✅ Output files ({len(file_pairs)}):")
        for output_path, _ in file_pairs:
            logger.log(f"  - {output_path.name}")

    if failed_tasks:
        logger.log(f"\n❌ Failed tasks:")
        for task in failed_tasks:
            logger.log(f"  - {task}")

    logger.log("="*50)

def handle_asset_packing(args: PackTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'pack' 命令的逻辑。"""
    logger.log("--- Start Asset Packing ---")

    bundle_path = Path(args.bundle)
    asset_folder = Path(args.folder)
    output_dir = Path(args.output_dir)

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bundle_path.is_file():
        logger.log(f"❌ Error: Bundle file '{bundle_path}' does not exist.")
        return
    if not asset_folder.is_dir():
        logger.log(f"❌ Error: Asset folder '{asset_folder}' does not exist.")
        return

    # 创建 SaveOptions 和 SpineOptions 对象
    save_options = SaveOptions(
        perform_crc=not args.no_crc,
        extra_bytes=parse_hex_bytes(args.extra_bytes),
        compression=args.compression
    )

    spine_options = SpineOptions(
        enabled=args.enable_spine_conversion,
        converter_path=Path(args.spine_converter_path) if args.spine_converter_path else None,
        target_version=args.target_spine_version or None,
    )

    # 调用核心处理函数
    success, message = process_asset_packing(
        target_bundle_path=bundle_path,
        asset_folder=asset_folder,
        output_dir=output_dir,
        save_options=save_options,
        spine_options=spine_options,
        log=logger.log
    )

    logger.log("\n" + "="*50)
    if success:
        logger.log(f"✅ Operation Successful: {message}")
    else:
        logger.log(f"❌ Operation Failed: {message}")


def handle_crc(args: CrcTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'crc' 命令的逻辑。"""
    logger.log("--- Start CRC Tool ---")

    modified_path = Path(args.modified)
    if not modified_path.is_file():
        logger.log(f"❌ Error: Modified file '{modified_path}' does not exist.")
        return

    resource_dir = args.resource_dir or get_BA_path()

    # 确定原始文件路径：优先使用 --original，其次使用 resource_dir 自动查找
    original_path = None
    if args.original:
        original_path = Path(args.original)
        if not original_path.is_file():
            logger.log(f"❌ Error: Manually specified original file '{original_path.name}' does not exist.")
            return
        logger.log(f"Manually specified original file: {original_path}")
    elif resource_dir:
        logger.log(f"No original file provided, searching automatically in '{resource_dir}'...")
        game_dir = Path(resource_dir)
        if not game_dir.is_dir():
            logger.log(f"❌ Error: Game resource directory '{game_dir}' does not exist or is not a directory.")
            return

        # 在搜索目录中查找同名文件（只取第一个找到的）
        search_dirs = get_search_resource_dirs(game_dir)
        target_name = modified_path.name
        original_path: Path | None = None
        for dir_path in search_dirs:
            if not dir_path.exists():
                continue
            candidate = dir_path / target_name
            if candidate.is_file():
                original_path = candidate
                break

        if original_path is None:
            logger.log(f"❌ Auto-search failed: File '{target_name}' not found in search directories")
            return
        logger.log(f"  > Found original file: {original_path}")

    # --- 模式 1: 仅检查/计算 CRC ---
    if args.check_only:
        try:
            with open(modified_path, "rb") as f:
                modified_data = f.read()
            modified_crc_hex = f"{CRCUtils.compute_crc32(modified_data):08X}"
            logger.log(f"Modified File CRC32: {modified_crc_hex}  ({modified_path.name})")

            if original_path:
                with open(original_path, "rb") as f:
                    original_data = f.read()
                original_crc_hex = f"{CRCUtils.compute_crc32(original_data):08X}"
                logger.log(f"Original File CRC32: {original_crc_hex}  ({original_path.name})")
                if original_crc_hex == modified_crc_hex:
                    logger.log("✅ CRC Match: Yes")
                else:
                    logger.log("❌ CRC Match: No")
        except Exception as e:
            logger.log(f"❌ Error computing CRC: {e}")
        return

    # --- 模式 2: 修正 CRC ---
    if not modified_path:
        logger.log("❌ Error: For CRC fix, must provide '--modified' file.")
        return

    try:
        # 从文件名提取目标 CRC
        _, _, _, _, crc_str = parse_filename(modified_path.name)
        if not crc_str:
            logger.log("❌ Error: Could not extract target CRC from filename.")
            return
        
        target_crc = int(crc_str)
        logger.log(f"Target CRC from filename: {target_crc:08X}")

        # 检查当前 CRC 是否已匹配
        with open(modified_path, "rb") as f:
            current_crc = CRCUtils.compute_crc32(f.read())
        
        if current_crc == target_crc:
            logger.log("⚠ CRC values already match, no fix needed.")
            return

        logger.log("CRC mismatch. Starting CRC fix...")

        if not args.no_backup:
            backup_path = modified_path.with_suffix(modified_path.suffix + '.backup')
            shutil.copy2(modified_path, backup_path)
            logger.log(f"  > Backup file created: {backup_path.name}")

        success = CRCUtils.manipulate_file_crc(modified_path, target_crc, parse_hex_bytes(args.extra_bytes))

        if success:
            logger.log("✅ CRC Fix Successful! The modified file has been updated.")
        else:
            logger.log("❌ CRC Fix Failed.")

    except Exception as e:
        logger.log(f"❌ Error during CRC fix process: {e}")


def handle_env(args: EnvTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'env' 命令，打印环境信息。"""
    logger.log(get_environment_info(ignore_tk=True))


def handle_extract(args: ExtractTap, logger: Logger = NULL_LOGGER) -> None:
    """处理 'extract' 命令的逻辑。"""
    logger.log("--- Start Asset Extraction ---")

    bundle_paths = [Path(b) for b in args.bundles]
    output_dir = Path(args.output_dir)

    # 验证bundle文件是否存在
    valid_bundles = []
    for bp in bundle_paths:
        if bp.is_file():
            valid_bundles.append(bp)
        else:
            logger.log(f"❌ Error: Bundle file '{bp}' does not exist.")

    if not valid_bundles:
        logger.log("❌ Error: No valid bundle files provided.")
        return

    # 确保基础输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    # 处理资源类型
    asset_types = set(args.asset_types)
    if 'ALL' in asset_types:
        asset_types = {'Texture2D', 'TextAsset', 'Mesh'}

    logger.log(f"Specified asset extraction types: {', '.join(asset_types)}")
    logger.log(f"Bundles to process: {len(valid_bundles)}")
    for bp in valid_bundles:
        logger.log(f"  - {bp.name}")

    # 创建SpineOptions对象
    spine_options = SpineOptions(
        enabled=args.enable_spine_downgrade,
        converter_path=Path(args.spine_converter_path) if args.spine_converter_path else None,
        target_version=args.target_spine_version or None,
    )

    # 检查Spine降级配置
    if args.enable_spine_downgrade:
        if not spine_options.is_valid():
            logger.log("❌ Error: Spine downgrade is enabled but configuration is invalid.")
            logger.log("   Please provide a valid --spine-converter-path and --target-spine-version.")
            return
        logger.log(f"Spine downgrade enabled: target version {args.target_spine_version}")

    # 确定子目录名
    subdir_name = args.subdir.strip() if args.subdir else ""
    if not subdir_name and len(valid_bundles) == 1:
        # 单个bundle时，自动从文件名提取核心名作为子目录
        subdir_name = parse_filename(valid_bundles[0].stem).core

    # 确定最终输出路径
    if subdir_name:
        final_output_dir = output_dir / subdir_name
    else:
        final_output_dir = output_dir

    logger.log(f"Base output directory: {output_dir}")
    if subdir_name:
        logger.log(f"Subdirectory: {subdir_name}")
    logger.log(f"Final output directory: {final_output_dir}")

    # 调用核心处理函数
    success, message = process_asset_extraction(
        bundle_path=valid_bundles,
        output_dir=final_output_dir,
        asset_types_to_extract=asset_types,
        spine_options=spine_options,
        atlas_export_mode=args.atlas_export_mode,
        log=logger.log
    )

    logger.log("\n" + "="*50)
    if success:
        logger.log(f"✅ Operation Successful: {message}")
    else:
        logger.log(f"❌ Operation Failed: {message}")
