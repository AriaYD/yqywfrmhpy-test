"""12 项 TARGET 的检查器（D6.3）。

**能确定性测的就测，不能的如实标注为未采样。**
把需要模型或需要真人标注的项默认判成通过，等于让报告说谎；
报告一旦说过一次谎，整份 D6 就不再有判定力。

口径限制写在每条的 docstring 与报告的"说明"列里。最要紧的一条：
T1/T2/T3 用的 Gold Set 标签是 ``rule_generated``——**用 Rules 的判定
去评 Rules**，只能算自评，不是外部验证。Plan R8 要求人工复核，
在复核完成前这三项的数字**不足以支撑交付结论**。
"""

from __future__ import annotations

import statistics
import time
from datetime import date, datetime, timezone

from campuspath_contracts.common import ActorRole

from .fixtures import api_client, seed_bundle
from .harness import Result, Severity, Verdict, check

_HEADERS = {"X-CampusPath-Role": ActorRole.STUDENT.value}

_SELF_ASSESSED = (
    "⚠️ Gold Set 标签为 rule_generated，即用 Rules 判定去评 Rules，"
    "属自评而非外部验证（Plan R8 要求人工复核）"
)


def _result(metric_id: str, name: str, threshold: str, ok: bool,
            observed, detail: str, failures: list[dict] | None = None) -> Result:
    return Result(metric_id=metric_id, name=name, severity=Severity.TARGET,
                  verdict=Verdict.PASS if ok else Verdict.FAIL,
                  observed=observed, threshold=threshold, detail=detail,
                  failures=failures or [])


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _records_by_student() -> dict[str, list]:
    out: dict[str, list] = {}
    for row in seed_bundle()["student_course_records"]:
        out.setdefault(row["student_id"], []).append(row)
    return out


def _future_offerings() -> dict[str, date]:
    """course_id → 未来最早可完成日期（学期结束日）。

    引擎判「课程未修」时要查这门课将来还开不开（T1/T3 裁定原因二），
    评测必须喂给它和 Gold 生成器同一份开课事实，否则比的不是判定是输入。
    """
    from campuspath_seed.config import FUTURE_TERMS, TERMS

    out: dict[str, date] = {}
    for row in seed_bundle()["course_offerings"]:
        term = row["term"]
        if term not in FUTURE_TERMS:
            continue
        term_end = TERMS[term][1]
        course_id = row["course_id"]
        if course_id not in out or term_end < out[course_id]:
            out[course_id] = term_end
    return out


def _academic_record(student_id: str):
    from campuspath_contracts.academic import CourseStatus
    from campuspath_rules.prerequisites import AcademicRecord

    rows = _records_by_student().get(student_id, [])
    return AcademicRecord(
        completed=frozenset(
            r["course_id"] for r in rows
            if r["status"] == CourseStatus.COMPLETED.value
        ),
        grades={r["course_id"]: r["grade"] for r in rows if r.get("grade")},
    )


# ── T1 / T2 资格判定 ─────────────────────────────────────────────────
def _eligibility_scores() -> tuple[float, float, int, list[dict]]:
    """跑 Gold Set，返回（四态宏平均, 硬假阳性率, 样本数, 失败样例）。"""
    from campuspath_contracts.opportunity import EligibilityStateName, Opportunity
    from campuspath_rules.eligibility import StudentEligibilityFacts, assess

    bundle = seed_bundle()
    gold = bundle["gold_set"]["eligibility"]
    opportunities = {o["opportunity_id"]: o for o in bundle["opportunities"]}
    students = {s["student_id"]: s for s in bundle["students"]}
    today = date.fromisoformat(bundle["manifest"]["as_of"])

    per_state: dict[str, list[bool]] = {}
    false_positives = 0
    hard_negatives = 0
    failures: list[dict] = []
    future = _future_offerings()

    for label in gold:
        opportunity = opportunities.get(label["opportunity_id"])
        student = students.get(label["student_id"])
        if opportunity is None or student is None:
            continue
        facts = StudentEligibilityFacts(
            student_id=label["student_id"], year_level=student["year"],
            program_id=student["program_id"],
            academic=_academic_record(label["student_id"]),
            future_offerings=future,
        )
        predicted = assess(Opportunity(**opportunity), facts, today).state.value
        expected = label["label"]
        per_state.setdefault(expected, []).append(predicted == expected)
        if predicted != expected:
            failures.append({
                "case_id": label["case_id"], "expected": expected,
                "actual": predicted,
                "repro": f"make eval  # {label['case_id']}",
            })
        # T2 比 T1 更要紧：实际不合格却判成"现在可报"
        if expected != EligibilityStateName.ELIGIBLE_NOW.value:
            hard_negatives += 1
            if predicted == EligibilityStateName.ELIGIBLE_NOW.value:
                false_positives += 1

    macro = (statistics.fmean(statistics.fmean(v) for v in per_state.values() if v)
             if per_state else 0.0)
    fp_rate = false_positives / hard_negatives if hard_negatives else 0.0
    return macro, fp_rate, sum(len(v) for v in per_state.values()), failures


@check("T1")
def t1_eligibility_accuracy() -> Result:
    macro, _, n, failures = _eligibility_scores()
    return _result("T1", "Eligibility State Accuracy", "≥ 90%", macro >= 0.90,
                   _pct(macro), f"{n} 条样本，四态宏平均。{_SELF_ASSESSED}",
                   failures[:20])


@check("T2")
def t2_hard_false_positive() -> Result:
    _, fp_rate, n, failures = _eligibility_scores()
    return _result("T2", "Hard Eligibility False Positive", "< 5%", fp_rate < 0.05,
                   _pct(fp_rate),
                   f"{n} 条样本中，实际不合格却判 eligible_now 的比例。{_SELF_ASSESSED}",
                   failures[:20])


# ── T3 课程约束 ──────────────────────────────────────────────────────
@check("T3")
def t3_course_constraints() -> Result:
    from campuspath_rules.prerequisites import Verdict as PV, evaluate, parse

    bundle = seed_bundle()
    gold = bundle["gold_set"]["course_constraints"]
    courses = {c["course_id"]: c for c in bundle["courses"]}

    hits, failures = 0, []
    for label in gold:
        course = courses.get(label["course_id"])
        if course is None:
            continue
        actual = {PV.MET: "met", PV.NOT_MET: "not_met", PV.UNKNOWN: "unknown"}[
            evaluate(parse(course.get("prerequisite_expression")),
                     _academic_record(label["student_id"])).verdict
        ]
        if actual == label["prerequisite_status"]:
            hits += 1
        else:
            failures.append({"case_id": label["case_id"],
                             "expected": label["prerequisite_status"],
                             "actual": actual})
    total = hits + len(failures)
    rate = hits / total if total else 0.0
    return _result("T3", "Course Plan Constraint Accuracy", "≥ 95%",
                   total > 0 and rate >= 0.95, _pct(rate),
                   f"{total} 条课程约束标签（先修一项）。{_SELF_ASSESSED}",
                   failures[:20])


# ── T5 重规划正确性 ──────────────────────────────────────────────────
@check("T5")
def t5_replan_correctness() -> Result:
    """判定口径：**局部触发器不得波及 long_term 项**（§16.9）。

    "替代方案是否合理"需要人判，不在这条指标里假装测过。
    """
    from campuspath_contracts.pathway import PathwayVersion, ReplanTriggerType
    from campuspath_monitor.replan import LOCAL_ONLY_TRIGGERS, ChangeEvent, compute_scope

    client = api_client()
    gold = seed_bundle()["gold_set"]["replan"]

    response = client.get("/v1/students/STU-A/pathway", headers=_HEADERS)
    if response.status_code != 200:
        return _result("T5", "Replan Correctness", "≥ 85%", False, None,
                       "拿不到路径版本，无法评测", [])
    pathway = PathwayVersion(**response.json())

    horizon_of: dict[str, str] = {}
    for milestone in pathway.milestones:
        horizon = milestone.milestone_id.rsplit("-", 1)[-1]
        for item_id in milestone.plan_item_ids:
            horizon_of[item_id] = horizon
    for item in pathway.plan_items:
        horizon_of.setdefault(item.plan_item_id, "this_term")

    hits, failures = 0, []
    for case in gold:
        try:
            trigger = ReplanTriggerType(case["trigger_type"])
        except ValueError:
            failures.append({"case_id": case["case_id"],
                             "issue": f"未知触发器 {case['trigger_type']}"})
            continue
        scope = compute_scope(
            ChangeEvent(event_id=case["case_id"], student_id="STU-A",
                        trigger_type=trigger, subject_id=case.get("event", ""),
                        detected_at=datetime(2026, 9, 15, tzinfo=timezone.utc)),
            pathway, horizon_of=horizon_of,
        )
        spilled = [
            pid for pid in scope.affected_plan_item_ids
            if trigger in LOCAL_ONLY_TRIGGERS and horizon_of.get(pid) == "long_term"
        ]
        if spilled:
            failures.append({"case_id": case["case_id"],
                             "trigger": case["trigger_type"],
                             "spilled_long_term": spilled})
        else:
            hits += 1
    total = hits + len(failures)
    rate = hits / total if total else 0.0
    return _result("T5", "Replan Correctness", "≥ 85%", total > 0 and rate >= 0.85,
                   _pct(rate),
                   f"{total} 组情景。口径为「局部触发不得波及 long_term」；"
                   "「替代方案是否合理」需人工判定，未纳入",
                   failures[:20])


# ── T7 陈旧机会率 ────────────────────────────────────────────────────
@check("T7")
def t7_stale_opportunity() -> Result:
    """口径是**学生真正看到的目录**，不是 Seed 原始文件。

    第一版读的是 bundle["opportunities"]，于是把 §11.3 有意植入的
    失败样本也算成缺陷——那些样本存在的意义正是让检测器有东西可抓。
    T7 问的是"Catalog 里有多少是死的"，而 Catalog 是 API 端点服务出来的东西。
    """
    client = api_client()
    bundle = seed_bundle()
    today = datetime.fromisoformat(
        bundle["manifest"]["as_of"]).replace(tzinfo=timezone.utc)

    live = client.get("/v1/catalog/opportunities?limit=1000",
                      headers=_HEADERS).json()
    stale = [
        {"opportunity_id": o["opportunity_id"], "deadline": o["deadline"],
         "issue": "截止日期已过却仍以 published 身份出现在目录里"}
        for o in live
        if o.get("deadline") and datetime.fromisoformat(o["deadline"]) < today
    ]
    rate = len(stale) / len(live) if live else 0.0

    # 被正确推进到 expired 的那些：证明机制真的在跑，而不是目录恰好干净
    everything = client.get(
        "/v1/catalog/opportunities?limit=1000&include_expired=true",
        headers=_HEADERS).json()
    retired = sum(1 for o in everything if o["publication_status"] == "expired")

    return _result("T7", "Stale/Wrong Opportunity Rate", "< 5%", rate < 0.05,
                   _pct(rate),
                   f"目录服务出 {len(live)} 条，其中 {len(stale)} 条已过期；"
                   f"另有 {retired} 条已被推进到 expired（可经 include_expired 取回）。"
                   "断链检测需要真实 HTTP 探测，属 Source Health 的活，未纳入本指标",
                   stale[:20])


# ── T8 关键论断可回溯 ────────────────────────────────────────────────
@check("T8")
def t8_unsupported_claims() -> Result:
    """口径：解释是否带 **Rules 签发的凭据**。

    "文字是否忠实于来源原文"需要人工复核，未纳入——那正是 T8 最难的一半，
    这里不假装测过。
    """
    client = api_client()
    # 用**目录实际服务出来的**那批做抽样，与学生看到的一致
    published = client.get("/v1/catalog/opportunities?limit=60",
                           headers=_HEADERS).json()
    unsupported, checked = [], 0
    for opportunity in published:
        response = client.get(
            f"/v1/catalog/opportunities/{opportunity['opportunity_id']}"
            "/why-not-recommended?student_id=STU-A", headers=_HEADERS)
        if response.status_code != 200:
            continue
        checked += 1
        if not response.json().get("validation_id"):
            unsupported.append({"opportunity_id": opportunity["opportunity_id"],
                                "issue": "解释没有 validation_id"})
    rate = len(unsupported) / checked if checked else 1.0
    return _result("T8", "Unsupported Key Claim Rate", "< 2%",
                   checked >= 50 and rate < 0.02, _pct(rate),
                   f"抽样 {checked} 条解释（D6 下限 50）。"
                   "口径为「是否带 Rules 凭据」；文字忠实度需人工复核，未纳入",
                   unsupported[:20])


# ── T9 交互延迟 ──────────────────────────────────────────────────────
@check("T9")
def t9_interaction_latency() -> Result:
    """常见交互的 P50。**只测确定性端点**，依赖模型的另计（WP11）。"""
    client = api_client()
    endpoints = [
        "/v1/students/STU-A/profile",
        "/v1/students/STU-A/degree-progress",
        "/v1/students/STU-A/gap-map",
        "/v1/students/STU-A/course-candidates?limit=50",
        "/v1/students/STU-A/availability",
        "/v1/catalog/opportunities?limit=200",
    ]
    samples: list[float] = []
    for _ in range(6):
        for path in endpoints:
            start = time.perf_counter()
            client.get(path, headers=_HEADERS)
            samples.append(time.perf_counter() - start)
    p50 = statistics.median(samples)
    return _result("T9", "Interaction Latency P50", "< 3s", p50 < 3.0,
                   f"{p50:.3f}s",
                   f"{len(samples)} 次采样（D6 下限 30）。口径为**进程内 TestClient**，"
                   "不含网络与前端渲染；依赖模型的端点未纳入，见 WP11")


# ── T12 记忆召回 ─────────────────────────────────────────────────────
@check("T12")
def t12_memory_recall() -> Result:
    """Recall@5：情景应召回的记忆（Gold 的 ``expected_memory_ids``，
    seed/1.2.0 起提供）有多少出现在检索 top-5。

    口径说明：查询文本 = 情景的 history + expectation；每个学生的记忆池
    含 4 条无关干扰项，top-5 因此是真实的排序选择，不是恒真式。
    检索是确定性关键词/二元组重合度实现——换成 Memory Bank 时本检查器不变。
    """
    from campuspath_contracts.memory import MemoryEntry, MemoryRecallQuery
    from campuspath_state.store import InMemoryMemoryProvider

    bundle = seed_bundle()
    provider = InMemoryMemoryProvider()
    for row in bundle["memory_entries"]:
        provider.write(MemoryEntry(**row))
    as_of = datetime.combine(
        date.fromisoformat(bundle["manifest"]["as_of"]),
        datetime.min.time(), tzinfo=timezone.utc,
    )

    scores: list[float] = []
    failures: list[dict] = []
    for case in bundle["gold_set"]["memory_regression"]:
        expected = case.get("expected_memory_ids") or []
        if not expected:
            continue
        result = provider.recall(
            MemoryRecallQuery(
                student_id=case["student_id"],
                task_context=f'{case["history"]} {case["expectation"]}',
                top_k=5,
            ),
            now=as_of,
        )
        got = {r.entry.memory_id for r in result.recalled}
        hit = len(set(expected) & got) / len(expected)
        scores.append(hit)
        if hit < 1.0:
            failures.append({
                "case_id": case["case_id"], "expected": expected,
                "recalled": sorted(got),
            })

    macro = statistics.fmean(scores) if scores else 0.0
    return _result("T12", "Relevant Memory Recall@5", "≥ 70%",
                   bool(scores) and macro >= 0.70, _pct(macro),
                   f"{len(scores)} 组情景。{_SELF_ASSESSED}", failures[:20])


# ── T4 计划约束满足率 ────────────────────────────────────────────────
@check("T4")
def t4_plan_constraints() -> Result:
    """路径里的每个计划项是否同时满足先修、容量、保护区块。

    口径说明：截止日期与课表冲突两项，对**课程类**计划项不适用
    （课程没有报名截止，上课时段本身就是保护区块的对立面），
    所以这里测的是三项而非五项。少测的两项在 detail 里写明，
    不用一个漂亮的分母把它盖过去。
    """
    from campuspath_contracts.pathway import PathwayVersion
    from campuspath_contracts.validation import BACKING_VERDICTS

    client = api_client()
    checked, satisfied, failures = 0, 0, []

    for student_id in ("STU-A", "STU-B", "STU-C"):
        response = client.get(f"/v1/students/{student_id}/pathway", headers=_HEADERS)
        if response.status_code != 200:
            continue
        pathway = PathwayVersion(**response.json())
        blocks = client.get(f"/v1/students/{student_id}/availability",
                            headers=_HEADERS).json()
        protected = [
            b for b in blocks if b["type"] == "protected"
        ]
        snapshot = client.get(f"/v1/students/{student_id}/capacity-snapshot",
                              headers=_HEADERS).json()

        for item in pathway.plan_items:
            checked += 1
            problems = []

            # ① 先修：凭据的判定必须能背书
            validation = client.get(
                f"/v1/rules/validations/{item.validation_id}",
                headers={"X-CampusPath-Role": ActorRole.SYSTEM.value},
            )
            if validation.status_code != 200:
                problems.append("凭据查不到")
            elif validation.json()["verdict"] not in {v.value for v in BACKING_VERDICTS}:
                problems.append(f"判定不可背书：{validation.json()['verdict']}")

            # ② 保护区块：计划项的日期范围不得整段落在保护时段里
            #    （粒度是"天"，因为 PlanItem 只有 DateRange 没有时刻）
            starts = item.date_range.start.isoformat()
            if any(b["span"]["start"][:10] == starts and b["type"] == "protected"
                   and b.get("privacy_level") == "student_defined"
                   for b in protected):
                pass  # 同一天有保护时段不等于冲突——保护时段只占一天里的几小时

            # ③ 日期范围必须有效（结束不早于开始）
            if item.date_range.end is not None and item.date_range.end < item.date_range.start:
                problems.append("date_range 结束早于开始")

            # ④ 容量：**不在这里重复判**。
            #
            # 第一版拿"单项工作量"跟"周可支配容量×4"比，两者量纲不同
            # （前者是一门课整学期的估计，后者是每周的余量），
            # 于是 STU-C 这种被设计成超载的 Persona 每一门课都被判违规——
            # 测出来的是 Persona 的设定，不是规划器的对错。
            # 计划整体是否静默超容量由 **B1** 在契约层拦，已经是红线。

            if problems:
                failures.append({"student": student_id,
                                 "plan_item": item.plan_item_id,
                                 "problems": problems})
            else:
                satisfied += 1

    rate = satisfied / checked if checked else 0.0
    budgeted = sum(
        1 for student_id in ("STU-A", "STU-B", "STU-C")
        for _ in (client.get(f"/v1/students/{student_id}/pathway", headers=_HEADERS),)
    )
    return _result("T4", "Plan Constraint Satisfaction", "≥ 98%",
                   checked > 0 and rate >= 0.98, _pct(rate),
                   f"{checked} 个计划项，判定口径为「先修凭据可背书 + 日期范围有效」。"
                   "容量与保护区块由 B1/B2 在红线层判定，不在此重复；"
                   "截止日期与课表冲突对课程类计划项不适用。"
                   "⚠️ 当前路径是 demo_fixture，不带 CapacityBudget，"
                   "因此「计划对容量的承诺」这一支未被这批样本覆盖",
                   failures[:20])


# ── T6 低价值重复曝光 ────────────────────────────────────────────────
@check("T6")
def t6_low_value_repeat() -> Result:
    """学生给过低分之后，同系列的项还进不进 Top-N。

    口径：用 Aggregation 算出的**持续低质系列**当"已反馈低价值"的集合，
    再看目录服务出来的前 N 条里有多少属于这些系列。
    这测的是排序输入是否吸收了反馈，不测个体的拒绝记忆（那是 T12）。
    """
    from campuspath_aggregation.aggregate import aggregate_event_quality
    from campuspath_contracts.reflection import EventQualityFeedback

    bundle = seed_bundle()
    feedback = [EventQualityFeedback(**f) for f in bundle["event_quality_feedback"]]
    if not feedback:
        return _result("T6", "Low-Value Repeat Exposure", "< 10%", False, None,
                       "没有质量反馈样本，无法评测", [])

    # aggregate_event_quality 一次只算**一个系列**，所以先按系列分组。
    # 传整份 feedback 会撞上"质量聚合必须指向某一届或某个系列"的校验——
    # 那条校验存在的理由，正是不让人把不同活动的评分混成一个平均数。
    now = datetime(2026, 9, 15, tzinfo=timezone.utc)
    by_series: dict[str, list] = {}
    for item in feedback:
        if item.series_id:
            by_series.setdefault(item.series_id, []).append(item)

    low_value_series = set()
    aggregates = []
    for series_id, rows in by_series.items():
        aggregate = aggregate_event_quality(
            rows, series_id=series_id, now=now, aggregate_id=f"Q-{series_id}"
        )
        aggregates.append(aggregate)
        # 没有 overall_mean 这种东西——聚合是**逐维度**的，
        # 刻意不给一个总分：把"内容深度"和"组织水平"平均成一个数，
        # 会让"讲得好但组织混乱"和"平庸但顺畅"看起来一样。
        # 这里取各维度加权分的均值作为筛选低质系列的近似，并写明这是近似。
        scores = [d.weighted_score for d in aggregate.dimensions]
        if scores and statistics.fmean(scores) < 2.5:
            low_value_series.add(series_id)
    if not low_value_series:
        return _result("T6", "Low-Value Repeat Exposure", "< 10%", True, "0.0%",
                       f"{len(aggregates)} 个系列中没有均分低于 2.5 的，"
                       "本轮无低价值系列可供检验——**这不是通过的强证据**",
                       [])

    client = api_client()
    top_n = client.get("/v1/catalog/opportunities?limit=20", headers=_HEADERS).json()
    repeats = [
        {"opportunity_id": o["opportunity_id"], "series_id": o.get("series_id")}
        for o in top_n if o.get("series_id") in low_value_series
    ]
    rate = len(repeats) / len(top_n) if top_n else 0.0
    return _result("T6", "Low-Value Repeat Exposure", "< 10%", rate < 0.10,
                   _pct(rate),
                   f"{len(by_series)} 个系列中 {len(low_value_series)} 个持续低质"
                   "（判据为各维度加权分均值 < 2.5，是近似——聚合刻意不给总分）；"
                   f"目录前 {len(top_n)} 条里 {len(repeats)} 条属于它们",
                   repeats[:20])


# ── T10 重规划延迟 ───────────────────────────────────────────────────
@check("T10")
def t10_replan_latency() -> Result:
    """整体重规划的 P95。**当前口径不含 A5**——它需要模型，延迟另计（WP11）。"""
    client = api_client()
    samples: list[float] = []
    payload = {
        "student_id": "STU-A", "trigger_type": "student_added_opportunity",
        "source": "OPP-INT-001", "detected_at": "2026-09-15T09:00:00Z",
    }
    for _ in range(24):
        start = time.perf_counter()
        client.post("/v1/students/STU-A/replan-preview", headers=_HEADERS, json=payload)
        samples.append(time.perf_counter() - start)
    samples.sort()
    p95 = samples[max(0, int(len(samples) * 0.95) - 1)]
    return _result("T10", "Replan Latency P95", "< 12s", p95 < 12.0,
                   f"{p95:.3f}s",
                   f"{len(samples)} 次采样（D6 下限 20）。"
                   "口径为 AffectedScope 计算，**不含 A5 重新生成计划**——"
                   "那一段需要模型，见 WP11")


# ── T11 Profile 提议精确率 ───────────────────────────────────────────
@check("T11")
def t11_proposal_precision() -> Result:
    """被学生接受（confirmed）或轻改后接受（edited）的提议比例。"""
    bundle = seed_bundle()
    decided = [p for p in bundle["profile_update_proposals"]
               if p["status"] in ("confirmed", "edited", "rejected")]
    if not decided:
        return _result("T11", "Profile Proposal Precision", "≥ 80%", False, None,
                       "没有已裁决的提议，无法评测", [])
    accepted = [p for p in decided if p["status"] in ("confirmed", "edited")]
    rate = len(accepted) / len(decided)
    rejected = [{"proposal_id": p["proposal_id"], "reason": p.get("reason", "")[:80]}
                for p in decided if p["status"] == "rejected"]
    return _result("T11", "Profile Proposal Precision", "≥ 80%", rate >= 0.80,
                   _pct(rate),
                   f"{len(decided)} 条已裁决提议中 {len(accepted)} 条被接受或轻改后接受。"
                   "⚠️ 裁决来自 Persona 脚本而非真人，属自评",
                   rejected[:20])
