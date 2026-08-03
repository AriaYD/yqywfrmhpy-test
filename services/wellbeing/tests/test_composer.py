"""Wellbeing Reminder Composer：模板、两次提醒状态机、最小化 outreach。

对应 D3 的 Wellbeing 条款与 B6 / B13。
双语各走一遍——`Plan §2` 的双语要求不只针对前端，模板本身就必须两份齐全。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from campuspath_contracts.common import Locale
from campuspath_contracts.common import LocalizedText
from campuspath_contracts.wellbeing import (
    NON_DIAGNOSTIC_DISCLAIMER,
    DataCoverage,
    ObservationSource,
    OutreachConsent,
    Severity,
    WellbeingCapacitySignal,
    WellbeingReminderEvent,
    WellbeingSignalType,
)

from campuspath_wellbeing.composer import (
    MAX_REMINDERS,
    REEVALUATE_AFTER,
    OutreachWithoutConsent,
    TooManyReminders,
    build_outreach,
    compose_reminder,
    decide,
    is_deliverable,
)
from campuspath_wellbeing.templates import build_template, supported_signal_types

NOW = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
LOCALES = (Locale.ZH_HANS, Locale.EN)


def signal(
    signal_type: WellbeingSignalType = WellbeingSignalType.CAPACITY_OVERLOAD,
    student_id: str = "STU-B",
) -> WellbeingCapacitySignal:
    needs_setting = signal_type in {
        WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED,
        WellbeingSignalType.RECOVERY_BLOCK_ABSENT,
    }
    source = (
        ObservationSource.SELF_REPORTED
        if signal_type is WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP
        else ObservationSource.CAPACITY_SNAPSHOT
    )
    return WellbeingCapacitySignal(
        signal_id=f"SIG-{signal_type.value}",
        student_id=student_id,
        signal_type=signal_type,
        period_start=date(2026, 9, 14),
        period_end=date(2026, 9, 20),
        observation_source=source,
        data_coverage=DataCoverage(
            window_days=7, days_with_data=7,
            prerequisite_setting_present=True if needs_setting else False,
        ),
        reference_line=LocalizedText(zh_Hans="学生自定的每周可支配容量", en="学生自定的每周可支配容量"),
        observed_value=LocalizedText(zh_Hans="计划 8.1 小时 / 可支配 -1.7 小时", en="计划 8.1 小时 / 可支配 -1.7 小时"),
        severity=Severity.BLOCKING,
        evaluated_at=NOW,
        rule_id="WB.CAPACITY.OVERLOAD",
    )


def reminder(number: int, *, delivered: datetime, action: str = "none",
             snoozed: datetime | None = None) -> WellbeingReminderEvent:
    return WellbeingReminderEvent(
        reminder_id=f"REM-{number}",
        student_id="STU-B",
        signal_ids=("SIG-x",),
        reminder_number=number,  # type: ignore[arg-type]
        template_id="T",
        locale=Locale.ZH_HANS,
        delivered_at=delivered,
        student_action=action,  # type: ignore[arg-type]
        snoozed_until=snoozed,
    )


# --------------------------------------------------------------------------
# 模板
# --------------------------------------------------------------------------


@pytest.mark.parametrize("signal_type", supported_signal_types())
@pytest.mark.parametrize("locale", LOCALES)
def test_every_signal_has_a_template_in_both_languages(signal_type, locale):
    """双语不是"英文版稍后补"：五类信号 × 两种语言都必须存在。"""
    template = build_template(signal_type, locale, observed="X", coverage="7/7")
    assert template.locale is locale
    assert template.slot1_observation
    assert "X" in template.slot1_observation


@pytest.mark.parametrize("locale", LOCALES)
def test_disclaimer_is_present_in_both_languages(locale):
    template = build_template(
        WellbeingSignalType.CAPACITY_OVERLOAD, locale, observed="x", coverage="7/7"
    )
    assert NON_DIAGNOSTIC_DISCLAIMER[locale].lower() in template.slot3_non_judgment.lower()


@pytest.mark.parametrize("locale", LOCALES)
def test_all_six_slots_are_filled(locale):
    template = build_template(
        WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED, locale,
        observed="7 天中 2 晚", coverage="7/7",
    )
    assert template.slot1_observation and template.slot2_data_source
    assert template.slot3_non_judgment and template.slot4_immediate_options
    assert template.slot5_support_options and template.slot6_consent_state


@pytest.mark.parametrize("locale", LOCALES)
def test_first_reminder_does_not_offer_counsellor_contact(locale):
    """第 1 次只给自助选项；主动联系是第 2 次才出现的分级（§16.8.3）。"""
    first = build_template(
        WellbeingSignalType.CAPACITY_OVERLOAD, locale, reminder_number=1,
        observed="x", coverage="7/7",
    )
    second = build_template(
        WellbeingSignalType.CAPACITY_OVERLOAD, locale, reminder_number=2,
        observed="x", coverage="7/7",
    )
    assert len(second.slot5_support_options) > len(first.slot5_support_options)


@pytest.mark.parametrize("locale", LOCALES)
def test_consent_slot_reflects_actual_state(locale):
    without = build_template(
        WellbeingSignalType.CAPACITY_OVERLOAD, locale,
        has_standing_consent=False, observed="x", coverage="7/7",
    )
    with_consent = build_template(
        WellbeingSignalType.CAPACITY_OVERLOAD, locale,
        has_standing_consent=True, observed="x", coverage="7/7",
    )
    assert without.slot6_consent_state != with_consent.slot6_consent_state


def test_templates_contain_no_diagnostic_vocabulary():
    """§16.8.4 明令禁止"抑郁/自杀风险"这类诊断性措辞。"""
    banned = ("抑郁", "焦虑症", "自杀", "depress", "suicid", "anxiety disorder",
              "mental illness", "diagnos")
    for signal_type in supported_signal_types():
        for locale in LOCALES:
            template = build_template(signal_type, locale, observed="x", coverage="7/7")
            blob = " ".join(
                [template.slot1_observation, template.slot2_data_source,
                 template.slot3_non_judgment, template.slot6_consent_state,
                 *template.slot4_immediate_options, *template.slot5_support_options]
            ).lower()
            for word in banned:
                if word == "diagnos":
                    # 免责声明里的 "not a medical diagnosis" 是被要求出现的
                    continue
                assert word not in blob, f"{signal_type.value}/{locale.value} 含 {word}"


# --------------------------------------------------------------------------
# 两次提醒状态机
# --------------------------------------------------------------------------


def test_no_signal_means_no_reminder():
    assert decide([], auto_rescheduling_possible=False, previous_reminders=[], now=NOW).send is False


def test_auto_reschedulable_signal_does_not_disturb_the_student():
    """§16.8.3：还能自动重排消除的，交给 A5 出 Low-load 计划，不发提醒。"""
    decision = decide(
        [signal()], auto_rescheduling_possible=True, previous_reminders=[], now=NOW
    )
    assert decision.send is False
    assert "Low-load" in decision.reason


def test_first_reminder_is_sent_when_rescheduling_cannot_fix_it():
    decision = decide(
        [signal()], auto_rescheduling_possible=False, previous_reminders=[], now=NOW
    )
    assert decision.send is True
    assert decision.reminder_number == 1


def test_second_reminder_waits_for_the_reevaluation_window():
    """已知会失败的样例：第 1 次刚发完就发第 2 次。"""
    just_sent = [reminder(1, delivered=NOW - timedelta(hours=2))]
    decision = decide(
        [signal()], auto_rescheduling_possible=False, previous_reminders=just_sent, now=NOW
    )
    assert decision.send is False
    assert "再评估" in decision.reason


def test_second_reminder_after_the_window_when_signal_persists():
    stale = [reminder(1, delivered=NOW - REEVALUATE_AFTER - timedelta(hours=1))]
    decision = decide(
        [signal()], auto_rescheduling_possible=False, previous_reminders=stale, now=NOW
    )
    assert decision.send is True
    assert decision.reminder_number == 2


@pytest.mark.parametrize(
    "action", ["acknowledged", "switched_low_load", "removed_tasks", "muted"]
)
def test_handled_signal_closes_instead_of_escalating(action):
    handled = [reminder(1, delivered=NOW - timedelta(days=3), action=action)]
    decision = decide(
        [signal()], auto_rescheduling_possible=False, previous_reminders=handled, now=NOW
    )
    assert decision.send is False


def test_snoozed_reminder_is_respected():
    snoozed = [
        reminder(1, delivered=NOW - timedelta(days=3), snoozed=NOW + timedelta(days=2))
    ]
    decision = decide(
        [signal()], auto_rescheduling_possible=False, previous_reminders=snoozed, now=NOW
    )
    assert decision.send is False
    assert "延后" in decision.reason


def test_never_a_third_reminder():
    """提醒最多两次。第三次不是关心，是 Alert Overload。"""
    two = [
        reminder(1, delivered=NOW - timedelta(days=5)),
        reminder(2, delivered=NOW - timedelta(days=3)),
    ]
    decision = decide(
        [signal()], auto_rescheduling_possible=False, previous_reminders=two, now=NOW
    )
    assert decision.send is False
    assert str(MAX_REMINDERS) in decision.reason


def test_compose_refuses_a_third_reminder():
    with pytest.raises(TooManyReminders):
        compose_reminder(
            signal(), reminder_number=3, locale=Locale.EN,
            has_standing_consent=False, now=NOW,
        )


@pytest.mark.parametrize("locale", LOCALES)
def test_composed_reminder_carries_the_measured_value(locale):
    event, template = compose_reminder(
        signal(), reminder_number=1, locale=locale, has_standing_consent=False, now=NOW
    )
    assert event.locale is locale
    assert event.template_id == template.template_id
    assert "8.1" in template.slot1_observation
    assert event.reevaluate_after == NOW + REEVALUATE_AFTER


def test_second_reminder_switches_on_low_load_mode():
    event, _ = compose_reminder(
        signal(), reminder_number=2, locale=Locale.ZH_HANS,
        has_standing_consent=False, now=NOW,
    )
    assert event.low_load_mode is True
    assert event.reevaluate_after is None


# --------------------------------------------------------------------------
# B13 最小化 outreach
# --------------------------------------------------------------------------


def consent(**kw) -> OutreachConsent:
    base = dict(
        consent_id="CONSENT-1",
        student_id="STU-B",
        scope="single_request",
        recipient_role="counseling_wellbeing_queue",
        granted_at=NOW - timedelta(hours=1),
    )
    base.update(kw)
    return OutreachConsent(**base)


def test_outreach_requires_valid_consent():
    request = build_outreach(
        signal(), consent(),
        internal_student_ref="internal-ref-9f2",
        acknowledgement_url="https://example.invalid/ack/1",
        now=NOW,
    )
    assert request.consent_id == "CONSENT-1"
    assert request.email_fields.student_requested_contact is True


def test_revoked_consent_blocks_outreach():
    with pytest.raises(OutreachWithoutConsent):
        build_outreach(
            signal(), consent(revoked_at=NOW - timedelta(minutes=1)),
            internal_student_ref="ref", acknowledgement_url="https://example.invalid/a",
            now=NOW,
        )


def test_expired_consent_blocks_outreach():
    with pytest.raises(OutreachWithoutConsent):
        build_outreach(
            signal(), consent(expires_at=NOW - timedelta(minutes=1)),
            internal_student_ref="ref", acknowledgement_url="https://example.invalid/a",
            now=NOW,
        )


def test_consent_for_another_student_blocks_outreach():
    """已知会失败的样例：拿别人的同意给这个学生发信。"""
    with pytest.raises(OutreachWithoutConsent):
        build_outreach(
            signal(student_id="STU-B"), consent(student_id="STU-C"),
            internal_student_ref="ref", acknowledgement_url="https://example.invalid/a",
            now=NOW,
        )


def test_outreach_carries_only_whitelisted_fields():
    request = build_outreach(
        signal(), consent(),
        internal_student_ref="internal-ref-9f2",
        acknowledgement_url="https://example.invalid/ack/1",
        now=NOW,
    )
    payload = request.email_fields.model_dump()
    assert set(payload) == {
        "internal_student_ref", "student_requested_contact", "trigger_category",
        "triggered_at", "consent_receipt_id", "acknowledgement_url",
    }
    blob = str(payload).lower()
    for leak in ("course", "calendar", "reflection", "profile", "goal", "sleep hours"):
        assert leak not in blob


def test_sent_is_not_the_same_as_supported():
    """§16.8.4：不得把 `email accepted` 当作学生已获得支持。"""
    request = build_outreach(
        signal(), consent(), internal_student_ref="ref",
        acknowledgement_url="https://example.invalid/a", now=NOW,
    )
    assert is_deliverable(request) is False
    assert is_deliverable(request.model_copy(update={"delivery_status": "sent"})) is False
    assert is_deliverable(request.model_copy(update={"delivery_status": "claimed"})) is True
