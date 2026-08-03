"""ADK Workflow Agent 的四处用法（Spec §8.1 表 S1–S3 + A0 的 SequentialAgent）。

D2 要求"四种用法各有一份 trace 证据"。所以这里不是把 ADK 的类包一层，
而是把**每种用法的不变式**写成可执行的东西：

| # | 位置 | 构件 | 不变式 |
|---|---|---|---|
| S1 | A5 内部 | `ParallelAgent` | 三套约束强度各自独立推理，互不看对方的中间结果 |
| S2 | A5 内部 | `LoopAgent(max=3)` | 违反容量/保护区块/先修就带着原因重生成；**循环退出时必然无违规，否则失败** |
| S3 | A4 内部 | `ParallelAgent` | 每个来源在独立子上下文里抽取，一个来源的注入污染不了另一个 |
| A0 | 固定流水线 | `SequentialAgent` | context → gap → match → plan 的顺序确定 |

S2 的不变式是这里最要紧的一条：Spec 说它让
``Capacity Violation = 0`` 与 ``Protected Block Violation = 0``
"成为循环不变式而非期望值"。循环跑完仍有违规就**抛异常**，不是返回最后一版。
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Generic, Iterable, Sequence, TypeVar

from campuspath_contracts.academic import CoursePlanVariant

T = TypeVar("T")

#: Spec §8.1 S2：`LoopAgent(max_iterations=3)`。
MAX_REPAIR_ITERATIONS = 3


class ConstraintRepairFailed(RuntimeError):
    """循环用尽仍有违规。**不返回最后一版**——那一版是违规的。"""

    def __init__(self, iterations: int, violations: Sequence[str]) -> None:
        self.iterations = iterations
        self.violations = tuple(violations)
        super().__init__(
            f"{iterations} 轮修复后仍有 {len(violations)} 项违规，拒绝输出：\n  "
            + "\n  ".join(violations)
        )


class CrossContaminated(RuntimeError):
    """S3：一个来源的内容出现在了另一个来源的抽取结果里。"""


@dataclasses.dataclass(frozen=True)
class ParallelOutcome(Generic[T]):
    """S1/S3 的产物。逐个记录，便于对照 trace。"""

    results: tuple[T, ...]
    labels: tuple[str, ...]

    def by_label(self, label: str) -> T:
        return self.results[self.labels.index(label)]


def run_parallel_variants(
    generate: Callable[[CoursePlanVariant], T],
    variants: Sequence[CoursePlanVariant] = (
        CoursePlanVariant.BALANCED,
        CoursePlanVariant.AMBITIOUS,
        CoursePlanVariant.LOW_LOAD,
    ),
) -> ParallelOutcome[T]:
    """**S1**：Plan A/B/C 在三套不同强度约束下并行生成。

    每个变体拿到的只有自己的约束——不传其他变体的中间结果。
    Spec 的措辞是"每套方案获得独立且专注的推理"；共享上下文会让三套方案
    互相看齐，最后变成同一个方案的三种措辞。
    """
    return ParallelOutcome(
        results=tuple(generate(variant) for variant in variants),
        labels=tuple(variant.value for variant in variants),
    )


def run_repair_loop(
    generate: Callable[[tuple[str, ...]], T],
    validate: Callable[[T], Sequence[str]],
    *,
    max_iterations: int = MAX_REPAIR_ITERATIONS,
) -> tuple[T, int]:
    """**S2**：生成 → Rules 校验 → 带着违规原因重生成。

    返回 ``(通过校验的产物, 用了几轮)``。用尽仍违规则抛
    :class:`ConstraintRepairFailed`——这正是让 B1/B2 成为**不变式**的地方：
    退出这个函数的产物一定是校验通过的，否则根本没有产物。

    ``generate`` 拿到上一轮的违规原因，不是拿到"重试一次"。
    没有原因的重试只是换个随机种子。
    """
    reasons: tuple[str, ...] = ()
    candidate: T | None = None
    for attempt in range(1, max_iterations + 1):
        candidate = generate(reasons)
        violations = tuple(validate(candidate))
        if not violations:
            return candidate, attempt
        reasons = violations
    raise ConstraintRepairFailed(max_iterations, reasons)


@dataclasses.dataclass(frozen=True)
class SourceExtraction(Generic[T]):
    source_id: str
    result: T


def run_isolated_extraction(
    sources: Sequence[tuple[str, str]],
    extract: Callable[[str, str], T],
    *,
    contamination_check: Callable[[T, str], bool] | None = None,
) -> tuple[SourceExtraction[T], ...]:
    """**S3**：多来源并行抽取，每个来源在**独立子上下文**里。

    ``sources`` 是 ``(source_id, 原始内容)``。``extract`` 每次只拿到一个来源的
    内容——签名上就传不进第二个来源，所以"一个来源的注入污染另一个"
    在这一层做不到（Spec §8.9.1 第 1 条）。

    ``contamination_check`` 是额外一道：抽取结果里出现了别的来源的特征串就报错。
    结构上做不到的事情仍然值得检查一次——防的是日后有人给 extract 加个全局缓存。
    """
    outcomes: list[SourceExtraction[T]] = []
    for source_id, content in sources:
        result = extract(source_id, content)
        outcomes.append(SourceExtraction(source_id, result))

    if contamination_check is not None:
        for outcome in outcomes:
            for other_id, other_content in sources:
                if other_id == outcome.source_id:
                    continue
                if contamination_check(outcome.result, other_content):
                    raise CrossContaminated(
                        f"{outcome.source_id} 的抽取结果里出现了 {other_id} 的内容"
                    )
    return tuple(outcomes)


@dataclasses.dataclass(frozen=True)
class Step(Generic[T]):
    name: str
    run: Callable[[dict[str, object]], T]


def run_sequential(steps: Sequence[Step], initial: dict[str, object] | None = None
                   ) -> dict[str, object]:
    """**A0 的固定流水线**：context → gap → match → plan。

    用 `SequentialAgent` 表达是为了**顺序确定性**（Spec §8.1）：
    已知意图不该每次都让模型重新决定先做什么。
    每一步的产物按名字进上下文，后一步能读到前一步的结果。
    """
    state: dict[str, object] = dict(initial or {})
    for step in steps:
        state[step.name] = step.run(state)
    return state


#: A0 确定性路由表命中时的标准流水线（Spec §8.8 推荐执行顺序）。
DEFAULT_PIPELINE = ("context", "gap", "match", "plan")
