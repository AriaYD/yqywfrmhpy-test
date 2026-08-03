"""CampusPath A0 Orchestrator —— Agent Engine 部署形态（R7-D）。

**这是 A0 的云端运行时镜像，不是第二个 A0。** 判定逻辑与本地
``campuspath_agents.roster.OrchestratorAgent`` 同一张路由表；
``agents/tests/test_cloud_mirror.py`` 断言两者逐项一致——表改了
镜像没跟上，CI 会先红。

部署为独立包（不 import campuspath_agents）：Agent Engine 打包的是
本目录，把整个 monorepo 塞进 runtime 只为查一张字典不值得。
模型调用走 Vertex（Agent Engine 托管运行时自带 ADC，吃赠金账号）。
"""

from google.adk.agents import Agent

#: 与 roster.OrchestratorAgent.ROUTES 逐项一致（有 CI 断言守着）。
#: 已知意图 → 确定性路由，**不调模型**；只有未命中才由 LLM 编排。
ROUTES: dict[str, list[str]] = {
    "plan_courses": ["A1", "A2", "A3", "A5"],
    "find_opportunities": ["A1", "A3", "A5"],
    "build_pathway": ["A1", "A2", "A3", "A5"],
    "view_gap_map": ["A1", "A3"],
    "reflect": ["A1"],
    "replan": ["A5"],
    "browse_plaza": [],
    "update_profile": ["A1"],
    "set_goal": ["A3"],
    "onboard": ["A1"],
    "approve_actions": [],
    "explain_why_not_recommended": ["A5"],
}


def route_intent(intent: str) -> dict:
    """查确定性路由表：这个意图要派哪些 Agent、按什么顺序。

    Args:
        intent: 意图标识（如 plan_courses / find_opportunities / reflect）。

    Returns:
        kind=deterministic_route 与调用序列；未知意图返回 kind=llm_composed，
        表示需要模型兜底编排（并说明这不是路由表的一部分）。
    """
    key = intent.strip().lower()
    if key in ROUTES:
        return {
            "kind": "deterministic_route",
            "intent": key,
            "calls": [
                {"call_id": f"C-{i + 1}", "agent": a,
                 "parallel_group": "facts" if a in {"A1", "A2", "A3"} else None}
                for i, a in enumerate(ROUTES[key])
            ],
            "model_used": False,
        }
    return {
        "kind": "llm_composed",
        "intent": key,
        "known_intents": sorted(ROUTES),
        "model_used": True,
        "note": "未命中路由表——由 LLM 编排兜底，trace 里与确定性路由分得开",
    }


root_agent = Agent(
    name="campuspath_orchestrator",
    model="gemini-2.5-flash",
    description="CampusPath A0：意图路由编排器（确定性路由表优先，模型只做兜底）",
    instruction=(
        "你是 CampusPath 的 A0 Orchestrator。收到学生请求时：\n"
        "1. 先判断它属于哪个已知意图，调用 route_intent 查确定性路由表；\n"
        "2. 命中路由表就按工具返回的调用序列回答『派了哪些 Agent、谁并行谁串行』，"
        "不要自行增删 Agent；\n"
        "3. 未命中时如实说明这是 LLM 兜底编排，并给出最小必要的 Agent 序列建议。\n"
        "永远不要虚构路由表里没有的 Agent。回答用中文。"
    ),
    tools=[route_intent],
)
