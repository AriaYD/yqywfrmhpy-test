"""双人设线上评测 Bug-1/2（2026-08-03，用户批准修复）：

「换目标」的失效清单此前缺两项——旧目标的现场研究结果顶替新目标的
编制画像（张冠李戴）、选修推荐日缓存带着旧目标理由过夜。本文件钉住
统一口径：**目标变更 = research 按目标名失效 + course-rec/match 缓存清空**；
同名重存（未改目标）不触发失效——现场结果复用语义不受伤。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

SEARCH_JSON = (
    '[{"company": "RoboCo", "jd_title": "Robot Engineer", '
    '"url": "https://robo.example.invalid/jd"}]'
)
LINES = "hard|technical_skill|机器人抓取项目经验|Robot grasping projects"


def call(client, method, path, **kw):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kw.pop("headers", {})}
    return client.request(method, path, headers=headers, **kw)


def _goal_body(target: str) -> dict:
    return {
        "goal_id": "GOAL-STU-A-primary", "student_id": "STU-A",
        "role": "primary", "development_mode": "employment",
        "target_type": "role", "target_name": target,
        "horizon": "long_term", "created_at": "2026-09-15T09:00:00Z",
    }


@pytest.fixture()
def deps() -> Deps:
    d = Deps("full", model=ScriptedModel({
        "jd-search:GOAL-STU-A-primary": SEARCH_JSON,
        "jd-extract:GOAL-STU-A-primary:0": LINES,
    }))
    d.research_fetch_fn = lambda url: "职位要求 " * 40
    return d


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


BASE = "/v1/students/STU-A/goals/GOAL-STU-A-primary/decomposition/research"


def _run_research_to_done(client) -> None:
    r = call(client, "POST", BASE)
    assert r.status_code == 200, r.text
    deadline = time.time() + 5
    while time.time() < deadline:
        body = call(client, "GET", BASE).json()
        if body["state"] != "running":
            assert body["state"] == "done", body
            return
        time.sleep(0.05)
    raise AssertionError("研究任务超时未完成")


def test_renamed_goal_hides_stale_research(client):
    """Bug-1 本体：改目标名后，旧研究不许再从状态端点与拆解里冒出来。"""
    call(client, "POST", "/v1/students/STU-A/goals",
         json=_goal_body("机器人工程师"))
    _run_research_to_done(client)
    # 改名成完全不同的岗位
    call(client, "POST", "/v1/students/STU-A/goals",
         json=_goal_body("AI 产品经理"))
    status = call(client, "GET", BASE)
    assert status.status_code == 404, \
        f"旧岗位的研究任务不许挂在新目标名下：{status.text}"
    d = call(client, "GET",
             "/v1/students/STU-A/goals/GOAL-STU-A-primary/decomposition").json()
    assert not any(f.get("origin") == "ai_live" for f in d["facets"]), \
        "机器人实采 facets 顶替了产品经理的画像（Bug-1 未修）"
    assert d["role_profile"] == "ai-product-manager", "新目标编制画像必须回来"


def test_same_target_resave_keeps_research(client):
    """反例（复用语义不许误伤）：同名重存目标 → 研究结果照常复用。"""
    call(client, "POST", "/v1/students/STU-A/goals",
         json=_goal_body("机器人工程师"))
    _run_research_to_done(client)
    call(client, "POST", "/v1/students/STU-A/goals",
         json=_goal_body("机器人工程师"))
    assert call(client, "GET", BASE).status_code == 200
    d = call(client, "GET",
             "/v1/students/STU-A/goals/GOAL-STU-A-primary/decomposition").json()
    assert any(f.get("origin") == "ai_live" for f in d["facets"])


def test_goal_change_evicts_course_rec_and_match_caches(deps):
    """Bug-2 本体 + matches 同口径：换目标当场清空两份当日缓存。"""
    deps.model = None      # 规则降级路径即可命中缓存机制
    client = TestClient(create_app(deps))
    call(client, "GET", "/v1/students/STU-A/course-recommendations")
    call(client, "GET", "/v1/students/STU-A/matches?limit=5")
    assert any(k[0] == "STU-A" for k in deps.course_rec_cache), "前提：缓存已建"
    assert "STU-A" in deps.match_cache, "前提：缓存已建"
    call(client, "POST", "/v1/students/STU-A/goals",
         json=_goal_body("数据记者"))
    assert not any(k[0] == "STU-A" for k in deps.course_rec_cache), \
        "换目标后选修推荐缓存必须失效（Bug-2 未修）"
    assert "STU-A" not in deps.match_cache, "换目标后推荐缓存必须失效"
    # 再取即按新目标重建
    r = call(client, "GET", "/v1/students/STU-A/course-recommendations")
    assert r.status_code == 200
    assert any(k[0] == "STU-A" for k in deps.course_rec_cache)
