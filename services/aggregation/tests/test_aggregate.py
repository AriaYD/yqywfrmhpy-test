"""Aggregation Service：B9 小样本抑制、B10 去标识、时间衰减。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from campuspath_contracts.aggregation import MAX_COHORT_DIMENSIONS, MIN_CELL_N, MetricTuple
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.reflection import (
    CohortDims,
    DimensionRating,
    EventQualityFeedback,
    QualityDimension,
)

from campuspath_aggregation.aggregate import (
    TooManyDimensions,
    aggregate_all_cells,
    aggregate_event_quality,
    aggregate_resource_coverage,
    build_exposure_gap_ranking,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
COHORT = CohortDims(school="ENGG", year_level=2, development_mode="employment")


def metric(**kw) -> MetricTuple:
    base = dict(
        period="2026-27_FALL", cohort_dims=COHORT,
        eligible_count=40, seen_count=20, acted_count=5,
        gap_total=10, gap_covered=7,
        uncovered_requirement_categories=(RequirementCategory.RESEARCH_EXPERIENCE,),
    )
    base.update(kw)
    return MetricTuple(**base)


def feedback(index: int, rating: int, days_ago: int = 0, **kw) -> EventQualityFeedback:
    base = dict(
        feedback_id=f"EQF-{index}", occurrence_id="OCC-1", series_id="SER-1",
        verified_attendance=True, verification_ref=f"ver_{index:016x}",
        dimensions=tuple(DimensionRating(dimension=d, rating=rating) for d in QualityDimension),
        fit_tags=(), cohort_dims=COHORT,
        submitted_at=NOW - timedelta(days=days_ago),
    )
    base.update(kw)
    return EventQualityFeedback(**base)


# ── B9 ────────────────────────────────────────────────────────────────


def test_small_cell_suppresses_every_rate():
    result = aggregate_resource_coverage(
        [metric() for _ in range(MIN_CELL_N - 1)],
        period="2026-27_FALL", scope="school", computed_at=NOW,
    )
    assert result.discovery_rate is None
    assert result.action_rate is None
    assert result.gap_coverage_rate is None
    assert result.suppressed_cells


def test_sufficient_cell_reports_rates():
    result = aggregate_resource_coverage(
        [metric() for _ in range(MIN_CELL_N)],
        period="2026-27_FALL", scope="school", computed_at=NOW,
    )
    assert result.discovery_rate == pytest.approx(0.5)
    assert result.action_rate == pytest.approx(0.25)
    assert result.gap_coverage_rate == pytest.approx(0.7)


def test_too_many_dimensions_is_refused_not_suppressed():
    """抑制会让人以为"再筛细一点就有了"；拒绝才是正确信号。"""
    with pytest.raises(TooManyDimensions):
        aggregate_resource_coverage(
            [metric() for _ in range(20)], period="2026-27_FALL", scope="school",
            cohort_dimensions=("school", "year_level", "development_mode"),
            cohort_values=("ENGG", 2, "employment"),
            computed_at=NOW,
        )
    assert MAX_COHORT_DIMENSIONS == 2


# ── 以下来自 2026-07-29 的独立审查：分组维度收下就丢掉，抑制被架空 ──


def _mixed_population():
    """100 个 ENGG/Y2 什么都看得到；2 个 BUS/Y4 什么都看不到。"""
    def one(school, year, seen):
        return MetricTuple(
            period="2026-27_FALL",
            cohort_dims=CohortDims(school=school, year_level=year,
                                   development_mode="employment"),
            eligible_count=10, seen_count=seen, acted_count=0,
            gap_total=5, gap_covered=3,
        )
    return [one("ENGG", 2, 10) for _ in range(100)] + [one("BUS", 4, 0) for _ in range(2)]


def test_cohort_dimensions_actually_filter():
    """曾经只按 period 过滤：2 人的格子拿到全校 102 人的分母，
    既冒充了该群体的数字，又让 MIN_CELL_N 抑制永远不触发。"""
    result = aggregate_resource_coverage(
        _mixed_population(), period="2026-27_FALL", scope="school",
        cohort_dimensions=("school", "year_level"), cohort_values=("BUS", 4),
        computed_at=NOW,
    )
    assert result.cell_n == 2, "分组维度没有生效"
    assert result.discovery_rate is None, "2 人的格子不得输出数值"
    assert result.suppressed_cells


def test_each_cell_is_suppressed_on_its_own_sample():
    cells = {c.aggregate_id: c for c in aggregate_all_cells(
        _mixed_population(), period="2026-27_FALL", scope="school",
        cohort_dimensions=("school", "year_level"), computed_at=NOW,
    )}
    assert cells["AGG-BUS-4"].cell_n == 2
    assert cells["AGG-BUS-4"].discovery_rate is None
    assert cells["AGG-ENGG-2"].cell_n == 100
    assert cells["AGG-ENGG-2"].discovery_rate == pytest.approx(1.0)


def test_dimension_names_cannot_be_concatenated_to_dodge_the_limit():
    """把五个维度拼成一个字符串，层数检查看起来就是 1 层。"""
    with pytest.raises(TooManyDimensions):
        aggregate_resource_coverage(
            _mixed_population(), period="2026-27_FALL", scope="school",
            cohort_dimensions=("school+year_level+development_mode",),
            cohort_values=("x",), computed_at=NOW,
        )


def test_duplicate_dimensions_are_refused():
    with pytest.raises(TooManyDimensions):
        aggregate_resource_coverage(
            _mixed_population(), period="2026-27_FALL", scope="school",
            cohort_dimensions=("school", "school"), cohort_values=("ENGG", "ENGG"),
            computed_at=NOW,
        )


def test_dimensions_without_values_is_refused():
    """给了维度却不指明是哪一格，算出来的是全体数字却会被贴上分组标签。"""
    with pytest.raises(ValueError):
        aggregate_resource_coverage(
            _mixed_population(), period="2026-27_FALL", scope="school",
            cohort_dimensions=("school",), computed_at=NOW,
        )


def test_rare_uncovered_category_is_suppressed_from_the_ranking():
    """只有一两个人缺的类别，进榜就等于指向那一两个人。"""
    tuples = [metric() for _ in range(MIN_CELL_N)]
    tuples.append(metric(uncovered_requirement_categories=(RequirementCategory.LANGUAGE,)))
    result = aggregate_resource_coverage(
        tuples, period="2026-27_FALL", scope="school", computed_at=NOW
    )
    ranked = {e.category for e in result.unmet_requirement_ranking}
    assert RequirementCategory.RESEARCH_EXPERIENCE in ranked
    assert RequirementCategory.LANGUAGE not in ranked
    assert any("language" in c.cell_key for c in result.suppressed_cells)


def test_other_periods_are_not_mixed_in():
    tuples = [metric() for _ in range(MIN_CELL_N)] + [
        metric(period="2025-26_FALL") for _ in range(20)
    ]
    result = aggregate_resource_coverage(
        tuples, period="2026-27_FALL", scope="school", computed_at=NOW
    )
    assert result.cell_n == MIN_CELL_N


def test_no_function_takes_a_student_id():
    """§17.1.2 边界 2：后端不提供从聚合下钻到个体的查询。"""
    import inspect

    from campuspath_aggregation import aggregate as module

    for name, obj in vars(module).items():
        if inspect.isfunction(obj) and not name.startswith("_"):
            assert "student_id" not in inspect.signature(obj).parameters, name


# ── 曝光断层榜 ────────────────────────────────────────────────────────


def test_exposure_ranking_puts_the_worst_first():
    ranking = build_exposure_gap_ranking(
        {"OPP-A": (40, 4), "OPP-B": (30, 24), "OPP-C": (20, 1)}
    )
    assert [e.opportunity_id for e in ranking] == ["OPP-C", "OPP-A", "OPP-B"]


def test_exposure_ranking_drops_small_cells():
    ranking = build_exposure_gap_ranking({"OPP-A": (MIN_CELL_N - 1, 0)})
    assert ranking == ()


# ── 质量聚合 ──────────────────────────────────────────────────────────


def test_quality_below_threshold_reports_no_scores():
    result = aggregate_event_quality(
        [feedback(i, 5) for i in range(MIN_CELL_N - 1)], occurrence_id="OCC-1", now=NOW
    )
    assert result.dimensions == ()
    assert result.verified_n == MIN_CELL_N - 1


def test_quality_above_threshold_reports_scores_with_intervals():
    result = aggregate_event_quality(
        [feedback(i, 4) for i in range(MIN_CELL_N + 3)], occurrence_id="OCC-1", now=NOW
    )
    assert len(result.dimensions) == len(QualityDimension)
    for dimension in result.dimensions:
        assert dimension.ci_low <= dimension.weighted_score <= dimension.ci_high


def test_unverified_feedback_does_not_count():
    items = [feedback(i, 5) for i in range(MIN_CELL_N + 5)]
    items = [
        f.model_copy(update={"verified_attendance": False, "verification_ref": None})
        for f in items
    ]
    result = aggregate_event_quality(items, occurrence_id="OCC-1", now=NOW)
    assert result.verified_n == 0


def test_old_feedback_weighs_less():
    """活动会改进，三年前的评价不该和上个月的一样重。"""
    recent = [feedback(i, 5, days_ago=1) for i in range(MIN_CELL_N)]
    old = [feedback(100 + i, 1, days_ago=365 * 3) for i in range(MIN_CELL_N)]
    result = aggregate_event_quality(recent + old, occurrence_id="OCC-1", now=NOW)
    score = result.dimensions[0].weighted_score
    assert score > 3.0, f"时间衰减未生效，加权分 {score}"


def test_series_level_aggregation_spans_occurrences():
    items = [feedback(i, 4) for i in range(MIN_CELL_N)] + [
        feedback(100 + i, 4, occurrence_id="OCC-2") for i in range(MIN_CELL_N)
    ]
    result = aggregate_event_quality(items, series_id="SER-1", now=NOW)
    assert result.verified_n == MIN_CELL_N * 2
