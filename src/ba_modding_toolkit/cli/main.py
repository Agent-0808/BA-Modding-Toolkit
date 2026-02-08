# cli/main.py - CLI 主入口
from .taps import MainTap
from .handlers import (
    setup_cli_logger,
    handle_update,
    handle_asset_packing,
    handle_crc,
    handle_env,
    handle_extract,
)

# --- 命令映射 ---

COMMAND_HANDLERS = {
    'update': handle_update,
    'pack': handle_asset_packing,
    'crc': handle_crc,
    'env': handle_env,
    'extract': handle_extract,
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