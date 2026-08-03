"""演示用的确定性路径夹具。

**它不是 A5，也不允许变成 A5。**

D1 要求学生端有三个时间视图（≥12–18 个月 / 本学期 / 未来 2 周）且
"三者数据同源"。同源的那个源是 :class:`PathwayVersion`。而 A5 需要
Vertex 后端，没有 ADC 时整条链路返回 503——于是三个视图会同时空掉，
D1 无法演示。

所以这里造一份**不做任何取舍**的路径：

* 候选来自 Rules Engine 判定可以背书的课程，**按 course_id 字典序**取，
  不打分、不排序、不在竞争选项之间挑优劣（架构第 1 条）；
* 每个计划项的 ``validation_id`` 是 Rules Engine **真的签发**的，
  会被 ``enforce_validation_binding`` 逐条查——不是编出来的字符串；
* ``trigger`` 明写 ``demo_fixture``，前端据此打标，不冒充 A5 的产物。

A5 一旦跑通，POST /pathway 会直接覆盖它。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.academic import CourseStatus
from campuspath_contracts.common import DateRange, LocalizedText
from campuspath_contracts.pathway import (
    Milestone,
    PathwayVersion,
    PlanItem,
    PlanItemKind,
    PlanItemStatus,
)
from campuspath_contracts.validation import BACKING_VERDICTS

#: 每个时间视图各取多少项（课程数, 课外机会数）。刻意小：夹具的作用是
#: 让视图有东西可渲染，不是假装 A5 已经做完了规划。
#: 课外机会（I/J，2026-07-31）：课外活动规划页只显示非课程条目——
#: 夹具若全是课程，那一页对每个演示学生都是空的。
_HORIZON_PLAN = (
    ("next_two_weeks", 2, 1, 14, PlanItemStatus.IN_PROGRESS),
    ("this_term", 3, 2, 120, PlanItemStatus.ACCEPTED),
    ("long_term", 3, 2, 400, PlanItemStatus.PROPOSED),
)


def build_demo_pathway(deps, student_id: str) -> PathwayVersion | None:
    """返回该学生的演示路径；素材不足时返回 ``None``（而不是空路径）。"""
    from campuspath_rules.engine import RulesEngine
    from campuspath_rules.prerequisites import AcademicRecord

    student = deps.students.get(student_id)
    if student is None:
        return None

    rows = deps.records.get(student_id, [])
    done = frozenset(r.course_id for r in rows if r.status is CourseStatus.COMPLETED)
    record = AcademicRecord(
        completed=done, grades={r.course_id: r.grade for r in rows if r.grade}
    )

    # 候选池：本专业要求里还没修的课，按 course_id 排序。没有排名概念。
    candidates: list[str] = sorted(
        {
            course_id
            for requirement in deps.requirements.get(student.program_id, [])
            for course_id in requirement.alternatives
            if course_id not in done and course_id in deps.catalog
        }
    )
    if not candidates:
        return None

    engine = RulesEngine(registry=deps.validations)
    now = datetime.now(timezone.utc)
    today: date = deps.today

    # 课外机会候选：与课程同一纪律——按 opportunity_id 字典序，不打分不排序。
    # 资格判定与 /matches 用同一个 Rules 入口，validation_id 真实签发（B8 不豁免）。
    from campuspath_rules.eligibility import StudentEligibilityFacts

    facts = StudentEligibilityFacts(
        student_id=student_id, year_level=student.year,
        program_id=student.program_id, academic=record,
        has_visa_constraint=any(c.kind == "visa" for c in student.constraints),
        future_offerings=getattr(deps, "future_offerings", None),
    )
    declined = getattr(deps, "declined", {}).get(student_id, set())
    opportunity_candidates = sorted(
        (o for o in getattr(deps, "opportunities", ())
         if o.requirement_categories
         and o.opportunity_id not in declined),
        key=lambda o: o.opportunity_id,
    )

    fixture_note = LocalizedText(
        zh_Hans="演示夹具：由确定性规则判定生成，未经 A5 取舍",
        en="Demo fixture: rule-derived, not an A5 trade-off",
    )

    items: list[PlanItem] = []
    milestones: list[Milestone] = []
    horizons: list[str] = []
    cursor = 0
    opp_cursor = 0

    for horizon, course_count, opp_count, offset_days, status in _HORIZON_PLAN:
        picked: list[PlanItem] = []
        start = today + timedelta(days=offset_days - 7)
        while len(picked) < course_count and cursor < len(candidates):
            course_id = candidates[cursor]
            cursor += 1
            course = deps.catalog[course_id]
            validation = engine.validate_prerequisite(
                course_id, course.prerequisite_expression, record, now=now
            )
            # 判定不能背书就跳过。夹具**也要**过 B8 那道闸门——
            # 一份自己都过不了闸门的演示数据没有演示价值。
            if validation.verdict not in BACKING_VERDICTS:
                continue
            picked.append(
                PlanItem(
                    plan_item_id=f"PI-{student_id}-{course_id.replace(' ', '')}",
                    kind=PlanItemKind.COURSE,
                    subject_id=course_id,
                    # 目录只有英文标题（HKUST 公开目录如此）。不假造中文译名——
                    # 两侧都给英文，比给一个我们没有出处的翻译诚实。
                    title=LocalizedText(zh_Hans=course.title, en=course.title),
                    date_range=DateRange(start=start,
                                         end=start + timedelta(days=offset_days)),
                    workload_hours=float(course.credits or 3) * 3.0,
                    status=status,
                    assumptions=(fixture_note,),
                    validation_id=validation.validation_id,
                )
            )
        opp_picked = 0
        while opp_picked < opp_count and opp_cursor < len(opportunity_candidates):
            opportunity = opportunity_candidates[opp_cursor]
            opp_cursor += 1
            _outcome, validation = engine.validate_eligibility(
                opportunity, facts, today, now
            )
            if validation.verdict not in BACKING_VERDICTS:
                continue
            opp_picked += 1
            # 2026-08-02 用户报障修复：机会类条目的日期用**活动真实起止**
            # （有 starts_at 就不再拍档期桶日期）——否则「未来两周」标签会
            # 列出一个 11 月的活动，而日历在这两周里当然找不到它，两个视图
            # 互相矛盾。没有真实时间的机会才退回档期桶。
            if opportunity.starts_at is not None:
                item_range = DateRange(
                    start=opportunity.starts_at.date(),
                    end=(opportunity.ends_at.date()
                         if opportunity.ends_at is not None
                         else opportunity.starts_at.date()),
                )
            else:
                item_range = DateRange(start=start,
                                       end=start + timedelta(days=offset_days))
            picked.append(
                PlanItem(
                    plan_item_id=f"PI-{student_id}-{opportunity.opportunity_id}",
                    kind=PlanItemKind.OPPORTUNITY,
                    subject_id=opportunity.opportunity_id,
                    title=opportunity.title_localized
                    or LocalizedText(zh_Hans=opportunity.title, en=opportunity.title),
                    date_range=item_range,
                    workload_hours=float(opportunity.workload_hours_total or 20.0),
                    status=status,
                    assumptions=(fixture_note,),
                    validation_id=validation.validation_id,
                )
            )
        if not picked:
            continue
        horizons.append(horizon)
        items.extend(picked)
        milestones.append(
            Milestone(
                milestone_id=f"MS-{student_id}-{horizon}",
                title=LocalizedText(zh_Hans=horizon, en=horizon),
                plan_item_ids=tuple(p.plan_item_id for p in picked),
            )
        )

    if not items or not horizons:
        return None

    return PathwayVersion(
        pathway_id=f"PW-{student_id}-demo",
        student_id=student_id,
        version=1,
        created_at=now,
        trigger="demo_fixture",
        horizons=tuple(horizons),  # type: ignore[arg-type]
        assumptions=(
            LocalizedText(
                zh_Hans="这是演示夹具，不是 A5 的规划结果。数据全部为合成数据。",
                en="Demo fixture, not an A5 plan. All data is synthetic.",
            ),
        ),
        milestones=tuple(milestones),
        plan_items=tuple(items),
    )
