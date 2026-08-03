"""容量与保护区块的硬约束（Spec §16.8、B1、B2）。**零 LLM。**

这两条是 A5 内部 `LoopAgent`（S2）的循环不变式：生成计划 → 这里校验 →
违反就带着原因重生成。因此这里的函数必须给出**可被机器读懂的违规原因**，
而不只是 True/False——不然重生成时模型只知道"错了"，不知道错在哪。
"""

from __future__ import annotations

import dataclasses

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    CapacitySnapshot,
)
from campuspath_contracts.common import TimeRange


@dataclasses.dataclass(frozen=True)
class ProtectedBlockViolation:
    plan_item_id: str
    block_id: str
    overlap_minutes: float

    def describe(self) -> str:
        return (
            f"{self.plan_item_id} 与保护区块 {self.block_id} 重叠 "
            f"{self.overlap_minutes:.0f} 分钟"
        )


@dataclasses.dataclass(frozen=True)
class CapacityViolation:
    period_start: str
    planned_hours: float
    discretionary_hours: float

    @property
    def excess_hours(self) -> float:
        return round(self.planned_hours - self.discretionary_hours, 2)

    def describe(self) -> str:
        return (
            f"{self.period_start} 起的一周：计划 {self.planned_hours:.1f}h 超出可支配 "
            f"{self.discretionary_hours:.1f}h，超出 {self.excess_hours:.1f}h"
        )


def _overlap_minutes(a: TimeRange, b: TimeRange) -> float:
    start = max(a.start, b.start)
    end = min(a.end, b.end)
    if end <= start:
        return 0.0
    return (end - start).total_seconds() / 60.0


def find_protected_block_violations(
    proposed: dict[str, TimeRange],
    blocks: list[AvailabilityBlock],
) -> list[ProtectedBlockViolation]:
    """B2：排程结果与保护区块求交集，非空即违规。

    只看 ``PROTECTED``。``BUSY`` 冲突是可以协商的（学生可以翘一次会），
    保护区块不是——睡眠、用餐、通勤、恢复不是可压缩空档（Spec §16.8）。
    """
    protected = [b for b in blocks if b.type is AvailabilityType.PROTECTED]
    violations: list[ProtectedBlockViolation] = []
    for plan_item_id, span in sorted(proposed.items()):
        for block in protected:
            minutes = _overlap_minutes(span, block.span)
            if minutes > 0:
                violations.append(
                    ProtectedBlockViolation(plan_item_id, block.block_id, minutes)
                )
    return violations


def find_capacity_violations(
    snapshots: list[CapacitySnapshot],
    *,
    allow_warned_overload: bool = True,
) -> list[CapacityViolation]:
    """B1：未经显式警告的超载即违规。

    超载本身不违规——**静默**超载才违规（Spec §16.8：超载只能作为显式警告的
    备选，不能静默安排）。``allow_warned_overload=False`` 用于评测时收紧到
    "任何超载都算"，用来观察差距。
    """
    violations: list[CapacityViolation] = []
    for snapshot in snapshots:
        over = snapshot.planned_load_hours > snapshot.discretionary_capacity_hours
        if not over:
            continue
        if allow_warned_overload and snapshot.overload_signal:
            continue
        violations.append(
            CapacityViolation(
                period_start=snapshot.period_start.isoformat(),
                planned_hours=snapshot.planned_load_hours,
                discretionary_hours=snapshot.discretionary_capacity_hours,
            )
        )
    return violations


def buffer_below_floor(snapshot: CapacitySnapshot, min_buffer_ratio: float) -> bool:
    """缓冲低于学生自设下限。缓冲是容量的一部分，不是可被计划吃掉的余量。"""
    return snapshot.buffer_ratio < min_buffer_ratio
