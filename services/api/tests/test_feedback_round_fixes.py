"""验收反馈批测试（2026-08-02 五批用户意见）。

覆盖：一键巡检任务、主/副目标推荐配额、成长曲线真实口径、
国际生计划项官方指引注入、批准无视非阻断冲突的 ⚠️ 持久化。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole
from campuspath_connector.fetcher import ProbeResult
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

from test_intl_pack_api import _enable


@pytest.fixture()
def deps() -> Deps:
    return Deps("full", model=None)


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def as_role(client: TestClient, role: str):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: role, **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


# ── C：一键巡检 ───────────────────────────────────────────────────────


def test_sources_sweep_runs_all_real_sources(client, deps, monkeypatch):
    import campuspath_api.app as app_module
    monkeypatch.setattr(app_module, "_SWEEP_DELAY", 0.0, raising=False)
    deps.probe_fn = lambda url, prev: ProbeResult(
        outcome="unchanged", new_hash="f" * 64)
    admin = as_role(client, ActorRole.CAREER_CENTER_ADMIN.value)
    r = admin("POST", "/v1/ops/sources/refresh-all")
    assert r.status_code == 200, r.text
    total = r.json()["total"]
    real_active = sum(1 for s in deps.registered_sources.values()
                      if s.is_real_fetch and s.status == "active")
    assert total == real_active >= 85   # 92 源 + IANG 繁中版 − 8 mock
    for _ in range(200):                 # 轮询到 done（探测是假的，秒级完成）
        job = admin("GET", "/v1/ops/sources/refresh-all").json()
        if job["state"] != "running":
            break
        time.sleep(0.05)
    assert job["state"] == "done", job
    assert job["done"] == total
    assert job["errors"] == 0
    # 全部源都有巡检痕迹
    checked = [s for s in deps.registered_sources.values()
               if s.is_real_fetch and s.last_checked_at is not None]
    assert len(checked) == total


def test_sources_sweep_forbidden_for_students(client):
    r = as_role(client, ActorRole.STUDENT.value)(
        "POST", "/v1/ops/sources/refresh-all")
    assert r.status_code == 403


# ── B（第 3 批）：主/副目标推荐配额 ──────────────────────────────────


def _add_candidate_goal(call, target="Data Analytics Competition"):
    r = call("POST", "/v1/students/STU-A/goals", json={
        "goal_id": "GOAL-CAND-T1", "student_id": "STU-A",
        "role": "candidate", "development_mode": "employment",
        "target_type": "role", "target_name": target,
        "horizon": "long_term", "confidence": 0.5, "status": "candidate",
        "alternatives": [], "created_at": "2026-08-02T00:00:00Z",
    })
    assert r.status_code == 200, r.text


def test_candidate_goal_gets_reserved_slots(client, deps):
    call = as_role(client, ActorRole.STUDENT.value)
    _add_candidate_goal(call)

    def hit_count(limit=10):
        rows = call("GET", f"/v1/students/STU-A/matches?limit={limit}").json()
        n = 0
        for m in rows:
            opp = next(o for o in deps.opportunities
                       if o.opportunity_id == m["opportunity_id"])
            words = {w for text in (opp.title, *opp.skills, *opp.category_tags)
                     for w in str(text).lower().replace("_", " ").split()}
            if words & {"data", "analytics", "competition"}:
                n += 1
        return n

    # share=0.4 → 10 席里至少 4 席给副目标相关（种子里比赛类充足）
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"candidate_goal_share": 0.4})
    assert r.status_code == 200, r.text
    assert deps.students["STU-A"].candidate_goal_share == 0.4
    high = hit_count()
    assert high >= 4, f"share=0.4 时副目标命中仅 {high}"
    # 配比改动即时生效（缓存作废）：降到 0.1 → 保底 1 席，命中数不增
    call("POST", "/v1/students/STU-A/profile/self-edit",
         json={"candidate_goal_share": 0.1})
    low = hit_count()
    assert low <= high
    assert low >= 1


# ── A（第 2 批）：成长曲线真实口径 ───────────────────────────────────


def test_growth_trajectory_counts_real_evidence(client, deps):
    call = as_role(client, ActorRole.STUDENT.value)
    r = call("GET", "/v1/students/STU-A/growth-trajectory")
    assert r.status_code == 200, r.text
    points = r.json()["points"]
    assert points
    # 口径：证据数 = EvidenceRecord.obtained_at 落入该学期的条目数
    expected = sum(1 for e in deps.evidence if e.student_id == "STU-A")
    assert sum(p["new_confirmed_evidence"] for p in points) == expected >= 1
    # 已关闭差距维持 0（判定链未接入，宁缺毋假；前端不展示）
    assert all(p["gaps_closed"] == 0 for p in points)


# ── A（第 4 批）：国际生计划项官方指引 ───────────────────────────────


def test_intl_plan_items_carry_official_guidance(client, deps):
    call = as_role(client, ActorRole.STUDENT.value)
    _enable(call)
    items = call("GET", "/v1/students/STU-A/pathway").json()["plan_items"]
    intl = {i["plan_item_id"]: i for i in items
            if i["plan_item_id"].startswith("PI-INTL-")}
    assert intl
    joined = {pid: " ".join(a["zh_Hans"] for a in item["assumptions"])
              for pid, item in intl.items()}
    # IANG 确认动作 → 入境处官方链接（含用户指定的繁中版所在域）
    iang = next(v for k, v in joined.items() if k.startswith("PI-INTL-CONFIRM"))
    assert "官方指引" in iang and "immd.gov.hk" in iang, iang
    # 毕业时间核实 → 教务处链接
    grad = next((v for k, v in joined.items()
                 if "graduation" in intl[k]["subject_id"]), None)
    assert grad is not None and "registry.hkust.edu.hk" in grad, grad


# ── B（第 2 批）：无视非阻断冲突批准 → ⚠️ 持久化 ─────────────────────


def test_soft_conflict_approval_marks_item(client, deps):
    call = as_role(client, ActorRole.STUDENT.value)
    # 找一个 STU-A 的普通忙碌块，把提案时段压上去（非阻断冲突）
    busy = next(b for b in deps.availability
                if b.student_id == "STU-A" and b.type.value == "busy")
    opp = deps.opportunities[0]
    proposal = {
        "proposal_id": f"SP-SOFT-{opp.opportunity_id}",
        "student_id": "STU-A",
        "plan_item_ids": [f"PI-SOFT-{opp.opportunity_id}"],
        "proposed_slots": [{
            "plan_item_id": f"PI-SOFT-{opp.opportunity_id}",
            "span": {"start": busy.span.start.isoformat().replace("+00:00", "Z"),
                     "end": busy.span.end.isoformat().replace("+00:00", "Z")},
            "conflicts": [],
        }],
        "assumptions": [], "student_decision": "approved",
        "calendar_action_ids": [],
    }
    r = call("POST", "/v1/students/STU-A/schedule-proposals", json=proposal)
    assert r.status_code == 200, r.text
    conflicts = [c for s in r.json()["proposed_slots"] for c in s["conflicts"]]
    assert conflicts and all(not c["blocking"] for c in conflicts)
    item = next(i for i in call("GET", "/v1/students/STU-A/pathway")
                .json()["plan_items"]
                if i["subject_id"] == opp.opportunity_id)
    assert item["title"]["zh_Hans"].startswith("⚠️"), item["title"]


# ── 日历两报障（2026-08-02 第 7 批）───────────────────────────────────


def test_routine_sleep_covers_first_morning(client, deps):
    """跨午夜睡眠窗必须从 period_start 前一晚开始生成——
    否则首日 00:00–07:30 的凌晨睡眠在日历上是空白（用户截图报障）。"""
    call = as_role(client, ActorRole.STUDENT.value)
    r = call("POST", "/v1/students/STU-A/routine", json={
        "sleep": {"start": "23:00", "end": "07:30"},
        "meals": [{"start": "12:00", "end": "13:00"}],
    })
    assert r.status_code == 200, r.text
    period_start = deps.snapshots["STU-A"][0].period_start
    lead_day = (period_start - __import__("datetime").timedelta(days=1)).isoformat()
    lead = [b for b in deps.availability
            if b.block_id == f"AB-STU-A-routine-sleep-{lead_day}"]
    assert lead, "缺少 period_start 前一晚的睡眠块"
    assert lead[0].span.end.date() == period_start   # 覆盖首日凌晨
    # H5 反例：三餐（不跨午夜）不生成前一晚的块
    assert not [b for b in deps.availability
                if b.block_id == f"AB-STU-A-routine-meal0-{lead_day}"]


def test_fixture_opportunity_items_use_real_event_dates(client, deps):
    """机会类计划项日期 = 活动真实起止——「未来两周」标签与日历必须同一口径
    （用户报障：标签里列 11 月活动，日历这两周当然找不到）。"""
    call = as_role(client, ActorRole.STUDENT.value)
    items = call("GET", "/v1/students/STU-A/pathway").json()["plan_items"]
    checked = 0
    for item in items:
        if item["kind"] != "opportunity":
            continue
        opp = next((o for o in deps.opportunities
                    if o.opportunity_id == item["subject_id"]), None)
        if opp is None or opp.starts_at is None:
            continue
        checked += 1
        assert item["date_range"]["start"] == opp.starts_at.date().isoformat(), item
        if opp.ends_at is not None:
            assert item["date_range"]["end"] == opp.ends_at.date().isoformat(), item
    assert checked >= 1, "夹具里没有带真实时间的机会条目可验"


# ── B（第 8 批）：命中编制库的岗位不叠加现场拆解残留 ────────────────


def _post_goal(call, goal_id, target, role="candidate"):
    r = call("POST", "/v1/students/STU-A/goals", json={
        "goal_id": goal_id, "student_id": "STU-A", "role": role,
        "development_mode": "employment", "target_type": "role",
        "target_name": target, "horizon": "long_term", "confidence": 0.5,
        "status": "candidate" if role == "candidate" else "active",
        "alternatives": [], "created_at": "2026-08-02T00:00:00Z",
    })
    assert r.status_code == 200, r.text


def test_matched_role_drops_stale_live_research(client, deps):
    """审计红-2 后半（2026-08-02 用户裁定，取代此前「命中即丢弃残留」）：
    编制画像只是缓存——学生显式现场拆解过的岗位，live 结果**取代**编制
    facets（原关切「两种口径不混排」仍然成立：编制的市场证据 facets 必须
    全部让位，不残留混排）；未命中岗位照常并入（H5 双向）。"""
    from campuspath_contracts.goals import (
        DecompositionResearchJob, RequirementCategory, RequirementFacet)
    from campuspath_contracts.common import LocalizedText

    call = as_role(client, ActorRole.STUDENT.value)
    live_facet = RequirementFacet(
        category=RequirementCategory.TECHNICAL_SKILL, kind="hard",
        description=LocalizedText(zh_Hans="现场拆解残留项", en="live leftover"),
        evidence_sources=(), origin="ai_live",
    )

    def fake_job(goal_id):
        return DecompositionResearchJob(
            job_id=f"RJ-{goal_id}", student_id="STU-A", goal_id=goal_id,
            state="done", progress=100,
            stage=LocalizedText(zh_Hans="完成", en="done"),
            started_at="2026-08-02T00:00:00Z", daily_remaining=1,
            finished_at="2026-08-02T00:01:00Z",
            facets=(live_facet,),
        )

    _post_goal(call, "GOAL-SWE-T2", "软件工程师（后端）")
    deps.research_jobs[("STU-A", "GOAL-SWE-T2")] = fake_job("GOAL-SWE-T2")
    d = call("GET", "/v1/students/STU-A/goals/GOAL-SWE-T2/decomposition").json()
    assert any(f.get("origin") == "ai_live" for f in d["facets"]), \
        "显式现场拆解的结果必须生效"
    assert not any(f.get("origin") != "ai_live" and f.get("market_note")
                   for f in d["facets"]), \
        "编制画像的市场证据 facets 必须被 live 取代——两种口径不许混排"

    _post_goal(call, "GOAL-NOHIT-T1", "Marine Biologist")   # 编制库外
    deps.research_jobs[("STU-A", "GOAL-NOHIT-T1")] = fake_job("GOAL-NOHIT-T1")
    d2 = call("GET", "/v1/students/STU-A/goals/GOAL-NOHIT-T1/decomposition").json()
    assert d2["role_profile"] is None
    assert any(f.get("origin") == "ai_live" for f in d2["facets"]), \
        "未命中岗位的现场结果应并入"
