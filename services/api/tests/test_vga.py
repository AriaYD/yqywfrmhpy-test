"""北极星指标 VGA 落地（2026-08-04 用户指令，Spec §17.1）。

定义：学生真实完成、且经证据或反思证明产生价值的行动数。不奖励点击、
收藏、报名或忙碌本身。生产者 = 反思闭环（行动+证据齐备的唯一确定性链）：
反思 OPP → 铸 EV-REFL 证据 → 同步铸 verified_growth=True 的 ActionEvent。
汇总端点按事件时间戳逐月分桶；0 是事实不是 404。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


def call(client, method, path, **kw):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


@pytest.fixture()
def deps() -> Deps:
    return Deps("full")          # 无模型：VGA 全链零 LLM，必须照常工作


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def _reflect(client, rid: str, subject: str):
    return call(client, "POST", "/v1/students/STU-A/reflections", json={
        "reflection_id": rid, "student_id": "STU-A", "subject_id": subject,
        "personal_learning": "访谈里学会了追问",
        "created_at": "2026-09-15T09:00:00Z",
    })


def test_reflection_on_activity_mints_vga_event(client, deps):
    assert _reflect(client, "REFL-VGA-1", "OPP-EVT-001").status_code == 200
    vga = [a for a in deps.actions.get("STU-A", [])
           if a.verified_growth]
    assert len(vga) == 1
    event = vga[0]
    assert event.subject_id == "OPP-EVT-001"
    assert event.evidence_ids, "VGA 事件必须挂证据（契约校验器口径）"
    assert event.evidence_ids[0].startswith("EV-REFL-")


def test_same_reflection_twice_counts_once(client, deps):
    _reflect(client, "REFL-VGA-2", "OPP-EVT-001")
    _reflect(client, "REFL-VGA-2", "OPP-EVT-001")
    vga = [a for a in deps.actions.get("STU-A", [])
           if a.verified_growth]
    assert len(vga) == 1, "同一条反思重复提交不许重复计入 VGA"


def test_course_reflection_does_not_mint_vga(client, deps):
    _reflect(client, "REFL-VGA-3", "COMP 1021")
    assert not [a for a in deps.actions.get("STU-A", [])
                if a.verified_growth]


def test_vga_summary_buckets_by_month(client, deps):
    """两个月份各一条 → months 两桶、total=2、本月计数只含本月。"""
    from datetime import datetime, timezone

    from campuspath_contracts.pathway import ActionEvent, ActionType

    now = datetime.now(timezone.utc)
    old = now.replace(year=now.year - 1)
    for i, ts in enumerate((now, old)):
        deps.actions.setdefault("STU-A", []).append(ActionEvent(
            event_id=f"ACT-VGA-DOCTOR-{i}", student_id="STU-A",
            action_type=ActionType.COMPLETE, subject_id="OPP-EVT-001",
            timestamp=ts, evidence_ids=("EV-DOCTOR-1",),
            verified_growth=True))
    body = call(client, "GET", "/v1/students/STU-A/vga-summary")
    assert body.status_code == 200, body.text
    data = body.json()
    assert data["total_count"] == 2
    assert data["current_month"] == now.strftime("%Y-%m")
    assert data["current_month_count"] == 1
    months = {m["month"]: m["count"] for m in data["months"]}
    assert months == {now.strftime("%Y-%m"): 1, old.strftime("%Y-%m"): 1}


def test_vga_summary_zero_is_a_fact_not_404(client):
    body = call(client, "GET", "/v1/students/STU-A/vga-summary")
    assert body.status_code == 200
    data = body.json()
    assert data["total_count"] == 0
    assert data["months"] == []
