"""D2 安全契约：工具白名单、A4 隔离、Vertex-only 运行时守卫。

这些断言的价值在于**不需要调用模型**就能跑。安全边界如果只有在
真的发一次请求时才成立，就没法在每次提交时验证它。
"""

from __future__ import annotations

import pytest

from campuspath_contracts.agents import (
    AGENT_TOOL_WHITELIST,
    AGENT_WRITE_DOMAINS,
    A4_TOOL_WHITELIST,
    ToolPermissionError,
)
from campuspath_contracts.common import AgentId, DataDomain

from campuspath_agents.tools import ToolBelt, belt_for, unequipped_whitelist_entries
from campuspath_agents.vertex import (
    API_KEY_ENVS,
    USE_VERTEX_ENV,
    AIStudioPathBlocked,
    assert_vertex_only,
    check_environment,
)

VERTEX_ENV = {
    USE_VERTEX_ENV: "TRUE",
    "GOOGLE_CLOUD_PROJECT": "keen-opus-498918-m8",
    "GOOGLE_CLOUD_LOCATION": "us-central1",
}


# ── B12 运行时守卫 ────────────────────────────────────────────────


def test_correct_vertex_environment_passes():
    assert check_environment(VERTEX_ENV) == []
    assert_vertex_only(VERTEX_ENV)


def test_missing_use_vertexai_is_blocked():
    """一行 Python 都不用改，删掉这个变量账单就从赠金转到个人卡。"""
    env = {k: v for k, v in VERTEX_ENV.items() if k != USE_VERTEX_ENV}
    with pytest.raises(AIStudioPathBlocked) as excinfo:
        assert_vertex_only(env)
    assert USE_VERTEX_ENV in str(excinfo.value)


@pytest.mark.parametrize("value", ["", "false", "0", "no", "FALSE"])
def test_falsy_use_vertexai_is_blocked(value):
    with pytest.raises(AIStudioPathBlocked):
        assert_vertex_only({**VERTEX_ENV, USE_VERTEX_ENV: value})


@pytest.mark.parametrize("name", API_KEY_ENVS)
def test_any_api_key_is_blocked(name):
    """Vertex 走 ADC，不需要任何 API key。出现 key 就是有人在走另一条路。"""
    with pytest.raises(AIStudioPathBlocked) as excinfo:
        assert_vertex_only({**VERTEX_ENV, name: "not-a-real-key"})
    assert name in str(excinfo.value)


@pytest.mark.parametrize("name", ["GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION"])
def test_missing_vertex_settings_are_blocked(name):
    """缺了会在第一次调用时才报错——那时候已经在 Demo 现场了。"""
    env = {k: v for k, v in VERTEX_ENV.items() if k != name}
    with pytest.raises(AIStudioPathBlocked):
        assert_vertex_only(env)


def test_all_problems_are_reported_at_once():
    """一次说完，不要修一个再报下一个。"""
    problems = check_environment({API_KEY_ENVS[0]: "x"})
    assert len(problems) >= 3


# ── 工具白名单 ────────────────────────────────────────────────────


def _noop(**_kwargs):
    return None


def test_a4_belt_has_exactly_two_tools():
    belt = belt_for(AgentId.A4_OPPORTUNITY,
                    {"read_source": _noop, "emit_opportunity_draft": _noop})
    assert belt.available == A4_TOOL_WHITELIST


@pytest.mark.parametrize(
    "tool",
    ["read_student_state", "read_profile", "read_calendar", "publish_opportunity",
     "write_catalog", "send_email", "http_post"],
)
def test_a4_cannot_be_equipped_with_forbidden_tools(tool):
    """注册时就拒绝：模型即使被完全劫持，也调不到不存在的东西。"""
    with pytest.raises(ToolPermissionError):
        belt_for(AgentId.A4_OPPORTUNITY, {tool: _noop})


def test_calling_an_unequipped_tool_is_refused_and_logged():
    belt = belt_for(AgentId.A4_OPPORTUNITY, {"read_source": _noop})
    with pytest.raises(ToolPermissionError):
        belt.call("emit_opportunity_draft")
    assert belt.call_log[-1].accepted is False


def test_whitelist_is_rechecked_at_call_time():
    """防的是日后有人往 belt 里塞一个方法而忘了改白名单。"""
    belt = ToolBelt(AgentId.A4_OPPORTUNITY)
    belt._tools["read_student_state"] = _noop        # 绕过 register
    with pytest.raises(ToolPermissionError):
        belt.call("read_student_state")


def test_successful_calls_are_logged_for_governance():
    """D2 要求 Agent 治理证据。审计从 call_log 来。"""
    belt = belt_for(AgentId.A4_OPPORTUNITY, {"read_source": _noop})
    belt.call("read_source", url="https://example.invalid/x")
    assert belt.call_log[-1].accepted is True
    assert belt.call_log[-1].tool_name == "read_source"


def test_a1_cannot_be_equipped_to_write_insights():
    """§8.9.2：A1 没有任何写入 Aggregated Insights 的工具权限。"""
    for tool in ("write_aggregate", "write_insights"):
        with pytest.raises(ToolPermissionError):
            belt_for(AgentId.A1_STUDENT_CONTEXT, {tool: _noop})


@pytest.mark.parametrize("agent", list(AgentId))
def test_no_agent_can_be_equipped_with_private_reflection_tools(agent):
    """§8.9.2 的类型隔离前提是"没人把 Reflection 原文工具递给别的 Agent"。"""
    for tool in ("read_reflection_private_text", "read_calendar_event_titles"):
        with pytest.raises(ToolPermissionError):
            belt_for(agent, {tool: _noop})


def test_unequipped_whitelist_entries_are_visible():
    """分阶段实现会有缺口，但缺口应当可见——
    否则"A5 能调 validate_constraints"会在没人发现时变成不能。"""
    belt = belt_for(AgentId.A5_PATHWAY, {"validate_constraints": _noop})
    missing = unequipped_whitelist_entries(belt)
    assert "emit_pathway_version" in missing
    assert "validate_constraints" not in missing


def test_write_domains_still_exclude_aggregated_insights():
    for agent, domains in AGENT_WRITE_DOMAINS.items():
        assert DataDomain.AGGREGATED_INSIGHTS not in domains, agent.value
