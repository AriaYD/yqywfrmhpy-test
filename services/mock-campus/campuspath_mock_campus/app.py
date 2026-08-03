"""Mock Campus REST（WP4）：SIS / Degree Audit / Catalog / Timetable /
Opportunity Sources / Calendar Fixtures / Source Health。

Spec §11.4 的要求是"**必须使用与未来真实适配器相同的 Schema 和接口**，
避免 Demo 后全部重写"。所以每个端点的响应类型直接就是 WP1 的契约模型，
而不是一份"长得差不多"的 Mock DTO——由 ``tests/test_conformance.py``
逐个端点断言。

零 LLM：本服务只搬运 Seed 数据，不做任何判定，更不调用模型。
"""

from __future__ import annotations

from datetime import datetime, timezone

from campuspath_contracts.academic import (
    CourseCatalogItem,
    CourseOffering,
    DegreeRequirement,
    StudentCourseRecord,
)
from campuspath_contracts.common import CONTRACTS_VERSION
from campuspath_contracts.opportunity import Opportunity
from campuspath_contracts.calendar import CalendarDetailLevel
from campuspath_contracts.publishing import SourceHealth
from campuspath_connector.adapters import BusyInterval
from fastapi import FastAPI, HTTPException, Query

from . import store

#: 全站标记（D1）。Mock 服务也要带——评委看到的每一条数据都是合成的。
SYNTHETIC_NOTICE = "Synthetic / Demo Data"


def create_app(profile_name: str = "full") -> FastAPI:
    app = FastAPI(
        title="CampusPath Mock Campus",
        version=CONTRACTS_VERSION,
        description=(
            "合成校园系统（SIS / Degree Audit / Course Catalog / Timetable / "
            "Opportunity Sources / Calendar）。**全部数据为合成数据**，"
            "课程目录来自 HKUST 公开页面，不含任何真实学生信息。\n\n"
            "接口形状与未来的真实适配器一致（Spec §11.4），"
            "因此换成真实学校系统时不需要重写调用方。"
        ),
    )
    data = store.load(profile_name)

    @app.middleware("http")
    async def mark_synthetic(request, call_next):
        """每个响应都带 `Synthetic / Demo Data` 头。

        放在中间件而不是逐个端点加：漏一个端点就等于漏一个"这是真数据"的误会。
        """
        response = await call_next(request)
        response.headers["X-CampusPath-Data"] = SYNTHETIC_NOTICE
        return response

    # ── SIS ─────────────────────────────────────────────────────────
    @app.get("/sis/students/{student_id}/course-records",
             response_model=list[StudentCourseRecord], tags=["SIS"])
    def course_records(student_id: str) -> list[StudentCourseRecord]:
        if student_id not in data.student_ids:
            raise HTTPException(404, f"未知学生 {student_id}")
        return data.course_records.get(student_id, [])

    @app.get("/sis/students", response_model=list[str], tags=["SIS"])
    def students() -> list[str]:
        """Demo Persona 列表。真实 SIS 不会有这个端点，Mock 需要它来做切换。"""
        return list(data.student_ids)

    # ── Degree Audit ────────────────────────────────────────────────
    @app.get("/degree-audit/programs/{program_id}/requirements",
             response_model=list[DegreeRequirement], tags=["Degree Audit"])
    def requirements(program_id: str) -> list[DegreeRequirement]:
        found = data.requirements.get(program_id)
        if not found:
            raise HTTPException(404, f"未知培养方案 {program_id}")
        return found

    # ── Course Catalog ──────────────────────────────────────────────
    @app.get("/catalog/courses", response_model=list[CourseCatalogItem], tags=["Catalog"])
    def catalog(
        subject: str | None = Query(None, description="学科代码，如 COMP"),
        limit: int = Query(500, ge=1, le=2000),
    ) -> list[CourseCatalogItem]:
        rows = data.catalog
        if subject:
            rows = [c for c in rows if c.subject == subject.upper()]
        return rows[:limit]

    @app.get("/catalog/courses/{course_id:path}",
             response_model=CourseCatalogItem, tags=["Catalog"])
    def course(course_id: str) -> CourseCatalogItem:
        for item in data.catalog:
            if item.course_id == course_id:
                return item
        raise HTTPException(404, f"未知课程 {course_id}")

    # ── Timetable ───────────────────────────────────────────────────
    @app.get("/timetable/offerings", response_model=list[CourseOffering], tags=["Timetable"])
    def offerings(
        term: str = Query(..., description="学期，如 2026-27_FALL"),
        course_id: str | None = None,
    ) -> list[CourseOffering]:
        rows = [o for o in data.offerings if o.term == term]
        if course_id:
            rows = [o for o in rows if o.course_id == course_id]
        return rows

    # ── Opportunity Sources ─────────────────────────────────────────
    @app.get("/opportunities", response_model=list[Opportunity], tags=["Opportunities"])
    def opportunities(
        source_id: str | None = None,
        limit: int = Query(500, ge=1, le=2000),
    ) -> list[Opportunity]:
        """**只返回已发布的**。草稿与被驳回的不在这里，也不该在（Spec §8.9.1）。"""
        rows = data.opportunities
        if source_id:
            rows = [o for o in rows if o.source_id == source_id]
        return rows[:limit]

    # ── Calendar Fixtures ───────────────────────────────────────────
    @app.get("/calendar/{student_id}/free-busy",
             response_model=list[BusyInterval], tags=["Calendar"])
    def free_busy(
        student_id: str,
        start: datetime,
        end: datetime,
        detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY,
    ) -> list[BusyInterval]:
        """按**被告知的层级**返回。

        参与人、地点、描述在任何层级都没有——接口里就没有那些字段，
        所以那部分的 B5 仍然是"没地方放"，不是"记得不要返回"。

        标题是二级授权放行的那一项，因此它有字段，但**默认参数是最小层级**：
        忘了传等于取最少。Mock 与真实 Provider 形状一致，是 Spec §11.4 的要求——
        否则 Demo 之后要重写调用方。

        ⚠️ 这一层**不判断学生授权了什么**。授权是 Profile 上的事实，
        由 CampusPath 的 API 层判定；校方系统不知道也不该知道
        学生在 CampusPath 里勾了什么。
        """
        if student_id not in data.student_ids:
            raise HTTPException(404, f"未知学生 {student_id}")
        rows = [
            interval for interval in data.busy.get(student_id, [])
            if interval.start < end and interval.end > start
        ]
        if detail_level is CalendarDetailLevel.EVENT_TITLES:
            return rows
        return [BusyInterval(start=r.start, end=r.end) for r in rows]

    # ── Source Health ───────────────────────────────────────────────
    @app.get("/ops/source-health", response_model=list[SourceHealth], tags=["Ops"])
    def health() -> list[SourceHealth]:
        """Spec §6.11 的八项运维指标。不展示任何原文或学生数据。"""
        return store.source_health(datetime.now(timezone.utc))

    @app.get("/healthz", tags=["Ops"])
    def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "contracts_version": CONTRACTS_VERSION,
            "seed_profile": data.profile_name,
            "as_of": data.as_of.date().isoformat(),
            "notice": SYNTHETIC_NOTICE,
        }

    return app


app = create_app()
