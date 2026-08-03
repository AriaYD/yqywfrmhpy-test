"""现场 AI 拆解后台任务测试（A4，2026-08-02）。

模型用 ScriptedModel 桩（canned 行），任务线程真实跑——
轮询 GET 直到 done，验证 ai_live facets 并入拆解、每日限次、404 分支。
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from campuspath_agents.model import ScriptedModel
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

# 2026-08-02 用户裁定重建后：现场拆解 = 真流水线（接地搜索 → 逐家抓取
# → 逐行拆解 → 确定性加权）。桩按流水线的三步喂：搜索 JSON、逐家拆解行。
SEARCH_JSON = (
    '[{"company": "AlphaCo", "jd_title": "Junior Designer", '
    '"url": "https://alpha.example.invalid/jd"},'
    ' {"company": "BetaCo", "jd_title": "Product Designer", '
    '"url": "https://beta.example.invalid/jd"},'
    ' {"company": "GammaCo", "jd_title": "UX Intern", '
    '"url": "https://gamma.example.invalid/jd"}]'
)
LINES_A = "\n".join([
    "hard|technical_skill|掌握核心工具链|Master the core toolchain",
    "hard|project_portfolio|两个可验证项目|Two verifiable projects",
    "soft|communication|清晰表达设计取舍|Communicate design trade-offs",
    "垃圾行不合法要被跳过",
    "bad|category|x|y",
])
LINES_B = "\n".join([
    "hard|technical_skill|熟练使用设计工具|Fluent with design tools",
    "constraint|language|工作语言要求|Working language requirement",
])


@pytest.fixture()
def deps() -> Deps:
    d = Deps("full", model=ScriptedModel({
        "jd-search:GOAL-A-C": SEARCH_JSON,
        "jd-extract:GOAL-A-C:0": LINES_A,
        "jd-extract:GOAL-A-C:1": LINES_B,
        # GammaCo 抓取失败（fetch 桩返回 None），不会走到 extract:2
    }))
    # 抓取桩：Gamma 抓不到（流水线必须如实跳过），其余给足够长的正文
    d.research_fetch_fn = lambda url: (
        None if "gamma" in url else "职位要求 " * 40)
    return d


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def call(client: TestClient, method: str, path: str, **kwargs):
    headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kwargs.pop("headers", {})}
    return client.request(method, path, headers=headers, **kwargs)


BASE = "/v1/students/STU-A/goals/GOAL-A-C/decomposition/research"


def _wait_done(client: TestClient, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = call(client, "GET", BASE).json()
        if body["state"] != "running":
            return body
        time.sleep(0.05)
    raise AssertionError("研究任务超时未完成")


def test_full_research_cycle(client):
    r = call(client, "POST", BASE)
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["state"] == "running"
    assert job["daily_remaining"] == 1

    done = _wait_done(client)
    assert done["state"] == "done", done.get("error")
    assert done["progress"] == 100
    # 真流水线口径：实采 2 家（Gamma 抓取失败被如实跳过）；
    # 类别 = technical_skill / project_portfolio / communication / language
    facets = done["facets"]
    assert len(facets) == 4, [f["category"] for f in facets]
    assert all(f["origin"] == "ai_live" for f in facets)
    # 市场证据来自实采计数：2 家中 N 家要求
    assert all(f["market_note"] and "2 家在招 JD 中" in f["market_note"]["zh_Hans"]
               for f in facets), facets[0].get("market_note")
    by_cat = {f["category"]: f for f in facets}
    # technical_skill 两家都要求 → 覆盖 100% ≥60% ⇒ core；其余 1/2 ⇒ standard
    assert by_cat["technical_skill"]["priority"] == "core"
    assert "2 家要求" in by_cat["technical_skill"]["market_note"]["zh_Hans"]
    assert by_cat["project_portfolio"]["priority"] == "standard"
    # 取证来源逐条带真实 URL（来自搜索结果）
    assert any("alpha.example.invalid" in src["zh_Hans"]
               for src in by_cat["technical_skill"]["evidence_sources"])
    # 完成语如实报告实采与跳过数
    assert "实采 2 家" in done["stage"]["zh_Hans"]
    assert "1 家抓取失败" in done["stage"]["zh_Hans"]

    # 拆解端点把 ai_live facets 并入（origin 区分显示；GOAL-A-C 未命中编制库）
    decomposition = call(
        client, "GET", "/v1/students/STU-A/goals/GOAL-A-C/decomposition").json()
    live = [f for f in decomposition["facets"] if f["origin"] == "ai_live"]
    assert len(live) == 4


def test_daily_limit_and_status_404(client):
    assert call(client, "GET", BASE).status_code == 404   # 尚无任务
    assert call(client, "POST", BASE).status_code == 200
    _wait_done(client)
    assert call(client, "POST", BASE).status_code == 200  # 第 2 次
    _wait_done(client)
    third = call(client, "POST", BASE)
    assert third.status_code == 429
    assert third.json()["detail"]["error"] == "daily_research_limit"


def test_unknown_goal_404(client):
    r = call(client, "POST",
             "/v1/students/STU-A/goals/NO-SUCH/decomposition/research")
    assert r.status_code == 404


def test_no_model_backend_503(client, deps):
    deps.model = None
    r = call(client, "POST", BASE)
    assert r.status_code == 503


def test_grounded_fallback_recovers_shell_pages():
    """大厂 JS 壳页直抓失败 → 接地抽取回退成功，且引用 URL 换成模型
    实际读到的页面（SOURCE| 行）。"""
    deps = Deps("full", model=ScriptedModel({
        "jd-search:GOAL-A-C": (
            '[{"company": "DeltaCo", "jd_title": "UX Designer", '
            '"url": "https://delta.example.invalid/spa-shell"}]'),
        "jd-extract-grounded:GOAL-A-C:0": "\n".join([
            "hard|technical_skill|设计工具链|Design toolchain",
            "soft|user_empathy|以用户为中心|User-centred mindset",
            "SOURCE|https://mirror.example.invalid/delta-jd",
        ]),
    }))
    deps.research_fetch_fn = lambda url: None      # 直抓全败
    client = TestClient(create_app(deps))
    r = call(client, "POST", BASE)
    assert r.status_code == 200, r.text
    done = _wait_done(client)
    assert done["state"] == "done", done.get("error")
    assert "实采 1 家" in done["stage"]["zh_Hans"]
    facets = done["facets"]
    assert facets and all("1 家在招 JD 中 1 家要求" in f["market_note"]["zh_Hans"]
                          for f in facets)
    assert any("mirror.example.invalid" in src["zh_Hans"]
               for f in facets for src in f["evidence_sources"]), \
        "引用 URL 未替换为接地实际来源"


def test_rerun_replaces_previous_result():
    """2026-08-02 用户裁定：已有实采结果自动复用；显式重跑 → 新结果**覆盖**
    旧结果（不叠加、不并存）。"""
    deps = Deps("full", model=ScriptedModel({
        "jd-search:GOAL-A-C": (
            '[{"company": "OldCo", "jd_title": "Designer", '
            '"url": "https://old.example.invalid/jd"}]'),
        "jd-extract:GOAL-A-C:0": "hard|technical_skill|旧结果技能|Old-run skill",
    }))
    deps.research_fetch_fn = lambda url: "职位要求 " * 40
    client = TestClient(create_app(deps))
    assert call(client, "POST", BASE).status_code == 200
    first = _wait_done(client)
    assert first["state"] == "done"
    assert "OldCo" in first["facets"][0]["evidence_sources"][0]["zh_Hans"]

    # 无需重跑：拆解端点直接复用已完成结果
    d1 = call(client, "GET",
              "/v1/students/STU-A/goals/GOAL-A-C/decomposition").json()
    assert any("旧结果技能" in f["description"]["zh_Hans"] for f in d1["facets"])

    # 显式重跑：换一套采集结果，旧结果被整体替换
    deps.model.script["jd-search:GOAL-A-C"] = (
        '[{"company": "NewCo", "jd_title": "Designer II", '
        '"url": "https://new.example.invalid/jd"}]')
    deps.model.script["jd-extract:GOAL-A-C:0"] = \
        "hard|technical_skill|新结果技能|New-run skill"
    assert call(client, "POST", BASE).status_code == 200   # 第 2 次（限额内）
    second = _wait_done(client)
    assert second["state"] == "done"
    d2 = call(client, "GET",
              "/v1/students/STU-A/goals/GOAL-A-C/decomposition").json()
    live = [f for f in d2["facets"] if f["origin"] == "ai_live"]
    assert any("新结果技能" in f["description"]["zh_Hans"] for f in live)
    assert not any("旧结果技能" in f["description"]["zh_Hans"] for f in live), \
        "旧实采结果应被覆盖而不是叠加"


def test_live_overrides_compiled_profile_when_student_reran(deps):
    """审计红-2 后半（2026-08-02 用户裁定）：编制画像只是缓存——学生对
    已命中画像的岗位显式现场拆解后，live 结果成为唯一口径**取代**编制
    facets（不叠加混排）；约束/占位条目保留。"""
    deps.model = ScriptedModel({
        "jd-search:GOAL-A-P": SEARCH_JSON,
        "jd-extract:GOAL-A-P:0": LINES_A,
        "jd-extract:GOAL-A-P:1": LINES_B,
    })
    client = TestClient(create_app(deps))
    base = "/v1/students/STU-A/goals/GOAL-A-P/decomposition/research"

    before = call(client, "GET",
                  "/v1/students/STU-A/goals/GOAL-A-P/decomposition").json()
    assert before["role_profile"] == "software-engineer"
    assert any(f.get("market_note") for f in before["facets"]), "前提：编制画像带市场证据"

    r = call(client, "POST", base)
    assert r.status_code == 200, r.text
    deadline = time.time() + 5
    while time.time() < deadline:
        body = call(client, "GET", base).json()
        if body["state"] != "running":
            break
        time.sleep(0.05)
    assert body["state"] == "done", body

    after = call(client, "GET",
                 "/v1/students/STU-A/goals/GOAL-A-P/decomposition").json()
    origins = {f.get("origin") for f in after["facets"]}
    assert "ai_live" in origins, "live 结果必须并入"
    compiled_market = [f for f in after["facets"]
                       if f.get("origin") != "ai_live" and f.get("market_note")]
    assert compiled_market == [], "编制画像 facets 必须被 live 取代，不许混排"
    assert any(f.get("kind") == "constraint" for f in after["facets"]), "约束条目保留"
