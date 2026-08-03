"""Context Pack → Rules 凭据桥测试（B1）。

关键断言：**Pack 自铸的 VAL-* 过不了 B8，Rules 签发的才行**——
这是桥存在的理由，必须双向证明（H5）。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from campuspath_rules.context_pack import evaluate_context_pack
from campuspath_rules.engine import RulesEngine

TODAY = date(2026, 8, 2)
NOW = datetime(2026, 8, 2, 9, tzinfo=timezone.utc)

HK_GRAD_PROFILE = {
    "student_cohort": "international",
    "study_jurisdiction": "HK-SAR",
    "intended_work_jurisdiction": "HK-SAR",
    "institution": "HKUST",
    "programme_level": "undergraduate",
    "study_mode": "full_time",
    "goal_type": "graduate_employment",
    "permission_category": "student_visa",
    "permission_expiry_date": "2027-06-30",
    "intended_start_date": "2026-09-01",
    "consent_context_pack": True,
}


def test_rules_issue_a_real_validation_for_pack_evaluation():
    engine = RulesEngine()
    envelope, validation = evaluate_context_pack(
        engine, HK_GRAD_PROFILE, today=TODAY, now=NOW)
    # Pack 处于 draft/review_required → 状态必然 needs_confirmation（如实）
    assert envelope["eligibility_state"] == "needs_confirmation"
    assert envelope["review_required"] is True
    assert validation.verdict.value == "needs_confirmation"
    # B8 第二层：id 真的在 Registry 的签发链上
    assert engine.registry.verify(validation.validation_id, validation.subject_ref)
    # 留痕：Pack 自己的 digest 与规则 id 都进了 reasons
    observed = " ".join(r.observed or "" for r in validation.reasons)
    assert "pack_digest=VAL-" in observed
    assert any(r.rule_id.startswith("CTXPACK.HK-") for r in validation.reasons)
    assert any(r.rule_id == "CTXPACK.REVIEW_REQUIRED" for r in validation.reasons)


def test_pack_minted_digest_is_not_a_rules_credential():
    """H5 反例：把信封里的 VAL-* 当 validation_id 用，必须被拒。"""
    engine = RulesEngine()
    envelope, _ = evaluate_context_pack(engine, HK_GRAD_PROFILE, today=TODAY, now=NOW)
    pack_digest = envelope["validation_id"]
    assert pack_digest.startswith("VAL-")
    from campuspath_contracts.common import SourceRef
    subject = SourceRef(entity_type="context_pack_evaluation",
                        entity_id="intl-student-context")
    assert not engine.registry.verify(pack_digest, subject)


def test_no_consent_still_evaluates_but_stays_confirmation():
    engine = RulesEngine()
    profile = {**HK_GRAD_PROFILE, "consent_context_pack": False}
    envelope, validation = evaluate_context_pack(engine, profile, today=TODAY, now=NOW)
    assert envelope["pack_status"]["consented"] is False
    assert envelope["eligibility_state"] == "needs_confirmation"
    assert validation.verdict.value == "needs_confirmation"


def test_replay_is_deterministic():
    """同一输入连调两次（Plan §10.2 幂等坑）：同一 id、不炸。"""
    engine = RulesEngine()
    _, first = evaluate_context_pack(engine, HK_GRAD_PROFILE, today=TODAY, now=NOW)
    _, second = evaluate_context_pack(engine, HK_GRAD_PROFILE, today=TODAY, now=NOW)
    assert first.validation_id == second.validation_id
    assert first.decision_key() == second.decision_key()


def test_opportunity_fields_flow_into_evaluation():
    """「某公司是否接受留学生」只能来自 Opportunity 字段，缺失 → 缺证据。"""
    engine = RulesEngine()
    envelope, _ = evaluate_context_pack(
        engine,
        {**HK_GRAD_PROFILE, "goal_type": "internship"},
        {"opportunity_id": "OPP-X", "opportunity_location": "Hong Kong",
         "opportunity_hours": 20, "opportunity_type": "internship"},
        today=TODAY, now=NOW,
    )
    assert "school_approval" in envelope["missing_information"]


def test_prep_item_validation_backs_action_plan_items():
    """fix/intl-chain：Pack 派生动作的凭据要能背书 PlanItem(kind=action)。"""
    from campuspath_contracts.common import SourceRef
    from campuspath_rules.context_pack import issue_prep_item_validation

    engine = RulesEngine()
    envelope, _ = evaluate_context_pack(engine, HK_GRAD_PROFILE, today=TODAY, now=NOW)
    validation = issue_prep_item_validation(
        engine, subject_id="prep-transition", student_id="STU-A",
        detail="Plan the graduate-employment transition",
        pack_digest=envelope["validation_id"],
        pack_version=envelope["pack_version"], now=NOW,
    )
    ok = SourceRef(entity_type="action", entity_id="prep-transition")
    assert engine.registry.verify(validation.validation_id, ok)
    # H5 反例：主体张冠李戴必须被拒
    other = SourceRef(entity_type="action", entity_id="someone-elses-action")
    assert not engine.registry.verify(validation.validation_id, other)
    # 留痕：能追回 Pack 自己的 digest
    observed = " ".join(r.observed or "" for r in validation.reasons)
    assert "pack_digest=VAL-" in observed


def test_prep_item_ids_do_not_collide_across_pack_revisions():
    """codex #6/#12：digest 变了（Pack 或档案输入变了）→ 新 id，不撞旧凭据；
    digest 没变 → 幂等重签同 id 不炸。跨学生 context 不同 → id 不同。"""
    from campuspath_rules.context_pack import issue_prep_item_validation

    engine = RulesEngine()
    envelope_a, _ = evaluate_context_pack(engine, HK_GRAD_PROFILE, today=TODAY, now=NOW)
    changed_profile = {**HK_GRAD_PROFILE, "intended_work_jurisdiction": "CN-mainland"}
    envelope_b, _ = evaluate_context_pack(engine, changed_profile, today=TODAY, now=NOW)
    assert envelope_a["validation_id"] != envelope_b["validation_id"], \
        "前提不成立：两份输入居然同 digest"

    def issue(digest, student="STU-A"):
        return issue_prep_item_validation(
            engine, subject_id=f"{student}-prep-transition", student_id=student,
            detail="Plan the graduate-employment transition",
            pack_digest=digest, pack_version=envelope_a["pack_version"], now=NOW)

    first = issue(envelope_a["validation_id"])
    again = issue(envelope_a["validation_id"])     # 同 digest：幂等，不炸
    assert first.validation_id == again.validation_id
    revised = issue(envelope_b["validation_id"])   # 新 digest：新 id，不改判旧凭据
    assert revised.validation_id != first.validation_id
    other_student = issue(envelope_a["validation_id"], student="STU-B")
    assert other_student.validation_id != first.validation_id
