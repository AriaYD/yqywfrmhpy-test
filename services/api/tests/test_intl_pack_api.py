"""国际学生规则包 API 测试（B2/B3，2026-08-02）。

链路：档案自助编辑写入 InternationalStudentContext（唯一入口）→
/consents 授 context_pack → GET context-pack/evaluation 出信封 +
Rules 签发凭据。全程零模型调用。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole, is_wellformed_validation_id
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


@pytest.fixture()
def deps() -> Deps:
    return Deps("full", model=object())


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def student(client: TestClient):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


INTL_CONTEXT = {
    "study_jurisdiction": "HK-SAR",
    "intended_work_jurisdiction": "HK-SAR",
    "study_mode": "full_time",
    "permission_category": "student_visa",
    "permission_expiry_date": "2027-06-30",
    "intended_start_date": "2026-09-01",
    "school_approval": None,
    "employer_sponsorship_expected": None,
    "language_evidence": ["IELTS 7.0"],
    "target_cities": ["Hong Kong"],
    "updated_at": "2026-08-02T00:00:00Z",
}


def _enable(call, student_id="STU-A"):
    # 顺序即闸门（审查 #6）：先同意，后落库——反过来会 403
    r = call("POST", f"/v1/students/{student_id}/consents",
             json={"scope": "context_pack", "granted": True})
    assert r.status_code == 200, r.text
    r = call("POST", f"/v1/students/{student_id}/profile/self-edit",
             json={"intl_context": INTL_CONTEXT})
    assert r.status_code == 200, r.text


def test_evaluation_409_before_enabling(client):
    r = student(client)("GET", "/v1/students/STU-A/context-pack/evaluation")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "intl_context_not_enabled"


def test_enable_then_evaluate(client, deps):
    call = student(client)
    _enable(call)
    r = call("GET", "/v1/students/STU-A/context-pack/evaluation")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["consented"] is True
    assert body["installed"] is True
    # Pack 处于 draft/review_required：如实 needs_confirmation + 待复核
    assert body["eligibility_state"] == "needs_confirmation"
    assert body["review_required"] is True
    assert body["pack_version"] == "0.1.0"
    assert len(body["source_links"]) >= 1
    # 凭据是 Rules 签发的真 id（形状 + 在 Registry 可验证）
    assert is_wellformed_validation_id(body["rules_validation_id"])
    assert body["pack_digest"].startswith("VAL-")
    issued = deps.validations.get(body["rules_validation_id"])
    assert issued is not None


def test_evaluation_with_opportunity_param(client):
    call = student(client)
    _enable(call)
    opp = call("GET", "/v1/catalog/opportunities?limit=1").json()[0]
    r = call("GET",
             f"/v1/students/STU-A/context-pack/evaluation?opportunity_id={opp['opportunity_id']}")
    assert r.status_code == 200
    assert r.json()["eligibility_state"] == "needs_confirmation"


def test_clear_intl_context_disables(client):
    call = student(client)
    _enable(call)
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"clear_intl_context": True})
    assert r.status_code == 200
    assert r.json()["intl_context"] is None
    r = call("GET", "/v1/students/STU-A/context-pack/evaluation")
    assert r.status_code == 409


def test_self_declared_term_is_rejected(client):
    """2026-08-03 用户裁定：学生自述「我现在大几」的通道全部撤除——
    学期/年级一律以教务侧为准（演示 = seed manifest 教务码 + 校方
    year 记录；接真实系统 = 教务系统下发）。契约层 extra=forbid
    直接拒收该字段，错误输入通道从结构上不存在。"""
    call = student(client)
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"current_term": "y2s1"})
    assert r.status_code == 422, r.text
    profile = call("GET", "/v1/students/STU-A/profile").json()
    assert "current_term" not in profile, "档案不再暴露自述学期字段"


def test_store_without_consent_is_403(client):
    """审查 #6：敏感自述落库前必须已有 context_pack 同意。"""
    call = student(client)
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"intl_context": INTL_CONTEXT})
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "context_pack_consent_required"


def test_clear_also_revokes_consent_server_side(client, deps):
    """审查 #6：取消勾选 = 服务端顺带撤销同意，不依赖前端补第二刀。"""
    call = student(client)
    _enable(call)
    call("POST", "/v1/students/STU-A/profile/self-edit",
         json={"clear_intl_context": True})
    from campuspath_contracts.profile import ConsentScope
    assert not deps.students["STU-A"].has_consent(ConsentScope.CONTEXT_PACK)


def test_decomposition_gains_intl_column_when_enabled(client, deps):
    """B3：拆解在 Pack 注入后带国际生准备列；未勾选时该列为空。"""
    call = student(client)
    goal = next(g for g in deps.goals["STU-A"]
                if g.development_mode.value == "employment")
    before = call("GET",
                  f"/v1/students/STU-A/goals/{goal.goal_id}/decomposition").json()
    assert before["intl_facets"] == []
    assert before["intl_pack_version"] is None

    _enable(call)
    after = call("GET",
                 f"/v1/students/STU-A/goals/{goal.goal_id}/decomposition").json()
    assert len(after["intl_facets"]) >= 2
    assert after["intl_pack_version"] == "0.1.0"
    assert after["intl_review_required"] is True
    assert all(f["kind"] == "constraint" for f in after["intl_facets"])
    # 硬性/软性/约束三层原样保留（第四列是追加，不是替换）
    assert len(after["facets"]) == len(before["facets"])
