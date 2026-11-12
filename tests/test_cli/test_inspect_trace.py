# CLI 层测试：inspect/trace 能正常运行（输出契约由 core 层测试覆盖）

from typing import TYPE_CHECKING

from ba_modding_toolkit.cli.handlers import handle_inspect, handle_trace
from ba_modding_toolkit.cli.taps import InspectTap, TraceTap

if TYPE_CHECKING:
    from conftest import SampleCase


class LogCapture:
    """捕获 handler 输出的最小 Logger 替身（handler 仅调用 log）"""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def log(self, message: str) -> None:
        self.lines.append(message)


def test_inspect_runs(sample_case: "SampleCase") -> None:
    """对真实 bundle 运行 inspect 不抛异常且有输出"""
    logger = LogCapture()
    handle_inspect(InspectTap().parse_args([str(sample_case.bundle_paths[0])]), logger)
    assert logger.lines


def test_trace_runs(sample_case: "SampleCase") -> None:
    """对真实 bundle 运行 trace 不抛异常且有输出"""
    logger = LogCapture()
    handle_trace(TraceTap().parse_args([str(sample_case.bundle_paths[0])]), logger)
    assert logger.lines


def test_missing_input_terminates_gracefully() -> None:
    """输入文件不存在时不抛异常，正常返回"""
    logger = LogCapture()
    handle_inspect(InspectTap().parse_args(["nonexistent.bundle"]), logger)
    handle_trace(TraceTap().parse_args(["nonexistent.bundle"]), logger)
    assert logger.lines
