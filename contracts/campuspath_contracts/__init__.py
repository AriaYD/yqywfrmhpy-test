"""CampusPath 契约层（WP1）。

**唯一的 Schema 真相来源。** 前端类型、Agent 输出校验、Mock 服务、评测断言
全部从这里生成或导入——Plan WP1 验收条款要求"前后端、Agent、Mock 服务全部从
同一份 Schema 生成类型"。

本包**不得 import 任何模型 SDK**（B11/B12）。确定性服务平面会 import 它，
一旦这里混进 SDK，Rules / Capacity / Wellbeing 三个模块的零 LLM 断言就一起失效。
"""

from __future__ import annotations

from pydantic import BaseModel

from . import (
    academic,
    advising,
    agents,
    aggregation,
    calendar,
    common,
    goals,
    guards,
    memory,
    opportunity,
    packs,
    pathway,
    profile,
    publishing,
    reflection,
    validation,
    wellbeing,
)
from .common import CONTRACTS_VERSION

__all__ = [
    "CONTRACTS_VERSION",
    "ROOT_MODELS",
    "academic",
    "agents",
    "aggregation",
    "calendar",
    "common",
    "goals",
    "guards",
    "memory",
    "opportunity",
    "packs",
    "pathway",
    "profile",
    "publishing",
    "reflection",
    "validation",
    "wellbeing",
]

_MODULES = (
    academic,
    advising,
    agents,
    aggregation,
    calendar,
    goals,
    memory,
    opportunity,
    packs,
    pathway,
    profile,
    publishing,
    reflection,
    validation,
    wellbeing,
)


def _collect_root_models() -> dict[str, type[BaseModel]]:
    """收集所有对外契约模型，供 Schema 导出与"是否有模型漏了测试"的检查使用。"""
    found: dict[str, type[BaseModel]] = {}
    for module in _MODULES:
        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name)
            if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel:
                if obj.__module__.startswith("campuspath_contracts."):
                    found[name] = obj
    # 基类不是契约本身
    for base in ("CampusPathModel", "FrozenModel"):
        found.pop(base, None)
    return dict(sorted(found.items()))


#: 名称 → 模型类。导出 JSON Schema 与契约测试都遍历它。
ROOT_MODELS: dict[str, type[BaseModel]] = _collect_root_models()
