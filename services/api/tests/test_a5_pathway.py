"""审计 E（2026-08-02）：A5 类本体接进线上 GET /pathway。

关键断言：模型可用且理由脚本就绪 → trigger=a5:<目标指纹>、每项带真凭据、
课程计划走 generate_course_plans、换目标自动重生成、已批准吸收项跨版本
携带；模型理由不可用 → 如实回落夹具（不冒充 A5）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

A5_SCRIPT = "\n".join([
    "OPP-EVT-001\t贴合主目标的沟通训练\tCommunication training for the goal",
    "overall\t优先近期可完成的差距闭环\tClose near-term gaps first",
])


@pytest.fixture()
def deps() -> Deps:
    d = Deps("full")
    d.model = ScriptedModel({"a5-pathway:STU-A": A5_SCRIPT,
                             "match_rationale:STU-A": "为目标补差距\tCloses a gap"})
    return d


def call(client, method, path, **kw):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


def test_pathway_is_a5_generated_when_model_available(deps):
    client = TestClient(create_app(deps))
    r = call(client, "GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["trigger"].startswith("a5:"), body["trigger"]
    assert body["plan_items"], "A5 路径必须有条目"
    assert all(i["validation_id"] for i in body["plan_items"]), "B8：每项带凭据"
    # 课程计划来自 generate_course_plans（balanced 变体）
    assert body["course_plan"] is not None
    assert body["course_plan"]["variant"] == "balanced"
    # 两次读取稳定（缓存，不重复生成）
    again = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert again["pathway_id"] == body["pathway_id"]


def test_goal_change_regenerates_pathway(deps):
    client = TestClient(create_app(deps))
    first = call(client, "GET", "/v1/students/STU-A/pathway").json()
    r = call(client, "POST", "/v1/students/STU-A/goals", json={
        "goal_id": "GOAL-STU-A-primary", "student_id": "STU-A",
        "role": "primary", "development_mode": "employment",
        "target_type": "role", "target_name": "游戏开发工程师",
        "horizon": "long_term", "created_at": "2026-09-15T09:00:00Z",
    })
    assert r.status_code == 200, r.text
    second = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert second["pathway_id"] != first["pathway_id"], "换目标必须重生成"
    assert second["version"] > first["version"]


def test_model_rationale_failure_falls_back_to_fixture():
    d = Deps("full")
    d.model = ScriptedModel({})      # a5 purpose 未预设 → 调用抛错
    client = TestClient(create_app(d))
    r = call(client, "GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 200, r.text
    assert r.json()["trigger"] == "demo_fixture", "拿不到模型就不冒充 A5"


def test_no_model_keeps_fixture_semantics():
    d = Deps("full")
    d.model = None
    client = TestClient(create_app(d))
    r = call(client, "GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 200
    assert r.json()["trigger"] == "demo_fixture"


def test_approved_items_survive_regeneration(deps):
    client = TestClient(create_app(deps))
    first = call(client, "GET", "/v1/students/STU-A/pathway").json()
    # 报名 + 批准一个机会（吸收进 pathway）
    opp = "OPP-EVT-039"
    call(client, "POST", "/v1/students/STU-A/actions", json={
        "event_id": f"AE-TEST-{opp}", "student_id": "STU-A",
        "action_type": "apply", "subject_id": opp,
        "occurred_at": "2026-09-15T09:00:00Z",
    })
    sp = call(client, "POST", "/v1/students/STU-A/schedule-proposals", json={
        "proposal_id": f"SP-{opp}", "student_id": "STU-A",
        "plan_item_ids": [f"PI-{opp}"],
        "proposed_slots": [{
            "plan_item_id": f"PI-{opp}",
            "span": {"start": "2026-10-25T14:59:00Z",
                     "end": "2026-10-25T17:59:00Z"},
            "conflicts": [],
        }],
        "student_decision": "pending",
    })
    assert sp.status_code == 200, sp.text
    ap = call(client, "POST", "/v1/students/STU-A/schedule-proposals", json={
        **sp.json(), "student_decision": "approved",
    })
    assert ap.status_code == 200, ap.text
    # 换目标 → 重生成 → 已批准条目仍在
    call(client, "POST", "/v1/students/STU-A/goals", json={
        "goal_id": "GOAL-STU-A-primary", "student_id": "STU-A",
        "role": "primary", "development_mode": "employment",
        "target_type": "role", "target_name": "游戏开发工程师",
        "horizon": "long_term", "created_at": "2026-09-15T09:00:00Z",
    })
    regenerated = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert regenerated["pathway_id"] != first["pathway_id"]
    assert any(i["subject_id"] == opp for i in regenerated["plan_items"]), \
        "已批准吸收的条目不许因重规划消失"


def test_near_term_overload_prefits_instead_of_failing(deps):
    """钉住修复循环的容量兜底：近两周档塞进多个 20h 活动（top8 里 4 个
    超载项）时，S2 循环逐轮砍分数最低者、在 3 轮上限内收敛——A5 仍然
    成功（trigger=a5:）且近两周机会负荷回到预算内，不许静默回落夹具。"""
    from datetime import datetime, timedelta, timezone

    soon = datetime.now(timezone.utc) + timedelta(days=3)
    doctored = []
    for i, o in enumerate(deps.opportunities[:40]):
        if i < 6:
            doctored.append(o.model_copy(update={
                "starts_at": soon, "ends_at": soon + timedelta(hours=3),
                "workload_hours_total": 20.0}))
        else:
            doctored.append(o)
    deps.opportunities = doctored + list(deps.opportunities[40:])
    client = TestClient(create_app(deps))
    body = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert body["trigger"].startswith("a5:"), \
        f"超载不该让 A5 整体失败回夹具，得到 {body['trigger']}"
    near_hours = sum(
        i["workload_hours"] for i in body["plan_items"]
        if i["kind"] == "opportunity"
        and i["date_range"]["start"] <= (datetime.now(timezone.utc)
                                         + timedelta(days=14)).date().isoformat())
    assert near_hours <= 30.0, f"近两周档 {near_hours}h 超预算"


def test_intensity_variant_is_user_selectable(deps):
    """Spec §8.1 S1 三档强度（2026-08-03 用户问出缺口）：三变体一直在后台
    生成，但用户选不了。钉住：GET /pathway?intensity= 按档出课程计划
    （low_load 2 门 / balanced 3 门 / ambitious 4 门），并按档独立缓存。"""
    client = TestClient(create_app(deps))
    counts = {}
    for variant, expect in (("low_load", 2), ("balanced", 3), ("ambitious", 4)):
        body = call(client, "GET",
                    f"/v1/students/STU-A/pathway?intensity={variant}").json()
        assert body["trigger"].startswith("a5:"), body["trigger"]
        cp = body["course_plan"]
        assert cp is not None and cp["variant"] == variant
        counts[variant] = len(cp["course_items"])
        again = call(client, "GET",
                     f"/v1/students/STU-A/pathway?intensity={variant}").json()
        assert again["pathway_id"] == body["pathway_id"]
    assert counts == {"low_load": 2, "balanced": 3, "ambitious": 4}


def test_course_plan_term_uses_academic_termcode(deps):
    """2026-08-03 用户报障的余波钉子：课程计划学期一律用教务 TermCode
    （deps.current_term）。历史：曾把学生自述的 y1s2 年级码塞进
    CoursePlanItem → 整页 500；用户随后裁定自述学期通道全部撤除，
    这里保留格式断言防止任何回归。"""
    client = TestClient(create_app(deps))
    body = call(client, "GET", "/v1/students/STU-A/pathway")
    assert body.status_code == 200, body.text
    parsed = body.json()
    assert parsed["trigger"].startswith("a5:"), parsed["trigger"]
    assert parsed["course_plan"] is not None
    import re as _re
    for item in parsed["course_plan"]["course_items"]:
        assert _re.fullmatch(r"\d{4}-\d{2}_(FALL|WINTER|SPRING|SUMMER)",
                             item["term"]), item["term"]


def test_unexpected_a5_exception_falls_back_and_negative_caches(deps, monkeypatch):
    """读端点不许 500（审查 M10 同一条纪律）：A5 生成抛**任何**异常都要
    回落夹具，且计入失败负缓存——否则每次 GET 都重烧模型再炸一遍。"""
    import campuspath_api.a5_pathway as a5mod

    calls = {"n": 0}

    def boom(*a, **k):
        calls["n"] += 1
        raise RuntimeError("boom")

    monkeypatch.setattr(a5mod, "build_a5_pathway", boom)
    client = TestClient(create_app(deps))
    r = call(client, "GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 200, r.text
    assert r.json()["trigger"] == "demo_fixture"
    call(client, "GET", "/v1/students/STU-A/pathway")
    assert calls["n"] == 1, "异常后必须进负缓存，不许每次读都重试"


def test_intensity_default_stays_balanced(deps):
    client = TestClient(create_app(deps))
    body = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert body["course_plan"]["variant"] == "balanced"


def test_intensity_scales_activity_plan_not_just_courses(deps):
    """用户裁定口径（2026-08-03 二改）：**近两周活动数上限 = 3/5/7**（进取
    两周 7 个已是极限），总活动池随档放大；课程门数 2/3/4 不变。近两周
    实际条目还受"两周内真有多少活动"限制——上限是天花板不是配额。
    为让上限可观测，把前 9 个机会都拍到 3 天后开始。"""
    from datetime import datetime, timedelta, timezone

    soon = datetime.now(timezone.utc) + timedelta(days=3)
    # 全量拍近两周：让上限成为唯一约束（假绿教训：只拍前 9 个可能
    # 进不了分数前列，断言碰巧通过什么也没证明）
    deps.opportunities = [
        o.model_copy(update={
            "starts_at": soon, "ends_at": soon + timedelta(hours=2),
            "workload_hours_total": 2.0})
        for o in deps.opportunities]
    client = TestClient(create_app(deps))
    near_counts, total_counts = {}, {}
    caps = {"low_load": 3, "balanced": 5, "ambitious": 7}
    for variant in ("low_load", "balanced", "ambitious"):
        body = call(client, "GET",
                    f"/v1/students/STU-A/pathway?intensity={variant}").json()
        assert body["trigger"].startswith("a5:")
        opp = [i for i in body["plan_items"] if i["kind"] == "opportunity"]
        near_cut = (datetime.now(timezone.utc) + timedelta(days=14))             .date().isoformat()
        near_counts[variant] = sum(
            1 for i in opp if i["date_range"]["start"] <= near_cut)
        total_counts[variant] = len(opp)
        assert near_counts[variant] <= caps[variant],             f"{variant} 近两周 {near_counts[variant]} 超上限 {caps[variant]}"
    assert near_counts["low_load"] < near_counts["ambitious"], near_counts
    assert total_counts["low_load"] <= total_counts["ambitious"], total_counts
