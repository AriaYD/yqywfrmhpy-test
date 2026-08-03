"""四态资格判定（Spec §16.1–16.2）。**零 LLM。**

四态不是"能申请 / 不能申请"加两个装饰。它们对应四种**不同的系统动作**：

| 状态 | 系统动作 |
|---|---|
| `eligible_now` | 进近期行动层 |
| `future_eligible` | 进长期路径，并生成桥接行动与预计可申请窗口 |
| `needs_confirmation` | 保留并提示确认，**不淘汰** |
| `ineligible_current_cycle` | 本轮不安排，可作未来参考 |

合并多条规则时的优先级写在 :data:`STATE_PRECEDENCE`。
`eligible_now` 排最后是刻意的：它直接对应 T2（把不合格判成可申请），
而 T2 比 T1 更要紧——判错成"可申请"会让学生白花时间去申请。
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping
from datetime import date

from campuspath_contracts.common import LocalizedText
from campuspath_contracts.messages import render
from campuspath_contracts.opportunity import (
    EligibilityRule,
    EligibilityRuleKind,
    EligibilityStateName,
    Opportunity,
)

from .prerequisites import AcademicRecord, Verdict, evaluate, parse

#: 多条规则的合并优先级（由强到弱）。
#:
#: ``NEEDS_CONFIRMATION`` 排在 ``FUTURE_ELIGIBLE`` **之前**。
#: 一条规则说"升到大三就行"、另一条说"签证状态不明"时，
#: 若判成 future_eligible 并附上一个确切日期，学生看到的是
#: 「保留并安排桥接行动」，而那个待确认项可能让他永远不合格——
#: 系统给了一个自己站不住的日期。判成 needs_confirmation 会促使先去解决它。
#:
#: ``ELIGIBLE_NOW`` 仍排最后，理由不变：它直接对应 T2（把不合格判成可申请）。
STATE_PRECEDENCE: tuple[EligibilityStateName, ...] = (
    EligibilityStateName.INELIGIBLE_CURRENT_CYCLE,
    EligibilityStateName.NEEDS_CONFIRMATION,
    EligibilityStateName.FUTURE_ELIGIBLE,
    EligibilityStateName.ELIGIBLE_NOW,
)

_YEAR_ABOVE = re.compile(r"year\s*(\d)\s*(?:or above|\+)", re.I)
_YEAR_EXACT = re.compile(r"^\s*year\s*(\d)\s*$", re.I)
_COURSE_CODE = re.compile(r"\b([A-Z]{4})\s?(\d{4}[A-Z]?)\b")


@dataclasses.dataclass(frozen=True)
class StudentEligibilityFacts:
    """判定资格所需的最小事实集。

    **没有目标原文、没有 Reflection、没有日历。** 资格是硬条件比对，
    不需要知道学生想做什么。传得越少，越不可能在这一层泄露。
    """

    student_id: str
    year_level: int
    program_id: str
    academic: AcademicRecord
    has_visa_constraint: bool = False
    cgpa: float | None = None
    #: 学生升到下一年级的日期，用于 future_eligible 的可申请窗口
    next_year_start: date | None = None
    #: course_id → 未来最早可完成日期（通常取学期结束日）。
    #:
    #: ``None`` = 调用方没有开课目录，引擎只能沿用「课程可补修」的旧假设；
    #: **空 dict 不是 None**——它表示「有目录，且没有任何课在未来开」。
    #: 2026-07-31 裁定（docs/T1-T3-adjudication.md 原因二）：
    #: 「补修就能达成」在那门课再也不开时是一个没有依据的承诺，
    #: 有目录时必须查，查不到未来开课的缺课判 ineligible_current_cycle。
    future_offerings: Mapping[str, date] | None = None


@dataclasses.dataclass(frozen=True)
class RuleAssessment:
    state: EligibilityStateName
    #: **双语**。曾经是单语中文 prose，塞进 LocalizedText 时两侧填同一串，
    #: 于是英文界面里整段中文。判定理由会直接显示给学生，它就是 UI 文案。
    reason: LocalizedText
    reachable_on: date | None = None


@dataclasses.dataclass(frozen=True)
class EligibilityOutcome:
    state: EligibilityStateName
    reasons: tuple[LocalizedText, ...]
    next_eligibility_date: date | None
    per_rule: tuple[RuleAssessment, ...]
    #: ``next_eligibility_date`` 是不是推算出来的兜底值。
    #: 契约要求 future_eligible 必须给日期，但没有规则能给出日期时，
    #: 我们只能推一个下学年起点——那是估计值，必须说出来，
    #: 否则学生会把一个我们站不住的日期当成承诺。
    next_eligibility_date_is_estimate: bool = False


def _year_start_for(level: int, facts: StudentEligibilityFacts, today: date) -> date:
    """学生升到 ``level`` 年级的日期。缺省按每年 9 月 1 日推算。"""
    if facts.next_year_start is not None and level == facts.year_level + 1:
        return facts.next_year_start
    delta = max(level - facts.year_level, 0)
    return date(today.year + delta, 9, 1)


def _assess_rule(
    rule: EligibilityRule, facts: StudentEligibilityFacts, today: date
) -> RuleAssessment:
    # Spec §16.2 第 5 条：模型推断只能产生 needs_confirmation，不能淘汰
    if rule.source_tier == "model_inferred":
        return RuleAssessment(
            EligibilityStateName.NEEDS_CONFIRMATION,
            render("elig.model_inferred", expression=rule.expression),
        )

    if rule.kind is EligibilityRuleKind.YEAR_LEVEL:
        match = _YEAR_ABOVE.search(rule.expression) or _YEAR_EXACT.match(rule.expression)
        if match is None:
            return RuleAssessment(
                EligibilityStateName.NEEDS_CONFIRMATION,
                render("elig.year_ambiguous", expression=rule.expression),
            )
        required = int(match.group(1))
        if facts.year_level >= required:
            return RuleAssessment(
                EligibilityStateName.ELIGIBLE_NOW,
                render("elig.year_ok", actual=facts.year_level,
                       expression=rule.expression),
            )
        reachable = _year_start_for(required, facts, today)
        return RuleAssessment(
            EligibilityStateName.FUTURE_ELIGIBLE,
            render("elig.year_future", actual=facts.year_level, required=required),
            reachable,
        )

    if rule.kind is EligibilityRuleKind.PREREQUISITE_COURSE:
        expression = _strip_completed_prefix(rule.expression)
        outcome = evaluate(parse(expression), facts.academic)
        if outcome.verdict is Verdict.MET:
            return RuleAssessment(
                EligibilityStateName.ELIGIBLE_NOW,
                render("elig.course_ok", detail=outcome.reasons),
            )
        if outcome.verdict is Verdict.UNKNOWN:
            return RuleAssessment(
                EligibilityStateName.NEEDS_CONFIRMATION,
                render("elig.course_unknown", detail=outcome.reasons),
            )
        # 课程可以补修 → 未来可达——但只有那门课**还会开**才算数。
        # 没有开课目录时只能沿用旧假设；有目录时必须验证：
        # 把「未来还开的课」全部假设修完再评一次，仍 NOT_MET 就是这条路走不通。
        if facts.future_offerings is not None:
            hypothetical = AcademicRecord(
                completed=frozenset(facts.academic.completed)
                | frozenset(facts.future_offerings),
                grades=dict(facts.academic.grades),
            )
            retry = evaluate(parse(expression), hypothetical)
            if retry.verdict is Verdict.NOT_MET:
                return RuleAssessment(
                    EligibilityStateName.INELIGIBLE_CURRENT_CYCLE,
                    render("elig.course_unreachable", detail=outcome.reasons),
                )
            if retry.verdict is Verdict.UNKNOWN:
                # 补修后能否满足取决于成绩等未知条件——带日期的 future_eligible
                # 是承诺，UNKNOWN 撑不起承诺（与 T1/T3 裁定同一原则）
                return RuleAssessment(
                    EligibilityStateName.NEEDS_CONFIRMATION,
                    render("elig.course_unknown", detail=retry.reasons),
                )
            codes = [f"{a} {b}" for a, b in _COURSE_CODE.findall(expression)]
            dates = [
                facts.future_offerings[c]
                for c in codes
                if c not in facts.academic.completed and c in facts.future_offerings
            ]
            return RuleAssessment(
                EligibilityStateName.FUTURE_ELIGIBLE,
                render("elig.course_reachable", detail=outcome.reasons),
                max(dates) if dates else None,
            )
        return RuleAssessment(
            EligibilityStateName.FUTURE_ELIGIBLE,
            render("elig.course_reachable", detail=outcome.reasons),
            None,
        )

    if rule.kind is EligibilityRuleKind.WORK_AUTHORIZATION:
        key = "elig.work_auth_visa" if facts.has_visa_constraint else "elig.work_auth"
        return RuleAssessment(
            EligibilityStateName.NEEDS_CONFIRMATION,
            render(key, expression=rule.expression),
        )

    if rule.kind is EligibilityRuleKind.GPA:
        threshold = _parse_gpa(rule.expression)
        if facts.cgpa is None or threshold is None:
            return RuleAssessment(
                EligibilityStateName.NEEDS_CONFIRMATION,
                render("elig.gpa_unparsed", expression=rule.expression),
            )
        if facts.cgpa >= threshold:
            return RuleAssessment(
                EligibilityStateName.ELIGIBLE_NOW,
                render("elig.cgpa_ok", actual=facts.cgpa, expression=rule.expression),
            )
        return RuleAssessment(
            EligibilityStateName.INELIGIBLE_CURRENT_CYCLE,
            render("elig.cgpa_no", actual=facts.cgpa, expression=rule.expression),
        )

    if rule.kind is EligibilityRuleKind.MEMBERSHIP:
        return RuleAssessment(
            EligibilityStateName.ELIGIBLE_NOW,
            render("elig.membership", expression=rule.expression),
        )

    if rule.kind is EligibilityRuleKind.APPLICATION_WINDOW:
        return RuleAssessment(
            EligibilityStateName.NEEDS_CONFIRMATION,
            render("elig.window_confirm", expression=rule.expression),
        )

    return RuleAssessment(
        EligibilityStateName.NEEDS_CONFIRMATION,
        render("elig.rule_uncovered", kind=rule.kind.value,
               expression=rule.expression),
    )


def assess(
    opportunity: Opportunity, facts: StudentEligibilityFacts, today: date
) -> EligibilityOutcome:
    """对一条机会给出四态判定。"""
    assessments: list[RuleAssessment] = []

    if opportunity.deadline is not None and opportunity.deadline.date() < today:
        assessments.append(
            RuleAssessment(
                EligibilityStateName.INELIGIBLE_CURRENT_CYCLE,
                render("elig.deadline_passed",
                       deadline=opportunity.deadline.date(), today=today),
            )
        )

    for rule in opportunity.eligibility_rules:
        assessment = _assess_rule(rule, facts, today)
        # 非硬性要求（"preferred"）不该把学生推进 future/ineligible。
        # `mandatory` 字段此前从没被读过，于是"加分项"和"硬门槛"效果完全一样。
        # 模型推断的规则例外：它恒为非 mandatory，但按 §16.2 第 5 条要提示确认。
        if (not rule.mandatory
                and rule.source_tier != "model_inferred"
                and assessment.state in {EligibilityStateName.FUTURE_ELIGIBLE,
                                         EligibilityStateName.INELIGIBLE_CURRENT_CYCLE}):
            assessment = RuleAssessment(
                EligibilityStateName.ELIGIBLE_NOW,
                render("elig.preferred_only",
                       detail=assessment.reason),
            )
        assessments.append(assessment)

    if not assessments:
        assessments.append(
            RuleAssessment(
                EligibilityStateName.ELIGIBLE_NOW, render("elig.no_hard_rules")
            )
        )

    states = {a.state for a in assessments}
    state = next(s for s in STATE_PRECEDENCE if s in states)

    next_date: date | None = None
    estimated = False
    reasons = [a.reason for a in assessments]
    if state is EligibilityStateName.FUTURE_ELIGIBLE:
        candidates = [a.reachable_on for a in assessments if a.reachable_on is not None]
        if candidates:
            next_date = max(candidates)
        else:
            # 契约要求 future_eligible 必须给日期，否则学生无法安排桥接行动。
            # 但没有规则给得出日期时，我们只能推一个下学年起点——**说明它是估计值**。
            next_date = date(today.year + 1, 9, 1)
            estimated = True
            reasons.append(render("elig.estimated_date", date=next_date))

    return EligibilityOutcome(
        state=state,
        reasons=tuple(reasons),
        next_eligibility_date=next_date,
        per_rule=tuple(assessments),
        next_eligibility_date_is_estimate=estimated,
    )


def _strip_completed_prefix(expression: str) -> str:
    return re.sub(r"^\s*completed\s+", "", expression, flags=re.I)


def _parse_gpa(expression: str) -> float | None:
    """解析 GPA 阈值。**含多个数字时返回 None**（→ needs_confirmation）。

    此前取第一个匹配：``"CGPA 2.5 in the last two semesters, or 3.0 overall"``
    会解析成 2.5，于是一个 CGPA 2.8 的学生被判成合格——又一个 T2 假阳性。
    读不准就交给学生确认，不要猜一个对他有利的数字。
    """
    matches = re.findall(r"\d\.\d+", expression)
    if len(matches) != 1:
        return None
    return float(matches[0])
