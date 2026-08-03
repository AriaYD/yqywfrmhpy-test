"""Spec §16.8：Wellbeing 容量信号、两次提醒与 consent-based outreach。

**全链零 LLM**（Spec §8.9.4）。判定归 Rules & Constraint Engine 的阈值比较，
文案归 Wellbeing Reminder Composer 的固定模板。本模块不得 import 任何模型 SDK。

契约层承担三件事：

1. 每条信号必须声明 ``data_coverage``。Spec §16.8.2 对五类信号各有前置数据要求，
   缺数据时只能返回 unknown，**不得从空白日历反推**（B6）。
2. 提醒模板的六个槽位缺一不可，且"不代表任何医学诊断"在两种语言里都必须出现。
   模板能保证 100%，模型不能——这正是本链路不用 LLM 的原因。
3. outreach 邮件字段是**白名单**：多一个字段就反序列化失败（B13、Spec §16.8.4）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    CampusPathModel,
    FrozenModel,
    Identifier,
    Locale,
    LocalizedText,
    StrEnum,
    StudentId,
)

#: 六槽位模板中必须原样出现的免责声明（Spec §16.8.3 第 3 项）。
NON_DIAGNOSTIC_DISCLAIMER = {
    Locale.ZH_HANS: "不代表任何医学诊断",
    Locale.EN: "not a medical diagnosis",
}


class WellbeingSignalType(StrEnum):
    """Spec §16.8.2 的五类。全部是阈值比较，无语义判断。"""

    SLEEP_OPPORTUNITY_COMPRESSED = "sleep_opportunity_compressed"
    SELF_REPORTED_SHORT_SLEEP = "self_reported_short_sleep"
    ACTIVITY_OPPORTUNITY_LOW = "activity_opportunity_low"
    RECOVERY_BLOCK_ABSENT = "recovery_block_absent"
    CAPACITY_OVERLOAD = "capacity_overload"


class ObservationSource(StrEnum):
    STUDENT_DEFINED_WINDOW = "student_defined_window"
    SELF_REPORTED = "self_reported"
    CAPACITY_SNAPSHOT = "capacity_snapshot"
    PLANNED_SCHEDULE = "planned_schedule"


class Severity(StrEnum):
    INFO = "info"
    ATTENTION = "attention"
    BLOCKING = "blocking"  # 阻止该排程发布，不是"关于这个学生的判断"


class DataCoverage(CampusPathModel):
    """这条信号是基于多少数据得出的。覆盖不足时不得升级严重度。"""

    window_days: int = Field(ge=1, le=90)
    days_with_data: int = Field(ge=0)
    prerequisite_setting_present: bool = Field(
        description="学生是否已显式设置对应的窗口/偏好；False 时信号不得触发",
    )

    @model_validator(mode="after")
    def _coverage_within_window(self) -> "DataCoverage":
        if self.days_with_data > self.window_days:
            raise ValueError("days_with_data 不能超过 window_days")
        return self


class WellbeingCapacitySignal(CampusPathModel):
    """由 Rules & Constraint Engine 确定性产出（Spec §14.2）。

    ``non_diagnostic`` 恒为 True 且不可赋成 False——这不是配置项。
    """

    signal_id: Identifier
    student_id: StudentId
    signal_type: WellbeingSignalType
    period_start: date
    period_end: date
    observation_source: ObservationSource
    data_coverage: DataCoverage
    #: **双语**。这两条会直接显示给学生，是 UI 文案（见 messages.py）。
    #: 零 LLM 链路意味着它们必须来自固定模板，不能现场翻译。
    reference_line: LocalizedText = Field(
        description="所依据的参考线原文，例如 '成人每 24 小时至少 7 小时'（Spec §16.8.1）"
    )
    observed_value: LocalizedText = Field(description="实测值，例如 '7 天中 3 天低于 7 小时'")
    severity: Severity = Severity.INFO
    non_diagnostic: Literal[True] = True
    evaluated_at: datetime
    rule_id: Identifier = Field(description="产生该信号的阈值规则 id，可回溯到 rule set")

    @model_validator(mode="after")
    def _no_signal_without_student_setting(self) -> "WellbeingCapacitySignal":
        """B6 的类型层前哨：没有学生显式设置就不许生成需要该设置的信号。"""
        needs_setting = {
            WellbeingSignalType.SLEEP_OPPORTUNITY_COMPRESSED,
            WellbeingSignalType.RECOVERY_BLOCK_ABSENT,
        }
        if self.signal_type in needs_setting and not self.data_coverage.prerequisite_setting_present:
            raise ValueError(
                f"{self.signal_type.value} 要求学生已显式设置对应窗口/偏好，"
                "不得从空白日历推断（Spec §16.8.2、B6）"
            )
        if self.signal_type is WellbeingSignalType.SELF_REPORTED_SHORT_SLEEP:
            if self.observation_source is not ObservationSource.SELF_REPORTED:
                raise ValueError("self_reported_short_sleep 的来源必须标记为 self_reported")
        return self


class ReminderTemplate(FrozenModel):
    """Spec §16.8.3 的六个槽位。每种语言一份，缺一不可。"""

    template_id: Identifier
    locale: Locale
    slot1_observation: str = Field(min_length=1, description="系统观察到了什么")
    slot2_data_source: str = Field(min_length=1, description="数据来自哪里、覆盖范围")
    slot3_non_judgment: str = Field(min_length=1, description="系统没有作出什么判断")
    slot4_immediate_options: tuple[str, ...] = Field(min_length=1)
    slot5_support_options: tuple[str, ...] = Field(min_length=1)
    slot6_consent_state: str = Field(min_length=1)

    @model_validator(mode="after")
    def _disclaimer_present(self) -> "ReminderTemplate":
        required = NON_DIAGNOSTIC_DISCLAIMER[self.locale]
        if required.lower() not in self.slot3_non_judgment.lower():
            raise ValueError(
                f"{self.locale.value} 模板的 slot3 必须原样包含「{required}」（Spec §16.8.3）"
            )
        return self


class WellbeingReminderEvent(CampusPathModel):
    """两次提醒状态机的一条记录（Spec §14.2、§16.8.3）。"""

    reminder_id: Identifier
    student_id: StudentId
    signal_ids: tuple[Identifier, ...] = Field(min_length=1)
    reminder_number: Literal[1, 2]
    template_id: Identifier
    locale: Locale
    delivered_at: datetime
    student_action: Literal[
        "none", "acknowledged", "switched_low_load", "removed_tasks",
        "snoozed", "requested_contact", "muted"
    ] = "none"
    snoozed_until: datetime | None = None
    low_load_mode: bool = False
    reevaluate_after: datetime | None = Field(
        default=None, description="第 1 次提醒后 24–72 小时再评估（Spec §16.8.3）"
    )


class OutreachPurpose(StrEnum):
    NON_URGENT_WELLBEING_CHECKIN = "non_urgent_wellbeing_checkin"


class OutreachConsent(FrozenModel):
    """Spec §14.2。没有有效同意就没有任何个体信息离开学生侧（B13）。"""

    consent_id: Identifier
    student_id: StudentId
    scope: Literal["single_request", "standing_opt_in"]
    recipient_role: Literal["counseling_wellbeing_queue"]
    purpose: OutreachPurpose = OutreachPurpose.NON_URGENT_WELLBEING_CHECKIN
    granted_at: datetime
    expires_at: datetime | None = None
    revoked_at: datetime | None = None

    def is_valid_at(self, when: datetime) -> bool:
        if self.revoked_at is not None and when >= self.revoked_at:
            return False
        if self.expires_at is not None and when > self.expires_at:
            return False
        return when >= self.granted_at


class OutreachEmailFields(CampusPathModel):
    """Spec §16.8.4 的字段白名单。**这个模型的字段列表就是允许发送的全部内容。**

    禁止出现（由 extra="forbid" + 边界扫描共同保证）：课程标题、日历标题、
    参与人、地点、完整 Profile、私人 Reflection、模型推断、诊断性措辞。
    """

    internal_student_ref: str = Field(
        description="学校内部标识或学生自选联系方式，不含姓名/学号原文"
    )
    student_requested_contact: Literal[True] = Field(
        description="恒为 True：只有学生主动请求或已有有效 opt-in 才发送"
    )
    trigger_category: WellbeingSignalType
    triggered_at: datetime
    consent_receipt_id: Identifier
    acknowledgement_url: str = Field(description="回执链接，用于追踪认领")


class WellbeingOutreachRequest(CampusPathModel):
    """Spec §14.2。投递状态必须可追踪——``email accepted`` 不等于学生获得支持。"""

    request_id: Identifier
    consent_id: Identifier
    student_id: StudentId = Field(
        description="仅存在于学生私有域的请求记录中；邮件本身携带的是 internal_student_ref"
    )
    trigger_category: WellbeingSignalType
    email_fields: OutreachEmailFields
    requested_at: datetime
    delivery_status: Literal[
        "queued", "sent", "bounced", "failed", "claimed", "closed"
    ] = "queued"
    human_owner: str | None = None
    disposition: str | None = None

    @model_validator(mode="after")
    def _consistent_trigger(self) -> "WellbeingOutreachRequest":
        if self.email_fields.trigger_category is not self.trigger_category:
            raise ValueError("邮件字段中的 trigger_category 与请求不一致")
        if self.email_fields.consent_receipt_id != self.consent_id:
            raise ValueError("邮件引用的同意回执与 consent_id 不一致（B13）")
        return self


class CrisisProtocolInvocation(FrozenModel):
    """Spec §16.8.5：学生明确自述即时危险时 A0 的**唯一**动作。

    不走两次提醒，也不发普通邮件。系统只展示学校预配置的官方资源，
    后续处置交给受训人员——契约层不承载任何评估或分级字段。
    """

    invocation_id: Identifier
    student_id: StudentId
    invoked_at: datetime
    protocol_ref: Identifier = Field(description="学校预配置的 Crisis Safety Protocol id")
    resources_shown: tuple[LocalizedText, ...] = Field(min_length=1)
    handoff_recorded: bool = False


class WellbeingAssessmentRequest(CampusPathModel):
    """R5-E（2026-08-01）：ISI + PSS-10 标准化自评作答。

    原始作答提交，反向计分在 wellbeing 服务里做（零 LLM，纯算术）。
    """

    student_id: StudentId
    isi_answers: tuple[int, ...] = Field(min_length=7, max_length=7)
    pss10_answers: tuple[int, ...] = Field(min_length=10, max_length=10)


class WellbeingAssessmentResult(CampusPathModel):
    """计分与两层分流结果。**筛查不是诊断**——声明是本模型的必填字段。

    分流只是"建议联系谁"；外联仍由学生一键确认发起（B13 不放宽）。
    """

    student_id: StudentId
    isi_score: int = Field(ge=0, le=28)
    isi_band: Literal["none", "subclinical", "moderate", "severe"]
    pss10_score: int = Field(ge=0, le=40)
    pss10_band: Literal["low", "moderate", "high"]
    routing: Literal["none", "tutor", "counseling_center"]
    recommended_contact_name: str | None = Field(
        default=None, description="按分流从学生自填联系人里取的姓名；未填则 None")
    # R8-3（2026-08-01 用户裁定，Spec §16.8 已同步）：第一层分流
    # （routing=tutor）由系统**自动**联系学生自填的班级 tutor——
    # 量表由学生本人主动提交，提交动作即知情动作；B13 的"学生请求"
    # 语义据此覆盖第一层。第二层仍是学生自选时段预约，不自动。
    auto_contact_sent: bool = False
    auto_contact_email: str | None = Field(default=None, max_length=254)
    disclaimer: LocalizedText


class WellbeingEscalation(CampusPathModel):
    """升级判定：什么时候提示做量表。全部确定性阈值，口径写死在字段里。

    2026-08-02 用户裁定换用「睡眠-负荷平衡」计数模型（工程化简化，依据：
    ATUS 时间使用调查的 3.5h 生理固定成本、WHO/ILO 每周 55h 过劳阈值、
    Scarcity 时间贫困的 15–20% 缓冲共识；**非医疗建议**）：

    * 合格日 = 当天有效睡眠 <7h **且** 学习工作（忙+课程）时长 >11h；
    * ``warning``：滚动 14 天内合格日 ≥10 → 温和弹窗提醒调整作息；
    * ``assessment``：滚动 28 天内合格日 ≥20 → 弹窗引导完成 ISI+PSS-10，
      完成（``last_assessment_at`` 晚于触发窗口起点）后弹窗解除；
      分流沿用 §16.8：初级 → 联系辅导员；PSS>20 或 ISI 中度及以上 →
      引导预约心理咨询室。学生也可随时**主动**发起评估。

    睡眠只看学生**显式声明**的窗口与侵入它的安排——未声明不推断（§16.8.2）。
    """

    student_id: StudentId
    declared_sleep_hours: float | None = Field(
        default=None, description="学生声明的睡眠窗口时长；None=未声明（不推断）")
    sleep_deficit_consecutive_days: int = Field(ge=0)
    data_coverage_days: int = Field(ge=0, description="有数据可判的天数，如实报告")
    #: 滚动 14 天窗口内「睡眠<7h 且 学习>11h」的合格日数（阈值 10）
    qualifying_days_14: int = Field(default=0, ge=0)
    #: 滚动 28 天窗口内的合格日数（阈值 20）
    qualifying_days_28: int = Field(default=0, ge=0)
    #: 最近一次完成 ISI+PSS-10 的时间；assessment 弹窗据此解除
    last_assessment_at: datetime | None = None
    overload_now: bool = False
    refused_or_deferred_30d: int = Field(ge=0)
    tier: Literal["none", "warning", "assessment"]
    reasons: tuple[LocalizedText, ...] = ()


# --------------------------------------------------------------------------
# R8-3（2026-08-01 用户裁定）：三层心理干预
# --------------------------------------------------------------------------


class CounselingWindow(FrozenModel):
    """心理咨询室每周开放窗口（校方 wellbeing-desk 设置）。

    审查修复（2026-08-01）：pattern 只保证"两位数:两位数"，``99:99`` 能过——
    slot 生成时 ``datetime(...)`` 当场炸成 500，且炸的是**全体学生**的预约面。
    时间合法性在契约层挡住，不留给运行时。"""

    weekday: int = Field(ge=0, le=6, description="0=周一 … 6=周日")
    start: str = Field(pattern=r"^\d{2}:\d{2}$")
    end: str = Field(pattern=r"^\d{2}:\d{2}$")

    @model_validator(mode="after")
    def _times_are_real_and_ordered(self) -> "CounselingWindow":
        def minutes(value: str) -> int:
            hh, mm = (int(x) for x in value.split(":"))
            if hh > 23 or mm > 59:
                raise ValueError(f"非法时间 {value}——小时 00–23、分钟 00–59")
            return hh * 60 + mm

        if minutes(self.start) >= minutes(self.end):
            raise ValueError(f"窗口起点必须早于终点：{self.start} → {self.end}")
        return self


class CounselingHours(CampusPathModel):
    """咨询室工作时段。学生端可预约时段**只**从这里生成——
    校方没开放的时间，学生端物理上看不到。"""

    windows: tuple[CounselingWindow, ...] = Field(min_length=1)
    slot_minutes: int = Field(default=30, ge=15, le=120)
    updated_at: datetime


class CounselingSlot(FrozenModel):
    slot_id: Identifier
    start: datetime
    end: datetime
    booked: bool = False


class CounselingBooking(CampusPathModel):
    """第二层分流（ISI≥15 且 PSS-10>20）的咨询预约。

    预约展示给咨询室：姓名 / 专业 / 年级 / 班级 / 联系方式（用户裁定
    2026-08-01）。专业与年级由服务端从 Profile 回填，学生不可伪造；
    姓名 / 班级 / 联系方式由学生在预约时自填。"""

    booking_id: Identifier
    student_id: StudentId
    slot_id: Identifier
    student_name: str = Field(min_length=1, max_length=120)
    program: str = Field(min_length=1, max_length=200)
    year: int = Field(ge=1, le=8)
    class_label: str | None = Field(default=None, max_length=60)
    contact: str = Field(min_length=3, max_length=254)
    created_at: datetime


class EmergencyAccessResult(CampusPathModel):
    """第三层：紧急红按钮。跳过一切排队，直接给值班室负责人电话。

    防滥用（用户裁定）：每学期最多按 2 次，第 3 次起拉黑一学期。
    安全底线：即使被拉黑，拒绝响应里也必须带校园热线号码——
    防滥用挡的是"跳过排队"的特权，不挡求助信息本身。"""

    student_id: StudentId
    duty_phone: str = Field(min_length=1, max_length=40)
    uses_this_term: int = Field(ge=0)
    blacklisted: bool = False
    note: LocalizedText
