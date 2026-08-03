"""档案更新提议确认链路（2026-08-02 用户报障：确认即 500、技能不落库）。

复现路径 = 真实 Resume 提炼产物的形状：skill 加项是裸字符串，
experience 加项**没有 period 字段**（A1 不猜时间段）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


@pytest.fixture()
def deps() -> Deps:
    return Deps("full", model=None)


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def student(client: TestClient):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


RESUME_LIKE_PROPOSAL = {
    "proposal_id": "PROP-RESUME-T1",
    "student_id": "STU-A",
    "proposed_changes": [
        {"entity_type": "skill", "operation": "add",
         "field_path": "skills[]", "old_value": None, "new_value": "Java"},
        {"entity_type": "skill", "operation": "add",
         "field_path": "skills[]", "old_value": None, "new_value": "Git/GitHub"},
        # A1 现状：经历没有 period_start/period_end（不猜时间段）
        {"entity_type": "experience", "operation": "add",
         "field_path": "experiences[]", "old_value": None,
         "new_value": {"organization": "HKUST Student Union Hackathon",
                       "role": "front end"}},
        {"entity_type": "experience", "operation": "add",
         "field_path": "experiences[]", "old_value": None,
         "new_value": {"organization": "HKUST Computer Society",
                       "role": "Officer"}},
    ],
    "reason": "来自 Resume「t.md」的候选变更（待确认）",
    "impact": "medium",
    "status": "pending",
    "created_at": "2026-08-02T00:00:00Z",
}


def test_confirm_resume_proposal_materialises_everything(client, deps):
    call = student(client)
    r = call("POST", "/v1/students/STU-A/profile/proposals",
             json=RESUME_LIKE_PROPOSAL)
    assert r.status_code == 200, r.text
    before_tags = set(deps.students["STU-A"].interests)

    r = call("POST",
             "/v1/students/STU-A/profile/proposals/PROP-RESUME-T1/decision"
             "?decision=confirmed")
    assert r.status_code == 200, r.text          # 用户报障时这里 500

    after = deps.students["STU-A"]
    # 技能真的写进档案的自述标签池（interests；去重、保序）
    assert "Java" in after.interests and "Git/GitHub" in after.interests
    assert len(after.interests) == len(set(t.lower() for t in after.interests))
    assert before_tags <= set(after.interests)
    # 两条经历都落库（此前共用一个 EXP-id 只落第一条）
    exps = [e for e in deps.experiences
            if e.student_id == "STU-A" and "PROP-RESUME-T1" in e.experience_id]
    assert len(exps) == 2, [e.experience_id for e in exps]
    assert {e.organization for e in exps} == {
        "HKUST Student Union Hackathon", "HKUST Computer Society"}
    # 幂等：重复确认不翻倍
    call("POST", "/v1/students/STU-A/profile/proposals/PROP-RESUME-T1/decision"
                 "?decision=confirmed")
    assert len([e for e in deps.experiences
                if "PROP-RESUME-T1" in e.experience_id]) == 2
    assert len(deps.students["STU-A"].interests) == len(after.interests)


def test_reject_leaves_profile_untouched(client, deps):
    call = student(client)
    call("POST", "/v1/students/STU-A/profile/proposals", json={
        **RESUME_LIKE_PROPOSAL, "proposal_id": "PROP-RESUME-T2"})
    before = deps.students["STU-A"].interests
    r = call("POST",
             "/v1/students/STU-A/profile/proposals/PROP-RESUME-T2/decision"
             "?decision=rejected")
    assert r.status_code == 200, r.text
    assert deps.students["STU-A"].interests == before
    assert not [e for e in deps.experiences if "PROP-RESUME-T2" in e.experience_id]
