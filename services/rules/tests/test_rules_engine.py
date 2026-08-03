"""Rules Engine：四态资格、容量、保护区块、Wellbeing 阈值、凭据签发。

对应 D3 的验收条款与 B1 / B2 / B6 / B8。
每组都带**已知会失败的样例**——只测 happy path 的规则引擎等于没测。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CapacitySnapshot,
)
from campuspath_contracts.common import Provenance, SourceRef, TimeRange
from campuspath_contracts.opportunity import (
    EligibilityRule,
    EligibilityRuleKind,
    EligibilityStateName,
    Opportunity,
    OpportunityType,
)
from campuspath_contracts.profile import EnergyProfile
from campuspath_contracts.validation import Verdict
from campuspath_contracts.wellbeing import WellbeingSignalType

from campuspath_rules.capacity_rules import (
    find_capacity_violations,
    find_protected_block_violations,
)
from campuspath_rules.eligibility import StudentEligibilityFacts, assess
from campuspath_rules.engine import RulesEngine
from campuspath_rules.prerequisites import AcademicRecord
from campuspath_rules.wellbeing import (
    SleepObservation,
    WellbeingInputs,
    evaluate_signals,
)

TODAY = date(2026, 9, 15)
NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)


def _provenance() -> Provenance:
    return Provenance(source="seed", retrieved_at=NOW, parser_version="test/1.0")


def opportunity(*rules: EligibilityRule, deadline_offset: int = 30, oid="OPP-1") -> Opportunity:
    return Opportunity(
        opportunity_id=oid,
        type=OpportunityType.INTERNSHIP,
        title="合成实习（Demo）",
        organizer="合成公司（Demo）",
        eligibility_rules=tuple(rules),
        deadline=datetime.combine(
            TODAY + timedelta(days=deadline_offset), datetime.min.time(), tzinfo=timezone.utc
        ),
        official_url="https://example.invalid/opp",
        source_id="SRC-1",
        provenance=_provenance(),
    )


def facts(year: int = 2, *completed: str, visa: bool = False, cgpa: float | None = None,
          future_offerings=None):
    return StudentEligibilityFacts(
        student_id="STU-A",
        year_level=year,
        program_id="BSC-COMP",
        academic=AcademicRecord(completed=frozenset(completed)),
        has_visa_constraint=visa,
        cgpa=cgpa,
        future_offerings=future_offerings,
    )


def year_rule(expr: str, tier: str = "organizer_structured") -> EligibilityRule:
    return EligibilityRule(
        kind=EligibilityRuleKind.YEAR_LEVEL, expression=expr, source_tier=tier
    )


# --------------------------------------------------------------------------
# 四态资格
# --------------------------------------------------------------------------


def test_no_rules_means_eligible_now():
    outcome = assess(opportunity(), facts(), TODAY)
    assert outcome.state is EligibilityStateName.ELIGIBLE_NOW


def test_year_gate_met():
    outcome = assess(opportunity(year_rule("Year 3 or above")), facts(3), TODAY)
    assert outcome.state is EligibilityStateName.ELIGIBLE_NOW


def test_year_gate_becomes_future_eligible_not_ineligible():
    """Spec §16.1：大一面对"仅限大三"的实习，不应被永久删除。"""
    outcome = assess(opportunity(year_rule("Year 3 or above")), facts(1), TODAY)
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE
    assert outcome.next_eligibility_date is not None
    assert outcome.next_eligibility_date > TODAY


def test_ambiguous_year_becomes_needs_confirmation():
    outcome = assess(
        opportunity(year_rule("Penultimate-year students preferred", "official_page_text")),
        facts(2), TODAY,
    )
    assert outcome.state is EligibilityStateName.NEEDS_CONFIRMATION


def test_expired_deadline_is_ineligible_this_cycle():
    outcome = assess(opportunity(deadline_offset=-1), facts(), TODAY)
    assert outcome.state is EligibilityStateName.INELIGIBLE_CURRENT_CYCLE


def test_expired_deadline_outranks_a_satisfied_year_rule():
    """已知会失败的样例：截止已过却因年级满足而判成可申请。"""
    outcome = assess(
        opportunity(year_rule("Year 1 or above"), deadline_offset=-5), facts(3), TODAY
    )
    assert outcome.state is EligibilityStateName.INELIGIBLE_CURRENT_CYCLE


def test_model_inferred_rule_can_never_disqualify():
    """Spec §16.2 第 5 条。

    用 GPA 而不是 YEAR_LEVEL：审查实测，原来那条用的表达式
    "Probably final-year only" 两个年级正则都不匹配，无论守卫在不在
    都会落到 needs_confirmation——测试恒绿，守卫其实没被测到。
    换成一条**本来会淘汰学生**的规则，守卫才是载荷。
    """
    rule = EligibilityRule(
        kind=EligibilityRuleKind.GPA,
        expression="CGPA 3.5 or above",
        source_tier="model_inferred",
        mandatory=False,
    )
    outcome = assess(opportunity(rule), facts(3, cgpa=3.0), TODAY)
    assert outcome.state is EligibilityStateName.NEEDS_CONFIRMATION, (
        "模型推断把 CGPA 3.0 的学生淘汰了"
    )


def test_unmet_course_requirement_is_future_eligible():
    """课程可以补修，所以是"未来可达"而不是"本轮不合格"。"""
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011",
        source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(2), TODAY)
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE


def test_unmet_course_with_no_future_offering_is_ineligible():
    """T1/T3 裁定原因二：那门课再也不开时，「补修就能达成」是没有依据的承诺。

    ``future_offerings={}`` 是"有目录、且没有任何课在未来开"，不是"没有目录"。
    """
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011",
        source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(2, future_offerings={}), TODAY)
    assert outcome.state is EligibilityStateName.INELIGIBLE_CURRENT_CYCLE


def test_unmet_course_with_future_offering_carries_the_completion_date():
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011",
        source_tier="organizer_structured",
    )
    term_end = date(2027, 5, 21)
    outcome = assess(
        opportunity(rule), facts(2, future_offerings={"COMP 2011": term_end}), TODAY
    )
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE
    assert outcome.next_eligibility_date == term_end
    assert not outcome.next_eligibility_date_is_estimate


def test_no_catalog_keeps_the_retake_assumption():
    """``future_offerings=None`` = 调用方没有开课目录——只能沿用旧假设，不装作查过。"""
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011",
        source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(2, future_offerings=None), TODAY)
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE


def test_met_course_requirement_is_eligible_now():
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011",
        source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(2, "COMP 2011"), TODAY)
    assert outcome.state is EligibilityStateName.ELIGIBLE_NOW


def test_work_authorisation_is_always_needs_confirmation():
    """系统不掌握签证状态。不掌握 ≠ 不满足，也 ≠ 满足。"""
    rule = EligibilityRule(
        kind=EligibilityRuleKind.WORK_AUTHORIZATION,
        expression="Must hold valid HK work authorisation",
        source_tier="organizer_structured",
    )
    assert assess(opportunity(rule), facts(3), TODAY).state is (
        EligibilityStateName.NEEDS_CONFIRMATION
    )


def test_gpa_below_threshold_is_ineligible_this_cycle():
    rule = EligibilityRule(
        kind=EligibilityRuleKind.GPA, expression="CGPA >= 3.0",
        source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(3, cgpa=2.4), TODAY)
    assert outcome.state is EligibilityStateName.INELIGIBLE_CURRENT_CYCLE


def test_gpa_unknown_is_needs_confirmation_not_ineligible():
    rule = EligibilityRule(
        kind=EligibilityRuleKind.GPA, expression="CGPA >= 3.0",
        source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(3), TODAY)
    assert outcome.state is EligibilityStateName.NEEDS_CONFIRMATION


def test_future_eligible_always_carries_a_date():
    """契约要求 future_eligible 必须给日期，否则学生排不了桥接行动。"""
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011", source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(2), TODAY)
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE
    assert outcome.next_eligibility_date is not None


def test_every_state_reports_reasons():
    for rules, student in (
        ((), facts()),
        ((year_rule("Year 3 or above"),), facts(1)),
        ((year_rule("Maybe seniors"),), facts(1)),
    ):
        assert assess(opportunity(*rules), student, TODAY).reasons


# --------------------------------------------------------------------------
# B2 保护区块
# --------------------------------------------------------------------------


def _block(start_hour: int, end_hour: int, kind=AvailabilityType.PROTECTED, bid="AB-1"):
    return AvailabilityBlock(
        block_id=bid, student_id="STU-A",
        span=TimeRange(
            start=datetime(2026, 9, 16, start_hour, tzinfo=timezone.utc),
            end=datetime(2026, 9, 16, end_hour, tzinfo=timezone.utc),
        ),
        type=kind, source=BlockSource.STUDENT_DEFINED,
    )


def _slot(start_hour: int, end_hour: int) -> TimeRange:
    return TimeRange(
        start=datetime(2026, 9, 16, start_hour, tzinfo=timezone.utc),
        end=datetime(2026, 9, 16, end_hour, tzinfo=timezone.utc),
    )


def test_overlap_with_protected_block_is_a_violation():
    violations = find_protected_block_violations({"PI-1": _slot(7, 9)}, [_block(6, 8)])
    assert len(violations) == 1
    assert violations[0].overlap_minutes == 60


def test_touching_but_not_overlapping_is_fine():
    """边界相接不算重叠。差一分钟就报违规会让计划无法紧邻休息区块排。"""
    assert find_protected_block_violations({"PI-1": _slot(8, 10)}, [_block(6, 8)]) == []


def test_busy_block_is_not_protected():
    """BUSY 冲突可以协商，PROTECTED 不行——两者不能混为一谈。"""
    busy = _block(6, 10, kind=AvailabilityType.BUSY)
    assert find_protected_block_violations({"PI-1": _slot(7, 9)}, [busy]) == []


def test_violation_message_names_both_sides():
    violations = find_protected_block_violations({"PI-1": _slot(7, 9)}, [_block(6, 8)])
    described = violations[0].describe()
    assert "PI-1" in described and "AB-1" in described


# --------------------------------------------------------------------------
# B1 容量
# --------------------------------------------------------------------------


def _snapshot(planned: float, discretionary: float, overload: bool):
    return CapacitySnapshot(
        snapshot_id="CS-1", student_id="STU-A",
        period_start=TODAY, period_end=TODAY + timedelta(days=6),
        fixed_load_hours=10.0, protected_time_hours=0.0, transition_hours=0.0,
        recovery_buffer_hours=0.0, existing_flexible_hours=0.0,
        usable_free_hours=max(discretionary, 0.0),
        discretionary_capacity_hours=discretionary,
        planned_load_hours=planned, buffer_ratio=0.1, overload_signal=overload,
    )


def test_silent_overload_is_a_violation():
    """契约层已经不让这种对象被构造出来，所以这里直接构造一个"已警告"的，
    再把警告去掉——模拟实现层绕过契约写库的情形。"""
    snapshot = _snapshot(12.0, 10.0, overload=True)
    silent = snapshot.model_construct(**{**snapshot.model_dump(), "overload_signal": False})
    assert find_capacity_violations([silent])


def test_warned_overload_is_not_a_violation():
    assert find_capacity_violations([_snapshot(12.0, 10.0, overload=True)]) == []


def test_strict_mode_counts_any_overload():
    violations = find_capacity_violations(
        [_snapshot(12.0, 10.0, overload=True)], allow_warned_overload=False
    )
    assert len(violations) == 1
    assert violations[0].excess_hours == 2.0


def test_within_capacity_is_clean():
    assert find_capacity_violations([_snapshot(8.0, 10.0, overload=False)]) == []


# --------------------------------------------------------------------------
# B6 Wellbeing 阈值
# --------------------------------------------------------------------------


def _energy(**kw) -> EnergyProfile:
    base = dict(weekly_discretionary_hours=12.0, min_buffer_ratio=0.2)
    base.update(kw)
    return EnergyProfile(**base)


def _inputs(**kw) -> WellbeingInputs:
    base = dict(
        student_id="STU-A",
        period_start=TODAY,
        period_end=TODAY + timedelta(days=6),
        energy_profile=_energy(),
    )
    base.update(kw)
    return WellbeingInputs(**base)


def test_no_sleep_window_means_no_sleep_signal():
    """B6 的核心反例：日历再满，没设窗口就不许生成睡眠信号。"""
    nights = tuple(
        SleepObservation(TODAY + timedelta(days=i), 5.0) for i in range(7)
    )
    signals = evaluate_signals(_inputs(sleep_nights=nights), now=NOW)
    kinds = {s.signal_type for s in signals}
    assert WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED not in kinds


def test_sleep_signal_needs_two_compressed_nights():
    energy = _energy(sleep_window_start="00:30", sleep_window_end="07:30")
    one_night = (SleepObservation(TODAY, 6.0),) + tuple(
        SleepObservation(TODAY + timedelta(days=i), 8.0) for i in range(1, 7)
    )
    signals = evaluate_signals(
        _inputs(energy_profile=energy, sleep_nights=one_night), now=NOW
    )
    assert WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED not in {
        s.signal_type for s in signals
    }


def test_two_compressed_nights_trigger_a_blocking_signal():
    energy = _energy(sleep_window_start="00:30", sleep_window_end="07:30")
    nights = (
        SleepObservation(TODAY, 6.0),
        SleepObservation(TODAY + timedelta(days=1), 6.5),
    ) + tuple(SleepObservation(TODAY + timedelta(days=i), 8.0) for i in range(2, 7))
    signals = evaluate_signals(
        _inputs(energy_profile=energy, sleep_nights=nights), now=NOW
    )
    sleep = next(
        s for s in signals if s.signal_type is WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED
    )
    assert sleep.severity.value == "blocking"
    assert sleep.non_diagnostic is True
    assert sleep.data_coverage.prerequisite_setting_present is True


def test_no_activity_data_means_no_activity_signal():
    """没打卡 ≠ 没运动。无数据必须返回 unknown（即不生成信号）。"""
    signals = evaluate_signals(_inputs(activity_minutes=None), now=NOW)
    assert WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW not in {
        s.signal_type for s in signals
    }


def test_low_activity_is_only_informational():
    signals = evaluate_signals(_inputs(activity_minutes=40), now=NOW)
    activity = next(
        s for s in signals if s.signal_type is WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW
    )
    assert activity.severity.value == "info"


def test_recovery_signal_needs_the_preference_defined():
    capacity = _snapshot(9.0, 10.0, overload=False)
    without = evaluate_signals(
        _inputs(capacity=capacity, has_recovery_block=False), now=NOW
    )
    assert WellbeingSignalType.RECOVERY_BLOCK_ABSENT not in {
        s.signal_type for s in without
    }

    with_pref = evaluate_signals(
        _inputs(
            energy_profile=_energy(recovery_preference_defined=True),
            capacity=capacity,
            has_recovery_block=False,
        ),
        now=NOW,
    )
    assert WellbeingSignalType.RECOVERY_BLOCK_ABSENT in {s.signal_type for s in with_pref}


def test_self_reported_short_sleep_needs_three_short_days():
    two_short = (6.0, 6.0, 8.0, 8.0, 8.0, 8.0, 8.0)
    signals = evaluate_signals(_inputs(self_reported_sleep_hours=two_short), now=NOW)
    assert WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP not in {
        s.signal_type for s in signals
    }

    three_short = (6.0, 6.0, 6.0, 8.0, 8.0, 8.0, 8.0)
    signals = evaluate_signals(_inputs(self_reported_sleep_hours=three_short), now=NOW)
    reported = next(
        s for s in signals if s.signal_type is WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP
    )
    assert reported.observation_source.value == "self_reported"


def test_capacity_overload_signal():
    signals = evaluate_signals(_inputs(capacity=_snapshot(12.0, 10.0, True)), now=NOW)
    overload = next(
        s for s in signals if s.signal_type is WellbeingSignalType.CAPACITY_OVERLOAD
    )
    assert overload.severity.value == "blocking"


def test_every_signal_is_non_diagnostic():
    energy = _energy(
        sleep_window_start="00:30", sleep_window_end="07:30",
        recovery_preference_defined=True,
    )
    nights = tuple(SleepObservation(TODAY + timedelta(days=i), 5.0) for i in range(7))
    signals = evaluate_signals(
        _inputs(
            energy_profile=energy, sleep_nights=nights,
            self_reported_sleep_hours=(5.0,) * 7, activity_minutes=10,
            capacity=_snapshot(20.0, 10.0, True), has_recovery_block=False,
        ),
        now=NOW,
    )
    assert len(signals) == 5, "五类信号应当全部触发"
    assert all(s.non_diagnostic is True for s in signals)
    assert all(s.rule_id.startswith("WB.") for s in signals)


# --------------------------------------------------------------------------
# B8 凭据签发
# --------------------------------------------------------------------------


def test_engine_issues_a_verifiable_validation():
    engine = RulesEngine()
    _, validation = engine.validate_eligibility(
        opportunity(year_rule("Year 3 or above")), facts(3), TODAY, NOW
    )
    subject = SourceRef(entity_type="opportunity", entity_id="OPP-1")
    assert engine.registry.verify(validation.validation_id, subject, now=NOW)


def test_validation_id_is_deterministic():
    """同一 rule set + 同一主体 ⇒ 同一 id，评测报告才能逐字比对（D6.7）。"""
    a = RulesEngine().validate_prerequisite("COMP 2012", "COMP 2011", AcademicRecord())
    b = RulesEngine().validate_prerequisite("COMP 2012", "COMP 2011", AcademicRecord())
    assert a.validation_id == b.validation_id


def test_rule_set_version_changes_the_validation_id():
    """改了判定逻辑却复用旧 id，审计链就断了。"""
    a = RulesEngine(rule_set_version="rules/2026.07").validate_prerequisite(
        "COMP 2012", "COMP 2011", AcademicRecord()
    )
    b = RulesEngine(rule_set_version="rules/2026.08").validate_prerequisite(
        "COMP 2012", "COMP 2011", AcademicRecord()
    )
    assert a.validation_id != b.validation_id


def test_eligibility_validation_expires_with_the_deadline():
    engine = RulesEngine()
    opp = opportunity(deadline_offset=10)
    _, validation = engine.validate_eligibility(opp, facts(3), TODAY, NOW)
    assert validation.expires_at == opp.deadline

    after = datetime(2026, 10, 1, tzinfo=timezone.utc)
    subject = SourceRef(entity_type="opportunity", entity_id="OPP-1")
    assert engine.registry.verify(validation.validation_id, subject, now=after) is False


def test_prerequisite_validation_carries_reasons():
    validation = RulesEngine().validate_prerequisite(
        "COMP 2012", "COMP 2011", AcademicRecord()
    )
    assert validation.verdict is Verdict.VIOLATED
    assert validation.reasons
    assert all(r.rule_id.startswith("PREREQ.") for r in validation.reasons)


def test_capacity_validation_reports_satisfied_when_clean():
    validation = RulesEngine().validate_capacity(
        "STU-A", [_snapshot(8.0, 10.0, overload=False)], NOW
    )
    assert validation.verdict is Verdict.SATISFIED
    assert validation.reasons


def test_protected_block_validation_reports_the_overlap():
    validation = RulesEngine().validate_protected_blocks(
        "STU-A", {"PI-1": _slot(7, 9)}, [_block(6, 8)], NOW
    )
    assert validation.verdict is Verdict.VIOLATED
    assert "AB-1" in validation.reasons[0].message.zh_Hans



# ── 以下来自 2026-07-29 的独立审查：阈值与合取条件没有被任何测试钉住 ──


def test_recovery_signal_requires_both_conditions_not_either():
    """§16.8.2：「未来 7 天没有完整恢复区块，**且**计划占用超过可支配容量的 80%」。

    审查实测：把 `and` 改成 `or` 没有任何测试变红——于是任何一个没设恢复区块的
    学生都会收到提醒，无论负荷多低。那是 B6 的静默回归。
    """
    energy = _energy(recovery_preference_defined=True)
    light = _snapshot(planned=1.0, discretionary=10.0, overload=False)
    signals = evaluate_signals(
        _inputs(energy_profile=energy, capacity=light, has_recovery_block=False), now=NOW
    )
    assert WellbeingSignalType.RECOVERY_BLOCK_ABSENT not in {s.signal_type for s in signals}, (
        "负荷只有 10%，不该因为没有恢复区块就提醒"
    )

    heavy = _snapshot(planned=9.0, discretionary=10.0, overload=False)
    signals = evaluate_signals(
        _inputs(energy_profile=energy, capacity=heavy, has_recovery_block=False), now=NOW
    )
    assert WellbeingSignalType.RECOVERY_BLOCK_ABSENT in {s.signal_type for s in signals}


def test_recovery_utilisation_threshold_matters():
    """80% 这个数是产品规则。改动它必须让测试变红，否则等于没定过。"""
    from campuspath_rules.wellbeing import DEFAULT_THRESHOLDS

    assert DEFAULT_THRESHOLDS.recovery_capacity_utilisation == 0.8
    energy = _energy(recovery_preference_defined=True)
    just_under = _snapshot(planned=7.9, discretionary=10.0, overload=False)
    just_over = _snapshot(planned=8.1, discretionary=10.0, overload=False)
    assert WellbeingSignalType.RECOVERY_BLOCK_ABSENT not in {
        s.signal_type for s in evaluate_signals(
            _inputs(energy_profile=energy, capacity=just_under, has_recovery_block=False),
            now=NOW)
    }
    assert WellbeingSignalType.RECOVERY_BLOCK_ABSENT in {
        s.signal_type for s in evaluate_signals(
            _inputs(energy_profile=energy, capacity=just_over, has_recovery_block=False),
            now=NOW)
    }


def test_activity_reference_threshold_matters():
    from campuspath_rules.wellbeing import DEFAULT_THRESHOLDS

    assert DEFAULT_THRESHOLDS.activity_minutes_reference == 150
    under = evaluate_signals(_inputs(activity_minutes=149, activity_days_with_data=7), now=NOW)
    over = evaluate_signals(_inputs(activity_minutes=151, activity_days_with_data=7), now=NOW)
    assert WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW in {s.signal_type for s in under}
    assert WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW not in {s.signal_type for s in over}


def test_activity_coverage_reports_the_real_number_of_days():
    """曾经写死 7/7：学生只打卡过一次 20 分钟散步，提醒里也说"覆盖 7/7 天"。"""
    signals = evaluate_signals(
        _inputs(activity_minutes=20, activity_days_with_data=1), now=NOW
    )
    activity = next(
        s for s in signals if s.signal_type is WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW
    )
    assert activity.data_coverage.days_with_data == 1
    assert "1/7" in activity.observed_value.zh_Hans
    assert "1/7" in activity.observed_value.en



# ── 以下来自 2026-07-29 的独立审查 ──


def test_needs_confirmation_outranks_future_eligible():
    """一条规则说"升到大三就行"、另一条说"签证状态不明"。

    判成 future_eligible 会给学生一个确切日期与桥接行动，
    而那个待确认项可能让他永远不合格——系统给了一个自己站不住的承诺。
    """
    outcome = assess(
        opportunity(
            year_rule("Year 3 or above"),
            EligibilityRule(kind=EligibilityRuleKind.WORK_AUTHORIZATION,
                            expression="Must hold valid HK work authorisation",
                            source_tier="organizer_structured"),
        ),
        facts(1), TODAY,
    )
    assert outcome.state is EligibilityStateName.NEEDS_CONFIRMATION
    assert outcome.next_eligibility_date is None, "待确认状态不该附带确切日期"


def test_estimated_date_says_so():
    """契约要求 future_eligible 必须给日期；没有来源给得出时只能推算，
    那就必须说明是推算的，否则学生会当成承诺。"""
    rule = EligibilityRule(
        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
        expression="Completed COMP 2011", source_tier="organizer_structured",
    )
    outcome = assess(opportunity(rule), facts(2), TODAY)
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE
    assert outcome.next_eligibility_date_is_estimate is True
    assert any("估计" in r.zh_Hans for r in outcome.reasons)


def test_year_gate_date_is_not_an_estimate():
    """年级门槛能算出确切日期，就不该被标成估计值。"""
    outcome = assess(opportunity(year_rule("Year 3 or above")), facts(1), TODAY)
    assert outcome.state is EligibilityStateName.FUTURE_ELIGIBLE
    assert outcome.next_eligibility_date_is_estimate is False


def test_non_mandatory_rule_does_not_disqualify():
    """`mandatory` 字段此前从没被读过：一个"加分项"没满足，
    效果和硬门槛完全一样，会把学生推进 future_eligible。"""
    preferred = EligibilityRule(
        kind=EligibilityRuleKind.YEAR_LEVEL,
        expression="Year 4 or above",
        source_tier="official_page_text",
        mandatory=False,
    )
    outcome = assess(opportunity(preferred), facts(1), TODAY)
    assert outcome.state is EligibilityStateName.ELIGIBLE_NOW
    assert any("非硬性要求" in r.zh_Hans for r in outcome.reasons)
    assert any("Preferred" in r.en for r in outcome.reasons)


def test_mandatory_rule_still_gates():
    hard = EligibilityRule(
        kind=EligibilityRuleKind.YEAR_LEVEL, expression="Year 4 or above",
        source_tier="organizer_structured", mandatory=True,
    )
    assert assess(opportunity(hard), facts(1), TODAY).state is (
        EligibilityStateName.FUTURE_ELIGIBLE
    )


def test_ambiguous_gpa_threshold_is_not_guessed():
    """审查者标为"未验证推断"，实测确实成立：取第一个数字会把
    "CGPA 2.5 in the last two semesters, or 3.0 overall" 解析成 2.5，
    于是 CGPA 2.8 的学生被判成合格。读不准就交给学生确认。"""
    rule = EligibilityRule(
        kind=EligibilityRuleKind.GPA,
        expression="CGPA 2.5 in the last two semesters, or 3.0 overall",
        source_tier="official_page_text",
    )
    outcome = assess(opportunity(rule), facts(3, cgpa=2.8), TODAY)
    assert outcome.state is EligibilityStateName.NEEDS_CONFIRMATION


def test_negative_capacity_does_not_render_as_inf_percent() -> None:
    """可支配容量为负时不能出现 "inf%"。

    实测（浏览器）见过一次：`f"{float('inf'):.0%}"` 渲染成 ``inf%``，
    于是学生收到的提醒里有一个数学符号，而不是一句话。
    这条断言用**已知会触发该分支**的输入锁住它。
    """
    from campuspath_rules.wellbeing import _utilisation

    # 已安排 8h，可支配为负——学生已经在赤字里，比例是无穷大。
    # §16.6 的公式必须成立（契约会校验），所以用保护时段把可支配压到负数。
    overloaded = CapacitySnapshot(
        snapshot_id="CS-NEG", student_id="STU-A",
        period_start=TODAY, period_end=TODAY + timedelta(days=6),
        fixed_load_hours=10.0, protected_time_hours=6.0, transition_hours=0.0,
        recovery_buffer_hours=0.0, existing_flexible_hours=0.0,
        usable_free_hours=4.5, discretionary_capacity_hours=-1.5,
        planned_load_hours=8.0, buffer_ratio=-0.3, overload_signal=True,
    )
    assert _utilisation(overloaded) == float("inf")

    signals = evaluate_signals(
        _inputs(capacity=overloaded, has_recovery_block=False), now=NOW
    )
    assert signals, "这组输入本该产出信号，否则这条测试什么也没测到"
    for signal in signals:
        for side in (signal.observed_value.zh_Hans, signal.observed_value.en):
            assert "inf" not in side.lower(), side
