"""Spec §14.2 日历与容量。由 **Capacity & Calendar Service**（确定性、零 LLM）持有。

三条硬边界：

1. **Token 不进契约**。本模块没有任何 access_token / refresh_token 字段。
   凭据止步于服务内部的 Secret Manager 引用，不出现在任何可序列化的模型里，
   因此也不可能被塞进 LLM 上下文（Spec §8.9、CLAUDE.md 架构第 3 条）。
   **这一条不受采集层级影响**：二级授权放行的是标题**文本**，不是凭据。
2. **采集不得超出已授权层级**。:class:`AvailabilityBlock` 永远没有参与人、
   地点、备注字段；``title`` 只在学生授权了 :attr:`CalendarDetailLevel.EVENT_TITLES`
   时才允许有值。B5 因此从"日历详情 = 0"变成
   **"超出授权层级的采集 = 0"**——仍然是类型层事实，而且测的是真正该测的东西。
3. **写入是我们造的内容，不是读来的内容**。:class:`CalendarWriteDraft` 里的
   ``event_title`` 是 CampusPath 生成、学生预览确认后写回的文本，
   与"读取并保存学生原有事件标题"是两回事，故在边界扫描中显式豁免。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    FrozenModel,
    Identifier,
    LocalizedText,
    StrEnum,
    StudentId,
    TimeRange,
)


class CalendarProviderId(StrEnum):
    GOOGLE = "google"
    OUTLOOK = "outlook"
    FIXTURE = "fixture"  # 降级路径 R3；UI 必须明确标记


class CalendarDetailLevel(StrEnum):
    """采集层级。**两级，学生各自授权，默认只有第一级。**

    产品上的取舍：只知道忙/闲的系统只能说"你没空了"；知道标题才说得出
    "这个周三的例会也许可以缺一次"。后者是学生明确要的能力，所以它是
    一个**可选的第二级授权**，而不是默认打开、也不是永远不做。

    ``AvailabilityBlock.title`` 只在 :attr:`EVENT_TITLES` 下才允许有值，
    由 ``_title_requires_grant`` 在类型层强制——
    "没授权却带了标题"因此构造不出来，不靠调用方记得过滤。
    """

    FREE_BUSY_ONLY = "free_busy_only"
    EVENT_TITLES = "event_titles"


class AvailabilityType(StrEnum):
    """Spec §16.6 的五类时段。"""

    BUSY = "busy"
    FREE = "free"
    PROTECTED = "protected"
    BUFFER = "buffer"
    FLEXIBLE = "flexible"


class BlockSource(StrEnum):
    CALENDAR_FREEBUSY = "calendar_freebusy"
    STUDENT_DEFINED = "student_defined"
    COURSE_TIMETABLE = "course_timetable"
    DERIVED = "derived"


class CalendarConnection(CampusPathModel):
    """学生的日历授权状态。**没有 token 字段，这是有意的。**"""

    connection_id: Identifier
    student_id: StudentId
    provider: CalendarProviderId
    selected_calendar_refs: tuple[str, ...] = Field(
        default=(), description="日历的不透明 id，不含日历显示名"
    )
    scopes: tuple[str, ...] = ()
    detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY
    last_sync: datetime | None = None
    revoked_at: datetime | None = None

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None


class AvailabilityBlock(CampusPathModel):
    """一段被分类过的时间。只有起止、类型、来源——**没有内容**。"""

    block_id: Identifier
    student_id: StudentId
    span: TimeRange
    type: AvailabilityType
    source: BlockSource
    detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY
    title: str | None = Field(
        default=None, max_length=200,
        description=(
            "事件标题。**只有 detail_level 为 event_titles 时才允许有值**——"
            "学生没授权二级就带着标题的区块，在类型层构造不出来"
        ),
    )
    privacy_level: Literal["opaque", "student_defined"] = "opaque"
    reachable: bool = Field(
        default=True,
        description="跨地点无法到达的空档不计入 Usable Free Time（Spec §16.6）",
    )
    reminder_minutes_before: int | None = Field(
        default=None, ge=0, le=10080,
        description="A（2026-07-31）：学生给自己视图里的行程设的提醒。"
                    "只属于 CampusPath 视图，不回写权威日历",
    )

    @model_validator(mode="after")
    def _title_requires_grant(self) -> "AvailabilityBlock":
        """B5 的类型层落点。

        以前这里是"永远没有 title 字段"，现在是"没授权就不许有值"。
        两者同样构造不出违规对象，但后者说得出学生真正同意了什么。
        """
        if self.title is not None and self.detail_level is not CalendarDetailLevel.EVENT_TITLES:
            raise ValueError(
                "未授权 event_titles 的时段不得携带标题（B5：采集不得超出授权层级）"
            )
        return self


class CapacitySnapshot(CampusPathModel):
    """Spec §16.6 的算术结果。纯计算，可单测到小数点。"""

    snapshot_id: Identifier
    student_id: StudentId
    period_start: date
    period_end: date
    fixed_load_hours: float = Field(ge=0, description="课程、工作、通勤等固定负担")
    protected_time_hours: float = Field(ge=0, description="睡眠、用餐、恢复等保护区块")
    transition_hours: float = Field(default=0.0, ge=0)
    recovery_buffer_hours: float = Field(default=0.0, ge=0)
    existing_flexible_hours: float = Field(default=0.0, ge=0)
    usable_free_hours: float = Field(ge=0, description="已剔除碎片、深夜与不可达时段")
    discretionary_capacity_hours: float = Field(description="可为负：说明已经超载")
    planned_load_hours: float = Field(default=0.0, ge=0)
    buffer_ratio: float = Field(
        description="未安排时间占 usable_free 的比例，可为负。"
                    "**分母是 usable_free 而非 discretionary**——后者已经把 "
                    "recovery_buffer 扣掉了，再用它当分母就等于同一份缓冲收两次费"
    )
    overload_signal: bool = False

    @model_validator(mode="after")
    def _capacity_formula_holds(self) -> "CapacitySnapshot":
        """Spec §16.6 的公式必须真的成立，不能是各字段各填各的。"""
        expected = (
            self.usable_free_hours
            - self.protected_time_hours
            - self.transition_hours
            - self.recovery_buffer_hours
            - self.existing_flexible_hours
        )
        if abs(expected - self.discretionary_capacity_hours) > 0.01:
            raise ValueError(
                "discretionary_capacity_hours 与 §16.6 公式不符："
                f"期望 {expected:.2f}，实际 {self.discretionary_capacity_hours:.2f}"
            )
        if self.overload_signal is False and self.planned_load_hours > self.discretionary_capacity_hours:
            raise ValueError("planned_load 超过 discretionary_capacity 却未置 overload_signal（B1）")
        return self


class ScheduleConflict(CampusPathModel):
    conflict_type: Literal[
        "protected_block", "busy_overlap", "exam", "prerequisite_timing",
        "capacity_exceeded", "travel_infeasible"
    ]
    blocking: bool = Field(description="True 表示不得静默排程，必须显式警告或改期")
    with_block_id: Identifier | None = None
    detail: LocalizedText | None = None


class ProposedSlot(CampusPathModel):
    plan_item_id: Identifier
    span: TimeRange
    conflicts: tuple[ScheduleConflict, ...] = ()


class ScheduleProposal(CampusPathModel):
    """A5 的排程预览。学生批准前不写任何日历（Spec §15.4 规则 8）。"""

    proposal_id: Identifier
    student_id: StudentId
    plan_item_ids: tuple[Identifier, ...] = ()
    proposed_slots: tuple[ProposedSlot, ...] = ()
    assumptions: tuple[LocalizedText, ...] = ()
    student_decision: Literal["pending", "approved", "modified", "rejected"] = "pending"
    calendar_action_ids: tuple[Identifier, ...] = ()

    @model_validator(mode="after")
    def _no_silent_blocking_conflict(self) -> "ScheduleProposal":
        if self.student_decision == "approved":
            blocking = [
                c for s in self.proposed_slots for c in s.conflicts if c.blocking
            ]
            if blocking:
                raise ValueError(
                    "存在 blocking 冲突的排程不得进入 approved 状态（B1/B2）"
                )
        return self


class CalendarWriteDraft(CampusPathModel):
    """要写回日历的事件内容。**由 CampusPath 生成**，学生预览后才落地。

    ``event_title`` 在边界扫描中被显式豁免（见 tests/test_boundary_guards.py）：
    B5 禁止的是"读取并保存学生原有事件的标题"，不是"我们创建的事件有名字"。
    """

    event_title: str = Field(max_length=200)
    span: TimeRange
    reminder_minutes_before: int | None = Field(default=None, ge=0, le=10080)


class CalendarAction(CampusPathModel):
    """Action & Consent Service 的写入动作。幂等键防重复写。"""

    action_id: Identifier
    student_id: StudentId
    provider: CalendarProviderId
    action: Literal["create", "update", "delete"]
    draft: CalendarWriteDraft | None = None
    idempotency_key: str = Field(min_length=8)
    approval_receipt_id: Identifier | None = None
    external_event_id: str | None = None
    result: Literal["pending", "succeeded", "failed", "skipped"] = "pending"
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _write_requires_approval(self) -> "CalendarAction":
        if self.result in {"succeeded", "pending"} and self.approval_receipt_id is None:
            raise ValueError("未记录同意回执的日历写入不被允许（Spec §15.4 规则 8）")
        if self.action in {"create", "update"} and self.draft is None:
            raise ValueError("create/update 必须带 draft")
        return self


class CalendarSyncReceipt(FrozenModel):
    """一次 free/busy 拉取的审计记录。用于证明我们只取了 free/busy。"""

    receipt_id: Identifier
    connection_id: Identifier
    fetched_at: datetime
    window_start: datetime
    window_end: datetime
    block_count: int = Field(ge=0)
    detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY


class AvailabilityBlockPatch(CampusPathModel):
    """A（2026-07-31）：学生在周日历上直接编辑一个时段。

    全部字段可选——只改动提供的那些；服务端把补丁套到原块上后
    **重新整体校验**，所以 B5 的标题授权约束照常生效，绕不过去。
    """

    span: TimeRange | None = None
    title: str | None = Field(default=None, max_length=200)
    type: AvailabilityType | None = None
    reminder_minutes_before: int | None = Field(default=None, ge=0, le=10080)


class RoutineWindow(CampusPathModel):
    """一天内的一段固定作息，如 12:00–13:00 午饭。"""

    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")


class RoutineRequest(CampusPathModel):
    """M（2026-07-31）：学生**显式提交**自己的日常作息（§16.8.2：不得从日历反推）。

    睡眠与用餐生成保护时段块，但**不再从可支配容量里扣**——
    §16.7 的每周可支配小时数本来就不含它们，再扣一次人人都是负容量。
    """

    sleep: RoutineWindow | None = None
    meals: tuple[RoutineWindow, ...] = Field(default=(), max_length=4)
