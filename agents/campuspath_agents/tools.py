"""工具白名单的**运行时**强制（Spec §8.9.1、D2 安全契约测试）。

契约层的 `AGENT_TOOL_WHITELIST` 是一张表；表本身不会阻止任何事。
这里让它变成闸门：Agent 拿到的是 :class:`ToolBelt`，
belt 里根本没有白名单之外的函数，而且每次调用都再查一次。

为什么两道都要：

* **没有那个函数** —— 模型即使被完全注入劫持，也调不到不存在的东西；
* **调用时再查** —— 防的是有人日后往 belt 里塞一个方法而忘了改白名单。

威胁模型（Spec §8.9.1 末）：即使 A4 被完全劫持，它能造成的最大影响是
"提交一条会被人工审核拒绝的草稿"。这条结论成立的前提就是 belt 里
只有 ``read_source`` 与 ``emit_opportunity_draft``。
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable

from campuspath_contracts.agents import (
    AGENT_TOOL_WHITELIST,
    FORBIDDEN_TOOL_PATTERNS,
    ToolPermissionError,
    assert_tool_allowed,
)
from campuspath_contracts.common import AgentId


@dataclasses.dataclass(frozen=True)
class ToolCall:
    """一次工具调用的审计记录。D2 的治理证据从这里来。"""

    agent: AgentId
    tool_name: str
    accepted: bool
    detail: str = ""


class ToolBelt:
    """一个 Agent 能用的全部工具。**注册时就查白名单。**"""

    def __init__(self, agent: AgentId) -> None:
        self.agent = agent
        self._tools: dict[str, Callable[..., Any]] = {}
        self._log: list[ToolCall] = []

    def register(self, name: str, fn: Callable[..., Any]) -> None:
        assert_tool_allowed(self.agent, name)
        for pattern in FORBIDDEN_TOOL_PATTERNS.get(self.agent, frozenset()):
            if name.startswith(pattern):
                raise ToolPermissionError(
                    f"{self.agent.value} 的禁止清单命中 {pattern!r}：{name}"
                )
        self._tools[name] = fn

    @property
    def available(self) -> frozenset[str]:
        return frozenset(self._tools)

    @property
    def call_log(self) -> tuple[ToolCall, ...]:
        return tuple(self._log)

    def call(self, name: str, /, **kwargs: Any) -> Any:
        """调用一个工具。**每次都重新查白名单**，不信任注册时的判断。"""
        try:
            assert_tool_allowed(self.agent, name)
        except ToolPermissionError as exc:
            self._log.append(ToolCall(self.agent, name, False, str(exc)))
            raise
        fn = self._tools.get(name)
        if fn is None:
            self._log.append(ToolCall(self.agent, name, False, "工具未注册"))
            raise ToolPermissionError(
                f"{self.agent.value} 没有装备工具 {name!r}；"
                f"已装备：{sorted(self._tools)}"
            )
        self._log.append(ToolCall(self.agent, name, True))
        return fn(**kwargs)


def belt_for(agent: AgentId, tools: dict[str, Callable[..., Any]]) -> ToolBelt:
    """按白名单装备一个 Agent。传入白名单之外的工具会当场报错。"""
    belt = ToolBelt(agent)
    for name, fn in sorted(tools.items()):
        belt.register(name, fn)
    return belt


def unequipped_whitelist_entries(belt: ToolBelt) -> frozenset[str]:
    """白名单里有、但没装备的工具。

    不是错误——分阶段实现时本来就会有缺口。但它应该**可见**，
    否则"A5 能调 validate_constraints"会在没人发现的情况下变成不能。
    """
    return AGENT_TOOL_WHITELIST[belt.agent] - belt.available
