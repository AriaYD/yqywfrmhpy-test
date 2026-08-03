"""Spec §14.2：学业、课程与培养方案。

两条硬契约：

* :class:`AnnotatedCourseCandidate` 是 A2 的产出，**不含任何排序分数**
  （Spec §8.1）。由 ``tests/test_boundary_guards.py`` 用字段名扫描强制。
* :class:`CoursePlan` 是 A5 的产出，**必须携带 validation_ids**（Spec §8.9.3）。

课程目录字段与 HKUST 公开目录抓取结果对齐（``seed/scrape_hkust_catalog.py``），
先修保留**原始表达式**（如 ``COMP 1021 OR COMP 1023``）而非解析后的结构——
解析是 Rules Engine 的职责，契约层保留原文以便判定依据可回溯（D6.5 规则③）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    Confidence,
    CourseId,
    DataUncertainty,
    Identifier,
    LocalizedText,
    Provenance,
    StrEnum,
    StudentId,
    TermCode,
    Uncertainty,
    ValidationId,
)


class CourseStatus(StrEnum):
    PLANNED = "planned"
    ENROLLED = "enrolled"
    COMPLETED = "completed"
    DROPPED = "dropped"
    WAITLISTED = "waitlisted"


class RecordSource(StrEnum):
    SIS = "sis"
    LMS = "lms"
    STUDENT_REPORTED = "student_reported"
    DEGREE_AUDIT = "degree_audit"


class OfferingPattern(StrEnum):
    EVERY_TERM = "every_term"
    FALL_ONLY = "fall_only"
    SPRING_ONLY = "spring_only"
    ALTERNATE_YEARS = "alternate_years"
    IRREGULAR = "irregular"
    UNKNOWN = "unknown"


class CapacityStatus(StrEnum):
    OPEN = "open"
    WAITLIST = "waitlist"
    FULL = "full"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class PrerequisiteStatus(StrEnum):
    """A2 的标注结果之一。``UNKNOWN`` 必须能传导到 UI，不许悄悄当成 MET。"""

    MET = "met"
    NOT_MET = "not_met"
    IN_PROGRESS = "in_progress"
    WAIVED = "waived"
    UNKNOWN = "unknown"


class MeetingSlot(CampusPathModel):
    """课表时段。**不含教师个人联系方式，也不含学生名单。**"""

    weekday: Literal["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    venue: str | None = None


class AcademicProgram(CampusPathModel):
    program_id: Identifier
    degree: str
    major: str
    catalog_year: str = Field(pattern=r"^\d{4}-\d{2}$")
    total_credits: float = Field(gt=0)
    requirement_group_ids: tuple[Identifier, ...] = ()
    policy_source: Provenance | None = None


class StudentCourseRecord(CampusPathModel):
    record_id: Identifier
    student_id: StudentId
    course_id: CourseId
    term: TermCode
    status: CourseStatus
    credits: float = Field(ge=0)
    grade_scope: Literal["letter", "pass_fail", "audit", "not_released", "withheld"] = "not_released"
    grade: str | None = Field(
        default=None,
        description="仅在学生授权 SIS_RECORDS 时填充；未授权时为 None 而非 'N/A'",
    )
    source: RecordSource
    updated_at: datetime


class CourseCatalogItem(CampusPathModel):
    """课程目录条目。真实数据来自 HKUST 公开目录（无学生数据）。"""

    course_id: CourseId
    subject: str
    title: str
    description: str | None = None
    credits: float = Field(ge=0)
    prerequisite_expression: str | None = Field(
        default=None,
        description="来源原文，例如 'COMP 1021 OR COMP 1023'；解析交给 Rules Engine",
    )
    corequisite_expression: str | None = None
    exclusion_expression: str | None = None
    previous_course_code: str | None = None
    offering_pattern: OfferingPattern = OfferingPattern.UNKNOWN
    skill_tags: tuple[Identifier, ...] = Field(
        default=(), description="A2 由课程描述映射产出，属语义判断"
    )
    intended_learning_outcomes: tuple[str, ...] = ()
    source: Provenance


class CourseOffering(CampusPathModel):
    offering_id: Identifier
    course_id: CourseId
    term: TermCode
    section: str
    schedule: tuple[MeetingSlot, ...] = ()
    capacity_status: CapacityStatus = CapacityStatus.UNKNOWN
    instructor: str | None = None
    delivery_mode: str | None = None
    exam_time: datetime | None = None
    updated_at: datetime


class DegreeRequirement(CampusPathModel):
    requirement_id: Identifier
    program_id: Identifier
    group: str
    rule: str = Field(description="要求原文，判定由 Rules Engine 完成")
    required_credits: float | None = Field(default=None, ge=0)
    required_count: int | None = Field(default=None, ge=0)
    alternatives: tuple[CourseId, ...] = ()

    @model_validator(mode="after")
    def _needs_a_quantity(self) -> "DegreeRequirement":
        if self.required_credits is None and self.required_count is None:
            raise ValueError("DegreeRequirement 必须给出 required_credits 或 required_count")
        return self


class DegreeRequirementProgress(CampusPathModel):
    """学生在某条要求上的进度。satisfied_by 必须指向真实的课程记录。"""

    requirement_id: Identifier
    satisfied_by: tuple[Identifier, ...] = ()
    earned_credits: float = Field(default=0.0, ge=0)
    remaining_credits: float = Field(default=0.0, ge=0)
    satisfied: bool = False


class DegreeProgress(CampusPathModel):
    """A2 输出。纯事实聚合，不含"你应该先修哪门"这类建议。"""

    student_id: StudentId
    program_id: Identifier
    as_of: datetime
    total_earned_credits: float = Field(ge=0)
    total_required_credits: float = Field(gt=0)
    requirement_progress: tuple[DegreeRequirementProgress, ...] = ()
    uncertainties: tuple[DataUncertainty, ...] = ()


class AcademicState(CampusPathModel):
    """A2 输出：SIS/LMS/Degree/Catalog 调和后的学业事实。"""

    student_id: StudentId
    as_of: datetime
    current_term: TermCode
    course_records: tuple[StudentCourseRecord, ...] = ()
    current_term_credits: float = Field(default=0.0, ge=0)
    lms_workload_signal: float | None = Field(
        default=None, ge=0,
        description="LMS 侧的负荷代理（未完成作业数等）；非成绩、非评价",
    )
    source_conflicts: tuple[DataUncertainty, ...] = Field(
        default=(), description="SIS 与 LMS 冲突时如实上报，不擅自择一"
    )


class AnnotatedCourseCandidate(CampusPathModel):
    """A2 产出（Spec §14.2）。**不含任何排序分数** —— 排序是 A5 的独占职责。

    ``workload_estimate_hours_per_week`` 是事实估计而非价值判断，因此允许存在；
    任何名为 score/rank/utility 的字段都会被边界扫描拒绝。
    """

    candidate_id: Identifier
    course_id: CourseId
    offering_id: Identifier | None = None
    satisfies_requirement_groups: tuple[Identifier, ...] = ()
    prerequisite_status: PrerequisiteStatus = PrerequisiteStatus.UNKNOWN
    prerequisite_detail: LocalizedText | None = None
    offering_term: TermCode | None = None
    conflict_flags: tuple[str, ...] = Field(
        default=(), description="与已选课程/考试/保护区块的冲突标记，由 Capacity+Rules 提供"
    )
    workload_estimate_hours_per_week: float | None = Field(default=None, ge=0)
    skill_tags: tuple[Identifier, ...] = ()
    source: Provenance
    uncertainty: Uncertainty = Uncertainty.NONE


class CoursePlanVariant(StrEnum):
    """S1 ParallelAgent 的三套约束强度（Spec §8.1 表 S1）。"""

    BALANCED = "balanced"
    AMBITIOUS = "ambitious"
    LOW_LOAD = "low_load"


class CoursePlanItem(CampusPathModel):
    course_id: CourseId
    offering_id: Identifier | None = None
    term: TermCode
    credits: float = Field(ge=0)
    validation_id: ValidationId = Field(
        description="Rules 对该课程项的校验凭据；缺失即被 API 拒绝（Spec §8.9.3）"
    )
    alternatives: tuple[CourseId, ...] = ()
    rationale: LocalizedText | None = None


class CoursePlan(CampusPathModel):
    """A5 产出。三个变体由 S1 `ParallelAgent` 并行生成。"""

    plan_id: Identifier
    student_id: StudentId
    variant: CoursePlanVariant
    term: TermCode
    course_items: tuple[CoursePlanItem, ...] = Field(min_length=1)
    total_credits: float = Field(ge=0)
    goal_value: float = Field(description="A5 的取舍分数。只有 A5 的输出允许出现分数")
    degree_value: float
    gap_value: float
    workload_cost: float = 0.0
    explanation: LocalizedText
    confidence: Confidence = 0.5
    validation_ids: tuple[ValidationId, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _every_item_validation_is_declared(self) -> "CoursePlan":
        declared = set(self.validation_ids)
        missing = [i.course_id for i in self.course_items if i.validation_id not in declared]
        if missing:
            raise ValueError(
                f"CoursePlan.validation_ids 未涵盖以下课程项的凭据：{missing}（B8）"
            )
        return self


class ProgramRequirementGroup(CampusPathModel):
    """专业课程要求组（真实 HKUST ugprog/PDF 抓取，2026-07-31 用户需求 C/K）。

    抓不到的数字字段是 ``None``，**不编造**；``has_or_logic`` 表示组内课程
    存在择一逻辑（精确语义以 ``source_url`` 的官方 PDF 为准，D6.5：
    冲突时以来源原文为准）。
    """

    group_name: str
    type: Literal["required", "elective", "school_requirement", "other"]
    credits_required: float | None = None
    courses_required: int | None = None
    estimated_credits_sum: float | None = None
    has_or_logic: bool = False
    course_codes: tuple[str, ...] = ()
    source_url: str


class ProgramTermPlan(CampusPathModel):
    """R4-J（2026-07-31）：一个专业在某个学期的建议修读安排。

    数据来自官方 PDF 的课程清单 + 按先修链推断的学期排布（source_note 写明
    哪部分是官方、哪部分是推断——接入真实教务系统后由 SIS 数据整体替换）。
    """

    term_key: str = Field(pattern=r"^Y[1-4]_(FALL|SPRING)$")
    required: tuple[str, ...] = ()
    notes: str | None = Field(default=None, max_length=2000)


class ProgramCurriculum(CampusPathModel):
    """一个本科专业的四年课程要求全貌（必修组/选修组/毕业要求）。"""

    program_id: Identifier
    name: str
    school: str
    normative_duration: str | None = None
    total_credits_required: float | None = None
    substituted_for: str | None = Field(
        default=None, description="显式记录替代关系（如 BCB 替代 Biological Science）"
    )
    university_graduation_requirements: tuple[str, ...] = ()
    requirement_groups: tuple[ProgramRequirementGroup, ...] = ()
    source_urls: tuple[str, ...] = ()
    term_plans: tuple[ProgramTermPlan, ...] = Field(
        default=(), description="按学期的建议修读安排（大一上→大四下，R4-J）"
    )
    term_plan_note: str | None = Field(
        default=None, max_length=1000,
        description="学期排布的数据来源说明（官方/推断），如实呈现")


class CourseRecommendation(CampusPathModel):
    """R4-K（2026-07-31）：推荐给学生的**选修课**（必修课不推荐——反正都要修）。

    两层筛选：规则关键词初筛 → AI 复筛并给出每门课的推荐理由。
    判定边界：AI 评的是"这门课与你的目标相关不相关"，**不覆盖** Rules 的
    先修判定（§16.2/B8）——先修读不懂的课最多进"待用户确认"，附原文提示。
    """

    course_id: CourseId
    title: str
    credits: float = Field(ge=0)
    description: str | None = None
    verdict: Literal["recommended", "needs_user_confirmation"]
    reason: LocalizedText = Field(description="为什么推荐/为什么待确认——每门都有")
    reason_source: Literal["model", "rules"] = Field(
        description="理由出处：AI 复筛产出，或模型不可用时的规则降级（如实自报）"
    )
    prerequisite_note: LocalizedText | None = Field(
        default=None,
        description="先修规则读不懂时的原文提示——判定归 Rules，这里只是提醒"
    )
    skill_tags: tuple[Identifier, ...] = ()
    official_url: str | None = None
