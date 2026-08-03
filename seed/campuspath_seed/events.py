"""Profile 更新事件与长期记忆条目。

Profile 更新走的是 Spec §8.2.2 的三段式：Proposal → 学生决定 → ChangeEvent。
因此这里成对生成，且**刻意包含被拒绝与被修改的分支**——
只有确认分支的数据集无法证明 B3（拒绝了却写进去了）不会发生。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.memory import (
    MemoryEntry,
    MemoryOrigin,
    MemoryType,
)
from campuspath_contracts.profile import (
    ImpactLevel,
    ProfileChangeEvent,
    ProfileUpdateProposal,
    ProposalStatus,
    ProposedChange,
)

from .config import SEED_TODAY
from .personas import PersonaBundle
from .rng import pick, stream

_TZ = timezone.utc


def _dt(d: date, hour: int = 11) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=_TZ)


@dataclasses.dataclass
class EventBundle:
    proposals: list[ProfileUpdateProposal]
    change_events: list[ProfileChangeEvent]
    memories: list[MemoryEntry]


_CHANGE_TEMPLATES = (
    ("skill", "add", "skills[]", "user_research", "反思中提到独立完成 5 次用户访谈", ImpactLevel.MEDIUM),
    ("experience", "add", "experiences[]", "EXP-NEW", "实习结束并上传了推荐信", ImpactLevel.HIGH),
    ("project", "add", "projects[]", "PRJ-NEW", "课程项目结课并提交了作品链接", ImpactLevel.LOW),
    ("interest", "update", "interests", "machine learning", "连续三次选择了机器学习相关活动", ImpactLevel.LOW),
    ("constraint", "add", "constraints[]", "每周六不可安排", "学生在排程时连续拒绝周六时段", ImpactLevel.MEDIUM),
    ("energy_profile", "update", "energy_profile.weekly_discretionary_hours", "9", "学生连续两周延期任务", ImpactLevel.HIGH),
)

#: 决定分支的配比：确认 / 修改后确认 / 拒绝。拒绝分支必须存在，否则测不到 B3。
_DECISIONS = (
    ProposalStatus.CONFIRMED,
    ProposalStatus.CONFIRMED,
    ProposalStatus.EDITED,
    ProposalStatus.REJECTED,
    ProposalStatus.PENDING,
)


def build_events(personas: list[PersonaBundle], count: int) -> EventBundle:
    rng = stream("profile_events")
    deep = [p for p in personas if p.is_deep] or personas[:1]

    proposals: list[ProfileUpdateProposal] = []
    changes: list[ProfileChangeEvent] = []
    version_cursor = {p.profile.student_id: 1 for p in deep}

    for index in range(count):
        persona = deep[index % len(deep)]
        sid = persona.profile.student_id
        entity, operation, field_path, new_value, reason, impact = _CHANGE_TEMPLATES[
            index % len(_CHANGE_TEMPLATES)
        ]
        decision = _DECISIONS[index % len(_DECISIONS)]
        created = _dt(SEED_TODAY - timedelta(days=120 - index * 4))
        decided = None if decision is ProposalStatus.PENDING else created + timedelta(days=1)

        proposal_id = f"PROP-{sid}-{index + 1:03d}"
        proposals.append(
            ProfileUpdateProposal(
                proposal_id=proposal_id,
                student_id=sid,
                proposed_changes=(
                    ProposedChange(
                        entity_type=entity, operation=operation,
                        field_path=field_path, new_value=new_value,
                    ),
                ),
                reason=reason,
                source_event_ids=(f"EVT-{sid}-{index + 1:03d}",),
                evidence_ids=tuple(e.evidence_id for e in persona.evidence[:1]),
                impact=impact,
                status=decision,
                created_at=created,
                decided_at=decided,
            )
        )

        if decision is ProposalStatus.PENDING:
            continue

        before = version_cursor[sid]
        wrote = decision in {ProposalStatus.CONFIRMED, ProposalStatus.EDITED}
        after = before + 1 if wrote else before
        version_cursor[sid] = after
        changes.append(
            ProfileChangeEvent(
                event_id=f"PCE-{sid}-{index + 1:03d}",
                student_id=sid,
                profile_version_before=before,
                profile_version_after=after,
                actor="student",
                decision=decision,
                timestamp=decided,
                changed_fields=(field_path,) if wrote else (),
                proposal_id=proposal_id,
            )
        )

    # 长期记忆：拒绝记录是 T6（低价值重复曝光）的判据来源。
    #
    # 每人 9 条：前 5 条是 T12 记忆回归情景的**预期召回对象**
    # （goldset 按模板序号引用 `MEM-{sid}-{序号+1:03d}`，改这里必须同步那里），
    # 后 4 条是干扰项——没有干扰项，top-5 召回在 5 条记忆里是恒真式，
    # Recall@5 测不出任何东西。
    memories: list[MemoryEntry] = []
    memory_templates = (
        (MemoryType.REJECTION, MemoryOrigin.STUDENT_STATEMENT,
         "明确表示不想再参加纯讲座形式的活动，认为收获有限"),
        (MemoryType.PREFERENCE, MemoryOrigin.STUDENT_STATEMENT,
         "偏好小组形式、有产出物的活动，反馈过于基础的内容不想重复"),
        (MemoryType.DECISION, MemoryOrigin.STUDENT_STATEMENT,
         "决定本学期不申请交换，专注实习申请"),
        (MemoryType.EXPERIENCE, MemoryOrigin.EXTERNAL_FACT,
         "已完成一段数据分析实习并提交反思，获得推荐信"),
        (MemoryType.EXPERIENCE, MemoryOrigin.EXTERNAL_FACT,
         "参加过同系列活动的上一届，提交过申请但未获录取"),
        # —— 干扰项：与回归情景无关，但同属这个学生 ——
        (MemoryType.PREFERENCE, MemoryOrigin.STUDENT_STATEMENT,
         "喜欢在早晨安排深度专注时段"),
        (MemoryType.ENERGY_PATTERN, MemoryOrigin.SYSTEM_INFERENCE,
         "连续两周在周五晚间的任务被延期"),
        (MemoryType.DECISION, MemoryOrigin.STUDENT_STATEMENT,
         "决定把周末上午留给家人，不安排任何任务"),
        (MemoryType.PREFERENCE, MemoryOrigin.STUDENT_STATEMENT,
         "对户外与运动类社团兴趣不大"),
    )
    for persona in deep:
        sid = persona.profile.student_id
        for tindex, (mtype, origin, content) in enumerate(memory_templates):
            created = _dt(SEED_TODAY - timedelta(days=90 - tindex * 5))
            memories.append(
                MemoryEntry(
                    memory_id=f"MEM-{sid}-{tindex + 1:03d}",
                    student_id=sid,
                    type=mtype,
                    origin=origin,
                    content=content,
                    source_event_id=f"EVT-{sid}-{tindex + 1:03d}",
                    confidence=0.8 if origin is MemoryOrigin.STUDENT_STATEMENT else 0.45,
                    valid_from=created,
                    # 系统推断必须设复查时间：不把短期情绪写成性格标签（Spec §8.6）
                    review_at=created + timedelta(days=90)
                    if origin is MemoryOrigin.SYSTEM_INFERENCE else None,
                )
            )

    return EventBundle(proposals=proposals, change_events=changes, memories=memories)
