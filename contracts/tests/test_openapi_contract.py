"""OpenAPI 合同的自洽性，以及"磁盘产物 == 代码"的可复现性断言。

WP1 的验收条款是"前后端、Agent、Mock 服务全部从同一份 Schema 生成类型"。
只要磁盘上的 ``schema/`` 与 ``openapi/`` 可能落后于代码，这句话就不成立——
所以这里把 ``export_schemas.py --check`` 的逻辑也纳入测试。
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

from campuspath_contracts import ROOT_MODELS
from campuspath_contracts.common import ActorRole, CONTRACTS_VERSION
from campuspath_contracts.openapi import (
    API_ENDPOINTS,
    ROLE_RESTRICTED_PREFIXES,
    build_openapi,
)

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import export_schemas  # noqa: E402


@pytest.fixture(scope="module")
def document() -> dict:
    return build_openapi(ROOT_MODELS)


def test_every_referenced_model_exists(document):
    """路由表引用的模型必须都在契约里——这是"契约先行"能成立的前提。"""
    schemas = document["components"]["schemas"]
    for endpoint in API_ENDPOINTS:
        assert endpoint.response_model in schemas, endpoint.path
        if endpoint.request_model is not None:
            assert endpoint.request_model in schemas, endpoint.path


def test_no_dangling_refs(document):
    """所有 $ref 都能解析。悬空引用会让代码生成器静默产出 unknown。"""
    schemas = document["components"]["schemas"]
    dangling: list[str] = []

    def walk(node, where: str):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[-1]
                if name not in schemas:
                    dangling.append(f"{where} → {ref}")
            for key, value in node.items():
                walk(value, f"{where}.{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, f"{where}[{i}]")

    walk(document, "root")
    assert dangling == [], dangling


def test_pathway_endpoint_declares_unbacked_rejection():
    """B8：API 层必须声明它会拒绝缺失/伪造 validation_id 的输出。"""
    endpoint = next(e for e in API_ENDPOINTS if e.path.endswith("/pathway"))
    assert (422, "unbacked_validation_id") in endpoint.errors


def test_publisher_endpoint_declares_scope_violation():
    """B7：越权投稿必须被拦截。"""
    endpoint = next(e for e in API_ENDPOINTS if e.path == "/v1/publisher/submissions")
    assert (403, "scope_violation") in endpoint.errors


def test_outreach_endpoint_requires_consent():
    endpoint = next(e for e in API_ENDPOINTS if e.path.endswith("/wellbeing/outreach"))
    assert (403, "consent_missing") in endpoint.errors
    assert (422, "field_not_whitelisted") in endpoint.errors


def test_wellbeing_queue_is_not_reachable_by_career_center_roles():
    """D5 隔离验证的 API 侧：Curator / Reviewer / Publisher 都进不了 outreach 队列。"""
    endpoint = next(e for e in API_ENDPOINTS if e.path == "/v1/wellbeing/outreach-queue")
    assert set(endpoint.roles) == {ActorRole.WELLBEING_COORDINATOR}
    for role in (ActorRole.CURATOR, ActorRole.REVIEWER, ActorRole.PUBLISHER, ActorRole.STUDENT):
        assert role not in endpoint.roles


def test_insights_endpoints_have_no_individual_drilldown():
    """Spec §17.1.2 硬性边界 2：后端不提供"查看构成该数字的学生"的查询。"""
    for endpoint in API_ENDPOINTS:
        if endpoint.path.startswith("/v1/insights/"):
            assert "student" not in endpoint.path
            assert "student_id" not in endpoint.path
            assert endpoint.response_model in {
                "ResourceCoverageAggregate", "EventQualityAggregate"
            }


def test_role_restricted_prefixes_match_the_endpoint_table():
    for prefix, roles in ROLE_RESTRICTED_PREFIXES.items():
        matched = [e for e in API_ENDPOINTS if e.path.startswith(prefix)]
        assert matched, f"{prefix} 没有对应端点"
        for endpoint in matched:
            assert roles <= set(endpoint.roles), f"{endpoint.path} 的角色与前缀表不一致"


def test_student_scoped_paths_carry_student_id():
    for endpoint in API_ENDPOINTS:
        if endpoint.path.startswith("/v1/students/"):
            assert "{student_id}" in endpoint.path


def test_operation_ids_are_unique(document):
    ids = [
        op["operationId"]
        for path_item in document["paths"].values()
        for op in path_item.values()
    ]
    assert len(ids) == len(set(ids))


def test_version_is_pinned(document):
    assert document["info"]["version"] == CONTRACTS_VERSION


# --------------------------------------------------------------------------
# 可复现性
# --------------------------------------------------------------------------


def test_export_is_deterministic():
    """跑两次必须字节一致，否则 D6.7 的"两次数字一致"无从谈起。"""
    first = export_schemas.build_outputs()
    second = export_schemas.build_outputs()
    assert first == second


def test_disk_artifacts_match_the_code():
    """已知会失败的场景：改了模型却忘了重新导出。"""
    stale = [
        str(path.relative_to(ROOT))
        for path, content in export_schemas.build_outputs().items()
        if not path.exists() or path.read_text(encoding="utf-8") != content
    ]
    assert stale == [], (
        f"以下产物已过期，请运行 `make contracts`：{stale}"
    )


def test_exported_openapi_is_valid_json():
    document = json.loads((ROOT / "openapi" / "campuspath.json").read_text(encoding="utf-8"))
    assert document["openapi"] == "3.1.0"
    assert document["paths"]


def test_every_model_has_an_exported_schema():
    index = json.loads((ROOT / "schema" / "_index.json").read_text(encoding="utf-8"))
    assert set(index["models"]) == set(ROOT_MODELS)
    for name in ROOT_MODELS:
        assert (ROOT / "schema" / f"{name}.json").exists(), name
