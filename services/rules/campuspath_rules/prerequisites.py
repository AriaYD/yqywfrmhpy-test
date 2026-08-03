"""先修表达式解析与三值判定。

Rules & Constraint Engine 的一部分，**零 LLM**：一个先修表达式该不该算满足，
是语法与集合运算的问题，不是语义判断。真实表达式的形状见课程目录快照。

## 三值逻辑，以及为什么必须是三值

判定结果只有 MET / NOT_MET / **UNKNOWN** 三种。第三种不是偷懒：

* 成绩条件而学生未授权成绩 → 不知道；
* HKDSE、AL 等外部资历 → 系统里根本没有；
* `(For DDP only) …; (For all others) …` 这类**程序限定** → 我们没有可靠的
  项目代码映射；
* 解析器读不懂的写法 → 不知道。

这些一律是 UNKNOWN，向上传导成资格四态里的 `needs_confirmation`。
**绝不能变成 NOT_MET** —— 那是 Spec §16.2 第 5 条明确禁止的"以推断淘汰学生"。

## 组合规则

| 节点 | MET | NOT_MET | 否则 |
|---|---|---|---|
| ALL（AND） | 全部 MET | **任一** NOT_MET | UNKNOWN |
| ANY（OR） | **任一** MET | 全部 NOT_MET | UNKNOWN |

AND 里有一支确定不满足就整体不满足——那不是猜测，是逻辑蕴含。
OR 里有一支不满足但另一支未知，则整体未知。
"""

from __future__ import annotations

import dataclasses
import re
from enum import Enum
from typing import Iterable, Sequence

from campuspath_contracts.common import LocalizedText
from campuspath_contracts.messages import render

__all__ = [
    "AcademicRecord",
    "Verdict",
    "Outcome",
    "Node",
    "All",
    "Any_",
    "CourseRequirement",
    "ExternalRequirement",
    "ProgramScoped",
    "Unparsed",
    "parse",
    "evaluate",
    "parse_coverage",
]


class Verdict(str, Enum):
    """三值判定。``str`` 混入是为了能直接进 JSON 与错误信息。"""

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


#: HKUST 字母等级，由高到低。``P`` 视同及格但无等第。
GRADE_ORDER: tuple[str, ...] = (
    "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "F",
)
_PASSING = set(GRADE_ORDER[:-1]) | {"P", "PASS"}


@dataclasses.dataclass(frozen=True)
class AcademicRecord:
    """判定所需的最小学业事实。

    刻意只有两项：修过什么、成绩是多少。先修判定不需要姓名、目标或日历——
    传得越少，越不可能在这一层泄露不该泄露的东西。
    """

    completed: frozenset[str] = frozenset()
    grades: dict[str, str] = dataclasses.field(default_factory=dict)

    def has(self, course_id: str) -> bool:
        return course_id in self.completed

    def grade_of(self, course_id: str) -> str | None:
        return self.grades.get(course_id)


@dataclasses.dataclass(frozen=True)
class Outcome:
    verdict: Verdict
    #: **双语**。判定理由会直接显示给学生，它就是 UI 文案（见 messages.py）。
    reasons: tuple[LocalizedText, ...]

    def __bool__(self) -> bool:  # pragma: no cover - 防止误用
        raise TypeError("三值判定不能当布尔用——UNKNOWN 会被静默当成 False")


# --------------------------------------------------------------------------
# AST
# --------------------------------------------------------------------------


class Node:
    def evaluate(self, record: AcademicRecord) -> Outcome:  # pragma: no cover - 抽象
        raise NotImplementedError

    def is_fully_parsed(self) -> bool:
        return True


@dataclasses.dataclass(frozen=True)
class CourseRequirement(Node):
    course_id: str
    min_grade: str | None = None
    note: str | None = None

    def evaluate(self, record: AcademicRecord) -> Outcome:
        label = self.course_id + (f"（{self.note}）" if self.note else "")
        if not record.has(self.course_id):
            return Outcome(Verdict.NOT_MET, (render("prereq.not_met", course=label),))
        if self.min_grade is None:
            return Outcome(Verdict.MET, (render("prereq.met", course=label),))

        grade = record.grade_of(self.course_id)
        if grade is None:
            return Outcome(
                Verdict.UNKNOWN,
                (render("prereq.grade_unknown", course=label,
                        required=self.min_grade),),
            )
        if _grade_meets(grade, self.min_grade):
            return Outcome(Verdict.MET, (render("prereq.grade_met", course=label,
                                            actual=grade, required=self.min_grade),))
        return Outcome(Verdict.NOT_MET, (render("prereq.grade_not_met", course=label,
                                                actual=grade, required=self.min_grade),))


@dataclasses.dataclass(frozen=True)
class ExternalRequirement(Node):
    """系统外的资历（HKDSE、A-Level 等）。永远 UNKNOWN。"""

    text: str

    def evaluate(self, record: AcademicRecord) -> Outcome:
        return Outcome(Verdict.UNKNOWN, (render("prereq.external", text=self.text),))

    def is_fully_parsed(self) -> bool:
        return True          # 能识别出"这是外部资历"本身就是解析成功


@dataclasses.dataclass(frozen=True)
class ProgramScoped(Node):
    """带项目限定的分支，例如 `(For DDP only) …`。

    不把它当成 OR：那会让不属于该项目的学生凭另一支通过，
    制造 Spec §17.5 里 `Hard Eligibility False Positive` 的假阳性。
    """

    text: str

    def evaluate(self, record: AcademicRecord) -> Outcome:
        return Outcome(
            Verdict.UNKNOWN,
            (render("prereq.programme_scoped", text=self.text),),
        )


@dataclasses.dataclass(frozen=True)
class Unparsed(Node):
    text: str

    def evaluate(self, record: AcademicRecord) -> Outcome:
        return Outcome(Verdict.UNKNOWN, (render("prereq.unreadable", text=self.text),))

    def is_fully_parsed(self) -> bool:
        return False


@dataclasses.dataclass(frozen=True)
class Empty(Node):
    def evaluate(self, record: AcademicRecord) -> Outcome:
        return Outcome(Verdict.MET, (render("prereq.none"),))


@dataclasses.dataclass(frozen=True)
class All(Node):
    children: tuple[Node, ...]

    def evaluate(self, record: AcademicRecord) -> Outcome:
        outcomes = [child.evaluate(record) for child in self.children]
        reasons = tuple(r for o in outcomes for r in o.reasons)
        if any(o.verdict is Verdict.NOT_MET for o in outcomes):
            return Outcome(Verdict.NOT_MET, reasons)
        if any(o.verdict is Verdict.UNKNOWN for o in outcomes):
            return Outcome(Verdict.UNKNOWN, reasons)
        return Outcome(Verdict.MET, reasons)

    def is_fully_parsed(self) -> bool:
        return all(child.is_fully_parsed() for child in self.children)


@dataclasses.dataclass(frozen=True)
class Any_(Node):
    children: tuple[Node, ...]

    def evaluate(self, record: AcademicRecord) -> Outcome:
        outcomes = [child.evaluate(record) for child in self.children]
        reasons = tuple(r for o in outcomes for r in o.reasons)
        if any(o.verdict is Verdict.MET for o in outcomes):
            return Outcome(Verdict.MET, reasons)
        if any(o.verdict is Verdict.UNKNOWN for o in outcomes):
            return Outcome(Verdict.UNKNOWN, reasons)
        return Outcome(Verdict.NOT_MET, reasons)

    def is_fully_parsed(self) -> bool:
        return all(child.is_fully_parsed() for child in self.children)


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------

_COURSE = re.compile(r"^([A-Z]{4})\s*(\d{4}[A-Z]?)$")
_COURSE_ANYWHERE = re.compile(r"\b([A-Z]{4})\s*(\d{4}[A-Z]?)\b")
_PRIOR_TO = re.compile(r"\(\s*prior to\s+([^)]*)\)", re.I)
_PROGRAM_SCOPE = re.compile(r"\(\s*For\b[^)]*\)", re.I)
_GRADE_CLAUSE = re.compile(
    r"^(?:a\s+)?(?:grade\s+)?(?P<grade>[A-D][+-]?|pass|passing)\s*(?:grade)?"
    r"(?:\s+or\s+above)?\s+in\s+(?P<targets>.+)$",
    re.I,
)
_LEVEL_CLAUSE = re.compile(r"^level\s+\d", re.I)
_EXTERNAL_HINT = re.compile(r"HKDSE|A-?Level|\bAL\b|IB\b|SAT\b", re.I)


def _normalise(text: str) -> str:
    text = text.replace("[", "(").replace("]", ")")
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(".")


def _split_top_level(text: str, separators: Sequence[str]) -> list[str] | None:
    """按括号深度 0 上的分隔符切分。没切到就返回 None。

    ``" or above"`` 里的 ``or`` 不是分隔符——那是成绩条件的一部分。
    把它当分隔符会把 `Grade A- or above in COMP 2012` 劈成两半，
    于是一条本来能判定的先修变成两段读不懂的碎片。
    """
    parts: list[str] = []
    depth = 0
    cursor = 0
    index = 0
    lowered = text.lower()
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
            index += 1
            continue
        if char == ")":
            depth -= 1
            index += 1
            continue
        if depth == 0:
            for separator in separators:
                if not lowered.startswith(separator, index):
                    continue
                after = index + len(separator)
                if separator.strip() == "or" and lowered[after:].lstrip().startswith("above"):
                    continue
                parts.append(text[cursor:index])
                cursor = after
                index = after
                break
            else:
                index += 1
                continue
            continue
        index += 1
    if not parts:
        return None
    parts.append(text[cursor:])
    return [p.strip() for p in parts if p.strip()]


def _strip_outer_parens(text: str) -> str:
    while text.startswith("(") and text.endswith(")"):
        depth = 0
        for index, char in enumerate(text):
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0 and index != len(text) - 1:
                    return text
        text = text[1:-1].strip()
    return text


def _parse_grade_clause(text: str) -> Node | None:
    match = _GRADE_CLAUSE.match(text)
    if match is None:
        return None
    grade = match.group("grade").upper()
    if grade in {"PASS", "PASSING"}:
        grade = "PASS"
    targets = match.group("targets").strip()

    # 目标里还含连接词或第二个成绩条件，说明这不是一个原子——交回上层去拆。
    # 硬吃下来会把 `Grade A in X AND Pass grade in Y` 压平成 `X OR Y`。
    if re.search(r"\band\b|\bor\b(?!\s+above)|grade\s", targets, re.I):
        return None

    if _EXTERNAL_HINT.search(targets) or not _COURSE_ANYWHERE.search(targets):
        return ExternalRequirement(text)

    codes = [f"{a} {b}" for a, b in _COURSE_ANYWHERE.findall(targets)]
    nodes: tuple[Node, ...] = tuple(
        CourseRequirement(course_id=code, min_grade=grade) for code in codes
    )
    return nodes[0] if len(nodes) == 1 else Any_(nodes)


def _parse_atom(text: str) -> Node:
    text = text.strip()
    if not text:
        return Empty()

    note = None
    prior = _PRIOR_TO.search(text)
    if prior is not None:
        note = f"prior to {prior.group(1).strip()}"
        text = _PRIOR_TO.sub("", text).strip()

    compact = re.sub(r"\s+", " ", text)
    course = _COURSE.match(compact.replace(" ", "")) or _COURSE.match(compact)
    if course is not None:
        return CourseRequirement(f"{course.group(1)} {course.group(2)}", note=note)

    graded = _parse_grade_clause(compact)
    if graded is not None:
        return graded

    if _LEVEL_CLAUSE.match(compact) or _EXTERNAL_HINT.search(compact):
        return ExternalRequirement(compact)

    return Unparsed(compact)


def _parse_expression(text: str) -> Node:
    text = _strip_outer_parens(_normalise(text))
    if not text:
        return Empty()

    if _PROGRAM_SCOPE.search(text):
        # 整条表达式带项目限定即整体不可判——不拆开，避免半条通过
        return ProgramScoped(text)

    # 分号是最外层的 OR
    semicolons = _split_top_level(text, (";",))
    if semicolons and len(semicolons) > 1:
        children = tuple(
            _parse_expression(re.sub(r"^(or|and)\s+", "", part, flags=re.I))
            for part in semicolons
        )
        return Any_(children)

    # 优先级由低到高：OR → AND → 成绩子句 → /
    #
    # 成绩子句**必须排在 OR/AND 之后**。曾经它排在最前面，于是
    #   (Grade A in COMP 1023) OR (Grade A in COMP 1021 AND Pass grade in COMP 1028)
    # 被整条当成一个成绩子句，里面所有课程代码被 `_COURSE_ANYWHERE` 一把捞出来接成
    # OR——嵌套的 AND 就这么消失了，只修了 COMP 1021 的学生被判成满足。
    # 那是把"不满足"判成"满足"，正是 T2 最怕的方向。
    #
    # `/` 排在 AND 之后，因为 `A / B AND C` 的人类读法是 `(A or B) and C`：
    # `/` 表示"这几门课等效，任选其一"，AND 表示"另一个要求槽位"。
    for separators, combinator in (
        ((" or ",), Any_),
        ((" and ",), All),
    ):
        parts = _split_top_level(text, separators)
        if parts and len(parts) > 1:
            cleaned = [re.sub(r"^(or|and)\s+", "", p, flags=re.I).strip() for p in parts]
            children = tuple(_parse_expression(p) for p in cleaned if p)
            if len(children) == 1:
                return children[0]
            return combinator(children)

    # 到这里，text 里已经没有顶层的 or/and，成绩子句可以安全地整条识别：
    # `Grade A- or above in COMP 2011 / COMP 2012 / COMP 2012H`
    graded = _parse_grade_clause(text)
    if graded is not None:
        return graded

    slashed = _split_top_level(text, ("/",))
    if slashed and len(slashed) > 1:
        children = tuple(_parse_expression(p) for p in slashed if p)
        if len(children) == 1:
            return children[0]
        return Any_(children)

    return _parse_atom(text)


def parse(expression: str | None) -> Node:
    """把先修表达式原文解析成 AST。永不抛异常——读不懂就是 :class:`Unparsed`。"""
    if expression is None or not expression.strip():
        return Empty()
    try:
        return _parse_expression(expression)
    except Exception:                                    # pragma: no cover - 兜底
        return Unparsed(expression.strip())


def evaluate(node: Node, record: AcademicRecord) -> Outcome:
    return node.evaluate(record)


def _grade_meets(actual: str, required: str) -> bool:
    actual = actual.strip().upper()
    required = required.strip().upper()
    if required == "PASS":
        return actual in _PASSING
    if actual in {"P", "PASS"}:
        # 及格制成绩无法与等第比较：调用方拿到的是 NOT_MET 而非静默放行
        return False
    if actual not in GRADE_ORDER or required not in GRADE_ORDER:
        return False
    return GRADE_ORDER.index(actual) <= GRADE_ORDER.index(required)


# --------------------------------------------------------------------------
# 覆盖率：把"解析能力"变成一个会退化就变红的数字
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class ParseCoverage:
    """两个比率，因为它们衡量的不是一回事。

    ``fully_parsed_ratio`` 回答"解析器有没有读懂结构"；
    ``actionable_ratio`` 回答"读懂之后能不能对某个学生给出 MET/NOT_MET"。

    只报前者会掩盖一种退化：解析器把什么都当成外部资历，
    于是每条都"解析成功"、每条都只能返回 UNKNOWN，而数字是 100%。
    """

    total: int
    fully_parsed: int
    actionable: int
    program_scoped: int
    external: int
    unparsed_samples: tuple[str, ...]

    @property
    def fully_parsed_ratio(self) -> float:
        return self.fully_parsed / self.total if self.total else 1.0

    @property
    def actionable_ratio(self) -> float:
        return self.actionable / self.total if self.total else 1.0


def _is_actionable(node: Node) -> bool:
    """该节点对某个学生是否可能给出 MET 或 NOT_MET（而非恒为 UNKNOWN）。"""
    if isinstance(node, (ExternalRequirement, ProgramScoped, Unparsed)):
        return False
    if isinstance(node, Any_):
        return any(_is_actionable(child) for child in node.children)
    if isinstance(node, All):
        return all(_is_actionable(child) for child in node.children)
    return True


def parse_coverage(expressions: Iterable[str]) -> ParseCoverage:
    total = 0
    fully = 0
    actionable = 0
    scoped = 0
    external = 0
    samples: list[str] = []
    for expression in expressions:
        total += 1
        node = parse(expression)
        if isinstance(node, ProgramScoped):
            scoped += 1
        if isinstance(node, ExternalRequirement):
            external += 1
        if _is_actionable(node):
            actionable += 1
        if node.is_fully_parsed():
            fully += 1
        elif len(samples) < 10:
            samples.append(expression)
    return ParseCoverage(
        total=total,
        fully_parsed=fully,
        actionable=actionable,
        program_scoped=scoped,
        external=external,
        unparsed_samples=tuple(samples),
    )
