"""Capacity & Calendar Service —— free/busy → 五类时段 → CapacitySnapshot。

**零 LLM，且日历 Token 与原始事件字段止步于此**（Spec §15.4 规则 3、CLAUDE.md 第 3 条）。
本模块的输入是 :class:`FreeBusyInterval`：只有起止时间，没有标题、参与人、地点。
Provider 适配器负责在更外层就把这些字段丢掉——契约里根本没有承载它们的地方。

## §16.6 的公式

```
Discretionary Capacity =
    Usable Free Time
  - Protected Life Blocks（落在成长时段内的）
  - Transition / Commute Time
  - Recovery Buffer
  - Existing Flexible Commitments
```

`Usable Free Time` 的起点是**学生自己声明的每周可支配成长时间**
（§16.7：「不是一周全部 168 小时」），再扣掉日历里查到的不可用碎片。

睡眠与用餐虽然也是保护区块，但它们本来就不在成长时段内，
**不能再从成长预算里扣一次**——那会把可支配容量算成大幅负数，
让每个学生看起来都严重超载，于是 B1 的告警彻底失去意义。
它们仍然进 :class:`AvailabilityBlock`，因为 B2 需要它们来挡排程。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CapacitySnapshot,
)
from campuspath_contracts.common import TimeRange
from campuspath_contracts.profile import EnergyProfile

#: 短于此长度的空档不计入可用时间（§16.6：过短碎片不算）。
MIN_USABLE_FRAGMENT = timedelta(minutes=30)

#: 成长时段的作息边界。此范围之外的空档不计入 Usable Free Time。
GROWTH_WINDOW = (time(8, 0), time(23, 0))


@dataclasses.dataclass(frozen=True)
class FreeBusyInterval:
    """来自 CalendarProvider 的一段忙碌时间。

    **只有起止。** 没有标题、参与人、地点、备注——B5 的边界在适配器就划好了，
    不是靠下游"记得不要用"。
    """

    start: datetime
    end: datetime


@dataclasses.dataclass(frozen=True)
class StudentBoundaries:
    """学生**显式设置**的边界。一个字段都不许从日历反推（§16.8.2）。"""

    sleep_window: tuple[time, time] | None = None
    meal_windows: tuple[tuple[time, time], ...] = ()
    recovery_windows: tuple[tuple[int, time, time], ...] = ()   # (weekday, start, end)
    unavailable_windows: tuple[tuple[int, time, time], ...] = ()
    commute_minutes_per_class_day: int = 0


def _span(day: date, window: tuple[time, time], tzinfo) -> TimeRange:
    start = datetime.combine(day, window[0], tzinfo=tzinfo)
    end = datetime.combine(day, window[1], tzinfo=tzinfo)
    if end <= start:                       # 跨午夜的睡眠窗口
        end += timedelta(days=1)
    return TimeRange(start=start, end=end)


def _in_growth_window(span: TimeRange) -> bool:
    return GROWTH_WINDOW[0] <= span.start.timetz().replace(tzinfo=None) < GROWTH_WINDOW[1]


def classify(
    student_id: str,
    week_start: date,
    busy: list[FreeBusyInterval],
    boundaries: StudentBoundaries,
    *,
    tzinfo,
    reachable_checker=None,
) -> list[AvailabilityBlock]:
    """把 free/busy 与学生边界分成五类时段。

    ``reachable_checker(span) -> bool`` 由调用方注入（跨地点是否来得及）。
    默认全部可达——**默认宽松是有意的**：把"可能到不了"当成"到不了"
    会凭空削减学生的可用时间。
    """
    blocks: list[AvailabilityBlock] = []
    index = 0

    def emit(span: TimeRange, kind: AvailabilityType, source: BlockSource,
             tag: str, reachable: bool = True) -> None:
        nonlocal index
        index += 1
        blocks.append(
            AvailabilityBlock(
                block_id=f"AB-{student_id}-{week_start.isoformat()}-{tag}-{index}",
                student_id=student_id,
                span=span,
                type=kind,
                source=source,
                privacy_level=("student_defined"
                               if source is BlockSource.STUDENT_DEFINED else "opaque"),
                reachable=reachable,
            )
        )

    for interval in sorted(busy, key=lambda i: i.start):
        span = TimeRange(start=interval.start, end=interval.end)
        emit(span, AvailabilityType.BUSY, BlockSource.CALENDAR_FREEBUSY, "busy",
             True if reachable_checker is None else reachable_checker(span))

    for offset in range(7):
        day = week_start + timedelta(days=offset)
        if boundaries.sleep_window:
            emit(_span(day, boundaries.sleep_window, tzinfo), AvailabilityType.PROTECTED,
                 BlockSource.STUDENT_DEFINED, "sleep")
        for meal in boundaries.meal_windows:
            emit(_span(day, meal, tzinfo), AvailabilityType.PROTECTED,
                 BlockSource.STUDENT_DEFINED, "meal")
        for weekday, start, end in boundaries.recovery_windows:
            if weekday == offset:
                emit(_span(day, (start, end), tzinfo), AvailabilityType.PROTECTED,
                     BlockSource.STUDENT_DEFINED, "recovery")
        for weekday, start, end in boundaries.unavailable_windows:
            if weekday == offset:
                emit(_span(day, (start, end), tzinfo), AvailabilityType.PROTECTED,
                     BlockSource.STUDENT_DEFINED, "unavailable")

    if boundaries.commute_minutes_per_class_day:
        class_days = sorted({b.span.start.date() for b in blocks
                             if b.type is AvailabilityType.BUSY})
        for day in class_days:
            start = datetime.combine(
                day, GROWTH_WINDOW[0], tzinfo=tzinfo
            ) - timedelta(minutes=boundaries.commute_minutes_per_class_day)
            emit(TimeRange(start=start, end=start + timedelta(
                minutes=boundaries.commute_minutes_per_class_day)),
                AvailabilityType.BUFFER, BlockSource.DERIVED, "commute")

    # 成长时段里剩下的空白 → FREE。
    #
    # 这一步曾经缺失，于是 classify() 只产出 BUSY/PROTECTED/BUFFER，
    # 而 find_unusable_fragments 只看 FREE——§16.6 的"过短碎片、深夜、
    # 跨地点无法到达不计入"在真实管道里一次都没执行过，
    # reachable_checker 也从来没有消费者。看起来是道保证，其实没接上。
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        window_start = datetime.combine(day, GROWTH_WINDOW[0], tzinfo=tzinfo)
        window_end = datetime.combine(day, GROWTH_WINDOW[1], tzinfo=tzinfo)
        occupied = sorted(
            (max(b.span.start, window_start), min(b.span.end, window_end))
            for b in blocks
            if b.span.start < window_end and b.span.end > window_start
        )
        cursor = window_start
        for start, end in occupied:
            if start > cursor:
                gap = TimeRange(start=cursor, end=start)
                emit(gap, AvailabilityType.FREE, BlockSource.DERIVED, "gap",
                     True if reachable_checker is None else reachable_checker(gap))
            cursor = max(cursor, end)
        if cursor < window_end:
            gap = TimeRange(start=cursor, end=window_end)
            emit(gap, AvailabilityType.FREE, BlockSource.DERIVED, "gap",
                 True if reachable_checker is None else reachable_checker(gap))

    return blocks


@dataclasses.dataclass(frozen=True)
class UnusableFragment:
    span: TimeRange
    reason: str


def find_unusable_fragments(
    blocks: list[AvailabilityBlock]
) -> list[UnusableFragment]:
    """§16.6：过短碎片、深夜、跨地点无法到达的时段不计入 Usable Free Time。"""
    fragments: list[UnusableFragment] = []
    for block in blocks:
        if block.type is not AvailabilityType.FREE:
            continue
        if not block.reachable:
            fragments.append(UnusableFragment(block.span, "跨地点无法到达"))
        elif block.span.minutes < MIN_USABLE_FRAGMENT.total_seconds() / 60:
            fragments.append(UnusableFragment(block.span, "碎片过短"))
        elif not _in_growth_window(block.span):
            fragments.append(UnusableFragment(block.span, "落在成长时段之外"))
    return fragments


def _hours(blocks: list[AvailabilityBlock], kind: AvailabilityType,
           tag: str | None = None) -> float:
    return round(
        sum(b.span.minutes for b in blocks
            if b.type is kind and (tag is None or f"-{tag}-" in b.block_id)) / 60.0,
        2,
    )


def _declared_protected_hours(boundaries: StudentBoundaries) -> float:
    """从**学生的声明**算出要从成长预算里扣的保护时间。

    只有恢复区块与"不可用窗口"要扣：睡眠与用餐本来就不在成长预算内
    （§16.7 的可支配时间已经排除了它们），再扣一次会把每个学生都算成大幅负容量，
    于是 B1 的超载告警对所有人恒真，等于没有。

    此前这里靠 ``"-recovery-" in block_id`` 挑块——注释说的是"落在成长时段内"，
    代码做的是按 tag 匹配，两者对不上，而且学号里只要出现 ``-recovery-``
    就会算错。改成直接读声明，没有字符串匹配。
    """
    total = 0.0
    for _weekday, start, end in boundaries.recovery_windows:
        total += (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    for _weekday, start, end in boundaries.unavailable_windows:
        total += (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return round(total / 60.0, 2)


def build_snapshot(
    student_id: str,
    week_start: date,
    blocks: list[AvailabilityBlock],
    energy: EnergyProfile,
    planned_load_hours: float,
    *,
    boundaries: StudentBoundaries,
    snapshot_id: str | None = None,
) -> CapacitySnapshot:
    """按 §16.6 计算一周的 CapacitySnapshot。纯算术，可单测到小数点。"""
    unusable = round(
        sum(f.span.minutes for f in find_unusable_fragments(blocks)) / 60.0, 2
    )
    usable_free = round(max(energy.weekly_discretionary_hours - unusable, 0.0), 2)

    protected_in_growth = _declared_protected_hours(boundaries)
    transition = _hours(blocks, AvailabilityType.BUFFER)
    flexible = _hours(blocks, AvailabilityType.FLEXIBLE)
    recovery_buffer = round(usable_free * energy.min_buffer_ratio, 2)

    discretionary = round(
        usable_free - protected_in_growth - transition - recovery_buffer - flexible, 2
    )
    overload = planned_load_hours > discretionary
    # 未安排比例按 **usable_free** 算，不按 discretionary 算。
    # discretionary 已经把 recovery_buffer 扣掉了；再拿它当分母去比 min_buffer_ratio，
    # 等于把同一份缓冲收两次费——一个真有 35% 余量的学生会因此收到 blocking 信号。
    buffer_ratio = (
        round((usable_free - planned_load_hours) / usable_free, 3)
        if usable_free > 0 else 0.0
    )

    return CapacitySnapshot(
        snapshot_id=snapshot_id or f"CS-{student_id}-{week_start.isoformat()}",
        student_id=student_id,
        period_start=week_start,
        period_end=week_start + timedelta(days=6),
        fixed_load_hours=_hours(blocks, AvailabilityType.BUSY),
        protected_time_hours=round(protected_in_growth, 2),
        transition_hours=transition,
        recovery_buffer_hours=recovery_buffer,
        existing_flexible_hours=flexible,
        usable_free_hours=usable_free,
        discretionary_capacity_hours=discretionary,
        planned_load_hours=round(planned_load_hours, 2),
        buffer_ratio=buffer_ratio,
        overload_signal=overload,
    )
