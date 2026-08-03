"""审计黄-8 + B 缺口（2026-08-02）：反思闭环真正回流推荐。

用户初衷原话：「让用户写活动的反思总结和评分，就是为了让系统更懂用户
喜好、还有活动的质量——质量不好的以后少推荐」。此前第六维「活动质量」
只用了来源新鲜度，聚合质量分与个人 fit 偏好都没接线。本文件钉住：

* 全体维度：同一活动的匿名四维均分（样本 ≥3 才生效，与聚合抑制阈值同
  口径）拉高/拉低第六维——质量差的活动分数真的会降；
* 个人维度：学生自己反思里的 fit_tag（很匹配 / 太难 / 形式不适合…）
  按类别词修正个人偏好维——标过「不适合」的同类活动会被压后。
"""

from __future__ import annotations

from datetime import date

from campuspath_contracts.opportunity import EligibilityStateName
from campuspath_api.matching import (
    personal_fit_modifier,
    score_breakdown,
)


class _Opp:
    def __init__(self, *, skills=(), categories=("workshop",)):
        from datetime import datetime, timezone
        self.skills = tuple(skills)
        self.category_tags = tuple(categories)
        self.requirement_categories = ()
        self.workload_hours_total = 2.0
        # 90 天前核验 → freshness=0.5：让质量分的拉高/拉低两个方向都可观测
        self.last_verified_at = datetime(2026, 6, 17, tzinfo=timezone.utc)
        self.provenance = type("P", (), {"evidence_snippet": None})()


TODAY = date(2026, 9, 15)


def _score(opp, **kw):
    return score_breakdown(
        opp, interest_tags=frozenset(), open_requirement_categories=frozenset(),
        weekly_capacity_hours=20.0, today=TODAY, **kw)


def test_quality_score_moves_the_sixth_dimension():
    base = _score(_Opp())
    good = _score(_Opp(), quality_score=0.95)
    bad = _score(_Opp(), quality_score=0.20)
    assert good.event_quality_source_trust > base.event_quality_source_trust
    assert bad.event_quality_source_trust < base.event_quality_source_trust


def test_personal_fit_modifier_covers_every_real_fit_tag():
    """审查 H1：词表必须来自 FitTag 枚举本体——此前手写词表与真实取值
    完全不交集，功能死代码而测试还绿。这里遍历**枚举全集**，每个取值
    都必须产生非零修正（GOOD_FIT 为正、其余为负）。"""
    from campuspath_contracts.reflection import FitTag

    class _Refl:
        def __init__(self, subject_id, fit_tag):
            self.subject_id = subject_id
            self.fit_tag = fit_tag

    categories_of = {"OPP-X": ("workshop",)}
    for tag in FitTag:
        mod = personal_fit_modifier(
            ("workshop",), [_Refl("OPP-X", tag.value)], categories_of)
        if tag is FitTag.GOOD_FIT:
            assert mod > 0, tag
        else:
            assert mod < 0, f"{tag} 应为负修正，得到 {mod}"


def test_negative_fit_penalises_even_with_zero_interest_overlap():
    """审查 M12：个人负修正作用在加权和层——兴趣重叠为 0（恰是"标过
    不适合"的常见情形）时也必须真的压分，不许被维度层 clamp 吃掉。"""
    from campuspath_api.matching import weighted_score

    opp = _Opp(categories=("workshop",))
    breakdown = _score(opp)          # interest_tags 为空 → preference=0
    assert breakdown.personal_preference_fit == 0.0
    base = weighted_score(breakdown, EligibilityStateName.ELIGIBLE_NOW)
    penalised = weighted_score(
        breakdown, EligibilityStateName.ELIGIBLE_NOW, personal_fit=-0.3)
    boosted = weighted_score(
        breakdown, EligibilityStateName.ELIGIBLE_NOW, personal_fit=0.3)
    assert penalised < base < boosted


def test_quality_trust_is_coarsened_to_one_decimal():
    """审查 H2：质量分掺入第六维后粗化到 0.1 档——防止从
    quality_confidence + freshness_days 联立还原小样本均分。"""
    got = _score(_Opp(), quality_score=0.6337).event_quality_source_trust
    assert got == round(got, 1), got
