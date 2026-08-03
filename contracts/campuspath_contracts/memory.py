"""Spec §8.3–8.7、§14.4：四层记忆模型的契约面。

结构化数据库是权威事实；语义记忆只用于**召回**，不得覆盖成绩、资格或学生已确认的决定
（Spec §8.4 末）。契约层用 :class:`MemoryEntry.authority` 把这条写死：
记忆条目永远是 ``advisory``，没有 ``authoritative`` 取值可选。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    Confidence,
    Identifier,
    StrEnum,
    StudentId,
    Visibility,
)


class MemoryType(StrEnum):
    DECISION = "decision"
    PREFERENCE = "preference"
    EXPERIENCE = "experience"
    REJECTION = "rejection"          # 学生明确拒绝过的方向，防止换个名字重复推荐（T6）
    ENERGY_PATTERN = "energy_pattern"
    CONTACT = "contact"
    DOMAIN_FACT = "domain_fact"


class MemoryOrigin(StrEnum):
    """Spec §8.6：必须区分"学生原话"/"系统推断"/"外部事实"。"""

    STUDENT_STATEMENT = "student_statement"
    SYSTEM_INFERENCE = "system_inference"
    EXTERNAL_FACT = "external_fact"


class MemoryEntry(CampusPathModel):
    memory_id: Identifier
    student_id: StudentId
    type: MemoryType
    origin: MemoryOrigin
    content: str = Field(min_length=1, max_length=2000)
    source_event_id: Identifier = Field(
        description="Spec §8.6：每条记忆都要能回溯到一个事件。无来源的记忆不许写入"
    )
    confidence: Confidence = 0.5
    valid_from: datetime
    review_at: datetime | None = None
    supersedes: Identifier | None = Field(
        default=None, description="用 supersedes 表达更新，不静默覆盖"
    )
    superseded_by: Identifier | None = None
    visibility: Visibility = Visibility.PRIVATE
    authority: Literal["advisory"] = Field(
        default="advisory",
        description="记忆永远不是权威事实——权威在结构化数据库（Spec §8.4）",
    )
    student_locked: bool = Field(
        default=False, description="学生锁定后系统不得修改或覆盖该条"
    )

    @model_validator(mode="after")
    def _inference_is_not_a_personality_label(self) -> "MemoryEntry":
        if self.origin is MemoryOrigin.SYSTEM_INFERENCE and self.review_at is None:
            raise ValueError(
                "系统推断的记忆必须设置 review_at——不把短期情绪永久写成性格标签"
                "（Spec §8.6）"
            )
        return self


class MemoryProposal(CampusPathModel):
    """A1 Memory Curation Skill 的输出。高影响或有冲突的必须先经学生确认。"""

    proposal_id: Identifier
    student_id: StudentId
    entry: MemoryEntry
    high_impact: bool = False
    conflicts_with: tuple[Identifier, ...] = ()
    requires_student_confirmation: bool = False
    created_at: datetime

    @model_validator(mode="after")
    def _conflict_or_high_impact_needs_confirmation(self) -> "MemoryProposal":
        if (self.high_impact or self.conflicts_with) and not self.requires_student_confirmation:
            raise ValueError(
                "高影响或有冲突的记忆建议必须走学生确认（Spec §8.5、§8.6）"
            )
        return self


class MemoryRecallQuery(CampusPathModel):
    """按当前任务召回最小上下文，**不把完整人生记录塞进每次 Prompt**（Spec §8.6）。"""

    student_id: StudentId
    task_context: str = Field(min_length=1, max_length=1000)
    types: tuple[MemoryType, ...] = ()
    top_k: int = Field(default=5, ge=1, le=20)
    as_of: datetime | None = None


class RecalledMemory(CampusPathModel):
    entry: MemoryEntry
    relevance: Confidence
    stale: bool = Field(
        default=False, description="已过 review_at 或被 supersede；用于 Stale Memory Use Rate"
    )


class MemoryRecallResult(CampusPathModel):
    query: MemoryRecallQuery
    recalled: tuple[RecalledMemory, ...] = ()
    retrieved_at: datetime

    @model_validator(mode="after")
    def _respects_top_k(self) -> "MemoryRecallResult":
        if len(self.recalled) > self.query.top_k:
            raise ValueError("召回条数超过 top_k")
        return self


class MemoryCorrection(CampusPathModel):
    """学生对一条记忆的纠正（F17）。

    产生一条**新**条目并取代旧条目——旧条目保留并标记被取代（§8.6：
    不静默覆盖）。纠正内容是学生原话，origin 恒为 student_statement。
    """

    memory_id: Identifier = Field(description="被纠正的条目")
    corrected_content: str = Field(min_length=1, max_length=2000)


class MemoryForgetReceipt(CampusPathModel):
    """「忘记」的回执。条目被真正移除；移除这件事本身留痕。"""

    memory_id: Identifier
    student_id: StudentId
    forgotten_at: datetime


class StudentDataExport(CampusPathModel):
    """设置页「导出我的数据」（F01/F17）。只含**这个学生自己**可见域的记录。"""

    student_id: StudentId
    exported_at: datetime
    profile: "StudentProfile"
    evidence: tuple["EvidenceRecord", ...] = ()
    notes: tuple["Note", ...] = ()
    experiences: tuple["ExperienceRecord", ...] = ()
    goals: tuple["Goal", ...] = ()
    memory_entries: tuple[MemoryEntry, ...] = ()
    reflections: tuple["Reflection", ...] = ()
    proposals: tuple["ProfileUpdateProposal", ...] = ()
    course_records: tuple["StudentCourseRecord", ...] = ()
    availability: tuple["AvailabilityBlock", ...] = ()
    capacity_snapshots: tuple["CapacitySnapshot", ...] = ()
    schedule_proposals: tuple["ScheduleProposal", ...] = ()
    actions: tuple["ActionEvent", ...] = ()
    reminders: tuple["WellbeingReminderEvent", ...] = ()
    consents_on_record: tuple["OutreachConsent", ...] = ()


class DeletionReceipt(CampusPathModel):
    """「删除我的数据」的回执。Demo 环境立即生效（进程内数据即刻清除）。"""

    student_id: StudentId
    requested_at: datetime
    scope: Literal["all_personal_data"] = "all_personal_data"
    effect: Literal["immediate"] = "immediate"


from .academic import StudentCourseRecord  # noqa: E402  避免顶部循环引用
from .calendar import (  # noqa: E402
    AvailabilityBlock,
    CapacitySnapshot,
    ScheduleProposal,
)
from .goals import Goal  # noqa: E402
from .pathway import ActionEvent  # noqa: E402
from .profile import (  # noqa: E402
    EvidenceRecord,
    ExperienceRecord,
    Note,
    ProfileUpdateProposal,
    StudentProfile,
)
from .reflection import Reflection  # noqa: E402
from .wellbeing import OutreachConsent, WellbeingReminderEvent  # noqa: E402

StudentDataExport.model_rebuild()
