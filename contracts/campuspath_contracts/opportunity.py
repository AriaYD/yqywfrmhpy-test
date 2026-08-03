"""Spec §14.3 / §16.1–16.3：机会、四态资格与匹配。

两条契约：

* **四态资格不是布尔过滤器**。``Ineligible current cycle`` 与 ``Future eligible``
  是不同的结论：前者本轮不安排，后者进长期路径。契约层用枚举强制区分，
  防止实现退化成"能申请 / 不能申请"（Spec §16.1）。
* **每一条资格结论携带 validation_id**（Spec §8.9.3）。资格由 Rules 判定，
  A5 只负责解释与排序；``EligibilityAssessment`` 因此不含任何分数字段。

A4 的产出（``OpportunityDraft``）走独立的审核链路，在 Schema 闸门通过前
**不进入** Catalog，也不进入任何学生上下文（Spec §8.9.1）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .common import (
    CampusPathModel,
    Confidence,
    FrozenModel,
    Identifier,
    LocalizedText,
    OpportunityId,
    Provenance,
    StrEnum,
    Uncertainty,
    ValidationId,
)
from .goals import RequirementCategory


class OpportunityType(StrEnum):
    INTERNSHIP = "internship"
    JOB = "job"
    RESEARCH_POSITION = "research_position"
    COMPETITION = "competition"
    WORKSHOP = "workshop"
    EVENT = "event"
    CLUB_ACTIVITY = "club_activity"
    SCHOLARSHIP = "scholarship"
    EXCHANGE = "exchange"
    MENTORSHIP = "mentorship"
    VOLUNTEER = "volunteer"
    # 2026-08-02 用户裁定 G：政策源变更检测产出的「政策更新提醒卡」。
    # 不是可报名的机会——广场上只展示与跳转官方源，无报名/加入日历动作。
    POLICY_UPDATE = "policy_update"


class InternationalAcceptance(StrEnum):
    """「是否接受国际学生」三态（B，2026-08-02）。

    **模型永远不猜这个字段**（integration-contract：employer claims 归
    Opportunity 所有）——取值只能来自发布者填写或官方源结构化抽取；
    UNKNOWN 时求值器自动 needs_confirmation，界面不显示不编造。
    """

    ACCEPTS = "accepts"
    NOT_ACCEPTED = "not_accepted"
    UNKNOWN = "unknown"


class OrganizerCategory(StrEnum):
    """主办方分类（2026-07-31 八大类；2026-08-02 用户裁定扩为十大类）。
    浏览筛选用这一层，不用原始名称。"""

    CAMPUS_OFFICIAL = "campus_official"          # 校园官方 / 主校区
    SCHOOL_FACULTY = "school_faculty"            # 学院 / 学系 / 实验室
    CAREER_CENTER = "career_center"
    ENTREPRENEURSHIP_CENTER = "entrepreneurship_center"
    STUDENT_CLUB = "student_club"
    ALUMNI = "alumni"
    ENTERPRISE = "enterprise"
    PARTNER_ENTERPRISE = "partner_enterprise"    # 与学校有合作关系的企业
    POLICY = "policy"                            # 政策与官方通知（校方/政府公开信息）
    INTL_POLICY = "intl_policy"                  # 留学生相关政策（勾选国际生后可见筛选）


class PublicationStatus(StrEnum):
    """Spec D5 的完整状态机。缺任何一个状态都无法演示退回/驳回分支。"""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    AUTO_CHECKED = "auto_checked"
    IN_REVIEW = "in_review"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    APPROVED = "approved"
    PUBLISHED = "published"
    UPDATED = "updated"
    EXPIRED = "expired"
    WITHDRAWN = "withdrawn"
    ARCHIVED = "archived"


class EligibilityRuleKind(StrEnum):
    YEAR_LEVEL = "year_level"
    PROGRAM = "program"
    GPA = "gpa"
    PREREQUISITE_COURSE = "prerequisite_course"
    WORK_AUTHORIZATION = "work_authorization"
    LANGUAGE = "language"
    MEMBERSHIP = "membership"
    APPLICATION_WINDOW = "application_window"
    OTHER = "other"


class EligibilityRule(CampusPathModel):
    """来自机会来源的**具体规则**，不是全局年级假设（Spec §16.1）。"""

    kind: EligibilityRuleKind
    expression: str = Field(description="来源原文或结构化表达式")
    source_tier: Literal[
        "organizer_structured", "official_page_text", "institution_confirmed",
        "institution_note", "model_inferred"
    ] = Field(description="Spec §16.2 的优先级；model_inferred 只能导向 needs_confirmation")
    mandatory: bool = True

    @model_validator(mode="after")
    def _inference_cannot_disqualify(self) -> "EligibilityRule":
        if self.source_tier == "model_inferred" and self.mandatory:
            raise ValueError(
                "模型推断的规则不得标记为 mandatory——它只能产生 needs_confirmation，"
                "不能作为淘汰依据（Spec §16.2 第 5 条）"
            )
        return self


class Opportunity(CampusPathModel):
    opportunity_id: OpportunityId
    type: OpportunityType
    title: str = Field(max_length=300, description="来源给出的官方标题（通常是英文）")
    title_localized: LocalizedText | None = Field(
        default=None,
        description=(
            "来源**自己**提供的译名。为空表示来源只有一种语言——"
            "这时 UI 回落到 title，而不是找模型现翻一个：机会名称会被学生"
            "拿去搜索、报名、写进简历，翻错的代价不是读起来别扭而已。"
        ),
    )
    organizer: str
    organizer_localized: LocalizedText | None = None
    #: 主办方八大类（2026-07-31 用户裁定，取代按原始名称的碎片化筛选）。
    #: None = 旧数据未标注，前端归入"企业"以外的「未分类」不猜。
    organizer_category: OrganizerCategory | None = None
    occurrence_id: Identifier | None = Field(
        default=None, description="同一系列的某一届"
    )
    series_id: Identifier | None = None
    category_tags: tuple[str, ...] = ()

    @field_validator("category_tags", mode="after")
    @classmethod
    def _dedupe_category_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """去重保序（2026-07-31 用户报障）：类型词与随机标签撞车曾产生
        ('internship','internship')，前端拿标签当 React key 直接报错。
        在类型层规范化，任何来源（Seed / A4 草稿 / 真实抓取）都干净。"""
        return tuple(dict.fromkeys(value))
    requirement_categories: tuple[RequirementCategory, ...] = Field(
        default=(), description="该机会能覆盖的要求类别，用于 Gap Coverage 计算"
    )
    eligibility_rules: tuple[EligibilityRule, ...] = ()
    # ── 国际学生相关字段（B，2026-08-02）。三个都只能来自发布者填写或
    #    官方源结构化抽取——**不许由模型推断**；默认值 = 如实的"不知道"。
    accepts_international: InternationalAcceptance = InternationalAcceptance.UNKNOWN
    sponsorship_support: LocalizedText | None = None
    language_requirements: tuple[LocalizedText, ...] = Field(default=(), max_length=5)
    deadline: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    workload_hours_total: float | None = Field(default=None, ge=0)
    skills: tuple[Identifier, ...] = ()
    official_url: str
    source_id: Identifier
    provenance: Provenance
    publication_status: PublicationStatus = PublicationStatus.DRAFT
    last_verified_at: datetime | None = Field(
        default=None, description="用于 T7 Stale/Wrong Opportunity Rate"
    )


# --------------------------------------------------------------------------
# 四态资格
# --------------------------------------------------------------------------


class EligibilityStateName(StrEnum):
    """Spec §16.1。四态，不是两态。"""

    ELIGIBLE_NOW = "eligible_now"
    FUTURE_ELIGIBLE = "future_eligible"
    NEEDS_CONFIRMATION = "needs_confirmation"
    INELIGIBLE_CURRENT_CYCLE = "ineligible_current_cycle"


class EligibilityReason(CampusPathModel):
    rule_kind: EligibilityRuleKind
    satisfied: bool | None = Field(
        default=None, description="None 表示信息不足——这本身就是 needs_confirmation 的依据"
    )
    detail: LocalizedText
    source_tier: str


class EligibilityAssessment(CampusPathModel):
    """由 Rules & Constraint Engine 判定，A5 只负责解释（Spec §16.5 步骤 1–2）。

    **无分数字段。** 排序发生在 :class:`MatchResult`，那是 A5 的产出。
    """

    assessment_id: Identifier
    opportunity_id: OpportunityId
    state: EligibilityStateName
    reasons: tuple[EligibilityReason, ...] = ()
    next_eligibility_date: date | None = None
    blocking_requirement_ids: tuple[Identifier, ...] = ()
    validation_id: ValidationId = Field(
        description="Spec §8.9.3：每一条资格结论必须携带 Rules 的校验凭据"
    )
    evaluated_at: datetime

    @model_validator(mode="after")
    def _future_eligible_needs_a_date(self) -> "EligibilityAssessment":
        if self.state is EligibilityStateName.FUTURE_ELIGIBLE and self.next_eligibility_date is None:
            raise ValueError(
                "future_eligible 必须给出预计可申请日期，否则学生无法安排桥接行动（Spec §16.1）"
            )
        if self.state is EligibilityStateName.NEEDS_CONFIRMATION and not self.reasons:
            raise ValueError("needs_confirmation 必须说明缺什么信息")
        return self


class MatchScoreBreakdown(CampusPathModel):
    """Spec §16.3 的六项权重。**只有 A5 允许产出分数。**

    拆开而不是只给一个百分比，是因为 §16.3 要求"每条结果必须显示为什么推荐"。
    """

    goal_alignment: float = Field(ge=0, le=1)
    gap_reduction_value: float = Field(ge=0, le=1)
    evidence_portfolio_value: float = Field(ge=0, le=1)
    workload_energy_fit: float = Field(ge=0, le=1)
    personal_preference_fit: float = Field(ge=0, le=1)
    event_quality_source_trust: float = Field(ge=0, le=1)


class MatchResult(CampusPathModel):
    """A5 产出。资格结论直接内嵌，避免"分数高但没资格"被单独展示。"""

    match_id: Identifier
    opportunity_id: OpportunityId
    eligibility: EligibilityAssessment
    score: float = Field(ge=0, le=1)
    breakdown: MatchScoreBreakdown
    gap_value: float = Field(ge=0)
    covered_requirement_ids: tuple[Identifier, ...] = ()
    reasons: tuple[LocalizedText, ...] = Field(min_length=1)
    risks: tuple[LocalizedText, ...] = ()
    workload_fit: Literal["comfortable", "tight", "over_capacity", "unknown"] = "unknown"
    quality_confidence: Confidence | None = Field(
        default=None, description="来自 Aggregation 的质量置信度；样本不足时为 None"
    )
    freshness_days: int | None = Field(default=None, ge=0)
    uncertainty: Uncertainty = Uncertainty.NONE
    #: 国际生逐机会注记（2026-08-02 修复批）：服务端从该机会自己的三态字段
    #: （accepts_international / sponsorship_support / language_requirements）与
    #: Pack 信封的准备动作提前量确定性派生——逐卡不同、缺就是缺、零 LLM。
    #: 学生未勾选国际生或未同意 Pack 时恒为空。
    intl_notes: tuple[LocalizedText, ...] = ()
    #: 1.32.0（审计黄-8）：这张卡服务于哪个目标——主/副配比（80/20）
    #: 此前对学生完全不可见、不可验证；无副目标时为 None。
    goal_role: Literal["primary", "candidate"] | None = None


class EligibilityExplanation(CampusPathModel):
    """A5 面向学生的解释。每条关键论断都要能回溯到来源（T8 < 2%）。"""

    opportunity_id: OpportunityId
    state: EligibilityStateName
    summary: LocalizedText
    what_is_missing: tuple[LocalizedText, ...] = ()
    when_reachable: LocalizedText | None = None
    supporting_provenance: tuple[Provenance, ...] = ()
    validation_id: ValidationId


# --------------------------------------------------------------------------
# A4 的产出：草稿与校验问题
# --------------------------------------------------------------------------


class ValidationIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


class ValidationIssue(CampusPathModel):
    """确定性 Schema 闸门的输出。blocking 项**直接丢弃并告警，不回喂 LLM 重试**
    （Spec §8.9.1 第 3 条）。"""

    code: str
    severity: ValidationIssueSeverity
    field_path: str | None = None
    detail: LocalizedText


class SourceIngestRequest(FrozenModel):
    """外部源摄入请求（R7-D）。``raw_content`` 是**不可信数据**：
    它只会作为数据块进入 A4 的模型调用，永不拼进 system prompt（§8.9.1）。"""

    source_id: Identifier
    source_url: str | None = Field(default=None, max_length=500)
    raw_content: str = Field(min_length=1, max_length=20_000)


class OpportunityDraft(CampusPathModel):
    """A4 产出。在通过闸门并被人工审核前，它既不进 Catalog 也不进学生上下文。

    A4 只有 ``read_source`` 与 ``emit_opportunity_draft`` 两个工具，
    因此本模型是 A4 唯一的对外出口（Spec §8.9.1 第 2 条）。
    """

    draft_id: Identifier
    source_id: Identifier
    extracted: Opportunity
    provenance: Provenance
    issues: tuple[ValidationIssue, ...] = ()
    duplicate_of: OpportunityId | None = None
    extraction_confidence: Confidence = 0.5

    @model_validator(mode="after")
    def _draft_is_never_published(self) -> "OpportunityDraft":
        allowed = {PublicationStatus.DRAFT, PublicationStatus.SUBMITTED}
        if self.extracted.publication_status not in allowed:
            raise ValueError(
                "A4 的草稿只能是 draft/submitted 状态——A4 没有发布权（Spec §8.9.1）"
            )
        return self


class ReviewSuggestion(CampusPathModel):
    """A4 给人工审核者的建议。**是建议，不是决定**——批准权在 Publishing Service。"""

    draft_id: Identifier
    suggested_decision: Literal["approve", "request_changes", "reject", "needs_human_judgment"]
    rationale: LocalizedText
    issues: tuple[ValidationIssue, ...] = ()
