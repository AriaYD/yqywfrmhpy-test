"""Student State & Memory Platform：B3、Evidence 独立留存、记忆召回。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from campuspath_contracts.memory import (
    MemoryEntry,
    MemoryOrigin,
    MemoryProposal,
    MemoryRecallQuery,
    MemoryType,
)
from campuspath_contracts.profile import (
    EnergyProfile,
    EvidenceRecord,
    ImpactLevel,
    Note,
    ProfileUpdateProposal,
    ProposalStatus,
    ProposedChange,
    StudentProfile,
)

from campuspath_state.store import (
    InMemoryMemoryProvider,
    ProposalNotFound,
    StudentStateStore,
    UnconfirmedWrite,
    accept_memory_proposal,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


def profile(version: int = 1) -> StudentProfile:
    return StudentProfile(
        student_id="STU-A", institution="HKUST", program_id="BSC-COMP",
        level="undergraduate", year=2, expected_graduation=date(2029, 6, 30),
        energy_profile=EnergyProfile(weekly_discretionary_hours=14.0),
        version=version, updated_at=NOW,
    )


def proposal(pid: str = "PROP-1", status=ProposalStatus.PENDING, **kw) -> ProfileUpdateProposal:
    base = dict(
        proposal_id=pid, student_id="STU-A",
        proposed_changes=(
            ProposedChange(entity_type="skill", operation="add",
                           field_path="skills[]", new_value="user_research"),
        ),
        reason="反思中提到独立完成 5 次用户访谈",
        impact=ImpactLevel.MEDIUM, status=status, created_at=NOW,
    )
    base.update(kw)
    return ProfileUpdateProposal(**base)


def store() -> StudentStateStore:
    return StudentStateStore(profile=profile())


# --------------------------------------------------------------------------
# B3：Profile 的唯一写入路径
# --------------------------------------------------------------------------


def test_confirmation_bumps_the_version_exactly_once():
    s = store()
    s.submit_proposal(proposal())
    event = s.apply_decision("PROP-1", ProposalStatus.CONFIRMED,
                             decided_at=NOW, changed_fields=("skills",))
    assert event.profile_version_before == 1
    assert event.profile_version_after == 2
    assert s.profile.version == 2


def test_rejection_keeps_the_event_but_not_the_change():
    """Spec §8.2.2：拒绝时保留事件，不写入当前 Profile。"""
    s = store()
    s.submit_proposal(proposal())
    event = s.apply_decision("PROP-1", ProposalStatus.REJECTED, decided_at=NOW)
    assert s.profile.version == 1
    assert event.changed_fields == ()
    assert len(s.events) == 1, "拒绝也要留痕，否则无法回答'为什么这条没写进去'"


def test_agent_cannot_submit_an_already_confirmed_proposal():
    """已知会失败的样例：A1 自己把状态置成 confirmed 再提交。"""
    s = store()
    with pytest.raises(UnconfirmedWrite):
        s.submit_proposal(proposal(status=ProposalStatus.CONFIRMED, decided_at=NOW))


def test_proposal_for_another_student_is_refused():
    s = store()
    with pytest.raises(UnconfirmedWrite):
        s.submit_proposal(proposal(student_id="STU-B"))


def test_there_is_no_direct_profile_write_method():
    """B3 的结构性保证：除了 apply_decision，没有别的写入入口。"""
    writers = [
        name for name in dir(StudentStateStore)
        if not name.startswith("_") and name.startswith(("set_", "update_", "write_"))
    ]
    assert writers == [], f"出现了绕过确认的写入方法：{writers}"


def test_pending_is_not_a_decision():
    s = store()
    s.submit_proposal(proposal())
    with pytest.raises(UnconfirmedWrite):
        s.apply_decision("PROP-1", ProposalStatus.PENDING, decided_at=NOW)


def test_unknown_proposal_is_rejected():
    with pytest.raises(ProposalNotFound):
        store().apply_decision("nope", ProposalStatus.CONFIRMED, decided_at=NOW)


def test_events_are_append_only():
    s = store()
    s.submit_proposal(proposal())
    s.apply_decision("PROP-1", ProposalStatus.CONFIRMED, decided_at=NOW,
                     changed_fields=("skills",))
    assert isinstance(s.events, tuple), "事件流不能把可变引用交出去"


def test_version_can_be_replayed_to_a_point_in_time():
    s = store()
    for index in range(3):
        pid = f"PROP-{index}"
        s.submit_proposal(proposal(pid))
        s.apply_decision(pid, ProposalStatus.CONFIRMED,
                         decided_at=NOW + timedelta(days=index), changed_fields=("skills",))
    assert s.profile_version_at(NOW) == 2
    assert s.profile_version_at(NOW + timedelta(days=5)) == 4


# --------------------------------------------------------------------------
# Evidence 与 Note 独立留存
# --------------------------------------------------------------------------


def test_evidence_survives_profile_changes():
    """Spec §8.2.3：Profile 项只引用 evidence_ids，不复制后丢掉原记录。"""
    s = store()
    s.put_evidence(EvidenceRecord(
        evidence_id="EV-1", student_id="STU-A", evidence_type="certificate",
        source="upload", object_ref="vault/STU-A/x.pdf", obtained_at=date(2026, 5, 1),
    ))
    s.submit_proposal(proposal())
    s.apply_decision("PROP-1", ProposalStatus.REJECTED, decided_at=NOW)
    assert s.evidence("EV-1") is not None
    assert s.evidence_count == 1


def test_notes_are_stored_separately_from_evidence():
    s = store()
    s.put_note(Note(note_id="N-1", student_id="STU-A", author="student",
                    text="私人反思", created_at=NOW))
    assert s.note("N-1") is not None
    assert s.evidence("N-1") is None


# --------------------------------------------------------------------------
# L2 记忆
# --------------------------------------------------------------------------


def memory(mid: str, content: str, *, mtype=MemoryType.PREFERENCE,
           origin=MemoryOrigin.STUDENT_STATEMENT, **kw) -> MemoryEntry:
    base = dict(
        memory_id=mid, student_id="STU-A", type=mtype, origin=origin,
        content=content, source_event_id=f"EVT-{mid}", valid_from=NOW,
    )
    if origin is MemoryOrigin.SYSTEM_INFERENCE:
        base["review_at"] = NOW + timedelta(days=90)
    base.update(kw)
    return MemoryEntry(**base)


def test_recall_returns_task_relevant_entries_only():
    """Spec §8.6：只召回与当前任务相关的最小上下文。"""
    provider = InMemoryMemoryProvider()
    provider.write(memory("M-1", "偏好 小组 形式 的 活动"))
    provider.write(memory("M-2", "决定 本学期 不申请 交换"))
    result = provider.recall(
        MemoryRecallQuery(student_id="STU-A", task_context="推荐 小组 活动", top_k=5),
        now=NOW,
    )
    assert [r.entry.memory_id for r in result.recalled] == ["M-1"]


def test_recall_works_on_unspaced_chinese():
    """无空格中文靠字符二元组匹配（T12 的检索基础）。

    此前整句是一个 token，只有逐字相同的两句才"相关"——
    中文记忆在真实查询下永远召回不到。
    """
    provider = InMemoryMemoryProvider()
    provider.write(memory("M-1", "明确表示不想再参加纯讲座形式的活动"))
    provider.write(memory("M-2", "对户外与运动类社团兴趣不大"))
    result = provider.recall(
        MemoryRecallQuery(student_id="STU-A", task_context="已明确拒绝纯讲座类活动", top_k=5),
        now=NOW,
    )
    ids = [r.entry.memory_id for r in result.recalled]
    assert ids and ids[0] == "M-1"
    assert "M-2" not in ids


def test_recall_respects_top_k():
    provider = InMemoryMemoryProvider()
    for index in range(10):
        provider.write(memory(f"M-{index}", "活动 偏好"))
    result = provider.recall(
        MemoryRecallQuery(student_id="STU-A", task_context="活动", top_k=3), now=NOW
    )
    assert len(result.recalled) == 3


def test_recall_never_crosses_students():
    provider = InMemoryMemoryProvider()
    provider.write(memory("M-1", "活动 偏好").model_copy(update={"student_id": "STU-B"}))
    result = provider.recall(
        MemoryRecallQuery(student_id="STU-A", task_context="活动", top_k=5), now=NOW
    )
    assert result.recalled == ()


def test_supersede_keeps_the_timeline():
    """Spec §8.6：新旧冲突时保留时间线，用 supersedes 表示更新，不静默覆盖。"""
    provider = InMemoryMemoryProvider()
    provider.write(memory("M-1", "偏好 线下 活动"))
    provider.write(memory("M-2", "偏好 线上 活动", supersedes="M-1"))
    assert provider.entries["M-1"].superseded_by == "M-2"
    assert provider.entries["M-1"].content == "偏好 线下 活动"


def test_superseded_entries_are_flagged_stale_on_recall():
    provider = InMemoryMemoryProvider()
    provider.write(memory("M-1", "偏好 线下 活动"))
    provider.write(memory("M-2", "偏好 线上 活动", supersedes="M-1"))
    result = provider.recall(
        MemoryRecallQuery(student_id="STU-A", task_context="偏好 活动", top_k=5), now=NOW
    )
    by_id = {r.entry.memory_id: r for r in result.recalled}
    assert by_id["M-1"].stale is True
    assert by_id["M-2"].stale is False


def test_entries_past_review_date_are_stale():
    provider = InMemoryMemoryProvider()
    provider.write(memory("M-1", "周五 晚间 任务 常被 延期",
                          mtype=MemoryType.ENERGY_PATTERN,
                          origin=MemoryOrigin.SYSTEM_INFERENCE))
    result = provider.recall(
        MemoryRecallQuery(student_id="STU-A", task_context="周五 任务", top_k=5),
        now=NOW + timedelta(days=200),
    )
    assert result.recalled[0].stale is True


def test_memory_is_never_authoritative():
    """Spec §8.4：语义记忆用于召回，不应覆盖成绩、资格或学生已确认的决定。"""
    assert memory("M-1", "x").authority == "advisory"
    assert "authoritative" not in str(MemoryEntry.model_fields["authority"].annotation)


def test_high_impact_memory_needs_confirmation():
    provider = InMemoryMemoryProvider()
    prop = MemoryProposal(
        proposal_id="MP-1", student_id="STU-A",
        entry=memory("M-1", "学生 可能 不适合 研究 方向",
                     origin=MemoryOrigin.SYSTEM_INFERENCE),
        high_impact=True, requires_student_confirmation=True, created_at=NOW,
    )
    with pytest.raises(UnconfirmedWrite):
        accept_memory_proposal(provider, prop, student_confirmed=False)
    assert provider.entries == {}

    accept_memory_proposal(provider, prop, student_confirmed=True)
    assert "M-1" in provider.entries


def test_low_impact_memory_writes_without_confirmation():
    provider = InMemoryMemoryProvider()
    prop = MemoryProposal(
        proposal_id="MP-2", student_id="STU-A", entry=memory("M-2", "偏好 小组"),
        high_impact=False, requires_student_confirmation=False, created_at=NOW,
    )
    accept_memory_proposal(provider, prop, student_confirmed=False)
    assert "M-2" in provider.entries
