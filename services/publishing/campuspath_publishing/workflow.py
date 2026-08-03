"""Publishing, Review & Audit Service（Spec §6.9、D5、B7）。**零 LLM。**

状态机的合法迁移表在契约层（``ALLOWED_TRANSITIONS``）；这里加的是
**谁能做这次迁移**与**做完要留下什么**：

* 越权投稿被拦截 **且记录**（B7 的判定包含可追溯，只拦不记不算通过）；
* 已发布内容改了触发字段必须**重新审核**（Spec §11.3 的失败样本）；
* 每次迁移写一条审计，包含执行人、前后状态、依据。

A4 在这条链路上没有任何权限：它只能产出 `OpportunityDraft`，
草稿进不了 Catalog，也进不了学生上下文（Spec §8.9.1）。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime

from campuspath_contracts.common import ActorRole
from campuspath_contracts.opportunity import Opportunity, PublicationStatus
from campuspath_contracts.publishing import (
    ALLOWED_TRANSITIONS,
    REVIEW_TRIGGERING_FIELDS,
    ModerationDecision,
    PublicationSubmission,
    PublisherRoleGrant,
    ScopeViolation,
    TransitionNotAllowed,
    assert_transition_allowed,
)


class ScopeDenied(PermissionError):
    """越权。异常里带上 :class:`ScopeViolation`，调用方必须把它写进审计。"""

    def __init__(self, violation: ScopeViolation) -> None:
        super().__init__(
            f"{violation.principal_id} 越权：{violation.reason}"
        )
        self.violation = violation


@dataclasses.dataclass(frozen=True)
class PublishAudit:
    entry_id: str
    submission_id: str
    actor_id: str
    role: ActorRole
    from_status: PublicationStatus
    to_status: PublicationStatus
    at: datetime
    detail: str


@dataclasses.dataclass
class PublishingService:
    grants: dict[str, PublisherRoleGrant] = dataclasses.field(default_factory=dict)
    _audit: list[PublishAudit] = dataclasses.field(default_factory=list)
    _violations: list[ScopeViolation] = dataclasses.field(default_factory=list)

    @property
    def audit_log(self) -> tuple[PublishAudit, ...]:
        return tuple(self._audit)

    @property
    def violations(self) -> tuple[ScopeViolation, ...]:
        return tuple(self._violations)

    def register(self, grant: PublisherRoleGrant) -> None:
        self.grants[grant.principal_id] = grant

    # ── B7 授权检查 ─────────────────────────────────────────────────

    def _require(
        self,
        principal_id: str,
        required_role: ActorRole,
        *,
        when: date,
        at: datetime,
        organization_id: str | None = None,
        categories: tuple[str, ...] = (),
        direct_publish: bool = False,
    ) -> PublisherRoleGrant:
        """每一次状态迁移都要过这里。

        曾经只有 ``submit()`` 调用它，于是 ``publish`` / ``apply_decision`` /
        ``withdraw`` 收一个任意字符串当 actor 就照做——把内容送进学生端广场
        这个后果最重的动作，反而是唯一不需要身份的。
        """
        grant = self.grants.get(principal_id)
        org = organization_id or (grant.organization_id if grant else "<unknown>")
        category = categories[0] if categories else "<none>"

        if grant is None:
            self._deny(principal_id, org, category, None, "no_grant", at)
        if grant.role is not required_role:
            self._deny(principal_id, org, category, grant.grant_id, "role_not_granted", at)
        if not grant.is_active_on(when):
            self._deny(principal_id, org, category, grant.grant_id, "grant_expired", at)
        if organization_id is not None and grant.organization_id != organization_id:
            self._deny(principal_id, org, category, grant.grant_id, "wrong_organization", at)
        # 每一个分类都要在授权范围内。只查 category_tags[0] 时，
        # 后面挂的分类就绕过了授权——而分类正是内容进哪个广场入口的依据。
        for tag in categories:
            if tag not in grant.allowed_categories:
                self._deny(principal_id, org, tag, grant.grant_id, "category_not_allowed", at)
        if direct_publish and not grant.can_publish_directly:
            self._deny(principal_id, org, category, grant.grant_id,
                       "direct_publish_not_allowed", at)
        return grant

    def _deny(self, principal_id: str, organization_id: str, category: str,
              grant_id: str | None, reason: str, at: datetime) -> None:
        violation = ScopeViolation(
            violation_id=f"VIO-{len(self._violations) + 1:04d}",
            principal_id=principal_id,
            attempted_organization_id=organization_id,
            attempted_category=category,
            grant_id=grant_id,
            reason=reason,  # type: ignore[arg-type]
            occurred_at=at,
        )
        self._violations.append(violation)
        raise ScopeDenied(violation)

    # ── 状态迁移 ────────────────────────────────────────────────────

    def submit(
        self, submission: PublicationSubmission, *, when: date, at: datetime
    ) -> PublicationSubmission:
        self._require(
            submission.owner_principal_id, ActorRole.PUBLISHER,
            when=when, at=at,
            organization_id=submission.organization_id,
            categories=tuple(submission.category_tags),
        )
        assert_transition_allowed(submission.status, PublicationStatus.SUBMITTED)
        updated = submission.model_copy(
            update={"status": PublicationStatus.SUBMITTED, "submitted_at": at}
        )
        self._record(submission, updated, submission.owner_principal_id,
                     ActorRole.PUBLISHER, at, "投稿提交")
        return updated

    def apply_decision(
        self,
        submission: PublicationSubmission,
        decision: ModerationDecision,
        *,
        at: datetime,
        when: date | None = None,
    ) -> PublicationSubmission:
        # 审核人可以审别的组织的投稿，因此不检查 organization——但必须是 REVIEWER
        self._require(decision.reviewer_id, ActorRole.REVIEWER,
                      when=when or at.date(), at=at)
        target = decision.target_status
        assert_transition_allowed(submission.status, target)
        updated = submission.model_copy(update={"status": target})
        self._record(submission, updated, decision.reviewer_id, ActorRole.REVIEWER, at,
                     f"审核决定：{decision.decision}")
        return updated

    def publish(
        self, submission: PublicationSubmission, *, actor_id: str, at: datetime,
        when: date | None = None,
    ) -> PublicationSubmission:
        self._require(actor_id, ActorRole.CURATOR, when=when or at.date(), at=at,
                      categories=tuple(submission.category_tags))
        assert_transition_allowed(submission.status, PublicationStatus.PUBLISHED)
        updated = submission.model_copy(update={"status": PublicationStatus.PUBLISHED})
        self._record(submission, updated, actor_id, ActorRole.CURATOR, at, "发布")
        return updated

    def update_published(
        self,
        submission: PublicationSubmission,
        new_content: Opportunity,
        *,
        actor_id: str,
        at: datetime,
        when: date | None = None,
        reviewer_id: str | None = None,
    ) -> PublicationSubmission:
        """已发布内容的更新。**改了触发字段就必须重新审核**（Spec §11.3）。

        触发复审时必须同时指定 ``reviewer_id``：契约要求 ``in_review`` 有明确
        审核人，否则审核责任无归属。此前这里把状态置成 in_review 却不指定人，
        只是因为 ``model_copy`` 不校验才没报错——那不是通过，是没被检查。
        """
        self._require(actor_id, ActorRole.PUBLISHER, when=when or at.date(), at=at,
                      organization_id=submission.organization_id,
                      categories=tuple(submission.category_tags))
        changed = _changed_fields(submission.content, new_content)
        needs_review = bool(changed & REVIEW_TRIGGERING_FIELDS)
        target = PublicationStatus.UPDATED
        assert_transition_allowed(submission.status, target)
        updated = submission.model_copy(
            update={
                "status": target,
                "content": new_content.model_copy(update={"publication_status": target}),
                "draft_version": submission.draft_version + 1,
            }
        )
        detail = (
            f"更新字段 {sorted(changed)}；"
            + ("命中复审触发字段，须重新进入审核" if needs_review else "未命中复审触发字段")
        )
        self._record(submission, updated, actor_id, ActorRole.PUBLISHER, at, detail)
        if needs_review:
            if reviewer_id is None:
                raise ValueError(
                    f"更新命中复审触发字段 {sorted(changed & REVIEW_TRIGGERING_FIELDS)}，"
                    "必须指定 reviewer_id——没有明确审核人的 in_review 等于没人负责"
                )
            self._require(reviewer_id, ActorRole.REVIEWER, when=when or at.date(), at=at)
            assert_transition_allowed(target, PublicationStatus.IN_REVIEW)
            reviewed = updated.model_copy(
                update={"status": PublicationStatus.IN_REVIEW,
                        "current_reviewer_id": reviewer_id}
            )
            self._record(updated, reviewed, actor_id, ActorRole.PUBLISHER, at,
                         f"自动回到 in_review，指派给 {reviewer_id}")
            return reviewed
        return updated

    def withdraw(
        self, submission: PublicationSubmission, *, actor_id: str, at: datetime, reason: str,
        when: date | None = None,
    ) -> PublicationSubmission:
        self._require(actor_id, ActorRole.CURATOR, when=when or at.date(), at=at)
        assert_transition_allowed(submission.status, PublicationStatus.WITHDRAWN)
        updated = submission.model_copy(update={"status": PublicationStatus.WITHDRAWN})
        self._record(submission, updated, actor_id, ActorRole.CURATOR, at, f"撤下：{reason}")
        return updated

    def expire(
        self, submission: PublicationSubmission, *, at: datetime
    ) -> PublicationSubmission:
        assert_transition_allowed(submission.status, PublicationStatus.EXPIRED)
        updated = submission.model_copy(update={"status": PublicationStatus.EXPIRED})
        self._record(submission, updated, "system", ActorRole.SYSTEM, at, "截止日期已过")
        return updated

    def _record(
        self, before: PublicationSubmission, after: PublicationSubmission,
        actor_id: str, role: ActorRole, at: datetime, detail: str,
    ) -> None:
        self._audit.append(
            PublishAudit(
                entry_id=f"PUBAUD-{len(self._audit) + 1:05d}",
                submission_id=before.submission_id,
                actor_id=actor_id,
                role=role,
                from_status=before.status,
                to_status=after.status,
                at=at,
                detail=detail,
            )
        )


def _changed_fields(before: Opportunity, after: Opportunity) -> set[str]:
    b, a = before.model_dump(mode="json"), after.model_dump(mode="json")
    return {key for key in b if b[key] != a.get(key)}
