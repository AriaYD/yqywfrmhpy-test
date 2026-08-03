"""§16.6 的六类规划信号。**零 LLM。**

Spec 说得很直接：这些信号"只触发降低强度、移动任务、提供替代项或询问学生，
**不能自动下医学结论**"。所以它们和 Wellbeing Capacity Signal 是两种东西：

| | 规划信号（本模块） | Wellbeing Capacity Signal |
|---|---|---|
| 用途 | 调整计划 | 提醒学生并可能触发支持选项 |
| 数据类别 | 排程 | 全产品风险最高的一类 |
| 前置条件 | 无 | 学生必须先显式设置窗口/偏好 |

把两者混在一起，就会出现"日历满 → 判定健康风险"这种 B6 明令禁止的推断。
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from datetime import date, timedelta

from campuspath_contracts.calendar import AvailabilityBlock, AvailabilityType, CapacitySnapshot
from campuspath_contracts.common import IntensityMode

#: 各强度模式下每周计划小时上限。学生自选，不是系统替他决定。
INTENSITY_CEILING: dict[IntensityMode, float] = {
    IntensityMode.GENTLE: 8.0,
    IntensityMode.BALANCED: 14.0,
    IntensityMode.SPRINT: 22.0,
}

#: 连续多少天没有完整休息区块算"连续"。产品规则，可配置。
CONSECUTIVE_DAYS_WITHOUT_REST = 3

#: 一天里超过多少次上下文切换算频繁。
CONTEXT_SWITCH_PER_DAY = 4

#: 一周里截止/考试集中到多少个才算"集中在同一周期"。
DEADLINE_CLUSTER = 3

#: 学生连续拒绝/延期多少次，说明真实容量可能低于设定值。
DECLINE_STREAK = 3


@dataclasses.dataclass(frozen=True)
class PlanningSignal:
    """一条规划信号。``suggested_action`` 只在四种里取值——不含任何医学动作。"""

    kind: str
    detail: str
    suggested_action: str          # reduce_intensity | move_task | offer_alternative | ask_student

    def __post_init__(self) -> None:
        allowed = {"reduce_intensity", "move_task", "offer_alternative", "ask_student"}
        if self.suggested_action not in allowed:
            raise ValueError(
                f"规划信号只能建议 {sorted(allowed)}，不得下医学结论：{self.suggested_action}"
            )


def detect(
    *,
    week_start: date,
    blocks: list[AvailabilityBlock],
    snapshot: CapacitySnapshot,
    intensity: IntensityMode,
    exam_or_deadline_days: list[date],
    consecutive_declines: int,
    buffer_squeezed_by_new_event: bool,
) -> list[PlanningSignal]:
    """六类信号一次性检出（§16.6）。"""
    signals: list[PlanningSignal] = []

    # 1. 连续多日没有完整休息区块
    rest_days = {
        b.span.start.date() for b in blocks
        if b.type is AvailabilityType.PROTECTED and "-recovery-" in b.block_id
    }
    streak = 0
    longest = 0
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        streak = 0 if day in rest_days else streak + 1
        longest = max(longest, streak)
    if longest >= CONSECUTIVE_DAYS_WITHOUT_REST:
        signals.append(PlanningSignal(
            "no_rest_block_streak",
            f"连续 {longest} 天没有完整休息区块",
            "offer_alternative",
        ))

    # 2. 课程/考试/截止集中在同一周期
    in_week = [d for d in exam_or_deadline_days if week_start <= d < week_start + timedelta(days=7)]
    if len(in_week) >= DEADLINE_CLUSTER:
        signals.append(PlanningSignal(
            "deadline_cluster",
            f"本周有 {len(in_week)} 个考试或截止日期",
            "move_task",
        ))

    # 3. 频繁上下文切换
    per_day = Counter(b.span.start.date() for b in blocks
                      if b.type in {AvailabilityType.BUSY, AvailabilityType.FLEXIBLE})
    busiest = max(per_day.values(), default=0)
    if busiest >= CONTEXT_SWITCH_PER_DAY:
        signals.append(PlanningSignal(
            "context_switching",
            f"单日最多 {busiest} 次任务切换",
            "move_task",
        ))

    # 4. 超过学生选择的强度上限
    ceiling = INTENSITY_CEILING[intensity]
    if snapshot.planned_load_hours > ceiling:
        signals.append(PlanningSignal(
            "above_intensity_ceiling",
            f"计划 {snapshot.planned_load_hours:.1f}h 超过 {intensity.value} 模式上限 {ceiling:.0f}h",
            "reduce_intensity",
        ))

    # 5. 持续拒绝或延期 → 真实容量可能低于设定值
    if consecutive_declines >= DECLINE_STREAK:
        signals.append(PlanningSignal(
            "capacity_overestimated",
            f"连续 {consecutive_declines} 次拒绝或延期，实际可支配时间可能低于设定的 "
            f"{snapshot.usable_free_hours:.1f}h",
            "ask_student",
        ))

    # 6. 临时事件挤压缓冲
    if buffer_squeezed_by_new_event or snapshot.buffer_ratio < 0:
        signals.append(PlanningSignal(
            "buffer_squeezed",
            f"缓冲比降至 {snapshot.buffer_ratio:.2f}",
            "reduce_intensity",
        ))

    return signals
