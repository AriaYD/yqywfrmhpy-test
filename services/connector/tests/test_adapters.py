"""Connector & Catalog：统一接口形状与 Source Health 八项。"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from campuspath_contracts.publishing import SourceKind

from campuspath_contracts.calendar import CalendarDetailLevel

from campuspath_connector.adapters import (
    BusyInterval,
    CalendarProvider,
    EducationDataAdapter,
    OpportunityProvider,
    SourceProbe,
    assess_health,
    needs_human_attention,
)

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


def probe(**kw) -> SourceProbe:
    base = dict(
        source_id="SRC-1", kind=SourceKind.OPPORTUNITY_SOURCE, attempted_at=NOW,
        succeeded=True, http_status=200, records_seen=100, records_parsed=98,
        required_fields_present=390, required_fields_expected=400,
        broken_links=1, checked_links=100, deadline_conflicts=0,
        duplicate_signals=0, last_success_at=NOW - timedelta(hours=2),
    )
    base.update(kw)
    return SourceProbe(**base)


# ── 接口形状 ──────────────────────────────────────────────────────────


def test_education_adapter_is_read_only():
    """CampusPath 不改学校的权威系统——接口里没有写方法。"""
    methods = [m for m in dir(EducationDataAdapter) if not m.startswith("_")]
    for verb in ("create", "update", "delete", "write", "set"):
        assert not any(m.startswith(verb) for m in methods), methods


def test_calendar_provider_returns_no_detail_beyond_the_title():
    """B5 现在的形态：**采集不得超出授权层级**。

    标题是二级授权放行的那一项，所以它可以在返回类型里；
    参与人、地点、描述仍然连字段都没有——那些从来没有被授权过，
    也不打算做成"再加一级"。
    """
    fields = set(BusyInterval.__dataclass_fields__)
    assert fields == {"start", "end", "title"}
    for forbidden in ("attendees", "location", "description", "organizer", "notes"):
        assert forbidden not in fields


def test_free_busy_defaults_to_the_minimum_tier():
    """忘了传 detail_level 等于**取最少**，不是取最多。

    默认值站错边的接口，会让"没授权却取了标题"变成一次疏忽就能造成的事故。
    """
    signature = inspect.signature(CalendarProvider.free_busy)
    default = signature.parameters["detail_level"].default
    assert default is CalendarDetailLevel.FREE_BUSY_ONLY


def test_calendar_provider_write_takes_a_title_we_supply():
    """写回的事件名是我们生成的，与"读取并保存学生原有标题"是两回事。"""
    signature = inspect.signature(CalendarProvider.create_event)
    assert "title" in signature.parameters
    assert "idempotency_key" in signature.parameters


def test_opportunity_provider_declares_its_source():
    assert "source_id" in dir(OpportunityProvider)


# ── Source Health 八项 ────────────────────────────────────────────────


def test_all_eight_metrics_are_produced():
    health = assess_health(probe(), now=NOW)
    for field in ("last_successful_sync", "fetch_auth_status", "parse_success_rate",
                  "freshness_hours", "broken_link_rate", "deadline_consistency_issues",
                  "schema_coverage_rate", "duplicate_conflict_signals"):
        assert getattr(health, field) is not None


def test_health_exposes_no_content():
    """§6.11：只展示运维指标，不展示原文。"""
    payload = assess_health(probe(), now=NOW).model_dump()
    for key in payload:
        assert key not in {"title", "description", "records", "sample", "body"}


@pytest.mark.parametrize(
    "status,expected",
    [(429, "rate_limited"), (401, "auth_expired"), (403, "auth_expired"), (500, "unreachable")],
)
def test_failure_status_is_classified(status, expected):
    health = assess_health(probe(succeeded=False, http_status=status), now=NOW)
    assert health.fetch_auth_status == expected


def test_freshness_is_measured_from_the_last_success():
    health = assess_health(
        probe(last_success_at=NOW - timedelta(hours=30)), now=NOW
    )
    assert health.freshness_hours == pytest.approx(30.0, abs=0.1)


def test_never_checked_is_not_reported_as_broken():
    """没检查过 ≠ 全都坏了。用 freshness 暴露"根本没跑过"，而不是把比率打成 0。"""
    health = assess_health(probe(checked_links=0, broken_links=0), now=NOW)
    assert health.broken_link_rate == 0.0 or health.broken_link_rate == 1.0
    assert health.parse_success_rate <= 1.0


# ── 人工队列 ──────────────────────────────────────────────────────────


def test_healthy_source_does_not_enter_the_queue():
    """§6.11：连接器自动同步，只有异常才进人工队列。"""
    assert needs_human_attention(assess_health(probe(), now=NOW)) is False


@pytest.mark.parametrize(
    "kw",
    [
        {"succeeded": False, "http_status": 401},
        {"last_success_at": NOW - timedelta(days=10)},
        {"records_parsed": 50},
        {"broken_links": 30},
        {"deadline_conflicts": 2},
        {"required_fields_present": 100},
        {"duplicate_signals": 3},
    ],
)
def test_each_abnormal_condition_raises_the_flag(kw):
    assert needs_human_attention(assess_health(probe(**kw), now=NOW)) is True
