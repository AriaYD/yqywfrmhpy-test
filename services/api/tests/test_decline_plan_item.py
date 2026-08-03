"""「不参加」垃圾桶（2026-08-03 用户需求 B）：课外规划里的活动条目可删。

语义钉死：删除 = ①从当前规划版本移除（含里程碑引用）②留 DECLINE 审计
事件（append-only，B3 口径）③已写入的日历真实块一并移除 ④记入拒绝名单，
**A5 重新生成不复活**。未知条目 404。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


def call(client, method, path, **kw):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


@pytest.fixture()
def deps() -> Deps:
    d = Deps("full", model=ScriptedModel({
        "a5-pathway:STU-A": "overall\t取舍思路\tOverall",
        "match_rationale:STU-A": "契合\tFits",
    }))
    return d


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def _first_opportunity_item(client) -> dict:
    body = call(client, "GET", "/v1/students/STU-A/pathway").json()
    item = next(i for i in body["plan_items"] if i["kind"] == "opportunity")
    return item


def test_decline_removes_item_blocks_and_leaves_audit(client, deps):
    item = _first_opportunity_item(client)
    pid, subject = item["plan_item_id"], item["subject_id"]
    # 预置一块"已批准写入"的日历真实块——删除必须连它一起收走
    from campuspath_contracts.calendar import AvailabilityBlock
    block = AvailabilityBlock.model_validate({
        "block_id": f"AB-STU-A-plan-{subject}-PI-{subject}",
        "student_id": "STU-A", "type": "busy",
        "span": {"start": "2026-10-25T14:59:00Z", "end": "2026-10-25T17:59:00Z"},
        "source": "student_defined", "detail_level": "event_titles",
        "title": "测试活动块",
    })
    deps.availability.append(block)

    r = call(client, "DELETE", f"/v1/students/STU-A/pathway/items/{pid}")
    assert r.status_code == 200, r.text

    after = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert pid not in [i["plan_item_id"] for i in after["plan_items"]]
    assert all(pid not in m["plan_item_ids"] for m in after["milestones"])
    assert not any(b.block_id == block.block_id for b in deps.availability), \
        "已写入的日历块必须一并移除"
    events = call(client, "GET", "/v1/students/STU-A/actions").json()
    assert any(e["action_type"] == "decline" and e["subject_id"] == subject
               for e in events), "拒绝要留审计事件"


def test_declined_subject_does_not_resurrect_on_regeneration(client):
    item = _first_opportunity_item(client)
    subject = item["subject_id"]
    call(client, "DELETE",
         f"/v1/students/STU-A/pathway/items/{item['plan_item_id']}")
    # 换目标触发 A5 重新生成——被拒的活动不许回来
    call(client, "POST", "/v1/students/STU-A/goals", json={
        "goal_id": "GOAL-STU-A-primary", "student_id": "STU-A",
        "role": "primary", "development_mode": "employment",
        "target_type": "role", "target_name": "数据可视化工程师",
        "horizon": "long_term", "created_at": "2026-09-15T09:00:00Z",
    })
    regen = call(client, "GET", "/v1/students/STU-A/pathway").json()
    assert regen["trigger"].startswith("a5:")
    assert subject not in [i["subject_id"] for i in regen["plan_items"]], \
        "A5 重新生成把被拒活动复活了"


def test_decline_unknown_item_404(client):
    r = call(client, "DELETE", "/v1/students/STU-A/pathway/items/PI-NOPE")
    assert r.status_code == 404
