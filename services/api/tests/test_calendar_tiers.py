"""B5 在**部署边界**上的落点：采集不得超出学生授权的层级。

契约层保证"没授权的对象构造不出来"；这里保证 API **实际返回的东西**
也守着同一条线，即使数据源给多了。两层都要有，因为它们防的是不同的事：
契约防的是有人写错代码，这里防的是数据里本来就多。

最关键的一条是 :func:`test_titles_are_withheld_without_the_grant`——
它**先往数据里塞一个带标题的区块**（模拟 Provider 给多了），
再断言未授权的学生拿不到它。不注入这个"已知会泄漏"的样例，
这条测试就只是在复述"数据里本来没有标题"。
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CalendarDetailLevel,
)
from campuspath_contracts.common import ActorRole, TimeRange
from campuspath_contracts.profile import ConsentRecord, ConsentScope

from campuspath_api.app import Deps, create_app
from campuspath_api.rbac import ROLE_HEADER

HEADERS = {ROLE_HEADER: ActorRole.STUDENT.value}
NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)


def _titled_block(student_id: str) -> AvailabilityBlock:
    return AvailabilityBlock(
        block_id=f"AB-{student_id}-titled",
        student_id=student_id,
        span=TimeRange(
            start=datetime(2026, 9, 16, 9, tzinfo=timezone.utc),
            end=datetime(2026, 9, 16, 11, tzinfo=timezone.utc),
        ),
        type=AvailabilityType.BUSY,
        source=BlockSource.CALENDAR_FREEBUSY,
        detail_level=CalendarDetailLevel.EVENT_TITLES,
        title="Society weekly meeting",
    )


@pytest.fixture
def deps() -> Deps:
    d = Deps("full", model=object())      # 不需要真模型
    d.availability.append(_titled_block("STU-A"))
    return d


def test_titles_are_withheld_without_the_grant(deps: Deps):
    """数据里**有**标题，学生**没**授权 → 响应里必须没有标题。"""
    assert any(b.title for b in deps.availability if b.student_id == "STU-A")

    client = TestClient(create_app(deps))
    rows = client.get("/v1/students/STU-A/availability", headers=HEADERS).json()

    assert rows, "STU-A 本该有时段，否则这条测试什么也没测到"
    # B5 的对象是**私人日历采集**（calendar_freebusy）。课表（教务公开数据）
    # 与学生自设区块（本人笔迹）不在其列——R4-M（2026-07-31）。
    gated = [r for r in rows if r["source"] == "calendar_freebusy"]
    assert gated, "应有日历同步块，否则这条测试什么也没测到"
    assert all(row["title"] is None for row in gated)
    assert all(row["detail_level"] == "free_busy_only" for row in gated)


def test_titles_are_returned_once_the_student_grants_the_second_tier(deps: Deps):
    profile = deps.students["STU-A"]
    deps.students["STU-A"] = profile.model_copy(update={
        "consent": profile.consent + (
            ConsentRecord(
                scope=ConsentScope.CALENDAR_EVENT_TITLES,
                granted=True, granted_at=NOW, receipt_id="RCPT-TIER2",
            ),
        )
    })

    client = TestClient(create_app(deps))
    rows = client.get("/v1/students/STU-A/availability", headers=HEADERS).json()
    assert any(row["title"] == "Society weekly meeting" for row in rows)


def test_a_revoked_grant_stops_returning_titles(deps: Deps):
    """撤销必须**立刻**生效。曾经 granted=True 不代表现在还能看。"""
    profile = deps.students["STU-A"]
    deps.students["STU-A"] = profile.model_copy(update={
        "consent": profile.consent + (
            ConsentRecord(
                scope=ConsentScope.CALENDAR_EVENT_TITLES,
                granted=True, granted_at=NOW, revoked_at=NOW,
                receipt_id="RCPT-TIER2",
            ),
        )
    })

    client = TestClient(create_app(deps))
    rows = client.get("/v1/students/STU-A/availability", headers=HEADERS).json()
    gated = [r for r in rows if r["source"] == "calendar_freebusy"]
    assert gated and all(row["title"] is None for row in gated)


def test_no_calendar_response_ever_carries_more_than_a_title(deps: Deps):
    """二级授权放行的是**标题这一项**，不是"详情随便取"。"""
    client = TestClient(create_app(deps))
    rows = client.get("/v1/students/STU-A/availability", headers=HEADERS).json()
    for row in rows:
        for forbidden in ("attendees", "location", "description", "organizer", "notes"):
            assert forbidden not in row
