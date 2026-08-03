"""两级授权在 Provider 这一层的落点。

最重要的一条是 :func:`test_free_busy_tier_never_leaks_titles`：
它用**同一份夹具、同一个时间窗**跑两次，只改 detail_level，
断言一级授权下**每一个**区间的 title 都是 None。
只测"二级能拿到标题"是不够的——泄漏发生在另一个方向。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from campuspath_contracts.calendar import CalendarDetailLevel

from campuspath_connector.calendar_providers import (
    FixtureCalendarProvider,
    GoogleCalendarProvider,
)

TZ = timezone.utc
START = datetime(2026, 9, 14, tzinfo=TZ)          # 周一
END = START + timedelta(days=7)


def test_free_busy_tier_never_leaks_titles():
    provider = FixtureCalendarProvider()
    minimal = provider.free_busy("STU-A", START, END)
    assert minimal, "夹具在这一周本该有忙碌区间，否则这条测试什么也没测到"
    assert all(interval.title is None for interval in minimal)

    granted = provider.free_busy(
        "STU-A", START, END, detail_level=CalendarDetailLevel.EVENT_TITLES
    )
    assert any(interval.title for interval in granted)
    # 两个层级看到的**时间**必须完全一样：授权改变的是能看见什么，
    # 不是日历本身。若两者时段不同，说明实现走了两条不同的取数路径。
    assert [(i.start, i.end) for i in minimal] == [(i.start, i.end) for i in granted]


def test_the_default_argument_is_the_minimum_tier():
    """忘了传参 = 取最少。这条锁住默认值的方向。"""
    provider = FixtureCalendarProvider()
    assert all(i.title is None for i in provider.free_busy("STU-A", START, END))


def test_fixture_is_deterministic():
    """同一学生同一周两次调用必须字节一致——Demo 重跑不能变样。"""
    provider = FixtureCalendarProvider()
    first = provider.free_busy("STU-B", START, END)
    second = provider.free_busy("STU-B", START, END)
    assert [(i.start, i.end, i.title) for i in first] == [
        (i.start, i.end, i.title) for i in second
    ]


def test_different_students_get_different_shifts():
    provider = FixtureCalendarProvider()
    a = [i.start for i in provider.free_busy("STU-A", START, END)]
    c = [i.start for i in provider.free_busy("STU-C", START, END)]
    assert a != c, "所有学生日历一模一样会让 persona 切换看起来是坏的"


def test_intervals_stay_inside_the_requested_window():
    provider = FixtureCalendarProvider()
    narrow_end = START + timedelta(days=2)
    for interval in provider.free_busy("STU-A", START, narrow_end):
        assert interval.end > START
        assert interval.start < narrow_end


def test_create_event_is_idempotent_on_the_key():
    provider = FixtureCalendarProvider()
    first = provider.create_event(
        "STU-A", "复习", START, START + timedelta(hours=2), idempotency_key="k-1"
    )
    again = provider.create_event(
        "STU-A", "别的标题", START, START + timedelta(hours=3), idempotency_key="k-1"
    )
    assert first == again, "同一幂等键必须给同一个外部 id"


def test_google_provider_refuses_rather_than_returning_empty():
    """未接线的实现**不能**返回空列表。

    空列表会被上游读成"这周没有安排"，于是容量算出一个凭空多出来的
    可支配时间。抛错至少是诚实的。
    """
    with pytest.raises(NotImplementedError):
        GoogleCalendarProvider().free_busy("STU-A", START, END)
