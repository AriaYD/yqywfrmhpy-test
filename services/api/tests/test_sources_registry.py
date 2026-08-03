"""源注册表端点测试（C3，2026-08-02）。

全部离线：deps.probe_fn 换成桩，不发真实请求。
覆盖：列表角色栅栏、刷新 404/409、mock 源不抓取、
政策源变更→政策卡直发广场（同日去重）、
非白名单变更源不发任何条目、unchanged/error 的健康态。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from campuspath_connector.fetcher import ProbeResult
from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER


@pytest.fixture()
def deps() -> Deps:
    d = Deps("tiny", model=object())   # 模型桩：这些端点不该碰模型
    return d


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def admin(client: TestClient):
    def call(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: ActorRole.CAREER_CENTER_ADMIN.value,
                   **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return call


def test_list_sources_requires_admin_roles(client):
    anonymous = client.get("/v1/ops/sources")
    assert anonymous.status_code == 403
    student = client.get("/v1/ops/sources",
                         headers={ROLE_HEADER: ActorRole.STUDENT.value})
    assert student.status_code == 403


def test_list_sources_marks_real_vs_mock(client):
    rows = admin(client)("GET", "/v1/ops/sources").json()
    assert len(rows) >= 60
    by_id = {r["source_id"]: r for r in rows}
    assert by_id["urop-projects"]["is_real_fetch"] is True
    assert by_id["SRC-partner-ats"]["is_real_fetch"] is False
    assert by_id["hkust-event-calendar"]["extraction_depth"] == "full_chain"
    assert by_id["urop-projects"]["extraction_depth"] == "change_monitor"


def test_refresh_unknown_source_404(client):
    r = admin(client)("POST", "/v1/ops/sources/no-such-source/refresh")
    assert r.status_code == 404


def test_refresh_mock_source_does_not_probe(client, deps):
    def exploding_probe(url, prev):   # pragma: no cover - 只为断言未被调用
        raise AssertionError("mock 源不得发起抓取")
    deps.probe_fn = exploding_probe
    r = admin(client)("POST", "/v1/ops/sources/SRC-partner-ats/refresh")
    assert r.status_code == 200
    assert r.json()["last_checked_at"] is not None


def test_refresh_policy_source_change_publishes_one_card_per_day(client, deps):
    deps.probe_fn = lambda url, prev: ProbeResult(
        outcome="changed", new_hash="a" * 64, text_excerpt="IANG updated text")
    before = len(deps.opportunities)
    r1 = admin(client)("POST", "/v1/ops/sources/HK-IMMD-IANG/refresh")
    assert r1.status_code == 200
    assert r1.json()["content_hash"] == "a" * 64
    cards = [o for o in deps.opportunities if o.type.value == "policy_update"]
    assert len(cards) == 1
    card = cards[0]
    assert card.organizer_category.value == "intl_policy"
    assert card.publication_status.value == "published"
    assert card.official_url.startswith("https://www.immd.gov.hk")
    # 同日再刷（哈希又变）：不再发第二张
    deps.probe_fn = lambda url, prev: ProbeResult(
        outcome="changed", new_hash="b" * 64, text_excerpt="again")
    admin(client)("POST", "/v1/ops/sources/HK-IMMD-IANG/refresh")
    cards = [o for o in deps.opportunities if o.type.value == "policy_update"]
    assert len(cards) == 1
    assert len(deps.opportunities) == before + 1


def test_refresh_non_whitelisted_change_publishes_nothing(client, deps):
    """change_monitor 深度的源变了：只记变更，不硬造广场条目。"""
    deps.probe_fn = lambda url, prev: ProbeResult(
        outcome="changed", new_hash="c" * 64, text_excerpt="urop page changed")
    before = len(deps.opportunities)
    r = admin(client)("POST", "/v1/ops/sources/urop-projects/refresh")
    assert r.status_code == 200
    assert r.json()["last_changed_at"] is not None
    assert len(deps.opportunities) == before


def test_refresh_unchanged_and_error_states(client, deps):
    deps.probe_fn = lambda url, prev: ProbeResult(outcome="unchanged", new_hash="d" * 64)
    r = admin(client)("POST", "/v1/ops/sources/ec-events/refresh")
    assert r.status_code == 200
    assert r.json()["last_changed_at"] is None
    assert deps.source_fetch_status["ec-events"] == "ok"

    deps.probe_fn = lambda url, prev: ProbeResult(outcome="error", detail="URLError: boom")
    r = admin(client)("POST", "/v1/ops/sources/ec-events/refresh")
    assert r.status_code == 200
    assert deps.source_fetch_status["ec-events"] == "unreachable"


def test_refresh_is_deterministic_on_replay(client, deps):
    """同一输入连调两次（Plan §10.2 幂等坑）：第二次不炸、结果一致。"""
    deps.probe_fn = lambda url, prev: ProbeResult(outcome="unchanged", new_hash="e" * 64)
    first = admin(client)("POST", "/v1/ops/sources/bm-events/refresh")
    second = admin(client)("POST", "/v1/ops/sources/bm-events/refresh")
    assert first.status_code == second.status_code == 200
    assert first.json()["content_hash"] == second.json()["content_hash"]
