"""每个契约端点都被真实调用一次，并且**调用两次**。

这条测试是 2026-07-30 两个 bug 的直接产物：

* `why-not-recommended` 缺一个 import，真实调用直接 500——
  而当时 31 项测试全绿，因为**没有一条测试调过那个端点**。
  覆盖率不是测试数量，是"每个对外入口至少被真实调用过一次"。
* 同一个端点**第二次**调用也炸（确定性 id 与每次变化的时间戳冲突）。
  只调一次的测试永远发现不了重放问题。

所以这里做两件事：遍历契约里的每一个端点，各调两次，断言**没有 5xx**。
业务正确性由各自的专项测试负责；这条只负责"它真的能被调用"。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole
from campuspath_contracts.openapi import API_ENDPOINTS

from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)

#: 路径参数与查询参数的可用取值。用 Seed 里真实存在的 id，
#: 这样 404 就真的意味着"端点坏了"，而不是"我编了个不存在的 id"。
PATH_VALUES = {
    "student_id": "STU-A",
    "proposal_id": "PROP-DEMO",
    "validation_id": "val_" + "0" * 32,
    "opportunity_id": "OPP-INT-001",
    "submission_id": "SUB-001",
    "memory_id": "MEM-STU-A-001",
}

#: 个别端点需要不同的路径取值：删除数据是**真的删**，
#: 用一个其他测试不依赖的精简学生当靶子，别把 STU-A 从世界上抹掉。
PATH_OVERRIDES: dict[str, dict[str, str]] = {
    "/v1/students/{student_id}/deletion-request": {"student_id": "STU-L"},
}

QUERY_VALUES = {
    "/v1/catalog/opportunities/{opportunity_id}/why-not-recommended": {
        "student_id": "STU-A"
    },
    "/v1/students/{student_id}/profile/proposals/{proposal_id}/decision": {
        "decision": "confirmed"
    },
}

#: POST 的最小请求体。刻意用**契约模型能接受的最小合法值**——
#: 目的是走到 handler，不是测业务逻辑。
def _bodies() -> dict[str, dict]:
    provenance = {"source": "s", "retrieved_at": "2026-09-15T09:00:00Z",
                  "parser_version": "t"}
    opportunity = {
        "opportunity_id": "OPP-NEW", "type": "workshop", "title": "工作坊",
        "organizer": "ORG-career-center",
        "official_url": "https://example.invalid/w", "source_id": "SRC-1",
        "provenance": provenance, "publication_status": "draft",
    }
    return {
        "/v1/students/{student_id}/profile/proposals": {
            "proposal_id": "PROP-DEMO", "student_id": "STU-A",
            "proposed_changes": [{"entity_type": "skill", "operation": "add",
                                  "field_path": "skills[]", "new_value": "x"}],
            "reason": "demo", "status": "pending",
            "created_at": "2026-09-15T09:00:00Z",
        },
        "/v1/students/{student_id}/profile/proposals/{proposal_id}/decision": {},
        "/v1/students/{student_id}/pathway": {
            "pathway_id": "PV", "student_id": "STU-A", "version": 1,
            "created_at": "2026-09-15T09:00:00Z", "trigger": "t",
            "horizons": ["this_term"], "plan_items": [],
        },
        "/v1/students/{student_id}/schedule-proposals": {
            "proposal_id": "SP", "student_id": "STU-A", "student_decision": "pending",
        },
        "/v1/students/{student_id}/calendar-actions": {
            "action_id": "CA", "student_id": "STU-A", "provider": "fixture",
            "action": "create",
            "draft": {"event_title": "复习",
                      "span": {"start": "2026-09-16T19:00:00Z",
                               "end": "2026-09-16T21:00:00Z"}},
            "idempotency_key": "idem-0001", "approval_receipt_id": "RCPT-1",
        },
        "/v1/students/{student_id}/actions": {
            "event_id": "AE", "student_id": "STU-A", "action_type": "save",
            "subject_id": "OPP-INT-001", "timestamp": "2026-09-15T09:00:00Z",
        },
        "/v1/students/{student_id}/reflections": {
            "reflection_id": "R", "student_id": "STU-A", "subject_id": "OPP-INT-001",
            "created_at": "2026-09-15T09:00:00Z",
        },
        "/v1/students/{student_id}/memory/recall": {
            "student_id": "STU-A", "task_context": "推荐 活动", "top_k": 3,
        },
        "/v1/students/{student_id}/wellbeing/outreach": {
            "request_id": "REQ", "consent_id": "CONSENT-DEMO", "student_id": "STU-B",
            "trigger_category": "capacity_overload",
            "email_fields": {
                "internal_student_ref": "ref", "student_requested_contact": True,
                "trigger_category": "capacity_overload",
                "triggered_at": "2026-09-15T09:00:00Z",
                "consent_receipt_id": "CONSENT-DEMO",
                "acknowledgement_url": "https://example.invalid/ack",
            },
            "requested_at": "2026-09-15T09:00:00Z",
        },
        "/v1/students/{student_id}/goals": {
            "goal_id": "GOAL-NEW", "student_id": "STU-A", "role": "candidate",
            "development_mode": "employment", "target_type": "role",
            "target_name": "Backend Engineer",
            "created_at": "2026-09-15T09:00:00Z",
        },
        "/v1/students/{student_id}/replan-preview": {
            "student_id": "STU-A",
            "trigger_type": "student_added_opportunity",
            "source": "OPP-INT-001",
            "detected_at": "2026-09-15T09:00:00Z",
        },
        "/v1/rules/validate": {"entity_type": "course", "entity_id": "COMP 1021"},
        "/v1/students/{student_id}/memory/{memory_id}/correction": {
            "memory_id": "MEM-STU-A-001",
            "corrected_content": "其实我只是不喜欢超过两小时的讲座",
        },
        "/v1/publisher/submissions": {
            "submission_id": "SUB-NEW", "owner_principal_id": "PUB-ORG-career-center",
            "organization_id": "ORG-career-center", "draft_version": 1,
            "content": opportunity, "category_tags": ["workshop"], "status": "draft",
        },
        "/v1/review/submissions/{submission_id}/decisions": {
            "decision_id": "MOD", "submission_id": "SUB-001", "submission_version": 1,
            "reviewer_id": "PUB-ORG-career-center", "decision": "approve",
            "reasons": [{"zh_Hans": "通过", "en": "approved"}],
            "timestamp": "2026-09-15T09:00:00Z",
        },
        "/v1/ops/opportunity-drafts": {
            "draft_id": "D", "source_id": "SRC-1", "extracted": opportunity,
            "provenance": provenance,
        },
    }


@pytest.fixture(scope="module")
def client() -> TestClient:
    deps = Deps("full")
    # 巡检类端点在本 harness 里不许真的出网：探测打桩 + 零礼貌间隔。
    # 这条 harness 只回答"入口通不通"，不做真实抓取。
    from campuspath_connector.fetcher import ProbeResult
    import campuspath_api.app as app_module
    app_module._SWEEP_DELAY = 0.0
    deps.probe_fn = lambda url, prev: ProbeResult(outcome="unchanged",
                                                  new_hash="0" * 64)
    return TestClient(create_app(deps))


def _fill(path: str) -> str:
    filled = path
    values = {**PATH_VALUES, **PATH_OVERRIDES.get(path, {})}
    for name, value in values.items():
        filled = filled.replace("{" + name + "}", value)
    return filled


@pytest.mark.parametrize(
    "endpoint", API_ENDPOINTS,
    ids=[f"{e.method} {e.path}" for e in API_ENDPOINTS],
)
def test_endpoint_can_actually_be_called_twice(client: TestClient, endpoint):
    """真实调用两次，断言没有 5xx（503 除外——那是"依赖不可用"，不是坏）。

    不检查业务正确性，那是各自专项测试的事。这条只回答一个问题：
    **这个入口真的通吗，而且通第二次吗。**
    """
    url = _fill(endpoint.path)
    headers = {ROLE_HEADER: endpoint.roles[0].value}
    body = _bodies().get(endpoint.path)
    params = QUERY_VALUES.get(endpoint.path)

    seen: list[int] = []
    for _ in range(2):
        response = client.request(
            endpoint.method, url, headers=headers, json=body, params=params
        )
        seen.append(response.status_code)
        assert response.status_code != 500, (
            f"{endpoint.method} {url} 返回 500：\n{response.text[:400]}"
        )
        assert response.status_code < 500 or response.status_code == 503, (
            f"{endpoint.method} {url} 返回 {response.status_code}"
        )

    if f"{endpoint.method} {endpoint.path}" == "POST /v1/ops/sources/refresh-all":
        # 单例后台任务：第二次触发若撞上运行中 → 409 是**设计内**的确定性
        # 响应（sweep_already_running），不是状态被意外改写
        assert seen[0] == 200 and seen[1] in (200, 409), seen
        return
    assert seen[0] == seen[1], (
        f"{endpoint.method} {url} 两次调用状态码不同：{seen}——"
        "同一输入应得同一结果，不一致说明有状态被意外改写"
    )


def test_the_fixture_ids_exist_in_the_seed(client: TestClient):
    """如果 fixture 里的 id 是编的，上面那条会因为 404 而"通过"，测不到东西。"""
    assert client.request(
        "GET", "/v1/students/STU-A/profile",
        headers={ROLE_HEADER: ActorRole.STUDENT.value},
    ).status_code == 200
    # 已截止的默认不在目录里，所以这里要带上 include_expired——
    # fixture 用的那条恰好过了截止日期，那正是"目录不再假装它还开着"的证据。
    catalog = client.request(
        "GET", "/v1/catalog/opportunities?limit=1000&include_expired=true",
        headers={ROLE_HEADER: ActorRole.STUDENT.value},
    ).json()
    assert any(o["opportunity_id"] == PATH_VALUES["opportunity_id"] for o in catalog), (
        "fixture 用的 opportunity_id 连 include_expired 都找不到"
    )
