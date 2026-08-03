"""ISI / PSS-10 两层预警计分与分流（R5-E，2026-08-01）。

**纯算术，零 LLM**——本模块与整个 wellbeing 包同受三层零 LLM 扫描。
量表是公开的标准化筛查工具，题面固定、计分固定；
它们**不是诊断**，分流也只是"建议联系谁"，最终外联仍要学生确认（B13）。

计分口径：

* ISI：7 题 × 0–4，总分 0–28。0–7 无临床意义；8–14 亚临床；
  15–21 中度；22–28 重度。
* PSS-10：10 题 × 0–4，总分 0–40；第 4、5、7、8 题反向计分（0↔4）。
  0–13 低；14–26 中；27–40 高。

两层分流（用户裁定 2026-08-01；完备化档位见 tests/test_assessment.py 顶注）：

* ``counseling_center``：ISI ≥ 15 **且** PSS-10 > 20；
* ``tutor``：未达上层但 ISI ≥ 8 或 PSS-10 ≥ 14；
* ``none``：两者都低——只给自我调节建议，不打扰任何联系人。
"""

from __future__ import annotations

import dataclasses

#: 反向计分的题号（1 起）。PSS-10 的正性表述题。
_PSS10_REVERSED = frozenset({4, 5, 7, 8})

DISCLAIMER_ZH = (
    "以上为标准化自评筛查，不构成任何医学诊断或医学评估；"
    "分流仅为联系建议，是否发起联系由你决定。"
)
DISCLAIMER_EN = (
    "This is a standardised self-report screening, not a diagnosis or medical "
    "assessment of any kind; the routing is only a suggestion of whom to "
    "contact, and reaching out remains your decision."
)


@dataclasses.dataclass(frozen=True)
class AssessmentScore:
    isi_score: int
    isi_band: str            # none | subclinical | moderate | severe
    pss10_score: int
    pss10_band: str          # low | moderate | high
    routing: str             # none | tutor | counseling_center
    disclaimer_zh: str = DISCLAIMER_ZH
    disclaimer_en: str = DISCLAIMER_EN


def _validate(answers: list[int] | tuple[int, ...], count: int,
              upper: int, name: str) -> None:
    if len(answers) != count:
        raise ValueError(f"{name} 需要 {count} 题，收到 {len(answers)} 题")
    for index, value in enumerate(answers, start=1):
        if not isinstance(value, int) or not 0 <= value <= upper:
            raise ValueError(f"{name} 第 {index} 题取值须在 0–{upper}，收到 {value!r}")


def _isi_band(score: int) -> str:
    if score <= 7:
        return "none"
    if score <= 14:
        return "subclinical"
    if score <= 21:
        return "moderate"
    return "severe"


def _pss10_band(score: int) -> str:
    if score <= 13:
        return "low"
    if score <= 26:
        return "moderate"
    return "high"


def score_assessment(
    isi_answers: list[int] | tuple[int, ...],
    pss10_answers: list[int] | tuple[int, ...],
) -> AssessmentScore:
    """计分 + 两层分流。答案是原始作答；反向计分在这里做，调用方不用管。"""
    _validate(isi_answers, 7, 4, "ISI")
    _validate(pss10_answers, 10, 4, "PSS-10")

    isi_score = sum(isi_answers)
    pss10_score = sum(
        (4 - value) if index in _PSS10_REVERSED else value
        for index, value in enumerate(pss10_answers, start=1)
    )

    if isi_score >= 15 and pss10_score > 20:
        routing = "counseling_center"
    elif isi_score >= 8 or pss10_score >= 14:
        routing = "tutor"
    else:
        routing = "none"

    return AssessmentScore(
        isi_score=isi_score,
        isi_band=_isi_band(isi_score),
        pss10_score=pss10_score,
        pss10_band=_pss10_band(pss10_score),
        routing=routing,
    )
