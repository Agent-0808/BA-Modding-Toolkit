# utils/common.py
"""通用小件：日志占位、类型别名、子进程标志、装饰器"""

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from typing import Callable, ParamSpec, TypeVar


# Windows 下隐藏子进程的控制台窗口（避免Nuitka打包后弹出terminal）
CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def no_log(message):
    """A dummy logger that does nothing."""
    pass


LogFunc = Callable[[str], None]

ProgressCallback = Callable[[int, int, str], None]


def is_safe_relative_name(name: str) -> bool:
    """Whether a name read from an untrusted file stays below a folder when joined to it, on every platform.

    Refuses absolute paths, drive and stream prefixes and parent references, including the segments of dots and
    spaces that Windows normalises into them."""
    if "\0" in name or ":" in name:
        return False
    return all(part.rstrip(". ") for part in name.replace("\\", "/").split("/"))


def is_safe_file_name(name: str) -> bool:
    """``is_safe_relative_name`` for a single file name, without folders."""
    return "/" not in name and "\\" not in name and is_safe_relative_name(name)


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

_T = TypeVar("_T")
_R2 = TypeVar("_R2")


def run_batch(
    tasks: list[_T],
    worker: Callable[[_T], _R2],
    collect: Callable[[_T, _R2 | None, Exception | None], None],
    name_of: Callable[[_T], str],
    progress_callback: ProgressCallback | None = None,
    max_workers: int = 1,
) -> None:
    """通用批量执行模板：统一"串行 for 循环 / 线程池 + as_completed"调度骨架。

    - 串行（max_workers <= 1）：顺序执行，进度回调在任务处理前调用
    - 并行：ThreadPoolExecutor 提交全部任务，as_completed 收集；
      collect 在锁内调用（保证聚合线程安全），进度回调在完成后锁外调用
    - worker 抛异常不中断批次，以 collect(task, None, exc) 交给调用方记录失败

    Args:
        tasks: 任务列表
        worker: 执行单个任务的函数
        collect: 结果聚合函数，参数为 (任务, worker 返回值或 None, 异常或 None)；
                 串行路径无锁调用，并行路径在锁内调用
        name_of: 从任务提取展示名（用于进度回调第三个参数）
        progress_callback: 进度回调，接收 (已完成数, 总数, 任务名)
        max_workers: 并行线程数，<=1 时串行执行
    """
    total = len(tasks)

    def report(completed: int, name: str) -> None:
        if progress_callback:
            progress_callback(completed, total, name)

    if max_workers <= 1:
        # 串行处理：进度回调在处理前调用
        for i, task in enumerate(tasks, 1):
            name = name_of(task)
            report(i, name)
            try:
                result = worker(task)
            except Exception as e:
                collect(task, None, e)
            else:
                collect(task, result, None)
        return

    # 并行处理：计数与聚合只在主循环（本线程）中进行，collect 外部加锁统一保护
    lock = threading.Lock()
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(worker, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            name = name_of(task)
            try:
                result = future.result()
            except Exception as e:
                exc: Exception | None = e
                result = None
            else:
                exc = None
            with lock:
                completed += 1
                collect(task, result, exc)
            report(completed, name)


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
