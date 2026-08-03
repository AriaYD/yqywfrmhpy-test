"""Publishing / Review / Audit：B7 越权拦截、状态机、复审触发。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from campuspath_contracts.common import ActorRole, LocalizedText, Provenance
from campuspath_contracts.opportunity import (
    Opportunity,
    OpportunityType,
    PublicationStatus,
)
from campuspath_contracts.publishing import (
    ModerationDecision,
    PublicationSubmission,
    PublisherRoleGrant,
    TransitionNotAllowed,
)

from campuspath_publishing.workflow import PublishingService, ScopeDenied

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
TODAY = date(2026, 9, 15)


def grant(**kw) -> PublisherRoleGrant:
    base = dict(
        grant_id="GRANT-1", principal_id="PUB-club", organization_id="ORG-club",
        role=ActorRole.PUBLISHER, allowed_categories=("workshop",),
        can_publish_directly=False,
        valid_from=TODAY - timedelta(days=30), valid_to=TODAY + timedelta(days=30),
        granted_by="PUB-admin",
    )
    base.update(kw)
    return PublisherRoleGrant(**base)


def opportunity(**kw) -> Opportunity:
    base = dict(
        opportunity_id="OPP-1", type=OpportunityType.WORKSHOP, title="合成工作坊（Demo）",
        organizer="ORG-club", official_url="https://example.invalid/o", source_id="SRC-1",
        provenance=Provenance(source="portal", retrieved_at=NOW, parser_version="t/1"),
        publication_status=PublicationStatus.DRAFT,
        deadline=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )
    base.update(kw)
    return Opportunity(**base)


def submission(status=PublicationStatus.DRAFT, **kw) -> PublicationSubmission:
    base = dict(
        submission_id="SUB-1", owner_principal_id="PUB-club", organization_id="ORG-club",
        draft_version=1, content=opportunity(publication_status=status),
        category_tags=("workshop",), status=status,
        submitted_at=None if status is PublicationStatus.DRAFT else NOW,
    )
    base.update(kw)
    return PublicationSubmission(**base)


def service() -> PublishingService:
    """注册三种角色。审核与发布也需要身份——这不是脚手架，是 B7 的要求。"""
    s = PublishingService()
    s.register(grant())
    s.register(grant(grant_id="GRANT-REV", principal_id="REV-1",
                     organization_id="ORG-career-center", role=ActorRole.REVIEWER,
                     allowed_categories=("workshop", "internship")))
    s.register(grant(grant_id="GRANT-CUR", principal_id="CUR-1",
                     organization_id="ORG-career-center", role=ActorRole.CURATOR,
                     allowed_categories=("workshop", "internship"),
                     can_publish_directly=True))
    return s


# ── B7 ────────────────────────────────────────────────────────────────


def test_in_review_requires_a_named_reviewer():
    """契约层的要求：没有指定审核人的 in_review 构造不出来。"""
    with pytest.raises(Exception):
        submission(PublicationStatus.IN_REVIEW)


def test_in_scope_submission_succeeds():
    s = service()
    updated = s.submit(submission(), when=TODAY, at=NOW)
    assert updated.status is PublicationStatus.SUBMITTED
    assert s.violations == ()
    assert s.audit_log[0].to_status is PublicationStatus.SUBMITTED


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({"organization_id": "ORG-other"}, "wrong_organization"),
        ({"category_tags": ("internship",)}, "category_not_allowed"),
        ({"owner_principal_id": "PUB-nobody"}, "no_grant"),
    ],
)
def test_out_of_scope_submission_is_blocked_and_recorded(kw, expected):
    """B7 的判定包含可追溯：只拦不记不算通过。"""
    s = service()
    with pytest.raises(ScopeDenied) as excinfo:
        s.submit(submission(**kw), when=TODAY, at=NOW)
    assert excinfo.value.violation.reason == expected
    assert len(s.violations) == 1


def test_expired_grant_is_blocked():
    s = PublishingService()
    s.register(grant(valid_to=TODAY - timedelta(days=1)))
    with pytest.raises(ScopeDenied) as excinfo:
        s.submit(submission(), when=TODAY, at=NOW)
    assert excinfo.value.violation.reason == "grant_expired"


# ── 状态机 ────────────────────────────────────────────────────────────


def decision(kind: str) -> ModerationDecision:
    return ModerationDecision(
        decision_id="MOD-1", submission_id="SUB-1", submission_version=1,
        reviewer_id="REV-1", decision=kind,  # type: ignore[arg-type]
        reasons=(LocalizedText(zh_Hans="理由", en="reason"),), timestamp=NOW,
    )


def test_changes_requested_branch():
    s = service()
    # 契约要求 in_review 必须有明确审核人，否则审核责任无归属
    updated = s.apply_decision(
        submission(PublicationStatus.IN_REVIEW, current_reviewer_id="REV-1"),
        decision("request_changes"), at=NOW)
    assert updated.status is PublicationStatus.CHANGES_REQUESTED


def test_rejected_branch():
    s = service()
    updated = s.apply_decision(
        submission(PublicationStatus.IN_REVIEW, current_reviewer_id="REV-1"),
        decision("reject"), at=NOW)
    assert updated.status is PublicationStatus.REJECTED


def test_cannot_publish_from_submitted():
    """已知会失败的样例：跳过审核直接发布。"""
    s = service()
    with pytest.raises(TransitionNotAllowed):
        s.publish(submission(PublicationStatus.SUBMITTED), actor_id="CUR-1", at=NOW)


def test_publish_from_approved():
    s = service()
    updated = s.publish(submission(PublicationStatus.APPROVED), actor_id="CUR-1", at=NOW)
    assert updated.status is PublicationStatus.PUBLISHED


# ── 复审触发 ──────────────────────────────────────────────────────────


def test_changing_the_deadline_forces_re_review():
    """Spec §11.3：已发布活动更新截止日期后没有重新审核，是明确的失败样本。"""
    s = service()
    published = submission(PublicationStatus.PUBLISHED)
    updated = s.update_published(
        published,
        opportunity(publication_status=PublicationStatus.PUBLISHED,
                    deadline=datetime(2026, 11, 1, tzinfo=timezone.utc)),
        actor_id="PUB-club", at=NOW, reviewer_id="REV-1",
    )
    assert updated.status is PublicationStatus.IN_REVIEW
    assert updated.current_reviewer_id == "REV-1"
    assert any("复审" in entry.detail for entry in s.audit_log)


def test_re_review_without_a_named_reviewer_is_refused():
    """契约要求 in_review 有明确审核人。此前这里置成 in_review 却不指定人，
    只是因为 model_copy 不校验才没报错——那不是通过，是没被检查。"""
    s = service()
    with pytest.raises(ValueError):
        s.update_published(
            submission(PublicationStatus.PUBLISHED),
            opportunity(publication_status=PublicationStatus.PUBLISHED,
                        deadline=datetime(2026, 11, 1, tzinfo=timezone.utc)),
            actor_id="PUB-club", at=NOW,
        )


def test_changing_the_title_alone_does_not_force_re_review():
    s = service()
    published = submission(PublicationStatus.PUBLISHED)
    updated = s.update_published(
        published,
        opportunity(publication_status=PublicationStatus.PUBLISHED, title="改了标题"),
        actor_id="PUB-club", at=NOW,
    )
    assert updated.status is PublicationStatus.UPDATED


def test_update_bumps_the_draft_version():
    s = service()
    updated = s.update_published(
        submission(PublicationStatus.PUBLISHED),
        opportunity(publication_status=PublicationStatus.PUBLISHED, title="改了标题"),
        actor_id="PUB-club", at=NOW,
    )
    assert updated.draft_version == 2


# ── 撤下与过期 ────────────────────────────────────────────────────────


def test_withdraw_is_audited_with_a_reason():
    s = service()
    s.withdraw(submission(PublicationStatus.PUBLISHED), actor_id="CUR-1", at=NOW,
               reason="活动取消")
    assert "活动取消" in s.audit_log[0].detail


def test_expire_is_attributed_to_the_system():
    s = service()
    s.expire(submission(PublicationStatus.PUBLISHED), at=NOW)
    assert s.audit_log[0].role is ActorRole.SYSTEM


def test_every_transition_is_audited():
    s = service()
    submitted = s.submit(submission(), when=TODAY, at=NOW)
    reviewed = s.apply_decision(
        submitted.model_copy(update={"status": PublicationStatus.IN_REVIEW,
                                     "current_reviewer_id": "REV-1"}),
        decision("approve"), at=NOW,
    )
    s.publish(reviewed, actor_id="CUR-1", at=NOW)
    assert len(s.audit_log) == 3



# ── 以下来自 2026-07-29 的独立审查：只有 submit() 检查授权 ──


def test_unregistered_actor_cannot_publish():
    """后果最重的动作——把内容送进学生端广场——曾经是唯一不需要身份的。"""
    empty = PublishingService()
    with pytest.raises(ScopeDenied):
        empty.publish(submission(PublicationStatus.APPROVED), actor_id="ATTACKER", at=NOW)
    assert len(empty.violations) == 1
    assert empty.violations[0].reason == "no_grant"


def test_unregistered_reviewer_cannot_approve():
    empty = PublishingService()
    with pytest.raises(ScopeDenied):
        empty.apply_decision(
            submission(PublicationStatus.IN_REVIEW, current_reviewer_id="REV-1"),
            decision("approve"), at=NOW,
        )
    assert len(empty.violations) == 1


def test_unregistered_actor_cannot_withdraw():
    empty = PublishingService()
    with pytest.raises(ScopeDenied):
        empty.withdraw(submission(PublicationStatus.PUBLISHED), actor_id="ATTACKER",
                       at=NOW, reason="x")
    assert len(empty.violations) == 1


def test_publisher_cannot_act_as_reviewer():
    """角色是分开的：能投稿不等于能审自己的稿。"""
    s = service()
    bad = ModerationDecision(
        decision_id="MOD-X", submission_id="SUB-1", submission_version=1,
        reviewer_id="PUB-club",          # 这是 PUBLISHER，不是 REVIEWER
        decision="approve", reasons=(LocalizedText(zh_Hans="自批", en="self-approve"),),
        timestamp=NOW,
    )
    with pytest.raises(ScopeDenied) as excinfo:
        s.apply_decision(submission(PublicationStatus.IN_REVIEW,
                                    current_reviewer_id="PUB-club"), bad, at=NOW)
    assert excinfo.value.violation.reason == "role_not_granted"


def test_every_category_tag_is_checked_not_just_the_first():
    """分类决定内容进哪个广场入口。只查第一个，后面挂的就绕过了授权。"""
    s = service()
    with pytest.raises(ScopeDenied) as excinfo:
        s.submit(submission(category_tags=("workshop", "internship", "scholarship")),
                 when=TODAY, at=NOW)
    assert excinfo.value.violation.reason == "category_not_allowed"
    assert excinfo.value.violation.attempted_category in {"internship", "scholarship"}


def test_all_authorised_categories_pass():
    s = service()
    s.register(grant(allowed_categories=("workshop", "competition")))
    updated = s.submit(submission(category_tags=("workshop", "competition")),
                       when=TODAY, at=NOW)
    assert updated.status is PublicationStatus.SUBMITTED
