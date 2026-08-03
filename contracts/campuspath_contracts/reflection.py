"""Spec §9 / §14.4：Reflection、Key Takeaway 与活动质量反馈。

这是全系统隐私风险最集中的一处类型边界（Spec §8.9.2）：
A1 同时接触 Reflection 原文与最终流向校方的质量信号。

因此本模块把两者拆成**两个互不包含的类型**：

* :class:`Reflection` —— 含 ``private_text``，只存在于 Student Private Vault，
  没有任何指向 Aggregation 的字段；
* :class:`EventQualityFeedback` —— A1 通往 Aggregation Service 的**唯一**类型，
  全部为枚举与数值，**不含任何自由文本字段，也不含 student_id**。

B4 `Private Reflection Exposure = 0` 因此不依赖提示词，而是"接口类型上传不了"。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    Confidence,
    DevelopmentModeType,
    EvidenceId,
    Identifier,
    LocalizedText,
    NoteId,
    StrEnum,
    StudentId,
)


class EnergyCost(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    DRAINING = "draining"


class Reflection(CampusPathModel):
    """学生私有。``private_text`` 永远不离开 Student Private Vault。"""

    reflection_id: Identifier
    student_id: StudentId
    subject_id: Identifier = Field(description="被反思的行动 / 活动 / 课程")
    personal_learning: str | None = Field(default=None, max_length=5000)
    preference_delta: tuple[str, ...] = ()
    goal_delta: tuple[str, ...] = ()
    energy_cost: EnergyCost = EnergyCost.MODERATE
    next_action: str | None = Field(default=None, max_length=1000)
    private_text: str | None = Field(
        default=None,
        max_length=20000,
        description="学生原文。类型层保证它没有任何通往 Aggregation 的路径（B4）",
    )
    #: R4-E（2026-07-31）：学生**自己那份**评分留档，用于回看筛选。
    #: 出域的去标识评分仍走 event-feedback；这里的副本只在 student_private 域。
    rating_content_depth: int | None = Field(default=None, ge=1, le=5)
    rating_practical_value: int | None = Field(default=None, ge=1, le=5)
    rating_organization: int | None = Field(default=None, ge=1, le=5)
    #: 第 4 维（2026-08-02 用户裁定 D 批）：预期兑现（Spec §9.4 Expected vs. Realized）
    rating_expectation_match: int | None = Field(default=None, ge=1, le=5)
    fit_tag: str | None = Field(default=None, max_length=40)
    profile_candidate_ids: tuple[Identifier, ...] = ()
    created_at: datetime


class TakeawayType(StrEnum):
    CONCEPT = "concept"
    METHOD = "method"
    TOOL = "tool"
    DOMAIN_FACT = "domain_fact"
    SELF_INSIGHT = "self_insight"
    CONTACT = "contact"


class KeyTakeaway(CampusPathModel):
    """Spec §14.4：``author`` 恒为 student——系统不替学生总结"你学到了什么"。"""

    takeaway_id: Identifier
    student_id: StudentId
    text: str = Field(min_length=1, max_length=2000)
    type: TakeawayType
    tags: tuple[str, ...] = ()
    linked_goal_id: Identifier | None = None
    linked_skill_id: Identifier | None = None
    remember_flag: bool = False
    author: Literal["student"] = "student"
    created_at: datetime


class ReflectionResult(CampusPathModel):
    """A1 的一次 Reflection Skill 运行结果（Spec §9）。三类产出各自独立。"""

    result_id: Identifier
    student_id: StudentId
    reflection: Reflection
    takeaways: tuple[KeyTakeaway, ...] = ()
    profile_proposal_ids: tuple[Identifier, ...] = ()
    quality_feedback_id: Identifier | None = Field(
        default=None,
        description="指向结构化质量反馈的 id；原文不随之传出（§8.9.2）",
    )


# --------------------------------------------------------------------------
# 通往 Aggregation 的唯一类型
# --------------------------------------------------------------------------


class QualityDimension(StrEnum):
    """固定维度。新增维度要改 Spec，不能由前端随手加一个自由文本问题。"""

    CONTENT_DEPTH = "content_depth"
    ORGANIZATION = "organization"
    PRACTICAL_VALUE = "practical_value"
    NETWORKING_VALUE = "networking_value"
    EXPECTATION_MATCH = "expectation_match"


class FitTag(StrEnum):
    """区分"活动不好"与"对我不合适"（Spec §17.4 Personal-vs-Global Separation）。"""

    TOO_BASIC_FOR_ME = "too_basic_for_me"
    TOO_ADVANCED_FOR_ME = "too_advanced_for_me"
    WRONG_FORMAT_FOR_ME = "wrong_format_for_me"
    SCHEDULE_MISMATCH = "schedule_mismatch"
    GOOD_FIT = "good_fit"


class DimensionRating(CampusPathModel):
    dimension: QualityDimension
    rating: int = Field(ge=1, le=5)


class CohortDims(CampusPathModel):
    """粗粒度分组维度。**只有这三项**——细到专业方向以下就可能反查到个人。

    三个字段都是**受约束类型**，不是自由文本。此前 ``school`` 与
    ``development_mode`` 是裸 ``str``，于是
    ``school="ENGG/COMP/AI-track/2024-intake/GPA3.7-3.8"`` 完全合法——
    §17.1.2 要求"仅粗粒度分组、不含专业方向以下的细分"，
    而把细分塞进一个字符串既绕过了这条，也绕过了维度层数限制。
    """

    school: str = Field(
        pattern=r"^[A-Z]{2,6}$",
        description="学院代码，例如 'ENGG'。限制成短代码，塞不下更细的分层",
    )
    year_level: int = Field(ge=1, le=8)
    development_mode: DevelopmentModeType = Field(
        description="用枚举而非自由文本。枚举本来就存在，此前只是没接上"
    )


class StudentEventFeedbackForm(CampusPathModel):
    """学生端 C 轨评分表单（2026-07-31 用户要求：评分拆维度，不混在一起）。

    三个维度 + 一个个人匹配标签，对应架构的 Personal-vs-Global 分离：
    内容深度/实用收获/组织是**活动本身**的质量（进聚合）；
    「对我的匹配」是**个人**判断，只以 FitTag 枚举出域，不折进质量分。
    服务端（A1 的职责位）把本表单转换为去标识的 EventQualityFeedback；
    student_id 只在 URL 路径里，永不进入聚合载荷（§8.9.2）。
    """

    subject_id: Identifier = Field(description="被评的机会 / 活动")
    content_depth: int = Field(ge=1, le=5, description="内容深度与质量")
    practical_value: int = Field(ge=1, le=5, description="实用收获——是否学到东西")
    #: 第 4 维（D 批，2026-08-02）：预期兑现（Spec §9.4 Expected vs. Realized）
    expectation_match: int | None = Field(default=None, ge=1, le=5)
    organization: int | None = Field(default=None, ge=1, le=5, description="组织与流程")
    fit: FitTag = Field(description="与我的目标/形式的匹配——个人判断，不是质量分")
    attended_verified: bool = False


class EventQualityFeedback(CampusPathModel):
    """A1 → Aggregation Service 的唯一载荷（Spec §8.9.2）。

    **没有 student_id，没有自由文本。** 这两条由字段列表 + ``extra="forbid"``
    + ``tests/test_boundary_guards.py`` 的字段名扫描三重保证。
    """

    feedback_id: Identifier
    occurrence_id: Identifier
    series_id: Identifier | None = None
    verified_attendance: bool
    verification_ref: str | None = Field(
        default=None,
        pattern=r"^ver_[0-9a-f]{16,64}$",
        description=(
            "出勤验证的**不透明**凭据。刻意不叫 evidence_id——指向学生 Evidence 的 id "
            "会把聚合域重新连回个人。改名只是把字段从扫描器眼前挪走；"
            "正则才让「不透明」这件事可校验：EV-STUDENT-S001-transcript 这种串现在会被拒"
        ),
    )
    dimensions: tuple[DimensionRating, ...] = Field(min_length=1)
    fit_tags: tuple[FitTag, ...] = ()
    cohort_dims: CohortDims
    submitted_at: datetime

    @model_validator(mode="after")
    def _unverified_cannot_claim_ref(self) -> "EventQualityFeedback":
        if not self.verified_attendance and self.verification_ref is not None:
            raise ValueError("未验证出勤不应携带 verification_ref")
        return self
