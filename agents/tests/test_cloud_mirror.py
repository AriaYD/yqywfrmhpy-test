"""R7-D：云端部署镜像与本地 roster 的一致性。

Agent Engine 上跑的 orchestrator 是独立打包的（不 import 本 monorepo），
路由表因此存在第二份。这里断言两份逐项一致——表改了镜像没跟上，
先红的是 CI，不是演示现场。
"""

import importlib.util
import pathlib
import sys


def _load_cloud_module(name: str, rel: str):
    path = pathlib.Path(__file__).resolve().parents[1] / "cloud" / rel
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_cloud_orchestrator_routes_mirror_roster():
    from campuspath_agents.roster import OrchestratorAgent

    cloud = _load_cloud_module(
        "cloud_orchestrator_agent", "orchestrator_agent/agent.py")

    local = {
        intent.value: [a.value for a in agents]
        for intent, agents in OrchestratorAgent.ROUTES.items()
    }
    assert cloud.ROUTES == local, (
        "云端镜像路由表与 roster.OrchestratorAgent.ROUTES 不一致——"
        "改了其中一份必须同步另一份并重新部署"
    )


def test_cloud_orchestrator_route_tool_is_deterministic():
    cloud = _load_cloud_module(
        "cloud_orchestrator_agent2", "orchestrator_agent/agent.py")
    hit = cloud.route_intent("find_opportunities")
    assert hit["kind"] == "deterministic_route" and hit["model_used"] is False
    assert [c["agent"] for c in hit["calls"]] == ["A1", "A3", "A5"]
    miss = cloud.route_intent("write_my_thesis")
    assert miss["kind"] == "llm_composed" and miss["model_used"] is True


def test_cloud_scout_cannot_publish():
    """A4 镜像：工具签名里没有 status 可传，产出恒为 draft。"""
    cloud = _load_cloud_module(
        "cloud_scout_agent", "opportunity_scout_agent/agent.py")
    draft = cloud.emit_opportunity_draft(
        title="X", organizer="Y", category="published",  # 越界分类也进不了发布态
        summary="s", signup_hint="",
    )["draft"]
    assert draft["publication_status"] == "draft"
    assert draft["category"] == "event"
    assert draft["signup_hint"] == "未提供"
