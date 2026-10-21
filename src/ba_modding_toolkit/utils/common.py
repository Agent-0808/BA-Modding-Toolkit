# utils/common.py
"""通用小件：日志占位、类型别名、子进程标志、装饰器"""

import subprocess
import sys
import time
from functools import wraps
from typing import Callable, ParamSpec, TypeVar


# Windows 下隐藏子进程的控制台窗口（避免Nuitka打包后弹出terminal）
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def no_log(message):
    """A dummy logger that does nothing."""
    pass


LogFunc = Callable[[str], None]

ProgressCallback = Callable[[int, int, str], None]


def parse_hex_bytes(hex_str: str | None) -> bytes | None:
    """将字符串转换为 bytes

    Args:
        hex_str: 如果以 0x 或 0X 开头，则按十六进制解析（如 "0x08080808"）
               否则按 ASCII 字符串直接编码

    Returns:
        如果输入为空或无效则返回 None，否则返回对应的 bytes
    """
    if not hex_str:
        return None
    try:
        # 如果以 0x 或 0X 开头，按十六进制解析
        if hex_str.startswith("0x") or hex_str.startswith("0X"):
            hex_str = hex_str[2:]
            # 验证是否为有效的十六进制字符串（必须为偶数长度）
            if len(hex_str) % 2 != 0:
                return None
            return bytes.fromhex(hex_str)
        # 否则按 ASCII 字符串直接编码
        return hex_str.encode("ascii")
    except (ValueError, UnicodeEncodeError):
        return None


_P = ParamSpec("_P")
_R = TypeVar("_R")

def timing(func: Callable[_P, _R]) -> Callable[_P, _R]:
    """函数运行时间统计装饰器，结果直接 print 输出"""
    @wraps(func)
    def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            print(f"[timing] {func.__qualname__}: {time.perf_counter() - start:.3f}s")
    return wrapper


def throttle_progress(callback: ProgressCallback, interval: float = 0.1) -> ProgressCallback:
    """为进度回调 (current, total, filename) 添加时间节流

    interval 秒内最多实际调用一次回调，最后一次（current >= total）必定调用，
    用于避免海量文件的逐条 GUI 更新。
    """
    last = 0.0

    def throttled(current: int, total: int, filename: str) -> None:
        nonlocal last
        now = time.perf_counter()
        if current >= total or now - last >= interval:
            last = now
            callback(current, total, filename)

    return throttled
