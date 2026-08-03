"""Wellbeing 五类信号的阈值判定（Spec §16.8.2）。**零 LLM，且必须如此。**

五条判定全是阈值比较，不含任何语义判断（见下表）。在全产品风险最高的数据类别上
引入模型不增加能力，只增加幻觉风险（Spec §8.9.4）。

| Signal | 触发条件 | 前置数据 |
|---|---|---|
| sleep_opportunity_compressed | 未来 7 天内 **2 晚**被计划挤压至 < 7 小时 | **必须**有学生设定的睡眠窗口 |
| self_reported_short_sleep | 近 7 天均值 < 7 小时，或 7 天中 ≥ 3 天 < 7 小时 | 学生自报 |
| activity_opportunity_low | 滚动 7 天中等强度等效活动 < 150 分钟 | 学生打卡；无数据返回 unknown |
| recovery_block_absent | 未来 7 天无完整恢复区块，**且**计划占用 > 可支配容量 80% | 学生须先定义恢复偏好 |
| capacity_overload | 计划负荷 > 可支配容量 100%，或缓冲低于学生设定下限 | CapacitySnapshot 完整 |

阈值里 7 小时与 150 分钟来自一般健康建议；"2 晚""3 天""80%"是 CampusPath
为降低误报设的**产品规则**，不是临床阈值（Spec §16.8.2 末段）。
它们集中在 :class:`WellbeingThresholds`，改一个数就等于改产品规则，会在 diff 里看到。

B6（Wellbeing False Escalation = 0）的实现方式是：
**缺前置数据就返回 None，而不是"按空白日历推断一个"。**
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone

from campuspath_contracts.calendar import AvailabilityType, CapacitySnapshot
from campuspath_contracts.profile import EnergyProfile
from campuspath_contracts.common import LocalizedText
from campuspath_contracts.messages import render
from campuspath_contracts.wellbeing import (
    DataCoverage,
    ObservationSource,
    Severity,
    WellbeingCapacitySignal,
    WellbeingSignalType,
)


@dataclasses.dataclass(frozen=True)
class WellbeingThresholds:
    """产品规则，不是临床阈值。真实试点前须由 Counseling、Student Affairs、
    隐私负责人与学生代表共同评审（Spec §16.8.2）。"""

    sleep_hours_reference: float = 7.0
    compressed_nights_required: int = 2
    self_reported_short_days_required: int = 3
    activity_minutes_reference: int = 150
    recovery_capacity_utilisation: float = 0.8
    window_days: int = 7


DEFAULT_THRESHOLDS = WellbeingThresholds()


@dataclasses.dataclass(frozen=True)
class SleepObservation:
    """某一晚睡眠窗口被计划挤压后的剩余时长。"""

    night: date
    available_hours: float


@dataclasses.dataclass(frozen=True)
class WellbeingInputs:
    """判定所需的全部输入。**没有一项是推断出来的。**"""

    student_id: str
    period_start: date
    period_end: date
    energy_profile: EnergyProfile
    capacity: CapacitySnapshot | None = None
    #: 睡眠窗口在未来 7 天每晚的剩余时长；仅当学生设置了窗口时才有意义
    sleep_nights: tuple[SleepObservation, ...] = ()
    #: 学生自报的每日睡眠小时数（近 7 天），标记 self-reported
    self_reported_sleep_hours: tuple[float, ...] = ()
    #: 学生打卡的中等强度等效活动分钟数（滚动 7 天合计）；None 表示无数据
    activity_minutes: int | None = None
    #: 上面那个数字覆盖了几天。**必须与数字一起给**——
    #: 曾经这里写死成 7/7，于是学生只打卡过一次 20 分钟散步，
    #: 提醒里照样告诉他"覆盖范围 7/7 天"。§16.8.3 槽位 2 要的正是真实覆盖范围。
    activity_days_with_data: int = 0
    #: 未来 7 天是否存在完整恢复区块
    has_recovery_block: bool = False


def _coverage(inputs: WellbeingInputs, days_with_data: int, prerequisite: bool,
              thresholds: WellbeingThresholds) -> DataCoverage:
    return DataCoverage(
        window_days=thresholds.window_days,
        days_with_data=min(days_with_data, thresholds.window_days),
        prerequisite_setting_present=prerequisite,
    )


def _signal(
    inputs: WellbeingInputs,
    signal_type: WellbeingSignalType,
    source: ObservationSource,
    coverage: DataCoverage,
    reference_line: LocalizedText,
    observed: LocalizedText,
    severity: Severity,
    rule_id: str,
    now: datetime,
) -> WellbeingCapacitySignal:
    return WellbeingCapacitySignal(
        signal_id=f"SIG-{inputs.student_id}-{signal_type.value}-{inputs.period_start}",
        student_id=inputs.student_id,
        signal_type=signal_type,
        period_start=inputs.period_start,
        period_end=inputs.period_end,
        observation_source=source,
        data_coverage=coverage,
        reference_line=reference_line,
        observed_value=observed,
        severity=severity,
        evaluated_at=now,
        rule_id=rule_id,
    )


def evaluate_signals(
    inputs: WellbeingInputs,
    *,
    thresholds: WellbeingThresholds = DEFAULT_THRESHOLDS,
    now: datetime | None = None,
) -> list[WellbeingCapacitySignal]:
    """返回本期应当生成的信号。缺前置数据的信号**不生成**，而不是猜一个。"""
    now = now or datetime.now(timezone.utc)
    energy = inputs.energy_profile
    signals: list[WellbeingCapacitySignal] = []

    # ── 1. 睡眠机会被挤压 ──────────────────────────────────────────
    has_sleep_window = bool(energy.sleep_window_start and energy.sleep_window_end)
    if has_sleep_window and inputs.sleep_nights:
        compressed = [
            night for night in inputs.sleep_nights
            if night.available_hours < thresholds.sleep_hours_reference
        ]
        if len(compressed) >= thresholds.compressed_nights_required:
            signals.append(_signal(
                inputs, WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED,
                ObservationSource.STUDENT_DEFINED_WINDOW,
                _coverage(inputs, len(inputs.sleep_nights), True, thresholds),
                render("wb.ref.sleep",
                       hours=f"{thresholds.sleep_hours_reference:.0f}"),
                render("wb.obs.sleep_compressed",
                       window=thresholds.window_days, nights=len(compressed),
                       hours=f"{thresholds.sleep_hours_reference:.0f}"),
                Severity.BLOCKING,          # 阻止该排程并生成第 1 次提醒
                "WB.SLEEP.COMPRESSED", now,
            ))

    # ── 2. 自报睡眠不足 ────────────────────────────────────────────
    reports = inputs.self_reported_sleep_hours
    if reports:
        short_days = [h for h in reports if h < thresholds.sleep_hours_reference]
        average = sum(reports) / len(reports)
        if (average < thresholds.sleep_hours_reference
                or len(short_days) >= thresholds.self_reported_short_days_required):
            signals.append(_signal(
                inputs, WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP,
                ObservationSource.SELF_REPORTED,
                _coverage(inputs, len(reports), True, thresholds),
                render("wb.ref.sleep",
                       hours=f"{thresholds.sleep_hours_reference:.0f}"),
                render("wb.obs.self_reported_sleep", days=len(reports),
                       average=f"{average:.1f}", short=len(short_days)),
                Severity.ATTENTION,         # 建议低负荷模式；不自动上报
                "WB.SLEEP.SELF_REPORTED", now,
            ))

    # ── 3. 活动量偏低 ──────────────────────────────────────────────
    # 无数据返回 unknown（即不生成信号），不能把"没打卡"当成"没运动"
    if inputs.activity_minutes is not None:
        if inputs.activity_minutes < thresholds.activity_minutes_reference:
            days = inputs.activity_days_with_data
            signals.append(_signal(
                inputs, WellbeingSignalType.ACTIVITY_OPPORTUNITY_LOW,
                ObservationSource.SELF_REPORTED,
                _coverage(inputs, days, True, thresholds),
                render("wb.ref.activity",
                       minutes=thresholds.activity_minutes_reference),
                render("wb.obs.activity", days=days,
                       window=thresholds.window_days,
                       minutes=inputs.activity_minutes),
                Severity.INFO,
                "WB.ACTIVITY.LOW", now,
            ))

    # ── 容量类信号的共同前置：CapacitySnapshot 必须**完整** ────────
    #
    # §16.8.2 对 capacity_overload 写的数据要求就是"CapacitySnapshot 完整"，
    # 而代码此前只检查 `capacity is not None`。一个还没连日历、
    # 可支配容量为 0 的学生，会被算成"占用 100%"并收到 blocking 信号——
    # 那不是超载，那是没有数据。B6 要求的正是不出现这种升级。
    capacity = inputs.capacity
    if capacity is not None and capacity.usable_free_hours <= 0:
        capacity = None

    # ── 4. 恢复区块缺失 ────────────────────────────────────────────
    if energy.recovery_preference_defined and capacity is not None:
        utilisation = _utilisation(capacity)
        if not inputs.has_recovery_block and utilisation > thresholds.recovery_capacity_utilisation:
            signals.append(_signal(
                inputs, WellbeingSignalType.RECOVERY_BLOCK_ABSENT,
                ObservationSource.CAPACITY_SNAPSHOT,
                _coverage(inputs, thresholds.window_days, True, thresholds),
                render("wb.ref.recovery"),
                # 可支配容量已经为负时 utilisation 是 inf，
                # `f"{inf:.0%}"` 会渲染成 "inf%" —— 给学生看一个数学符号
                # 而不是一句话。这种情况本来就该换一种说法。
                (render("wb.obs.recovery_no_capacity",
                        window=thresholds.window_days)
                 if utilisation == float("inf")
                 else render("wb.obs.recovery", window=thresholds.window_days,
                             utilisation=f"{utilisation:.0%}")),
                Severity.ATTENTION,
                "WB.RECOVERY.ABSENT", now,
            ))

    # ── 5. 容量超载 ────────────────────────────────────────────────
    if capacity is not None:
        over_capacity = capacity.planned_load_hours > capacity.discretionary_capacity_hours
        under_buffer = capacity.buffer_ratio < energy.min_buffer_ratio
        if over_capacity or under_buffer:
            signals.append(_signal(
                inputs, WellbeingSignalType.CAPACITY_OVERLOAD,
                ObservationSource.CAPACITY_SNAPSHOT,
                _coverage(inputs, thresholds.window_days, True, thresholds),
                render("wb.ref.capacity"),
                render("wb.obs.capacity",
                       planned=f"{capacity.planned_load_hours:.1f}",
                       available=f"{capacity.discretionary_capacity_hours:.1f}",
                       buffer=f"{capacity.buffer_ratio:.2f}",
                       floor=f"{energy.min_buffer_ratio:.2f}"),
                Severity.BLOCKING,          # 阻止静默发布该计划
                "WB.CAPACITY.OVERLOAD", now,
            ))

    return signals


def _utilisation(capacity: CapacitySnapshot) -> float:
    """计划负荷占可支配容量的比例。

    容量为 0 且计划也为 0 时返回 **0.0**，不是 1.0：
    什么都没安排不该被描述成"占满了"。曾经返回 1.0，
    于是空计划的学生会收到"计划占用可支配容量 100%"的提醒。
    """
    if capacity.planned_load_hours <= 0:
        return 0.0
    if capacity.discretionary_capacity_hours <= 0:
        return float("inf")
    return capacity.planned_load_hours / capacity.discretionary_capacity_hours
