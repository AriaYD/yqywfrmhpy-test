"""评测共享的重对象：Seed 与 API 客户端。

两者都**只建一次**：Seed 构建要读 1500 门课，13 条 BLOCKER 各建一次
会把评测拖成分钟级；而 D6.7 要求两次跑数字一致，共享同一个实例
也顺带保证了它们看到的是同一份数据。
"""

from __future__ import annotations

import functools
from typing import Any


@functools.cache
def seed_bundle() -> dict[str, Any]:
    from campuspath_seed.build import build_seed

    return build_seed("full")


@functools.cache
def _deps():
    from campuspath_api.app import Deps

    # model=None：**评测不调模型**。13 条 BLOCKER 全是结构性的，
    # 依赖模型的端点会返回 503，而那正是它们此刻的真实状态。
    return Deps("full", model=None)


@functools.cache
def api_client():
    from fastapi.testclient import TestClient

    from campuspath_api.app import create_app

    return TestClient(create_app(_deps()))
