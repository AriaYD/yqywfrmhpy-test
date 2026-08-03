"""D2 安全契约测试：Agent 工具白名单、Runtime 隔离与写权限域（Spec §8.9）。

这些断言的价值在于它们**可以在没有任何 Agent 实现的情况下失败**。
WP6 写 Agent 时必须从这三张表取工具集合，而不是自己再列一份。
"""

from __future__ import annotations

import pytest

from campuspath_contracts.agents import (
    A4_TOOL_WHITELIST,
    AGENT_RUNTIME,
    AGENT_TOOL_WHITELIST,
    AGENT_WRITE_DOMAINS,
    FORBIDDEN_TOOL_PATTERNS,
    AgentCall,
    IntentId,
    ToolPermissionError,
    WorkflowKind,
    WorkflowPlan,
    assert_tool_allowed,
)
from campuspath_contracts.common import AgentId, DataDomain, RuntimeId

from conftest import NOW


def test_exactly_six_agents():
    """Spec §8.1：6 个语义 Agent。加第 7 个要先改 Spec。"""
    assert len(AgentId) == 6
    assert set(AGENT_RUNTIME) == set(AgentId)
    assert set(AGENT_TOOL_WHITELIST) == set(AgentId)
    assert set(AGENT_WRITE_DOMAINS) == set(AgentId)


def test_exactly_two_runtimes_and_a4_is_alone():
    assert len(RuntimeId) == 2
    ops = [a for a, r in AGENT_RUNTIME.items() if r is RuntimeId.OPPORTUNITY_OPS]
    assert ops == [AgentId.A4_OPPORTUNITY], "A4 独立部署是安全边界，不是性能优化"


def test_a4_has_exactly_two_tools():
    """Spec §8.9.1 第 2 条。"""
    assert A4_TOOL_WHITELIST == {"read_source", "emit_opportunity_draft"}
    assert AGENT_TOOL_WHITELIST[AgentId.A4_OPPORTUNITY] == A4_TOOL_WHITELIST


@pytest.mark.parametrize(
    "tool",
    [
        "read_student_state",
        "read_profile",
        "read_calendar",
        "read_wellbeing_signal",
        "publish_opportunity",
        "write_catalog",
        "send_email",
        "http_post",
    ],
)
def test_a4_cannot_call_student_or_publishing_tools(tool):
    """已知会失败的样例集：A4 被要求调用它不该有的工具。"""
    with pytest.raises(ToolPermissionError):
        assert_tool_allowed(AgentId.A4_OPPORTUNITY, tool)


def test_forbidden_patterns_do_not_intersect_whitelists():
    """禁止清单与白名单必须互斥，否则两张表在打架。"""
    for agent, patterns in FORBIDDEN_TOOL_PATTERNS.items():
        allowed = AGENT_TOOL_WHITELIST[agent]
        for tool in allowed:
            for pattern in patterns:
                assert not tool.startswith(pattern), f"{agent.value} 的白名单里有 {tool}"


def test_no_agent_can_write_aggregated_insights():
    """Spec §8.9.2：只有确定性的 Aggregation Service 能写聚合域。"""
    for agent, domains in AGENT_WRITE_DOMAINS.items():
        assert DataDomain.AGGREGATED_INSIGHTS not in domains, agent.value


def test_a4_has_no_write_domain_at_all():
    assert AGENT_WRITE_DOMAINS[AgentId.A4_OPPORTUNITY] == frozenset()


def test_no_agent_writes_the_wellbeing_or_calendar_domain():
    """Wellbeing 判定归 Rules，日历归 Capacity Service——都不是 Agent 的写域。"""
    for agent, domains in AGENT_WRITE_DOMAINS.items():
        assert DataDomain.WELLBEING not in domains, agent.value
        assert DataDomain.CALENDAR not in domains, agent.value


def test_a1_cannot_write_insights_tools():
    for tool in ("write_aggregate", "write_insights"):
        with pytest.raises(ToolPermissionError):
            assert_tool_allowed(AgentId.A1_STUDENT_CONTEXT, tool)


def test_a5_can_validate_constraints():
    """A5 必须能调 Rules——否则它拿不到 validation_id。"""
    assert_tool_allowed(AgentId.A5_PATHWAY, "validate_constraints")


# --------------------------------------------------------------------------
# 编排契约
# --------------------------------------------------------------------------


def test_agent_call_rejects_tool_outside_whitelist():
    with pytest.raises(Exception) as excinfo:
        AgentCall(call_id="C-1", agent=AgentId.A4_OPPORTUNITY, tool_name="read_student_state")
    assert "read_student_state" in str(excinfo.value)


def test_deterministic_route_requires_an_intent():
    with pytest.raises(Exception):
        WorkflowPlan(
            plan_id="WF-1",
            student_id="S-001",
            kind=WorkflowKind.DETERMINISTIC_ROUTE,
            calls=(AgentCall(call_id="C-1", agent=AgentId.A3_GOAL_GAP),),
            created_at=NOW,
        )


def test_valid_deterministic_plan():
    plan = WorkflowPlan(
        plan_id="WF-2",
        student_id="S-001",
        kind=WorkflowKind.DETERMINISTIC_ROUTE,
        intent=IntentId.PLAN_COURSES,
        calls=(
            AgentCall(call_id="C-1", agent=AgentId.A2_ACADEMIC, parallel_group="facts"),
            AgentCall(call_id="C-2", agent=AgentId.A3_GOAL_GAP, parallel_group="facts"),
            AgentCall(call_id="C-3", agent=AgentId.A5_PATHWAY, depends_on=("C-1", "C-2")),
        ),
        created_at=NOW,
    )
    assert plan.intent is IntentId.PLAN_COURSES


def test_plan_rejects_dangling_dependency():
    with pytest.raises(Exception):
        WorkflowPlan(
            plan_id="WF-3",
            student_id="S-001",
            kind=WorkflowKind.LLM_COMPOSED,
            calls=(AgentCall(call_id="C-1", agent=AgentId.A5_PATHWAY, depends_on=("C-missing",)),),
            created_at=NOW,
        )


def test_response_envelope_always_marks_synthetic_data():
    """D1 要求全站 `Synthetic / Demo Data` 标记，做成类型上关不掉。"""
    from pydantic import ValidationError

    from campuspath_contracts.agents import ResponseEnvelope
    from campuspath_contracts.common import Locale

    envelope = ResponseEnvelope(
        envelope_id="E-1",
        student_id="S-001",
        locale=Locale.EN,
        payload_type="MatchResult[]",
        generated_at=NOW,
    )
    assert envelope.synthetic_data_notice is True
    with pytest.raises(ValidationError):
        ResponseEnvelope(
            envelope_id="E-2",
            student_id="S-001",
            locale=Locale.EN,
            payload_type="MatchResult[]",
            synthetic_data_notice=False,
            generated_at=NOW,
        )
