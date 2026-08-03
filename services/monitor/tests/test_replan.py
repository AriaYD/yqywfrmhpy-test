"""Event Monitor & Replan：去抖与 AffectedScope（T5 的判据来源）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from campuspath_contracts.common import DateRange, LocalizedText
from campuspath_contracts.pathway import (
    Milestone,
    PathwayVersion,
    PlanItem,
    PlanItemKind,
    ReplanTriggerType,
)

from campuspath_monitor.replan import (
    DEBOUNCE_WINDOW,
    LOCAL_ONLY_TRIGGERS,
    ChangeEvent,
    build_trigger,
    compute_scope,
    debounce,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
TODAY = date(2026, 9, 15)
VID = "val_" + "a" * 32


def item(pid: str, subject: str, deps: tuple[str, ...] = (), kind=PlanItemKind.ACTION) -> PlanItem:
    return PlanItem(
        plan_item_id=pid, kind=kind, subject_id=subject,
        title=LocalizedText(zh_Hans=pid, en=pid),
        date_range=DateRange(start=TODAY, end=TODAY + timedelta(days=7)),
        dependencies=deps, validation_id=VID,
    )


def horizons(pw: PathwayVersion, *, long_term: tuple[str, ...] = ()) -> dict[str, str]:
    """每个计划项的时间尺度。

    ``compute_scope`` 现在**必须**拿到它：此前它可选且缺失时按 this_term 处理，
    调用方忘了传，"日历变化不推翻长期目标"这条保护就静默失效。
    """
    return {
        i.plan_item_id: ("long_term" if i.plan_item_id in long_term else "this_term")
        for i in pw.plan_items
    }


def pathway(*items: PlanItem, milestones=()) -> PathwayVersion:
    return PathwayVersion(
        pathway_id="PV-1", student_id="STU-A", version=3, created_at=NOW,
        trigger="initial", horizons=("this_term", "long_term"),
        plan_items=items, milestones=milestones,
    )


def event(trigger=ReplanTriggerType.CALENDAR_CHANGE, subject="OPP-1", at=NOW) -> ChangeEvent:
    return ChangeEvent(event_id="EV-1", student_id="STU-A", trigger_type=trigger,
                       subject_id=subject, detected_at=at)


# ── 去抖 ──────────────────────────────────────────────────────────────


def test_rapid_same_kind_events_collapse_to_one():
    events = [event(at=NOW + timedelta(seconds=i * 10)) for i in range(5)]
    assert len(debounce(events)) == 1


def test_debounce_keeps_the_latest_state():
    """学生连改三次日程，该重算的是最终状态。"""
    events = [
        event(subject="A", at=NOW),
        event(subject="B", at=NOW + timedelta(seconds=10)),
        event(subject="C", at=NOW + timedelta(seconds=20)),
    ]
    assert debounce(events)[0].subject_id == "C"


def test_events_outside_the_window_are_kept_separate():
    events = [event(at=NOW), event(at=NOW + DEBOUNCE_WINDOW + timedelta(seconds=1))]
    assert len(debounce(events)) == 2


def test_different_trigger_kinds_do_not_collapse():
    events = [
        event(ReplanTriggerType.CALENDAR_CHANGE, at=NOW),
        event(ReplanTriggerType.NEW_GRADE, at=NOW + timedelta(seconds=5)),
    ]
    assert len(debounce(events)) == 2


# ── AffectedScope ────────────────────────────────────────────────────


def test_direct_subject_is_affected():
    pw = pathway(item("PI-1", "OPP-1"))
    scope = compute_scope(event(subject="OPP-1"), pw, horizon_of=horizons(pw))
    assert scope.affected_plan_item_ids == ("PI-1",)


def test_unrelated_items_are_reported_as_unaffected():
    """T5 判的是"只改受影响路径"，没有 unaffected 就无从证伪。"""
    pw = pathway(item("PI-1", "OPP-1"), item("PI-2", "OPP-2"), item("PI-3", "COMP 3711"))
    scope = compute_scope(event(subject="OPP-1"), pw, horizon_of=horizons(pw))
    assert scope.affected_plan_item_ids == ("PI-1",)
    assert scope.unaffected_plan_item_ids == ("PI-2", "PI-3")


def test_downstream_dependencies_are_affected():
    pw = pathway(item("PI-1", "OPP-1"), item("PI-2", "OPP-2", deps=("PI-1",)),
                 item("PI-3", "OPP-3", deps=("PI-2",)), item("PI-4", "OPP-4"))
    scope = compute_scope(event(subject="OPP-1"), pw, horizon_of=horizons(pw))
    assert set(scope.affected_plan_item_ids) == {"PI-1", "PI-2", "PI-3"}
    assert scope.unaffected_plan_item_ids == ("PI-4",)


def test_affected_and_unaffected_never_overlap():
    pw = pathway(item("PI-1", "OPP-1"), item("PI-2", "OPP-2", deps=("PI-1",)))
    scope = compute_scope(event(subject="OPP-1"), pw, horizon_of=horizons(pw))
    assert not set(scope.affected_plan_item_ids) & set(scope.unaffected_plan_item_ids)


def test_calendar_change_does_not_touch_long_term_items():
    """Spec §16.9：日历变化只重排冲突项，不推翻无关长期目标。"""
    pw = pathway(item("PI-1", "OPP-1"), item("PI-2", "OPP-2", deps=("PI-1",)))
    scope = compute_scope(
        event(ReplanTriggerType.CALENDAR_CHANGE, subject="OPP-1"), pw,
        horizon_of=horizons(pw, long_term=("PI-2",)),
    )
    assert scope.affected_plan_item_ids == ("PI-1",)
    assert "PI-2" in scope.unaffected_plan_item_ids


def test_new_grade_may_touch_long_term_items():
    """成绩变化影响先修链，长期项该受影响就受影响——不是一刀切。"""
    pw = pathway(item("PI-1", "COMP 2011"), item("PI-2", "COMP 3711", deps=("PI-1",)))
    scope = compute_scope(
        event(ReplanTriggerType.NEW_GRADE, subject="COMP 2011"), pw,
        horizon_of=horizons(pw, long_term=("PI-2",)),
    )
    assert set(scope.affected_plan_item_ids) == {"PI-1", "PI-2"}


def test_local_only_trigger_set_matches_the_spec():
    assert ReplanTriggerType.CALENDAR_CHANGE in LOCAL_ONLY_TRIGGERS
    assert ReplanTriggerType.NEW_GRADE not in LOCAL_ONLY_TRIGGERS


def test_weekly_overload_touches_every_non_milestone_item():
    pw = pathway(item("PI-1", "A"), item("PI-2", "B"),
                 item("PI-3", "C", kind=PlanItemKind.MILESTONE))
    scope = compute_scope(
        event(ReplanTriggerType.WEEKLY_OVERLOAD, subject="week"), pw,
        horizon_of=horizons(pw),
    )
    assert set(scope.affected_plan_item_ids) == {"PI-1", "PI-2"}


def test_milestones_referencing_affected_items_are_listed():
    milestone = Milestone(
        milestone_id="MS-1", title=LocalizedText(zh_Hans="申请季", en="Application season"),
        plan_item_ids=("PI-1",),
    )
    pw = pathway(item("PI-1", "OPP-1"), item("PI-2", "OPP-2"), milestones=(milestone,))
    scope = compute_scope(event(subject="OPP-1"), pw, horizon_of=horizons(pw))
    assert scope.affected_milestone_ids == ("MS-1",)


def test_scope_carries_a_bilingual_rationale():
    pw = pathway(item("PI-1", "OPP-1"))
    scope = compute_scope(event(), pw, horizon_of=horizons(pw))
    assert scope.rationale.zh_Hans and scope.rationale.en


def test_trigger_records_the_old_version():
    pw = pathway(item("PI-1", "OPP-1"))
    trigger = build_trigger(event(), pw, compute_scope(event(), pw, horizon_of=horizons(pw)))
    assert trigger.old_plan_version == 3



# ── 以下来自 2026-07-29 的独立审查 ──


def test_debounce_does_not_starve_a_busy_student():
    """窗口若锚在"上一条被保留的事件"上，每次合并都重置计时。

    实测：每 80 秒改一次日程（窗口 90 秒）的学生，连续一小时只留下 1 条，
    也就是这一小时内一次都不会被重规划——去抖变成了饥饿。
    """
    from campuspath_monitor.replan import MAX_DEBOUNCE_DELAY

    events = [
        event(at=NOW + timedelta(seconds=80 * i)) for i in range(45)
    ]
    kept = debounce(events)
    assert len(kept) > 1, "连续一小时的编辑不该只重规划一次"
    span = events[-1].detected_at - events[0].detected_at
    assert len(kept) >= span // MAX_DEBOUNCE_DELAY


def test_debounce_still_collapses_a_short_burst():
    """封顶不能把正常的合并也拆开。"""
    events = [event(at=NOW + timedelta(seconds=10 * i)) for i in range(5)]
    assert len(debounce(events)) == 1


def test_local_only_trigger_requires_horizons():
    """调用方忘了传 horizon_of 时，此前"日历变化不推翻长期目标"静默失效。"""
    from campuspath_monitor.replan import MissingHorizon

    pw = pathway(item("PI-1", "OPP-1"), item("PI-2", "OPP-2"))
    with pytest.raises(MissingHorizon):
        compute_scope(event(ReplanTriggerType.CALENDAR_CHANGE, subject="OPP-1"), pw,
                      horizon_of={"PI-1": "this_term"})


def test_non_local_trigger_does_not_need_horizons():
    """成绩变化本来就允许波及长期项，不必强制调用方给出时间尺度。"""
    pw = pathway(item("PI-1", "COMP 2011"))
    scope = compute_scope(
        event(ReplanTriggerType.NEW_GRADE, subject="COMP 2011"), pw, horizon_of={}
    )
    assert scope.affected_plan_item_ids == ("PI-1",)
