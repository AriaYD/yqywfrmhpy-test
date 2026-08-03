"""A5 的机会匹配（Spec §8.1 A5 行、§17.4）。

**分工严格照架构第 1 条走：**

* **资格**由 Rules Engine 判定，四态，带真实签发的 ``validation_id``。
  模型碰不到这一步——它连"这条能不能报"都不参与，更别说改判。
* **取舍**由 A5 做，而且只做这一件事：在**已经合规**的候选之间给出
  相对优先级与理由。它拿到的输入是结构化的事实摘要，不是原始文本。

拆开的理由是：模型对"该不该排在前面"可以有观点，对"你有没有资格"不能有。
两者混在一个调用里，前者的措辞就会污染后者的结论。

分数本身是**确定性的加权和**——六个维度各自可单测。模型只产出理由文案。
把打分也交给模型，同一个学生刷新两次会看到不同排序，而 D6.7 要求
固定 Seed 两次数字一致。
"""

from __future__ import annotations

from datetime import date, datetime

from campuspath_contracts.common import LocalizedText, Uncertainty
from campuspath_contracts.opportunity import (
    EligibilityStateName,
    MatchResult,
    MatchScoreBreakdown,
    Opportunity,
)

#: 六个维度的权重（Spec §17.4）。和为 1，改这里等于改产品主张，要过评审。
_WEIGHTS = {
    "goal_alignment": 0.30,
    "gap_reduction_value": 0.25,
    "evidence_portfolio_value": 0.15,
    "workload_energy_fit": 0.15,
    "personal_preference_fit": 0.10,
    "event_quality_source_trust": 0.05,
}

#: 资格状态对排序的影响。**不是过滤**——四态里只有一个真正排除，
#: 其余都还留在列表里，让学生自己看见"现在不行但将来行"。
_STATE_FACTOR = {
    EligibilityStateName.ELIGIBLE_NOW: 1.0,
    EligibilityStateName.NEEDS_CONFIRMATION: 0.85,
    EligibilityStateName.FUTURE_ELIGIBLE: 0.6,
    EligibilityStateName.INELIGIBLE_CURRENT_CYCLE: 0.25,
}


def _overlap(left: tuple[str, ...], right: frozenset[str]) -> float:
    if not left:
        return 0.0
    return len([x for x in left if x in right]) / len(left)


#: 个人 fit 修正的步长与上限（审计黄-8/B 缺口，2026-08-02）：
#: 学生自己反思里标过「不匹配」的类别 → 同类机会每命中一个类别 −0.15，
#: 标过「很匹配」→ +0.15；封顶 ±0.30——反思能校准偏好，但不许一票否决。
_FIT_STEP, _FIT_CAP = 0.15, 0.30

#: 审查 H1：标签取值域**必须**来自契约枚举本体——此前手写词表与真实
#: FitTag 完全不交集，功能上线即死代码而测试还绿着（测试与实现共用了
#: 同一套错误假设）。GOOD_FIT 为唯一正向，其余四个为负向。
from campuspath_contracts.reflection import FitTag as _FitTag

_POSITIVE_FIT_TAGS = frozenset({_FitTag.GOOD_FIT.value})
_NEGATIVE_FIT_TAGS = frozenset(
    t.value for t in _FitTag) - _POSITIVE_FIT_TAGS


def personal_fit_modifier(
    category_tags: tuple[str, ...],
    reflections,
    categories_of: dict[str, tuple[str, ...]],
) -> float:
    """从学生**自己的**反思 fit_tag 推个人偏好修正（确定性，零模型）。

    只用学生本人的私域评分修正学生本人的推荐——不出域、不进聚合，
    与 B4（原文不出 Vault）无冲突。
    """
    modifier = 0.0
    target = set(category_tags)
    for reflection in reflections:
        tag = getattr(reflection, "fit_tag", None)
        if not tag:
            continue
        shared = target & set(categories_of.get(reflection.subject_id, ()))
        if not shared:
            continue
        if tag in _POSITIVE_FIT_TAGS:
            modifier += _FIT_STEP * len(shared)
        elif tag in _NEGATIVE_FIT_TAGS:
            modifier -= _FIT_STEP * len(shared)
    return max(-_FIT_CAP, min(_FIT_CAP, round(modifier, 4)))


def score_breakdown(
    opportunity: Opportunity,
    *,
    interest_tags: frozenset[str],
    open_requirement_categories: frozenset[str],
    weekly_capacity_hours: float,
    today: date,
    quality_score: float | None = None,
) -> MatchScoreBreakdown:
    """六维打分。纯函数，可单测到小数点——这是它不交给模型的原因。

    2026-08-02 审计修正：第六维不再只有新鲜度——有足量匿名评分
    （``quality_score``∈[0,1]，样本 ≥ 聚合抑制阈值时由调用方传入）时各占
    一半，并**粗化到 0.1 档**（审查 H2：与 freshness_days 联立可解出小样本
    均分——粗化让还原只剩档位精度）。个人 fit 修正不在这里：它作用在
    :func:`weighted_score` 的加权和层（审查 M12：clamp 在维度层会把
    「兴趣重叠为 0 但学生标过不适合」的负修正整个吃掉）。
    """
    goal_alignment = _overlap(opportunity.skills, interest_tags)
    gap_reduction = _overlap(
        tuple(c.value for c in opportunity.requirement_categories),
        open_requirement_categories,
    )
    # 有官方 URL + 有出处快照的机会，作为证据更硬。
    evidence_value = 0.5 + 0.5 * float(bool(opportunity.provenance.evidence_snippet))

    load = opportunity.workload_hours_total or 0.0
    if weekly_capacity_hours <= 0:
        workload_fit = 0.0
    elif load == 0:
        workload_fit = 0.5          # 来源没说工作量，不奖不罚
    else:
        # 占用可支配容量越多越不合适；超过一整周的容量直接归零
        workload_fit = max(0.0, 1.0 - load / (weekly_capacity_hours * 4))

    preference = _overlap(opportunity.category_tags, interest_tags)

    freshness = 1.0
    if opportunity.last_verified_at is not None:
        stale_days = (today - opportunity.last_verified_at.date()).days
        freshness = max(0.0, 1.0 - stale_days / 180)
    if quality_score is None:
        quality_trust = freshness
    else:
        blended = 0.5 * freshness + 0.5 * max(0.0, min(1.0, quality_score))
        quality_trust = round(blended, 1)      # H2：0.1 档粗化

    return MatchScoreBreakdown(
        goal_alignment=round(goal_alignment, 4),
        gap_reduction_value=round(gap_reduction, 4),
        evidence_portfolio_value=round(evidence_value, 4),
        workload_energy_fit=round(workload_fit, 4),
        personal_preference_fit=round(preference, 4),
        event_quality_source_trust=round(quality_trust, 4),
    )


def weighted_score(
    breakdown: MatchScoreBreakdown, state: EligibilityStateName,
    personal_fit: float = 0.0,
) -> float:
    """加权和 × 资格因子。``personal_fit``（审查 M12）在这里叠加：
    学生自己反思的类别修正按偏好维权重计入总分、允许把低分压得更低，
    再统一 floor 到 0——维度层展示保持"纯重叠"口径不被污染。"""
    base = sum(getattr(breakdown, name) * weight for name, weight in _WEIGHTS.items())
    base = max(0.0, base + _WEIGHTS["personal_preference_fit"] * personal_fit)
    return round(base * _STATE_FACTOR.get(state, 0.5), 4)


def workload_fit_label(
    opportunity: Opportunity, weekly_capacity_hours: float
) -> str:
    load = opportunity.workload_hours_total
    if load is None or load == 0:
        return "unknown"        # 来源没说就是不知道，不猜
    if weekly_capacity_hours <= 0:
        return "over_capacity"
    ratio = load / (weekly_capacity_hours * 4)
    if ratio <= 0.4:
        return "comfortable"
    if ratio <= 0.9:
        return "tight"
    return "over_capacity"


def build_match(
    opportunity: Opportunity,
    *,
    eligibility,
    breakdown: MatchScoreBreakdown,
    weekly_capacity_hours: float,
    covered_requirement_ids: tuple[str, ...],
    rationale: tuple[LocalizedText, ...],
    risks: tuple[LocalizedText, ...],
    today: date,
    now: datetime,
    intl_notes: tuple[LocalizedText, ...] = (),
    goal_role: str | None = None,
) -> MatchResult:
    freshness_days = None
    if opportunity.last_verified_at is not None:
        freshness_days = (today - opportunity.last_verified_at.date()).days
    return MatchResult(
        match_id=f"M-{opportunity.opportunity_id}",
        opportunity_id=opportunity.opportunity_id,
        eligibility=eligibility,
        score=weighted_score(breakdown, eligibility.state),
        breakdown=breakdown,
        gap_value=breakdown.gap_reduction_value,
        covered_requirement_ids=covered_requirement_ids,
        reasons=rationale,
        risks=risks,
        workload_fit=workload_fit_label(opportunity, weekly_capacity_hours),
        quality_confidence=breakdown.event_quality_source_trust,
        freshness_days=freshness_days,
        intl_notes=intl_notes,
        goal_role=goal_role,
        # 来源没说工作量时，这条匹配结论本身带着不确定性——
        # 让它在类型层显形，而不是被一个看起来精确的分数盖住。
        uncertainty=(
            Uncertainty.MISSING_SOURCE_FIELD
            if not opportunity.workload_hours_total
            else Uncertainty.NONE
        ),
    )
