"""活动数据闭环测试（D 批，2026-08-02）。

签到 → 验证出勤自动回填 → 实时统计 → 周期报告（admin-only）→ 两月归档。
模型桩提供报告叙事；RBAC 越权分支逐条实测（用户裁定：报告只有
career_center_admin 有权限）。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


@pytest.fixture()
def deps() -> Deps:
    scripted = {f"quality-report:{p}": "中文结论段。<EN>English summary."
                for p in ("weekly", "monthly", "term", "year")}
    return Deps("full", model=ScriptedModel(scripted))


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def as_role(client: TestClient, role: ActorRole):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: role.value, **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


def _an_event(deps) -> str:
    """取一个**已经开始**的带反馈活动（签到从开始当天起计数——用户细化）。
    seed 活动多在未来：把第一个 OCC-EVT 活动的开始时间挪到昨天。"""
    index, opp = next(
        (i, o) for i, o in enumerate(deps.opportunities)
        if o.occurrence_id and o.occurrence_id.startswith("OCC-EVT"))
    if opp.starts_at is None or opp.starts_at > datetime.now(timezone.utc):
        deps.opportunities[index] = opp.model_copy(update={
            "starts_at": datetime.now(timezone.utc) - timedelta(days=1)})
    return opp.opportunity_id


def test_checkin_not_open_before_event_day(client, deps):
    """用户细化（2026-08-02）：活动开始当天前签到 → 409，不计数。"""
    admin = as_role(client, ActorRole.CAREER_CENTER_ADMIN)
    student = as_role(client, ActorRole.STUDENT)
    future = next(o for o in deps.opportunities
                  if o.starts_at and o.starts_at > datetime.now(timezone.utc))
    info = admin("GET",
                 f"/v1/ops/opportunities/{future.opportunity_id}/checkin").json()
    assert info["counting_open"] is False
    r = student("POST", "/v1/students/STU-A/checkin",
                json={"opportunity_id": future.opportunity_id,
                      "token": info["token"]})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "checkin_not_open"


def test_checkin_roundtrip_and_bad_token(client, deps):
    admin = as_role(client, ActorRole.CAREER_CENTER_ADMIN)
    student = as_role(client, ActorRole.STUDENT)
    opp = _an_event(deps)

    info = admin("GET", f"/v1/ops/opportunities/{opp}/checkin").json()
    assert info["token"].startswith("chk_")
    assert info["attend_count"] == 0
    assert opp in info["checkin_url"]

    r = student("POST", "/v1/students/STU-A/checkin",
                json={"opportunity_id": opp, "token": info["token"]})
    assert r.status_code == 200 and r.json()["attend_count"] == 1
    # 重复签到幂等（人数不翻倍）
    r = student("POST", "/v1/students/STU-A/checkin",
                json={"opportunity_id": opp, "token": info["token"]})
    assert r.json()["already_checked_in"] is True
    assert r.json()["attend_count"] == 1
    # 伪 token 422
    bad = student("POST", "/v1/students/STU-A/checkin",
                  json={"opportunity_id": opp, "token": "chk_" + "0" * 32})
    assert bad.status_code == 422


def test_checkin_backfills_verified_attendance(client, deps):
    student = as_role(client, ActorRole.STUDENT)
    admin = as_role(client, ActorRole.CAREER_CENTER_ADMIN)
    opp = _an_event(deps)
    token = admin("GET", f"/v1/ops/opportunities/{opp}/checkin").json()["token"]
    student("POST", "/v1/students/STU-A/checkin",
            json={"opportunity_id": opp, "token": token})
    r = student("POST", "/v1/students/STU-A/event-feedback", json={
        "subject_id": opp, "content_depth": 5, "practical_value": 4,
        "organization": 4, "expectation_match": 5,
        "fit": "good_fit", "attended_verified": False,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verified_attendance"] is True, "扫码过就该自动验证出勤"
    dims = {d["dimension"] for d in body["dimensions"]}
    assert "expectation_match" in dims, "第 4 维要进聚合载荷"


def test_quality_summary_rbac_and_content(client, deps):
    assert as_role(client, ActorRole.STUDENT)(
        "GET", "/v1/ops/opportunities/quality-summary").status_code == 403
    rows = as_role(client, ActorRole.CAREER_CENTER_ADMIN)(
        "GET", "/v1/ops/opportunities/quality-summary").json()
    assert len(rows) >= 5   # seed 有 6 个带反馈的 occurrence
    scored = [r for r in rows if r["avg_overall"] is not None]
    assert scored, "达到阈值的活动应有实时分数"
    for row in rows:
        if row["avg_overall"] is None:
            assert row["verified_n"] < 5 or row["feedback_n"] == 0


def test_quality_report_admin_only_and_lifecycle(client, deps):
    # 用户裁定：报告仅 career_center_admin——其余角色一律 403
    for role in (ActorRole.STUDENT, ActorRole.REVIEWER, ActorRole.CURATOR,
                 ActorRole.PUBLISHER):
        assert as_role(client, role)(
            "POST", "/v1/ops/quality-reports/monthly").status_code == 403, role

    admin = as_role(client, ActorRole.CAREER_CENTER_ADMIN)
    assert admin("GET", "/v1/ops/quality-reports/monthly").status_code == 404
    assert admin("POST", "/v1/ops/quality-reports/nonsense").status_code == 404

    job = admin("POST", "/v1/ops/quality-reports/year").json()
    assert job["state"] == "running"
    deadline = time.time() + 8
    while time.time() < deadline:
        body = admin("GET", "/v1/ops/quality-reports/year").json()
        if body["state"] != "running":
            break
        time.sleep(0.05)
    assert body["state"] == "done", body.get("error")
    report = body["report"]
    assert report["feedback_total"] >= 1
    assert report["by_organizer"], "主办方分组对比是报告核心段"
    assert report["by_type"]
    assert report["narrative"]["zh_Hans"].startswith("中文结论")
    assert report["data_notes"], "口径注不能省"
    # 抑制纪律：低于阈值的分组行不给分数
    for row in report["by_organizer"] + report["by_type"] + report["by_school"]:
        if row["verified_n"] < 5:
            assert row["avg_overall"] is None


def test_two_month_archive_view(client, deps):
    """结束超两月的活动：默认目录不出现，archive 视图出现，评分被拒收。"""
    student = as_role(client, ActorRole.STUDENT)
    admin = as_role(client, ActorRole.CAREER_CENTER_ADMIN)
    old = deps.opportunities[0].model_copy(update={
        "opportunity_id": "OPP-OLD-001",
        "occurrence_id": "OCC-OLD-001",
        "title": "三个月前的老活动",
        "ends_at": datetime.now(timezone.utc) - timedelta(days=90),
        "deadline": None,
    })
    deps.opportunities.append(old)
    live_ids = {o["opportunity_id"] for o in
                student("GET", "/v1/catalog/opportunities?limit=1000").json()}
    assert "OPP-OLD-001" not in live_ids
    archive = admin("GET", "/v1/catalog/opportunities?view=archive&limit=1000").json()
    assert "OPP-OLD-001" in {o["opportunity_id"] for o in archive}
    r = student("POST", "/v1/students/STU-A/event-feedback", json={
        "subject_id": "OPP-OLD-001", "content_depth": 5, "practical_value": 5,
        "organization": 5, "fit": "good_fit", "attended_verified": True,
    })
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "stats_frozen"


def test_quality_summary_covers_every_plaza_row(client, deps):
    """2026-08-04 用户报障：校方广场的四维统计区整块消失。旧实现把
    零反馈零签到的活动直接跳过——但统计位必须**常驻**：没反馈就如实
    显示 0 + Insufficient，不许"要先有学生反馈才配有统计区"。"""
    rows = as_role(client, ActorRole.CAREER_CENTER_ADMIN)(
        "GET", "/v1/ops/opportunities/quality-summary").json()
    ids = {r["opportunity_id"] for r in rows}
    plaza = [o.opportunity_id for o in deps.opportunities]
    missing = [oid for oid in plaza if oid not in ids]
    assert not missing, f"{len(missing)} 条广场活动没有统计行，如 {missing[:3]}"
    zero = next((r for r in rows if r["feedback_n"] == 0), None)
    assert zero is not None, "零反馈活动也要有统计行"
    assert zero["avg_overall"] is None and zero["verified_n"] == 0


def test_quality_summary_carries_dimension_and_fit_breakdown(client, deps):
    """2026-08-04 用户裁定：呈现不能只拼计数——学生评的是**四维分**
    （内容深度/实用收获/组织/预期兑现）外加**个人契合标签**（§17.4
    与质量分隔离）。汇总行必须把两者都带给校方端；契合分布与维度分
    同受 k-匿名阈值约束：verified < MIN_CELL_N 的行必须为空。"""
    rows = as_role(client, ActorRole.CAREER_CENTER_ADMIN)(
        "GET", "/v1/ops/opportunities/quality-summary").json()
    scored = [r for r in rows if r["avg_overall"] is not None]
    assert scored, "seed 有达阈值的活动"
    for row in scored:
        assert row["dimensions"], "达阈值必须带逐维分"
        assert row["fit_distribution"], "达阈值必须带契合分布"
        total = sum(s["share"] for s in row["fit_distribution"])
        # 份额各自四位舍入，和允许展示精度内的余差
        assert abs(total - 1.0) < 0.005, f"契合份额之和应≈1，得 {total}"
        for s in row["fit_distribution"]:
            assert s["fit"] in {"good_fit", "too_basic_for_me",
                                "too_advanced_for_me", "wrong_format_for_me",
                                "schedule_mismatch"}
    for row in rows:
        if row["avg_overall"] is None:
            assert row["fit_distribution"] == [], \
                "低于 k-匿名阈值不得输出契合分布（B9 同一条纪律）"
