"""Spec §17.1.2 / §14.4：匿名聚合与校方洞察。

Aggregation Service 是确定性零 LLM 服务，只接受两类输入：

* :class:`~campuspath_contracts.reflection.EventQualityFeedback` —— 活动质量；
* :class:`MetricTuple` —— 资源利用率（去标识元组）。

契约层强制两条 BLOCKER：

* **B10 MetricTuple Field Leakage**：元组的字段列表就是全部允许出域的内容。
  ``uncovered_requirement_categories`` 只收枚举的**要求类别**，
  不收缺口原文——原文能反推到具体学生。
* **B9 Metric Re-identification**：样本量低于阈值的单元格**必须**把数值置为 None
  并显示 `Insufficient evidence`。这里用 validator 强制，
  而不是指望前端记得判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import CampusPathModel, Identifier, StrEnum, TermCode
from .goals import RequirementCategory
from .reflection import CohortDims, QualityDimension

#: 低于该样本量的任何聚合单元格一律抑制（Spec §17.1.2 硬性边界第 1 条）。
#: 数值是产品规则而非统计定理，改动须同步评测项 B9 的用例。
MIN_CELL_N = 5

#: 分组维度可组合的最大层数，防止多重筛选把单元格缩到可识别规模（硬性边界第 3 条）。
MAX_COHORT_DIMENSIONS = 2


class InsufficientEvidence(StrEnum):
    """UI 必须显示的占位值。刻意做成枚举，避免被渲染成 0 或 '-'。"""

    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class MetricTuple(CampusPathModel):
    """离开学生数据域时携带的全部内容（Spec §17.1.2）。

    计算发生在学生私有域内；这个对象是**计算结果**，出域时已无 student_id。
    原始曝光与行动记录永不离开。
    """

    period: TermCode
    cohort_dims: CohortDims
    eligible_count: int = Field(ge=0)
    seen_count: int = Field(ge=0)
    acted_count: int = Field(ge=0)
    gap_total: int = Field(ge=0)
    gap_covered: int = Field(ge=0)
    uncovered_requirement_categories: tuple[RequirementCategory, ...] = ()

    @model_validator(mode="after")
    def _counts_are_nested(self) -> "MetricTuple":
        if self.seen_count > self.eligible_count:
            raise ValueError("seen_count 不能超过 eligible_count")
        if self.acted_count > self.seen_count:
            raise ValueError("acted_count 不能超过 seen_count（行动必先经过曝光）")
        if self.gap_covered > self.gap_total:
            raise ValueError("gap_covered 不能超过 gap_total")
        return self


class SuppressedCell(CampusPathModel):
    """被抑制的单元格。**记录被抑制这件事本身，但不记录被抑制的数值。**"""

    cell_key: str
    n: int = Field(ge=0)
    reason: Literal["below_min_cell_n", "too_many_dimensions"] = "below_min_cell_n"


class ExposureGapEntry(CampusPathModel):
    """曝光断层榜的一行：合格的人多，实际看到的人少。"""

    opportunity_id: Identifier
    eligible_n: int = Field(ge=MIN_CELL_N)
    seen_n: int = Field(ge=0)
    exposure_rate: float = Field(ge=0, le=1)


class UnmetRequirementEntry(CampusPathModel):
    """供给缺口榜的一行：这个要求类别，资源池里没有东西能覆盖。"""

    category: RequirementCategory
    occurrences: int = Field(ge=MIN_CELL_N)
    covered_by_any_resource: bool = False


class ResourceCoverageAggregate(CampusPathModel):
    """校方看到的最终形态。三项比率在样本不足时**必须**为 None。"""

    aggregate_id: Identifier
    period: TermCode
    scope: Literal["institution", "school", "year_level", "development_mode"]
    cohort_dims_used: tuple[str, ...] = ()
    cell_n: int = Field(ge=0)
    discovery_rate: float | None = Field(default=None, ge=0, le=1)
    action_rate: float | None = Field(default=None, ge=0, le=1)
    gap_coverage_rate: float | None = Field(default=None, ge=0, le=1)
    exposure_gap_ranking: tuple[ExposureGapEntry, ...] = ()
    unmet_requirement_ranking: tuple[UnmetRequirementEntry, ...] = ()
    suppressed_cells: tuple[SuppressedCell, ...] = ()
    computed_at: datetime

    @model_validator(mode="after")
    def _suppress_small_cells(self) -> "ResourceCoverageAggregate":
        if len(self.cohort_dims_used) > MAX_COHORT_DIMENSIONS:
            raise ValueError(
                f"分组维度层数 {len(self.cohort_dims_used)} 超过上限 {MAX_COHORT_DIMENSIONS}（B9）"
            )
        if self.cell_n < MIN_CELL_N:
            leaked = [
                name
                for name in ("discovery_rate", "action_rate", "gap_coverage_rate")
                if getattr(self, name) is not None
            ]
            if leaked or self.exposure_gap_ranking or self.unmet_requirement_ranking:
                raise ValueError(
                    f"样本量 {self.cell_n} < {MIN_CELL_N}，必须抑制数值并显示 "
                    f"Insufficient evidence（B9）；仍携带：{leaked or '排行榜'}"
                )
        return self


class DimensionAggregate(CampusPathModel):
    dimension: QualityDimension
    weighted_score: float = Field(ge=1, le=5)
    ci_low: float = Field(ge=1, le=5)
    ci_high: float = Field(ge=1, le=5)

    @model_validator(mode="after")
    def _interval_contains_estimate(self) -> "DimensionAggregate":
        if not (self.ci_low <= self.weighted_score <= self.ci_high):
            raise ValueError("weighted_score 必须落在置信区间内")
        return self


class EventQualityAggregate(CampusPathModel):
    """活动质量聚合（Spec §14.4）。时间衰减 + 届次/系列分层 + 样本阈值。"""

    aggregate_id: Identifier
    occurrence_id: Identifier | None = None
    series_id: Identifier | None = None
    cohort: CohortDims | None = None
    verified_n: int = Field(ge=0)
    dimensions: tuple[DimensionAggregate, ...] = ()
    time_decay_half_life_days: int = Field(default=365, ge=30)
    last_updated: datetime

    @model_validator(mode="after")
    def _threshold_and_target(self) -> "EventQualityAggregate":
        if self.occurrence_id is None and self.series_id is None:
            raise ValueError("质量聚合必须指向某一届或某个系列")
        if self.verified_n < MIN_CELL_N and self.dimensions:
            raise ValueError(
                f"verified_n={self.verified_n} 低于阈值 {MIN_CELL_N}，"
                "不得输出维度分数（B9）"
            )
        return self
