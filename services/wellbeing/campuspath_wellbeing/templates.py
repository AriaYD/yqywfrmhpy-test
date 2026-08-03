"""六槽位提醒模板（Spec §16.8.3）。中英各一份，**零 LLM**。

为什么是模板而不是让模型写：§16.8.3 要求提醒必须包含"不代表任何医学诊断"。
模板能保证 100% 出现；模型生成存在遗漏，或措辞滑向诊断性表述的概率。
在全产品风险最高的数据类别上，这个概率不该被接受（Spec §8.9.4）。

六个槽位缺一不可：

1. 系统观察到了什么
2. 数据来自哪里、覆盖范围是什么
3. 系统**没有**作出什么判断
4. 立即可执行的选项
5. 支持选项
6. 同意状态

槽位 1 与 2 需要填入实测值（第几晚、多少小时、覆盖几天），
因此模板是带占位符的**格式串**，填充由确定性代码完成，仍然没有模型参与。
"""

from __future__ import annotations

from campuspath_contracts.common import Locale
from campuspath_contracts.wellbeing import (
    NON_DIAGNOSTIC_DISCLAIMER,
    ReminderTemplate,
    WellbeingSignalType,
)

#: 槽位 1（观察）与槽位 2（数据来源）的格式串。``{observed}`` / ``{coverage}``
#: 由 composer 用信号里的实测值填充——不是模型改写。
_OBSERVATION: dict[WellbeingSignalType, dict[Locale, str]] = {
    WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED: {
        Locale.ZH_HANS: "接下来的计划压缩了你设定的睡眠窗口：{observed}。",
        Locale.EN: "Your upcoming plan compresses the sleep window you set: {observed}.",
    },
    WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP: {
        Locale.ZH_HANS: "你自己记录的睡眠时长低于一般建议线：{observed}。",
        Locale.EN: "The sleep hours you logged are below the general reference line: {observed}.",
    },
    WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW: {
        Locale.ZH_HANS: "你记录的活动量低于每周一般建议：{observed}。",
        Locale.EN: "The activity you logged is below the weekly general reference: {observed}.",
    },
    WellbeingSignalType.RECOVERY_BLOCK_ABSENT: {
        Locale.ZH_HANS: "未来七天里没有你定义的完整恢复区块：{observed}。",
        Locale.EN: "There is no complete recovery block of the kind you defined: {observed}.",
    },
    WellbeingSignalType.CAPACITY_OVERLOAD: {
        Locale.ZH_HANS: "本周计划超出了你自己设定的可支配容量：{observed}。",
        Locale.EN: "This week's plan exceeds the capacity you set for yourself: {observed}.",
    },
}

_DATA_SOURCE: dict[Locale, str] = {
    Locale.ZH_HANS: (
        "这条提醒只用了两类数据：你在设置里填的窗口与容量，以及你自己批准过的计划。"
        "覆盖范围为 {coverage}。"
    ),
    Locale.EN: (
        "This reminder uses only two things: the windows and capacity you entered in "
        "settings, and the plan you approved. Coverage: {coverage}."
    ),
}

#: 槽位 3。**必须原样包含免责声明**，由 ReminderTemplate 的 validator 强制。
_NON_JUDGMENT: dict[Locale, str] = {
    Locale.ZH_HANS: (
        f"系统只做了一次数字比较，没有对你的健康、能力或状态作出任何判断，"
        f"更{NON_DIAGNOSTIC_DISCLAIMER[Locale.ZH_HANS]}。"
    ),
    Locale.EN: (
        f"This is a numeric comparison only. It is not a judgement about your health, "
        f"ability or state, and it is {NON_DIAGNOSTIC_DISCLAIMER[Locale.EN]}."
    ),
}

_IMMEDIATE_OPTIONS: dict[Locale, tuple[str, ...]] = {
    Locale.ZH_HANS: (
        "切换到低负荷模式，由系统重排本周计划",
        "移除本周优先级最低的任务",
        "保留恢复区块，把冲突项挪到下周",
        "暂停这类提醒",
    ),
    Locale.EN: (
        "Switch to low-load mode and let the plan be rebuilt",
        "Drop this week's lowest-priority task",
        "Keep the recovery block and move the conflict to next week",
        "Pause reminders of this kind",
    ),
}

_IMMEDIATE_OPTIONS_SECOND: dict[Locale, tuple[str, ...]] = {
    Locale.ZH_HANS: (
        "已为你准备好低负荷版本的计划，可一键切换",
        "移除本周全部非关键任务",
        "暂停这类提醒",
    ),
    Locale.EN: (
        "A low-load version of your plan is ready to apply",
        "Drop every non-critical task this week",
        "Pause reminders of this kind",
    ),
}

_SUPPORT_OPTIONS: dict[Locale, tuple[str, ...]] = {
    Locale.ZH_HANS: ("查看学校官方的支持资源",),
    Locale.EN: ("See the university's official support resources",),
}

_SUPPORT_OPTIONS_SECOND: dict[Locale, tuple[str, ...]] = {
    Locale.ZH_HANS: (
        "查看学校官方的支持资源",
        "如果你希望，可以请学校的 counselor 联系你——由你决定，随时可撤销",
    ),
    Locale.EN: (
        "See the university's official support resources",
        "If you want, you can ask a counsellor to contact you — your call, revocable at any time",
    ),
}

_CONSENT_STATE: dict[Locale, dict[bool, str]] = {
    Locale.ZH_HANS: {
        False: "当前你没有授权任何非紧急联系。没有你的明确同意，学校不会收到任何个体信息。",
        True: "你此前授权过非紧急联系。可随时在设置里撤销，撤销后立即生效。",
    },
    Locale.EN: {
        False: (
            "You have not authorised any non-urgent outreach. Without your explicit "
            "consent, nothing about you individually reaches the university."
        ),
        True: (
            "You previously authorised non-urgent outreach. You can revoke it in "
            "settings at any time, effective immediately."
        ),
    },
}


def build_template(
    signal_type: WellbeingSignalType,
    locale: Locale,
    *,
    reminder_number: int = 1,
    has_standing_consent: bool = False,
    observed: str = "",
    coverage: str = "",
) -> ReminderTemplate:
    """产出一份填好实测值的六槽位模板。

    ``ReminderTemplate`` 的 validator 会检查槽位 3 含免责声明——
    真正的强制在契约层，这里只负责填对。
    """
    return ReminderTemplate(
        template_id=f"WB.{signal_type.value}.{reminder_number}.{locale.value}",
        locale=locale,
        slot1_observation=_OBSERVATION[signal_type][locale].format(observed=observed),
        slot2_data_source=_DATA_SOURCE[locale].format(coverage=coverage),
        slot3_non_judgment=_NON_JUDGMENT[locale],
        slot4_immediate_options=(
            _IMMEDIATE_OPTIONS_SECOND[locale] if reminder_number == 2
            else _IMMEDIATE_OPTIONS[locale]
        ),
        slot5_support_options=(
            _SUPPORT_OPTIONS_SECOND[locale] if reminder_number == 2
            else _SUPPORT_OPTIONS[locale]
        ),
        slot6_consent_state=_CONSENT_STATE[locale][has_standing_consent],
    )


def supported_signal_types() -> tuple[WellbeingSignalType, ...]:
    return tuple(_OBSERVATION)
