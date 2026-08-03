"""H5：**用已知会失败的样例验证这份报告真的会红。**

13/13 全绿是这个项目最容易自欺的一张表。一个 `return PASS` 的检查器
产出的报告和真检查器一模一样，而且永远不会有人发现——除非有人专门
去证明它会失败。

这里做三件事：

1. 未注册的指标必须判 ``NOT_MEASURED`` **并计入失败**；
2. 抛异常的检查器必须判 FAIL，且**不能让整轮评测消失**；
3. 退出码要分级：BLOCKER 挂 → 非零，只有 TARGET 未达标 → 0。
"""

from __future__ import annotations

import pytest

from campuspath_eval import harness
from campuspath_eval.harness import (
    BLOCKERS,
    Result,
    Severity,
    TARGETS,
    Verdict,
    exit_code,
    run_all,
)


@pytest.fixture
def empty_registry(monkeypatch):
    """清空注册表，模拟"一个检查器都没写"。"""
    monkeypatch.setattr(harness, "_REGISTRY", {})


def test_unregistered_metrics_are_not_silently_dropped(empty_registry):
    results = run_all()
    assert len(results) == len(BLOCKERS) + len(TARGETS), (
        "指标数量必须等于声明数量——少一项就是报告里有看不见的空白"
    )
    assert all(r.verdict is Verdict.NOT_MEASURED for r in results)


def test_not_measured_counts_as_failure(empty_registry):
    """⬜ **不是** ✅。把没测的东西显示成通过，是这份报告最危险的失败模式。"""
    results = run_all()
    assert not any(r.ok for r in results)
    assert exit_code(results) != 0


def test_a_throwing_check_fails_that_metric_only(monkeypatch):
    """一个检查器炸掉，只该让那一项变红，不该让整轮评测消失。"""

    def boom() -> Result:
        raise RuntimeError("检查器内部错误")

    monkeypatch.setattr(harness, "_REGISTRY", {"B1": boom})
    results = run_all()

    b1 = next(r for r in results if r.metric_id == "B1")
    assert b1.verdict is Verdict.FAIL
    assert "RuntimeError" in b1.detail
    assert b1.failures, "失败样例里必须留下 traceback，否则无法复现"
    assert len(results) == len(BLOCKERS) + len(TARGETS)


def test_exit_code_is_graded(monkeypatch):
    """D6.6：BLOCKER 挂 → 非零；只有 TARGET 未达标 → 0。"""
    def passing(metric_id: str, severity: Severity):
        def fn() -> Result:
            return Result(metric_id=metric_id, name="x", severity=severity,
                          verdict=Verdict.PASS)
        return fn

    def failing(metric_id: str, severity: Severity):
        def fn() -> Result:
            return Result(metric_id=metric_id, name="x", severity=severity,
                          verdict=Verdict.FAIL)
        return fn

    registry = {mid: passing(mid, Severity.BLOCKER) for mid in BLOCKERS}
    registry |= {mid: passing(mid, Severity.TARGET) for mid in TARGETS}

    monkeypatch.setattr(harness, "_REGISTRY", dict(registry))
    assert exit_code(run_all()) == 0

    # 只有 TARGET 挂：退出 0，但报告要标红（由 report.md 的 ❌ 体现）
    registry["T1"] = failing("T1", Severity.TARGET)
    monkeypatch.setattr(harness, "_REGISTRY", dict(registry))
    only_target = run_all()
    assert exit_code(only_target) == 0
    assert not next(r for r in only_target if r.metric_id == "T1").ok

    # BLOCKER 挂：必须非零
    registry["B1"] = failing("B1", Severity.BLOCKER)
    monkeypatch.setattr(harness, "_REGISTRY", dict(registry))
    assert exit_code(run_all()) != 0


def test_every_declared_metric_has_an_id_shaped_like_the_tables():
    """B1–B13 与 T1–T12 一个不少。数量写死是有意的：
    Plan D6 说的是 13 + 12，改数量等于改验收合同。"""
    assert len(BLOCKERS) == 13
    assert len(TARGETS) == 12
    assert sorted(BLOCKERS, key=lambda k: int(k[1:])) == [f"B{i}" for i in range(1, 14)]
    assert sorted(TARGETS, key=lambda k: int(k[1:])) == [f"T{i}" for i in range(1, 13)]
