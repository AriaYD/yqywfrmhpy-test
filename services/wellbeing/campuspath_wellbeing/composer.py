"""两次提醒状态机与最小化 outreach（Spec §16.8.3–16.8.4）。**零 LLM。**

状态机（§16.8.3 流程图的代码形态）：

```
信号产生
  ├─ 还能靠自动重排消除？ → 交给 A5 出 Low-load 计划，**不发提醒**
  └─ 不能 → 第 1 次提醒
            └─ 24–72 小时后重评估
                 ├─ 信号消失或学生已处理 → 关闭
                 └─ 持续且未处理 → 第 2 次提醒（低负荷模式 + 支持选项）
                                    └─ 学生主动请求 / 已有有效 opt-in？
                                         ├─ 否 → **什么都不发给学校**
                                         └─ 是 → 最小化 outreach（白名单字段）
```

两条不变式：

* **提醒最多两次。** 第三次不是"再提醒一下"，而是 Alert Overload。
* **没有学生主动请求或有效 opt-in，就没有任何个体信息离开学生侧**（B13）。
  这不靠调用方记得判断——``build_outreach`` 拿不到有效同意就抛异常。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta

from campuspath_contracts.common import Locale
from campuspath_contracts.wellbeing import (
    OutreachConsent,
    OutreachEmailFields,
    ReminderTemplate,
    WellbeingCapacitySignal,
    WellbeingOutreachRequest,
    WellbeingReminderEvent,
    WellbeingSignalType,
)

from .templates import build_template

#: §16.8.3 的"24–72 小时后再评估"。取下界：更早重评估意味着更早关闭，
#: 而不是更早发第二次——第二次的前提是信号**持续**。
REEVALUATE_AFTER = timedelta(hours=24)

#: 提醒次数上限。改这个数等于改产品对 Alert Overload 的容忍度。
MAX_REMINDERS = 2


class OutreachWithoutConsent(PermissionError):
    """在没有有效同意的情况下试图构造 outreach。API 层据此返回 403。"""


class TooManyReminders(RuntimeError):
    """试图发第三次提醒。"""


@dataclasses.dataclass(frozen=True)
class ReminderDecision:
    """一次评估的结果。``send`` 为 False 时 ``reason`` 说明为什么不发。"""

    send: bool
    reminder_number: int | None
    reason: str


def decide(
    signals: list[WellbeingCapacitySignal],
    *,
    auto_rescheduling_possible: bool,
    previous_reminders: list[WellbeingReminderEvent],
    now: datetime,
) -> ReminderDecision:
    """决定这一轮要不要发提醒、发第几次。"""
    if not signals:
        return ReminderDecision(False, None, "无信号")

    if auto_rescheduling_possible:
        # §16.8.3：还能自动重排消除的，交给 A5 出 Low-load 计划，不打扰学生
        return ReminderDecision(
            False, None, "信号可通过自动重排消除，改为生成 Low-load 计划，不发提醒"
        )

    sent = sorted(previous_reminders, key=lambda r: r.delivered_at)
    if not sent:
        return ReminderDecision(True, 1, "信号无法通过自动重排消除，发第 1 次提醒")

    if len(sent) >= MAX_REMINDERS:
        return ReminderDecision(
            False, None, f"已发送 {len(sent)} 次提醒，达到上限 {MAX_REMINDERS}，不再提醒"
        )

    last = sent[-1]
    if last.student_action in {"switched_low_load", "removed_tasks", "acknowledged", "muted"}:
        return ReminderDecision(False, None, f"学生已处理（{last.student_action}），关闭")
    if last.snoozed_until is not None and now < last.snoozed_until:
        return ReminderDecision(False, None, "学生已延后，尚未到期")
    if now - last.delivered_at < REEVALUATE_AFTER:
        return ReminderDecision(
            False, None,
            f"距上次提醒不足 {REEVALUATE_AFTER}，按 §16.8.3 需先等待再评估",
        )
    return ReminderDecision(True, 2, "信号持续且学生未处理，发第 2 次提醒（含低负荷与支持选项）")


def compose_reminder(
    signal: WellbeingCapacitySignal,
    *,
    reminder_number: int,
    locale: Locale,
    has_standing_consent: bool,
    now: datetime,
) -> tuple[WellbeingReminderEvent, ReminderTemplate]:
    """填模板并生成提醒事件。文案全部来自模板，没有一个字是模型写的。"""
    if reminder_number > MAX_REMINDERS:
        raise TooManyReminders(f"提醒次数上限为 {MAX_REMINDERS}")

    coverage = (
        f"{signal.data_coverage.days_with_data}/{signal.data_coverage.window_days} 天"
        if locale is Locale.ZH_HANS
        else f"{signal.data_coverage.days_with_data} of {signal.data_coverage.window_days} days"
    )
    template = build_template(
        signal.signal_type,
        locale,
        reminder_number=reminder_number,
        has_standing_consent=has_standing_consent,
        # observed_value 现在是双语的：按提醒的 locale 取对应那一侧。
        # 之前它是单语中文，于是英文提醒里会嵌一段中文实测值。
        observed=(
            signal.observed_value.zh_Hans
            if locale is Locale.ZH_HANS
            else signal.observed_value.en
        ),
        coverage=coverage,
    )
    event = WellbeingReminderEvent(
        reminder_id=f"REM-{signal.student_id}-{signal.signal_type.value}-{reminder_number}",
        student_id=signal.student_id,
        signal_ids=(signal.signal_id,),
        reminder_number=reminder_number,  # type: ignore[arg-type]
        template_id=template.template_id,
        locale=locale,
        delivered_at=now,
        low_load_mode=reminder_number == 2,
        reevaluate_after=now + REEVALUATE_AFTER if reminder_number == 1 else None,
    )
    return event, template


def build_outreach(
    signal: WellbeingCapacitySignal,
    consent: OutreachConsent,
    *,
    internal_student_ref: str,
    acknowledgement_url: str,
    now: datetime,
) -> WellbeingOutreachRequest:
    """构造最小化 outreach。**没有有效同意就直接抛异常，不给调用方选择。**

    字段白名单由 :class:`OutreachEmailFields` 的字段列表定义：
    课程标题、日历标题、参与人、地点、Profile、Reflection、模型推断、
    诊断性措辞在类型上就放不进去（Spec §16.8.4）。
    """
    if consent.student_id != signal.student_id:
        raise OutreachWithoutConsent("同意记录与信号属于不同学生")
    if not consent.is_valid_at(now):
        raise OutreachWithoutConsent(
            f"同意 {consent.consent_id} 在 {now.isoformat()} 无效（已撤销或已过期）"
        )

    return WellbeingOutreachRequest(
        request_id=f"REQ-{consent.consent_id}-{signal.signal_type.value}",
        consent_id=consent.consent_id,
        student_id=signal.student_id,
        trigger_category=signal.signal_type,
        email_fields=OutreachEmailFields(
            internal_student_ref=internal_student_ref,
            student_requested_contact=True,
            trigger_category=signal.signal_type,
            triggered_at=signal.evaluated_at,
            consent_receipt_id=consent.consent_id,
            acknowledgement_url=acknowledgement_url,
        ),
        requested_at=now,
        delivery_status="queued",
    )


def is_deliverable(request: WellbeingOutreachRequest) -> bool:
    """§16.8.4：``email accepted`` 不等于学生获得支持。

    只有进入 ``claimed`` 才算有人接手；``sent`` 只代表投递成功。
    调用方拿这个函数来避免把"发出去了"当成"处理完了"。
    """
    return request.delivery_status == "claimed"
