"""先修表达式解析与判定（TDD：本文件先于实现写成）。

素材全部来自 **真实的 HKUST 公开课程目录**，不是编造的样例。
这是 WP2 冻结课程快照的直接收益：解析器面对的是学校真的会写出来的句子。

贯穿全文件的一条安全性质：

> **解析器的无能只能变成 UNKNOWN，永远不能变成 NOT_MET。**

判不出来就说判不出来，交给学生确认。把"我看不懂"当成"你不满足"，
会直接制造 Spec §16.2 第 5 条禁止的那种淘汰。
"""

from __future__ import annotations

import pytest

from campuspath_rules.prerequisites import (
    AcademicRecord,
    Verdict,
    evaluate,
    parse,
)


def record(*completed: str, grades: dict[str, str] | None = None) -> AcademicRecord:
    return AcademicRecord(completed=frozenset(completed), grades=dict(grades or {}))


EMPTY = record()


# --------------------------------------------------------------------------
# 单课程
# --------------------------------------------------------------------------


def test_single_course_met():
    assert evaluate(parse("COMP 1021"), record("COMP 1021")).verdict is Verdict.MET


def test_single_course_not_met():
    assert evaluate(parse("COMP 1021"), EMPTY).verdict is Verdict.NOT_MET


def test_empty_expression_is_met():
    """无先修要求即满足，不是"未知"。"""
    assert evaluate(parse(""), EMPTY).verdict is Verdict.MET
    assert evaluate(parse(None), EMPTY).verdict is Verdict.MET


def test_course_code_without_space_is_normalised():
    assert evaluate(parse("COMP1021"), record("COMP 1021")).verdict is Verdict.MET


# --------------------------------------------------------------------------
# OR / AND / 括号 —— 真实表达式
# --------------------------------------------------------------------------


def test_simple_or():
    expr = parse("COMP 2011 OR COMP 2012 OR COMP 2012H")
    assert evaluate(expr, record("COMP 2012")).verdict is Verdict.MET
    assert evaluate(expr, EMPTY).verdict is Verdict.NOT_MET


def test_simple_and():
    expr = parse("COMP 3211 AND COMP 3511")
    assert evaluate(expr, record("COMP 3211", "COMP 3511")).verdict is Verdict.MET
    assert evaluate(expr, record("COMP 3211")).verdict is Verdict.NOT_MET


def test_and_binds_tighter_than_or():
    """`A OR B AND C` 必须解析为 `A OR (B AND C)`。

    弄反了会把"只修了 A"判成不满足，属于会淘汰学生的错误。
    """
    expr = parse("COMP 1021 OR COMP 2011 AND COMP 2012")
    assert evaluate(expr, record("COMP 1021")).verdict is Verdict.MET
    assert evaluate(expr, record("COMP 2011")).verdict is Verdict.NOT_MET
    assert evaluate(expr, record("COMP 2011", "COMP 2012")).verdict is Verdict.MET


def test_real_comp3711_expression():
    expr = parse("(COMP 2011 OR COMP 2012 OR COMP 2012H) AND (COMP 2711 OR COMP 2711H OR MATH 2343)")
    assert evaluate(expr, record("COMP 2012", "MATH 2343")).verdict is Verdict.MET
    assert evaluate(expr, record("COMP 2012")).verdict is Verdict.NOT_MET
    assert evaluate(expr, record("COMP 2711")).verdict is Verdict.NOT_MET


def test_real_bracket_expression():
    """方括号与圆括号等价（COMP 3511 的真实写法）。"""
    expr = parse("COMP 2611 OR [ELEC 2350 AND (COMP 2011 OR COMP 2012H)]")
    assert evaluate(expr, record("COMP 2611")).verdict is Verdict.MET
    assert evaluate(expr, record("ELEC 2350", "COMP 2011")).verdict is Verdict.MET
    assert evaluate(expr, record("ELEC 2350")).verdict is Verdict.NOT_MET


def test_slash_means_or():
    expr = parse("MATH 2111 / MATH 2121 / MATH 2131 / MATH 2350")
    assert evaluate(expr, record("MATH 2121")).verdict is Verdict.MET
    assert evaluate(expr, EMPTY).verdict is Verdict.NOT_MET


def test_prior_to_annotation_does_not_break_the_code():
    expr = parse("COMP 1021 OR COMP 1022P (prior to 2025-26) OR COMP 1023")
    assert evaluate(expr, record("COMP 1022P")).verdict is Verdict.MET
    assert evaluate(expr, record("COMP 1023")).verdict is Verdict.MET


def test_semicolon_behaves_as_or():
    expr = parse("MATH 2121/MATH 2111/MATH 2350/MATH 2131; or MATH 2343/COMP 2711")
    assert evaluate(expr, record("COMP 2711")).verdict is Verdict.MET
    assert evaluate(expr, record("MATH 2111")).verdict is Verdict.MET
    assert evaluate(expr, EMPTY).verdict is Verdict.NOT_MET


# --------------------------------------------------------------------------
# 成绩条件
# --------------------------------------------------------------------------


def test_grade_condition_met():
    expr = parse("Grade A- or above in COMP 2012")
    assert evaluate(expr, record("COMP 2012", grades={"COMP 2012": "A"})).verdict is Verdict.MET


def test_grade_condition_not_met():
    expr = parse("Grade A- or above in COMP 2012")
    assert evaluate(expr, record("COMP 2012", grades={"COMP 2012": "B+"})).verdict is Verdict.NOT_MET


def test_grade_condition_without_grade_is_unknown():
    """修过但成绩未授权/未出分——这是"不知道"，不是"不满足"。"""
    outcome = evaluate(parse("Grade A- or above in COMP 2012"), record("COMP 2012"))
    assert outcome.verdict is Verdict.UNKNOWN
    # reasons 现在是 LocalizedText：**两种语言都要断言**，
    # 只查中文会让"英文那侧没翻"重新变成看不见的缺陷
    assert any("成绩" in r.zh_Hans for r in outcome.reasons)
    assert any("grade" in r.en.lower() for r in outcome.reasons)


def test_grade_condition_over_slash_list():
    expr = parse("Grade B+ or above in COMP 2011 / COMP 2012 / COMP 2012H")
    assert evaluate(expr, record("COMP 2012", grades={"COMP 2012": "A-"})).verdict is Verdict.MET
    assert evaluate(expr, record("COMP 2011", grades={"COMP 2011": "C"})).verdict is Verdict.NOT_MET


def test_pass_grade_condition():
    expr = parse("Pass grade in COMP 1028")
    assert evaluate(expr, record("COMP 1028", grades={"COMP 1028": "D"})).verdict is Verdict.MET
    assert evaluate(expr, record("COMP 1028", grades={"COMP 1028": "F"})).verdict is Verdict.NOT_MET


def test_real_honors_expression():
    expr = parse("(Grade A or above in COMP 1023) OR (Grade A or above in COMP 1021 AND Pass grade in COMP 1028)")
    assert evaluate(expr, record("COMP 1023", grades={"COMP 1023": "A+"})).verdict is Verdict.MET
    assert evaluate(
        expr,
        record("COMP 1021", "COMP 1028", grades={"COMP 1021": "A", "COMP 1028": "P"}),
    ).verdict is Verdict.MET


# ── 以下四条来自 2026-07-29 的独立审查，全部是**当时真的判错**的真实表达式 ──
# 它们的共同根因：成绩子句曾排在拆 OR/AND 之前，把整条表达式一口吞下，
# 里面的连接词随之丢失。四条各自钉住一个方向。


def test_nested_and_inside_a_grade_branch_is_not_flattened_to_or():
    """COMP 2012H 的真实先修。**假阳性**：只修了 COMP 1021 曾被判成满足。

    这是 T2（把不合格判成可申请）最怕的方向——学生会去投一个他其实没资格的机会。
    """
    expr = parse(
        "(Grade A or above in COMP 1023) OR "
        "(Grade A or above in COMP 1021 AND Pass grade in COMP 1028)"
    )
    outcome = evaluate(expr, record("COMP 1021", grades={"COMP 1021": "A"}))
    assert outcome.verdict is Verdict.NOT_MET, "缺 COMP 1028 却被判满足"


def test_per_branch_grade_thresholds_are_kept():
    """MATH 4033 的真实先修。**假阴性**：MATH 2024 只需 B-，曾被按 A- 判。

    这是"以推断淘汰学生"，Spec §16.2 第 5 条禁止的方向。
    """
    expr = parse(
        "(Grade A- or above in MATH 2023 OR Grade B- or above in MATH 2024) "
        "AND (Grade B- or above in MATH 2131)"
    )
    outcome = evaluate(
        expr,
        record("MATH 2024", "MATH 2131", grades={"MATH 2024": "B", "MATH 2131": "B"}),
    )
    assert outcome.verdict is Verdict.MET, "MATH 2024 的 B- 线被误当成 A-"


def test_external_qualification_does_not_swallow_the_alternatives():
    """MATH 2350 / 2411 / 4921 的真实先修。

    曾经整条被当成"外部资历"，于是修过 MATH 1014 的学生永远停在 needs_confirmation。
    """
    expr = parse(
        "A passing grade in AL Pure Mathematics / AL Applied Mathematics "
        "OR MATH 1014 OR MATH 1020 OR MATH 1024"
    )
    assert evaluate(expr, record("MATH 1014")).verdict is Verdict.MET
    # 没修任何一门本校课的学生仍应是"不知道"，而不是"不满足"
    assert evaluate(expr, EMPTY).verdict is Verdict.UNKNOWN


def test_slash_binds_looser_than_and():
    """`A / B AND C` 的人类读法是 `(A or B) and C`。

    `/` 表示"这几门课等效，任选其一"，AND 表示"另一个要求槽位"。
    读反了又是一个假阳性。
    """
    expr = parse("COMP 2011 / COMP 2012 AND MATH 1014")
    assert evaluate(expr, record("COMP 2011")).verdict is Verdict.NOT_MET
    assert evaluate(expr, record("COMP 2011", "MATH 1014")).verdict is Verdict.MET


# --------------------------------------------------------------------------
# 判不出来的部分：只能是 UNKNOWN
# --------------------------------------------------------------------------


def test_external_qualification_is_unknown_not_failure():
    """HKDSE 成绩不在系统里。系统不知道 ≠ 学生不满足。"""
    outcome = evaluate(
        parse("Level 3 or above in HKDSE Mathematics Extended Module M1/M2"), EMPTY
    )
    assert outcome.verdict is Verdict.UNKNOWN


def test_program_scoped_expression_is_unknown():
    """`(For DDP only) X; (For all others) Y` 不能当成 `X OR Y`。

    当成 OR 会让不属于 DDP 的学生凭 X 通过——一个会直接推高 T2 的假阳性。
    """
    outcome = evaluate(
        parse("(For DDP only) LANG 1403 OR LANG 1404; (For all others) LANG 2030"),
        record("LANG 1403"),
    )
    assert outcome.verdict is Verdict.UNKNOWN
    assert any("适用" in r.zh_Hans or "限定" in r.zh_Hans for r in outcome.reasons)
    assert any("programme" in r.en.lower() for r in outcome.reasons)


def test_garbage_is_unknown_not_failure():
    outcome = evaluate(parse("Consent of instructor required"), EMPTY)
    assert outcome.verdict is Verdict.UNKNOWN


def test_unknown_never_becomes_not_met_inside_or():
    """`已知不满足 OR 未知` = 未知。不能因为一支不满足就整体判否。"""
    expr = parse("COMP 9999 OR Level 3 or above in HKDSE Mathematics")
    assert evaluate(expr, EMPTY).verdict is Verdict.UNKNOWN


def test_known_met_wins_over_unknown_inside_or():
    expr = parse("COMP 1021 OR Level 3 or above in HKDSE Mathematics")
    assert evaluate(expr, record("COMP 1021")).verdict is Verdict.MET


def test_unknown_inside_and_is_unknown():
    expr = parse("COMP 1021 AND Level 3 or above in HKDSE Mathematics")
    assert evaluate(expr, record("COMP 1021")).verdict is Verdict.UNKNOWN


def test_known_not_met_wins_over_unknown_inside_and():
    """AND 里有一支确定不满足，整体就是不满足——这不是猜测。"""
    expr = parse("COMP 9999 AND Level 3 or above in HKDSE Mathematics")
    assert evaluate(expr, EMPTY).verdict is Verdict.NOT_MET


# --------------------------------------------------------------------------
# 全量回归：真实目录里的每一条表达式都不能让解析器崩溃
# --------------------------------------------------------------------------


def test_every_real_expression_parses_without_crashing(real_expressions):
    for expression in real_expressions:
        outcome = evaluate(parse(expression), EMPTY)
        assert outcome.verdict in set(Verdict), expression
        assert outcome.reasons, expression


def test_no_real_expression_is_silently_dropped(real_expressions):
    """解析不了要**说出来**。静默当成"无要求"会让所有先修检查形同虚设。"""
    for expression in real_expressions:
        if not expression.strip():
            continue
        outcome = evaluate(parse(expression), EMPTY)
        assert outcome.verdict is not Verdict.MET, (
            f"空记录的学生不应满足任何非空先修，却在 {expression!r} 上通过了"
        )


def test_parse_coverage_is_reported(real_expressions):
    """把"能解析的比例"变成一个会退化就变红的数字，而不是感觉。"""
    from campuspath_rules.prerequisites import parse_coverage

    coverage = parse_coverage(real_expressions)
    assert coverage.total == len(real_expressions)
    # 阈值设在 92%：留一点余量，但解析能力真的退化时会变红。
    # 剩下的是自然语言写法（IELTS 分数、"for students without corequisites"），
    # 按契约就该是 UNKNOWN → needs_confirmation，不是解析失败。
    assert coverage.fully_parsed_ratio >= 0.92, coverage


def test_actionable_ratio_is_reported_separately(real_expressions):
    """"认出来了"不等于"能给出可行动结论"。

    `ExternalRequirement` 与 `ProgramScoped` 都算解析成功，但它们对**任何**学生
    都只会返回 UNKNOWN。只看 fully_parsed_ratio 的话，解析器退化成"全部返回
    ExternalRequirement"也是 100%——那个数字会一直好看下去。
    """
    from campuspath_rules.prerequisites import parse_coverage

    coverage = parse_coverage(real_expressions)
    assert coverage.actionable < coverage.fully_parsed, (
        "actionable 应当严格小于 fully_parsed：真实目录里确实有外部资历与项目限定"
    )
    assert coverage.actionable_ratio >= 0.88, coverage
