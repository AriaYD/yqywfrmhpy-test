"""stdio JSON-RPC 的 MCP 服务器：把白名单 Moodle 函数暴露成 MCP tools。

零第三方依赖——协议面只用到 initialize / tools/list / tools/call 三个方法，
手写比引一个 SDK 更容易审计（这条链路的卖点就是"每一层都看得见"）。

用法（本机先开隧道）：
    gcloud compute ssh campuspath-moodle --zone=asia-east2-a -- -L 8080:localhost:8080
    python -m moodle_mcp.server
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .client import ALLOWED_WSFUNCTIONS, MoodleClient, MoodleWsError, WsFunctionNotAllowed

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "moodle_site_info",
        "description": "Moodle 站点信息与本 token 可用的函数（只读）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "moodle_courses",
        "description": "全部课程（只读）",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "moodle_user_courses",
        "description": "某个学生（用户名，如 stu-a）注册的课程（只读）",
        "inputSchema": {
            "type": "object",
            "properties": {"username": {"type": "string"}},
            "required": ["username"],
        },
    },
]


def _dispatch(client: MoodleClient, name: str, arguments: dict[str, Any]) -> Any:
    if name == "moodle_site_info":
        return client.call("core_webservice_get_site_info")
    if name == "moodle_courses":
        return client.call("core_course_get_courses")
    if name == "moodle_user_courses":
        users = client.call(
            "core_user_get_users_by_field",
            field="username", values=[arguments["username"]],
        )
        if not users:
            return []
        return client.call("core_enrol_get_users_courses", userid=users[0]["id"])
    raise WsFunctionNotAllowed(f"未知工具 {name}")


def handle(client: MoodleClient, request: dict[str, Any]) -> dict[str, Any] | None:
    rid = request.get("id")
    method = request.get("method")
    if method == "initialize":
        result: Any = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "campuspath-moodle-mcp", "version": "1.0.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params", {})
        try:
            data = _dispatch(client, params.get("name", ""),
                             params.get("arguments", {}) or {})
            result = {"content": [{"type": "text",
                                   "text": json.dumps(data, ensure_ascii=False)}]}
        except (WsFunctionNotAllowed, MoodleWsError) as exc:
            result = {"content": [{"type": "text", "text": str(exc)}],
                      "isError": True}
    elif method in {"notifications/initialized", "notifications/cancelled"}:
        return None
    else:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"未实现的方法 {method}"}}
    return {"jsonrpc": "2.0", "id": rid, "result": result}


def main() -> None:
    client = MoodleClient()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(client, request)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
