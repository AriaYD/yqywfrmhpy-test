"""确定性随机：按命名空间派生子流。

为什么不用一个全局 ``random.Random(SEED)``：那样"给机会表多加一条"会让后面
所有表的取值整体错位，Gold Label 全部作废。按命名空间派生后，
改动只影响它自己的那条流。

用法::

    rng = stream("opportunities.internships")
    rng.choice(sorted(candidates))    # 注意：先排序，再交给 rng
"""

from __future__ import annotations

import hashlib
import random
from typing import Iterable, Sequence, TypeVar

from .config import MASTER_SEED

T = TypeVar("T")


def derive_seed(namespace: str) -> int:
    """由命名空间派生稳定种子。同名必同种子，跨机器、跨 Python 版本一致。

    不用内置 ``hash()``：它带 ``PYTHONHASHSEED`` 随机化，跨进程就变了。
    """
    digest = hashlib.sha256(f"{MASTER_SEED}:{namespace}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def stream(namespace: str) -> random.Random:
    return random.Random(derive_seed(namespace))


def pick(rng: random.Random, items: Iterable[T]) -> T:
    """从可迭代对象里取一个。**先排序**，避免 set/dict 的迭代序污染确定性。"""
    ordered = _ordered(items)
    if not ordered:
        raise ValueError("pick 收到空集合")
    return ordered[rng.randrange(len(ordered))]


def sample(rng: random.Random, items: Iterable[T], k: int) -> list[T]:
    ordered = _ordered(items)
    k = min(k, len(ordered))
    return rng.sample(ordered, k)


def shuffled(rng: random.Random, items: Iterable[T]) -> list[T]:
    ordered = _ordered(items)
    rng.shuffle(ordered)
    return ordered


def weighted(rng: random.Random, choices: Sequence[tuple[T, float]]) -> T:
    """按权重取一个。``choices`` 必须已排序，否则相同权重下结果不稳定。"""
    total = sum(w for _, w in choices)
    threshold = rng.random() * total
    running = 0.0
    for value, weight in choices:
        running += weight
        if running >= threshold:
            return value
    return choices[-1][0]


def _ordered(items: Iterable[T]) -> list[T]:
    materialised = list(items)
    if isinstance(items, (set, frozenset)):
        return sorted(materialised, key=_sort_key)
    return materialised


def _sort_key(value: object) -> str:
    return repr(value)
