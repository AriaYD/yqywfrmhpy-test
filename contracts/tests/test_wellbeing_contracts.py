"""B6 Wellbeing False Escalation / B13 Outreach Consent Integrity，以及零 LLM 链路的模板契约。

这是全产品风险最高的数据类别，因此契约层管得最死：
没有学生显式设置就生成不了信号，没有有效同意就构造不出 outreach，
模板里没有"不代表任何医学诊断"就实例化不了。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from campuspath_contracts.common import Locale
from campuspath_contracts.common import LocalizedText
from campuspath_contracts.wellbeing import (
    NON_DIAGNOSTIC_DISCLAIMER,
    DataCoverage,
    ObservationSource,
    OutreachConsent,
    OutreachEmailFields,
    ReminderTemplate,
    Severity,
    WellbeingCapacitySignal,
    WellbeingOutreachRequest,
    WellbeingSignalType,
)

from conftest import NOW


def _coverage(prerequisite: bool = True, **kw) -> DataCoverage:
    return DataCoverage(
        window_days=kw.get("window_days", 7),
        days_with_data=kw.get("days_with_data", 7),
        prerequisite_setting_present=prerequisite,
    )


def _signal(signal_type: WellbeingSignalType, *, prerequisite: bool = True, **kw):
    return WellbeingCapacitySignal(
        signal_id="SIG-1",
        student_id="S-001",
        signal_type=signal_type,
        period_start=date(2026, 7, 29),
        period_end=date(2026, 8, 5),
        observation_source=kw.get("observation_source", ObservationSource.PLANNED_SCHEDULE),
        data_coverage=_coverage(prerequisite),
        reference_line=LocalizedText(zh_Hans="成人每 24 小时至少 7 小时", en="reference"),
        observed_value=LocalizedText(zh_Hans="未来 7 天有 2 晚被压缩至 6.5 小时", en="observed"),
        severity=kw.get("severity", Severity.BLOCKING),
        evaluated_at=NOW,
        rule_id="WB.SLEEP.COMPRESSED",
    )


# --------------------------------------------------------------------------
# B6：不得从空白日历反推
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "signal_type",
    [
        WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED,
        WellbeingSignalType.RECOVERY_BLOCK_ABSENT,
    ],
)
def test_signal_requires_explicit_student_setting(signal_type):
    """已知会失败的样例：学生没设睡眠窗口 / 恢复偏好，却生成了信号。"""
    with pytest.raises(ValidationError) as excinfo:
        _signal(signal_type, prerequisite=False)
    assert "显式设置" in str(excinfo.value)


@pytest.mark.parametrize(
    "signal_type",
    [
        WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED,
        WellbeingSignalType.RECOVERY_BLOCK_ABSENT,
    ],
)
def test_signal_with_setting_is_accepted(signal_type):
    assert _signal(signal_type, prerequisite=True).signal_type is signal_type


def test_self_reported_signal_must_declare_its_source():
    with pytest.raises(ValidationError):
        _signal(
            WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP,
            observation_source=ObservationSource.CAPACITY_SNAPSHOT,
        )


def test_non_diagnostic_flag_cannot_be_turned_off():
    with pytest.raises(ValidationError):
        WellbeingCapacitySignal(
            signal_id="SIG-2",
            student_id="S-001",
            signal_type=WellbeingSignalType.CAPACITY_OVERLOAD,
            period_start=date(2026, 7, 29),
            period_end=date(2026, 8, 5),
            observation_source=ObservationSource.CAPACITY_SNAPSHOT,
            data_coverage=_coverage(),
            reference_line=LocalizedText(zh_Hans="学生自定容量", en="reference"),
            observed_value=LocalizedText(zh_Hans="计划负荷 112%", en="observed"),
            non_diagnostic=False,  # ← 不是配置项
            evaluated_at=NOW,
            rule_id="WB.CAPACITY.OVERLOAD",
        )


def test_data_coverage_cannot_exceed_window():
    with pytest.raises(ValidationError):
        DataCoverage(window_days=7, days_with_data=8, prerequisite_setting_present=True)


# --------------------------------------------------------------------------
# 六槽位模板与免责声明
# --------------------------------------------------------------------------


def _template(locale: Locale, slot3: str | None = None) -> ReminderTemplate:
    defaults = {
        Locale.ZH_HANS: "系统只比较了你设定的窗口与计划，不代表任何医学诊断。",
        Locale.EN: "This compares your own settings with your plan; it is not a medical diagnosis.",
    }
    return ReminderTemplate(
        template_id=f"WB.REMINDER.1.{locale.value}",
        locale=locale,
        slot1_observation="计划压缩了你设定的睡眠窗口" if locale is Locale.ZH_HANS
        else "Your plan compresses the sleep window you set",
        slot2_data_source="来自你设定的窗口与未来 7 天计划" if locale is Locale.ZH_HANS
        else "From your own settings and the next 7 days of your plan",
        slot3_non_judgment=slot3 if slot3 is not None else defaults[locale],
        slot4_immediate_options=("切换低负荷模式", "移除低优先级任务"),
        slot5_support_options=("查看校方官方资源",),
        slot6_consent_state="当前未授权任何非紧急联系，可随时更改",
    )


@pytest.mark.parametrize("locale", [Locale.ZH_HANS, Locale.EN])
def test_template_requires_non_diagnostic_disclaimer(locale):
    """已知会失败的样例：slot3 写得很委婉，但没有那句话。"""
    with pytest.raises(ValidationError) as excinfo:
        _template(locale, slot3="我们只是提醒你注意休息。" if locale is Locale.ZH_HANS
                  else "Just a gentle nudge to rest.")
    assert NON_DIAGNOSTIC_DISCLAIMER[locale] in str(excinfo.value)


@pytest.mark.parametrize("locale", [Locale.ZH_HANS, Locale.EN])
def test_valid_template_passes(locale):
    template = _template(locale)
    assert NON_DIAGNOSTIC_DISCLAIMER[locale].lower() in template.slot3_non_judgment.lower()


def test_template_slots_are_all_required():
    """六个槽位缺一不可（Spec §16.8.3）。"""
    required = {
        "slot1_observation", "slot2_data_source", "slot3_non_judgment",
        "slot4_immediate_options", "slot5_support_options", "slot6_consent_state",
    }
    assert required <= set(ReminderTemplate.model_fields)
    for name in required:
        assert ReminderTemplate.model_fields[name].is_required(), f"{name} 不应有默认值"


def test_both_locales_must_exist_as_separate_templates():
    """双语要求：每种语言一份模板，不是运行时翻译一份出来。"""
    zh, en = _template(Locale.ZH_HANS), _template(Locale.EN)
    assert zh.template_id != en.template_id


# --------------------------------------------------------------------------
# B13：同意完整性
# --------------------------------------------------------------------------


def _consent(**kw) -> OutreachConsent:
    return OutreachConsent(
        consent_id=kw.get("consent_id", "CONSENT-1"),
        student_id="S-001",
        scope="single_request",
        recipient_role="counseling_wellbeing_queue",
        granted_at=NOW,
        expires_at=kw.get("expires_at"),
        revoked_at=kw.get("revoked_at"),
    )


def _email(**kw) -> OutreachEmailFields:
    return OutreachEmailFields(
        internal_student_ref=kw.get("ref", "internal-ref-9f2"),
        student_requested_contact=True,
        trigger_category=kw.get("trigger", WellbeingSignalType.CAPACITY_OVERLOAD),
        triggered_at=NOW,
        consent_receipt_id=kw.get("consent_id", "CONSENT-1"),
        acknowledgement_url="https://example.test/ack/abc",
    )


def test_outreach_request_requires_matching_consent_receipt():
    """已知会失败的样例：邮件引用了另一份同意。"""
    with pytest.raises(ValidationError) as excinfo:
        WellbeingOutreachRequest(
            request_id="REQ-1",
            consent_id="CONSENT-1",
            student_id="S-001",
            trigger_category=WellbeingSignalType.CAPACITY_OVERLOAD,
            email_fields=_email(consent_id="CONSENT-OTHER"),
            requested_at=NOW,
        )
    assert "B13" in str(excinfo.value)


def test_outreach_request_trigger_must_match_email():
    with pytest.raises(ValidationError):
        WellbeingOutreachRequest(
            request_id="REQ-2",
            consent_id="CONSENT-1",
            student_id="S-001",
            trigger_category=WellbeingSignalType.RECOVERY_BLOCK_ABSENT,
            email_fields=_email(trigger=WellbeingSignalType.CAPACITY_OVERLOAD),
            requested_at=NOW,
        )


def test_valid_outreach_request_passes():
    req = WellbeingOutreachRequest(
        request_id="REQ-3",
        consent_id="CONSENT-1",
        student_id="S-001",
        trigger_category=WellbeingSignalType.CAPACITY_OVERLOAD,
        email_fields=_email(),
        requested_at=NOW,
    )
    assert req.delivery_status == "queued"


def test_student_requested_contact_cannot_be_false():
    """没有学生主动请求就不存在这封邮件——类型上不给 False 这个取值。

    此前这条的第一个断言写成
    ``_email(...).model_copy(update={...}).model_validate({...})``：
    ``model_validate`` 是 classmethod，拿一个只有一个键的 dict 去校验，
    抛的是"其余五个必填字段缺失"，``Literal[True]`` 只是顺带的一条。
    真正发生的事是 ``model_copy`` 成功把它翻成了 False，而测试把它当成了成功。
    现在 ``model_copy`` 会重新校验（见 common.py），所以这条直接断言它抛。
    """
    with pytest.raises(ValidationError):
        _email(ref="x").model_copy(update={"student_requested_contact": False})
    with pytest.raises(ValidationError):
        OutreachEmailFields(
            internal_student_ref="ref",
            student_requested_contact=False,
            trigger_category=WellbeingSignalType.CAPACITY_OVERLOAD,
            triggered_at=NOW,
            consent_receipt_id="CONSENT-1",
            acknowledgement_url="https://example.test/ack",
        )


def test_revoked_consent_is_not_valid():
    consent = _consent(revoked_at=NOW + timedelta(hours=1))
    assert consent.is_valid_at(NOW) is True
    assert consent.is_valid_at(NOW + timedelta(hours=2)) is False


def test_expired_consent_is_not_valid():
    consent = _consent(expires_at=NOW + timedelta(days=7))
    assert consent.is_valid_at(NOW + timedelta(days=6)) is True
    assert consent.is_valid_at(NOW + timedelta(days=8)) is False


def test_recipient_role_is_locked_to_counseling_queue():
    """Spec §16.8.4：不能发给 Career Center、导师或任意邮箱。"""
    with pytest.raises(ValidationError):
        OutreachConsent(
            consent_id="C-9",
            student_id="S-001",
            scope="single_request",
            recipient_role="career_center",
            granted_at=NOW,
        )
