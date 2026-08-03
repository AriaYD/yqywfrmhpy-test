"""B1 Capacity Violation / B2 Protected Block Violation 的契约层不变式。

S2（A5 的 `LoopAgent`）要让这两条成为**循环不变式**而非期望值。
循环不变式需要一个可判定的谓词——就是这里的这些 validator：
超载不标警告、blocking 冲突还 approved，都在构造对象时就失败。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CapacitySnapshot,
    ProposedSlot,
    ScheduleConflict,
    ScheduleProposal,
)
from campuspath_contracts.common import TimeRange
from campuspath_contracts.pathway import CapacityBudget

from conftest import NOW


def _snapshot(**kw) -> CapacitySnapshot:
    base = dict(
        snapshot_id="CS-1",
        student_id="S-001",
        period_start=date(2026, 7, 27),
        period_end=date(2026, 8, 2),
        fixed_load_hours=28.0,
        protected_time_hours=10.0,
        transition_hours=4.0,
        recovery_buffer_hours=3.0,
        existing_flexible_hours=2.0,
        usable_free_hours=30.0,
        discretionary_capacity_hours=11.0,
        planned_load_hours=8.0,
        buffer_ratio=0.27,
        overload_signal=False,
    )
    base.update(kw)
    return CapacitySnapshot(**base)


def test_capacity_formula_must_hold():
    """已知会失败的样例：各字段各填各的，公式对不上。"""
    with pytest.raises(ValidationError) as excinfo:
        _snapshot(discretionary_capacity_hours=25.0)
    assert "§16.6" in str(excinfo.value)


def test_valid_snapshot_passes():
    assert _snapshot().discretionary_capacity_hours == 11.0


def test_overload_must_be_signalled():
    """B1：计划超过可支配容量却没置 overload_signal。"""
    with pytest.raises(ValidationError) as excinfo:
        _snapshot(planned_load_hours=15.0)
    assert "B1" in str(excinfo.value)


def test_overload_with_signal_is_allowed():
    """超载本身不违规——**静默**超载才违规。"""
    snapshot = _snapshot(planned_load_hours=15.0, overload_signal=True)
    assert snapshot.overload_signal is True


def test_negative_discretionary_capacity_is_representable():
    """已经超载的学生必须能被如实表达，不能被 ge=0 夹成 0。

    容量为负时，即使这周什么都没安排也算超载——固定负担已经吃掉了全部时间。
    因此 ``overload_signal`` 必须为 True，否则被 B1 的 validator 拦下。
    """
    snapshot = _snapshot(
        usable_free_hours=15.0,
        protected_time_hours=10.0,
        transition_hours=4.0,
        recovery_buffer_hours=3.0,
        existing_flexible_hours=2.0,
        discretionary_capacity_hours=-4.0,
        planned_load_hours=0.0,
        buffer_ratio=-1.0,
        overload_signal=True,
    )
    assert snapshot.discretionary_capacity_hours < 0


def test_negative_capacity_without_signal_is_rejected():
    """容量为负却报告"一切正常"，正是 B1 要抓的静默超载。"""
    with pytest.raises(ValidationError):
        _snapshot(
            usable_free_hours=15.0,
            protected_time_hours=10.0,
            transition_hours=4.0,
            recovery_buffer_hours=3.0,
            existing_flexible_hours=2.0,
            discretionary_capacity_hours=-4.0,
            planned_load_hours=0.0,
            buffer_ratio=-1.0,
            overload_signal=False,
        )


# --------------------------------------------------------------------------
# CapacityBudget
# --------------------------------------------------------------------------


def test_budget_rejects_silent_overload():
    with pytest.raises(ValidationError) as excinfo:
        CapacityBudget(
            period_start=date(2026, 7, 27),
            period_end=date(2026, 8, 2),
            discretionary_capacity_hours=11.0,
            planned_hours=10.0,
            reserved_buffer_hours=3.0,
        )
    assert "B1" in str(excinfo.value)


def test_budget_with_explicit_warning_is_allowed():
    budget = CapacityBudget(
        period_start=date(2026, 7, 27),
        period_end=date(2026, 8, 2),
        discretionary_capacity_hours=11.0,
        planned_hours=10.0,
        reserved_buffer_hours=3.0,
        explicit_overload_warning=True,
    )
    assert budget.explicit_overload_warning


def test_budget_respects_the_buffer():
    """缓冲是容量的一部分，不是"可以被计划吃掉的余量"（Spec §16.8）。"""
    ok = CapacityBudget(
        period_start=date(2026, 7, 27),
        period_end=date(2026, 8, 2),
        discretionary_capacity_hours=11.0,
        planned_hours=8.0,
        reserved_buffer_hours=3.0,
    )
    assert ok.planned_hours + ok.reserved_buffer_hours == ok.discretionary_capacity_hours


# --------------------------------------------------------------------------
# B2：保护区块
# --------------------------------------------------------------------------


def _slot_with(conflict_type: str, blocking: bool) -> ProposedSlot:
    return ProposedSlot(
        plan_item_id="PI-1",
        span=TimeRange(start=NOW, end=NOW + timedelta(hours=2)),
        conflicts=(ScheduleConflict(conflict_type=conflict_type, blocking=blocking),),
    )


def test_approved_proposal_cannot_contain_blocking_conflict():
    """已知会失败的样例：与保护区块相交却被标成 approved。"""
    with pytest.raises(ValidationError) as excinfo:
        ScheduleProposal(
            proposal_id="SP-1",
            student_id="S-001",
            proposed_slots=(_slot_with("protected_block", blocking=True),),
            student_decision="approved",
        )
    assert "B1/B2" in str(excinfo.value)


def test_pending_proposal_may_surface_conflicts():
    """预览阶段必须能展示冲突——否则学生看不到为什么不能这么排。"""
    proposal = ScheduleProposal(
        proposal_id="SP-2",
        student_id="S-001",
        proposed_slots=(_slot_with("protected_block", blocking=True),),
        student_decision="pending",
    )
    assert proposal.proposed_slots[0].conflicts[0].blocking is True


def test_non_blocking_conflict_can_be_approved():
    proposal = ScheduleProposal(
        proposal_id="SP-3",
        student_id="S-001",
        proposed_slots=(_slot_with("busy_overlap", blocking=False),),
        student_decision="approved",
    )
    assert proposal.student_decision == "approved"


def test_protected_block_is_a_first_class_availability_type():
    """睡眠、吃饭、通勤不是"空档"（Spec §16.8）。"""
    block = AvailabilityBlock(
        block_id="AB-1",
        student_id="S-001",
        span=TimeRange(start=NOW, end=NOW + timedelta(hours=8)),
        type=AvailabilityType.PROTECTED,
        source=BlockSource.STUDENT_DEFINED,
        privacy_level="student_defined",
    )
    assert block.type is AvailabilityType.PROTECTED
    assert AvailabilityType.PROTECTED is not AvailabilityType.FREE


def test_time_range_rejects_inverted_span():
    with pytest.raises(ValidationError):
        TimeRange(start=NOW, end=NOW - timedelta(hours=1))
