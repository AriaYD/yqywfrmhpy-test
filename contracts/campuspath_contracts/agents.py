"""A0–A5 的编排契约与**治理表**（Spec §8.1、§8.9）。

本模块最重要的东西不是那几个 Envelope 模型，而是三张表：

* :data:`AGENT_RUNTIME` —— 哪个 Agent 部署在哪个 Runtime（A4 单独隔离是安全边界）；
* :data:`AGENT_TOOL_WHITELIST` —— 哪个 Agent 能调哪些工具；
* :data:`AGENT_WRITE_DOMAINS` —— 哪个 Agent 能往哪个数据域写。

D2 的"安全契约测试"直接遍历这三张表。把它们放在契约层而不是各 Agent 的实现里，
是为了让"A4 有没有拿到学生数据工具"这件事**可以被一行断言检查**，
而不是靠人去读六个 Agent 的初始化代码。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .common import (
    AgentId,
    CampusPathModel,
    DataDomain,
    Identifier,
    Locale,
    LocalizedText,
    RuntimeId,
    StrEnum,
    StudentId,
)

# --------------------------------------------------------------------------
# 治理表
# --------------------------------------------------------------------------

AGENT_RUNTIME: dict[AgentId, RuntimeId] = {
    AgentId.A0_ORCHESTRATOR: RuntimeId.STUDENT_PATH,
    AgentId.A1_STUDENT_CONTEXT: RuntimeId.STUDENT_PATH,
    AgentId.A2_ACADEMIC: RuntimeId.STUDENT_PATH,
    AgentId.A3_GOAL_GAP: RuntimeId.STUDENT_PATH,
    AgentId.A4_OPPORTUNITY: RuntimeId.OPPORTUNITY_OPS,
    AgentId.A5_PATHWAY: RuntimeId.STUDENT_PATH,
}

#: Spec §8.9.1：A4 只有两个工具。**没有**学生数据读取、**没有**发布、
#: **没有** Catalog 写入、**没有**出网写请求。
A4_TOOL_WHITELIST = frozenset({"read_source", "emit_opportunity_draft"})

AGENT_TOOL_WHITELIST: dict[AgentId, frozenset[str]] = {
    AgentId.A0_ORCHESTRATOR: frozenset(
        {"call_agent", "load_pack", "emit_response", "request_clarification",
         "invoke_crisis_protocol"}
    ),
    AgentId.A1_STUDENT_CONTEXT: frozenset(
        {"read_student_state", "emit_profile_proposal", "emit_memory_proposal",
         "recall_memory", "emit_reflection_result", "emit_quality_feedback"}
    ),
    AgentId.A2_ACADEMIC: frozenset(
        {"read_sis", "read_lms", "read_course_catalog", "read_timetable",
         "read_degree_audit", "emit_academic_state", "emit_course_candidates"}
    ),
    AgentId.A3_GOAL_GAP: frozenset(
        {"read_student_state", "read_academic_state", "read_pack",
         "emit_requirement_graph", "emit_gap_map"}
    ),
    AgentId.A4_OPPORTUNITY: A4_TOOL_WHITELIST,
    AgentId.A5_PATHWAY: frozenset(
        {"read_student_state", "read_academic_state", "read_gap_map",
         "read_capacity_snapshot", "read_wellbeing_signal", "read_catalog",
         "validate_constraints", "emit_match_result", "emit_course_plan",
         "emit_pathway_version", "emit_schedule_proposal"}
    ),
}

#: 明确禁止的工具名前缀。写成"禁止清单"是为了让新增工具时的疏忽也能被抓到：
#: 只查白名单，漏掉的是"白名单里多了一个不该有的"；这里查的是"绝不该出现的形状"。
#: 覆盖**全部六个** Agent。此前只有 A4 与 A1 有清单，于是给 A5 的白名单加一个
#: ``read_reflection_private_text`` 或 ``read_calendar_event_titles``，
#: 没有任何测试会红——而 §8.9.2 的类型隔离前提正是"没人把 Reflection 原文
#: 工具递给 A5"。
_NEVER_FOR_ANY_AGENT = frozenset(
    {"read_reflection_private_text", "read_calendar_event_titles",
     "read_calendar_attendees", "write_insights", "write_aggregate",
     "read_outreach", "read_wellbeing_raw"}
)

FORBIDDEN_TOOL_PATTERNS: dict[AgentId, frozenset[str]] = {
    AgentId.A0_ORCHESTRATOR: _NEVER_FOR_ANY_AGENT,
    AgentId.A1_STUDENT_CONTEXT: _NEVER_FOR_ANY_AGENT | frozenset({"publish"}),
    AgentId.A2_ACADEMIC: _NEVER_FOR_ANY_AGENT | frozenset(
        {"read_calendar", "read_wellbeing", "publish"}
    ),
    AgentId.A3_GOAL_GAP: _NEVER_FOR_ANY_AGENT | frozenset({"publish"}),
    AgentId.A4_OPPORTUNITY: _NEVER_FOR_ANY_AGENT | frozenset(
        {"read_student", "read_profile", "read_calendar", "read_wellbeing",
         "publish", "write_catalog", "http_post", "send_email"}
    ),
    AgentId.A5_PATHWAY: _NEVER_FOR_ANY_AGENT | frozenset({"publish"}),
}

#: 哪个 Agent 能往哪个数据域写。Aggregated Insights 域**没有任何 Agent 可写**——
#: 只有确定性的 Aggregation Service 能写（Spec §8.9.2）。
AGENT_WRITE_DOMAINS: dict[AgentId, frozenset[DataDomain]] = {
    AgentId.A0_ORCHESTRATOR: frozenset(),
    AgentId.A1_STUDENT_CONTEXT: frozenset({DataDomain.STUDENT_PRIVATE, DataDomain.STUDENT_OPERATIONAL}),
    AgentId.A2_ACADEMIC: frozenset({DataDomain.ACADEMIC}),
    AgentId.A3_GOAL_GAP: frozenset({DataDomain.STUDENT_OPERATIONAL}),
    AgentId.A4_OPPORTUNITY: frozenset(),
    AgentId.A5_PATHWAY: frozenset({DataDomain.STUDENT_OPERATIONAL}),
}


class ToolPermissionError(PermissionError):
    """Agent 试图调用白名单外的工具。Gateway 与测试共用这一个异常。"""


def assert_tool_allowed(agent: AgentId, tool_name: str) -> None:
    allowed = AGENT_TOOL_WHITELIST[agent]
    if tool_name not in allowed:
        raise ToolPermissionError(
            f"{agent.value} 不得调用工具 {tool_name!r}；白名单：{sorted(allowed)}"
        )


# --------------------------------------------------------------------------
# 编排 Envelope
# --------------------------------------------------------------------------


class WorkflowKind(StrEnum):
    """A0 的两条路径（Spec §8.1 A0 行）。已知意图走确定性路由表，不进 LLM。"""

    DETERMINISTIC_ROUTE = "deterministic_route"
    LLM_COMPOSED = "llm_composed"


class IntentId(StrEnum):
    """确定性路由表的键。命中即不调用 LLM 编排，这是 T9 延迟达标的主要来源。"""

    ONBOARD = "onboard"
    UPDATE_PROFILE = "update_profile"
    SET_GOAL = "set_goal"
    VIEW_GAP_MAP = "view_gap_map"
    PLAN_COURSES = "plan_courses"
    FIND_OPPORTUNITIES = "find_opportunities"
    BUILD_PATHWAY = "build_pathway"
    APPROVE_ACTIONS = "approve_actions"
    REFLECT = "reflect"
    REPLAN = "replan"
    BROWSE_PLAZA = "browse_plaza"
    EXPLAIN_WHY_NOT_RECOMMENDED = "explain_why_not_recommended"


class AgentCall(CampusPathModel):
    call_id: Identifier
    agent: AgentId
    tool_name: str | None = None
    depends_on: tuple[Identifier, ...] = ()
    parallel_group: str | None = Field(
        default=None, description="同一组内的调用可并行（A1/A2/A3），用于 WP11 延迟优化"
    )

    @model_validator(mode="after")
    def _tool_is_whitelisted(self) -> "AgentCall":
        if self.tool_name is not None:
            assert_tool_allowed(self.agent, self.tool_name)
        return self


class WorkflowPlan(CampusPathModel):
    """A0 的编排结果。``SequentialAgent`` 表达固定流水线的顺序确定性。"""

    plan_id: Identifier
    student_id: StudentId
    kind: WorkflowKind
    intent: IntentId | None = None
    calls: tuple[AgentCall, ...] = Field(min_length=1)
    created_at: datetime

    @model_validator(mode="after")
    def _deterministic_route_needs_intent(self) -> "WorkflowPlan":
        if self.kind is WorkflowKind.DETERMINISTIC_ROUTE and self.intent is None:
            raise ValueError("确定性路由必须命中一个 intent，否则应标记为 llm_composed")
        known = {c.call_id for c in self.calls}
        for c in self.calls:
            missing = [d for d in c.depends_on if d not in known]
            if missing:
                raise ValueError(f"{c.call_id} 依赖计划外的调用：{missing}")
        return self


class ClarificationRequest(CampusPathModel):
    """A0 决定何时询问学生。选项化提问优于开放式，便于评测与降低延迟。"""

    request_id: Identifier
    question: LocalizedText
    options: tuple[LocalizedText, ...] = ()
    field_path: str | None = None
    blocking: bool = True


class ResponseEnvelope(CampusPathModel):
    """所有面向学生的 Agent 响应的统一外壳。

    ``synthetic_data_notice`` 恒为 True：D1 要求全站标记 `Synthetic / Demo Data`，
    做成类型上不可关闭，比在每个页面模板里记得加一行可靠。
    """

    envelope_id: Identifier
    student_id: StudentId
    locale: Locale
    intent: IntentId | None = None
    payload_type: str
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="按 payload_type 对应 openapi.py 路由表里的响应模型。"
                    "``extra=\"forbid\"`` 伸不进 dict 内部，字段名扫描也看不见里面，"
                    "所以由下面的 validator 递归拦截禁用键",
    )
    clarification: ClarificationRequest | None = None
    trace_id: str | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    synthetic_data_notice: Literal[True] = True
    generated_at: datetime

    @model_validator(mode="after")
    def _payload_carries_no_private_content(self) -> "ResponseEnvelope":
        """这是所有面向学生响应的唯一外壳，也是唯一一个 ``Any`` 逃逸口。

        实测可以塞进去：``{"private_text": "...", "calendar_event_title": "..."}``。
        递归查键名，把 B4/B5 的禁用词挡在外面。
        """
        from .guards import CALENDAR_DETAIL_TERMS, FREE_TEXT_TERMS

        banned = (FREE_TEXT_TERMS | CALENDAR_DETAIL_TERMS) - {"description", "summary"}
        offenders: list[str] = []

        def walk(node: Any, path: str) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    lowered = str(key).lower()
                    if any(term in lowered for term in banned):
                        offenders.append(f"{path}.{key}")
                    walk(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    walk(value, f"{path}[{index}]")

        walk(self.payload, "payload")
        if offenders:
            raise ValueError(
                f"ResponseEnvelope.payload 携带了禁用键：{offenders}（B4/B5）"
            )
        return self


class StudentContextView(CampusPathModel):
    """A1 输出：为当前任务组装的最小上下文。

    **不含 private_text，不含日历详情。** 这是 A1 交给下游（尤其 A5）的东西，
    传多了就等于把私密内容送进了另一个 Agent 的上下文窗口。
    """

    student_id: StudentId
    profile_version: int = Field(ge=1)
    summary: LocalizedText
    confirmed_skill_ids: tuple[Identifier, ...] = ()
    confirmed_experience_ids: tuple[Identifier, ...] = ()
    active_goal_ids: tuple[Identifier, ...] = ()
    recalled_memory_ids: tuple[Identifier, ...] = ()
    generated_at: datetime


# --------------------------------------------------------------------------
# Demo 运行时控制（F1，2026-08-02 用户裁定）
# --------------------------------------------------------------------------
# 顶栏一键启停 Vertex AI Agent Engine 运行时（按小时计费——按钮存在的意义
# 就是"演示前启动、演示完关闭"）。仅 demo 口径：真实部署由运维管。


class AgentRuntimeStatus(CampusPathModel):
    #: ``unknown`` = 本环境探测不到运行时（如云端容器没有 adk/infra 脚本）——
    #: 引擎可能在别处运行着。**不许把探测失败冒充 stopped**（2026-08-02 审计发现：
    #: 云端曾在两个引擎真实运行时报 stopped，顶栏按钮因此说谎）。
    state: Literal["stopped", "starting", "running", "stopping", "unavailable", "unknown"]
    #: 已部署运行时的 display_name 列表
    runtimes: tuple[str, ...] = ()
    #: 启停任务进行中时的分段进度（确定性汇报，非模型自估）
    progress: int = Field(default=0, ge=0, le=100)
    stage: LocalizedText | None = None
    error: str | None = None
    checked_at: datetime


class AgentRuntimeCommand(CampusPathModel):
    action: Literal["start", "stop"]
