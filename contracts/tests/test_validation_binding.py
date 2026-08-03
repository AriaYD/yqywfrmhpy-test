"""B8 Unbacked Plan Item = 0：validation_id 的形状层与签发层。

只做其中一层是不够的：

* 只查形状 → 模型编一个 ``val_`` + 32 位十六进制就能过；
* 只查签发 → 缺字段的输出在到达闸门前就已经被当成"合法对象"传播开了。

两层都在这里被测到，包括各自的已知失败样例。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.academic import CoursePlan, CoursePlanItem, CoursePlanVariant
from campuspath_contracts.common import (
    DateRange,
    LocalizedText,
    SourceRef,
    is_wellformed_validation_id,
)
from campuspath_contracts.pathway import (
    PathwayVersion,
    PlanItem,
    PlanItemKind,
    enforce_validation_binding,
)
from campuspath_contracts.validation import (
    InMemoryValidationRegistry,
    UnbackedOutputError,
    deterministic_validation_id,
    new_validation_id,
)

from conftest import NOW, TODAY, make_validation

VALID_COURSE_VID = deterministic_validation_id(
    "rules/2026.07", SourceRef(entity_type="course", entity_id="COMP 2011")
)
VALID_OPP_VID = deterministic_validation_id(
    "rules/2026.07", SourceRef(entity_type="opportunity", entity_id="OPP-001")
)


def _plan_item(**overrides) -> dict:
    base = dict(
        plan_item_id="PI-1",
        kind=PlanItemKind.OPPORTUNITY,
        subject_id="OPP-001",
        title=LocalizedText(zh_Hans="投递实习", en="Apply for internship"),
        date_range=DateRange(start=TODAY, end=TODAY + timedelta(days=14)),
        validation_id=VALID_OPP_VID,
    )
    base.update(overrides)
    return base


def _pathway(items: tuple[PlanItem, ...], course_plan=None) -> PathwayVersion:
    return PathwayVersion(
        pathway_id="PV-1",
        student_id="S-001",
        version=1,
        created_at=NOW,
        trigger="initial",
        horizons=("this_term",),
        plan_items=items,
        course_plan=course_plan,
    )


# --------------------------------------------------------------------------
# 形状层
# --------------------------------------------------------------------------


def test_plan_item_without_validation_id_is_rejected():
    payload = _plan_item()
    payload.pop("validation_id")
    with pytest.raises(ValidationError) as excinfo:
        PlanItem(**payload)
    assert "validation_id" in str(excinfo.value)


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "val_",
        "validation-123",
        "val_XYZ",                       # 非十六进制
        "val_" + "a" * 31,               # 短一位
        "val_" + "a" * 33,               # 长一位
        "VAL_" + "a" * 32,               # 大小写错误
    ],
)
def test_malformed_validation_id_is_rejected(bad):
    with pytest.raises(ValidationError):
        PlanItem(**_plan_item(validation_id=bad))


def test_wellformed_ids_are_accepted():
    generated = new_validation_id()
    assert is_wellformed_validation_id(generated)
    item = PlanItem(**_plan_item(validation_id=generated))
    assert item.validation_id == generated


def test_deterministic_id_is_stable_across_calls():
    """D6.7 要求固定 Seed 两次跑出同样的数字；随机 id 会让报告永远有 diff。"""
    ref = SourceRef(entity_type="course", entity_id="COMP 2011")
    assert deterministic_validation_id("rules/2026.07", ref) == deterministic_validation_id(
        "rules/2026.07", ref
    )
    assert deterministic_validation_id("rules/2026.08", ref) != deterministic_validation_id(
        "rules/2026.07", ref
    )


# --------------------------------------------------------------------------
# 签发层
# --------------------------------------------------------------------------


def test_pathway_with_issued_ids_passes(registry):
    pathway = _pathway((PlanItem(**_plan_item()),))
    enforce_validation_binding(pathway, registry)  # 不抛异常即通过


def test_forged_but_wellformed_id_is_rejected(registry):
    """已知会失败的样例：格式完全正确，但 Rules 从未签发过。"""
    forged = "val_" + "0" * 32
    assert is_wellformed_validation_id(forged), "样例本身必须是形状合法的，否则测不到签发层"
    pathway = _pathway((PlanItem(**_plan_item(validation_id=forged)),))
    with pytest.raises(UnbackedOutputError) as excinfo:
        enforce_validation_binding(pathway, registry)
    assert forged in str(excinfo.value)


def test_validation_for_a_different_subject_is_rejected(registry):
    """拿 COMP 2011 的凭据去背书 OPP-001。张冠李戴同样是 unbacked。"""
    pathway = _pathway((PlanItem(**_plan_item(validation_id=VALID_COURSE_VID)),))
    with pytest.raises(UnbackedOutputError):
        enforce_validation_binding(pathway, registry)


def test_expired_validation_is_rejected(expiring_registry):
    pathway = _pathway(
        (
            PlanItem(
                **_plan_item(
                    kind=PlanItemKind.COURSE,
                    subject_id="COMP 2011",
                    validation_id=VALID_COURSE_VID,
                )
            ),
        )
    )
    with pytest.raises(UnbackedOutputError):
        enforce_validation_binding(pathway, expiring_registry)


def test_course_plan_items_are_checked_too(registry):
    """课程计划走的是另一条字段路径，不能只检查 plan_items。"""
    plan = CoursePlan(
        plan_id="CP-1",
        student_id="S-001",
        variant=CoursePlanVariant.BALANCED,
        term="2025-26_FALL",
        course_items=(
            CoursePlanItem(
                course_id="COMP 2011",
                term="2025-26_FALL",
                credits=4,
                validation_id="val_" + "1" * 32,  # 未签发
            ),
        ),
        total_credits=4,
        goal_value=0.8,
        degree_value=1.0,
        gap_value=0.5,
        explanation=LocalizedText(zh_Hans="核心必修", en="Core requirement"),
        validation_ids=("val_" + "1" * 32,),
    )
    pathway = _pathway((PlanItem(**_plan_item()),), course_plan=plan)
    with pytest.raises(UnbackedOutputError) as excinfo:
        enforce_validation_binding(pathway, registry)
    assert "COMP 2011" in str(excinfo.value)


def test_course_plan_rejects_item_whose_validation_is_not_declared():
    """CoursePlan 自身也要自洽：course_items 的凭据必须出现在 validation_ids 里。"""
    with pytest.raises(ValidationError):
        CoursePlan(
            plan_id="CP-2",
            student_id="S-001",
            variant=CoursePlanVariant.LOW_LOAD,
            term="2025-26_FALL",
            course_items=(
                CoursePlanItem(
                    course_id="COMP 2011",
                    term="2025-26_FALL",
                    credits=4,
                    validation_id=VALID_COURSE_VID,
                ),
            ),
            total_credits=4,
            goal_value=0.1,
            degree_value=1.0,
            gap_value=0.0,
            explanation=LocalizedText(zh_Hans="低负荷", en="Low load"),
            validation_ids=(VALID_OPP_VID,),  # 与课程项对不上
        )


def test_registry_refuses_silent_reissue():
    """同一个 validation_id 不能被改判——改判必须签发新 id，否则审计链断掉。"""
    from campuspath_contracts.validation import Verdict

    reg = InMemoryValidationRegistry()
    original = make_validation("course", "COMP 2011")
    reg.issue(original)
    reg.issue(original)  # 幂等重放是允许的

    # 用同一个 id 构造一份判定不同的记录（正规构造，不走 model_copy）
    changed = make_validation("course", "COMP 2011", verdict=Verdict.VIOLATED)
    assert changed.validation_id == original.validation_id
    with pytest.raises(ValueError):
        reg.issue(changed)


# ── 以下来自 2026-07-29 的独立审查 ──


def test_frozen_records_refuse_model_copy_update():
    """审查实测：一条 verdict=violated 的凭据可以被复制成 satisfied 且保留同一个 id，
    Registry 于是为这份伪造背书。frozen=True 挡赋值，挡不住 model_copy。"""
    from campuspath_contracts.validation import Verdict

    validation = make_validation("course", "COMP 2011", verdict=Verdict.VIOLATED)
    with pytest.raises(TypeError):
        validation.model_copy(update={"verdict": Verdict.SATISFIED})


def test_model_copy_update_revalidates_on_mutable_models():
    """B1/B2/B3/B6/B9 全都靠 model_validator 立起来，而 model_copy 曾经不校验。"""
    from campuspath_contracts.calendar import ProposedSlot, ScheduleConflict, ScheduleProposal
    from campuspath_contracts.common import TimeRange

    blocking = ProposedSlot(
        plan_item_id="PI-1",
        span=TimeRange(
            start=datetime(2026, 9, 16, 7, tzinfo=timezone.utc),
            end=datetime(2026, 9, 16, 9, tzinfo=timezone.utc),
        ),
        conflicts=(ScheduleConflict(conflict_type="protected_block", blocking=True),),
    )
    pending = ScheduleProposal(
        proposal_id="SP-1", student_id="S-1", proposed_slots=(blocking,),
        student_decision="pending",
    )
    with pytest.raises(ValidationError):
        pending.model_copy(update={"student_decision": "approved"})


def test_model_copy_without_update_still_works():
    """无 update 的复制是纯粹的克隆，不该被这条改动影响。"""
    validation = make_validation("course", "COMP 2011")
    assert validation.model_copy() == validation


def test_gate_rejects_a_genuinely_issued_but_violated_ruling():
    """S2：闸门曾经只查"签发过"，不查判定。

    Rules 真的签发了这条凭据、主体也完全正确——但它说的是"先修不满足"。
    拿它去背书计划项，等于证明了出处、没证明合规。
    """
    from campuspath_contracts.validation import Verdict

    reg = InMemoryValidationRegistry()
    violated = make_validation("course", "COMP 2011", verdict=Verdict.VIOLATED)
    reg.issue(violated)
    pathway = _pathway(
        (
            PlanItem(
                **_plan_item(
                    kind=PlanItemKind.COURSE, subject_id="COMP 2011",
                    validation_id=violated.validation_id,
                )
            ),
        )
    )
    with pytest.raises(UnbackedOutputError) as excinfo:
        enforce_validation_binding(pathway, reg)
    assert "violated" in str(excinfo.value)


def test_gate_accepts_needs_confirmation_because_spec_1604_allows_it():
    """§16.4：可以"先安排对 Needs confirmation 的核实动作"。

    把它一并拒掉会让那种计划项无法存在——那是矫枉过正，不是更安全。
    """
    from campuspath_contracts.validation import Verdict

    reg = InMemoryValidationRegistry()
    pending = make_validation("opportunity", "OPP-001",
                              verdict=Verdict.NEEDS_CONFIRMATION)
    reg.issue(pending)
    pathway = _pathway((PlanItem(**_plan_item(validation_id=pending.validation_id)),))
    enforce_validation_binding(pathway, reg)


def test_gate_covers_eligibility_claims_not_just_plan_items():
    """§8.9.3 说的是"每个 PlanItem、**每一条资格结论**"。"""
    reg = InMemoryValidationRegistry()
    reg.issue(make_validation("opportunity", "OPP-001"))
    pathway = _pathway((PlanItem(**_plan_item()),))
    forged = "val_" + "0" * 32
    with pytest.raises(UnbackedOutputError) as excinfo:
        enforce_validation_binding(pathway, reg, eligibility_claims={"OPP-002": forged})
    assert "eligibility:OPP-002" in str(excinfo.value)


def test_gate_explains_which_kind_of_failure_it_is():
    """只说 invalid 会让调用方无从修：分不清"模型编了个 id"与"Rules 判了违规"。"""
    reg = InMemoryValidationRegistry()
    reg.issue(make_validation("course", "COMP 2011"))
    wrong_subject = deterministic_validation_id(
        "rules/2026.07", SourceRef(entity_type="course", entity_id="COMP 2011")
    )
    pathway = _pathway(
        (PlanItem(**_plan_item(kind=PlanItemKind.OPPORTUNITY, subject_id="OPP-001",
                               validation_id=wrong_subject)),)
    )
    with pytest.raises(UnbackedOutputError) as excinfo:
        enforce_validation_binding(pathway, reg)
    assert "不是对" in str(excinfo.value)


def test_constraint_validation_is_immutable():
    validation = make_validation("course", "COMP 2011")
    with pytest.raises(ValidationError):
        validation.verdict = "violated"


def test_reissuing_the_same_ruling_is_idempotent():
    """确定性 id 只由（规则集 + 主体）决定，重新算一次时 evaluated_at 会变。

    把时刻算进同一性，同一个端点调用两次就会炸——实测过（why-not-recommended
    第二次 500）。"不可改判"说的是判定不能变。
    """
    from campuspath_contracts.validation import ConstraintValidation

    reg = InMemoryValidationRegistry()
    first = make_validation("course", "COMP 2011")
    reg.issue(first)

    # 同一判定，只是三小时后又算了一次（正规构造，不走 model_construct——
    # 后者不做嵌套模型的强制转换，拿到的 subject_ref 会是 dict）
    later = ConstraintValidation(
        validation_id=first.validation_id,
        rule_set_version=first.rule_set_version,
        subject_ref=first.subject_ref,
        verdict=first.verdict,
        reasons=first.reasons,
        evaluated_at=NOW + timedelta(hours=3),
        expires_at=first.expires_at,
    )
    reg.issue(later)
    assert reg.get(first.validation_id).evaluated_at == first.evaluated_at, (
        "重放不该覆盖最初的计算时刻"
    )


def test_reissuing_a_different_ruling_is_still_refused():
    from campuspath_contracts.validation import Verdict

    reg = InMemoryValidationRegistry()
    reg.issue(make_validation("course", "COMP 2011"))
    with pytest.raises(ValueError):
        reg.issue(make_validation("course", "COMP 2011", verdict=Verdict.VIOLATED))
