# maincli.py
import argparse
import sys
from pathlib import Path
import logging
import shutil
from utils import get_environment_info

# 将项目根目录添加到 sys.path，以便可以导入 processing 和 utils
sys.path.append(str(Path(__file__).parent.absolute()))

try:
    import processing
    from utils import CRCUtils
except ImportError as e:
    print(f"Error: Unable to import necessary modules: {e}")
    print("Please ensure 'processing.py' and 'utils.py' are in the same directory as this script.\n")

    # 打印环境信息，帮助用户调试
    print(get_environment_info())

    sys.exit(1)

# --- 日志设置 ---
# 创建一个简单的控制台日志记录器，代替GUI中的Logger
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

# --- 命令处理函数 ---

# ====== Mod Updating ======

def handle_update(args: argparse.Namespace, logger) -> None:
    """处理 'update' 命令的逻辑。"""
    logger.log("--- Start Mod Update ---")

    old_mod_path = Path(args.old)
    output_dir = Path(args.output_dir)
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    new_bundle_path: Path | None = None
    if args.target:
        new_bundle_path = Path(args.target)
    elif args.resource_dir:
        logger.log(f"No target bundle provided, searching automatically in '{args.resource_dir}'...")
        resource_dir = Path(args.resource_dir)
        if not resource_dir.is_dir():
            logger.log(f"❌ Error: Game resource directory '{resource_dir}' does not exist or is not a directory.")
            return
        
        found_path, message = processing.find_new_bundle_path(old_mod_path, resource_dir, logger.log)
        if not found_path:
            logger.log(f"❌ Auto-search failed: {message}")
            return
        new_bundle_path = found_path
    
    if not new_bundle_path:
        logger.log("❌ Error: Must provide '--target' or '--resource-dir' to determine the target resource file.")
        return

    asset_types = set(args.asset_types)
    logger.log(f"Specified asset replacement types: {', '.join(asset_types)}")

    save_options = processing.SaveOptions(
        perform_crc=not args.no_crc,
        enable_padding=args.padding,
        compression=args.compression
    )
    
    spine_options = processing.SpineOptions(
        enabled=args.enable_spine_conversion or False,
        converter_path=Path(args.spine_converter_path) if args.spine_converter_path else None,
        target_version=args.target_spine_version or None,
    )

    # 调用核心处理函数
    success, message = processing.process_mod_update(
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

def setup_update_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'update' 命令配置参数解析器。"""
    update_parser = subparsers.add_parser(
        'update', 
        help='Update or port a Mod, migrating assets from an old Mod to a specific Bundle.',
        formatter_class=argparse.RawTextHelpFormatter,
        description='''
Examples:
  # Automatically search for new file and update
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --resource-dir "C:\\path\\to\\GameData\\Windows"

  # Manually specify new file and update
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --target "C:\\path\\to\\new_game_file.bundle" --output-dir "C:\\path\\to\\output"

  # Enable Spine skeleton conversion
  python maincli.py update --old "old.bundle" --target "new.bundle" --output-dir "output" \
--enable-spine-conversion --spine-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.33"
'''
    )
    # --- 基本参数 ---
    update_parser.add_argument('--old', required=True, help='Path to the old Mod bundle file.')
    update_parser.add_argument('--output-dir', default='./output/', help='Directory to save the generated Mod file (Default: ./output/).')
    
    # --- 目标文件定位参数 ---
    target_group = update_parser.add_argument_group('Target Bundle Options')
    target_group.add_argument('--target', help='Path to the new game resource bundle file (Overrides --resource-dir if provided).')
    target_group.add_argument('--resource-dir', help='Path to the game resource directory, used to automatically find the matching new bundle file.')

    # --- 资源与保存参数 ---
    saving_group = update_parser.add_argument_group('Asset and Saving Options')
    saving_group.add_argument('--no-crc', action='store_true', help='Disable CRC fix function.')
    saving_group.add_argument('--padding', action='store_true', help='Add padding (private goods).')
    saving_group.add_argument(
        '--asset-types', 
        nargs='+', 
        default=['Texture2D', 'TextAsset', 'Mesh'], 
        choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'],
        help='List of asset types to replace. Options: Texture2D, TextAsset, Mesh, ALL. (Default: %(default)s)'
    )
    saving_group.add_argument(
        '--compression', 
        default='lzma', 
        choices=['lzma', 'lz4', 'original', 'none'],
        help='Compression method for Bundle files (Default: lzma). Options: lzma, lz4, original (keep original), none (no compression).'
    )

    # --- Spine 转换参数 ---
    spine_group = update_parser.add_argument_group('Spine Conversion Options')
    spine_group.add_argument('--enable-spine-conversion', action='store_true', help='Enable Spine skeleton conversion.')
    spine_group.add_argument('--spine-converter-path', help='Full path to SpineSkeletonDataConverter.exe.')
    spine_group.add_argument('--target-spine-version', default='4.2.33', help='Target Spine version (e.g., "4.2.33"). (Default: %(default)s)')

    update_parser.set_defaults(func=handle_update)

# ====== Asset Packer ======

def handle_asset_packing(args: argparse.Namespace, logger) -> None:
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
    save_options = processing.SaveOptions(
        perform_crc=not args.no_crc,
        enable_padding=False,
        compression=args.compression
    )

    # 调用核心处理函数
    success, message = processing.process_asset_packing(
        target_bundle_path=bundle_path,
        asset_folder=asset_folder,
        output_dir=output_dir,
        save_options=save_options,
        spine_options=None,
        log=logger.log
    )

    logger.log("\n" + "="*50)
    if success:
        logger.log(f"✅ Operation Successful: {message}")
    else:
        logger.log(f"❌ Operation Failed: {message}")

def setup_asset_packer_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'pack' 命令配置参数解析器。"""
    pack_parser = subparsers.add_parser(
        'pack', 
        help='Pack contents from an asset folder into a target bundle file.',
        formatter_class=argparse.RawTextHelpFormatter,
        description='''
Example:
  python maincli.py pack --bundle "C:\\path\\to\\target.bundle" --folder "C:\\path\\to\\assets" --output-dir "C:\\path\\to\\output"
'''
    )
    pack_parser.add_argument('--bundle', required=True, help='Path to the target bundle file to modify.')
    pack_parser.add_argument('--folder', required=True, help='Path to the folder containing asset files. Filenames (without extension) must match asset names in the bundle.')
    pack_parser.add_argument('--output-dir', required=False, default='./output/', help='Directory to save the modified bundle file (Default: ./output/).')
    pack_parser.add_argument('--no-crc', action='store_true', help='Disable CRC fix function.')
    pack_parser.add_argument(
        '--compression', 
        default='lzma', 
        choices=['lzma', 'lz4', 'original', 'none'],
        help='Compression method for Bundle files (Default: lzma). Options: lzma, lz4, original (keep original), none (no compression).'
    )
    pack_parser.set_defaults(func=handle_asset_packing)

# ====== CRC Tool ======

def handle_crc(args: argparse.Namespace, logger) -> None:
    """处理 'crc' 命令的逻辑。"""
    logger.log("--- Start CRC Tool ---")

    modified_path = Path(args.modified)
    if not modified_path.is_file():
        logger.log(f"❌ Error: Modified file '{modified_path}' does not exist.")
        return

    # 确定原始文件路径：优先使用 --original，其次使用 --resource-dir 自动查找
    original_path = None
    if args.original:
        original_path = Path(args.original)
        if not original_path.is_file():
            logger.log(f"❌ Error: Manually specified original file '{original_path}' does not exist.")
            return
        logger.log(f"Manually specified original file: {original_path.name}")
    elif args.resource_dir:
        logger.log(f"No original file provided, searching automatically in '{args.resource_dir}'...")
        game_dir = Path(args.resource_dir)
        if not game_dir.is_dir():
            logger.log(f"❌ Error: Game resource directory '{game_dir}' does not exist or is not a directory.")
            return
        
        # 使用与 update 命令相同的查找函数
        found_path, message = processing.find_new_bundle_path(modified_path, game_dir, logger.log)
        if not found_path:
            logger.log(f"❌ Auto-search failed: {message}")
            return
        original_path = found_path
        # find_new_bundle_path 函数内部会打印成功找到的日志

    # --- 模式 1: 仅检查/计算 CRC ---
    if args.check_only:
        try:
            with open(modified_path, "rb") as f: modified_data = f.read()
            modified_crc_hex = f"{CRCUtils.compute_crc32(modified_data):08X}"
            logger.log(f"Modified File CRC32: {modified_crc_hex}  ({modified_path.name})")

            if original_path:
                with open(original_path, "rb") as f: original_data = f.read()
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

        success = CRCUtils.manipulate_crc(original_path, modified_path)
        
        if success:
            logger.log("✅ CRC Fix Successful! The modified file has been updated.")
        else:
            logger.log("❌ CRC Fix Failed.")

    except Exception as e:
        logger.log(f"❌ Error during CRC fix process: {e}")

def setup_crc_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'crc' 命令配置参数解析器。"""
    crc_parser = subparsers.add_parser(
        'crc',
        help='Tool to fix file CRC32 checksum or calculate/compare CRC32 values.',
        formatter_class=argparse.RawTextHelpFormatter,
        description='''
Examples:
  # Fix CRC of my_mod.bundle to match original.bundle (Manual)
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle"

  # Automatically search original file in game directory and fix CRC
  python maincli.py crc --modified "my_mod.bundle" --resource-dir "C:\\path\\to\\game_data"

  # Check if CRC matches only, do not modify file (can combine with --resource-dir)
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle" --check-only

  # Calculate CRC for a single file
  python maincli.py crc --modified "my_mod.bundle" --check-only
'''
    )
    crc_parser.add_argument('--modified', required=True, help='Path to the modified file (to be fixed or calculated).')
    crc_parser.add_argument('--original', help='Path to the original file (provides target CRC value). Overrides --resource-dir if provided.')
    crc_parser.add_argument('--resource-dir', help='Path to the game resource directory, used to automatically find the matching original bundle file.')
    crc_parser.add_argument('--check-only', action='store_true', help='Only calculate and compare CRC, do not modify any files.')
    crc_parser.add_argument('--no-backup', action='store_true', help='Do not create a backup (.bak) before fixing the file.')
    crc_parser.set_defaults(func=handle_crc)


# ====== Print Environment ======

def handle_env(args: argparse.Namespace, logger) -> None:
    """处理 'env' 命令，打印环境信息。"""
    logger.log(get_environment_info())

def setup_env_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'env' 命令配置参数解析器。"""
    env_parser = subparsers.add_parser(
        'env', 
        help='Display system information and library versions of the current environment.',
        formatter_class=argparse.RawTextHelpFormatter
    )
    env_parser.set_defaults(func=handle_env)

def main() -> None:
    """主函数，用于解析命令行参数并分派任务。"""
    parser = argparse.ArgumentParser(
        description="BA Modding Toolkit - Command Line Interface.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # 配置各个子命令的解析器
    setup_update_parser(subparsers)
    setup_asset_packer_parser(subparsers)
    setup_crc_parser(subparsers)
    setup_env_parser(subparsers)

    # ==============================================================

    args = parser.parse_args()
    
    # 初始化日志记录器
    logger = setup_cli_logger()

    if hasattr(args, 'func'):
        args.func(args, logger)
    else:
        # 在没有提供子命令时，argparse 默认会显示帮助信息并退出
        parser.print_help()

if __name__ == "__main__":
    main()