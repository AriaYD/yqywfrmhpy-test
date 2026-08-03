"""Mock Campus 的数据来源：直接复用 WP2 的 Seed 生成器。

**不另存一份数据。** Mock 服务如果自己维护一套 fixture，它和 Seed 会各自漂移，
于是"跨表一致"这个 WP2 花了 16 项检查守住的性质，在 Demo 用的那条路径上失效。
这里让 Mock 直接吃 Seed 的产出，两者永远同源。

Seed 在进程内构建（full 档 0.03 秒），因此不需要先跑 `make seed`——
少一个"忘了生成"的失败模式。
"""

from __future__ import annotations

import dataclasses
import functools
from datetime import datetime, timedelta, timezone

from campuspath_contracts.academic import (
    CourseCatalogItem,
    CourseOffering,
    DegreeRequirement,
    StudentCourseRecord,
)
from campuspath_contracts.calendar import AvailabilityBlock, AvailabilityType
from campuspath_contracts.opportunity import Opportunity, PublicationStatus
from campuspath_contracts.publishing import SourceHealth, SourceKind
from campuspath_connector.adapters import BusyInterval, SourceProbe, assess_health


@dataclasses.dataclass(frozen=True)
class CampusData:
    """一份 Seed 快照。所有端点从这里读，谁也不自己造数据。"""

    profile_name: str
    course_records: dict[str, list[StudentCourseRecord]]
    requirements: dict[str, list[DegreeRequirement]]
    catalog: list[CourseCatalogItem]
    offerings: list[CourseOffering]
    opportunities: list[Opportunity]
    busy: dict[str, list[BusyInterval]]
    student_ids: tuple[str, ...]
    as_of: datetime


def _group(rows, key):
    grouped: dict[str, list] = {}
    for row in rows:
        grouped.setdefault(getattr(row, key), []).append(row)
    return grouped


@functools.lru_cache(maxsize=2)
def load(profile_name: str = "full") -> CampusData:
    """构建并缓存一份 Seed。同一进程内只建一次。"""
    import sys

    from campuspath_seed.build import build_seed  # 延迟导入：Seed 只在 Mock 里用得到

    bundle = build_seed(profile_name)

    records = [StudentCourseRecord(**r) for r in bundle["student_course_records"]]
    blocks = [AvailabilityBlock(**b) for b in bundle["availability_blocks"]]

    # 日历只对外暴露 free/busy：BUSY 时段的起止，没有别的。
    # 这不是"演示时先不填"——BusyInterval 里根本没有承载标题的地方（B5）。
    busy: dict[str, list[BusyInterval]] = {}
    for block in blocks:
        if block.type is not AvailabilityType.BUSY:
            continue
        busy.setdefault(block.student_id, []).append(
            BusyInterval(start=block.span.start, end=block.span.end)
        )

    return CampusData(
        profile_name=profile_name,
        course_records=_group(records, "student_id"),
        requirements=_group(
            [DegreeRequirement(**r) for r in bundle["degree_requirements"]], "program_id"
        ),
        catalog=[CourseCatalogItem(**c) for c in bundle["courses"]],
        offerings=[CourseOffering(**o) for o in bundle["course_offerings"]],
        opportunities=[
            Opportunity(**o) for o in bundle["opportunities"]
            if o["publication_status"] == PublicationStatus.PUBLISHED.value
        ],
        busy=busy,
        student_ids=tuple(s["student_id"] for s in bundle["students"]),
        as_of=datetime.fromisoformat(bundle["manifest"]["as_of"] + "T00:00:00+00:00"),
    )


#: 六个来源的健康探测。Demo 里这些数字是合成的，但**指标口径与真实适配器一致**，
#: 所以 Career Center 面板不需要为 Demo 单独写一套（Spec §11.4）。
_SOURCES: tuple[tuple[str, SourceKind, bool], ...] = (
    ("SRC-sis", SourceKind.EDUCATION_CONNECTOR, True),
    ("SRC-lms", SourceKind.EDUCATION_CONNECTOR, True),
    ("SRC-catalog", SourceKind.EDUCATION_CONNECTOR, True),
    ("SRC-timetable", SourceKind.EDUCATION_CONNECTOR, True),
    ("SRC-career-center", SourceKind.OPPORTUNITY_SOURCE, True),
    # 刻意留一个不健康的：面板全绿的话，没人知道它到底会不会变红
    ("SRC-partner-ats", SourceKind.OPPORTUNITY_SOURCE, False),
)


def source_health(now: datetime | None = None) -> list[SourceHealth]:
    now = now or datetime.now(timezone.utc)
    out: list[SourceHealth] = []
    for source_id, kind, healthy in _SOURCES:
        probe = SourceProbe(
            source_id=source_id,
            kind=kind,
            attempted_at=now,
            succeeded=healthy,
            http_status=200 if healthy else 429,
            records_seen=120,
            records_parsed=118 if healthy else 40,
            required_fields_present=470 if healthy else 300,
            required_fields_expected=480,
            broken_links=1 if healthy else 14,
            checked_links=120,
            deadline_conflicts=0 if healthy else 3,
            duplicate_signals=0 if healthy else 2,
            last_success_at=now - timedelta(hours=2 if healthy else 96),
        )
        out.append(assess_health(probe, now=now))
    return out
