"""Connector & Catalog Layer（Spec §6.11、§10、D3）。**零 LLM。**

三个统一接口，加一个 Source Health。接口先于实现存在，是为了让
Mock 服务（WP4）与未来的真实适配器**无法**长出不同的形状——
Spec §11.4 明说 Mock "必须使用与未来真实适配器相同的 Schema 和接口，
避免 Demo 后全部重写"。

一条边界写在类型里：:class:`CalendarProvider.free_busy` **必须显式收到
采集层级**才可能返回标题。2026-07-30 起日历授权分两级——
一级只有忙/闲，二级学生可另行授权读事件标题，让系统说得出
"这个周三的例会也许可以缺一次"，而不只是"你没空了"。

放宽的只有标题**文本**：token 仍由实现持有、**不出现在任何返回值里**，
架构第 3 条不动。B5 也仍然成立，只是从"日历详情 = 0"变成
"**超出已授权层级的采集 = 0**"，由 `AvailabilityBlock` 的 validator 强制。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from typing import Protocol, runtime_checkable

from campuspath_contracts.calendar import CalendarDetailLevel
from campuspath_contracts.academic import (
    CourseCatalogItem,
    CourseOffering,
    DegreeRequirement,
    StudentCourseRecord,
)
from campuspath_contracts.opportunity import Opportunity
from campuspath_contracts.publishing import SourceHealth, SourceKind


@runtime_checkable
class EducationDataAdapter(Protocol):
    """SIS / LMS / Degree Audit / Course Catalog / Timetable 的统一读取面。

    **只读。** 没有任何写方法——CampusPath 不改学校的权威系统。
    """

    def course_records(self, student_id: str) -> list[StudentCourseRecord]: ...

    def degree_requirements(self, program_id: str) -> list[DegreeRequirement]: ...

    def catalog(self, subject: str | None = None) -> list[CourseCatalogItem]: ...

    def offerings(self, term: str) -> list[CourseOffering]: ...


@dataclasses.dataclass(frozen=True)
class BusyInterval:
    """日历返回的全部内容。

    仍然**没有** attendees / location / description 的位置可放——
    二级授权放行的只有标题这一项，不是"详情随便取"。
    """

    start: datetime
    end: datetime
    #: 仅当调用方传入 :attr:`CalendarDetailLevel.EVENT_TITLES` 时才可能有值。
    #: Provider 自己不判断学生授权了什么——授权状态在 Capacity & Calendar
    #: Service 那一层，Provider 只按被告知的层级取数。
    title: str | None = None


@runtime_checkable
class CalendarProvider(Protocol):
    """Token 由实现持有，**不出现在任何返回值里**。

    ``detail_level`` 是必须显式传的：默认值写成 ``FREE_BUSY_ONLY``，
    所以忘了传等于取最少，而不是取最多。
    """

    def free_busy(
        self,
        student_id: str,
        start: datetime,
        end: datetime,
        *,
        detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY,
    ) -> list[BusyInterval]: ...

    def create_event(self, student_id: str, title: str, start: datetime,
                     end: datetime, *, idempotency_key: str) -> str: ...


@runtime_checkable
class OpportunityProvider(Protocol):
    def fetch(self, since: datetime | None = None) -> list[Opportunity]: ...

    def source_id(self) -> str: ...


# --------------------------------------------------------------------------
# Source Health（Spec §6.11 的八项）
# --------------------------------------------------------------------------


@dataclasses.dataclass
class SourceProbe:
    """一次同步的观测结果。喂给 :func:`assess_health` 得到八项指标。"""

    source_id: str
    kind: SourceKind
    attempted_at: datetime
    succeeded: bool
    http_status: int | None = None
    records_seen: int = 0
    records_parsed: int = 0
    required_fields_present: int = 0
    required_fields_expected: int = 0
    broken_links: int = 0
    checked_links: int = 0
    deadline_conflicts: int = 0
    duplicate_signals: int = 0
    last_success_at: datetime | None = None


def assess_health(probe: SourceProbe, *, now: datetime) -> SourceHealth:
    """把一次探测折算成八项运维指标。

    **不展示任何原文或学生数据**（Spec §6.11）：返回的全是比率与计数。
    """
    status = "ok"
    if not probe.succeeded:
        status = {
            429: "rate_limited",
            401: "auth_expired",
            403: "auth_expired",
        }.get(probe.http_status or 0, "unreachable")

    freshness = None
    if probe.last_success_at is not None:
        freshness = round((now - probe.last_success_at).total_seconds() / 3600, 2)

    return SourceHealth(
        source_id=probe.source_id,
        kind=probe.kind,
        last_successful_sync=probe.last_success_at,
        fetch_auth_status=status,  # type: ignore[arg-type]
        parse_success_rate=_ratio(probe.records_parsed, probe.records_seen),
        freshness_hours=freshness,
        broken_link_rate=_ratio(probe.broken_links, probe.checked_links),
        deadline_consistency_issues=probe.deadline_conflicts,
        schema_coverage_rate=_ratio(
            probe.required_fields_present, probe.required_fields_expected
        ),
        duplicate_conflict_signals=probe.duplicate_signals,
        checked_at=now,
    )


def needs_human_attention(health: SourceHealth, *, freshness_limit_hours: float = 72.0) -> bool:
    """Spec §6.11：连接器自动同步，**只有异常才进人工队列**。

    把"什么算异常"写在一个函数里，避免每个面板各判各的。
    """
    if health.fetch_auth_status != "ok":
        return True
    if health.freshness_hours is not None and health.freshness_hours > freshness_limit_hours:
        return True
    if health.parse_success_rate < 0.9:
        return True
    if health.broken_link_rate > 0.1:
        return True
    if health.deadline_consistency_issues > 0:
        return True
    if health.schema_coverage_rate < 0.9:
        return True
    return health.duplicate_conflict_signals > 0


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        # 没检查过 ≠ 全都坏了。返回 1.0 并让 freshness 去暴露"根本没跑过"
        return 1.0
    return round(min(max(numerator / denominator, 0.0), 1.0), 4)
