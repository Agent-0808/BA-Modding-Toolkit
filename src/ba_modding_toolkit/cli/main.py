# cli/main.py
import sys
from pathlib import Path
import logging
import shutil
import argparse
from typing import Literal

from tap import Tap

# 从 core 模块导入核心函数和类
from ..core import (
    find_new_bundle_path,
    SaveOptions,
    SpineOptions,
    process_mod_update,
    process_asset_packing
)
# 从 utils 模块导入工具函数
from ..utils import get_environment_info, CRCUtils, get_BA_path, get_search_resource_dirs


# --- 日志设置 ---
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


# --- Tap 参数类定义 ---
class BaseTap(Tap):
    """基础Tap类，提供共享配置。"""

    def configure(self) -> None:
        self.description = "BA Modding Toolkit - Command Line Interface."
        self.formatter_class = argparse.RawTextHelpFormatter
        self._underscores_to_dashes = True
class UpdateTap(Tap):
    """Update命令的参数解析器 - 用于更新或移植Mod。"""

    # 基本参数
    old: str  # Path to the old Mod bundle file.
    output_dir: str = './output/'  # Directory to save the generated Mod file (Default: ./output/).

    # 目标文件定位参数
    target: str | None = None  # Path to the new game resource bundle file (Overrides --resource-dir if provided).
    resource_dir: str | None = None  # Path to the game resource directory, used to automatically find the matching new bundle file.

    # 资源与保存参数
    no_crc: bool = False  # Disable CRC fix function.
    padding: bool = False  # Add padding.
    asset_types: list[str] = ['Texture2D', 'TextAsset', 'Mesh']  # List of asset types to replace.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method for Bundle files.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: str | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version (e.g., "4.2.33").

    def configure(self) -> None:
        self.description = '''Update or port a Mod, migrating assets from an old Mod to a specific Bundle.

Examples:
  # Automatically search for new file and update
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --resource-dir "C:\\path\\to\\GameData\\Windows"

  # Manually specify new file and update
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --target "C:\\path\\to\\new_game_file.bundle" --output-dir "C:\\path\\to\\output"

  # Enable Spine skeleton conversion
  python maincli.py update --old "old.bundle" --target "new.bundle" --output-dir "output" --enable-spine-conversion --spine-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.33"
'''
        self.formatter_class = argparse.RawTextHelpFormatter
        self._underscores_to_dashes = True
        self.add_argument('--asset-types', nargs='+', choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'])
class PackTap(Tap):
    """Pack命令的参数解析器 - 用于资源打包。"""

    # 基本参数
    bundle: str  # Path to the target bundle file to modify.
    folder: str  # Path to the folder containing asset files.
    output_dir: str = './output/'  # Directory to save the modified bundle file.

    # 保存参数
    no_crc: bool = False  # Disable CRC fix function.
    compression: Literal['lzma', 'lz4', 'original', 'none'] = 'lzma'  # Compression method for Bundle files.

    # Spine转换参数
    enable_spine_conversion: bool = False  # Enable Spine skeleton conversion.
    spine_converter_path: str | None = None  # Full path to SpineSkeletonDataConverter.exe.
    target_spine_version: str = '4.2.33'  # Target Spine version.

    def configure(self) -> None:
        self.description = '''Pack contents from an asset folder into a target bundle file.

Example:
  python maincli.py pack --bundle "C:\\path\\to\\target.bundle" --folder "C:\\path\\to\\assets" --output-dir "C:\\path\\to\\output"
'''
        self.formatter_class = argparse.RawTextHelpFormatter
        self._underscores_to_dashes = True

class CrcTap(Tap):
    """CRC命令的参数解析器 - 用于CRC修正工具。"""

    # 基本参数
    modified: str  # Path to the modified file (to be fixed or calculated).

    # 原始文件定位参数
    original: str | None = None  # Path to the original file (provides target CRC value).
    resource_dir: str | None = None  # Path to the game resource directory for auto-search.

    # 操作选项
    check_only: bool = False  # Only calculate and compare CRC, do not modify any files.
    no_backup: bool = False  # Do not create a backup (.bak) before fixing the file.

    def configure(self) -> None:
        self.description = '''Tool to fix file CRC32 checksum or calculate/compare CRC32 values.

Examples:
  # Fix CRC of my_mod.bundle to match original.bundle (Manual)
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle"

  # Automatically search original file in game directory and fix CRC
  python maincli.py crc --modified "my_mod.bundle" --resource-dir "C:\\path\\to\\game_data"

  # Check if CRC matches only, do not modify file
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle" --check-only

  # Calculate CRC for a single file
  python maincli.py crc --modified "my_mod.bundle" --check-only
'''
        self.formatter_class = argparse.RawTextHelpFormatter
        self._underscores_to_dashes = True

class EnvTap(Tap):
    """Env命令的参数解析器 - 用于显示环境信息。"""

    def configure(self) -> None:
        self.description = 'Display system information and library versions of the current environment.'

class MainTap(BaseTap):
    """主Tap类，包含所有子命令。"""

    def configure(self) -> None:
        super().configure()
        self.add_subparsers(dest='command', help='Available commands')
        self.add_subparser('update', UpdateTap, help='Update or port a Mod, migrating assets from an old Mod to a specific Bundle.')
        self.add_subparser('pack', PackTap, help='Pack contents from an asset folder into a target bundle file.')
        self.add_subparser('crc', CrcTap, help='Tool to fix file CRC32 checksum or calculate/compare CRC32 values.')
        self.add_subparser('env', EnvTap, help='Display system information and library versions.')

# --- 命令处理函数 ---

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
        enable_padding=args.padding,
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
        enable_padding=False,
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
            logger.log(f"❌ Error: Manually specified original file '{original_path}' does not exist.")
            return
        logger.log(f"Manually specified original file: {original_path.name}")
    elif resource_dir:
        logger.log(f"No original file provided, searching automatically in '{resource_dir}'...")
        game_dir = Path(resource_dir)
        if not game_dir.is_dir():
            logger.log(f"❌ Error: Game resource directory '{game_dir}' does not exist or is not a directory.")
            return

        # 使用与 update 命令相同的查找函数
        found_paths, message = find_new_bundle_path(modified_path, get_search_resource_dirs(game_dir), logger.log)
        if not found_paths:
            logger.log(f"❌ Auto-search failed: {message}")
            return
        original_path = found_paths[0]

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

        success = CRCUtils.manipulate_crc(original_path, modified_path)

        if success:
            logger.log("✅ CRC Fix Successful! The modified file has been updated.")
        else:
            logger.log("❌ CRC Fix Failed.")

    except Exception as e:
        logger.log(f"❌ Error during CRC fix process: {e}")


def handle_env(args: EnvTap, logger) -> None:
    """处理 'env' 命令，打印环境信息。"""
    logger.log(get_environment_info(ignore_tk=True))


# --- 命令映射 ---

COMMAND_HANDLERS = {
    'update': handle_update,
    'pack': handle_asset_packing,
    'crc': handle_crc,
    'env': handle_env,
}

def main() -> None:
    """主函数，用于解析命令行参数并分派任务。"""
    args = MainTap().parse_args()

    # 初始化日志记录器
    logger = setup_cli_logger()

    # 根据子命令调用对应的处理函数
    # Tap使用 dest 参数指定的属性名存储子命令名称
    command = getattr(args, 'command', None)
    if command in COMMAND_HANDLERS:
        COMMAND_HANDLERS[command](args, logger)
    else:
        # 如果没有提供子命令，显示帮助信息
        MainTap().print_help()

if __name__ == "__main__":
    main()