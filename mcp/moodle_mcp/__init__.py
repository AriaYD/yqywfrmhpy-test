"""Moodle BYO-MCP（Spec §11.4 / Plan WP3 / F04）。

三层结构：

* :mod:`client`  —— Moodle Web Services REST 客户端，**wsfunction 白名单只读**；
* :mod:`server`  —— stdio JSON-RPC 的 MCP 服务器，把白名单函数暴露成 MCP tools；
* :mod:`adapter` —— :class:`EducationDataAdapter` 的 Moodle 实现，
  只覆盖 Moodle 真正承载的数据（选课记录），其余如实返回空。

真实交互链：Moodle REST/Web Services → 本 MCP → ADK 侧作为 A2 的教育数据工具。
"""

from .adapter import MoodleEducationAdapter
from .client import MoodleClient, WsFunctionNotAllowed

__all__ = ["MoodleClient", "MoodleEducationAdapter", "WsFunctionNotAllowed"]
