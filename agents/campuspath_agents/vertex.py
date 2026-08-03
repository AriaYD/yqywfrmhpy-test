"""B12 的**运行时**那一半：确保模型调用真的走 Vertex。

源码扫描（`scripts/check_ai_studio.py`）看得见带 api_key 的 client 构造，  # ai-studio-denylist
看不见这个：

    ADK 与 google-genai 通过**环境变量**选后端。
    `GOOGLE_GENAI_USE_VERTEXAI` 没设或为 false 时，默认走 AI Studio，
    并从 API key 环境变量取密钥（见 API_KEY_ENVS）。

也就是说，一行 Python 都不用改，把一个环境变量删掉，账单就从赠金转到个人信用卡。
CLAUDE.md 写的是"代码中禁止"，但这条路径根本不经过代码。

所以每个 Agent 构造时都调用 :func:`assert_vertex_only`。**不是启动时检查一次**——
环境变量可以在进程运行中被改（测试、脚本、Cloud Run 的 revision 切换），
而构造 Agent 正是即将要花钱的那一刻。
"""

from __future__ import annotations

import dataclasses
import os

#: 必须为真，否则 google-genai 走 AI Studio。
USE_VERTEX_ENV = "GOOGLE_GENAI_USE_VERTEXAI"

#: 出现任何一个都说明有人准备用 API key 认证——那是 AI Studio 的方式。
API_KEY_ENVS = ("GOOGLE_API_KEY", "GEMINI_API_KEY")  # ai-studio-denylist

#: Vertex 必需的两项。缺了会在第一次调用时才报错，那时候已经在 Demo 现场了。
REQUIRED_VERTEX_ENVS = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")

_TRUTHY = {"1", "true", "yes", "on"}


class AIStudioPathBlocked(RuntimeError):
    """当前环境会让模型调用走 AI Studio。赠金不覆盖，直扣个人信用卡。"""


@dataclasses.dataclass(frozen=True)
class VertexConfig:
    project: str
    location: str

    @property
    def as_env(self) -> dict[str, str]:
        return {
            USE_VERTEX_ENV: "TRUE",
            "GOOGLE_CLOUD_PROJECT": self.project,
            "GOOGLE_CLOUD_LOCATION": self.location,
        }


def check_environment(env: dict[str, str] | None = None) -> list[str]:
    """返回环境里所有会导致走 AI Studio 的问题。空列表表示可以调模型。

    单独抽出来是为了能在测试里喂各种环境组合——
    直接读 ``os.environ`` 的检查器只能在真实环境下被验证一次。
    """
    env = os.environ if env is None else env
    problems: list[str] = []

    if str(env.get(USE_VERTEX_ENV, "")).strip().lower() not in _TRUTHY:
        problems.append(
            f"{USE_VERTEX_ENV} 未设为真——google-genai 会默认走 AI Studio，"
            "赠金不覆盖那条路径"
        )
    for name in API_KEY_ENVS:
        if env.get(name):
            problems.append(
                f"{name} 已设置——那是 AI Studio 的认证方式。"
                "Vertex 走 ADC，不需要任何 API key"
            )
    for name in REQUIRED_VERTEX_ENVS:
        if not env.get(name):
            problems.append(f"{name} 未设置，Vertex 调用会在运行时失败")
    return problems


def assert_vertex_only(env: dict[str, str] | None = None) -> None:
    """构造 Agent 前调用。有任何问题就拒绝构造。

    宁可在这里炸掉，也不要跑起来之后才发现钱扣在了别处——
    赠金 2026-09-27 过期，误扣是不可逆的。
    """
    problems = check_environment(env)
    if problems:
        raise AIStudioPathBlocked(
            "拒绝构造 Agent，当前环境会让模型调用走 AI Studio（见 CLAUDE.md）：\n  - "
            + "\n  - ".join(problems)
        )


def vertex_config(env: dict[str, str] | None = None) -> VertexConfig:
    assert_vertex_only(env)
    env = os.environ if env is None else env
    return VertexConfig(
        project=env["GOOGLE_CLOUD_PROJECT"], location=env["GOOGLE_CLOUD_LOCATION"]
    )
