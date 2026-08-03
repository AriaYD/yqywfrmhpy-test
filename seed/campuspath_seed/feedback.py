"""历史活动质量反馈与去标识指标元组。

两条数据都是**通往校方的出域数据**，因此这里生成的是契约里的边界类型本身：
:class:`EventQualityFeedback` 与 :class:`MetricTuple`。
它们连字段都不含 student_id——不是"生成时记得别写"，是类型上写不进去。

刻意造出三种情形，供 B9 与 §17.4 的指标验证：

1. **样本充足且质量稳定好**——正常基线；
2. **宣传好但反馈持续差**——Spec §11.3 的失败样本，跨两届都低分；
3. **样本不足**（verified_n < MIN_CELL_N）——聚合时必须显示 `Insufficient evidence`。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.aggregation import MIN_CELL_N, MetricTuple
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.opportunity import Opportunity
from campuspath_contracts.reflection import (
    CohortDims,
    DimensionRating,
    EventQualityFeedback,
    FitTag,
    QualityDimension,
)

from .config import CURRENT_TERM, SEED_TODAY
from .personas import PersonaBundle
from .rng import pick, sample, stream

_TZ = timezone.utc


def _dt(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, 18, tzinfo=_TZ)


@dataclasses.dataclass
class FeedbackBundle:
    feedback: list[EventQualityFeedback]
    metric_tuples: list[MetricTuple]
    #: 被刻意设成"宣传好、反馈差"的系列 id，供失败样本与评测引用
    persistently_low_series: list[str]
    #: 样本不足的 occurrence id
    under_threshold_occurrences: list[str]


_SCHOOLS = ("ENGG", "BUS", "SCI")
_MODES = ("employment", "exploration", "academia", "entrepreneurship")


def build_feedback(
    opportunities: list[Opportunity], personas: list[PersonaBundle], count: int
) -> FeedbackBundle:
    rng = stream("feedback")
    events = [o for o in opportunities if o.occurrence_id and o.series_id]
    if not events:
        return FeedbackBundle([], [], [], [])

    low_series = sorted({e.series_id for e in events})[:2]
    thin_occurrences = [e.occurrence_id for e in events[-2:]]

    feedback: list[EventQualityFeedback] = []
    index = 0
    for event in events:
        is_low = event.series_id in low_series
        is_thin = event.occurrence_id in thin_occurrences
        responses = 1 if is_thin else rng.randrange(MIN_CELL_N, MIN_CELL_N + 6)
        for _ in range(responses):
            if index >= count:
                break
            index += 1
            base = 2 if is_low else 4
            feedback.append(
                EventQualityFeedback(
                    feedback_id=f"EQF-{index:04d}",
                    occurrence_id=event.occurrence_id,
                    series_id=event.series_id,
                    verified_attendance=True,
                    # 不透明凭据：不能是 evidence_id，否则聚合域又连回个人
                    verification_ref=f"ver_{index:016x}",
                    dimensions=tuple(
                        DimensionRating(
                            dimension=dim,
                            rating=max(1, min(5, base + rng.randrange(-1, 2))),
                        )
                        for dim in QualityDimension
                    ),
                    fit_tags=(pick(rng, list(FitTag)),),
                    cohort_dims=CohortDims(
                        school=pick(rng, list(_SCHOOLS)),
                        year_level=rng.randrange(1, 5),
                        development_mode=pick(rng, list(_MODES)),
                    ),
                    submitted_at=_dt(SEED_TODAY - timedelta(days=rng.randrange(10, 200))),
                )
            )
        if index >= count:
            break

    # 去标识指标元组：每个学生在私有域内算出一条，出域时已无 student_id
    tuples: list[MetricTuple] = []
    for persona in personas:
        profile = persona.profile
        prng = stream(f"metrics.{profile.student_id}")
        eligible = prng.randrange(18, 46)
        seen = prng.randrange(int(eligible * 0.3), eligible + 1)
        acted = prng.randrange(0, max(1, int(seen * 0.4)) + 1)
        gap_total = prng.randrange(6, 16)
        gap_covered = prng.randrange(int(gap_total * 0.4), gap_total + 1)
        uncovered = tuple(
            sorted(
                set(sample(prng, list(RequirementCategory), gap_total - gap_covered)),
                key=lambda c: c.value,
            )
        )
        tuples.append(
            MetricTuple(
                period=CURRENT_TERM,
                cohort_dims=CohortDims(
                    school={"BSC-COMP": "ENGG", "BENG-IEDA": "ENGG", "BBA-ISOM": "BUS"}[
                        profile.program_id
                    ],
                    year_level=profile.year,
                    development_mode=(
                        profile.development_modes[0].mode.value
                        if profile.development_modes else "exploration"
                    ),
                ),
                eligible_count=eligible,
                seen_count=seen,
                acted_count=acted,
                gap_total=gap_total,
                gap_covered=gap_covered,
                uncovered_requirement_categories=uncovered,
            )
        )

    return FeedbackBundle(
        feedback=feedback,
        metric_tuples=tuples,
        persistently_low_series=low_series,
        under_threshold_occurrences=thin_occurrences,
    )
