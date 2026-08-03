"""RBAC：角色从**契约里的路由表**取，不在这里重列一份。

Spec §6.7 与 D5 的隔离验证要求：以 Career Center 角色登录，看不到任何 wellbeing
事件、Reflection 原文、个体日历。那条隔离如果靠两份各自维护的表来保证，
迟早会出现"契约里写了、中间件里漏了"。所以这里唯一的数据来源是
``campuspath_contracts.openapi``。

调用方通过 ``X-CampusPath-Role`` 声明角色。**这不是认证**——Demo 里没有 IdP。
它是授权层：真实部署时换成从 IAM/IAP 断言里取角色，这一层的判定逻辑不变。
"""

from __future__ import annotations

import dataclasses

from campuspath_contracts.common import ActorRole
from campuspath_contracts.openapi import API_ENDPOINTS

ROLE_HEADER = "X-CampusPath-Role"


class RoleDenied(PermissionError):
    def __init__(self, path: str, role: ActorRole | None, allowed: frozenset[ActorRole]):
        self.path = path
        self.role = role
        self.allowed = allowed
        super().__init__(
            f"{role.value if role else '<未声明>'} 不能访问 {path}；"
            f"允许的角色：{sorted(r.value for r in allowed)}"
        )


def _build_table() -> dict[tuple[str, str], frozenset[ActorRole]]:
    """``(method, path) -> 允许的角色``，直接由契约的路由表生成。"""
    return {
        (endpoint.method.upper(), endpoint.path): frozenset(endpoint.roles)
        for endpoint in API_ENDPOINTS
    }


ROLE_TABLE: dict[tuple[str, str], frozenset[ActorRole]] = _build_table()


@dataclasses.dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    reason: str


def check(method: str, path_template: str, role: ActorRole | None) -> AccessDecision:
    """判定一次访问。未在表中的路径**拒绝**，不是放行。

    默认放行会让"新加一个端点忘了配角色"变成一个开放接口；
    默认拒绝会让它变成一个报错的接口。后者会被发现，前者不会。
    """
    allowed = ROLE_TABLE.get((method.upper(), path_template))
    if allowed is None:
        return AccessDecision(False, f"{method} {path_template} 不在契约路由表中")
    if role is None:
        return AccessDecision(False, f"未声明角色（缺 {ROLE_HEADER}）")
    if role not in allowed:
        return AccessDecision(
            False,
            f"{role.value} 无权访问；允许 {sorted(r.value for r in allowed)}",
        )
    return AccessDecision(True, "")


def parse_role(raw: str | None) -> ActorRole | None:
    if not raw:
        return None
    try:
        return ActorRole(raw)
    except ValueError:
        return None
