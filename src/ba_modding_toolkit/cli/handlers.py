# cli/handlers.py
import logging
import shutil
import sys
from pathlib import Path

from .taps import UpdateTap, PackTap, CrcTap, EnvTap, ExtractTap
from ..core import (
    find_new_bundle_path,
    SaveOptions,
    SpineOptions,
    process_mod_update,
    process_asset_packing,
    process_asset_extraction,
    extract_core_filename,
)
from ..utils import get_environment_info, CRCUtils, get_BA_path, get_search_resource_dirs, parse_hex_bytes

def setup_cli_logger():
    """配置一个简单的日志记录器，将日志输出到控制台。"""
    log = logging.getLogger('cli')
    if not log.handlers:
        log.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        log.addHandler(handler)

    # 模拟GUI Logger的接口
    class CLILogger:
        def log(self, message):
            log.info(message)

    return CLILogger()


def handle_update(args: UpdateTap, logger) -> None:
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


def handle_asset_packing(args: PackTap, logger) -> None:
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


def handle_crc(args: CrcTap, logger) -> None:
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
    if not original_path:
        logger.log("❌ Error: For CRC fix, must provide '--original' or use '--resource-dir' for auto-search.")
        return

    try:
        if CRCUtils.check_crc_match(original_path, modified_path):
            logger.log("⚠ CRC values already match, no fix needed.")
            return

        logger.log("CRC mismatch. Starting CRC fix...")

        if not args.no_backup:
            backup_path = modified_path.with_suffix(modified_path.suffix + '.bak')
            shutil.copy2(modified_path, backup_path)
            logger.log(f"  > Backup file created: {backup_path.name}")

        success = CRCUtils.manipulate_crc(original_path, modified_path, parse_hex_bytes(args.extra_bytes))

        if success:
            logger.log("✅ CRC Fix Successful! The modified file has been updated.")
        else:
            logger.log("❌ CRC Fix Failed.")

    except Exception as e:
        logger.log(f"❌ Error during CRC fix process: {e}")


def handle_env(args: EnvTap, logger) -> None:
    """处理 'env' 命令，打印环境信息。"""
    logger.log(get_environment_info(ignore_tk=True))


def handle_extract(args: ExtractTap, logger) -> None:
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
        subdir_name = extract_core_filename(valid_bundles[0].stem)

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
