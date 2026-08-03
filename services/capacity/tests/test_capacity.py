"""Capacity & Calendar Service：五类时段、§16.6 公式、六类规划信号。

对应 D3 的 Capacity 条款与 B1 / B5。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CalendarDetailLevel,
)
from campuspath_contracts.common import IntensityMode, TimeRange
from campuspath_contracts.profile import EnergyProfile

from campuspath_capacity.capacity import (
    GROWTH_WINDOW,
    MIN_USABLE_FRAGMENT,
    FreeBusyInterval,
    StudentBoundaries,
    build_snapshot,
    classify,
    find_unusable_fragments,
)
from campuspath_capacity.signals import (
    CONSECUTIVE_DAYS_WITHOUT_REST,
    DECLINE_STREAK,
    INTENSITY_CEILING,
    PlanningSignal,
    detect,
)

TZ = timezone.utc
WEEK = date(2026, 9, 14)          # 周一


def busy(day_offset: int, start_hour: int, end_hour: int) -> FreeBusyInterval:
    day = WEEK + timedelta(days=day_offset)
    return FreeBusyInterval(
        start=datetime.combine(day, time(start_hour), tzinfo=TZ),
        end=datetime.combine(day, time(end_hour), tzinfo=TZ),
    )


def energy(**kw) -> EnergyProfile:
    base = dict(weekly_discretionary_hours=14.0, min_buffer_ratio=0.2)
    base.update(kw)
    return EnergyProfile(**base)


def free_block(day_offset: int, start_hour: int, end_minutes: int, *,
               reachable: bool = True, bid: str = "free") -> AvailabilityBlock:
    day = WEEK + timedelta(days=day_offset)
    start = datetime.combine(day, time(start_hour), tzinfo=TZ)
    return AvailabilityBlock(
        block_id=f"AB-STU-A-{WEEK}-{bid}-{day_offset}{start_hour}",
        student_id="STU-A",
        span=TimeRange(start=start, end=start + timedelta(minutes=end_minutes)),
        type=AvailabilityType.FREE,
        source=BlockSource.DERIVED,
        reachable=reachable,
    )


# --------------------------------------------------------------------------
# 五类时段
# --------------------------------------------------------------------------


def test_busy_intervals_become_busy_blocks():
    blocks = classify("STU-A", WEEK, [busy(0, 9, 11)], StudentBoundaries(), tzinfo=TZ)
    busy_blocks = [b for b in blocks if b.type is AvailabilityType.BUSY]
    assert len(busy_blocks) == 1
    assert busy_blocks[0].span.minutes == 120


def test_blocks_carry_no_event_detail():
    """B5：**默认层级下**分类结果不带任何事件详情。

    2026-07-30 起日历授权分两级：一级只有忙/闲，二级学生可另行授权读标题。
    Capacity Service 自己不做任何提升——它拿到什么就分类什么，
    所以这里断言的是"默认路径产出的 title 为 None、层级仍是 free_busy_only"。
    """
    blocks = classify("STU-A", WEEK, [busy(0, 9, 11)], StudentBoundaries(), tzinfo=TZ)
    fields = set(blocks[0].model_dump())
    assert fields == {
        "block_id", "student_id", "span", "type", "source", "privacy_level",
        "reachable", "detail_level", "title",
        # 2026-07-31（契约 1.5.0）：学生给自己视图块设的提醒分钟数。
        # 不是事件详情——没有内容、不来自 Provider；默认路径下必须为 None。
        "reminder_minutes_before",
    }
    assert blocks[0].title is None
    assert blocks[0].reminder_minutes_before is None
    assert blocks[0].detail_level is CalendarDetailLevel.FREE_BUSY_ONLY


def test_sleep_window_only_appears_when_the_student_set_it():
    """没设窗口 → 没有睡眠保护块。这是 B6 在数据层的前提。"""
    without = classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ)
    assert not [b for b in without if "-sleep-" in b.block_id]

    with_window = classify(
        "STU-A", WEEK, [],
        StudentBoundaries(sleep_window=(time(0, 30), time(7, 30))), tzinfo=TZ,
    )
    sleep_blocks = [b for b in with_window if "-sleep-" in b.block_id]
    assert len(sleep_blocks) == 7
    assert all(b.type is AvailabilityType.PROTECTED for b in sleep_blocks)
    assert all(b.privacy_level == "student_defined" for b in sleep_blocks)


def test_sleep_window_crossing_midnight_is_handled():
    blocks = classify(
        "STU-A", WEEK, [],
        StudentBoundaries(sleep_window=(time(23, 30), time(7, 0))), tzinfo=TZ,
    )
    sleep = next(b for b in blocks if "-sleep-" in b.block_id)
    assert sleep.span.minutes == 450          # 7.5 小时


def test_recovery_window_lands_on_the_right_weekday():
    blocks = classify(
        "STU-A", WEEK, [],
        StudentBoundaries(recovery_windows=((6, time(10), time(13)),)), tzinfo=TZ,
    )
    recovery = [b for b in blocks if "-recovery-" in b.block_id]
    assert len(recovery) == 1
    assert recovery[0].span.start.date() == WEEK + timedelta(days=6)


def test_unreachable_slot_is_flagged_not_dropped():
    """跨地点到不了的空档仍然记录下来，只是标记为不可达——
    直接丢掉会让"为什么这段没被排"无从解释。"""
    blocks = classify(
        "STU-A", WEEK, [busy(0, 9, 11)], StudentBoundaries(),
        tzinfo=TZ, reachable_checker=lambda span: False,
    )
    assert all(b.reachable is False for b in blocks if b.type is AvailabilityType.BUSY)


# --------------------------------------------------------------------------
# 不可用碎片
# --------------------------------------------------------------------------


def test_short_fragment_is_unusable():
    fragments = find_unusable_fragments([free_block(0, 14, 20)])
    assert len(fragments) == 1
    assert "碎片" in fragments[0].reason


def test_fragment_at_the_threshold_is_usable():
    minutes = int(MIN_USABLE_FRAGMENT.total_seconds() / 60)
    assert find_unusable_fragments([free_block(0, 14, minutes)]) == []


def test_late_night_gap_is_unusable():
    fragments = find_unusable_fragments([free_block(0, 2, 120)])
    assert "成长时段之外" in fragments[0].reason


def test_unreachable_gap_is_unusable():
    fragments = find_unusable_fragments([free_block(0, 14, 120, reachable=False)])
    assert "无法到达" in fragments[0].reason


def test_normal_gap_is_usable():
    assert find_unusable_fragments([free_block(0, 19, 150)]) == []


# --------------------------------------------------------------------------
# §16.6 公式
# --------------------------------------------------------------------------


def test_snapshot_satisfies_the_formula():
    """契约层的 validator 会检查公式；这里确认我们算出来的确实过得了。"""
    blocks = classify(
        "STU-A", WEEK, [busy(0, 9, 11), busy(2, 9, 11)],
        StudentBoundaries(
            sleep_window=(time(0, 30), time(7, 30)),
            meal_windows=((time(12), time(12, 45)),),
            recovery_windows=((6, time(10), time(12)),),
            commute_minutes_per_class_day=30,
        ),
        tzinfo=TZ,
    )
    snapshot = build_snapshot("STU-A", WEEK, blocks, energy(), planned_load_hours=4.0,
                            boundaries=StudentBoundaries())
    assert snapshot.discretionary_capacity_hours > 0
    assert snapshot.overload_signal is False


def test_sleep_and_meals_do_not_eat_the_growth_budget():
    """把睡眠也从成长预算里扣一次，会让每个学生都"严重超载"，
    于是 B1 的告警彻底失去意义。"""
    boundaries = StudentBoundaries(
        sleep_window=(time(0, 30), time(7, 30)),
        meal_windows=((time(12), time(12, 45)),),
    )
    blocks = classify("STU-A", WEEK, [], boundaries, tzinfo=TZ)
    snapshot = build_snapshot("STU-A", WEEK, blocks, energy(), planned_load_hours=0.0,
                            boundaries=StudentBoundaries())
    # 睡眠 49h + 用餐 5.25h 若被计入，可支配容量会变成大幅负数
    assert snapshot.protected_time_hours == 0.0
    assert snapshot.discretionary_capacity_hours > 0


def test_recovery_window_does_reduce_capacity():
    """恢复区块落在成长时段内，确实会占用可支配时间。"""
    plain = StudentBoundaries()
    with_rec = StudentBoundaries(recovery_windows=((6, time(10), time(13)),))
    without = build_snapshot(
        "STU-A", WEEK, classify("STU-A", WEEK, [], plain, tzinfo=TZ),
        energy(), planned_load_hours=0.0, boundaries=plain,
    )
    with_recovery = build_snapshot(
        "STU-A", WEEK, classify("STU-A", WEEK, [], with_rec, tzinfo=TZ),
        energy(), planned_load_hours=0.0, boundaries=with_rec,
    )
    assert with_recovery.discretionary_capacity_hours < without.discretionary_capacity_hours


def test_overload_is_signalled_not_hidden():
    blocks = classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ)
    snapshot = build_snapshot("STU-A", WEEK, blocks, energy(), planned_load_hours=99.0,
                            boundaries=StudentBoundaries())
    assert snapshot.overload_signal is True


def test_buffer_is_reserved_before_planning():
    """缓冲是容量的一部分，不是可被计划吃掉的余量（§16.8）。"""
    blocks = classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ)
    snapshot = build_snapshot(
        "STU-A", WEEK, blocks, energy(min_buffer_ratio=0.3), planned_load_hours=0.0,
        boundaries=StudentBoundaries(),
    )
    assert snapshot.recovery_buffer_hours == pytest.approx(
        snapshot.usable_free_hours * 0.3, abs=0.01
    )


# --------------------------------------------------------------------------
# 六类规划信号
# --------------------------------------------------------------------------


def _snapshot(planned: float, buffer_ratio: float | None = None):
    blocks = classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ)
    snapshot = build_snapshot("STU-A", WEEK, blocks, energy(), planned_load_hours=planned,
                              boundaries=StudentBoundaries())
    if buffer_ratio is None:
        return snapshot
    return snapshot.model_copy(update={"buffer_ratio": buffer_ratio})


def _detect(**kw):
    base = dict(
        week_start=WEEK,
        blocks=classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ),
        snapshot=_snapshot(4.0),
        intensity=IntensityMode.BALANCED,
        exam_or_deadline_days=[],
        consecutive_declines=0,
        buffer_squeezed_by_new_event=False,
    )
    base.update(kw)
    return detect(**base)


def test_no_rest_block_streak_is_detected():
    kinds = {s.kind for s in _detect()}
    assert "no_rest_block_streak" in kinds


def test_rest_blocks_break_the_streak():
    blocks = classify(
        "STU-A", WEEK, [],
        StudentBoundaries(recovery_windows=tuple((d, time(10), time(12)) for d in range(7))),
        tzinfo=TZ,
    )
    assert "no_rest_block_streak" not in {s.kind for s in _detect(blocks=blocks)}


def test_deadline_cluster_is_detected():
    days = [WEEK + timedelta(days=i) for i in (1, 2, 3)]
    assert "deadline_cluster" in {s.kind for s in _detect(exam_or_deadline_days=days)}


def test_deadlines_outside_the_week_do_not_count():
    days = [WEEK + timedelta(days=i) for i in (10, 11, 12)]
    assert "deadline_cluster" not in {s.kind for s in _detect(exam_or_deadline_days=days)}


def test_intensity_ceiling_is_the_students_own_choice():
    gentle = _detect(intensity=IntensityMode.GENTLE, snapshot=_snapshot(10.0))
    sprint = _detect(intensity=IntensityMode.SPRINT, snapshot=_snapshot(10.0))
    assert "above_intensity_ceiling" in {s.kind for s in gentle}
    assert "above_intensity_ceiling" not in {s.kind for s in sprint}
    assert INTENSITY_CEILING[IntensityMode.GENTLE] < INTENSITY_CEILING[IntensityMode.SPRINT]


def test_repeated_declines_suggest_asking_the_student():
    signals = _detect(consecutive_declines=DECLINE_STREAK)
    declined = next(s for s in signals if s.kind == "capacity_overestimated")
    assert declined.suggested_action == "ask_student"


def test_squeezed_buffer_is_detected():
    assert "buffer_squeezed" in {s.kind for s in _detect(buffer_squeezed_by_new_event=True)}


def test_negative_buffer_is_detected_even_without_a_new_event():
    assert "buffer_squeezed" in {s.kind for s in _detect(snapshot=_snapshot(4.0, buffer_ratio=-0.2))}


def test_planning_signals_can_never_suggest_a_medical_action():
    """§16.6：这些信号只触发降低强度、移动任务、提供替代项或询问学生。"""
    with pytest.raises(ValueError):
        PlanningSignal("x", "y", "refer_to_counselling")


def test_all_six_signal_kinds_are_reachable():
    days = [WEEK + timedelta(days=i) for i in (1, 2, 3)]
    blocks = classify(
        "STU-A", WEEK,
        [busy(0, 9, 10), busy(0, 11, 12), busy(0, 13, 14), busy(0, 15, 16)],
        StudentBoundaries(), tzinfo=TZ,
    )
    signals = _detect(
        blocks=blocks, exam_or_deadline_days=days, snapshot=_snapshot(30.0, buffer_ratio=-0.4),
        consecutive_declines=DECLINE_STREAK, buffer_squeezed_by_new_event=True,
        intensity=IntensityMode.GENTLE,
    )
    assert {s.kind for s in signals} == {
        "no_rest_block_streak", "deadline_cluster", "context_switching",
        "above_intensity_ceiling", "capacity_overestimated", "buffer_squeezed",
    }



# ── 以下来自 2026-07-29 的独立审查 ──


def test_free_gaps_are_emitted_so_fragment_removal_actually_runs():
    """classify() 曾经只产出 BUSY/PROTECTED/BUFFER，而碎片剔除只看 FREE——
    §16.6 的"过短碎片不计入"在真实管道里一次都没执行过。"""
    blocks = classify(
        "STU-A", WEEK,
        # 每天上午打散成许多短空档
        [busy(0, 9, 10), busy(0, 10, 11), busy(0, 11, 12)],
        StudentBoundaries(), tzinfo=TZ,
    )
    assert any(b.type is AvailabilityType.FREE for b in blocks), "没有 FREE 时段"


def test_short_gaps_between_classes_are_counted_as_unusable():
    blocks = classify(
        "STU-A", WEEK,
        [busy(0, 9, 10), FreeBusyInterval(
            start=datetime.combine(WEEK, time(10, 15), tzinfo=TZ),
            end=datetime.combine(WEEK, time(12), tzinfo=TZ))],
        StudentBoundaries(), tzinfo=TZ,
    )
    fragments = find_unusable_fragments(blocks)
    assert any("碎片" in f.reason for f in fragments), [f.reason for f in fragments]


def test_reachability_checker_is_actually_consulted():
    """注入的跨地点可达性钩子曾经没有任何消费者。"""
    blocks = classify("STU-A", WEEK, [busy(0, 9, 10)], StudentBoundaries(),
                      tzinfo=TZ, reachable_checker=lambda span: False)
    free = [b for b in blocks if b.type is AvailabilityType.FREE]
    assert free and all(b.reachable is False for b in free)
    assert any("无法到达" in f.reason for f in find_unusable_fragments(blocks))


def test_buffer_ratio_is_measured_on_usable_free_not_discretionary():
    """discretionary 已经把 recovery_buffer 扣掉了；再拿它当分母比 min_buffer_ratio，
    等于同一份缓冲收两次费——真有 35% 余量的学生会因此被判缓冲不足。"""
    blocks = classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ)
    snapshot = build_snapshot(
        "STU-A", WEEK, blocks, energy(weekly_discretionary_hours=20.0, min_buffer_ratio=0.2),
        planned_load_hours=13.0, boundaries=StudentBoundaries(),
    )
    assert snapshot.buffer_ratio == pytest.approx(0.35, abs=0.01)
    assert snapshot.buffer_ratio >= 0.2
    assert snapshot.overload_signal is False


def test_protected_hours_come_from_declarations_not_block_id_strings():
    """曾经靠 `"-recovery-" in block_id` 挑块：注释说按时段选，代码按 tag 选，
    而且学号里只要出现 -recovery- 就会算错。"""
    boundaries = StudentBoundaries(
        sleep_window=(time(0, 30), time(7, 30)),
        meal_windows=((time(12), time(12, 45)),),
        recovery_windows=((6, time(10), time(12)),),
    )
    blocks = classify("STU-A", WEEK, [], boundaries, tzinfo=TZ)
    snapshot = build_snapshot("STU-A", WEEK, blocks, energy(), planned_load_hours=0.0,
                              boundaries=boundaries)
    # 只有恢复区块的 2 小时被扣；睡眠 49h 与用餐 5.25h 本就不在成长预算内
    assert snapshot.protected_time_hours == pytest.approx(2.0)


def test_a_student_with_no_capacity_data_is_not_reported_as_fully_loaded():
    """B6：还没连日历、可支配容量为 0 的学生，不是"占用 100%"，是没有数据。"""
    from campuspath_rules.wellbeing import WellbeingInputs, evaluate_signals

    blocks = classify("STU-A", WEEK, [], StudentBoundaries(), tzinfo=TZ)
    empty = build_snapshot(
        "STU-A", WEEK, blocks, energy(weekly_discretionary_hours=0.0,
                                      recovery_preference_defined=True),
        planned_load_hours=0.0, boundaries=StudentBoundaries(),
    )
    signals = evaluate_signals(
        WellbeingInputs(
            student_id="STU-A", period_start=WEEK, period_end=WEEK + timedelta(days=6),
            energy_profile=energy(weekly_discretionary_hours=0.0,
                                  recovery_preference_defined=True),
            capacity=empty, has_recovery_block=False,
        ),
        now=datetime(2026, 9, 15, tzinfo=TZ),
    )
    assert signals == [], [s.signal_type.value for s in signals]
