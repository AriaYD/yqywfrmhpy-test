"""International Student Context Pack → Rules 凭据（B1，2026-08-02）。

队友的求值器（vendored 于 ``campuspath_packs``）零 LLM、needs_confirmation
兜底，但它自铸的 ``VAL-*`` digest 不在本 Registry 的签发链上——B8 闸门
（形状 + 签发 + verdict 三层）只认 Rules 签发的 validation_id。本模块是
唯一的桥：调求值器 → 把信封转成 ``ValidationReason`` → **Rules 签发真凭据**，
Pack 自己的 digest 与 rule_ids 记入 reasons 留痕，审计链两头都接上。

信封状态 → verdict 的映射是收敛的（不放大权限）：
- eligible_now        → SATISFIED（Pack 数据齐、规则通过、复核未过期时才可能出现）
- future_eligible     → NEEDS_CONFIRMATION（"以后可达"不是"现在放行"）
- needs_confirmation  → NEEDS_CONFIRMATION
- ineligible_current_cycle → VIOLATED
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from campuspath_contracts.common import LocalizedText, SourceRef
from campuspath_contracts.validation import (
    ConstraintValidation,
    RuleCategory,
    ValidationReason,
    Verdict,
)
from campuspath_packs import evaluate_intl_context

_STATE_VERDICT: dict[str, Verdict] = {
    "eligible_now": Verdict.SATISFIED,
    "future_eligible": Verdict.NEEDS_CONFIRMATION,
    "needs_confirmation": Verdict.NEEDS_CONFIRMATION,
    "ineligible_current_cycle": Verdict.VIOLATED,
}


def evaluate_context_pack(
    engine,
    profile_context: dict[str, Any],
    opportunity: dict[str, Any] | None = None,
    *,
    today: date,
    now: datetime | None = None,
    subject_context: str = "",
) -> tuple[dict[str, Any], ConstraintValidation]:
    """求值 + 签发。返回（原始信封, Rules 凭据）。

    ``engine`` 是 ``RulesEngine``——签发走它的 registry，与资格/先修
    同一条链。信封原样返回给上层（前端要展示 sources/preparation 等），
    但**任何进入计划的结论只能引用这里签发的 validation_id**。
    """
    now = now or datetime.now(timezone.utc)
    envelope = evaluate_intl_context(profile_context, opportunity, as_of=today)
    state = envelope["eligibility_state"]
    verdict = _STATE_VERDICT[state]

    reasons: list[ValidationReason] = [
        ValidationReason(
            rule_id="CTXPACK.STATE",
            category=RuleCategory.CONTEXT_PACK,
            verdict=verdict,
            message=LocalizedText(
                zh_Hans=f"国际学生规则包判定：{state}（Pack {envelope['pack_version'] or '未适用'}）",
                en=f"Context Pack decision: {state} (pack {envelope['pack_version'] or 'n/a'})",
            ),
            observed=f"pack_digest={envelope['validation_id']}",
            expected=None,
        )
    ]
    for rule_id in envelope["applicable_rule_ids"]:
        reasons.append(ValidationReason(
            rule_id=f"CTXPACK.{rule_id}",
            category=RuleCategory.CONTEXT_PACK,
            verdict=verdict,
            message=LocalizedText(
                zh_Hans=f"适用规则 {rule_id}（官方来源见信封 source_links）",
                en=f"Applicable rule {rule_id} (official sources in envelope)",
            ),
            observed=None,
            expected=None,
        ))
    if envelope["review_required"]:
        reasons.append(ValidationReason(
            rule_id="CTXPACK.REVIEW_REQUIRED",
            category=RuleCategory.CONTEXT_PACK,
            verdict=Verdict.NEEDS_CONFIRMATION,
            message=LocalizedText(
                zh_Hans="Pack 或其规则/来源待人工政策复核，结论以复核后为准",
                en="Pack, rules, or sources pending human policy review",
            ),
            observed=None,
            expected=None,
        ))

    subject = SourceRef(
        entity_type="context_pack_evaluation",
        entity_id=(opportunity or {}).get("opportunity_id", "intl-student-context"),
        entity_version=envelope["pack_version"],
    )
    validation = engine._issue(
        subject_ref=subject,
        verdict=verdict,
        reasons=tuple(reasons),
        now=now,
        # 政策会变：凭据活到 Pack 的下一个复核日就该重签
        expires_at=None,
        # 审查 #16：context 绑定主体（student_id），与 validate_eligibility 同口径——
        # 同一 Pack 结论对不同学生不共用一个 validation_id
        context=f"intl-pack:{subject_context}:{envelope['validation_id']}",
    )
    return envelope, validation


def issue_prep_item_validation(
    engine,
    *,
    subject_id: str,
    student_id: str,
    detail: str,
    pack_digest: str,
    pack_version: str | None,
    now: datetime,
) -> ConstraintValidation:
    """为 Pack 派生的准备/核实动作签发能背书 ``PlanItem(kind=action)`` 的凭据。

    B8 的主体绑定要求 ``SourceRef(entity_type="action", entity_id=subject_id)``
    与 PlanItem 的 kind/subject_id 逐字对齐（pathway.enforce_validation_binding）。
    判定恒为 NEEDS_CONFIRMATION——Spec §16.4 明确允许"先安排对
    needs_confirmation 的核实动作"，这正是这类计划项存在的理由；
    Pack 自己的 digest 记入 reasons 留痕，审计链与主凭据同构。
    """
    subject = SourceRef(
        entity_type="action", entity_id=subject_id, entity_version=pack_version,
    )
    reasons = (
        ValidationReason(
            rule_id="CTXPACK.PREP_ITEM",
            category=RuleCategory.CONTEXT_PACK,
            verdict=Verdict.NEEDS_CONFIRMATION,
            message=LocalizedText(
                zh_Hans=f"国际学生规则包派生的准备/核实动作：{detail}",
                en=f"Preparation/verification action derived from the Context Pack: {detail}",
            ),
            observed=f"pack_digest={pack_digest}",
            expected=None,
        ),
    )
    return engine._issue(
        subject_ref=subject,
        verdict=Verdict.NEEDS_CONFIRMATION,
        reasons=reasons,
        now=now,
        expires_at=None,
        # codex #6：context 必须纳入 pack_digest——digest 变了（Pack 内容或
        # 档案输入变了）reasons 就变，同 id 不同 decision_key 会被 Registry
        # 以"不可改判"拒绝，pathway 读取直接 500。digest 进 context 让
        # 每个 Pack 修订签发各自的新 id，旧 id 留在审计链里。
        context=f"intl-prep:{student_id}:{subject_id}:{pack_digest}",
    )
