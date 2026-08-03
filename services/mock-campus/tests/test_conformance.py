"""WP4 验收：Mock 服务的形状与 WP1 契约一致，且逐个端点跑得通。

Spec §11.4 的原话是"必须使用与未来真实适配器相同的 Schema 和接口，
**避免 Demo 后全部重写**"。所以这里断言的不是"字段差不多"，
而是响应类型**就是**契约里的那个类——一个长得像的 Mock DTO 会在换真适配器时
把调用方全部拖下水。
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import campuspath_contracts
from campuspath_contracts.academic import (
    CourseCatalogItem,
    CourseOffering,
    DegreeRequirement,
    StudentCourseRecord,
)
from campuspath_contracts.opportunity import Opportunity, PublicationStatus
from campuspath_contracts.calendar import CalendarDetailLevel
from campuspath_contracts.publishing import SourceHealth
from campuspath_connector.adapters import BusyInterval, EducationDataAdapter

from campuspath_mock_campus.app import SYNTHETIC_NOTICE, create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app("full"))


@pytest.fixture(scope="module")
def student(client: TestClient) -> str:
    return client.get("/sis/students").json()[0]


# --------------------------------------------------------------------------
# 形状：响应类型必须就是契约模型
# --------------------------------------------------------------------------

_EXPECTED_RESPONSE_MODELS = {
    "/sis/students/{student_id}/course-records": StudentCourseRecord,
    "/degree-audit/programs/{program_id}/requirements": DegreeRequirement,
    "/catalog/courses": CourseCatalogItem,
    # `:path` 转换器：HKUST 的课程代码带空格（"COMP 2011"）
    "/catalog/courses/{course_id:path}": CourseCatalogItem,
    "/timetable/offerings": CourseOffering,
    "/opportunities": Opportunity,
    "/calendar/{student_id}/free-busy": BusyInterval,
    "/ops/source-health": SourceHealth,
}


def test_every_endpoint_returns_a_contract_type():
    app = create_app("tiny")
    seen: dict[str, object] = {}
    for route in app.routes:
        model = getattr(route, "response_model", None)
        if model is None:
            continue
        inner = getattr(model, "__args__", (model,))[0]
        seen[route.path] = inner

    for path, expected in _EXPECTED_RESPONSE_MODELS.items():
        assert seen.get(path) is expected, f"{path} 的响应类型不是 {expected.__name__}"


def test_contract_types_come_from_the_contracts_package():
    """防的是"抄一份长得一样的 DTO"——那样契约变更不会传导到这里。"""
    for path, model in _EXPECTED_RESPONSE_MODELS.items():
        module = model.__module__
        assert module.startswith(("campuspath_contracts", "campuspath_connector")), (
            f"{path} 用的是 {module} 里的类型，不是契约层的"
        )


def test_free_busy_carries_nothing_beyond_the_title():
    """B5 现在的形态：采集不得超出授权层级。

    标题是二级放行的那一项，所以有字段；参与人、地点、描述从来没被授权过，
    连字段都不存在——那部分仍然是"没地方放"。
    """
    fields = set(BusyInterval.__dataclass_fields__)
    assert fields == {"start", "end", "title"}
    for forbidden in ("attendees", "location", "description", "organizer"):
        assert forbidden not in fields


def test_free_busy_has_no_detail_query_parameters():
    app = create_app("tiny")
    route = next(r for r in app.routes
                 if getattr(r, "path", "") == "/calendar/{student_id}/free-busy")
    params = inspect.signature(route.endpoint).parameters
    assert set(params) == {"student_id", "start", "end", "detail_level"}, (
        f"free-busy 的参数集变了：{set(params)}——"
        "多出来的任何一个都可能是新的采集入口"
    )
    # 默认值必须站在**最小采集**那一边：忘了传 = 取最少
    assert params["detail_level"].default is CalendarDetailLevel.FREE_BUSY_ONLY


def test_education_adapter_protocol_is_satisfiable_by_these_endpoints():
    """接口形状要和 ``EducationDataAdapter`` 对得上，换真适配器才不用改调用方。"""
    required = {"course_records", "degree_requirements", "catalog", "offerings"}
    assert required <= {m for m in dir(EducationDataAdapter) if not m.startswith("_")}


# --------------------------------------------------------------------------
# 行为：逐个端点跑通
# --------------------------------------------------------------------------


def test_healthz_reports_the_contract_version(client: TestClient):
    body = client.get("/healthz").json()
    assert body["contracts_version"] == campuspath_contracts.CONTRACTS_VERSION
    assert body["notice"] == SYNTHETIC_NOTICE


def test_every_response_is_marked_synthetic(client: TestClient, student: str):
    """D1 要求全站标记。放中间件里，漏一个端点就等于漏一个误会。"""
    for path in ("/healthz", "/sis/students", "/catalog/courses?limit=1",
                 f"/sis/students/{student}/course-records", "/ops/source-health"):
        response = client.get(path)
        assert response.headers["X-CampusPath-Data"] == SYNTHETIC_NOTICE, path


def test_course_records_round_trip_through_the_contract(client: TestClient, student: str):
    rows = client.get(f"/sis/students/{student}/course-records").json()
    assert rows
    # 反序列化回契约模型：字段名或类型有偏差，这里就会炸
    parsed = [StudentCourseRecord(**r) for r in rows]
    assert all(p.student_id == student for p in parsed)


def test_unknown_student_is_404_not_empty_list(client: TestClient):
    """空列表会让调用方以为"这个学生没有选课"，而不是"没有这个学生"。"""
    assert client.get("/sis/students/STU-NOBODY/course-records").status_code == 404


def test_catalog_keeps_real_prerequisite_expressions(client: TestClient):
    rows = [CourseCatalogItem(**c) for c in client.get("/catalog/courses").json()]
    expressions = [c.prerequisite_expression for c in rows if c.prerequisite_expression]
    assert any(" AND " in e for e in expressions)
    assert any(" OR " in e for e in expressions)


def test_catalog_filters_by_subject(client: TestClient):
    rows = client.get("/catalog/courses?subject=comp").json()
    assert rows and all(c["subject"] == "COMP" for c in rows)


def test_course_lookup_handles_the_space_in_hkust_codes(client: TestClient):
    """HKUST 课程代码带空格（``COMP 2011``），路径参数必须收得下。"""
    response = client.get("/catalog/courses/COMP 2011")
    assert response.status_code == 200
    assert response.json()["course_id"] == "COMP 2011"


def test_offerings_require_a_term(client: TestClient):
    assert client.get("/timetable/offerings").status_code == 422


def test_offerings_are_scoped_to_the_term(client: TestClient):
    rows = client.get("/timetable/offerings?term=2026-27_FALL").json()
    assert rows and all(o["term"] == "2026-27_FALL" for o in rows)


def test_only_published_opportunities_are_served(client: TestClient):
    """草稿与被驳回的不该出现在这里，也不该进任何学生上下文（§8.9.1）。"""
    rows = client.get("/opportunities").json()
    assert rows
    assert all(o["publication_status"] == PublicationStatus.PUBLISHED.value for o in rows)


def test_free_busy_is_windowed(client: TestClient, student: str):
    start = datetime(2026, 9, 14, tzinfo=timezone.utc)
    end = start + timedelta(days=2)
    rows = client.get(
        f"/calendar/{student}/free-busy",
        params={"start": start.isoformat(), "end": end.isoformat()},
    ).json()
    for row in rows:
        # 没传 detail_level → 标题必须是 None（字段在，值不给）
        assert set(row) == {"start", "end", "title"}, (
            f"free-busy 返回了额外字段：{set(row)}"
        )
        assert row["title"] is None
        assert datetime.fromisoformat(row["start"]) < end
        assert datetime.fromisoformat(row["end"]) > start


def test_source_health_reports_all_eight_metrics(client: TestClient):
    rows = [SourceHealth(**h) for h in client.get("/ops/source-health").json()]
    assert len(rows) >= 6
    for row in rows:
        for field in ("parse_success_rate", "broken_link_rate", "schema_coverage_rate",
                      "deadline_consistency_issues", "duplicate_conflict_signals",
                      "fetch_auth_status"):
            assert getattr(row, field) is not None


def test_at_least_one_source_is_unhealthy(client: TestClient):
    """面板全绿的话，没人知道它到底会不会变红。"""
    from campuspath_connector.adapters import needs_human_attention

    rows = [SourceHealth(**h) for h in client.get("/ops/source-health").json()]
    assert any(needs_human_attention(r) for r in rows)


def test_source_health_exposes_no_content(client: TestClient):
    body = client.get("/ops/source-health").json()
    blob = str(body).lower()
    for leak in ("student", "title", "reflection", "calendar", "email"):
        assert leak not in blob, f"Source Health 泄露了 {leak}"


# --------------------------------------------------------------------------
# OpenAPI 文档（WP4 验收条款）
# --------------------------------------------------------------------------


def test_openapi_document_is_generated(client: TestClient):
    document = client.get("/openapi.json").json()
    assert document["info"]["version"] == campuspath_contracts.CONTRACTS_VERSION
    assert "/sis/students/{student_id}/course-records" in document["paths"]


def test_openapi_schemas_are_named_after_contract_models(client: TestClient):
    schemas = client.get("/openapi.json").json()["components"]["schemas"]
    for name in ("StudentCourseRecord", "CourseCatalogItem", "CourseOffering",
                 "DegreeRequirement", "Opportunity", "SourceHealth", "BusyInterval"):
        assert name in schemas, f"OpenAPI 里没有 {name}——说明用了别的类型"
