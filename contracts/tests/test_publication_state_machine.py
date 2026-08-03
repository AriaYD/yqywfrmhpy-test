"""B7 Unauthorized Publication 与发布状态机（D5）。

状态机测试遍历 :data:`ALLOWED_TRANSITIONS` 全表，而不是只测 happy path：
D5 明确要求"退回修改"与"驳回"两条分支各演示一次，两者都必须可达且不可互相短路。
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from campuspath_contracts.opportunity import PublicationStatus
from campuspath_contracts.publishing import (
    ALLOWED_TRANSITIONS,
    REVIEW_TRIGGERING_FIELDS,
    PublisherRoleGrant,
    TransitionNotAllowed,
    assert_transition_allowed,
)
from campuspath_contracts.common import ActorRole

TODAY = date(2026, 7, 29)


def _grant(**kw) -> PublisherRoleGrant:
    base = dict(
        grant_id="G-1",
        principal_id="P-club-robotics",
        organization_id="ORG-robotics-club",
        role=ActorRole.PUBLISHER,
        allowed_categories=("workshop", "competition"),
        can_publish_directly=False,
        valid_from=TODAY - timedelta(days=30),
        valid_to=TODAY + timedelta(days=30),
        granted_by="P-admin",
    )
    base.update(kw)
    return PublisherRoleGrant(**base)


# --------------------------------------------------------------------------
# 状态机
# --------------------------------------------------------------------------


def test_every_status_appears_in_the_transition_table():
    """漏掉一个状态，实现里就会出现"查不到就放行"的分支。"""
    assert set(ALLOWED_TRANSITIONS) == set(PublicationStatus)


def test_archived_is_terminal():
    assert ALLOWED_TRANSITIONS[PublicationStatus.ARCHIVED] == frozenset()


def test_changes_requested_branch_is_reachable_and_returns_to_review():
    """D5 的"退回修改"分支：in_review → changes_requested → submitted。"""
    assert_transition_allowed(PublicationStatus.IN_REVIEW, PublicationStatus.CHANGES_REQUESTED)
    assert_transition_allowed(PublicationStatus.CHANGES_REQUESTED, PublicationStatus.SUBMITTED)


def test_rejected_branch_is_reachable_and_cannot_be_published():
    """D5 的"驳回"分支：驳回后只能归档，不能绕回发布。"""
    assert_transition_allowed(PublicationStatus.IN_REVIEW, PublicationStatus.REJECTED)
    assert ALLOWED_TRANSITIONS[PublicationStatus.REJECTED] == frozenset(
        {PublicationStatus.ARCHIVED}
    )


def test_submitted_cannot_jump_straight_to_published():
    """已知会失败的样例：跳过自动校验与人工审核直接发布。"""
    with pytest.raises(TransitionNotAllowed):
        assert_transition_allowed(PublicationStatus.SUBMITTED, PublicationStatus.PUBLISHED)


def test_draft_cannot_jump_to_approved():
    with pytest.raises(TransitionNotAllowed):
        assert_transition_allowed(PublicationStatus.DRAFT, PublicationStatus.APPROVED)


def test_published_update_must_go_back_through_review():
    """Spec §11.3 失败样本：改了截止日期却没重新审核。"""
    assert_transition_allowed(PublicationStatus.PUBLISHED, PublicationStatus.UPDATED)
    assert PublicationStatus.IN_REVIEW in ALLOWED_TRANSITIONS[PublicationStatus.UPDATED]
    assert "deadline" in REVIEW_TRIGGERING_FIELDS


def test_no_status_can_reach_published_without_approved_or_updated():
    """唯一进入 published 的入口是 approved 或 updated。"""
    sources = {s for s, targets in ALLOWED_TRANSITIONS.items() if PublicationStatus.PUBLISHED in targets}
    assert sources == {PublicationStatus.APPROVED, PublicationStatus.UPDATED}


# --------------------------------------------------------------------------
# B7：授权范围
# --------------------------------------------------------------------------


def test_grant_covers_its_own_organization_and_category():
    assert _grant().covers("ORG-robotics-club", "workshop", TODAY) is True


@pytest.mark.parametrize(
    "org,category,when,why",
    [
        ("ORG-other-club", "workshop", TODAY, "越权代表其他社团"),
        ("ORG-robotics-club", "internship", TODAY, "分类超出授权"),
        ("ORG-robotics-club", "workshop", TODAY + timedelta(days=60), "授权已过期"),
        ("ORG-robotics-club", "workshop", TODAY - timedelta(days=60), "授权尚未生效"),
    ],
)
def test_out_of_scope_attempts_are_not_covered(org, category, when, why):
    assert _grant().covers(org, category, when) is False, why


def test_revoked_grant_covers_nothing():
    from conftest import NOW

    revoked = _grant(revoked_at=NOW)
    assert revoked.covers("ORG-robotics-club", "workshop", TODAY) is False


def test_direct_publish_is_off_by_default():
    """学生社团获得 Portal 访问权 ≠ 获得直接公开发布权（Spec §6.8）。"""
    assert _grant().can_publish_directly is False
