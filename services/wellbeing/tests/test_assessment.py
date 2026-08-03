"""R5-E（2026-08-01，用户当日修订版）：ISI / PSS-10 两层预警计分——**纯算术，零 LLM**。

先写测试（TDD）。计分口径用两个量表的公开标准：

* ISI（失眠严重程度指数）：7 题 × 0–4，总分 0–28。
  0–7 无临床意义；8–14 亚临床；15–21 中度；22–28 重度。
* PSS-10（知觉压力量表）：10 题 × 0–4，总分 0–40，
  其中第 4、5、7、8 题**反向计分**（0↔4）。
  常用分档：0–13 低压力；14–26 中等；27–40 高压力。

两层分流（用户裁定 2026-08-01）：
* 第二层（心理咨询室）：ISI ≥ 15 **且** PSS-10 > 20 —— 重度失眠 + 高压力。
* 第一层（辅导员 tutor）：未达第二层、但任一量表有信号
  （ISI ≥ 8 或 PSS-10 ≥ 14）—— 压力 / 轻度睡眠障碍的初筛干预。
* 两者都低（ISI ≤ 7 且 PSS-10 ≤ 13）→ 无需干预，仅自我调节建议。
  （用户规则只写了两层的典型情形；单边达标归第一层——
  字面上只有"且"才进第二层。完备化档位在此明示，改口径先改这里。）

所有产出必须带"不构成诊断"声明——筛查不是诊断，分流不是结论。
"""

import pytest

from campuspath_wellbeing.assessment import (
    DISCLAIMER_EN,
    DISCLAIMER_ZH,
    score_assessment,
)


def test_pss10_reverse_scores_items_4_5_7_8():
    """PSS-10 的 4/5/7/8 题反向计分——不反向会把最平静的人算成最紧绷。"""
    # 全部答 0：正向题得 0，反向题得 4 → 总分 16
    result = score_assessment(isi_answers=[0] * 7, pss10_answers=[0] * 10)
    assert result.pss10_score == 16
    # 全部答 4：正向题得 4×6=24，反向题得 0 → 总分 24
    result = score_assessment(isi_answers=[0] * 7, pss10_answers=[4] * 10)
    assert result.pss10_score == 24


def test_tier2_requires_both_severe_insomnia_and_high_stress():
    """第二层：ISI ≥15 **且** PSS-10 >20 → 心理咨询室。"""
    isi15 = [3] * 5 + [0, 0]
    # PSS 原始答案设计成计分 >20：正向 6 题全 4（24 分）+ 反向 4 题全 4（0 分）= 24
    high_stress = [4] * 10
    result = score_assessment(isi_answers=isi15, pss10_answers=high_stress)
    assert result.isi_score == 15 and result.pss10_score == 24
    assert result.routing == "counseling_center"


def test_severe_isi_alone_stays_tier1():
    """单边达标（ISI ≥15 但 PSS-10 ≤20）→ 第一层辅导员——规则是"且"。"""
    calm = [0, 0, 0, 4, 4, 0, 4, 4, 0, 0]      # 反向题全 4 → 计 0；总分 0
    result = score_assessment(isi_answers=[3] * 5 + [0, 0], pss10_answers=calm)
    assert result.pss10_score == 0
    assert result.routing == "tutor"


def test_moderate_signals_route_to_tutor():
    """第一层：ISI ≥8 或 PSS-10 ≥14 → 辅导员初筛干预。"""
    result = score_assessment(isi_answers=[2] * 4 + [0] * 3, pss10_answers=[0] * 10)
    assert result.isi_score == 8 and result.routing == "tutor"


def test_minimal_scores_need_no_intervention():
    """两个量表都低 → 无需干预（自我调节建议），不打扰任何联系人。"""
    calm = [0, 0, 0, 4, 4, 0, 4, 4, 0, 0]      # PSS-10 计分 0
    result = score_assessment(isi_answers=[1] * 7, pss10_answers=calm)
    assert result.isi_score == 7 and result.pss10_score == 0
    assert result.routing == "none"


def test_band_boundaries_are_pinned():
    calm = [0, 0, 0, 4, 4, 0, 4, 4, 0, 0]
    assert score_assessment([2] * 7, calm).isi_band == "subclinical"       # 14
    assert score_assessment([3] * 7, calm).isi_band == "moderate"          # 21
    assert score_assessment([4] * 7, calm).isi_band == "severe"            # 28
    assert score_assessment([0] * 7, [4] * 10).pss10_band == "moderate"    # 24
    # 高压力档（≥27）：正向 6 题全 4 + 反向 4 题答 1（各计 3）= 24+3? 需 ≥27：
    # 正向 24 + 反向 4 题答 0（各计 4）= 40 → high
    assert score_assessment([0] * 7, [4, 4, 4, 0, 0, 4, 0, 0, 4, 4]).pss10_band == "high"


def test_answers_are_validated():
    """题数不对、分值越界必须报错——静默截断会改变分流结果。"""
    with pytest.raises(ValueError):
        score_assessment([1] * 6, [1] * 10)         # ISI 少一题
    with pytest.raises(ValueError):
        score_assessment([5] + [0] * 6, [1] * 10)   # ISI 单题上限 4
    with pytest.raises(ValueError):
        score_assessment([0] * 7, [1] * 9)          # PSS-10 少一题
    with pytest.raises(ValueError):
        score_assessment([0] * 7, [5] + [0] * 9)    # PSS-10 单题上限 4


def test_disclaimer_is_always_attached():
    """筛查不是诊断。声明是产出的一部分，不是 UI 的自觉。"""
    result = score_assessment([0] * 7, [0] * 10)
    assert "不构成" in result.disclaimer_zh and result.disclaimer_zh == DISCLAIMER_ZH
    assert "not a diagnosis" in result.disclaimer_en.lower()
    assert result.disclaimer_en == DISCLAIMER_EN


def test_no_model_sdk_in_scoring_path():
    """零 LLM：计分模块不得携带任何模型 SDK 依赖。"""
    import sys

    import campuspath_wellbeing.assessment  # noqa: F401

    assert not any(
        m.startswith(("google.genai", "google.generativeai", "vertexai"))  # ai-studio-denylist
        for m in sys.modules
    )
