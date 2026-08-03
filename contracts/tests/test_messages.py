"""文案目录的自检。

三条断言，每条都对应一种**会悄悄上线的**缺陷：

1. 两种语言的占位符集合必须完全一致——少一个占位符，那种语言就会
   丢掉具体数字，变成一句正确但没信息的话；
2. 没有一侧是空的——空串在界面上就是一片空白，不会报错；
3. 未登记的 key 必须抛异常——回落到 key 本身会让 ``elig.cgpa_ok``
   这样的字符串出现在学生面前，而它看起来像"某种编号"，不像 bug。
"""

from __future__ import annotations

import re

import pytest

from campuspath_contracts.messages import MESSAGES, UnknownMessage, render

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_both_languages_use_the_same_placeholders(key: str) -> None:
    zh, en = MESSAGES[key]
    assert set(_PLACEHOLDER.findall(zh)) == set(_PLACEHOLDER.findall(en)), (
        f"{key} 的中英占位符不一致——其中一种语言会丢掉具体数值"
    )


@pytest.mark.parametrize("key", sorted(MESSAGES))
def test_neither_language_is_empty(key: str) -> None:
    zh, en = MESSAGES[key]
    assert zh.strip() and en.strip(), f"{key} 有一侧是空的"


def test_unknown_key_raises_instead_of_falling_back() -> None:
    with pytest.raises(UnknownMessage):
        render("elig.this_key_does_not_exist")


def test_render_fills_both_sides() -> None:
    text = render("prereq.met", course="COMP 1021")
    assert "COMP 1021" in text.zh_Hans
    assert "COMP 1021" in text.en
    assert text.zh_Hans != text.en, (
        "两侧完全相同说明这条其实没翻译——那正是这次要消灭的东西"
    )


def test_the_placeholder_check_can_fail() -> None:
    """H5：用一个**已知会失败**的样例证明上面那条检查真的会红。"""
    broken = {"x.broken": ("有 {a} 和 {b}", "only {a}")}
    zh, en = broken["x.broken"]
    assert set(_PLACEHOLDER.findall(zh)) != set(_PLACEHOLDER.findall(en))
