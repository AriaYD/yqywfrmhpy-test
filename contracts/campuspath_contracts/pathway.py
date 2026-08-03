"""Spec §14.3 路径与行动，以及 §16.9 的重规划触发。

`PlanItem.validation_id` 是必填字段——这是 B8 `Unbacked Plan Item = 0` 的地基。
少写一个字段就反序列化失败，不需要 API 层再检查一遍"有没有"，
API 层只需要检查"是不是真的被签发过"（见 ``enforce_validation_binding``）。

重规划的契约要求是 **AffectedScope 显式列出受影响与不受影响的范围**：
T5 Replan Correctness 判的是"只改受影响路径"，没有这个字段就无从判起。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .academic import CoursePlan
from .common import (
    CampusPathModel,
    DateRange,
    EvidenceId,
    FrozenModel,
    Identifier,
    LocalizedText,
    StrEnum,
    StudentId,
    TermCode,
    ValidationId,
)
from .validation import UnbackedOutputError, ValidationRegistry
from .common import SourceRef


class PlanItemKind(StrEnum):
    COURSE = "course"
    OPPORTUNITY = "opportunity"
    ACTION = "action"
    MILESTONE = "milestone"


class PlanItemStatus(StrEnum):
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class PlanItem(CampusPathModel):
    """A5 输出的最小单元。**每一个都必须携带 validation_id**（Spec §8.9.3）。"""

    plan_item_id: Identifier
    kind: PlanItemKind
    subject_id: Identifier = Field(description="course_id / opportunity_id / action_id")
    title: LocalizedText
    milestone: str | None = None
    date_range: DateRange
    dependencies: tuple[Identifier, ...] = ()
    workload_hours: float = Field(default=0.0, ge=0)
    status: PlanItemStatus = PlanItemStatus.PROPOSED
    fallback: LocalizedText | None = Field(
        default=None, description="Spec §16.4：任何计划项都要标明失败后的 fallback"
    )
    assumptions: tuple[LocalizedText, ...] = ()
    validation_id: ValidationId


class CapacityBudget(CampusPathModel):
    """路径版本对容量的承诺。超出即 B1 违规，除非 ``explicit_overload_warning``。"""

    period_start: date
    period_end: date
    discretionary_capacity_hours: float
    planned_hours: float = Field(ge=0)
    reserved_buffer_hours: float = Field(ge=0)
    explicit_overload_warning: bool = False

    @model_validator(mode="after")
    def _no_silent_overload(self) -> "CapacityBudget":
        if self.planned_hours + self.reserved_buffer_hours > self.discretionary_capacity_hours:
            if not self.explicit_overload_warning:
                raise ValueError(
                    "计划负荷超出可支配容量却未标记 explicit_overload_warning（B1）"
                )
        return self


class Milestone(CampusPathModel):
    milestone_id: Identifier
    title: LocalizedText
    target_term: TermCode | None = None
    target_date: date | None = None
    plan_item_ids: tuple[Identifier, ...] = ()
    linked_goal_id: Identifier | None = None


class PathwayVersion(CampusPathModel):
    """多时间尺度路径（D1 要求三个视图数据同源，因此三者都从这里派生）。"""

    pathway_id: Identifier
    student_id: StudentId
    version: int = Field(ge=1)
    created_at: datetime
    trigger: str = Field(description="生成该版本的原因；初版为 'initial'")
    horizons: tuple[Literal["next_two_weeks", "this_term", "long_term"], ...] = Field(
        min_length=1
    )
    assumptions: tuple[LocalizedText, ...] = ()
    capacity_budgets: tuple[CapacityBudget, ...] = ()
    milestones: tuple[Milestone, ...] = ()
    plan_items: tuple[PlanItem, ...] = ()
    course_plan: CoursePlan | None = None
    alternatives: tuple[LocalizedText, ...] = ()
    previous_version: int | None = None

    @model_validator(mode="after")
    def _dependencies_and_milestones_resolve(self) -> "PathwayVersion":
        ids = {i.plan_item_id for i in self.plan_items}
        for item in self.plan_items:
            missing = [d for d in item.dependencies if d not in ids]
            if missing:
                raise ValueError(f"{item.plan_item_id} 依赖不存在的计划项：{missing}")
        for m in self.milestones:
            missing = [p for p in m.plan_item_ids if p not in ids]
            if missing:
                raise ValueError(f"里程碑 {m.milestone_id} 引用不存在的计划项：{missing}")
        return self


def _explain(registry: ValidationRegistry, validation_id: str, subject: SourceRef) -> str:
    """说清楚是"没签发"、"过期了"、"张冠李戴"还是"判定本身不合规"。

    只说"invalid"会让调用方无从修——尤其分不清"模型编了个 id"
    与"Rules 确实判了违规"，而这两件事的处置完全不同。
    """
    found = registry.get(validation_id)
    if found is None:
        return "该凭据从未被 Rules 签发"
    if found.is_expired():
        return f"凭据已于 {found.expires_at} 过期"
    if (found.subject_ref.entity_type != subject.entity_type
            or found.subject_ref.entity_id != subject.entity_id):
        return (f"凭据是对 {found.subject_ref.entity_type}:{found.subject_ref.entity_id} "
                f"的校验，不是对 {subject.entity_type}:{subject.entity_id}")
    return f"凭据判定为 {found.verdict.value}，不能用来背书计划项"


def enforce_validation_binding(
    pathway: PathwayVersion,
    registry: ValidationRegistry,
    *,
    eligibility_claims: dict[str, str] | None = None,
) -> None:
    """API 层闸门：每个 PlanItem 与每条资格结论都必须有**能背书它**的凭据。

    三层，缺一 B8 都不成立：

    1. **形状** —— ``validation_id`` 必填 + 正则，由类型保证；
    2. **签发** —— 凭据确实存在、未过期、且是对这个主体的；
    3. **判定** —— 凭据的 verdict 在 :data:`BACKING_VERDICTS` 内。

    第 3 层曾经缺失，于是一条 Rules 真实签发的"先修不满足"可以背书计划项：
    出处对，合规不对。

    Args:
        eligibility_claims: ``{opportunity_id: validation_id}``，A5 的资格结论。
            Spec §8.9.3 说的是"每个 PlanItem、**每一条资格结论**"，
            只查计划项会漏掉 MatchResult 与 EligibilityExplanation 那条路径。
    """
    offenders: list[str] = []

    def check(label: str, validation_id: str, subject: SourceRef) -> None:
        if not registry.verify(validation_id, subject):
            offenders.append(f"{label}：{_explain(registry, validation_id, subject)}")

    for item in pathway.plan_items:
        check(
            f"{item.plan_item_id}({item.validation_id})",
            item.validation_id,
            SourceRef(entity_type=item.kind.value, entity_id=item.subject_id),
        )
    if pathway.course_plan is not None:
        for course_item in pathway.course_plan.course_items:
            check(
                f"course:{course_item.course_id}({course_item.validation_id})",
                course_item.validation_id,
                SourceRef(entity_type="course", entity_id=course_item.course_id),
            )
    for opportunity_id, validation_id in sorted((eligibility_claims or {}).items()):
        check(
            f"eligibility:{opportunity_id}({validation_id})",
            validation_id,
            SourceRef(entity_type="opportunity", entity_id=opportunity_id),
        )

    if offenders:
        raise UnbackedOutputError(
            "以下输出的 validation_id 无法背书它（B8）：\n  " + "\n  ".join(offenders)
        )


class ActionType(StrEnum):
    APPLY = "apply"
    REGISTER = "register"
    SAVE = "save"
    #: 取消收藏。事件流 append-only：当前收藏态 = 该 subject 最新一条
    #: save/unsave 的方向，不是"有没有 save 过"。
    UNSAVE = "unsave"
    ADD_TO_PATHWAY = "add_to_pathway"
    COMPLETE = "complete"
    DECLINE = "decline"
    CALENDAR_WRITE = "calendar_write"
    REFLECT = "reflect"


class ActionEvent(FrozenModel):
    """append-only 行动事件。VGA 与所有 BASELINE 指标都从这里聚合。"""

    event_id: Identifier
    student_id: StudentId
    action_type: ActionType
    subject_id: Identifier
    plan_item_id: Identifier | None = None
    approval_receipt_id: Identifier | None = None
    timestamp: datetime
    result: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    evidence_ids: tuple[EvidenceId, ...] = ()
    verified_growth: bool = Field(
        default=False,
        description="是否计入 VGA：需有 Evidence 或 Reflection 证明产生了价值（Spec §17.1）",
    )

    @model_validator(mode="after")
    def _vga_needs_proof(self) -> "ActionEvent":
        if self.verified_growth and not self.evidence_ids:
            raise ValueError("计入 VGA 的行动必须至少引用一条 Evidence（Spec §17.1）")
        return self


class ReplanTriggerType(StrEnum):
    """Spec §16.9 的触发器清单。T5 要求注入 ≥ 10 类。"""

    NEW_GRADE = "new_grade"
    COURSE_ENROLMENT_CHANGE = "course_enrolment_change"
    CALENDAR_CHANGE = "calendar_change"
    OPPORTUNITY_CHANGE = "opportunity_change"
    ACTIVITY_FEEDBACK = "activity_feedback"
    PERSISTENT_LOW_QUALITY = "persistent_low_quality"
    GOAL_CONFIDENCE_SHIFT = "goal_confidence_shift"
    WEEKLY_OVERLOAD = "weekly_overload"
    STUDENT_DECLINED = "student_declined"
    PROFILE_UPDATE_DECIDED = "profile_update_decided"
    NEW_APPROVED_RESOURCE = "new_approved_resource"
    #: 学生自己从资讯广场把某个机会加进了日程。
    #:
    #: 单列一类而不是复用 ``opportunity_change``：那一类说的是"机会本身变了"
    #: （改期、取消），可能波及长期路径；而这一类是**学生的主动加项**，
    #: 按 §16.9 只该做局部重排——**原主路线为主**，新加的东西围着它排，
    #: 不是反过来。两者混用会让"我加了个讲座"推翻一整条长期规划。
    STUDENT_ADDED_OPPORTUNITY = "student_added_opportunity"


class ReplanRequest(CampusPathModel):
    """"有件事变了，会动到什么？"——**只描述变化本身**。

    刻意不复用 ``ReplanTrigger`` 作请求体：那个模型里带着 ``affected_scope``，
    而 affected_scope 正是这次要算出来的东西。让调用方先填一个空的再由
    服务端覆盖，等于把"谁负责算"这件事说不清楚。
    """

    student_id: StudentId
    trigger_type: "ReplanTriggerType"
    source: str = Field(description="变了的那个东西的 id，例如 opportunity_id")
    detected_at: datetime
    request_id: Identifier | None = None


class AffectedScope(CampusPathModel):
    """Event Monitor 的计算结果。**必须同时列出不受影响的范围**——

    T5 判的是"只改受影响路径"，只给受影响列表无法证伪"顺手把别的也改了"。
    """

    affected_plan_item_ids: tuple[Identifier, ...] = ()
    affected_goal_ids: tuple[Identifier, ...] = ()
    affected_milestone_ids: tuple[Identifier, ...] = ()
    unaffected_plan_item_ids: tuple[Identifier, ...] = ()
    rationale: LocalizedText


class ReplanTrigger(CampusPathModel):
    trigger_id: Identifier
    student_id: StudentId
    trigger_type: ReplanTriggerType
    source: str
    detected_at: datetime
    affected_scope: AffectedScope
    urgency: Literal["low", "normal", "high"] = "normal"
    old_plan_version: int = Field(ge=1)

    @model_validator(mode="after")
    def _scope_is_disjoint(self) -> "ReplanTrigger":
        overlap = set(self.affected_scope.affected_plan_item_ids) & set(
            self.affected_scope.unaffected_plan_item_ids
        )
        if overlap:
            raise ValueError(f"同一计划项不能同时受影响与不受影响：{sorted(overlap)}")
        return self
