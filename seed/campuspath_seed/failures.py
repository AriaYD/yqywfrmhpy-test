"""失败样本：Spec §11.3 的十六类，**全部覆盖**（D4 只要求 ≥12）。

每一类都由 Seed 里真实存在的数据支撑，不是"文档里写着我们支持"。
每条给出：注入了什么、期望系统怎么做、以及**期望它不要做什么**——
后者才是真正能证伪的部分。评测（WP10）按 ``case_id`` 逐条跑。
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta

from campuspath_contracts.opportunity import Opportunity, PublicationStatus

from .config import SEED_TODAY
from .personas import PersonaBundle


@dataclasses.dataclass
class FailureCase:
    case_id: str
    kind: str
    description: str
    injected: dict[str, str]
    expected_behaviour: str
    must_not: str
    gold_label: str


#: Spec §11.3 的十六类。顺序即原文顺序，便于逐条核对。
FAILURE_KINDS: tuple[str, ...] = (
    "expired_but_online",
    "year_gated_future_eligible",
    "ambiguous_year_requirement",
    "conflicting_deadlines_across_sources",
    "duplicate_different_title",
    "well_marketed_poor_feedback",
    "good_event_too_basic_for_student",
    "conflicts_with_course_or_rest",
    "missing_workload_field",
    "already_done_similar",
    "career_ok_but_degree_credits_short",
    "prereq_unmet_or_not_offered_or_full_or_clash",
    "calendar_gap_is_protected_time",
    "resume_extraction_or_expired_cert_or_rejected_write",
    "publisher_scope_violation",
    "published_updated_without_rereview_or_cancelled_still_shown",
)


def build_failure_cases(
    opportunities: list[Opportunity],
    personas: list[PersonaBundle],
    *,
    low_quality_series: list[str],
) -> tuple[list[FailureCase], list[Opportunity]]:
    """返回失败样本清单，以及**为这些样本额外注入的机会条目**。

    额外条目单独返回而不是就地改原表，是为了让"这条数据是为失败样本造的"
    在数据集里一眼可见。
    """
    by_id = {o.opportunity_id: o for o in opportunities}
    extra: list[Opportunity] = []
    cases: list[FailureCase] = []

    expired = next(
        (o for o in opportunities
         if o.deadline is not None and o.deadline.date() < SEED_TODAY), None
    )
    base = opportunities[0]

    # 1 已过期但页面仍在线
    cases.append(FailureCase(
        case_id="FAIL-01",
        kind="expired_but_online",
        description="截止日期已过，但官方页面仍可访问且未标注失效",
        injected={"opportunity_id": expired.opportunity_id if expired else base.opportunity_id,
                  "deadline": str(expired.deadline.date()) if expired else "n/a"},
        expected_behaviour="判为 ineligible_current_cycle 并显示「本轮已截止」；广场标记过期",
        must_not="不得因为页面可访问就当作仍可申请",
        gold_label="ineligible_current_cycle",
    ))

    # 2 大一不合格、大三可达
    year_gated = next(
        (o for o in opportunities
         if any("Year 3" in r.expression for r in o.eligibility_rules)), base
    )
    cases.append(FailureCase(
        case_id="FAIL-02",
        kind="year_gated_future_eligible",
        description="仅限大三及以上的实习，学生当前大二",
        injected={"opportunity_id": year_gated.opportunity_id, "student_id": "STU-A"},
        expected_behaviour="判为 future_eligible，给出预计可申请日期与桥接行动",
        must_not="不得从候选池中永久删除（Spec §16.1）",
        gold_label="future_eligible",
    ))

    # 3 年级要求含糊
    ambiguous = next(
        (o for o in opportunities
         if any("Penultimate" in r.expression for r in o.eligibility_rules)), base
    )
    cases.append(FailureCase(
        case_id="FAIL-03",
        kind="ambiguous_year_requirement",
        description="来源写「Penultimate-year students preferred」，未说明是否硬性",
        injected={"opportunity_id": ambiguous.opportunity_id},
        expected_behaviour="判为 needs_confirmation 并提示向来源核实",
        must_not="不得按统一年级假设直接淘汰",
        gold_label="needs_confirmation",
    ))

    # 4 两个来源截止日期冲突
    conflict_source = base.model_copy(update={
        "opportunity_id": "OPP-FAIL-04",
        "title": base.title + "（来源 B 版本）",
        "source_id": "SRC-partner-ats",
        "deadline": (base.deadline + timedelta(days=10)) if base.deadline else None,
    })
    extra.append(conflict_source)
    cases.append(FailureCase(
        case_id="FAIL-04",
        kind="conflicting_deadlines_across_sources",
        description="同一机会在两个来源上的截止日期相差 10 天",
        injected={"opportunity_ids": f"{base.opportunity_id},OPP-FAIL-04"},
        expected_behaviour="标记来源冲突，以官方来源原文为准并显示两个日期",
        must_not="不得静默取其中一个日期",
        gold_label="needs_confirmation",
    ))

    # 5 标题不同、内容重复
    duplicate = base.model_copy(update={
        "opportunity_id": "OPP-FAIL-05",
        "title": "【招募】" + base.title.replace("实习生", "实习机会"),
    })
    extra.append(duplicate)
    cases.append(FailureCase(
        case_id="FAIL-05",
        kind="duplicate_different_title",
        description="标题改写后重复投放，实为同一机会",
        injected={"opportunity_ids": f"{base.opportunity_id},OPP-FAIL-05"},
        expected_behaviour="去重合并并保留两条来源记录",
        must_not="不得作为两条独立机会同时进入 Top-N",
        gold_label="duplicate",
    ))

    # 6 宣传好、反馈持续差
    cases.append(FailureCase(
        case_id="FAIL-06",
        kind="well_marketed_poor_feedback",
        description="宣传充分但连续两届验证反馈都低于基线",
        injected={"series_ids": ",".join(low_quality_series)},
        expected_behaviour="质量置信度下调并触发替换；校方端看到匿名质量趋势",
        must_not="不得把低质量归因到某个学生，也不得输出个体反馈原文",
        gold_label="low_quality_series",
    ))

    # 7 活动本身优质但对该学生过于基础
    cases.append(FailureCase(
        case_id="FAIL-07",
        kind="good_event_too_basic_for_student",
        description="入门工作坊质量良好，但学生已有对应技能",
        injected={"opportunity_id": "OPP-EVT-001", "student_id": "STU-B"},
        expected_behaviour="按个人适配降权并说明原因（fit_tags=too_basic_for_me）",
        must_not="不得据此下调该活动的全局质量分（§17.4 个人 vs 全局分离）",
        gold_label="personal_mismatch_not_global_low_quality",
    ))

    # 8 与课程或休息边界冲突
    cases.append(FailureCase(
        case_id="FAIL-08",
        kind="conflicts_with_course_or_rest",
        description="活动时间与已选课程或学生设定的保护区块重叠",
        injected={"student_id": "STU-B", "week": "2026-09-14"},
        expected_behaviour="排程预览显示 blocking 冲突并给出替代时段",
        must_not="不得静默排进保护区块（B2）",
        gold_label="protected_block_conflict",
    ))

    # 9 工作量字段缺失
    missing_workload = next(
        (o for o in opportunities if o.workload_hours_total is None), base
    )
    cases.append(FailureCase(
        case_id="FAIL-09",
        kind="missing_workload_field",
        description="来源未提供工作量，容量校验缺输入",
        injected={"opportunity_id": missing_workload.opportunity_id},
        expected_behaviour="标记 uncertainty 并按保守估计提示，或请学生确认",
        must_not="不得默认按 0 小时排进计划",
        gold_label="needs_confirmation",
    ))

    # 10 已做过同类活动
    cases.append(FailureCase(
        case_id="FAIL-10",
        kind="already_done_similar",
        description="学生已完成同系列上一届活动",
        injected={"student_id": "STU-B", "series_id": "SER-简历工作坊"},
        expected_behaviour="不再推荐，或说明本届与上届的差异",
        must_not="不得换个名字重复推荐（T6）",
        gold_label="suppress_repeat",
    ))

    # 11 职业目标满足但毕业学分不足
    cases.append(FailureCase(
        case_id="FAIL-11",
        kind="career_ok_but_degree_credits_short",
        description="全选职业相关选修，导致某毕业要求组学分不足",
        injected={"student_id": "STU-A", "requirement_group": "BSC-COMP.MATH"},
        expected_behaviour="Rules 拒绝该课程组合并指出缺口所在要求组",
        must_not="毕业硬约束不得被更高的职业相关分数抵消（Spec §16.5）",
        gold_label="degree_requirement_violation",
    ))

    # 12 先修未满足 / 不开设 / 满额 / 与必修冲突
    cases.append(FailureCase(
        case_id="FAIL-12",
        kind="prereq_unmet_or_not_offered_or_full_or_clash",
        description="候选课程分别命中先修未满足、该学期不开设、名额已满、与必修时段冲突",
        injected={"student_id": "STU-A", "source": "gold_set:course_constraints"},
        expected_behaviour="四种情形分别给出不同的判定与替代课",
        must_not="不得把四种情形统一显示为「不可选」",
        gold_label="see_course_constraint_gold_set",
    ))

    # 13 日历看似有空档，实为保护时间
    cases.append(FailureCase(
        case_id="FAIL-13",
        kind="calendar_gap_is_protected_time",
        description="日历上的空白落在学生设定的睡眠或恢复窗口内",
        injected={"student_id": "STU-B", "block_tag": "sleep"},
        expected_behaviour="该时段不计入 Usable Free Time；排程绕开",
        must_not="不得把睡眠、用餐、通勤当成可压缩空档（Spec §16.8）",
        gold_label="protected_not_free",
    ))

    # 14 Resume 提取错误 / 证书过期 / 学生拒绝写入
    cases.append(FailureCase(
        case_id="FAIL-14",
        kind="resume_extraction_or_expired_cert_or_rejected_write",
        description="Resume 提取出一条学生并不认可的经历；另有一张证书已过期",
        injected={"student_id": "STU-B", "evidence_id": "EV-B-3",
                  "proposal_id": "PROP-B-REJECTED"},
        expected_behaviour="提案保持 pending；被拒绝后保留事件但不写入 Profile；过期证书标记 expired",
        must_not="不得静默写入 Canonical Profile（B3）",
        gold_label="rejected_proposal_not_written",
    ))

    # 15 越权投稿
    cases.append(FailureCase(
        case_id="FAIL-15",
        kind="publisher_scope_violation",
        description="社团代表其他组织投稿、超出授权分类、授权已过期、无直发权仍尝试直发",
        injected={"violation_ids": "VIO-001,VIO-002,VIO-003,VIO-004"},
        expected_behaviour="全部被拦截并写入审计记录",
        must_not="不得只拦截不记录（B7 的判定包含可追溯）",
        gold_label="all_blocked_and_audited",
    ))

    # 16 已发布内容更新未复审 / 活动取消仍在广场
    cases.append(FailureCase(
        case_id="FAIL-16",
        kind="published_updated_without_rereview_or_cancelled_still_shown",
        description="已发布机会修改了截止日期却未重新审核；另有一条已取消但仍在广场",
        injected={"submission_id": "SUB-009", "opportunity_id": "OPP-FAIL-16"},
        expected_behaviour="修改触发字段后状态回到 in_review；取消的条目从广场下架",
        must_not="不得让 updated 状态直接回到 published 而跳过复审",
        gold_label="requires_rereview",
    ))

    cancelled = base.model_copy(update={
        "opportunity_id": "OPP-FAIL-16",
        "title": base.title + "（已取消）",
        "publication_status": PublicationStatus.WITHDRAWN,
    })
    extra.append(cancelled)

    covered = {c.kind for c in cases}
    missing = [k for k in FAILURE_KINDS if k not in covered]
    if missing:
        raise AssertionError(f"失败样本未覆盖以下类别：{missing}")

    return cases, extra
