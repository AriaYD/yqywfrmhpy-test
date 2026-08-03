"""B9 Metric Re-identification / B10 MetricTuple Field Leakage 的行为层断言。

字段层的断言在 ``test_boundary_guards.py``；这里测的是**数值抑制**：
样本量不足时不能显示看似精确的数字，分组维度不能无限叠加。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from campuspath_contracts.aggregation import (
    MAX_COHORT_DIMENSIONS,
    MIN_CELL_N,
    DimensionAggregate,
    EventQualityAggregate,
    ExposureGapEntry,
    MetricTuple,
    ResourceCoverageAggregate,
    UnmetRequirementEntry,
)
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.reflection import CohortDims, QualityDimension

from conftest import NOW

COHORT = CohortDims(school="ENGG", year_level=2, development_mode="employment")


def _tuple(**kw) -> MetricTuple:
    base = dict(
        period="2025-26_FALL",
        cohort_dims=COHORT,
        eligible_count=40,
        seen_count=22,
        acted_count=6,
        gap_total=12,
        gap_covered=9,
        uncovered_requirement_categories=(RequirementCategory.RESEARCH_EXPERIENCE,),
    )
    base.update(kw)
    return MetricTuple(**base)


def _aggregate(**kw) -> ResourceCoverageAggregate:
    base = dict(
        aggregate_id="AGG-1",
        period="2025-26_FALL",
        scope="school",
        cohort_dims_used=("school",),
        cell_n=MIN_CELL_N,
        discovery_rate=0.55,
        action_rate=0.27,
        gap_coverage_rate=0.75,
        computed_at=NOW,
    )
    base.update(kw)
    return ResourceCoverageAggregate(**base)


def test_valid_metric_tuple():
    assert _tuple().acted_count == 6


@pytest.mark.parametrize(
    "kw",
    [
        {"seen_count": 41},                      # 看到的比合格的还多
        {"acted_count": 23},                     # 行动的比看到的还多
        {"gap_covered": 13},                     # 覆盖的比总数还多
    ],
)
def test_metric_tuple_counts_must_nest(kw):
    with pytest.raises(ValidationError):
        _tuple(**kw)


def test_metric_tuple_rejects_student_id():
    """已知会失败的样例：有人"顺手"把 student_id 塞进出域元组。"""
    payload = _tuple().model_dump()
    payload["student_id"] = "S-001"
    with pytest.raises(ValidationError) as excinfo:
        MetricTuple(**payload)
    assert "student_id" in str(excinfo.value)


def test_metric_tuple_rejects_free_text_gap_description():
    payload = _tuple().model_dump()
    payload["uncovered_gap_descriptions"] = ["想进 Google 做 UX 但没有用户研究经历"]
    with pytest.raises(ValidationError):
        MetricTuple(**payload)


# --------------------------------------------------------------------------
# B9：小样本抑制
# --------------------------------------------------------------------------


def test_cell_below_threshold_must_suppress_values():
    """已知会失败的样例：只有 4 个人的格子，却显示了 0.55 这样的精确比率。"""
    with pytest.raises(ValidationError) as excinfo:
        _aggregate(cell_n=MIN_CELL_N - 1)
    assert "Insufficient evidence" in str(excinfo.value)


def test_cell_below_threshold_with_suppressed_values_is_fine():
    agg = _aggregate(
        cell_n=MIN_CELL_N - 1,
        discovery_rate=None,
        action_rate=None,
        gap_coverage_rate=None,
    )
    assert agg.discovery_rate is None


def test_cell_below_threshold_cannot_carry_rankings():
    with pytest.raises(ValidationError):
        _aggregate(
            cell_n=MIN_CELL_N - 1,
            discovery_rate=None,
            action_rate=None,
            gap_coverage_rate=None,
            exposure_gap_ranking=(
                ExposureGapEntry(
                    opportunity_id="OPP-1", eligible_n=MIN_CELL_N, seen_n=1, exposure_rate=0.2
                ),
            ),
        )


def test_too_many_cohort_dimensions_is_rejected():
    """禁止细粒度交叉：多重筛选能把单元格缩到可识别规模。"""
    with pytest.raises(ValidationError) as excinfo:
        _aggregate(cohort_dims_used=("school", "year_level", "development_mode"))
    assert str(MAX_COHORT_DIMENSIONS) in str(excinfo.value)


def test_ranking_entries_themselves_respect_the_threshold():
    """榜单每一行也是一个单元格，同样受阈值约束。"""
    with pytest.raises(ValidationError):
        ExposureGapEntry(
            opportunity_id="OPP-1", eligible_n=MIN_CELL_N - 1, seen_n=0, exposure_rate=0.0
        )
    with pytest.raises(ValidationError):
        UnmetRequirementEntry(
            category=RequirementCategory.RESEARCH_EXPERIENCE, occurrences=MIN_CELL_N - 1
        )


# --------------------------------------------------------------------------
# 活动质量聚合
# --------------------------------------------------------------------------


def test_quality_aggregate_below_threshold_cannot_publish_scores():
    with pytest.raises(ValidationError):
        EventQualityAggregate(
            aggregate_id="Q-1",
            occurrence_id="OCC-1",
            verified_n=MIN_CELL_N - 1,
            dimensions=(
                DimensionAggregate(
                    dimension=QualityDimension.CONTENT_DEPTH,
                    weighted_score=4.2,
                    ci_low=3.9,
                    ci_high=4.5,
                ),
            ),
            last_updated=NOW,
        )


def test_quality_aggregate_needs_a_target():
    with pytest.raises(ValidationError):
        EventQualityAggregate(aggregate_id="Q-2", verified_n=10, last_updated=NOW)


def test_confidence_interval_must_contain_the_estimate():
    with pytest.raises(ValidationError):
        DimensionAggregate(
            dimension=QualityDimension.ORGANIZATION,
            weighted_score=4.8,
            ci_low=3.0,
            ci_high=4.5,
        )
