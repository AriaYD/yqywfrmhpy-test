"""Publisher 授权、投稿与审核记录。

D5 要求"退回修改"与"驳回"两条分支各演示一次、越权投稿被拦截一次，
所以投稿集合是**按状态机分支配额**生成的，不是随机撒点：
每条终态至少有一个样本，越权尝试单独成组并留下 :class:`ScopeViolation` 审计记录。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.common import ActorRole, LocalizedText
from campuspath_contracts.opportunity import (
    Opportunity,
    PublicationStatus,
    ValidationIssue,
    ValidationIssueSeverity,
)
from campuspath_contracts.publishing import (
    ModerationDecision,
    PublicationSubmission,
    PublisherRoleGrant,
    ScopeViolation,
)

from .config import SEED_TODAY
from .rng import pick, stream

_TZ = timezone.utc


def _dt(d: date, hour: int = 10) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=_TZ)


@dataclasses.dataclass
class PublishingBundle:
    grants: list[PublisherRoleGrant]
    submissions: list[PublicationSubmission]
    decisions: list[ModerationDecision]
    violations: list[ScopeViolation]


_ORGS = (
    ("ORG-career-center", "合成职业发展中心（Demo）", ("internship", "career_talk", "workshop", "scholarship"), True),
    ("ORG-robotics-club", "合成机器人社（Demo）", ("workshop", "competition"), False),
    ("ORG-data-club", "合成数据科学社（Demo）", ("workshop", "networking"), False),
    ("ORG-or-lab", "合成运筹实验室（Demo）", ("research",), False),
    ("ORG-hci-lab", "合成人机交互实验室（Demo）", ("research", "workshop"), False),
    ("ORG-entrepreneur", "合成创业中心（Demo）", ("competition", "networking"), False),
    ("ORG-alumni", "合成校友会（Demo）", ("career_talk", "networking"), False),
    ("ORG-scholarship", "合成奖学金办公室（Demo）", ("scholarship",), True),
    ("ORG-volunteer", "合成义工联（Demo）", ("volunteer",), False),
    ("ORG-partner-co", "合作企业（Demo）", ("internship",), False),
)


def build_publishing(
    opportunities: list[Opportunity], *, publishers: int, submissions: int
) -> PublishingBundle:
    rng = stream("publishing")
    grants: list[PublisherRoleGrant] = []
    for index, (org_id, _name, categories, direct) in enumerate(_ORGS[:publishers]):
        # 第 4 个授权刻意设成已过期，用于"授权已过期"失败样本
        expired = index == 3
        grants.append(
            PublisherRoleGrant(
                grant_id=f"GRANT-{index + 1:02d}",
                principal_id=f"PUB-{org_id}",
                organization_id=org_id,
                role=ActorRole.PUBLISHER,
                allowed_categories=categories,
                can_publish_directly=direct,
                valid_from=SEED_TODAY - timedelta(days=300),
                valid_to=(SEED_TODAY - timedelta(days=20)) if expired
                else (SEED_TODAY + timedelta(days=200)),
                granted_by="PUB-admin",
            )
        )

    # **审核员授权**。此前 Seed 里一个都没有，于是"人工审核批准"这条
    # D5 明确要求演示的分支根本跑不起来——投稿能进来，没人有权裁决。
    # 是浏览器实测点了三次裁决全拿 403 才发现的：审核端点本身是通的，
    # 缺的是被授权的人。
    grants.append(
        PublisherRoleGrant(
            grant_id="GRANT-REVIEWER-01",
            principal_id="REV-career-center",
            organization_id="ORG-career-center",
            role=ActorRole.REVIEWER,
            # 契约要求 allowed_categories 至少一项——那条约束是为**投稿方**
            # 设的（空列表等于一个什么都不授的授权）。审核方的语义不同：
            # 它要能看全，否则"这条不归我管"会变成没人处理的黑洞。
            # 这里列全所有在用分类，而不是去放宽契约——放宽了，
            # 空的投稿授权也会跟着被放行。
            allowed_categories=tuple(sorted(
                {c for _org, _name, cats, _direct in _ORGS for c in cats}
            )),
            can_publish_directly=False,
            valid_from=SEED_TODAY - timedelta(days=300),
            valid_to=SEED_TODAY + timedelta(days=200),
            granted_by="PUB-admin",
        )
    )

    # 每条终态至少一个样本；剩下的按已发布铺满
    branch_plan: list[PublicationStatus] = [
        PublicationStatus.DRAFT,
        PublicationStatus.SUBMITTED,
        PublicationStatus.AUTO_CHECKED,
        PublicationStatus.IN_REVIEW,
        PublicationStatus.CHANGES_REQUESTED,
        PublicationStatus.REJECTED,
        PublicationStatus.APPROVED,
        PublicationStatus.PUBLISHED,
        PublicationStatus.UPDATED,
        PublicationStatus.EXPIRED,
        PublicationStatus.WITHDRAWN,
        PublicationStatus.ARCHIVED,
    ]
    while len(branch_plan) < submissions:
        branch_plan.append(PublicationStatus.PUBLISHED)

    subs: list[PublicationSubmission] = []
    decisions: list[ModerationDecision] = []
    pool = [o for o in opportunities if o.type.value in
            {"workshop", "competition", "event", "club_activity", "research_position"}]

    for index, status in enumerate(branch_plan[:submissions]):
        grant = grants[index % len(grants)]
        content = pool[index % len(pool)].model_copy(
            update={
                "opportunity_id": f"OPP-SUB-{index + 1:03d}",
                "publication_status": status,
                "organizer": grant.organization_id,
            }
        )
        issues: tuple[ValidationIssue, ...] = ()
        if status in {PublicationStatus.CHANGES_REQUESTED, PublicationStatus.REJECTED}:
            issues = (
                ValidationIssue(
                    code="MISSING_ELIGIBILITY",
                    severity=ValidationIssueSeverity.BLOCKING,
                    field_path="eligibility_rules",
                    detail=LocalizedText(
                        zh_Hans="未填写资格条件，学生无法判断能否参加",
                        en="No eligibility rules provided; students cannot tell if they qualify",
                    ),
                ),
            )

        submitted_at = None if status is PublicationStatus.DRAFT else _dt(
            SEED_TODAY - timedelta(days=30 - index)
        )
        reviewer = f"REV-{(index % 3) + 1:02d}" if status is PublicationStatus.IN_REVIEW else None

        subs.append(
            PublicationSubmission(
                submission_id=f"SUB-{index + 1:03d}",
                owner_principal_id=grant.principal_id,
                organization_id=grant.organization_id,
                draft_version=1 if status is not PublicationStatus.UPDATED else 2,
                content=content,
                category_tags=(grant.allowed_categories[0],),
                source_evidence=(f"https://example.invalid/source/{index + 1}",),
                status=status,
                auto_check_issues=issues,
                submitted_at=submitted_at,
                current_reviewer_id=reviewer,
            )
        )

        decision_map = {
            PublicationStatus.CHANGES_REQUESTED: "request_changes",
            PublicationStatus.REJECTED: "reject",
            PublicationStatus.APPROVED: "approve",
            PublicationStatus.PUBLISHED: "approve",
            PublicationStatus.UPDATED: "approve",
        }
        if status in decision_map:
            decisions.append(
                ModerationDecision(
                    decision_id=f"MOD-{index + 1:03d}",
                    submission_id=f"SUB-{index + 1:03d}",
                    submission_version=1,
                    reviewer_id=f"REV-{(index % 3) + 1:02d}",
                    decision=decision_map[status],
                    reasons=(
                        LocalizedText(
                            zh_Hans="来源与必填字段核对通过" if decision_map[status] == "approve"
                            else "资格条件缺失，请补充后重新提交",
                            en="Source and required fields verified" if decision_map[status] == "approve"
                            else "Eligibility rules missing; please resubmit",
                        ),
                    ),
                    policy_checks=("source_verified", "deadline_valid"),
                    timestamp=_dt(SEED_TODAY - timedelta(days=25 - index)),
                )
            )

    # 越权尝试：四种典型原因各一次，全部被拦截且留痕（B7）。
    # 引用的授权从实际生成的 grants 里取，tiny 档授权少也不会指向不存在的 id。
    violation_specs = (
        ("wrong_organization", 1, "ORG-data-club", "workshop", 12),
        ("category_not_allowed", 2 % max(1, len(grants)), None, "internship", 9),
        ("grant_expired", 3 % max(1, len(grants)), None, "research", 5),
        ("direct_publish_not_allowed", 1 % max(1, len(grants)), None, "competition", 3),
    )
    violations: list[ScopeViolation] = []
    for index, (reason, grant_index, attempted_org, category, days_ago) in enumerate(
        violation_specs
    ):
        grant = grants[min(grant_index, len(grants) - 1)]
        violations.append(
            ScopeViolation(
                violation_id=f"VIO-{index + 1:03d}",
                principal_id=grant.principal_id,
                attempted_organization_id=attempted_org or grant.organization_id,
                attempted_category=category,
                grant_id=grant.grant_id,
                reason=reason,
                occurred_at=_dt(SEED_TODAY - timedelta(days=days_ago)),
            )
        )

    return PublishingBundle(
        grants=grants, submissions=subs, decisions=decisions, violations=violations
    )
