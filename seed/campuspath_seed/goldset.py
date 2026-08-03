"""Gold Set：四态资格、课程约束、重规划情景、记忆回归。

按 Plan R8，这里产出的是**规则生成的初版标签**，`review_status` 一律为
``rule_generated``。人工复核后才改为 ``human_reviewed``——在那之前，
任何用它算出来的 T1/T2/T3 都只是自评，不能当作已验证的准确率。

D6.5 的四条规则在这里的落点：

* ② 每条标签写明**判定依据** → 每条都有 ``reasons``，且引用具体规则原文；
* ③ 冲突时以来源原文为准 → 标签只看 ``EligibilityRule.expression`` 与
  真实先修表达式，不看任何模型输出；
* ④ 冻结后改动走版本号 → 每份 Gold Set 带 ``seed_version``；
* ① 先规则、后人工 → 见 ``review_status``。

**这不是 Rules Engine。** 它只做 Gold Label 需要的那点判定，
故意与 WP5 的实现分开写：用同一份代码生成标签又用它来评测，等于自己给自己打分。
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date, timedelta

from campuspath_contracts.academic import CourseStatus
from campuspath_contracts.opportunity import (
    EligibilityRuleKind,
    EligibilityStateName,
    Opportunity,
)

from .catalog import Catalog
from .config import CURRENT_TERM, FUTURE_TERMS, SEED_TODAY, SEED_VERSION, TERMS
from .personas import PersonaBundle
from .rng import stream

#: 多条规则得到不同结论时的合并优先级。写在这里而不是散在 if 里，
#: 因为它直接决定 T2（把不合格判成 Eligible now）的表现。
#:
#: 2026-07-31 裁定（docs/T1-T3-adjudication.md 原因一）：
#: ``NEEDS_CONFIRMATION`` 排在 ``FUTURE_ELIGIBLE`` 之前，与 Rules Engine 一致。
#: future_eligible 附带「预计可申请窗口」，那是一个承诺；还有硬条件没确认时
#: 给出确切日期，是系统自己站不住的承诺。时间线信息不因此丢失——
#: 它仍留在逐条 reasons 里，确认完成后状态自然重算为 future_eligible。
STATE_PRECEDENCE = (
    EligibilityStateName.INELIGIBLE_CURRENT_CYCLE,
    EligibilityStateName.NEEDS_CONFIRMATION,
    EligibilityStateName.FUTURE_ELIGIBLE,
    EligibilityStateName.ELIGIBLE_NOW,
)

_COURSE_CODE = re.compile(r"\b([A-Z]{4})\s?(\d{4}[A-Z]?)\b")
_YEAR_ABOVE = re.compile(r"year\s*(\d)\s*(?:or above|\+)", re.I)


@dataclasses.dataclass
class EligibilityGoldLabel:
    case_id: str
    student_id: str
    opportunity_id: str
    label: str
    reasons: list[str]
    next_eligibility_date: str | None
    review_status: str = "rule_generated"


@dataclasses.dataclass
class CourseConstraintGoldLabel:
    case_id: str
    student_id: str
    course_id: str
    satisfies_requirement_groups: list[str]
    prerequisite_status: str
    offered_in_current_term: bool
    offered_terms: list[str]
    timetable_conflict: bool
    reasons: list[str]
    review_status: str = "rule_generated"


@dataclasses.dataclass
class ReplanGoldCase:
    case_id: str
    student_id: str
    trigger_type: str
    event: str
    expected_affected: list[str]
    expected_unaffected: list[str]
    rationale: str
    review_status: str = "rule_generated"


@dataclasses.dataclass
class MemoryRegressionCase:
    case_id: str
    student_id: str
    subject_id: str
    history: str
    expectation: str
    #: T12 的判据：给定情景，记忆检索 top-5 里**应当**出现的记忆条目。
    #: seed/1.2.0 新增（D6.5 规则④）。id 按 events.py 的模板序号推导。
    expected_memory_ids: list[str] = dataclasses.field(default_factory=list)
    review_status: str = "rule_generated"


@dataclasses.dataclass
class GoldSet:
    seed_version: str
    eligibility: list[EligibilityGoldLabel]
    course_constraints: list[CourseConstraintGoldLabel]
    replan: list[ReplanGoldCase]
    memory_regression: list[MemoryRegressionCase]


# --------------------------------------------------------------------------
# 四态资格
# --------------------------------------------------------------------------


def _completed_courses(persona: PersonaBundle) -> set[str]:
    return {
        r.course_id for r in persona.course_records if r.status is CourseStatus.COMPLETED
    }


def _year_start(year_level: int, persona: PersonaBundle) -> date:
    """学生升到某年级的日期。用于 future_eligible 的可申请窗口。"""
    delta = year_level - persona.profile.year
    return date(SEED_TODAY.year + max(delta, 0), 9, 1)


def _rule_verdict(
    rule, persona: PersonaBundle, completed: set[str], catalog: Catalog
) -> tuple[EligibilityStateName, str, date | None]:
    profile = persona.profile

    if rule.source_tier == "model_inferred":
        return (EligibilityStateName.NEEDS_CONFIRMATION,
                f"规则来自模型推断，不能作为淘汰依据：{rule.expression}", None)

    if rule.kind is EligibilityRuleKind.YEAR_LEVEL:
        match = _YEAR_ABOVE.search(rule.expression)
        if not match:
            return (EligibilityStateName.NEEDS_CONFIRMATION,
                    f"年级表述含糊，需向来源确认：{rule.expression}", None)
        required = int(match.group(1))
        if profile.year >= required:
            return (EligibilityStateName.ELIGIBLE_NOW,
                    f"当前 Year {profile.year} 满足「{rule.expression}」", None)
        return (EligibilityStateName.FUTURE_ELIGIBLE,
                f"当前 Year {profile.year}，「{rule.expression}」在升入 Year {required} 后可达",
                _year_start(required, persona))

    if rule.kind is EligibilityRuleKind.PREREQUISITE_COURSE:
        codes = [f"{a} {b}" for a, b in _COURSE_CODE.findall(rule.expression)]
        if not codes:
            return (EligibilityStateName.NEEDS_CONFIRMATION,
                    f"先修要求未指明具体课程：{rule.expression}", None)
        missing = [c for c in codes if c not in completed]
        if not missing:
            return (EligibilityStateName.ELIGIBLE_NOW,
                    f"已修 {', '.join(codes)}，满足「{rule.expression}」", None)
        reachable = [
            c for c in missing
            if any(catalog.offerings_for(c, term) for term in FUTURE_TERMS)
        ]
        if len(reachable) == len(missing):
            first_term = next(
                term for term in FUTURE_TERMS
                if any(catalog.offerings_for(c, term) for c in missing)
            )
            return (EligibilityStateName.FUTURE_ELIGIBLE,
                    f"尚未修读 {', '.join(missing)}，{first_term} 有开课，可在其后满足",
                    TERMS[first_term][1])
        return (EligibilityStateName.INELIGIBLE_CURRENT_CYCLE,
                f"尚未修读 {', '.join(missing)}，且未来学期无开课记录", None)

    if rule.kind is EligibilityRuleKind.WORK_AUTHORIZATION:
        if any(c.kind == "visa" for c in profile.constraints):
            return (EligibilityStateName.NEEDS_CONFIRMATION,
                    f"学生有签证类约束，工作授权状态需本人确认：{rule.expression}", None)
        return (EligibilityStateName.NEEDS_CONFIRMATION,
                f"系统不掌握工作授权状态，需学生确认：{rule.expression}", None)

    if rule.kind is EligibilityRuleKind.GPA:
        return (EligibilityStateName.NEEDS_CONFIRMATION,
                f"Seed 不提供 CGPA，无法判定：{rule.expression}", None)

    if rule.kind is EligibilityRuleKind.MEMBERSHIP:
        return (EligibilityStateName.ELIGIBLE_NOW,
                f"在读学生即满足：{rule.expression}", None)

    return (EligibilityStateName.NEEDS_CONFIRMATION, f"未覆盖的规则类型：{rule.expression}", None)


def _label_one(
    persona: PersonaBundle, opportunity: Opportunity, catalog: Catalog
) -> EligibilityGoldLabel:
    completed = _completed_courses(persona)
    reasons: list[str] = []
    verdicts: list[EligibilityStateName] = []
    next_date: date | None = None

    if opportunity.deadline is not None and opportunity.deadline.date() < SEED_TODAY:
        reasons.append(
            f"截止日期 {opportunity.deadline.date()} 已过（今天 {SEED_TODAY}），本轮无法申请"
        )
        verdicts.append(EligibilityStateName.INELIGIBLE_CURRENT_CYCLE)

    for rule in opportunity.eligibility_rules:
        state, reason, when = _rule_verdict(rule, persona, completed, catalog)
        reasons.append(reason)
        verdicts.append(state)
        if state is EligibilityStateName.FUTURE_ELIGIBLE and when is not None:
            next_date = when if next_date is None else max(next_date, when)

    if not verdicts:
        reasons.append("来源未声明任何硬性资格条件")
        verdicts.append(EligibilityStateName.ELIGIBLE_NOW)

    label = next(state for state in STATE_PRECEDENCE if state in verdicts)
    if label is not EligibilityStateName.FUTURE_ELIGIBLE:
        next_date = None
    elif next_date is None:
        next_date = SEED_TODAY + timedelta(days=365)

    return EligibilityGoldLabel(
        case_id=f"GOLD-ELIG-{persona.profile.student_id}-{opportunity.opportunity_id}",
        student_id=persona.profile.student_id,
        opportunity_id=opportunity.opportunity_id,
        label=label.value,
        reasons=reasons,
        next_eligibility_date=next_date.isoformat() if next_date else None,
    )


def _build_eligibility(
    personas: list[PersonaBundle], opportunities: list[Opportunity],
    catalog: Catalog, target: int,
) -> list[EligibilityGoldLabel]:
    """在三个 Persona 上均匀取样，并**保证四态都有足够样本**。

    只按顺序取前 N 条会得到一个几乎全是 eligible_now 的 Gold Set，
    那样 T2（Hard Eligibility False Positive）根本测不出来。
    """
    deep = [p for p in personas if p.is_deep] or personas[:1]
    labels: list[EligibilityGoldLabel] = []
    for persona in deep:
        for opportunity in opportunities:
            labels.append(_label_one(persona, opportunity, catalog))

    by_state: dict[str, list[EligibilityGoldLabel]] = {}
    for label in labels:
        by_state.setdefault(label.label, []).append(label)

    rng = stream("gold.eligibility")
    per_state = max(1, target // max(1, len(by_state)))
    chosen: list[EligibilityGoldLabel] = []
    for state in sorted(by_state):
        bucket = by_state[state]
        rng.shuffle(bucket)
        chosen.extend(bucket[:per_state])
    remaining = [l for l in labels if l not in chosen]
    rng.shuffle(remaining)
    chosen.extend(remaining[: max(0, target - len(chosen))])
    return sorted(chosen, key=lambda l: l.case_id)


# --------------------------------------------------------------------------
# 课程约束
# --------------------------------------------------------------------------


#: 成绩从高到低。故意与 Rules Engine 的 GRADE_ORDER 分开写——
#: 用同一份代码生成标签又用它评测，等于自己给自己打分。
_GRADE_SCALE = ("A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F")
#: "Grade A- or above in" 里的 " or " 会被顶层 OR 切分器当成连接词，
#: 把成绩短语劈成两半。先归一化成不含 or 的记号，再进切分器。
_GRADE_PHRASE = re.compile(r"grade\s+([A-F][+-]?)\s+or\s+above\s+in", re.I)
_GRADE_ATOM = re.compile(r"^GRADEGE_([A-F][+-]?)_IN\s+(.+)$")
_PASS_ATOM = re.compile(r"^pass(?:ing)?\s+grade\s+in\s+(.+)$", re.I)


def _grade_meets(actual: str, required: str) -> bool | None:
    """成绩是否达标。无法比较返回 None（→ unknown），不猜。"""
    actual = actual.strip().upper()
    if required == "PASS":
        if actual in {"P", "PASS"} or actual in _GRADE_SCALE[:-1]:
            return True
        return False if actual == "F" else None
    if actual not in _GRADE_SCALE:
        return None
    return _GRADE_SCALE.index(actual) <= _GRADE_SCALE.index(required)


def _combine(verdicts: list[str], mode: str) -> str:
    if mode == "AND":
        if "not_met" in verdicts:
            return "not_met"
        return "unknown" if "unknown" in verdicts else "met"
    if "met" in verdicts:
        return "met"
    return "unknown" if "unknown" in verdicts else "not_met"


def _split_top_level(expression: str, connective: str) -> list[str]:
    """按顶层 AND/OR 切分；括号内不切。"""
    token = f" {connective} "
    upper = expression.upper()
    parts: list[str] = []
    depth, i, buf = 0, 0, ""
    while i < len(expression):
        ch = expression[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        if depth == 0 and upper.startswith(token, i):
            parts.append(buf)
            buf = ""
            i += len(token)
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return [p.strip() for p in parts if p.strip()]


def _strip_outer_parens(expression: str) -> str:
    expr = expression.strip()
    while expr.startswith("(") and expr.endswith(")"):
        depth = 0
        for index, ch in enumerate(expr):
            depth += ch == "("
            depth -= ch == ")"
            if depth == 0 and index < len(expr) - 1:
                return expr          # 外层括号不是一对，不能剥
        expr = expr[1:-1].strip()
    return expr


def _grade_condition(
    rest: str, required: str, completed: set[str], grades: dict[str, str]
) -> str:
    codes = [f"{a} {b}" for a, b in _COURSE_CODE.findall(rest)]
    if not codes:
        return "unknown"
    verdicts: list[str] = []
    for code in codes:                     # 多个课程代码视为等价择一（HKUST 用 "/"）
        grade = grades.get(code)
        if grade is not None:
            meets = _grade_meets(grade, required)
            verdicts.append("unknown" if meets is None else ("met" if meets else "not_met"))
        elif code in completed:
            verdicts.append("unknown")     # 修过但无成绩记录，判不了
        else:
            verdicts.append("not_met")     # 根本没修
    return _combine(verdicts, "OR")


def _eval_atom(atom: str, completed: set[str], grades: dict[str, str]) -> str:
    if re.search(r"level\s+\d|prior to", atom, re.I):
        return "unknown"
    if re.search(r"\bany\s+(?:one|two|three|\d)\b|至少", atom, re.I):
        # "Any 1 of / any two of" 这类计数选择本评估器不解析——
        # 解析器的无能只能变成 unknown，不能变成一个确定的错标签
        return "unknown"
    match = _GRADE_ATOM.match(atom)
    if match:
        return _grade_condition(match.group(2), match.group(1), completed, grades)
    match = _PASS_ATOM.match(atom)
    if match:
        return _grade_condition(match.group(1), "PASS", completed, grades)
    if re.search(r"grade", atom, re.I):
        return "unknown"                   # 有成绩条件但不认识写法——不猜
    codes = [f"{a} {b}" for a, b in _COURSE_CODE.findall(atom)]
    if not codes:
        return "unknown"
    if "/" in atom:                        # "COMP 2012 / COMP 2012H"：择一
        return "met" if any(c in completed for c in codes) else "not_met"
    return "met" if all(c in completed for c in codes) else "not_met"


def _eval_prereq(expression: str, completed: set[str], grades: dict[str, str]) -> str:
    expr = _strip_outer_parens(
        _GRADE_PHRASE.sub(lambda m: f"GRADEGE_{m.group(1).upper()}_IN", expression)
    )
    ors = _split_top_level(expr, "OR")
    if len(ors) > 1:
        return _combine([_eval_prereq(p, completed, grades) for p in ors], "OR")
    ands = _split_top_level(expr, "AND")
    if len(ands) > 1:
        return _combine([_eval_prereq(p, completed, grades) for p in ands], "AND")
    return _eval_atom(expr, completed, grades)


def _prerequisite_status(
    expression: str | None, completed: set[str], grades: dict[str, str]
) -> tuple[str, str]:
    """三值先修判定。2026-07-31 裁定（docs/T1-T3-adjudication.md T3 节）：

    含成绩条件的表达式**不再一律 unknown**——学生成绩在档且写法可识别时给出
    确定判定。「能不能读荣誉班」是入读资格不是先修条件，不在这个字段里。
    识别不了的写法仍归 unknown：解析器的无能只能变成"待确认"，不能变成判定。
    """
    if not expression:
        return "met", "该课程无先修要求"
    codes = [f"{a} {b}" for a, b in _COURSE_CODE.findall(expression)]
    if not codes:
        return "unknown", f"先修表达式未含可识别课程代码：{expression}"
    status = _eval_prereq(expression, completed, grades)
    if status == "met":
        return "met", f"按已修课程与成绩记录，满足「{expression}」"
    if status == "not_met":
        missing = [c for c in codes if c not in completed]
        detail = f"，缺 {', '.join(missing)}" if missing else ""
        return "not_met", f"按已修课程与成绩记录，不满足「{expression}」{detail}"
    return "unknown", f"先修表达式含规则层无法判定的条件：{expression}"


def _build_course_constraints(
    personas: list[PersonaBundle], catalog: Catalog, target: int
) -> list[CourseConstraintGoldLabel]:
    out: list[CourseConstraintGoldLabel] = []
    deep = [p for p in personas if p.is_deep] or personas[:1]
    # 名额按人分配并把余数补给前几个人，否则整除会让总数少于下限
    quotas = [target // len(deep) + (1 if i < target % len(deep) else 0)
              for i in range(len(deep))]
    for persona_index, persona in enumerate(deep):
        profile = persona.profile
        completed = _completed_courses(persona)
        enrolled_slots = {
            (slot.weekday, slot.start_time)
            for record in persona.course_records if record.term == CURRENT_TERM
            for offering in catalog.offerings_for(record.course_id, CURRENT_TERM)[:1]
            for slot in offering.schedule
        }
        codes = sorted(
            {
                code
                for req in catalog.requirements if req.program_id == profile.program_id
                for code in req.alternatives
                if code in catalog.courses and code not in completed
            }
        )
        for code in codes[: quotas[persona_index]]:
            groups = sorted(
                req.requirement_id
                for req in catalog.requirements
                if req.program_id == profile.program_id and code in req.alternatives
            )
            status, reason = _prerequisite_status(
                catalog.courses[code].prerequisite_expression, completed,
                {r.course_id: r.grade for r in persona.course_records if r.grade},
            )
            offered_terms = [
                term for term in (CURRENT_TERM, *FUTURE_TERMS)
                if catalog.offerings_for(code, term)
            ]
            conflict = any(
                (slot.weekday, slot.start_time) in enrolled_slots
                for offering in catalog.offerings_for(code, CURRENT_TERM)
                for slot in offering.schedule
            )
            out.append(
                CourseConstraintGoldLabel(
                    case_id=f"GOLD-CRS-{profile.student_id}-{code.replace(' ', '')}",
                    student_id=profile.student_id,
                    course_id=code,
                    satisfies_requirement_groups=groups,
                    prerequisite_status=status,
                    offered_in_current_term=CURRENT_TERM in offered_terms,
                    offered_terms=offered_terms,
                    timetable_conflict=conflict,
                    reasons=[
                        reason,
                        f"归属要求组 {', '.join(groups) or '（无）'}",
                        f"开课学期 {', '.join(offered_terms) or '（未来三个学期均无开课）'}",
                        "与本学期已选课程时段冲突" if conflict else "与本学期已选课程无时段冲突",
                    ],
                )
            )
    return sorted(out, key=lambda c: c.case_id)[:target] if target else out


# --------------------------------------------------------------------------
# 重规划情景（每种触发器至少一条，T5 要求 ≥10 类）
# --------------------------------------------------------------------------


def _build_replan(personas: list[PersonaBundle]) -> list[ReplanGoldCase]:
    ids = [p.profile.student_id for p in personas[:3]]
    while len(ids) < 3:                    # tiny 档只有一个 Persona
        ids.append(ids[0])
    a, b, c = ids
    cases = [
        ("new_grade", b, "ISOM 2500 出分为 A-",
         ["skill:statistics", "gap:statistics"], ["goal:GOAL-B-P", "milestone:internship-apply"],
         "成绩只更新相关技能与先修缺口，不改动目标与已排定的申请里程碑"),
        ("course_enrolment_change", a, "退掉 COMP 2012",
         ["course_plan:2026-27_SPRING", "gap:data_structures"], ["opportunity:OPP-EVT-001"],
         "重算学位进度与后续课程推荐，与活动无关"),
        ("calendar_change", b, "周三新增两小时固定会议",
         ["schedule:week-2026-09-14"], ["goal:GOAL-B-P", "course_plan:2026-27_SPRING"],
         "只重排冲突项并恢复缓冲，不推翻长期目标（Spec §16.9）"),
        ("opportunity_change", c, "OPP-LAB-003 截止日期提前 14 天",
         ["opportunity:OPP-LAB-003", "action:apply-lab-003"], ["course_plan:2026-27_SPRING"],
         "只重排受影响机会与近期行动"),
        ("activity_feedback", a, "参加完 OPP-EVT-002 后反馈「对我过于基础」",
         ["preference:event_level"], ["opportunity:OPP-LAB-001"],
         "更新偏好与难度模型，不因个人不适配而降低该活动的全局质量"),
        ("persistent_low_quality", b, "某系列连续两届收到低质量信号",
         ["opportunity:series-low-quality"], ["goal:GOAL-B-P"],
         "替换受影响活动，不推翻无关路径"),
        ("goal_confidence_shift", c, "主目标信心从 0.35 降到 0.2",
         ["goal:GOAL-C-P", "goal:GOAL-C-C", "gap:*"], ["course_plan:completed_terms"],
         "发起 Goal Review 并比较候选方向，已完成学期不受影响"),
        ("weekly_overload", b, "本周计划负荷超出可支配容量",
         ["schedule:week-2026-09-14", "plan_intensity"], ["goal:GOAL-B-P"],
         "自动降级非关键任务并提出新版本，不改目标"),
        ("student_declined", a, "拒绝「简历工作坊」并说明「已经参加过类似的」",
         ["memory:rejection", "recommendation:workshop"], ["opportunity:OPP-LAB-001"],
         "记录原因，避免换个名字重复推荐（T6）"),
        ("profile_update_decided", c, "确认新增技能 machine_learning",
         ["gap:machine_learning", "match:data-scientist"], ["course_plan:completed_terms"],
         "更新证据与缺口，保留原 Evidence 与决定记录"),
        ("new_approved_resource", a, "新审核通过一条机会进入广场",
         ["catalog:plaza", "match:candidate_pool"], ["schedule:week-2026-09-14"],
         "进入资讯广场，并按资格决定是否进入个性化候选池"),
        ("calendar_change", c, "保护区块被临时事件挤压",
         ["schedule:week-2026-09-14", "wellbeing:capacity_signal"], ["goal:GOAL-C-C"],
         "恢复缓冲并触发容量信号；wellbeing 判定仍由 Rules 阈值完成"),
    ]
    return [
        ReplanGoldCase(
            case_id=f"GOLD-REPLAN-{index + 1:02d}",
            student_id=student,
            trigger_type=trigger,
            event=event,
            expected_affected=affected,
            expected_unaffected=unaffected,
            rationale=rationale,
        )
        for index, (trigger, student, event, affected, unaffected, rationale) in enumerate(cases)
    ]


# --------------------------------------------------------------------------
# 记忆回归
# --------------------------------------------------------------------------


def _build_memory_regression(
    personas: list[PersonaBundle], opportunities: list[Opportunity], target: int
) -> list[MemoryRegressionCase]:
    rng = stream("gold.memory")
    deep = [p for p in personas if p.is_deep] or personas[:1]
    pool = [o.opportunity_id for o in opportunities]
    cases: list[MemoryRegressionCase] = []
    # (history, expectation, 应召回的记忆模板序号——对应 events.py 的 memory_templates)
    templates = (
        ("已明确拒绝，理由：与目标无关", "同类项不得再次进入 Top-N（T6）", (0,)),
        ("已完成并提交反思", "不得作为新任务再次推荐", (3,)),
        ("已参加过同系列上一届", "同系列新一届需说明差异才可推荐", (4,)),
        ("反馈「对我过于基础」", "同等难度的活动不得再推荐", (1,)),
        ("已申请但未录取", "可再次推荐，但必须显示上次结果", (4,)),
    )
    index = 0
    while len(cases) < target:
        persona = deep[index % len(deep)]
        subject = pool[(index * 7) % len(pool)]
        history, expectation, memory_indexes = templates[index % len(templates)]
        sid = persona.profile.student_id
        cases.append(
            MemoryRegressionCase(
                case_id=f"GOLD-MEM-{index + 1:02d}",
                student_id=sid,
                subject_id=subject,
                history=history,
                expectation=expectation,
                expected_memory_ids=[f"MEM-{sid}-{m + 1:03d}" for m in memory_indexes],
            )
        )
        index += 1
    return cases


def build_gold_set(
    personas: list[PersonaBundle],
    opportunities: list[Opportunity],
    catalog: Catalog,
    *,
    eligibility: int,
    course_constraints: int,
    memory_regression: int,
) -> GoldSet:
    return GoldSet(
        seed_version=SEED_VERSION,
        eligibility=_build_eligibility(personas, opportunities, catalog, eligibility),
        course_constraints=_build_course_constraints(personas, catalog, course_constraints),
        replan=_build_replan(personas),
        memory_regression=_build_memory_regression(personas, opportunities, memory_regression),
    )
