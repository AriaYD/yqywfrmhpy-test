"""Calendar Fixtures 与 CapacitySnapshot。

模式 B（Fixture）的数据源。接口与模式 A（真实 Google OAuth）完全一致——
两者产出的都是 :class:`AvailabilityBlock`，因为**日历原始事件字段止步于
Capacity & Calendar Service**（Spec §15.4 规则 3）。Fixture 里同样没有
标题、参与人、地点：不是"演示时先不填"，是这一层根本没有这些字段。

保护区块只来自**学生显式设置**：
睡眠窗口来自 ``EnergyProfile.sleep_window_*``，没设就没有睡眠保护块。
Persona A 就是这种情况，它是 B6 的反例样本——日历再满也不该升级。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta, timezone

from campuspath_contracts.calendar import (
    CalendarDetailLevel,
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CalendarConnection,
    CalendarDetailLevel,
    CalendarProviderId,
    CapacitySnapshot,
)
from campuspath_contracts.common import TimeRange
from campuspath_contracts.profile import ConsentScope

from .catalog import Catalog
from .config import CURRENT_TERM, SEED_TODAY
from .personas import PersonaBundle
from .rng import stream

_TZ = timezone.utc
_WEEKDAY_INDEX = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


@dataclasses.dataclass
class CalendarBundle:
    connections: list[CalendarConnection]
    blocks: list[AvailabilityBlock]
    snapshots: list[CapacitySnapshot]


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _span(day: date, start: str, end: str) -> TimeRange:
    sh, sm = (int(x) for x in start.split(":"))
    eh, em = (int(x) for x in end.split(":"))
    start_dt = datetime.combine(day, time(sh, sm), tzinfo=_TZ)
    end_dt = datetime.combine(day, time(eh, em), tzinfo=_TZ)
    if end_dt <= start_dt:                      # 跨午夜的睡眠窗口
        end_dt += timedelta(days=1)
    return TimeRange(start=start_dt, end=end_dt)


def _hours(blocks: list[AvailabilityBlock], kind: AvailabilityType) -> float:
    return round(sum(b.span.minutes for b in blocks if b.type is kind) / 60.0, 2)


def build_calendars(
    catalog: Catalog, personas: list[PersonaBundle], weeks: int
) -> CalendarBundle:
    connections: list[CalendarConnection] = []
    blocks: list[AvailabilityBlock] = []
    snapshots: list[CapacitySnapshot] = []

    week_start = _monday_of(SEED_TODAY)

    for persona in personas:
        profile = persona.profile
        if not profile.has_consent(ConsentScope.CALENDAR_FREEBUSY):
            continue

        sid = profile.student_id
        rng = stream(f"calendar.{sid}")
        connections.append(
            CalendarConnection(
                connection_id=f"CAL-{sid}",
                student_id=sid,
                provider=CalendarProviderId.FIXTURE,
                selected_calendar_refs=(f"cal-opaque-{sid.lower()}",),
                scopes=("calendar.freebusy.readonly",),
                detail_level=CalendarDetailLevel.FREE_BUSY_ONLY,
                last_sync=datetime(SEED_TODAY.year, SEED_TODAY.month, SEED_TODAY.day,
                                   7, 0, tzinfo=_TZ),
            )
        )

        # 二级日历授权：只有开了它的学生，区块里才允许出现标题。
        # 取自 Profile 上的同意记录，不是这里另设一个开关——
        # "学生同意了什么"必须只有一个出处。
        titles_granted = any(
            c.scope is ConsentScope.CALENDAR_EVENT_TITLES and c.granted
            and c.revoked_at is None
            for c in profile.consent
        )

        # 本学期在读课程的上课时段 → busy
        enrolled = [r.course_id for r in persona.course_records if r.term == CURRENT_TERM]
        meetings: list[tuple[int, str, str]] = []
        for course_id in enrolled:
            for offering in catalog.offerings_for(course_id, CURRENT_TERM)[:1]:
                for slot in offering.schedule:
                    meetings.append(
                        (_WEEKDAY_INDEX[slot.weekday], slot.start_time, slot.end_time)
                    )

        energy = profile.energy_profile
        # 冲刺型学生的固定承诺更多，用于造出真实的超载
        extra_commitments = 6 if energy.preferred_intensity.value == "sprint" else 2

        for week in range(weeks):
            base = week_start + timedelta(weeks=week)
            week_blocks: list[AvailabilityBlock] = []

            def emit(day_offset: int, start: str, end: str,
                     kind: AvailabilityType, source: BlockSource,
                     tag: str, reachable: bool = True,
                     title: str | None = None) -> None:
                day = base + timedelta(days=day_offset)
                # 标题只在学生授权了二级采集时才写进去。
                # 契约的 validator 会拒绝"没授权却带标题"的对象，
                # 所以这里写错了会在生成 Seed 时当场炸，而不是等到界面上。
                # 两类例外（R4-M，2026-07-31）：课表来自**教务公开数据**、
                # 学生自设区块是**本人笔迹**——都不是"从私人日历采集"，
                # B5 管不到它们，一级授权学生也该看得懂自己的课表。
                titled = title is not None and (
                    titles_granted
                    or source is BlockSource.COURSE_TIMETABLE
                    or source is BlockSource.STUDENT_DEFINED
                )
                week_blocks.append(
                    AvailabilityBlock(
                        block_id=f"AB-{sid}-W{week}-{tag}-{day_offset}",
                        student_id=sid,
                        span=_span(day, start, end),
                        type=kind,
                        source=source,
                        privacy_level=("student_defined"
                                       if source is BlockSource.STUDENT_DEFINED else "opaque"),
                        reachable=reachable,
                        detail_level=(CalendarDetailLevel.EVENT_TITLES if titled
                                      else CalendarDetailLevel.FREE_BUSY_ONLY),
                        title=title if titled else None,
                    )
                )

            # 一门课每周两次课，与真实课表节奏一致。
            # R4-M：标题带课程全名（教务公开数据），不用光秃秃的课程码。
            for index, (weekday, start, _end) in enumerate(meetings):
                long_end = f"{int(start[:2]) + 1:02d}:{int(start[3:]) + 20:02d}"
                course_id = enrolled[index] if index < len(enrolled) else None
                course = catalog.courses.get(course_id) if course_id else None
                label = (f"{course_id} · {course.title}" if course
                         else course_id)
                emit(weekday, start, long_end, AvailabilityType.BUSY,
                     BlockSource.COURSE_TIMETABLE, f"class{index}a",
                     title=f"{label} — Lecture" if course_id else None)
                emit((weekday + 2) % 5, start, long_end, AvailabilityType.BUSY,
                     BlockSource.COURSE_TIMETABLE, f"class{index}b",
                     title=f"{label} — Tutorial" if course_id else None)

            # 学生显式设置的保护区块
            if energy.sleep_window_start and energy.sleep_window_end:
                for day_offset in range(7):
                    emit(day_offset, energy.sleep_window_start, energy.sleep_window_end,
                         AvailabilityType.PROTECTED, BlockSource.STUDENT_DEFINED, "sleep",
                         title="Sleep")
            for day_offset in range(7):
                emit(day_offset, "12:00", "12:45", AvailabilityType.PROTECTED,
                     BlockSource.STUDENT_DEFINED, "meal", title="Meal")
            for constraint in profile.constraints:
                if constraint.kind == "caregiving":
                    emit(5, "09:00", "18:00", AvailabilityType.PROTECTED,
                         BlockSource.STUDENT_DEFINED, "care")

            # 通勤与恢复缓冲
            for day_offset in range(5):
                emit(day_offset, "08:15", "08:45", AvailabilityType.BUFFER,
                     BlockSource.DERIVED, "commute")
            if energy.recovery_preference_defined and week % 2 == 0:
                emit(6, "10:00", "13:00", AvailabilityType.PROTECTED,
                     BlockSource.STUDENT_DEFINED, "recovery", title="Recovery")

            # 其他既有承诺（兼职、社团、组会）
            for index in range(extra_commitments):
                day_offset = rng.randrange(0, 6)
                hour = 14 + (index % 4)
                emit(day_offset, f"{hour:02d}:00", f"{hour + 1:02d}:00",
                     AvailabilityType.FLEXIBLE, BlockSource.CALENDAR_FREEBUSY, f"commit{index}")

            # 夜间与碎片时段不计入可用时间：先算出真正可用的空档
            emit(1, "19:00", "21:30", AvailabilityType.FREE, BlockSource.DERIVED, "free1")
            emit(3, "19:00", "21:30", AvailabilityType.FREE, BlockSource.DERIVED, "free2")
            emit(6, "14:00", "18:00", AvailabilityType.FREE, BlockSource.DERIVED, "free3")
            # 跨地点无法到达的空档：存在，但不计入 Usable Free Time
            emit(2, "16:00", "17:00", AvailabilityType.FREE, BlockSource.DERIVED,
                 "unreachable", reachable=False)

            blocks.extend(week_blocks)

            # §16.6 的 Usable Free Time 起点是**学生自己声明的每周可支配成长时间**
            # （§16.7：「不是一周全部 168 小时」），再扣掉日历里查到的不可用碎片。
            # 睡眠与用餐虽然也是保护区块，但它们本来就不在成长时段内，
            # 不能再从成长预算里扣一次——那会把可支配容量算成大幅负数。
            unusable = round(
                sum(b.span.minutes for b in week_blocks
                    if b.type is AvailabilityType.FREE and not b.reachable) / 60.0, 2
            )
            usable_free = round(max(energy.weekly_discretionary_hours - unusable, 0.0), 2)

            # 只计入落在成长时段内的保护区块：恢复区块。
            protected_in_growth = round(
                sum(b.span.minutes for b in week_blocks
                    if b.type is AvailabilityType.PROTECTED
                    and b.block_id.endswith(("recovery-6",))) / 60.0, 2
            )
            transition = _hours(week_blocks, AvailabilityType.BUFFER)
            flexible = _hours(week_blocks, AvailabilityType.FLEXIBLE)
            recovery_buffer = round(usable_free * energy.min_buffer_ratio, 2)

            discretionary = round(
                usable_free - protected_in_growth - transition - recovery_buffer - flexible, 2
            )
            # 计划负荷由学生选择的强度决定，而不是反推容量——
            # 这样"超载"是数据里真实存在的情形，不是为了让断言通过而凑出来的
            intensity_factor = {"gentle": 0.25, "balanced": 0.35, "sprint": 0.9}[
                energy.preferred_intensity.value
            ]
            planned = round(energy.weekly_discretionary_hours * intensity_factor, 2)
            overload = planned > discretionary
            buffer_ratio = round(
                (discretionary - planned) / discretionary, 3
            ) if discretionary > 0 else -1.0

            snapshots.append(
                CapacitySnapshot(
                    snapshot_id=f"CS-{sid}-W{week}",
                    student_id=sid,
                    period_start=base,
                    period_end=base + timedelta(days=6),
                    fixed_load_hours=_hours(week_blocks, AvailabilityType.BUSY),
                    protected_time_hours=protected_in_growth,
                    transition_hours=transition,
                    recovery_buffer_hours=recovery_buffer,
                    existing_flexible_hours=flexible,
                    usable_free_hours=usable_free,
                    discretionary_capacity_hours=discretionary,
                    planned_load_hours=planned,
                    buffer_ratio=buffer_ratio,
                    overload_signal=overload,
                )
            )

    return CalendarBundle(connections=connections, blocks=blocks, snapshots=snapshots)
