"""Moodle Web Services REST 客户端。**白名单只读。**

白名单是闸门不是文档：不在 :data:`ALLOWED_WSFUNCTIONS` 里的函数
在发出任何网络请求**之前**就被拒绝。Moodle 的 token 权限在服务端
还有一层（campuspath_svc 只挂了读函数），两层都在才算数——
本层防"我们自己的代码手滑"，服务端防"token 泄露后被人拿去写"。

token 来源优先级：显式传入 → 环境变量 ``MOODLE_WS_TOKEN`` →
Secret Manager ``campuspath-moodle-ws-token``（走 ADC）。
token 从不出现在日志、异常信息或 repr 里。
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request
from typing import Any, Callable

#: 允许调用的 Moodle wsfunction。**全部只读。**
ALLOWED_WSFUNCTIONS: frozenset[str] = frozenset({
    "core_webservice_get_site_info",
    "core_course_get_courses",
    "core_enrol_get_enrolled_users",
    "core_enrol_get_users_courses",
    "core_user_get_users_by_field",
})

SECRET_NAME = "campuspath-moodle-ws-token"


class WsFunctionNotAllowed(PermissionError):
    """试图调用白名单之外的 wsfunction。"""


class MoodleWsError(RuntimeError):
    """Moodle 返回了 exception 结构（token 无效、函数未暴露等）。"""


def _token_from_secret_manager(project_id: str | None) -> str | None:
    try:  # 依赖可选：没装 SDK 或没有 ADC 的机器照样能跑单测
        from google.cloud import secretmanager  # type: ignore[import-not-found]

        project = project_id or os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            return None
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project}/secrets/{SECRET_NAME}/versions/latest"
        return client.access_secret_version(name=name).payload.data.decode()
    except Exception:
        return None


class MoodleClient:
    """transport 可注入：单测传一个假的，生产用默认的 urllib 实现。"""

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        token: str | None = None,
        *,
        project_id: str | None = None,
        transport: Callable[[str, dict[str, str]], str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = (
            token
            or os.environ.get("MOODLE_WS_TOKEN")
            or _token_from_secret_manager(project_id)
        )
        self._transport = transport or self._http_post

    def call(self, wsfunction: str, **params: Any) -> Any:
        if wsfunction not in ALLOWED_WSFUNCTIONS:
            raise WsFunctionNotAllowed(
                f"{wsfunction} 不在只读白名单里；允许：{sorted(ALLOWED_WSFUNCTIONS)}"
            )
        if not self._token:
            raise MoodleWsError(
                "没有可用的 Moodle token（MOODLE_WS_TOKEN / Secret Manager 均为空）"
            )
        payload = {
            "wstoken": self._token,
            "wsfunction": wsfunction,
            "moodlewsrestformat": "json",
            **_flatten(params),
        }
        raw = self._transport(f"{self.base_url}/webservice/rest/server.php", payload)
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("exception"):
            # errorcode 足够定位问题；message 可能回显请求内容，不带
            raise MoodleWsError(f"Moodle 异常：{data.get('errorcode', 'unknown')}")
        return data

    @staticmethod
    def _http_post(url: str, payload: dict[str, str]) -> str:
        body = urllib.parse.urlencode(payload).encode()
        request = urllib.request.Request(url, data=body, method="POST")
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            return response.read().decode()


def _flatten(params: dict[str, Any]) -> dict[str, str]:
    """Moodle 的数组参数写法：``field=username&values[0]=stu-a``。"""
    out: dict[str, str] = {}
    for key, value in params.items():
        if isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                out[f"{key}[{index}]"] = str(item)
        else:
            out[key] = str(value)
    return out
