"""Moodle MCP 的结构测试：白名单、身份映射、协议面。全部不出网。"""

from __future__ import annotations

import json

import pytest
from moodle_mcp.adapter import MoodleEducationAdapter, course_code
from moodle_mcp.client import (
    ALLOWED_WSFUNCTIONS,
    MoodleClient,
    MoodleWsError,
    WsFunctionNotAllowed,
)
from moodle_mcp.server import handle


def scripted(responses: dict[str, object]):
    """按 wsfunction 返回预设值的假 transport；顺带记录发出的请求。"""
    calls: list[dict[str, str]] = []

    def transport(url: str, payload: dict[str, str]) -> str:
        calls.append(payload)
        fn = payload["wsfunction"]
        if fn not in responses:
            raise AssertionError(f"未预设的 wsfunction：{fn}")
        return json.dumps(responses[fn])

    return transport, calls


def test_non_whitelisted_function_is_rejected_before_any_request():
    transport, calls = scripted({})
    client = MoodleClient(token="t", transport=transport)
    with pytest.raises(WsFunctionNotAllowed):
        client.call("core_user_create_users", users=[])   # 写函数
    assert calls == [], "白名单外的调用发出了网络请求"


def test_whitelist_contains_no_write_functions():
    assert all(
        not fn.split("_", 2)[-1].startswith(("create", "update", "delete"))
        for fn in ALLOWED_WSFUNCTIONS
    )


def test_moodle_exception_becomes_error_without_echoing_token():
    transport, _ = scripted({
        "core_course_get_courses": {"exception": "x", "errorcode": "invalidtoken"},
    })
    client = MoodleClient(token="secret-token", transport=transport)
    with pytest.raises(MoodleWsError) as exc:
        client.call("core_course_get_courses")
    assert "secret-token" not in str(exc.value)


def test_adapter_maps_enrolments_to_contract_records():
    transport, _ = scripted({
        "core_user_get_users_by_field": [{"id": 7, "username": "stu-a"}],
        "core_enrol_get_users_courses": [
            {"id": 2, "shortname": "COMP1021", "fullname": "Intro"},
            {"id": 3, "shortname": "HUMA1000", "fullname": "Cultures"},
            {"id": 1, "shortname": "site-home", "fullname": "非课程"},
        ],
    })
    adapter = MoodleEducationAdapter(
        MoodleClient(token="t", transport=transport), term="2026-27_FALL",
    )
    records = adapter.course_records("STU-A")
    assert [r.course_id for r in records] == ["COMP 1021", "HUMA 1000"]
    assert all(r.status.value == "enrolled" for r in records)
    assert all(r.grade is None for r in records)
    # Moodle 不承载的域必须为空，不许编造
    assert adapter.degree_requirements("BSC-COMP") == []
    assert adapter.catalog() == []


def test_course_code_mapping():
    assert course_code("COMP1021") == "COMP 1021"
    assert course_code("comp2012h") == "COMP 2012H"
    assert course_code("site-home") is None


def test_server_lists_tools_and_calls_through_whitelist():
    transport, _ = scripted({"core_course_get_courses": [{"id": 2}]})
    client = MoodleClient(token="t", transport=transport)

    listing = handle(client, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in listing["result"]["tools"]}
    assert names == {"moodle_site_info", "moodle_courses", "moodle_user_courses"}

    called = handle(client, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "moodle_courses", "arguments": {}},
    })
    assert not called["result"].get("isError")
    assert json.loads(called["result"]["content"][0]["text"]) == [{"id": 2}]

    unknown = handle(client, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "moodle_delete_everything", "arguments": {}},
    })
    assert unknown["result"]["isError"], "未知工具必须报错，不能静默成功"
