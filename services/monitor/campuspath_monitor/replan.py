"""Event Monitor & Replan Scheduler（Spec §16.9、D3）。**零 LLM。**

它只做一件事：**算出变化影响到哪里，以及影响不到哪里。**
生成新计划是 A5 的事——本模块只交出 :class:`AffectedScope` 给 A0。

为什么"影响不到哪里"同样要算出来：T5（Replan Correctness ≥ 85%）判的是
"只改受影响路径 + 合理替代"。只给受影响列表，无法证伪"顺手把别的也改了"。
Spec §16.9 也反复强调"不推翻无关长期目标"。

去抖（debounce）：同一学生的同类触发在窗口内合并成一次，
否则学生连改五个日程会触发五次全量重规划，直接拖垮 T10 的 P95。
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta

from campuspath_contracts.common import LocalizedText
from campuspath_contracts.messages import render
from campuspath_contracts.pathway import (
    AffectedScope,
    PathwayVersion,
    PlanItem,
    PlanItemKind,
    ReplanTrigger,
    ReplanTriggerType,
)

#: 同类触发在此窗口内合并。产品规则：够短以致学生察觉不到延迟，
#: 够长以致连续几次编辑只重算一次。
DEBOUNCE_WINDOW = timedelta(seconds=90)

#: 一串连续编辑最多被推迟这么久。**没有这个上界，去抖会变成饥饿**：
#: 窗口若锚在"上一条被保留的事件"上，每次合并都重置计时，
#: 一个每 80 秒改一次日程的学生可以一小时不被重规划，时长不限。
MAX_DEBOUNCE_DELAY = timedelta(minutes=5)

#: 哪些触发器只影响近期行动层，不该动长期路径（Spec §16.9）。
LOCAL_ONLY_TRIGGERS: frozenset[ReplanTriggerType] = frozenset({
    ReplanTriggerType.CALENDAR_CHANGE,
    ReplanTriggerType.WEEKLY_OVERLOAD,
    ReplanTriggerType.STUDENT_DECLINED,
    # 学生自己加了一个机会：围着原主路线排，不推翻长期目标。
    ReplanTriggerType.STUDENT_ADDED_OPPORTUNITY,
})


@dataclasses.dataclass(frozen=True)
class ChangeEvent:
    """一条外部变化。``subject_id`` 指向变了的东西，不是学生。"""

    event_id: str
    student_id: str
    trigger_type: ReplanTriggerType
    subject_id: str
    detected_at: datetime


def debounce(
    events: list[ChangeEvent],
    *,
    window: timedelta = DEBOUNCE_WINDOW,
    max_delay: timedelta = MAX_DEBOUNCE_DELAY,
) -> list[ChangeEvent]:
    """同一学生 + 同一触发类型在窗口内只保留**最后一条**。

    保留最后一条而不是第一条：学生连改三次日程，该重算的是最终状态。

    窗口锚在**这一串的第一条**上，并受 ``max_delay`` 封顶。
    此前锚在"上一条被保留的事件"上，每次合并都重置计时——
    实测一个每 80 秒改一次日程的学生，连续一小时一次都不会被重规划。
    """
    ordered = sorted(events, key=lambda e: (e.student_id, e.trigger_type.value, e.detected_at))
    kept: list[ChangeEvent] = []
    run_start: datetime | None = None
    for event in ordered:
        if kept:
            last = kept[-1]
            same = (last.student_id == event.student_id
                    and last.trigger_type is event.trigger_type)
            within_window = event.detected_at - last.detected_at <= window
            within_cap = (
                run_start is not None and event.detected_at - run_start <= max_delay
            )
            if same and within_window and within_cap:
                kept[-1] = event          # 用更新的替换掉，但计时不重置
                continue
        kept.append(event)
        run_start = event.detected_at
    return sorted(kept, key=lambda e: e.detected_at)


def _depends_on(items: dict[str, PlanItem], root_ids: set[str]) -> set[str]:
    """沿依赖边向下传播：受影响项的下游也受影响。"""
    affected = set(root_ids)
    changed = True
    while changed:
        changed = False
        for item in items.values():
            if item.plan_item_id in affected:
                continue
            if any(dep in affected for dep in item.dependencies):
                affected.add(item.plan_item_id)
                changed = True
    return affected


class MissingHorizon(ValueError):
    """局部触发器需要知道每个计划项的时间尺度，而调用方没给全。"""


def compute_scope(
    event: ChangeEvent,
    pathway: PathwayVersion,
    *,
    horizon_of: dict[str, str],
) -> AffectedScope:
    """算出 ``event`` 影响到 ``pathway`` 的哪些部分。

    ``horizon_of`` 给出每个计划项属于哪个时间尺度，**必填**。
    ``LOCAL_ONLY_TRIGGERS`` 的事件不会波及 ``long_term`` 的项——
    "日历改了一个会议"不该推翻十八个月的路径（Spec §16.9）。

    此前它可选且默认空字典，缺失时按 ``this_term`` 处理：调用方忘了传，
    这条保护就**静默失效**，日历变动照样波及长期目标。既不能默认放行，
    也不宜默认全部保护（那样局部重规划什么都改不动），只能要求说清楚。
    """
    items = {item.plan_item_id: item for item in pathway.plan_items}
    if event.trigger_type in LOCAL_ONLY_TRIGGERS:
        missing = sorted(set(items) - set(horizon_of))
        if missing:
            raise MissingHorizon(
                f"{event.trigger_type.value} 只影响近期层，必须知道每个计划项的时间尺度；"
                f"以下项缺 horizon：{missing}"
            )

    direct = {
        item.plan_item_id for item in pathway.plan_items
        if item.subject_id == event.subject_id
    }
    if event.trigger_type is ReplanTriggerType.WEEKLY_OVERLOAD:
        # 超载影响的是这一周排了东西的所有项，而不是某一个主体
        direct = {
            item.plan_item_id for item in pathway.plan_items
            if item.kind is not PlanItemKind.MILESTONE
        }

    affected = _depends_on(items, direct)

    if event.trigger_type in LOCAL_ONLY_TRIGGERS:
        affected = {pid for pid in affected if horizon_of[pid] != "long_term"}

    unaffected = set(items) - affected

    # 理由走双语模板目录（messages.py）：这句话会直接显示给学生，
    # 它就是 UI 文案。曾经两侧填同一串中文，英文界面里因此夹着中文。
    known = {
        ReplanTriggerType.CALENDAR_CHANGE,
        ReplanTriggerType.WEEKLY_OVERLOAD,
        ReplanTriggerType.STUDENT_DECLINED,
        ReplanTriggerType.NEW_GRADE,
        ReplanTriggerType.OPPORTUNITY_CHANGE,
        ReplanTriggerType.GOAL_CONFIDENCE_SHIFT,
        ReplanTriggerType.STUDENT_ADDED_OPPORTUNITY,
    }
    key = (f"replan.{event.trigger_type.value}" if event.trigger_type in known
           else "replan.default")

    return AffectedScope(
        affected_plan_item_ids=tuple(sorted(affected)),
        affected_goal_ids=(),
        affected_milestone_ids=tuple(sorted(
            m.milestone_id for m in pathway.milestones
            if set(m.plan_item_ids) & affected
        )),
        unaffected_plan_item_ids=tuple(sorted(unaffected)),
        rationale=render(key),
    )


def build_trigger(
    event: ChangeEvent, pathway: PathwayVersion, scope: AffectedScope
) -> ReplanTrigger:
    urgency = "high" if event.trigger_type in {
        ReplanTriggerType.WEEKLY_OVERLOAD, ReplanTriggerType.OPPORTUNITY_CHANGE
    } else "normal"
    return ReplanTrigger(
        trigger_id=f"RT-{event.event_id}",
        student_id=event.student_id,
        trigger_type=event.trigger_type,
        source=event.subject_id,
        detected_at=event.detected_at,
        affected_scope=scope,
        urgency=urgency,  # type: ignore[arg-type]
        old_plan_version=pathway.version,
    )
