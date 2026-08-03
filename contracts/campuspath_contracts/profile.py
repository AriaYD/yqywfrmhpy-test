"""Spec §14.1：学生 Profile、经历与证据。

关键契约：**Profile 的高影响写入必须经过 Proposal → 学生确认 → ChangeEvent 三段**
（Spec §8.2.2、B3 Unconfirmed Profile Write = 0）。
因此 :class:`StudentProfile` 没有任何"直接 setter"语义的模型——
写入路径的唯一入口是 :class:`ProfileUpdateProposal`。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    Confidence,
    DateRange,
    DevelopmentModeType,
    EvidenceId,
    FrozenModel,
    Identifier,
    IntensityMode,
    NoteId,
    StrEnum,
    StudentId,
    VerificationStatus,
    Visibility,
)


class ExperienceType(StrEnum):
    INTERNSHIP = "internship"
    PART_TIME = "part_time"
    RESEARCH = "research"
    PROJECT = "project"
    COMPETITION = "competition"
    CLUB = "club"
    VOLUNTEER = "volunteer"
    ENTREPRENEURSHIP = "entrepreneurship"
    EXCHANGE = "exchange"
    OTHER = "other"


class SkillSourceType(StrEnum):
    COURSE = "course"
    EXPERIENCE = "experience"
    PROJECT = "project"
    SELF_ASSESSED = "self_assessed"
    CERTIFICATE = "certificate"
    AGENT_INFERRED = "agent_inferred"


class SkillLevel(StrEnum):
    AWARE = "aware"
    PRACTICING = "practicing"
    PROFICIENT = "proficient"
    ADVANCED = "advanced"


class ConsentScope(StrEnum):
    """Spec §13：每一类数据的读取都要有独立同意，不做打包授权。"""

    SIS_RECORDS = "sis_records"
    LMS_RECORDS = "lms_records"
    #: 一级：只知道某个时段忙或不忙。默认，也是唯一在 onboarding 里预开的日历权限。
    CALENDAR_FREEBUSY = "calendar_freebusy"
    #: 二级：额外读取**事件标题**。默认关闭，学生单独授权。
    #:
    #: 开这一级换来的能力是"看得见你把时间花在哪，才能建议你把哪一项挪开"——
    #: 只知道忙/闲的系统只能说"你没空了"，说不出"这个周三的例会也许可以缺一次"。
    #: 关着它，其余功能照常：容量算术只需要忙/闲。
    CALENDAR_EVENT_TITLES = "calendar_event_titles"
    CALENDAR_WRITE = "calendar_write"
    SELF_REPORTED_WELLBEING = "self_reported_wellbeing"
    WELLBEING_OUTREACH = "wellbeing_outreach"
    ANONYMOUS_AGGREGATION = "anonymous_aggregation"
    MEMORY_RETENTION = "memory_retention"
    #: 国际学生规则包（B，2026-08-02）：勾选「我是国际生」即请求此同意；
    #: 撤销 = 全局卸载 Pack（拆解/推荐/时间线的 intl 注记一并消失）。
    CONTEXT_PACK = "context_pack"


class ProfileSelfEdit(CampusPathModel):
    """R4-G（2026-07-31）：学生本人直接编辑档案（LinkedIn 式 Edit）。

    与 B3 不冲突：提议→裁决路径挡的是 **Agent** 暗改档案；学生改自己的
    标签与经历不需要谁批准（先例：目标就是学生直接写的）。
    字段都可选——只改提供的部分。
    """

    interests: tuple[str, ...] | None = Field(default=None, max_length=30)
    experiences: tuple["ExperienceRecord", ...] | None = Field(
        default=None, max_length=50,
        description="整组替换本人的经历记录；每条 student_id 必须是本人")
    #: 国际学生上下文（B/F，2026-08-02）：档案页唯一入口。
    #: 提供即整体替换；显式置 null 走 clear_intl_context 标志（见下）。
    intl_context: InternationalStudentContext | None = None
    #: True = 取消「我是国际生」勾选（撤销同意 + 全局卸载）。
    #: 单独一个标志是因为"没传 intl_context"与"要清空它"必须可区分。
    clear_intl_context: bool = False
    #: 主/副目标推荐配比（2026-08-02）：目标工作室的配比控件写这里。
    candidate_goal_share: float | None = Field(default=None, ge=0.0, le=0.5)


class ConsentUpdateRequest(CampusPathModel):
    """学生自助开关**单项**同意（§13 不打包授权在端点形状上强制：一次一项）。

    撤销即时生效；授权回执由服务端签发（B13），请求体里没有它的位置。
    """

    scope: ConsentScope
    granted: bool


class ConsentRecord(CampusPathModel):
    scope: ConsentScope
    granted: bool
    granted_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    receipt_id: Identifier | None = Field(
        default=None, description="同意回执，用于审计（B13）"
    )

    @property
    def is_active(self) -> bool:
        return self.granted and self.revoked_at is None


class EnergyProfile(CampusPathModel):
    """Spec §16.7。全部由学生显式设置，**不得从空白日历反推**（§16.8.2）。"""

    weekly_discretionary_hours: float = Field(ge=0, le=80)
    preferred_intensity: IntensityMode = IntensityMode.BALANCED
    max_parallel_commitments: int = Field(default=2, ge=1, le=10)
    social_preference: Literal["solo", "small_group", "large_group", "mixed"] = "mixed"
    min_buffer_ratio: float = Field(
        default=0.2, ge=0.0, le=0.6,
        description="未安排缓冲下限，默认 20%（Spec §16.8）",
    )
    sleep_window_start: str | None = Field(
        default=None, pattern=r"^\d{2}:\d{2}$",
        description="学生显式设置的睡眠保护窗口起点；None 表示未设置，"
                    "此时 sleep_opportunity 信号不得触发",
    )
    sleep_window_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    recovery_preference_defined: bool = Field(
        default=False,
        description="Spec §16.8.2：未定义恢复偏好时 recovery_absent 信号不得触发",
    )


class StudentConstraint(CampusPathModel):
    kind: Literal["commute", "caregiving", "financial", "accessibility", "visa", "other"]
    description: str = Field(max_length=500)
    hard: bool = Field(default=False, description="hard=True 时进入 Rules 硬约束")


class DevelopmentMode(CampusPathModel):
    """Spec §14.3。学生可以同时属于多种模式，权重之和不强制为 1。"""

    mode: DevelopmentModeType
    weight: float = Field(ge=0.0, le=1.0)
    confidence: Confidence = 0.5


class InternationalStudentContext(CampusPathModel):
    """结构化国际学生上下文（用户裁定 F，2026-08-02：**不是**一个布尔开关）。

    存在即视为「我是国际生」已勾选；字段对齐 vendored Pack 的
    base/questions.yaml（integration-contract：这些字段归 Student Profile 所有，
    政策规则归 Pack 所有）。institution / programme_level / expected_graduation
    不重复存——求值时从 StudentProfile 本体派生，一份事实一个出处。
    """

    study_jurisdiction: Literal["HK-SAR", "CN-MAINLAND", "other"]
    intended_work_jurisdiction: Literal["HK-SAR", "CN-MAINLAND", "other"]
    study_mode: Literal["full_time", "part_time"] = "full_time"
    #: 当前证件/许可类别（如 student_visa）。自述，不是签发记录。
    permission_category: str = Field(min_length=1, max_length=80)
    permission_expiry_date: date
    intended_start_date: date | None = None
    #: None = 未确认（Pack 求值会把它列进 missing_information，不推断）
    school_approval: bool | None = None
    employer_sponsorship_expected: bool | None = None
    #: 语言能力证据（自述：如 "IELTS 7.0"、"HSK 6"）。是否需要考到多高
    #: 由目标方向决定——不留在中国发展则语言证书非必需（Pack 规则按
    #: goal_type/jurisdiction 条件给出程度差异，见目标拆解 intl 列）。
    language_evidence: tuple[str, ...] = Field(default=(), max_length=10)
    #: 目标城市（用户 B 提案字段；城市级政策差异 Pack 尚无 overlay，
    #: 求值会如实 needs_confirmation，不猜）
    target_cities: tuple[str, ...] = Field(default=(), max_length=5)
    updated_at: datetime


class StudentProfile(CampusPathModel):
    """L0 Canonical Profile（Spec §8.4）。只保存当前有效状态，历史在 Event Store。"""

    student_id: StudentId
    institution: str
    program_id: Identifier
    level: Literal["undergraduate", "postgraduate_taught", "postgraduate_research"]
    #: 年级来自校方记录（接真实系统 = 教务下发）。2026-08-03 用户裁定：
    #: 学生自述学期通道（曾有的 CurrentTerm y1s1–y4s2 与自选选择器）全部
    #: 撤除——学期语义全局只认教务 TermCode（seed manifest / SIS）。
    year: int = Field(ge=1, le=8)
    expected_graduation: date
    development_modes: tuple[DevelopmentMode, ...] = ()
    interests: tuple[str, ...] = ()
    constraints: tuple[StudentConstraint, ...] = ()
    #: 国际学生上下文（None = 未勾选/已取消）。勾选须伴随 context_pack 同意。
    intl_context: InternationalStudentContext | None = None
    #: 主/副目标推荐配比（2026-08-02 用户需求）：副（candidate）目标在活动与
    #: 选修推荐中的份额，0–0.5，默认 0.2（= 主 80% / 副 20%）。
    #: 只在学生同时有 primary + candidate 目标时生效；目标工作室可调。
    candidate_goal_share: float = Field(default=0.2, ge=0.0, le=0.5)
    energy_profile: EnergyProfile
    consent: tuple[ConsentRecord, ...] = ()
    version: int = Field(ge=1, description="每次确认写入 +1，与 ProfileChangeEvent 对应")
    updated_at: datetime

    def has_consent(self, scope: ConsentScope) -> bool:
        return any(c.scope is scope and c.is_active for c in self.consent)


class EvidenceRecord(CampusPathModel):
    """Spec §8.2.3：Evidence 独立留存，不随 Profile 更新消失。"""

    evidence_id: EvidenceId
    student_id: StudentId
    evidence_type: Literal[
        "certificate", "transcript", "artifact", "link", "award_letter",
        "reference", "screenshot", "other"
    ]
    source: str
    uri: str | None = None
    object_ref: str | None = Field(
        default=None, description="Private Vault 中的对象引用，按 student_id 前缀隔离"
    )
    issuer: str | None = None
    obtained_at: date
    verification_status: VerificationStatus = VerificationStatus.SELF_REPORTED
    visibility: Visibility = Visibility.PRIVATE
    checksum: str | None = None
    expires_at: date | None = None

    @model_validator(mode="after")
    def _needs_a_payload(self) -> "EvidenceRecord":
        if self.uri is None and self.object_ref is None:
            raise ValueError("EvidenceRecord 必须有 uri 或 object_ref 之一")
        return self


class Note(CampusPathModel):
    """学生或 Agent 的上下文说明。``text`` 是原文，永不进入聚合通路（B4）。"""

    note_id: NoteId
    student_id: StudentId
    author: Literal["student", "agent"]
    text: str | None = Field(default=None, max_length=20000)
    object_ref: str | None = None
    linked_entities: tuple[Identifier, ...] = ()
    visibility: Visibility = Visibility.PRIVATE
    created_at: datetime
    updated_at: datetime | None = None


class ExperienceRecord(CampusPathModel):
    experience_id: Identifier
    student_id: StudentId
    type: ExperienceType
    organization: str
    role: str
    period: DateRange
    responsibilities: tuple[str, ...] = ()
    outcomes: tuple[str, ...] = ()
    skills: tuple[Identifier, ...] = ()
    evidence_ids: tuple[EvidenceId, ...] = ()
    note_ids: tuple[NoteId, ...] = ()
    verification_status: VerificationStatus = VerificationStatus.SELF_REPORTED


class ProjectOutcome(CampusPathModel):
    project_id: Identifier
    student_id: StudentId
    project_type: Literal["course", "personal", "hackathon", "research", "startup"]
    title: str
    contribution: str = Field(max_length=2000)
    artifacts: tuple[str, ...] = ()
    measurable_result: str | None = None
    linked_course_id: Identifier | None = None
    linked_opportunity_id: Identifier | None = None
    evidence_ids: tuple[EvidenceId, ...] = ()


class Achievement(CampusPathModel):
    achievement_id: Identifier
    student_id: StudentId
    achievement_type: Literal["competition", "award", "scholarship", "certificate", "publication"]
    issuer: str
    level: Literal["department", "institution", "regional", "national", "international"]
    result: str
    prize: str | None = None
    issued_at: date
    expires_at: date | None = None
    verification_status: VerificationStatus = VerificationStatus.SELF_REPORTED
    evidence_ids: tuple[EvidenceId, ...] = ()


class SkillRecord(CampusPathModel):
    skill_id: Identifier
    student_id: StudentId
    level: SkillLevel
    source_type: SkillSourceType
    evidence_ids: tuple[EvidenceId, ...] = ()
    last_used_at: date | None = None
    confidence: Confidence = 0.5
    student_confirmed: bool = Field(
        default=False,
        description="agent_inferred 且未确认的技能不得进入 Canonical Profile（B3）",
    )

    @model_validator(mode="after")
    def _inferred_needs_confirmation(self) -> "SkillRecord":
        if self.source_type is SkillSourceType.AGENT_INFERRED and self.student_confirmed:
            if not self.evidence_ids:
                raise ValueError("被确认的推断技能必须至少引用一条 Evidence")
        return self


# --------------------------------------------------------------------------
# 写入路径：Proposal → 确认 → ChangeEvent
# --------------------------------------------------------------------------


class ProposalStatus(StrEnum):
    PENDING = "pending"
    EDITED = "edited"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ImpactLevel(StrEnum):
    """Spec §8.2.4：高影响推断不直接写入 Canonical Profile。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ProposedChange(CampusPathModel):
    # 1.32.0（2026-08-02 D 裁定）：Resume 模板化解析新增四类——教育/证书/
    # 语言/荣誉不再结构性丢弃；物化通道见 api.decide_proposal
    entity_type: Literal[
        "experience", "project", "achievement", "skill", "interest",
        "goal", "constraint", "energy_profile",
        "education", "certificate", "language", "honor"
    ]
    operation: Literal["add", "update", "remove"]
    field_path: str
    old_value: Any | None = None
    new_value: Any | None = None


class ProfileUpdateProposal(CampusPathModel):
    """A1 的输出。``status`` 只能由学生动作推进，Agent 不得自行置为 confirmed。"""

    proposal_id: Identifier
    student_id: StudentId
    proposed_changes: tuple[ProposedChange, ...] = Field(min_length=1)
    reason: str = Field(max_length=2000)
    source_event_ids: tuple[Identifier, ...] = ()
    evidence_ids: tuple[EvidenceId, ...] = ()
    impact: ImpactLevel = ImpactLevel.LOW
    status: ProposalStatus = ProposalStatus.PENDING
    created_at: datetime
    decided_at: datetime | None = None

    @model_validator(mode="after")
    def _decision_needs_timestamp(self) -> "ProfileUpdateProposal":
        terminal = {ProposalStatus.CONFIRMED, ProposalStatus.REJECTED, ProposalStatus.EDITED}
        if self.status in terminal and self.decided_at is None:
            raise ValueError(f"status={self.status.value} 必须带 decided_at")
        return self


class ProfileChangeEvent(FrozenModel):
    """append-only 变更事件（Spec §8.4 L1）。拒绝也要留事件，只是不写入 Profile。"""

    event_id: Identifier
    student_id: StudentId
    profile_version_before: int
    profile_version_after: int
    actor: Literal["student", "authoritative_source", "system"]
    decision: ProposalStatus
    timestamp: datetime
    changed_fields: tuple[str, ...] = ()
    proposal_id: Identifier | None = None

    @model_validator(mode="after")
    def _rejection_does_not_bump_version(self) -> "ProfileChangeEvent":
        if self.decision is ProposalStatus.REJECTED:
            if self.profile_version_after != self.profile_version_before:
                raise ValueError("被拒绝的提案不得改变 Profile 版本（B3）")
            if self.changed_fields:
                raise ValueError("被拒绝的提案不得记录 changed_fields")
        elif self.decision in {ProposalStatus.CONFIRMED, ProposalStatus.EDITED}:
            if self.profile_version_after != self.profile_version_before + 1:
                raise ValueError("确认写入必须使 Profile 版本恰好 +1")
        return self


class ResumeUpload(CampusPathModel):
    """Resume 上传（2026-07-31 用户需求 A）。markdown/纯文本直接进
    ``content_text``；PDF 走 ``content_base64``，由服务端抽取文本。

    上传**不直接写档案**：A1 从文本提炼出候选变更、生成一条恒为 pending 的
    ProfileUpdateProposal（B3），与现有档案冲突的条目标为 update 并带
    old_value——由学生逐项决定是否更新为新版本。
    """

    filename: str = Field(min_length=1, max_length=255)
    content_text: str | None = Field(default=None, max_length=100_000)
    content_base64: str | None = Field(
        default=None, max_length=4_000_000, description="PDF 原文（base64）"
    )

    @model_validator(mode="after")
    def _exactly_one_payload(self) -> "ResumeUpload":
        if (self.content_text is None) == (self.content_base64 is None):
            raise ValueError("content_text 与 content_base64 必须二选一")
        return self


class ContactPerson(CampusPathModel):
    """R5-E2（2026-08-01）：学生自填的重要联系人。

    联系方式**不写死在代码里**——每个班的辅导员/班主任/班长都不同，
    且变动频繁；学生入系统时填写，学期内任意时间可改。
    只在学生域与 outreach 分流使用，无任何通往聚合域的路径。
    """

    role: Literal["tutor", "class_teacher", "monitor"]
    name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)


class ImportantContacts(CampusPathModel):
    student_id: StudentId
    contacts: tuple[ContactPerson, ...] = Field(default=(), max_length=6)
    updated_at: datetime


class EducationEntry(CampusPathModel):
    """R5-B（2026-08-01）：教育经历——高中到研究生，含夏令营/交换/驾校等。"""

    school: str = Field(min_length=1, max_length=200)
    program: str | None = Field(default=None, max_length=200)
    start_year: str | None = Field(default=None, max_length=10)
    end_year: str | None = Field(default=None, max_length=10)
    note: str | None = Field(default=None, max_length=500)


class LanguageSkill(CampusPathModel):
    """语言：流利程度由学生自填；有考级也一并填。"""

    language: str = Field(min_length=1, max_length=60)
    proficiency: str = Field(min_length=1, max_length=60,
                             description="入门/初级/流利/接近母语等，学生自评")
    certification: str | None = Field(
        default=None, max_length=200, description="考级情况（如 IELTS 7.0），可空")


class ProfileEntry(CampusPathModel):
    """通用条目：出版物 / 荣誉奖项 / 组织机构成员。"""

    title: str = Field(min_length=1, max_length=300)
    issuer: str | None = Field(default=None, max_length=200)
    date: str | None = Field(default=None, max_length=20)
    url: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=500)


class ProfileExtras(CampusPathModel):
    """R5-B：LinkedIn 式档案的补充分区（学业记录/证据之外的自述部分）。

    全部由学生自填自改（同 contacts 的先例：B3 挡 Agent 暗改，不挡本人）。
    与 SIS/证据派生的分区不同，这里没有"核验状态"——它整体就是自述。
    """

    student_id: StudentId
    education: tuple[EducationEntry, ...] = Field(default=(), max_length=10)
    languages: tuple[LanguageSkill, ...] = Field(default=(), max_length=10)
    publications: tuple[ProfileEntry, ...] = Field(default=(), max_length=20)
    honors: tuple[ProfileEntry, ...] = Field(default=(), max_length=20)
    #: 1.32.0（审查 M6）：**自述**证书（Resume 模板解析物化到这里）。
    #: EvidenceRecord 要求真实载体（uri/object_ref），学生没上传文件时
    #: 伪造 Vault 引用是骗过不变式——自述证书归自述分区，学生真上传了
    #: 证书文件才走 Evidence 通道。
    certificates: tuple[ProfileEntry, ...] = Field(default=(), max_length=20)
    organizations: tuple[ProfileEntry, ...] = Field(default=(), max_length=20)
    hobbies: tuple[str, ...] = Field(
        default=(), max_length=20,
        description="与专业无关的个人爱好（弹琴/舞蹈/作曲等）")
    updated_at: datetime
