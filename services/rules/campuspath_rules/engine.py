"""Rules & Constraint Engine 的对外入口：签发 `ConstraintValidation`。

**这是系统里唯一有权签发 `validation_id` 的地方。** A5 的每个 PlanItem 与每条
资格结论都必须引用一个这里签发过的凭据，API 层据此拒绝无凭据的输出（Spec §8.9.3、B8）。

零 LLM：本模块与它 import 的一切都不得引入模型 SDK，由
``tests/test_llm_free.py`` 扫描依赖树强制。

签发的 id 是**确定性**的（同一 rule set + 同一主体 ⇒ 同一 id），
这样固定 Seed 的评测两次跑出来的报告可以逐字比对（D6.7）。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

from campuspath_contracts.calendar import AvailabilityBlock, CapacitySnapshot
from campuspath_contracts.common import LocalizedText, SourceRef, TimeRange
from campuspath_contracts.opportunity import EligibilityStateName, Opportunity
from campuspath_contracts.validation import (
    ConstraintValidation,
    InMemoryValidationRegistry,
    RuleCategory,
    ValidationReason,
    Verdict,
    deterministic_validation_id,
)

from .capacity_rules import find_capacity_violations, find_protected_block_violations
from .eligibility import EligibilityOutcome, StudentEligibilityFacts, assess
from .prerequisites import AcademicRecord, Verdict as PrereqVerdict, evaluate, parse

#: 规则集版本。改任何阈值或判定逻辑都要 bump——
#: 否则同一个 validation_id 会指向两套不同的判定，审计链就断了。
RULE_SET_VERSION = "rules/2026.07"

def _record_fingerprint(record: AcademicRecord, expression: str | None) -> str:
    """判定输入的稳定指纹。排序保证同一份记录两次得到同一串（D6.7）。"""
    import hashlib

    material = "|".join([
        expression or "",
        ",".join(sorted(record.completed)),
        ",".join(f"{k}={v}" for k, v in sorted(record.grades.items())),
    ])
    return hashlib.sha256(material.encode()).hexdigest()[:16]


_STATE_TO_VERDICT = {
    EligibilityStateName.ELIGIBLE_NOW: Verdict.SATISFIED,
    EligibilityStateName.FUTURE_ELIGIBLE: Verdict.VIOLATED,
    EligibilityStateName.NEEDS_CONFIRMATION: Verdict.NEEDS_CONFIRMATION,
    EligibilityStateName.INELIGIBLE_CURRENT_CYCLE: Verdict.VIOLATED,
}


@dataclasses.dataclass
class RulesEngine:
    """确定性判定 + 凭据签发。

    构造时注入 registry，是为了让 WP5 的 Firestore 实现与测试用的内存实现
    走完全相同的代码路径——契约测试因此对两者同样有效。
    """

    registry: InMemoryValidationRegistry = dataclasses.field(
        default_factory=InMemoryValidationRegistry
    )
    rule_set_version: str = RULE_SET_VERSION

    # ── 签发 ────────────────────────────────────────────────────────

    def _issue(
        self,
        subject_ref: SourceRef,
        verdict: Verdict,
        reasons: tuple[ValidationReason, ...],
        now: datetime,
        expires_at: datetime | None = None,
        context: str = "",
    ) -> ConstraintValidation:
        validation = ConstraintValidation(
            validation_id=deterministic_validation_id(
                self.rule_set_version, subject_ref, context
            ),
            rule_set_version=self.rule_set_version,
            subject_ref=subject_ref,
            verdict=verdict,
            reasons=reasons,
            evaluated_at=now,
            expires_at=expires_at,
        )
        self.registry.issue(validation)
        return validation

    # ── 资格 ────────────────────────────────────────────────────────

    def validate_eligibility(
        self,
        opportunity: Opportunity,
        facts: StudentEligibilityFacts,
        today: date,
        now: datetime | None = None,
    ) -> tuple[EligibilityOutcome, ConstraintValidation]:
        now = now or datetime.now(timezone.utc)
        outcome = assess(opportunity, facts, today)
        subject = SourceRef(entity_type="opportunity", entity_id=opportunity.opportunity_id)
        reasons = tuple(
            ValidationReason(
                rule_id=f"ELIG.{assessment.state.value.upper()}",
                category=RuleCategory.ELIGIBILITY,
                verdict=_STATE_TO_VERDICT[assessment.state],
                # reason 现在**本来就是** LocalizedText，不再需要把同一串塞进两侧
                message=assessment.reason,
            )
            for assessment in outcome.per_rule
        )
        # 资格随截止日期与名额变化，凭据不能永久有效
        expires = opportunity.deadline
        validation = self._issue(
            subject, _STATE_TO_VERDICT[outcome.state], reasons, now, expires,
            # 资格四态同样因人而异：同一个机会，大三能报大一不能。
            context=f"{facts.student_id}|{facts.year_level}|{facts.program_id}",
        )
        return outcome, validation

    # ── 先修 ────────────────────────────────────────────────────────

    def validate_prerequisite(
        self,
        course_id: str,
        expression: str | None,
        record: AcademicRecord,
        now: datetime | None = None,
    ) -> ConstraintValidation:
        now = now or datetime.now(timezone.utc)
        outcome = evaluate(parse(expression), record)
        verdict = {
            PrereqVerdict.MET: Verdict.SATISFIED,
            PrereqVerdict.NOT_MET: Verdict.VIOLATED,
            PrereqVerdict.UNKNOWN: Verdict.NEEDS_CONFIRMATION,
        }[outcome.verdict]
        subject = SourceRef(entity_type="course", entity_id=course_id)
        reasons = tuple(
            ValidationReason(
                rule_id=f"PREREQ.{course_id.replace(' ', '')}",
                category=RuleCategory.PREREQUISITE,
                verdict=verdict,
                message=reason,
                expected=expression,
            )
            for reason in outcome.reasons
        )
        # context 必须包含**判定所依赖的一切**：先修结论取决于这名学生
        # 修过什么、拿了什么成绩，也取决于我们拿到的是哪条表达式。
        # 少放一样，两次不同的判定就会撞上同一个 id。
        context = _record_fingerprint(record, expression)
        return self._issue(subject, verdict, reasons, now, context=context)

    # ── 容量与保护区块 ──────────────────────────────────────────────

    def validate_capacity(
        self,
        student_id: str,
        snapshots: list[CapacitySnapshot],
        now: datetime | None = None,
    ) -> ConstraintValidation:
        now = now or datetime.now(timezone.utc)
        violations = find_capacity_violations(snapshots)
        verdict = Verdict.VIOLATED if violations else Verdict.SATISFIED
        subject = SourceRef(entity_type="capacity", entity_id=student_id)
        reasons = tuple(
            ValidationReason(
                rule_id="CAP.NO_SILENT_OVERLOAD",
                category=RuleCategory.CAPACITY,
                verdict=Verdict.VIOLATED,
                message=LocalizedText(zh_Hans=v.describe(), en=v.describe()),
                observed=f"{v.planned_hours:.1f}h",
                expected=f"<= {v.discretionary_hours:.1f}h",
            )
            for v in violations
        ) or (
            ValidationReason(
                rule_id="CAP.NO_SILENT_OVERLOAD",
                category=RuleCategory.CAPACITY,
                verdict=Verdict.SATISFIED,
                message=LocalizedText(
                    zh_Hans="所有周次的计划负荷均未静默超出可支配容量",
                    en="No week silently exceeds discretionary capacity",
                ),
            ),
        )
        return self._issue(subject, verdict, reasons, now)

    def validate_protected_blocks(
        self,
        student_id: str,
        proposed: dict[str, TimeRange],
        blocks: list[AvailabilityBlock],
        now: datetime | None = None,
    ) -> ConstraintValidation:
        now = now or datetime.now(timezone.utc)
        violations = find_protected_block_violations(proposed, blocks)
        verdict = Verdict.VIOLATED if violations else Verdict.SATISFIED
        subject = SourceRef(entity_type="schedule", entity_id=student_id)
        reasons = tuple(
            ValidationReason(
                rule_id="SCHED.PROTECTED_BLOCK",
                category=RuleCategory.PROTECTED_BLOCK,
                verdict=Verdict.VIOLATED,
                message=LocalizedText(zh_Hans=v.describe(), en=v.describe()),
            )
            for v in violations
        ) or (
            ValidationReason(
                rule_id="SCHED.PROTECTED_BLOCK",
                category=RuleCategory.PROTECTED_BLOCK,
                verdict=Verdict.SATISFIED,
                message=LocalizedText(
                    zh_Hans="排程未与任何保护区块重叠",
                    en="No proposed slot overlaps a protected block",
                ),
            ),
        )
        return self._issue(subject, verdict, reasons, now)
