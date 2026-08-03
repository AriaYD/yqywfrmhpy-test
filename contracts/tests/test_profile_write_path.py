"""B3 Unconfirmed Profile Write = 0：Profile 的写入路径契约（Spec §8.2.2、§8.2.4）。

三段式：Proposal（pending）→ 学生决定 → ChangeEvent。
契约层保证的是"拒绝不写入、确认才 +1、Evidence 独立留存"，
让 B3 的评测只需回溯事件而不需要重放业务逻辑。
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.profile import (
    ConsentRecord,
    ConsentScope,
    EnergyProfile,
    EvidenceRecord,
    ImpactLevel,
    Note,
    ProfileChangeEvent,
    ProfileUpdateProposal,
    ProposalStatus,
    ProposedChange,
    SkillRecord,
    SkillLevel,
    SkillSourceType,
    StudentProfile,
)

from conftest import NOW, TODAY


def _proposal(**kw) -> ProfileUpdateProposal:
    base = dict(
        proposal_id="PR-1",
        student_id="S-001",
        proposed_changes=(
            ProposedChange(
                entity_type="skill",
                operation="add",
                field_path="skills[]",
                new_value="user_research",
            ),
        ),
        reason="实习反思中提到独立完成了 5 次用户访谈",
        impact=ImpactLevel.MEDIUM,
        created_at=NOW,
    )
    base.update(kw)
    return ProfileUpdateProposal(**base)


def _event(**kw) -> ProfileChangeEvent:
    base = dict(
        event_id="EV-1",
        student_id="S-001",
        profile_version_before=3,
        profile_version_after=4,
        actor="student",
        decision=ProposalStatus.CONFIRMED,
        timestamp=NOW,
        changed_fields=("skills",),
        proposal_id="PR-1",
    )
    base.update(kw)
    return ProfileChangeEvent(**base)


def test_new_proposal_starts_pending():
    assert _proposal().status is ProposalStatus.PENDING


def test_terminal_status_requires_a_decision_timestamp():
    """已知会失败的样例：状态跳到 confirmed 却没有决定时间，审计无从回溯。"""
    with pytest.raises(ValidationError):
        _proposal(status=ProposalStatus.CONFIRMED)


def test_confirmed_proposal_with_timestamp_is_valid():
    proposal = _proposal(status=ProposalStatus.CONFIRMED, decided_at=NOW)
    assert proposal.decided_at == NOW


def test_proposal_must_change_something():
    with pytest.raises(ValidationError):
        _proposal(proposed_changes=())


def test_rejection_does_not_bump_profile_version():
    """Spec §8.2.2：拒绝时"保留事件，不写入当前 Profile"。"""
    event = _event(
        decision=ProposalStatus.REJECTED,
        profile_version_after=3,
        changed_fields=(),
    )
    assert event.profile_version_after == event.profile_version_before


def test_rejection_that_bumps_version_is_rejected():
    """已知会失败的样例：拒绝了却还是写进去了——这正是 B3 要抓的。"""
    with pytest.raises(ValidationError) as excinfo:
        _event(decision=ProposalStatus.REJECTED)
    assert "B3" in str(excinfo.value)


def test_rejection_cannot_record_changed_fields():
    with pytest.raises(ValidationError):
        _event(decision=ProposalStatus.REJECTED, profile_version_after=3, changed_fields=("skills",))


@pytest.mark.parametrize("after", [3, 5, 10])
def test_confirmation_must_bump_version_by_exactly_one(after):
    with pytest.raises(ValidationError):
        _event(profile_version_after=after)


def test_change_event_is_immutable():
    event = _event()
    with pytest.raises(ValidationError):
        event.decision = ProposalStatus.REJECTED


def test_inferred_skill_confirmed_without_evidence_is_rejected():
    """§8.2.4：Agent 推断的技能，学生确认后才写入，且要能追溯到证据。"""
    with pytest.raises(ValidationError):
        SkillRecord(
            skill_id="user_research",
            student_id="S-001",
            level=SkillLevel.PRACTICING,
            source_type=SkillSourceType.AGENT_INFERRED,
            student_confirmed=True,
            evidence_ids=(),
        )


def test_inferred_skill_with_evidence_is_accepted():
    skill = SkillRecord(
        skill_id="user_research",
        student_id="S-001",
        level=SkillLevel.PRACTICING,
        source_type=SkillSourceType.AGENT_INFERRED,
        student_confirmed=True,
        evidence_ids=("EV-1",),
    )
    assert skill.student_confirmed


def test_evidence_needs_a_payload():
    """Spec §8.2.3：Evidence 保存来源与附件/链接。两者皆无就不是证据。"""
    with pytest.raises(ValidationError):
        EvidenceRecord(
            evidence_id="EV-9",
            student_id="S-001",
            evidence_type="certificate",
            source="self_upload",
            obtained_at=TODAY,
        )


def test_note_and_evidence_are_separate_entities():
    """Profile 只引用 id，不复制内容——这样 Profile 变更不会带走原记录。"""
    assert "text" in Note.model_fields
    assert "text" not in EvidenceRecord.model_fields


# --------------------------------------------------------------------------
# Profile 与同意
# --------------------------------------------------------------------------


def _profile(**kw) -> StudentProfile:
    base = dict(
        student_id="S-001",
        institution="HKUST",
        program_id="BENG-COMP",
        level="undergraduate",
        year=2,
        expected_graduation=date(2028, 6, 30),
        energy_profile=EnergyProfile(weekly_discretionary_hours=12),
        version=1,
        updated_at=NOW,
    )
    base.update(kw)
    return StudentProfile(**base)


def test_profile_without_consent_grants_nothing():
    assert _profile().has_consent(ConsentScope.CALENDAR_FREEBUSY) is False


def test_revoked_consent_is_not_active():
    profile = _profile(
        consent=(
            ConsentRecord(
                scope=ConsentScope.CALENDAR_FREEBUSY,
                granted=True,
                granted_at=NOW,
                revoked_at=NOW,
            ),
        )
    )
    assert profile.has_consent(ConsentScope.CALENDAR_FREEBUSY) is False


def test_energy_profile_sleep_window_defaults_to_unset():
    """B6 的前置条件：没设窗口就是没设，不给默认值假装设过。"""
    energy = EnergyProfile(weekly_discretionary_hours=10)
    assert energy.sleep_window_start is None
    assert energy.recovery_preference_defined is False
