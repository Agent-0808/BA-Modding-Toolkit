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
    print(f"错误: 无法导入必要的模块: {e}")
    print("请确保 'processing.py' 和 'utils.py' 文件与此脚本位于同一目录中。\n")

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
    logger.log("--- 开始更新 Mod ---")

    old_mod_path = Path(args.old)
    output_dir = Path(args.output_dir)
    
    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    new_bundle_path: Path | None = None
    if args.target:
        new_bundle_path = Path(args.target)
    elif args.resource_dir:
        logger.log(f"未提供新版资源文件，将在 '{args.resource_dir}' 中自动搜索...")
        game_dir = Path(args.resource_dir)
        if not game_dir.is_dir():
            logger.log(f"❌ 错误: 游戏资源目录 '{game_dir}' 不存在或不是一个目录。")
            return
        
        found_path, message = processing.find_new_bundle_path(old_mod_path, game_dir, logger.log)
        if not found_path:
            logger.log(f"❌ 自动搜索失败: {message}")
            return
        new_bundle_path = found_path
    
    if not new_bundle_path:
        logger.log("❌ 错误: 必须提供 '--target' 或 '--resource-dir' 以确定目标资源文件。")
        return

    asset_types = set(args.asset_types)
    logger.log(f"指定的资源替换类型: {', '.join(asset_types)}")

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
        logger.log(f"✅ 操作成功: {message}")
    else:
        logger.log(f"❌ 操作失败: {message}")

def setup_update_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'update' 命令配置参数解析器。"""
    update_parser = subparsers.add_parser(
        'update', 
        help='更新或移植 Mod，将旧 Mod 的资源移植到指定的Bundle中。',
        formatter_class=argparse.RawTextHelpFormatter,
        description='''
示例:
  # 自动搜索新文件并更新
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --resource-dir "C:\\path\\to\\GameData\\Windows"

  # 手动指定新文件并更新
  python maincli.py update --old "C:\\path\\to\\old_mod.bundle" --target "C:\\path\\to\\new_game_file.bundle" --output-dir "C:\\path\\to\\output"

  # 启用Spine骨骼转换
  python maincli.py update --old "old.bundle" --target "new.bundle" --output-dir "output" \
--enable-spine-conversion --spine-converter-path "C:\\path\\to\\SpineSkeletonDataConverter.exe" --target-spine-version "4.2.33"
'''
    )
    # --- 基本参数 ---
    update_parser.add_argument('--old', required=True, help='旧版 Mod bundle 文件的路径。')
    update_parser.add_argument('--output-dir', default='./output/', help='保存生成的新 Mod 文件的目录 (默认: ./output/)。')
    
    # --- 目标文件定位参数 ---
    target_group = update_parser.add_argument_group('Target Bundle Options')
    target_group.add_argument('--target', help='新版游戏资源 bundle 文件的路径 (如果提供，则优先于 --resource-dir)。')
    target_group.add_argument('--resource-dir', help='游戏资源目录的路径，用于自动查找匹配的新版 bundle 文件。')

    # --- 资源与保存参数 ---
    saving_group = update_parser.add_argument_group('Asset and Saving Options')
    saving_group.add_argument('--no-crc', action='store_true', help='禁用 CRC 修正功能。')
    saving_group.add_argument('--padding', action='store_true', help='添加私货')
    saving_group.add_argument(
        '--asset-types', 
        nargs='+', 
        default=['Texture2D', 'TextAsset', 'Mesh'], 
        choices=['Texture2D', 'TextAsset', 'Mesh', 'ALL'],
        help='要替换的资源类型列表。可选: Texture2D, TextAsset, Mesh, ALL。(默认: %(default)s)'
    )
    saving_group.add_argument(
        '--compression', 
        default='lzma', 
        choices=['lzma', 'lz4', 'original', 'none'],
        help='Bundle 文件的压缩方式 (默认: lzma)。可选: lzma, lz4, original(保持原始), none(不压缩)。'
    )

    # --- Spine 转换参数 ---
    spine_group = update_parser.add_argument_group('Spine Conversion Options')
    spine_group.add_argument('--enable-spine-conversion', action='store_true', help='启用Spine骨骼转换功能。')
    spine_group.add_argument('--spine-converter-path', help='SpineSkeletonDataConverter.exe 的完整路径。')
    spine_group.add_argument('--target-spine-version', default='4.2.33', help='目标Spine版本 (例如 "4.2.33")。(默认: %(default)s)')

    update_parser.set_defaults(func=handle_update)

# ====== Asset Packer ======

def handle_asset_packing(args: argparse.Namespace, logger) -> None:
    """处理 'pack' 命令的逻辑。"""
    logger.log("--- 开始资源打包 ---")
    
    bundle_path = Path(args.bundle)
    asset_folder = Path(args.folder)
    output_dir = Path(args.output_dir)

    # 确保输出目录存在
    output_dir.mkdir(parents=True, exist_ok=True)

    if not bundle_path.is_file():
        logger.log(f"❌ 错误: Bundle 文件 '{bundle_path}' 不存在。")
        return
    if not asset_folder.is_dir():
        logger.log(f"❌ 错误: 资源文件夹 '{asset_folder}' 不存在。")
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
        logger.log(f"✅ 操作成功: {message}")
    else:
        logger.log(f"❌ 操作失败: {message}")

def setup_asset_packer_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'pack' 命令配置参数解析器。"""
    pack_parser = subparsers.add_parser(
        'pack', 
        help='将资源文件夹中的内容打包到目标 bundle 文件中。',
        formatter_class=argparse.RawTextHelpFormatter,
        description='''
示例:
  python maincli.py pack --bundle "C:\\path\\to\\target.bundle" --folder "C:\\path\\to\\assets" --output-dir "C:\\path\\to\\output"
'''
    )
    pack_parser.add_argument('--bundle', required=True, help='要修改的目标 bundle 文件路径。')
    pack_parser.add_argument('--folder', required=True, help='包含资源文件的文件夹路径。资源文件名 (不含扩展名) 需与 bundle 内资源名匹配。')
    pack_parser.add_argument('--output-dir', required=False, default='./output/', help='保存修改后 bundle 文件的目录 (默认: ./output/)。')
    pack_parser.add_argument('--no-crc', action='store_true', help='禁用 CRC 修正功能。')
    pack_parser.add_argument(
        '--compression', 
        default='lzma', 
        choices=['lzma', 'lz4', 'original', 'none'],
        help='Bundle 文件的压缩方式 (默认: lzma)。可选: lzma, lz4, original(保持原始), none(不压缩)。'
    )
    pack_parser.set_defaults(func=handle_asset_packing)

# ====== CRC Tool ======

def handle_crc(args: argparse.Namespace, logger) -> None:
    """处理 'crc' 命令的逻辑。"""
    logger.log("--- 开始 CRC 工具 ---")

    modified_path = Path(args.modified)
    if not modified_path.is_file():
        logger.log(f"❌ 错误: 修改后文件 '{modified_path}' 不存在。")
        return

    # 确定原始文件路径：优先使用 --original，其次使用 --resource-dir 自动查找
    original_path = None
    if args.original:
        original_path = Path(args.original)
        if not original_path.is_file():
            logger.log(f"❌ 错误: 手动指定的原始文件 '{original_path}' 不存在。")
            return
        logger.log(f"已手动指定原始文件: {original_path.name}")
    elif args.resource_dir:
        logger.log(f"未提供原始文件，将在 '{args.resource_dir}' 中自动搜索...")
        game_dir = Path(args.resource_dir)
        if not game_dir.is_dir():
            logger.log(f"❌ 错误: 游戏资源目录 '{game_dir}' 不存在或不是一个目录。")
            return
        
        # 使用与 update 命令相同的查找函数
        found_path, message = processing.find_new_bundle_path(modified_path, game_dir, logger.log)
        if not found_path:
            logger.log(f"❌ 自动搜索失败: {message}")
            return
        original_path = found_path
        # find_new_bundle_path 函数内部会打印成功找到的日志

    # --- 模式 1: 仅检查/计算 CRC ---
    if args.check_only:
        try:
            with open(modified_path, "rb") as f: modified_data = f.read()
            modified_crc_hex = f"{CRCUtils.compute_crc32(modified_data):08X}"
            logger.log(f"修改后文件 CRC32: {modified_crc_hex}  ({modified_path.name})")

            if original_path:
                with open(original_path, "rb") as f: original_data = f.read()
                original_crc_hex = f"{CRCUtils.compute_crc32(original_data):08X}"
                logger.log(f"原始文件 CRC32:   {original_crc_hex}  ({original_path.name})")
                if original_crc_hex == modified_crc_hex:
                    logger.log("✅ CRC值匹配: 是")
                else:
                    logger.log("❌ CRC值匹配: 否")
        except Exception as e:
            logger.log(f"❌ 计算CRC时发生错误: {e}")
        return

    # --- 模式 2: 修正 CRC ---
    if not original_path:
        logger.log("❌ 错误: 进行CRC修正时，必须提供 '--original' 原始文件或使用 '--resource-dir' 进行自动查找。")
        return

    try:
        if CRCUtils.check_crc_match(original_path, modified_path):
            logger.log("⚠ CRC值已匹配，无需修正。")
            return

        logger.log("CRC值不匹配，开始进行CRC修正...")
        
        if not args.no_backup:
            backup_path = modified_path.with_suffix(modified_path.suffix + '.bak')
            shutil.copy2(modified_path, backup_path)
            logger.log(f"  > 已创建备份文件: {backup_path.name}")

        success = CRCUtils.manipulate_crc(original_path, modified_path)
        
        if success:
            logger.log("✅ CRC修正成功！修改后的文件已更新。")
        else:
            logger.log("❌ CRC修正失败。")

    except Exception as e:
        logger.log(f"❌ CRC修正过程中发生错误: {e}")

def setup_crc_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'crc' 命令配置参数解析器。"""
    crc_parser = subparsers.add_parser(
        'crc',
        help='工具，用于修正文件的 CRC32 值或计算/比较 CRC32 值。',
        formatter_class=argparse.RawTextHelpFormatter,
        description='''
示例:
  # 修正 my_mod.bundle 的 CRC，使其与 original.bundle 匹配 (手动指定)
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle"

  # 自动在游戏目录中查找原始文件并修正 CRC
  python maincli.py crc --modified "my_mod.bundle" --resource-dir "C:\\path\\to\\game_data"

  # 仅检查 CRC 是否匹配，不修改文件 (可配合 --resource-dir 自动查找)
  python maincli.py crc --modified "my_mod.bundle" --original "original.bundle" --check-only

  # 计算单个文件的 CRC
  python maincli.py crc --modified "my_mod.bundle" --check-only
'''
    )
    crc_parser.add_argument('--modified', required=True, help='修改后的文件路径 (待修正或计算)。')
    crc_parser.add_argument('--original', help='原始文件路径 (用于提供目标 CRC 值)。如果提供，则优先于 --resource-dir。')
    crc_parser.add_argument('--resource-dir', help='游戏资源目录的路径，用于自动查找匹配的原始 bundle 文件。')
    crc_parser.add_argument('--check-only', action='store_true', help='仅计算并比较 CRC，不修改任何文件。')
    crc_parser.add_argument('--no-backup', action='store_true', help='在修正文件前不创建备份 (.bak)。')
    crc_parser.set_defaults(func=handle_crc)


# ====== Print Environment ======

def handle_env(args: argparse.Namespace, logger) -> None:
    """处理 'env' 命令，打印环境信息。"""
    logger.log(get_environment_info())

def setup_env_parser(subparsers: argparse._SubParsersAction) -> None:
    """为 'env' 命令配置参数解析器。"""
    env_parser = subparsers.add_parser(
        'env', 
        help='显示当前环境的系统信息和库版本。',
        formatter_class=argparse.RawTextHelpFormatter
    )
    env_parser.set_defaults(func=handle_env)

def main() -> None:
    """主函数，用于解析命令行参数并分派任务。"""
    parser = argparse.ArgumentParser(
        description="BA Modding Toolkit - Command Line Interface.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest='command', required=True, help='可用的命令')

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