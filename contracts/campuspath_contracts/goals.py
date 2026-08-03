"""Spec §14.3 目标与缺口，以及 A3 的 RequirementGraph / DynamicGapMap。

G3（多目标）：``GoalSet`` 支持 1 主目标 + 1 候选目标，A3 对两者都出 Requirement
Graph，并给出**共享缺口**与**分叉点**——这是"1 主 + 1 候选"在契约层的落点，
不是 UI 的展示技巧。

G4（成长曲线）：``GrowthTrajectory`` 是纯确定性派生视图（Spec §17.3.1），
不需要额外 Agent，因此放在契约层由服务计算。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    Confidence,
    DevelopmentModeType,
    EvidenceId,
    GoalId,
    Identifier,
    LocalizedText,
    Provenance,
    RequirementId,
    StrEnum,
    StudentId,
    TermCode,
    Uncertainty,
)


class GoalStatus(StrEnum):
    ACTIVE = "active"
    CANDIDATE = "candidate"
    PAUSED = "paused"
    ACHIEVED = "achieved"
    ABANDONED = "abandoned"


class GoalRole(StrEnum):
    """G3：一个主目标 + 一个候选目标。"""

    PRIMARY = "primary"
    CANDIDATE = "candidate"


class Horizon(StrEnum):
    NEXT_TWO_WEEKS = "next_two_weeks"
    THIS_TERM = "this_term"
    LONG_TERM = "long_term"  # 12–18 个月


class RequirementCategory(StrEnum):
    """出域时 ``MetricTuple.uncovered_requirement_categories`` 只携带这一层。

    它必须足够粗，粗到无法反推是哪位学生——所以是枚举而不是自由文本。
    """

    COURSEWORK = "coursework"
    TECHNICAL_SKILL = "technical_skill"
    RESEARCH_EXPERIENCE = "research_experience"
    INDUSTRY_EXPERIENCE = "industry_experience"
    PROJECT_PORTFOLIO = "project_portfolio"
    TEAMWORK_EVIDENCE = "teamwork_evidence"
    COMMUNICATION = "communication"
    CREDENTIAL = "credential"
    LANGUAGE = "language"
    NETWORK = "network"
    ELIGIBILITY_STATUS = "eligibility_status"


class GapLevel(StrEnum):
    MISSING = "missing"
    PARTIAL = "partial"
    SATISFIED = "satisfied"
    UNKNOWN = "unknown"


class Goal(CampusPathModel):
    """一个目标 = **一个方向** + 学生在那个框架下写下的具体终点。

    ``development_mode`` 是 Spec 明确针对的五类人群（就业 / 深造 / 创业 /
    探索中 / 发展个人特长）。它先于 ``target_name`` 存在，因为"入职某公司"
    与"读某个博士项目"在要求图上根本不是同一类东西——先定方向，
    Requirement Graph 才有框架可依。

    ``exploration`` 是一等公民，不是"还没想好"的占位：Spec §16.1 明确
    "暂时不确定"是一种合法状态，系统不得逼学生先编一个目标出来。
    """

    goal_id: GoalId
    student_id: StudentId
    role: GoalRole
    development_mode: DevelopmentModeType
    target_type: Literal["role", "industry", "program", "skill", "exploration"]
    target_name: str = Field(max_length=200)
    horizon: Horizon = Horizon.LONG_TERM
    confidence: Confidence = 0.5
    status: GoalStatus = GoalStatus.ACTIVE
    alternatives: tuple[str, ...] = ()
    created_at: datetime
    last_reviewed: datetime | None = None


class GoalSet(CampusPathModel):
    """G3 的契约形态：最多一个主目标 + 一个候选目标。"""

    student_id: StudentId
    primary: Goal
    candidate: Goal | None = None

    @model_validator(mode="after")
    def _roles_match(self) -> "GoalSet":
        if self.primary.role is not GoalRole.PRIMARY:
            raise ValueError("primary 的 role 必须是 primary")
        if self.candidate is not None:
            if self.candidate.role is not GoalRole.CANDIDATE:
                raise ValueError("candidate 的 role 必须是 candidate")
            if self.candidate.goal_id == self.primary.goal_id:
                raise ValueError("主目标与候选目标不能是同一个 goal_id")
        return self


class Requirement(CampusPathModel):
    requirement_id: RequirementId
    goal_id: GoalId
    category: RequirementCategory
    description: LocalizedText
    level: Literal["entry", "competitive", "exceptional"] = "entry"
    source: Provenance | None = None
    mandatory: bool = True
    prerequisite_requirement_ids: tuple[RequirementId, ...] = ()
    validity_period_months: int | None = Field(default=None, ge=1)


class RequirementGraph(CampusPathModel):
    """A3 输出，可缓存（key = goal_id + program + catalog_year + pack 版本）。"""

    graph_id: Identifier
    goal_id: GoalId
    requirements: tuple[Requirement, ...] = Field(min_length=1)
    generated_at: datetime
    pack_ids: tuple[Identifier, ...] = Field(
        default=(), description="参与生成的 Context Pack / Career Path Pack"
    )
    cache_key: str

    @model_validator(mode="after")
    def _prerequisites_resolve(self) -> "RequirementGraph":
        known = {r.requirement_id for r in self.requirements}
        for r in self.requirements:
            missing = [p for p in r.prerequisite_requirement_ids if p not in known]
            if missing:
                raise ValueError(f"{r.requirement_id} 依赖图外的要求：{missing}")
        return self


class Gap(CampusPathModel):
    gap_id: Identifier
    student_id: StudentId
    requirement_id: RequirementId
    goal_id: GoalId
    gap_level: GapLevel
    evidence_ids: tuple[EvidenceId, ...] = ()
    priority: int = Field(ge=1, le=5, description="1 最高。由 A3 给出优先级，不是取舍分数")
    uncertainty: Uncertainty = Uncertainty.NONE
    estimated_reach_date: date | None = None
    estimated_reach_term: TermCode | None = None

    @model_validator(mode="after")
    def _satisfied_needs_evidence(self) -> "Gap":
        if self.gap_level is GapLevel.SATISFIED and not self.evidence_ids:
            raise ValueError("判定为 satisfied 的缺口必须引用至少一条 Evidence")
        return self


class SharedGap(CampusPathModel):
    """G3：主目标与候选目标共同需要的缺口——学生做这件事两条路都不亏。"""

    requirement_ids_primary: tuple[RequirementId, ...] = Field(min_length=1)
    requirement_ids_candidate: tuple[RequirementId, ...] = Field(min_length=1)
    category: RequirementCategory
    description: LocalizedText


class DivergencePoint(CampusPathModel):
    """G3：两条路开始要求不同投入的时点，也是学生必须做选择的时点。"""

    at_term: TermCode
    description: LocalizedText
    primary_only_requirement_ids: tuple[RequirementId, ...] = ()
    candidate_only_requirement_ids: tuple[RequirementId, ...] = ()


class DynamicGapMap(CampusPathModel):
    """A3 输出。同时覆盖主目标与候选目标（G3）。"""

    map_id: Identifier
    student_id: StudentId
    generated_at: datetime
    primary_goal_id: GoalId
    candidate_goal_id: GoalId | None = None
    gaps: tuple[Gap, ...] = ()
    shared_gaps: tuple[SharedGap, ...] = ()
    divergence_points: tuple[DivergencePoint, ...] = ()
    unknowns: tuple[LocalizedText, ...] = ()

    @model_validator(mode="after")
    def _no_comparison_without_candidate(self) -> "DynamicGapMap":
        if self.candidate_goal_id is None and (self.shared_gaps or self.divergence_points):
            raise ValueError("没有候选目标时不应产出共享缺口或分叉点")
        return self


class GoalReview(CampusPathModel):
    """目标信心显著变化时由 A3 发起（Spec §16.9）。"""

    review_id: Identifier
    student_id: StudentId
    goal_id: GoalId
    trigger: str
    confidence_before: Confidence
    confidence_after: Confidence
    comparison: tuple[LocalizedText, ...] = ()
    recommended_action: Literal["keep", "swap_with_candidate", "add_candidate", "pause"] = "keep"
    created_at: datetime


class GrowthTrajectoryPoint(CampusPathModel):
    term: TermCode
    gaps_closed: int = Field(ge=0)
    new_confirmed_evidence: int = Field(ge=0)
    goal_confidence: Confidence
    verified_growth_actions: int = Field(ge=0)


class GrowthTrajectory(CampusPathModel):
    """G4（Spec §17.3.1）。纯派生，无 Agent 参与，因此可被逐字段单测。"""

    student_id: StudentId
    goal_id: GoalId
    points: tuple[GrowthTrajectoryPoint, ...] = Field(min_length=1)
    computed_at: datetime


class VgaMonthPoint(CampusPathModel):
    """北极星指标 VGA 的单月桶（Spec §17.1：VGA / Active Student / Month）。"""

    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    count: int = Field(ge=0)


class VgaSummary(CampusPathModel):
    """北极星指标 VGA 汇总（2026-08-04 落地）：纯派生视图，从 Event Store
    （ActionEvent.verified_growth=True 且 result=succeeded）逐月聚合。
    0 是事实不是缺数据——months 可为空，端点不许因此 404。"""

    student_id: StudentId
    current_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    current_month_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    months: tuple[VgaMonthPoint, ...] = ()
    computed_at: datetime


class RequirementFacet(CampusPathModel):
    """目标拆解的一个条目（2026-07-31 用户需求 D）。

    三层分类来自用户裁定的口径（对齐招聘/猎头看人的通行维度）：

    * ``hard`` —— 学分课程、证书语言、可验证项目/实习/研究经历；
    * ``soft`` —— 表达沟通、领导力协作、人脉等个人素质，**必须写明取证来源**
      （俱乐部职务、黑客松、leadership 课程……），不许凭空断言；
    * ``constraint`` —— 地域/国籍/工作授权等外部硬约束，
      International Student Context Pack 加载后展开更多。
    """

    category: RequirementCategory
    kind: Literal["hard", "soft", "constraint"]
    description: LocalizedText
    evidence_sources: tuple[LocalizedText, ...] = Field(
        default=(), description="从学生的哪些经历/活动取证（soft 项必填的理由所在）"
    )
    resource_channels: tuple[str, ...] = Field(
        default=(), description="建议的资源渠道（OpportunityType 值）"
    )
    # ── 市场证据加权（A，2026-08-02）：来自离线编译流水线（JD 语料 +
    #    去标识履历聚合），编制期人工复核后入库——不是运行时模型判断。
    #: core = 市场证据加权的重点项（前端加粗 + 下划线强调）
    priority: Literal["core", "standard"] = "standard"
    #: 权重依据的两组实测数字（如「10 份 JD 中 9 份要求；30 份履历 24 份具备」）
    market_note: LocalizedText | None = None
    #: 指向权威证据参考表（evidence_catalog）条目 id，前端展开为可点官方链接
    evidence_refs: tuple[str, ...] = Field(default=(), max_length=8)
    #: 条目出处（现场拆解·提案 #27，执行者 A3）：compiled = 离线编译
    #: 流水线产物（人工复核过）；ai_live = 后台研究任务的模型产出——
    #: 前端必须标注「AI 现场拆解·待核验」，两种来源不许混淆显示。
    origin: Literal["compiled", "ai_live"] = "compiled"

    @model_validator(mode="after")
    def _soft_needs_evidence_sources(self) -> "RequirementFacet":
        if self.kind == "soft" and not self.evidence_sources:
            raise ValueError("软性要求必须写明取证来源——不可凭空断言个人素质")
        return self


class DecompositionResearchJob(CampusPathModel):
    """现场 AI 拆解的后台任务（用户提案 #27；执行者是 A3 GoalGapAgent）。

    任务跑在**服务端**——学生切页/关页不打断，回来轮询即接上进度。
    进度是三段式确定性汇报（收集/归类/合成），不是模型自报的百分比。
    每人每日限 2 次（防 token 失控），预编制画像命中的岗位不需要它。
    """

    job_id: Identifier
    student_id: Identifier
    goal_id: GoalId
    state: Literal["running", "done", "failed"]
    progress: int = Field(ge=0, le=100)
    stage: LocalizedText
    started_at: datetime
    finished_at: datetime | None = None
    #: done 时产出的 facets（origin 恒为 ai_live）；running/failed 为空
    facets: tuple[RequirementFacet, ...] = ()
    error: str | None = None
    #: 今日剩余可用次数（含本次扣减后）
    daily_remaining: int = Field(ge=0)


class GoalDecomposition(CampusPathModel):
    """一个目标的完整要求拆解（A3 按 Career Path Pack 内容表确定性产出）。

    这是"每类人一个 skill"在本架构里的落点：内容是 **Pack 数据**，
    产出方仍是 A3、编排方仍是 A5——不新增 Agent，不复制流程（§5.9）。
    """

    goal_id: GoalId
    development_mode: DevelopmentModeType
    facets: tuple[RequirementFacet, ...] = Field(min_length=1)
    special_note: LocalizedText | None = Field(
        default=None, description="约束层的补充说明（如 intl Pack 未加载时的占位提示）"
    )
    # ── 国际生准备列（用户增补 B，2026-08-02）。API 层在 Pack 已勾选+同意时
    #    从求值信封派生填充（preparation_actions / constraints / 缺失证据），
    #    **不是模型现猜**；空 = 未勾选/未同意/不适用。程度差异（如"不留在
    #    中国则语言证书非必需"）由 Pack 规则的 goal_type/jurisdiction 条件给出。
    intl_facets: tuple[RequirementFacet, ...] = ()
    intl_pack_version: str | None = None
    intl_review_required: bool = False
    #: 命中的岗位画像（A，2026-08-02）：按 Goal.target_name 确定性关键词匹配；
    #: None = 回落到方向级通用 Pack
    role_profile: str | None = None
