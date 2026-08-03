"""Spec §6.9 / §6.11 / §14.4：发布授权、审核状态机与来源健康。

状态机在契约层给出**唯一合法迁移表**（:data:`ALLOWED_TRANSITIONS`）。
D5 要求"退回修改"与"驳回"两条分支各演示一次，B7 要求越权投稿全部被拦截——
两者都需要一个可被测试直接遍历的迁移表，而不是散落在 if/else 里的实现细节。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    ActorRole,
    CampusPathModel,
    FrozenModel,
    Identifier,
    LocalizedText,
    StrEnum,
)
from .opportunity import Opportunity, PublicationStatus, ValidationIssue

#: 状态机的唯一真相。任何实现都必须查这张表，不得自行判断。
ALLOWED_TRANSITIONS: dict[PublicationStatus, frozenset[PublicationStatus]] = {
    PublicationStatus.DRAFT: frozenset({PublicationStatus.SUBMITTED, PublicationStatus.WITHDRAWN}),
    PublicationStatus.SUBMITTED: frozenset({PublicationStatus.AUTO_CHECKED, PublicationStatus.WITHDRAWN}),
    PublicationStatus.AUTO_CHECKED: frozenset(
        {PublicationStatus.IN_REVIEW, PublicationStatus.REJECTED, PublicationStatus.APPROVED}
    ),
    PublicationStatus.IN_REVIEW: frozenset(
        {
            PublicationStatus.CHANGES_REQUESTED,
            PublicationStatus.REJECTED,
            PublicationStatus.APPROVED,
        }
    ),
    PublicationStatus.CHANGES_REQUESTED: frozenset(
        {PublicationStatus.SUBMITTED, PublicationStatus.WITHDRAWN}
    ),
    PublicationStatus.APPROVED: frozenset({PublicationStatus.PUBLISHED, PublicationStatus.WITHDRAWN}),
    PublicationStatus.PUBLISHED: frozenset(
        {PublicationStatus.UPDATED, PublicationStatus.EXPIRED,
         PublicationStatus.WITHDRAWN, PublicationStatus.ARCHIVED}
    ),
    PublicationStatus.UPDATED: frozenset(
        {PublicationStatus.IN_REVIEW, PublicationStatus.PUBLISHED,
         PublicationStatus.EXPIRED, PublicationStatus.WITHDRAWN}
    ),
    PublicationStatus.REJECTED: frozenset({PublicationStatus.ARCHIVED}),
    PublicationStatus.EXPIRED: frozenset({PublicationStatus.ARCHIVED, PublicationStatus.UPDATED}),
    PublicationStatus.WITHDRAWN: frozenset({PublicationStatus.ARCHIVED}),
    PublicationStatus.ARCHIVED: frozenset(),
}

#: 已发布内容被修改后必须重新审核的字段（Spec §11.3 失败样本：改了截止日期却没复审）。
REVIEW_TRIGGERING_FIELDS = frozenset({"deadline", "eligibility_rules", "official_url", "starts_at"})


class TransitionNotAllowed(ValueError):
    """尝试了迁移表之外的状态变更。"""


def assert_transition_allowed(current: PublicationStatus, target: PublicationStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise TransitionNotAllowed(f"不允许的状态迁移：{current.value} → {target.value}")


class PublisherRoleGrant(CampusPathModel):
    """Spec §14.4。授权是**受限的**：限组织、限分类、限期限（D5）。"""

    grant_id: Identifier
    principal_id: Identifier
    organization_id: Identifier
    role: Literal[ActorRole.PUBLISHER, ActorRole.REVIEWER, ActorRole.CURATOR]
    allowed_categories: tuple[str, ...] = Field(min_length=1)
    can_publish_directly: bool = False
    valid_from: date
    valid_to: date
    granted_by: Identifier
    revoked_at: datetime | None = None

    def is_active_on(self, when: date) -> bool:
        if self.revoked_at is not None:
            return False
        return self.valid_from <= when <= self.valid_to

    def covers(self, organization_id: str, category: str, when: date) -> bool:
        """B7 的判定入口。三项全中才算有权，缺一即越权。"""
        return (
            self.is_active_on(when)
            and self.organization_id == organization_id
            and category in self.allowed_categories
        )


class ScopeViolation(FrozenModel):
    """越权尝试的审计记录。B7 要求被拦截**且记录**，只拦不记不算通过。"""

    violation_id: Identifier
    principal_id: Identifier
    attempted_organization_id: Identifier
    attempted_category: str
    grant_id: Identifier | None = None
    reason: Literal["no_grant", "wrong_organization", "category_not_allowed",
                    "grant_expired", "direct_publish_not_allowed", "role_not_granted"]
    occurred_at: datetime


class SubmissionAttachment(FrozenModel):
    """投稿附件。与证据上传同一纪律：demo 只存元数据与 vault 引用，不存 blob。"""

    file_name: str = Field(min_length=1, max_length=255)
    content_type: str = Field(min_length=1, max_length=100)
    size_bytes: int = Field(ge=0, le=20_000_000)
    object_ref: str = Field(min_length=1, max_length=500)


class PublicationSubmission(CampusPathModel):
    submission_id: Identifier
    owner_principal_id: Identifier
    organization_id: Identifier
    draft_version: int = Field(ge=1)
    content: Opportunity
    category_tags: tuple[str, ...] = Field(min_length=1)
    source_evidence: tuple[str, ...] = ()
    status: PublicationStatus = PublicationStatus.DRAFT
    auto_check_issues: tuple[ValidationIssue, ...] = ()
    submitted_at: datetime | None = None
    current_reviewer_id: Identifier | None = None
    # R7-B（2026-08-01）：投稿人自报的活动详情，审核队列据此裁决。
    # 全部可选——契约不逼旧投稿补历史字段，门户 UI 负责要求填写。
    applicant_name: str | None = Field(default=None, max_length=120)
    applicant_contact: str | None = Field(default=None, max_length=200)
    event_description: str | None = Field(default=None, max_length=4000)
    signup_method: str | None = Field(default=None, max_length=500)
    attachment: SubmissionAttachment | None = None

    @model_validator(mode="after")
    def _review_states_need_context(self) -> "PublicationSubmission":
        if self.status is not PublicationStatus.DRAFT and self.submitted_at is None:
            raise ValueError("离开 draft 的投稿必须有 submitted_at")
        if self.status is PublicationStatus.IN_REVIEW and self.current_reviewer_id is None:
            raise ValueError("in_review 必须有明确的审核人，否则审核责任无归属")
        return self


class ModerationDecision(FrozenModel):
    """人工审核的一次决定。不可变——改判需新增一条记录。"""

    decision_id: Identifier
    submission_id: Identifier
    submission_version: int = Field(ge=1)
    reviewer_id: Identifier
    decision: Literal["approve", "request_changes", "reject"]
    reasons: tuple[LocalizedText, ...] = Field(min_length=1)
    policy_checks: tuple[str, ...] = ()
    timestamp: datetime

    @property
    def target_status(self) -> PublicationStatus:
        return {
            "approve": PublicationStatus.APPROVED,
            "request_changes": PublicationStatus.CHANGES_REQUESTED,
            "reject": PublicationStatus.REJECTED,
        }[self.decision]


# --------------------------------------------------------------------------
# Source Health（Spec §6.11）
# --------------------------------------------------------------------------


class OpportunityAdminEdit(CampusPathModel):
    """B10（2026-08-01 用户裁定）：审核批准后的生命周期管理——
    活动取消/改期时，Career Center 可直接修改或下架已发布条目。
    全部字段可选：只改给了值的。"""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    deadline: datetime | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    official_url: str | None = Field(default=None, max_length=500)


class SourceKind(StrEnum):
    OPPORTUNITY_SOURCE = "opportunity_source"
    EDUCATION_CONNECTOR = "education_connector"
    # 2026-08-02 用户裁定 B/G：政策/官方信息源——每日核查变更；
    # 变更只产出「政策更新提醒卡」（POLICY_UPDATE 类型），不产出可报名机会。
    POLICY_SOURCE = "policy_source"


class SourceCategory(StrEnum):
    """源注册表的业务分类（2026-08-02，来自 HKUST 资源地图转录）。"""

    ADMIN_DEPARTMENT = "admin_department"        # 行政与学生服务部门
    SCHOOL_ACADEMIC = "school_academic"          # 学院 / 学系 / 学术单位
    CENTRAL_CALENDAR = "central_calendar"        # 中央活动日历
    CAREER_INTERNSHIP = "career_internship"      # 实习就业 / 招聘
    ENTREPRENEURSHIP = "entrepreneurship"        # 创业孵化 / 比赛
    RESEARCH_UROP = "research_urop"              # 科研 / UROP / 实验室招募
    EXCHANGE_CROSS_UNI = "exchange_cross_uni"    # 交换 / 跨校 / 联培
    CLUB_ALUMNI = "club_alumni"                  # 社团 / 校友目录
    POLICY = "policy"                            # 政策源（含留学生政策）
    EDUCATION_SYSTEM = "education_system"        # SIS/LMS/课程目录等教育系统连接器


class RegisteredSource(CampusPathModel):
    """官方信息源注册表条目（2026-08-02 用户裁定 C）。

    真实抓取回路的单一事实来源：console 源列表、变更检测、
    直发广场白名单判定都从这里读。**mock 源与真实源同表登记、
    `is_real_fetch` 显式区分**——界面与 Spec 都要如实标注（用户裁定 D）。
    """

    source_id: Identifier
    name: LocalizedText
    url: str = Field(min_length=1, max_length=500)
    kind: SourceKind
    category: SourceCategory
    priority: Literal["p0", "p1", "p2"] = "p2"
    render: Literal["static", "js"] = "static"
    entry_type: Literal["directory", "event_list", "program_hub", "policy_page"] = "event_list"
    #: True = 抓到的条目可能进广场（官方域名白名单内直发 Published）。
    opportunity_bearing: bool = False
    #: 接入深度（console 与 Spec 都如实标注）：full_chain = 有专用解析器、
    #: 变更后逐条抽取活动直发广场；change_monitor = 只做变更检测与健康度。
    extraction_depth: Literal["full_chain", "change_monitor"] = "change_monitor"
    #: True = 真实抓取源；False = mock/合成源（如 SRC-partner-ats）。
    is_real_fetch: bool = True
    last_checked_at: datetime | None = None
    last_changed_at: datetime | None = None
    content_hash: str | None = Field(default=None, max_length=64)
    #: 政策源受众（2026-08-02 修复批，落实广场双政策分类）：
    #: ``intl`` → 政策卡归 ``intl_policy``（留学生相关政策，仅勾选国际生可见）；
    #: ``all`` → 归 ``policy``（政策相关，所有人可见）。非政策源为 None。
    policy_audience: Literal["intl", "all"] | None = None
    #: 最近一次抓取结果；mock 源恒为 unknown（没有可抓的网页）。
    last_fetch_status: Literal["ok", "unreachable", "unknown"] = "unknown"
    #: 全链源最近一次抽取发布的条目数；None = 非全链源或尚未抽取。
    #: 「页面 changed 但抽出 0 条」= 解析器可能被上游改版打断（审查 #13）。
    last_extracted_count: int | None = Field(default=None, ge=0)
    status: Literal["active", "paused"] = "active"

    @property
    def official_hkust(self) -> bool:
        """直发广场白名单：仅 HKUST 官方域名（用户裁定 A——
        能上学校官网的信息本身已被学校筛过一遍，不再人工复审）。"""
        host = self.url.split("//", 1)[-1].split("/", 1)[0].lower()
        return (host in ("hkust.edu.hk", "ust.hk")
                or host.endswith(".hkust.edu.hk") or host.endswith(".ust.hk"))


class SourceHealth(CampusPathModel):
    """Spec §6.11 的八项运维指标。**不展示任何原文或学生数据。**"""

    source_id: Identifier
    kind: SourceKind
    last_successful_sync: datetime | None = None
    fetch_auth_status: Literal["ok", "rate_limited", "auth_expired", "unreachable", "unknown"] = "unknown"
    parse_success_rate: float = Field(ge=0, le=1)
    freshness_hours: float | None = Field(default=None, ge=0)
    broken_link_rate: float = Field(ge=0, le=1)
    deadline_consistency_issues: int = Field(ge=0)
    schema_coverage_rate: float = Field(ge=0, le=1)
    duplicate_conflict_signals: int = Field(ge=0)
    checked_at: datetime


# --------------------------------------------------------------------------
# 活动数据闭环（D 批，2026-08-02 用户裁定）：签到 / 实时评分 / 周期报告
# --------------------------------------------------------------------------
# 隐私口径与 F23 完全一致：评分载荷仍是去标识 EventQualityFeedback；
# 签到记录留在运营域（只出计数）；报告只出聚合行，低于 MIN_CELL_N 抑制。
# **报告端点仅 career_center_admin 可见**（用户裁定：学生与其他角色无权限）。

from .aggregation import DimensionAggregate  # noqa: E402  （同包契约，无环）
from .reflection import FitTag  # noqa: E402  （同包契约，无环）


class EventCheckinInfo(CampusPathModel):
    """每活动唯一签到码（管理端可见）。token 是服务端签发的不透明串——
    二维码内容 = checkin_url，学生扫码登录后 POST 签到。"""

    opportunity_id: Identifier
    token: str = Field(pattern=r"^chk_[0-9a-f]{32}$")
    checkin_url: str = Field(max_length=300)
    attend_count: int = Field(ge=0)
    #: 活动结束 + 2 个月后停止统计（签到与评分都不再收）
    stats_frozen: bool = False
    #: 用户细化（2026-08-02）：活动开始**当天**才开始计数
    opens_on: date | None = None
    counting_open: bool = True


class CheckinRequest(CampusPathModel):
    opportunity_id: Identifier
    token: str = Field(pattern=r"^chk_[0-9a-f]{32}$")


class CheckinResult(CampusPathModel):
    opportunity_id: Identifier
    accepted: bool
    already_checked_in: bool = False
    attend_count: int = Field(ge=0)


class FitShare(CampusPathModel):
    """契合标签在已验证反馈中的占比（2026-08-04 用户裁定上呈现层）。

    契合是**个人判断**（§17.4 Personal-vs-Global Separation），不折进
    质量分——但它的**分布**是给主办方的有效信号（"40% 说太基础" =
    受众标注要改）。以独立字段出域、前端独立分区展示，隔离不破。"""

    fit: FitTag
    share: float = Field(ge=0, le=1)


class OccurrenceQualitySummary(CampusPathModel):
    """plaza-admin 活动卡上的实时统计行。低于样本阈值时分数字段为 None、
    逐维与契合分布为空（前端显示 Insufficient evidence，不显示假精确）。"""

    opportunity_id: Identifier
    feedback_n: int = Field(ge=0)
    verified_n: int = Field(ge=0)
    attend_count: int = Field(ge=0)
    avg_overall: float | None = Field(default=None, ge=1, le=5)
    #: 真实好评率 = 验证参加者中均分 ≥4 的比例（分母只算 verified）
    favorable_rate: float | None = Field(default=None, ge=0, le=1)
    dimensions: tuple[DimensionAggregate, ...] = ()
    #: 契合分布（同受 k-匿名阈值约束，见 validator）
    fit_distribution: tuple[FitShare, ...] = ()
    stats_frozen: bool = False
    stats_until: datetime | None = None

    @model_validator(mode="after")
    def _fit_needs_threshold(self) -> "OccurrenceQualitySummary":
        from .aggregation import MIN_CELL_N

        if self.verified_n < MIN_CELL_N and self.fit_distribution:
            raise ValueError(
                f"verified_n={self.verified_n} 低于阈值 {MIN_CELL_N}，"
                "不得输出契合分布（B9 同一条纪律）")
        return self


class ReportPeriod(StrEnum):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    TERM = "term"
    YEAR = "year"


class ReportGroupRow(CampusPathModel):
    key: str = Field(max_length=120)
    label: LocalizedText | None = None
    activities_n: int = Field(ge=0)
    feedback_n: int = Field(ge=0)
    verified_n: int = Field(ge=0)
    #: None = 该分组维度下无法归因（如按学院——签到挂在活动上不挂学院），
    #: 不许填 0 冒充「无人到场」（审查 #11）。
    attend_count: int | None = Field(default=None, ge=0)
    avg_overall: float | None = Field(default=None, ge=1, le=5)
    favorable_rate: float | None = Field(default=None, ge=0, le=1)


class QualityReport(CampusPathModel):
    """周期性活动反馈报告（模板见 docs/quality-report-template.md）。

    统计全部确定性；`narrative` 是唯一的模型产物（输入只有本报告的
    聚合 JSON——无任何个体数据），无模型后端时为 None 并在 data_notes 注明。
    """

    report_id: Identifier
    period: ReportPeriod
    window_start: date
    window_end: date
    generated_at: datetime
    activities_total: int = Field(ge=0)
    feedback_total: int = Field(ge=0)
    verified_total: int = Field(ge=0)
    attend_total: int = Field(ge=0)
    by_organizer: tuple[ReportGroupRow, ...] = ()
    by_type: tuple[ReportGroupRow, ...] = ()
    by_school: tuple[ReportGroupRow, ...] = ()
    top_activities: tuple[ReportGroupRow, ...] = ()
    coverage_gaps: tuple[LocalizedText, ...] = ()
    narrative: LocalizedText | None = None
    data_notes: tuple[LocalizedText, ...] = ()


class SourcesSweepJob(CampusPathModel):
    """一键刷新全部真实源（2026-08-02 用户需求 C）。

    服务端后台线程逐源真实抓取 + 变更检测；进度 = ``done/total`` 确定性计数，
    不是模型自估。同一时间只允许一个巡检在跑（409）。mock 源与 paused 源跳过。
    """

    job_id: Identifier
    state: Literal["running", "done", "failed"]
    total: int = Field(ge=0)
    done: int = Field(ge=0)
    changed: int = Field(ge=0)
    errors: int = Field(ge=0)
    started_at: datetime
    finished_at: datetime | None = None
    error: str | None = None


class QualityReportJob(CampusPathModel):
    """报告生成后台任务：服务端线程 + 确定性分段进度，切页/关页不中断
    （与目标拆解研究任务同一交互模式）。"""

    job_id: Identifier
    period: ReportPeriod
    state: Literal["running", "done", "failed"]
    progress: int = Field(ge=0, le=100)
    stage: LocalizedText
    started_at: datetime
    finished_at: datetime | None = None
    report: QualityReport | None = None
    error: str | None = None
