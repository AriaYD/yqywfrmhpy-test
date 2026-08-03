"""A5 线上规划生成（审计 E 修复，2026-08-02）。

此前线上 `GET /pathway` 只有演示夹具（字典序、不取舍），`PathwayAgent`
的 `build_pathway` / `generate_course_plans` 只被测试调用——审计判为死链。
本模块把 A5 类本体接进线上路径：

* **取舍输入是结构化事实**：/matches 的确定性六维分（已带 Rules 资格凭据）、
  目标集、记忆中心的 advisory 摘要——不喂原始文本，日历详情照旧进不来；
* **选择与分桶确定性**（同分刷新不跳变，D6.7）：按分数取前 N，机会按真实
  起止日落 两周/学期/学年 三档；课程项经 `generate_course_plans` 三变体
  并行（S1），balanced 变体进 `PathwayVersion.course_plan`；
* **容量修复循环真实运行**（S2）：近两周档超预算 → 丢掉该档分数最低的
  机会重建，`run_repair_loop` 保证出口一定过校验；
* **模型只产理由文案**：一次调用，失败（无 ADC / 桩未预设）→ 返回 None，
  端点回落演示夹具并如实标注——**A5 拿不到模型就不冒充 A5**。

每个 PlanItem 的 `validation_id` 都是 Rules 已签发的真凭据（B8 不豁免）：
机会项复用 /matches 的资格凭据，课程项由先修判定当场签发。
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.academic import CoursePlanItem, CoursePlanVariant, CourseStatus
from campuspath_contracts.common import DateRange, LocalizedText
from campuspath_contracts.pathway import (
    Milestone,
    PathwayVersion,
    PlanItem,
    PlanItemKind,
    PlanItemStatus,
)
from campuspath_contracts.validation import BACKING_VERDICTS

#: 三档强度的完整口径（2026-08-03 用户裁定二改：**近两周活动数上限
#: 3/5/7**——「进取两周 7 个已经很离谱了」，这是天花板不是配额，实际
#: 条目还受两周内真实供给限制）。(课程门数, 活动池上限, 近两周条目上限,
#: 近两周时长预算)。时长按 11h/日模型折算：每活动含准备约 6–8h →
#: 3/5/7 个 ≈ 20/30/45h，作为条目上限之外的第二道闸。
_INTENSITY_PLAN = {
    CoursePlanVariant.LOW_LOAD: (2, 8, 3, 20.0),
    CoursePlanVariant.BALANCED: (3, 10, 5, 30.0),
    CoursePlanVariant.AMBITIOUS: (4, 12, 7, 45.0),
}


def goal_fingerprint(goals) -> str:
    basis = sorted((g.goal_id, g.target_name or "", str(g.role)) for g in goals)
    return hashlib.sha1(json.dumps(basis, ensure_ascii=False).encode()).hexdigest()[:12]


def _bucket(starts: date | None, today: date) -> str:
    if starts is None:
        return "this_term"
    days = (starts - today).days
    if days < 14:
        return "next_two_weeks"
    if days < 120:
        return "this_term"
    return "long_term"


def build_a5_pathway(
    deps,
    student_id: str,
    *,
    matches,
    model,
    memory_notes: tuple[str, ...] = (),
    carry_over: tuple[PlanItem, ...] = (),
    version: int = 1,
    intensity: CoursePlanVariant = CoursePlanVariant.BALANCED,
) -> PathwayVersion | None:
    """生成 A5 路径；模型理由调用失败返回 ``None``（调用方回落夹具）。"""
    from campuspath_agents.model import ModelRequest
    from campuspath_agents.roster import AgentId, PathwayAgent
    from campuspath_agents.tools import belt_for
    from campuspath_rules.engine import RulesEngine
    from campuspath_rules.prerequisites import AcademicRecord

    student = deps.students.get(student_id)
    if student is None or model is None:
        return None
    goals = deps.goals.get(student_id, ())
    if not goals:
        return None

    today: date = deps.today
    now = datetime.now(timezone.utc)
    opportunities = {o.opportunity_id: o for o in getattr(deps, "opportunities", ())}
    course_count, pool_cap, near_cap, near_budget = _INTENSITY_PLAN[intensity]
    declined = getattr(deps, "declined", {}).get(student_id, set())
    carry_over = tuple(i for i in carry_over if i.subject_id not in declined)
    carried_subjects = {i.subject_id for i in carry_over}

    # ── 机会侧：分数已是确定性六维加权（含资格因子），取前 8 做取舍池 ──
    pool = []
    for match in sorted(matches, key=lambda m: (-m.score, m.opportunity_id)):
        opp = opportunities.get(match.opportunity_id)
        if (opp is None or match.opportunity_id in carried_subjects
                or match.opportunity_id in declined):
            continue
        if match.eligibility.validation_id is None:
            continue
        pool.append((match, opp))
        if len(pool) >= pool_cap:
            break

    # ── 课程侧：先修判定能背书的候选（Rules 当场签发凭据）──
    rows = deps.records.get(student_id, [])
    done = frozenset(r.course_id for r in rows if r.status is CourseStatus.COMPLETED)
    record = AcademicRecord(
        completed=done, grades={r.course_id: r.grade for r in rows if r.grade})
    engine = RulesEngine(registry=deps.validations)
    course_pool: list[tuple[str, object]] = []
    for course_id in sorted({
            cid for req in deps.requirements.get(student.program_id, [])
            for cid in req.alternatives if cid not in done and cid in deps.catalog}):
        course = deps.catalog[course_id]
        validation = engine.validate_prerequisite(
            course_id, course.prerequisite_expression, record, now=now)
        if validation.verdict in BACKING_VERDICTS:
            course_pool.append((course_id, validation))
        if len(course_pool) >= 6:
            break

    a5 = PathwayAgent(AgentId.A5_PATHWAY, belt_for(AgentId.A5_PATHWAY, {}), model)

    # ── 模型只产理由（一次调用；失败 = 没有 A5 结果）──
    facts = {
        "goals": [{"id": g.goal_id, "target": g.target_name,
                   "role": str(g.role)} for g in goals],
        "picked_opportunities": [
            {"id": o.opportunity_id, "title": o.title, "score": m.score,
             "starts": o.starts_at.date().isoformat() if o.starts_at else None}
            for m, o in pool],
        "picked_courses": [cid for cid, _ in course_pool],
        "advisory_memories": list(memory_notes),
    }
    try:
        raw = model.generate(ModelRequest(
            system=(
                "你是 A5 规划 Agent。下面数据块是已合规的候选（资格与凭据已由"
                "规则引擎判定，你不得改判资格）。为每个候选写一行取舍理由："
                "id<TAB>中文理由<TAB>英文理由；最后一行写 overall<TAB>整体规划"
                "思路中文<TAB>英文。只输出这些行。"),
            data=(json.dumps(facts, ensure_ascii=False),),
            purpose=f"a5-pathway:{student_id}",
        ))
    except Exception:
        return None
    reasons: dict[str, LocalizedText] = {}
    overall = LocalizedText(zh_Hans="A5 规划：在合规候选间按目标契合与容量做取舍",
                            en="A5 plan: trade-offs among rule-cleared candidates")
    for line in raw.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) >= 3 and parts[0]:
            text = LocalizedText(zh_Hans=parts[1][:300], en=parts[2][:300])
            if parts[0] == "overall":
                overall = text
            else:
                reasons[parts[0]] = text

    # ── 课程计划三变体（S1 并行）；balanced 进 course_plan ──
    # 学期码只认教务 TermCode（seed manifest 的 current_term，Deps 构造时
    # 缺失即 KeyError 响亮失败，无需兜底——审查 L-1/L-2：getattr 默认值 +
    # 日期推导会把重构错误静默吞成"看起来也对"的产物）。
    # 历史：曾把学生自述的 y1s2 年级码塞进这里 → 整页 500；用户随后裁定
    # 自述学期通道全部撤除（契约已无该字段），学期语义全局只认教务侧。
    term = deps.current_term

    def build_items(variant: CoursePlanVariant) -> tuple[CoursePlanItem, ...]:
        count = _INTENSITY_PLAN[variant][0]
        return tuple(
            CoursePlanItem(
                course_id=cid, term=term,
                credits=float(deps.catalog[cid].credits or 3),
                validation_id=validation.validation_id,
                rationale=reasons.get(cid),
            )
            for cid, validation in course_pool[:count])

    course_plan = None
    if course_pool:
        # S1 三变体照常并行生成；上屏档位由学生选择（2026-08-03 用户问出
        # 「说明书有三档、界面选不了」的缺口）——默认 balanced
        variants = a5.generate_course_plans(student_id, term, build_items)
        course_plan = next(
            (v for v in variants if v.variant is intensity), None)
        if course_plan is not None:
            course_plan = course_plan.model_copy(update={
                "explanation": overall, "goal_value": round(sum(
                    m.score for m, _ in pool[:3]) / max(1, len(pool[:3])), 4)})

    # ── 组装 + 容量修复循环（S2）──
    def assemble(drop_ids: tuple[str, ...]) -> PathwayVersion:
        items: list[PlanItem] = list(carry_over)
        buckets: dict[str, list[PlanItem]] = {
            "next_two_weeks": [], "this_term": [], "long_term": []}
        for item in carry_over:
            buckets.setdefault(_bucket(item.date_range.start, today), []).append(item)
        near_used = sum(
            1 for i in carry_over
            if _bucket(i.date_range.start, today) == "next_two_weeks")
        for match, opp in pool:
            if opp.opportunity_id in drop_ids:
                continue
            horizon = _bucket(opp.starts_at.date() if opp.starts_at else None, today)
            if horizon == "next_two_weeks":
                if near_used >= near_cap:
                    continue        # 用户裁定：近两周条目天花板 3/5/7
                near_used += 1
            start = (opp.starts_at.date() if opp.starts_at
                     else today + timedelta(days=30))
            end = (opp.ends_at.date() if opp.ends_at else start)
            item = PlanItem(
                plan_item_id=f"PI-{student_id}-{opp.opportunity_id}",
                kind=PlanItemKind.OPPORTUNITY,
                subject_id=opp.opportunity_id,
                title=opp.title_localized
                or LocalizedText(zh_Hans=opp.title, en=opp.title),
                date_range=DateRange(start=start, end=end),
                workload_hours=float(opp.workload_hours_total or 10.0),
                status=PlanItemStatus.PROPOSED,
                assumptions=tuple(x for x in (reasons.get(opp.opportunity_id),)
                                  if x is not None),
                validation_id=match.eligibility.validation_id,
            )
            items.append(item)
            buckets[horizon].append(item)
        if course_plan is not None:
            term_start = today + timedelta(days=7)
            for cp_item in course_plan.course_items:
                course = deps.catalog[cp_item.course_id]
                item = PlanItem(
                    plan_item_id=(f"PI-{student_id}-"
                                  f"{cp_item.course_id.replace(' ', '')}"),
                    kind=PlanItemKind.COURSE,
                    subject_id=cp_item.course_id,
                    title=LocalizedText(zh_Hans=course.title, en=course.title),
                    date_range=DateRange(start=term_start,
                                         end=term_start + timedelta(days=110)),
                    workload_hours=float(cp_item.credits) * 3.0,
                    status=PlanItemStatus.PROPOSED,
                    assumptions=tuple(x for x in (cp_item.rationale,)
                                      if x is not None),
                    validation_id=cp_item.validation_id,
                )
                items.append(item)
                buckets["this_term"].append(item)
        horizons = tuple(h for h in ("next_two_weeks", "this_term", "long_term")
                         if buckets[h])
        milestones = tuple(
            Milestone(milestone_id=f"MS-{student_id}-{h}",
                      title=LocalizedText(zh_Hans=h, en=h),
                      plan_item_ids=tuple(i.plan_item_id for i in buckets[h]))
            for h in horizons)
        return PathwayVersion(
            pathway_id=f"PW-{student_id}-a5-{version}",
            student_id=student_id, version=version, created_at=now,
            trigger=f"a5:{goal_fingerprint(goals)}:{intensity.value}",
            horizons=horizons or ("this_term",),
            assumptions=(overall,),
            milestones=milestones,
            plan_items=tuple(items),
            course_plan=course_plan,
        )

    dropped: list[str] = []

    def build(feedback: tuple[str, ...]) -> PathwayVersion:
        if feedback:
            # 审查 M9：一轮砍到预算以内（按分数升序累减），不再每轮只砍
            # 一条——修复循环上限 3 轮，逐条砍会在 ≥4 个超载项时静默失败
            near = sorted(
                ((m, o) for m, o in pool
                 if o.opportunity_id not in dropped
                 and _bucket(o.starts_at.date() if o.starts_at else None,
                             today) == "next_two_weeks"),
                key=lambda t: t[0].score)
            excess = sum(float(o.workload_hours_total or 10.0)
                         for _, o in near) - near_budget
            for m, o in near:
                if excess <= 0:
                    break
                dropped.append(o.opportunity_id)
                excess -= float(o.workload_hours_total or 10.0)
        return assemble(tuple(dropped))

    def validate(candidate: PathwayVersion) -> list[str]:
        # 只计机会类新增：课程是整学期负荷（有自己的学分预算），
        # 已批准携带项是既成事实——都不该挤占「近两周新增」预算
        near_hours = sum(
            i.workload_hours for i in candidate.plan_items
            if i.kind is PlanItemKind.OPPORTUNITY
            and _bucket(i.date_range.start, today) == "next_two_weeks"
            and i.subject_id not in carried_subjects)
        if near_hours > near_budget:
            return [f"near-term overload: {near_hours:.0f}h > "
                    f"{near_budget:.0f}h"]
        return []

    try:
        pathway, _rounds = a5.build_pathway(student_id, build, validate)
    except Exception:
        # 含 ConstraintRepairFailed：留日志再回落，不静默（审查 M9/M10）
        import logging
        logging.getLogger("campuspath").exception("A5 修复循环未收敛，回落夹具")
        return None
    if not pathway.plan_items:
        return None
    return pathway
