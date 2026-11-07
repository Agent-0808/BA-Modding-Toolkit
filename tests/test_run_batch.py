# tests/test_run_batch.py
"""run_batch 批量执行模板的行为测试：调度、进度、异常降级"""

import pytest

from ba_modding_toolkit.utils import run_batch


def make_worker(fail_on: set[int]):
    """构造按任务编号失败的工作函数"""
    def worker(n: int) -> str:
        if n in fail_on:
            raise ValueError(f"boom-{n}")
        return f"ok-{n}"
    return worker


def run_case(max_workers: int, fail_on: set[int]) -> tuple[list[str], list[str], list[tuple]]:
    """执行一批任务，返回 (成功结果, 失败原因, 进度记录)"""
    results: list[str] = []
    failures: list[str] = []
    progress: list[tuple] = []

    def collect(task: int, result: str | None, exc: Exception | None) -> None:
        if exc is not None:
            failures.append(str(exc))
        else:
            results.append(result)

    run_batch(
        list(range(1, 6)),
        make_worker(fail_on),
        collect,
        name_of=str,
        progress_callback=lambda c, t, n: progress.append((c, t, n)),
        max_workers=max_workers,
    )
    return results, failures, progress


class TestRunBatch:
    @pytest.mark.parametrize("max_workers", [1, 3], ids=["serial", "parallel"])
    def test_all_success(self, max_workers: int):
        results, failures, progress = run_case(max_workers, set())
        assert sorted(results) == [f"ok-{i}" for i in range(1, 6)]
        assert failures == []
        # 每个任务恰好推进一次进度，最终到达 total
        assert sorted(c for c, _, _ in progress) == [1, 2, 3, 4, 5]
        assert progress[-1] == (5, 5, "5")

    @pytest.mark.parametrize("max_workers,fail_on", [
        (1, {3}),
        (3, {2, 5}),
    ], ids=["serial", "parallel"])
    def test_exception_does_not_abort_batch(self, max_workers: int, fail_on: set[int]):
        results, failures, progress = run_case(max_workers, fail_on)
        # 异常任务进入 failures，其余任务照常完成
        assert sorted(failures) == [f"boom-{i}" for i in sorted(fail_on)]
        assert sorted(results) == [f"ok-{i}" for i in range(1, 6) if i not in fail_on]
        # 全部 5 个任务都有进度记录
        assert len(progress) == 5

    def test_serial_progress_before_processing(self):
        """串行路径进度回调在处理前调用，按 1..total 顺序递增"""
        _, _, progress = run_case(1, set())
        assert [c for c, _, _ in progress] == [1, 2, 3, 4, 5]

    def test_empty_tasks(self):
        run_batch([], make_worker(set()), lambda *a: None, name_of=str, max_workers=4)

    def test_max_workers_zero_falls_back_to_serial(self):
        results, failures, _ = run_case(0, set())
        assert results == [f"ok-{i}" for i in range(1, 6)]
        assert failures == []