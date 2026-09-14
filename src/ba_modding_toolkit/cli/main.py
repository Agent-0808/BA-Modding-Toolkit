# cli/main.py - CLI 主入口
from .taps import MainTap
from ..i18n import i18n_manager
from .handlers import (
    setup_cli_logger,
    handle_update,
    handle_asset_packing,
    handle_crc,
    handle_parse,
    handle_env,
    handle_extract,
    handle_batch_update,
    handle_report,
    handle_batch_preview,
    handle_backup,
)

# --- 命令映射 ---

COMMAND_HANDLERS = {
    'update': handle_update,
    'batch-update': handle_batch_update,
    'pack': handle_asset_packing,
    'crc': handle_crc,
    'parse': handle_parse,
    'env': handle_env,
    'extract': handle_extract,
    'report': handle_report,
    'batch-preview': handle_batch_preview,
    'backup': handle_backup,
}

def _resolve_language(lang: str) -> str:
    """大小写不敏感地匹配可用语言代码（如 "en-us" -> "en-US"），未匹配则原样返回。"""
    normalized = lang.strip().replace('_', '-')
    for code in i18n_manager.get_available_languages():
        if code.lower() == normalized.lower():
            return code
    return normalized

def main() -> None:
    """主函数，用于解析命令行参数并分派任务。"""
    args = MainTap().parse_args()

    # 显式指定语言时覆盖默认语言（需在任何本地化输出之前生效）
    if args.lang:
        i18n_manager.set_language(_resolve_language(args.lang))

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