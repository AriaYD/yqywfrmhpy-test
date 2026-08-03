"""Aggregation Service（Spec §17.1.2、§14.4）。**零 LLM。**

只接受两类输入，且两者在**类型上**都不可能携带个体：

* :class:`EventQualityFeedback` —— 无自由文本、无 student_id；
* :class:`MetricTuple` —— 去标识元组。

这里实现的是契约管不了的那部分：**聚合之后的抑制**。
一条 MetricTuple 本身没问题，五条同一格子的 MetricTuple 聚合成一个
"ENGG / Year 2 / employment 的发现率 0.55"，如果那个格子只有 3 个人，
就等于把三个人的数据披露给了校方（B9）。

因此：

1. 单元格样本量 < ``MIN_CELL_N`` → 数值置 None，并把"被抑制"这件事记下来；
2. 分组维度层数 > ``MAX_COHORT_DIMENSIONS`` → 拒绝，不是抑制；
3. **不提供任何按 student_id 查询的入口**——后端没有那个函数（§17.1.2 边界 2）。
"""

from __future__ import annotations

import dataclasses
import math
from collections import defaultdict
from datetime import datetime

from campuspath_contracts.aggregation import (
    MAX_COHORT_DIMENSIONS,
    MIN_CELL_N,
    DimensionAggregate,
    EventQualityAggregate,
    ExposureGapEntry,
    MetricTuple,
    ResourceCoverageAggregate,
    SuppressedCell,
    UnmetRequirementEntry,
)
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.reflection import EventQualityFeedback, QualityDimension

#: 时间衰减半衰期（天）。一年前的反馈权重减半——活动会改进，旧评价不该永远算数。
DEFAULT_HALF_LIFE_DAYS = 365


class TooManyDimensions(ValueError):
    """分组维度层数超限。**拒绝而不是抑制**：抑制会让人以为"再筛细一点就有了"。"""


#: 允许用于分组的维度名。写成枚举而不是任意字符串，
#: 否则把五个维度拼成一个串（"school+year+major+gpa_band"）就能让层数检查形同虚设。
ALLOWED_COHORT_DIMENSIONS = ("school", "year_level", "development_mode")


def _cell_key(tuple_: MetricTuple, dimensions: tuple[str, ...]) -> tuple:
    values = {
        "school": tuple_.cohort_dims.school,
        "year_level": tuple_.cohort_dims.year_level,
        "development_mode": tuple_.cohort_dims.development_mode,
    }
    return tuple(values[d] for d in dimensions)


def _validate_dimensions(dimensions: tuple[str, ...]) -> None:
    unknown = [d for d in dimensions if d not in ALLOWED_COHORT_DIMENSIONS]
    if unknown:
        raise TooManyDimensions(
            f"未知的分组维度 {unknown}；只允许 {list(ALLOWED_COHORT_DIMENSIONS)}。"
            "把多个维度拼成一个字符串不会绕过层数限制，只会到这里报错。"
        )
    if len(set(dimensions)) != len(dimensions):
        raise TooManyDimensions(f"分组维度重复：{dimensions}")
    if len(dimensions) > MAX_COHORT_DIMENSIONS:
        raise TooManyDimensions(
            f"分组维度 {len(dimensions)} 层超过上限 {MAX_COHORT_DIMENSIONS}（B9）"
        )


def aggregate_resource_coverage(
    tuples: list[MetricTuple],
    *,
    period: str,
    scope: str,
    cohort_dimensions: tuple[str, ...] = (),
    cohort_values: tuple[object, ...] | None = None,
    computed_at: datetime,
    aggregate_id: str = "AGG-1",
) -> ResourceCoverageAggregate:
    """把去标识元组聚合成校方看到的**一个单元格**。

    ``cohort_dimensions`` 为空表示全校口径；非空时**必须**同时给出
    ``cohort_values`` 指明是哪一格。

    曾经这里只按 ``period`` 过滤，``cohort_dimensions`` 收下就丢掉，
    于是一个只有 2 人的院系-年级格子拿到的是全校 102 人的分母与比率：
    既把全校数字冒充成该群体的数字，又让 ``MIN_CELL_N`` 抑制永远不触发。
    要一次拿到所有格子，用 :func:`aggregate_all_cells`。
    """
    _validate_dimensions(cohort_dimensions)
    if cohort_dimensions and cohort_values is None:
        raise ValueError(
            "给了 cohort_dimensions 就必须给 cohort_values 指明是哪一格——"
            "否则算出来的是全体数字，却会被贴上该分组的标签"
        )
    if cohort_values is not None and len(cohort_values) != len(cohort_dimensions):
        raise ValueError("cohort_values 与 cohort_dimensions 长度不一致")

    relevant = [t for t in tuples if t.period == period]
    if cohort_dimensions:
        relevant = [
            t for t in relevant if _cell_key(t, cohort_dimensions) == tuple(cohort_values)
        ]
    cell_n = len(relevant)

    if cell_n < MIN_CELL_N:
        return ResourceCoverageAggregate(
            aggregate_id=aggregate_id, period=period, scope=scope,  # type: ignore[arg-type]
            cohort_dims_used=cohort_dimensions, cell_n=cell_n,
            discovery_rate=None, action_rate=None, gap_coverage_rate=None,
            suppressed_cells=(
                SuppressedCell(cell_key="|".join(cohort_dimensions) or "institution",
                               n=cell_n, reason="below_min_cell_n"),
            ),
            computed_at=computed_at,
        )

    eligible = sum(t.eligible_count for t in relevant)
    seen = sum(t.seen_count for t in relevant)
    acted = sum(t.acted_count for t in relevant)
    gap_total = sum(t.gap_total for t in relevant)
    gap_covered = sum(t.gap_covered for t in relevant)

    # 供给缺口榜：出现频次最高、但资源池覆盖不了的要求类别
    category_counts: dict[RequirementCategory, int] = defaultdict(int)
    for t in relevant:
        for category in t.uncovered_requirement_categories:
            category_counts[category] += 1
    unmet = tuple(
        UnmetRequirementEntry(category=category, occurrences=count,
                              covered_by_any_resource=False)
        for category, count in sorted(
            category_counts.items(), key=lambda kv: (-kv[1], kv[0].value)
        )
        if count >= MIN_CELL_N
    )
    suppressed = tuple(
        SuppressedCell(cell_key=f"category:{category.value}", n=count,
                       reason="below_min_cell_n")
        for category, count in sorted(category_counts.items(), key=lambda kv: kv[0].value)
        if count < MIN_CELL_N
    )

    return ResourceCoverageAggregate(
        aggregate_id=aggregate_id, period=period, scope=scope,  # type: ignore[arg-type]
        cohort_dims_used=cohort_dimensions, cell_n=cell_n,
        discovery_rate=round(seen / eligible, 4) if eligible else None,
        action_rate=round(acted / seen, 4) if seen else None,
        gap_coverage_rate=round(gap_covered / gap_total, 4) if gap_total else None,
        unmet_requirement_ranking=unmet,
        suppressed_cells=suppressed,
        computed_at=computed_at,
    )


def build_exposure_gap_ranking(
    exposure: dict[str, tuple[int, int]]
) -> tuple[ExposureGapEntry, ...]:
    """曝光断层榜：合格的人多、实际看到的人少。

    ``exposure`` 是 ``{opportunity_id: (eligible_n, seen_n)}``。
    样本不足的机会**不进榜**——榜单本身也是一个个单元格。
    """
    entries = [
        ExposureGapEntry(
            opportunity_id=opportunity_id,
            eligible_n=eligible_n,
            seen_n=seen_n,
            exposure_rate=round(seen_n / eligible_n, 4) if eligible_n else 0.0,
        )
        for opportunity_id, (eligible_n, seen_n) in sorted(exposure.items())
        if eligible_n >= MIN_CELL_N
    ]
    entries.sort(key=lambda e: (e.exposure_rate, e.opportunity_id))
    return tuple(entries)


def _decay_weight(submitted_at: datetime, now: datetime, half_life_days: int) -> float:
    age_days = max((now - submitted_at).days, 0)
    return 0.5 ** (age_days / half_life_days)


def aggregate_event_quality(
    feedback: list[EventQualityFeedback],
    *,
    occurrence_id: str | None = None,
    series_id: str | None = None,
    now: datetime,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
    aggregate_id: str = "Q-1",
) -> EventQualityAggregate:
    """活动质量聚合：时间衰减 + 样本阈值 + 置信区间。

    低于阈值时**不输出维度分数**——契约层的 validator 会拒绝，
    所以这里必须自己先判断，而不是构造完再抱歉。
    """
    relevant = [
        f for f in feedback
        if (occurrence_id is not None and f.occurrence_id == occurrence_id)
        or (series_id is not None and f.series_id == series_id)
    ]
    verified = [f for f in relevant if f.verified_attendance]

    if len(verified) < MIN_CELL_N:
        return EventQualityAggregate(
            aggregate_id=aggregate_id, occurrence_id=occurrence_id, series_id=series_id,
            verified_n=len(verified), dimensions=(),
            time_decay_half_life_days=half_life_days, last_updated=now,
        )

    dimensions: list[DimensionAggregate] = []
    for dimension in QualityDimension:
        pairs = [
            (rating.rating, _decay_weight(f.submitted_at, now, half_life_days))
            for f in verified for rating in f.dimensions if rating.dimension is dimension
        ]
        if not pairs:
            continue
        total_weight = sum(w for _, w in pairs)
        mean = sum(r * w for r, w in pairs) / total_weight
        # 加权标准误；样本小则区间宽，而不是假装精确
        variance = sum(w * (r - mean) ** 2 for r, w in pairs) / total_weight
        stderr = math.sqrt(variance / max(len(pairs), 1))
        margin = 1.96 * stderr
        dimensions.append(
            DimensionAggregate(
                dimension=dimension,
                weighted_score=round(min(max(mean, 1.0), 5.0), 3),
                ci_low=round(min(max(mean - margin, 1.0), 5.0), 3),
                ci_high=round(min(max(mean + margin, 1.0), 5.0), 3),
            )
        )

    return EventQualityAggregate(
        aggregate_id=aggregate_id, occurrence_id=occurrence_id, series_id=series_id,
        verified_n=len(verified), dimensions=tuple(dimensions),
        time_decay_half_life_days=half_life_days, last_updated=now,
    )


def aggregate_all_cells(
    tuples: list[MetricTuple],
    *,
    period: str,
    scope: str,
    cohort_dimensions: tuple[str, ...],
    computed_at: datetime,
) -> list[ResourceCoverageAggregate]:
    """按分组维度切出**所有**单元格，逐格聚合并逐格抑制。

    这是校方"分组对比"视图的数据源（Spec §17.1.2）。每格自带自己的
    ``cell_n``，样本不足的那格数值为 None——不会借别格的样本量蒙混过关。
    """
    _validate_dimensions(cohort_dimensions)
    relevant = [t for t in tuples if t.period == period]
    cells = sorted({_cell_key(t, cohort_dimensions) for t in relevant}, key=repr)
    return [
        aggregate_resource_coverage(
            relevant,
            period=period,
            scope=scope,
            cohort_dimensions=cohort_dimensions,
            cohort_values=cell,
            computed_at=computed_at,
            aggregate_id="AGG-" + "-".join(str(v) for v in cell),
        )
        for cell in cells
    ]
