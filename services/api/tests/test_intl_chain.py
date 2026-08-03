"""国际生链路修复批测试（fix/intl-chain，2026-08-02 审计后）。

审计报告 docs/intl-chain-audit-2026-08-02.md 的四条主根因，各对应一组断言：
1. For You 逐卡差异化 intl_notes（服务端确定性派生，非复读）；
2. 规划四档注入 Pack 准备/核实动作，且每条 PlanItem 凭据可被 B8 背书；
3. 政策卡按源受众落 policy / intl_policy 双分类；
4. 运行时探测不可用如实报 unknown，不冒充 stopped。

H5：每组都有反向样例（未勾选国际生 → 零注记/零注入；audience 缺省 → intl_policy）。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole, SourceRef
from campuspath_connector.fetcher import ProbeResult
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

from test_intl_pack_api import INTL_CONTEXT, _enable


@pytest.fixture()
def deps() -> Deps:
    return Deps("full", model=None)   # 全链零模型：注记/注入不许依赖模型后端


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def student(client: TestClient):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


def admin(client: TestClient):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: ActorRole.CAREER_CENTER_ADMIN.value,
                   **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


# ── 1. For You 逐卡差异化 ─────────────────────────────────────────────


def test_matches_without_intl_have_no_notes(client):
    r = student(client)("GET", "/v1/students/STU-A/matches?limit=10")
    assert r.status_code == 200
    assert all(m["intl_notes"] == [] for m in r.json())


def test_matches_intl_notes_differ_by_opportunity_fields(client, deps):
    _enable(student(client))
    # 就地改造三个已进推荐结果的签证敏感型机会：接受 / 不接受 / 未标注。
    # 分数输入不动 → 排名不动 → 断言只看注记差异。
    first = student(client)("GET", "/v1/students/STU-A/matches?limit=50")
    assert first.status_code == 200
    sensitive_ids = []
    for m in first.json():
        opp = next(o for o in deps.opportunities
                   if o.opportunity_id == m["opportunity_id"])
        if opp.type.value in ("internship", "job", "research_position",
                              "mentorship"):
            sensitive_ids.append(opp.opportunity_id)
        if len(sensitive_ids) == 3:
            break
    assert len(sensitive_ids) == 3, "推荐结果里签证敏感型机会不足 3 个"
    states = ("accepts", "not_accepted", "unknown")
    for oid, acc in zip(sensitive_ids, states):
        index = next(i for i, o in enumerate(deps.opportunities)
                     if o.opportunity_id == oid)
        deps.opportunities[index] = deps.opportunities[index].model_copy(
            update={"accepts_international": acc, "sponsorship_support": None,
                    "language_requirements": ()})
    r = student(client)("POST", "/v1/students/STU-A/matches/refresh")
    assert r.status_code == 200
    by_id = {m["opportunity_id"]: m for m in r.json()}
    if not all(oid in by_id for oid in sensitive_ids):
        by_id = {m["opportunity_id"]: m for m in
                 student(client)("GET", "/v1/students/STU-A/matches?limit=50").json()}
    texts = {oid: tuple(n["zh_Hans"] for n in by_id[oid]["intl_notes"])
             for oid in sensitive_ids if oid in by_id}
    # codex #13：分数输入未动，三个都必须还在——掉一个就是回归，不许放行
    assert len(texts) == 3, f"改造后的机会掉出结果：{sensitive_ids} vs {list(by_id)[:5]}"
    # 三态注记两两不同（复读 bug 的直接反例）
    assert len(set(texts.values())) == len(texts), texts
    for oid, acc in zip(sensitive_ids, states):
        if oid not in texts:
            continue
        if acc == "not_accepted":
            assert any("不面向国际学生" in t for t in texts[oid])
        if acc == "unknown":
            assert any("未标注" in t for t in texts[oid])


def test_matches_non_visa_types_stay_quiet_without_fields(client, deps):
    """讲座/工作坊类且发布方没标注 → 不硬贴注记（治「每张卡一句废话」）。"""
    _enable(student(client))
    r = student(client)("GET", "/v1/students/STU-A/matches?limit=50")
    assert r.status_code == 200
    exercised = 0
    for m in r.json():
        opp = next(o for o in deps.opportunities
                   if o.opportunity_id == m["opportunity_id"])
        if (opp.type.value in ("event", "workshop", "club_activity")
                and opp.accepts_international.value == "unknown"
                and opp.sponsorship_support is None
                and not opp.language_requirements):
            exercised += 1
            assert m["intl_notes"] == [], (
                f"{opp.opportunity_id} 无字段可依据却出现注记")
    # codex #13：断言必须真的被行使过，空循环全绿不算证据
    assert exercised >= 1, "结果里没有一个符合条件的非签证敏感机会"


# ── 2. 规划注入 ───────────────────────────────────────────────────────


def test_pathway_without_intl_has_no_intl_items(client):
    r = student(client)("GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 200
    assert not [i for i in r.json()["plan_items"]
                if i["plan_item_id"].startswith("PI-INTL-")]


def test_pathway_injects_backed_intl_prep_items(client, deps):
    _enable(student(client))
    r = student(client)("GET", "/v1/students/STU-A/pathway")
    assert r.status_code == 200
    items = [i for i in r.json()["plan_items"]
             if i["plan_item_id"].startswith("PI-INTL-")]
    assert items, "国际生已启用但规划里没有 Pack 派生条目"
    # 信封有 1 条准备动作 + 1 条约束 + 2 项缺失信息 → 至少 3 条
    assert len(items) >= 3
    for item in items:
        assert item["kind"] == "action"
        # B8：凭据真实签发且能背书该主体
        ref = SourceRef(entity_type="action", entity_id=item["subject_id"])
        assert deps.validations.verify(item["validation_id"], ref), item
        assert item["date_range"]["start"] <= item["date_range"]["end"]
    # 读时注入不落缓存：连读两次数量一致、不累加
    again = [i for i in student(client)("GET", "/v1/students/STU-A/pathway")
             .json()["plan_items"] if i["plan_item_id"].startswith("PI-INTL-")]
    assert len(again) == len(items)
    # 缓存的原始版本没有被污染
    cached = deps.pathways["STU-A"]
    assert not [i for i in cached.plan_items
                if i.plan_item_id.startswith("PI-INTL-")]
    # codex #10：日期语义可验证——核实类固定 today+3 → today+30；
    # 准备类锚点 = 计划开始日期（2026-09-01），除非已过期（另有测试）。
    # 注意基准是 deps.today（demo 固定日期），不是系统日期。
    from datetime import timedelta as _td
    today = deps.today
    verify_items = [i for i in items if i["plan_item_id"].startswith("PI-INTL-VERIFY-")]
    assert verify_items
    for item in verify_items:
        assert item["date_range"]["start"] == (today + _td(days=3)).isoformat()
        assert item["date_range"]["end"] == (today + _td(days=30)).isoformat()
    prep = next(i for i in items if i["plan_item_id"] == "PI-INTL-PREP-1")
    if (today + _td(days=3)).isoformat() <= "2026-09-01":
        assert prep["date_range"]["end"] == "2026-09-01"
    # codex #2：主体绑定学生——同一动作换个学生的主体必须验不过
    ref_other = SourceRef(entity_type="action",
                          entity_id=prep["subject_id"].replace("STU-A", "STU-B"))
    assert not deps.validations.verify(prep["validation_id"], ref_other)


def test_pathway_survives_pack_digest_change(client, deps):
    """codex #6 回归：档案输入变了 → Pack digest 变了 → 不许撞旧凭据 500。"""
    call = student(client)
    _enable(call)
    assert call("GET", "/v1/students/STU-A/pathway").status_code == 200
    changed = {**INTL_CONTEXT, "language_evidence": ["TOEFL 100"],
               "target_cities": ["Shenzhen"]}
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"intl_context": changed})
    assert r.status_code == 200, r.text
    again = call("GET", "/v1/students/STU-A/pathway")
    assert again.status_code == 200, again.text
    assert [i for i in again.json()["plan_items"]
            if i["plan_item_id"].startswith("PI-INTL-")]


def test_pathway_overdue_anchor_is_flagged_not_rewritten(client, deps):
    """codex #5：锚点已过 → 计划项显式标注逾期，不冒充未来目标日。"""
    call = student(client)
    overdue = {**INTL_CONTEXT, "intended_start_date": "2026-07-01"}
    r = call("POST", "/v1/students/STU-A/consents",
             json={"scope": "context_pack", "granted": True})
    assert r.status_code == 200
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"intl_context": overdue})
    assert r.status_code == 200, r.text
    items = [i for i in call("GET", "/v1/students/STU-A/pathway")
             .json()["plan_items"] if i["plan_item_id"] == "PI-INTL-PREP-1"]
    assert items
    joined = " ".join(a["zh_Hans"] for a in items[0]["assumptions"])
    assert "已过" in joined, items[0]["assumptions"]


def test_matches_cache_evicted_on_intl_toggle(client, deps):
    """codex #3：勾选/取消国际生后当日推荐缓存必须作废。"""
    call = student(client)
    assert all(m["intl_notes"] == [] for m in
               call("GET", "/v1/students/STU-A/matches?limit=50").json())
    _enable(call)   # 勾选——不经手动刷新，直接再读
    after = call("GET", "/v1/students/STU-A/matches?limit=50").json()
    assert any(m["intl_notes"] for m in after), "勾选后缓存未作废，注记不出现"
    r = call("POST", "/v1/students/STU-A/profile/self-edit",
             json={"clear_intl_context": True})
    assert r.status_code == 200
    cleared = call("GET", "/v1/students/STU-A/matches?limit=50").json()
    assert all(m["intl_notes"] == [] for m in cleared), "取消后注记仍残留"


def test_unknown_warning_survives_other_fields(client, deps):
    """codex #4：担保/语言注记在场时「未标注」警示不许被挤没。"""
    from campuspath_contracts.common import LocalizedText
    call = student(client)
    _enable(call)
    first = call("GET", "/v1/students/STU-A/matches?limit=50").json()
    target = next(m["opportunity_id"] for m in first
                  if next(o for o in deps.opportunities
                          if o.opportunity_id == m["opportunity_id"])
                  .type.value in ("internship", "job", "mentorship"))
    index = next(i for i, o in enumerate(deps.opportunities)
                 if o.opportunity_id == target)
    deps.opportunities[index] = deps.opportunities[index].model_copy(update={
        "accepts_international": "unknown",
        "sponsorship_support": LocalizedText(zh_Hans="可提供签证担保咨询",
                                             en="Sponsorship advice available"),
    })
    refreshed = call("POST", "/v1/students/STU-A/matches/refresh").json()
    row = next((m for m in refreshed if m["opportunity_id"] == target), None)
    if row is None:
        row = next(m for m in
                   call("GET", "/v1/students/STU-A/matches?limit=50").json()
                   if m["opportunity_id"] == target)
    zh = [n["zh_Hans"] for n in row["intl_notes"]]
    assert any("未标注" in t for t in zh), zh
    assert zh and "未标注" in zh[0], f"警示必须排第一：{zh}"


# ── 3. 政策双分类 ─────────────────────────────────────────────────────


def test_policy_card_category_follows_audience(client, deps):
    deps.probe_fn = lambda url, prev: ProbeResult(
        outcome="changed", new_hash="a" * 64, text_excerpt="changed")
    # HKUST-SFAO 标了 all → policy；HK-IMMD-IANG 标了 intl → intl_policy
    admin(client)("POST", "/v1/ops/sources/HKUST-SFAO/refresh")
    admin(client)("POST", "/v1/ops/sources/HK-IMMD-IANG/refresh")
    cards = {o.source_id: o for o in deps.opportunities
             if o.type.value == "policy_update"}
    assert cards["HKUST-SFAO"].organizer_category.value == "policy"
    assert cards["HK-IMMD-IANG"].organizer_category.value == "intl_policy"


def test_policy_card_without_audience_defaults_conservative(client, deps):
    """codex #14：未标 policy_audience 的政策源 → 收敛默认 intl_policy
    （宁可少见，不放大受众）。"""
    from campuspath_contracts.common import LocalizedText
    from campuspath_contracts.publishing import RegisteredSource, SourceKind
    deps.registered_sources["TEST-POL-NOAUDIENCE"] = RegisteredSource(
        source_id="TEST-POL-NOAUDIENCE",
        name=LocalizedText(zh_Hans="测试政策源（未标受众）",
                           en="Test policy source (no audience)"),
        url="https://www.example-policy.gov.hk/page",
        kind=SourceKind.POLICY_SOURCE,
        category="policy", entry_type="policy_page",
    )
    deps.probe_fn = lambda url, prev: ProbeResult(
        outcome="changed", new_hash="e" * 64, text_excerpt="changed")
    r = admin(client)("POST", "/v1/ops/sources/TEST-POL-NOAUDIENCE/refresh")
    assert r.status_code == 200, r.text
    card = next(o for o in deps.opportunities
                if o.source_id == "TEST-POL-NOAUDIENCE")
    assert card.organizer_category.value == "intl_policy"


# ── 4. 运行时状态诚实性 ───────────────────────────────────────────────


def test_runtime_status_without_script_is_unknown(client, deps):
    """探测不到 ≠ 已停止：曾在云端引擎真实运行时报 stopped（审计发现）。

    H5 反向自证：把 runtime_script_path 还原成 "auto"（本机脚本存在）时，
    状态必须**不是** unknown——unknown 分支只许在真探测不到时出现。
    """
    from datetime import datetime as _dt, timezone as _tz
    deps.runtime_script_path = None
    deps.runtime_status_cache = (_dt.min.replace(tzinfo=_tz.utc), None)
    r = admin(client)("GET", "/v1/ops/agent-runtime")
    assert r.status_code == 200
    assert r.json()["state"] == "unknown"


def test_runtime_probe_failure_is_unknown_and_success_is_not(client, deps, tmp_path):
    """codex #11：脚本存在但执行失败 → unknown；执行成功 → running/stopped。
    H5 双向：unknown 分支只在真探测不到时出现。"""
    from datetime import datetime as _dt, timezone as _tz

    def _reset_cache():
        deps.runtime_status_cache = (_dt.min.replace(tzinfo=_tz.utc), None)

    failing = tmp_path / "engine_fail.sh"
    failing.write_text("#!/bin/sh\nexit 7\n")
    deps.runtime_script_path = failing
    _reset_cache()
    assert admin(client)("GET", "/v1/ops/agent-runtime").json()["state"] == "unknown"

    stopped = tmp_path / "engine_stopped.sh"
    stopped.write_text("#!/bin/sh\necho '（没有已部署的 Agent Engine 运行时）'\n")
    deps.runtime_script_path = stopped
    _reset_cache()
    assert admin(client)("GET", "/v1/ops/agent-runtime").json()["state"] == "stopped"

    running = tmp_path / "engine_running.sh"
    running.write_text("#!/bin/sh\necho '- campuspath-orchestrator'\n")
    deps.runtime_script_path = running
    _reset_cache()
    body = admin(client)("GET", "/v1/ops/agent-runtime").json()
    assert body["state"] == "running"
    assert body["runtimes"] == ["campuspath-orchestrator"]


def test_runtime_rest_fallback_reports_cloud_engines(client, deps):
    """状态灯（2026-08-03 用户需求）：云端容器没有 adk 脚本时，探测走
    Vertex REST 列表回退——引擎在跑就亮绿灯，不再恒 unknown。
    H5 三向：有名字 → running；空列表 → stopped；REST 抛错 → unknown。"""
    from datetime import datetime as _dt, timezone as _tz

    def _reset():
        deps.runtime_status_cache = (_dt.min.replace(tzinfo=_tz.utc), None)

    deps.runtime_script_path = None          # 模拟云端：无脚本
    deps.runtime_rest_fn = lambda: ("campuspath-orchestrator",
                                    "campuspath-opportunity-scout")
    _reset()
    body = admin(client)("GET", "/v1/ops/agent-runtime").json()
    assert body["state"] == "running"
    assert "campuspath-orchestrator" in body["runtimes"]

    deps.runtime_rest_fn = lambda: ()
    _reset()
    assert admin(client)("GET", "/v1/ops/agent-runtime").json()["state"] == "stopped"

    def _boom():
        raise RuntimeError("no permission")
    deps.runtime_rest_fn = _boom
    _reset()
    assert admin(client)("GET", "/v1/ops/agent-runtime").json()["state"] == "unknown"
