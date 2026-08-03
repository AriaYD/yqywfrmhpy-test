"""「睡眠-负荷平衡」预警模型测试（2026-08-02 用户裁定）。

合格日 = 有效睡眠 <7h 且 学习工作（BUSY 块合计）>11h。
H5 双向：9/14 天不触发；10/14 → warning；20/28 → assessment；
完成量表 → last_assessment_at 落档（弹窗解除依据）。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.common import ActorRole
from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

STUDENT = "STU-A"


@pytest.fixture()
def deps() -> Deps:
    return Deps("full", model=None)


@pytest.fixture()
def client(deps: Deps) -> TestClient:
    return TestClient(create_app(deps))


def call(client: TestClient):
    def _c(method: str, path: str, **kwargs):
        headers = {ROLE_HEADER: ActorRole.STUDENT.value, **kwargs.pop("headers", {})}
        return client.request(method, path, headers=headers, **kwargs)
    return _c


def _setup_days(deps: Deps, qualifying: int, total: int) -> None:
    """重建 STU-A 的日历：total 天数据，前 qualifying 天为合格日
    （12h 忙碌 + 声明睡眠窗 6.5h），其余为轻负荷日。锚点=最后一天。"""
    template = next(b for b in deps.availability
                    if b.student_id == STUDENT and b.type.value == "busy")
    student = deps.students[STUDENT]
    deps.students[STUDENT] = student.model_copy(update={
        "energy_profile": student.energy_profile.model_copy(update={
            "sleep_window_start": "23:30", "sleep_window_end": "06:00",  # 6.5h < 7
        }),
    })
    deps.availability[:] = [b for b in deps.availability
                            if b.student_id != STUDENT]
    anchor = date(2026, 9, 20)
    for offset in range(total):
        day = anchor - timedelta(days=offset)
        heavy = offset < qualifying
        hours = 12 if heavy else 4          # 12h > 11 阈值；4h 远低于
        start = f"{day.isoformat()}T08:00:00Z"
        end_h = 8 + hours
        end = f"{day.isoformat()}T{end_h:02d}:00:00Z"
        deps.availability.append(template.model_copy(update={
            "block_id": f"AB-{STUDENT}-bal-{offset}",
            "span": template.span.model_copy(update={
                "start": start, "end": end}),
        }))


def test_nine_of_fourteen_days_stays_calm(client, deps):
    _setup_days(deps, qualifying=9, total=14)
    esc = call(client)("GET", f"/v1/students/{STUDENT}/wellbeing/escalation").json()
    assert esc["qualifying_days_14"] == 9
    assert esc["tier"] == "none"


def test_ten_of_fourteen_triggers_gentle_warning(client, deps):
    _setup_days(deps, qualifying=10, total=14)
    esc = call(client)("GET", f"/v1/students/{STUDENT}/wellbeing/escalation").json()
    assert esc["qualifying_days_14"] == 10
    assert esc["tier"] == "warning"
    assert any("11" in r["zh_Hans"] and "7" in r["zh_Hans"]
               for r in esc["reasons"])


def test_twenty_of_twentyeight_triggers_assessment(client, deps):
    _setup_days(deps, qualifying=20, total=28)
    esc = call(client)("GET", f"/v1/students/{STUDENT}/wellbeing/escalation").json()
    assert esc["qualifying_days_28"] == 20
    assert esc["tier"] == "assessment"
    assert esc["last_assessment_at"] is None


def test_assessment_completion_is_recorded(client, deps):
    _setup_days(deps, qualifying=20, total=28)
    c = call(client)
    r = c("POST", f"/v1/students/{STUDENT}/wellbeing/assessment", json={
        "student_id": STUDENT,
        "isi_answers": [1] * 7,          # 轻度以下
        "pss10_answers": [1] * 10,       # 低压
    })
    assert r.status_code == 200, r.text
    esc = c("GET", f"/v1/students/{STUDENT}/wellbeing/escalation").json()
    assert esc["last_assessment_at"] is not None   # 弹窗解除依据


def test_high_study_with_enough_sleep_does_not_qualify(client, deps):
    """H5 反例：只超时长、睡眠够 7h → 不计入。"""
    _setup_days(deps, qualifying=14, total=14)
    student = deps.students[STUDENT]
    deps.students[STUDENT] = student.model_copy(update={
        "energy_profile": student.energy_profile.model_copy(update={
            "sleep_window_start": "23:00", "sleep_window_end": "07:30",  # 8.5h
        }),
    })
    esc = call(client)("GET", f"/v1/students/{STUDENT}/wellbeing/escalation").json()
    assert esc["qualifying_days_14"] == 0
    assert esc["tier"] == "none"


def test_outreach_consent_defaults_off_for_every_student():
    """「外联同意必须默认关闭」是不变量，钉在状态确定的 fresh seed 上——
    浏览器门禁曾把它写成对**当前状态**的断言，用户合法授权一次就永远
    误报（2026-08-04 实发，pages.mjs 已改为只断言控件在场）。
    遍历全部学生（§10.2：fixture 别只造一份）。"""
    from campuspath_api.app import Deps
    from campuspath_contracts.profile import ConsentScope

    deps = Deps("full")
    assert deps.students, "种子里必须有学生"
    for sid, student in deps.students.items():
        granted = [c for c in student.consent
                   if c.scope is ConsentScope.WELLBEING_OUTREACH
                   and c.granted and c.revoked_at is None]
        assert not granted, f"{sid} 的外联同意在种子里就被打开了"
