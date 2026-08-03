"""Career Center Advisor 预约与会后建议（2026-07-31 用户新增需求 I）。

边界与既有原则一致：

* 学生端与 Advisor 端**分开**：学生只操作自己的预约；Advisor 只看预约队列
  与自己写的总结，**看不到**学生的反思原文、成绩、日历（RBAC 表自动生成）。
* Advisor 的会后建议是**给学生的文本**，不是对学生的评价记录——它回到
  学生自己的域里展示；聚合域没有任何通路（字段列表里没有可聚合载荷）。
* 学生会面后的收获写进普通 Reflection（subject = booking），复用 A 轨。
"""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from .common import CampusPathModel, Identifier, StrEnum, StudentId, TimeRange


class AdvisorBookingStatus(StrEnum):
    REQUESTED = "requested"
    CONFIRMED = "confirmed"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    #: Q（2026-07-31）：预约了没来。由 Advisor 标记；一学期累计 3 次
    #: 后系统拒绝该生新预约（把机会浪费给别人是有代价的）。
    NO_SHOW = "no_show"


class AdvisorSlot(CampusPathModel):
    """Advisor 的一个可约时段。**只报占用，不报占用者**——
    名录对学生可见，谁约了谁不是学生该看到的。

    R8-1：``blocked=True`` 表示 Advisor 标记了"此段不在"——
    学生端名录**物理上看不到**这样的时段（服务端按角色过滤），
    Advisor 工作台看得到并可随时解除。"""

    slot_id: Identifier
    advisor_id: Identifier
    span: TimeRange
    booked: bool = False
    blocked: bool = False


class Advisor(CampusPathModel):
    """Career Center 的一位顾问（合成名录）。接入真实系统时本模型不变，
    数据源换成 Career Center 的排班表。"""

    advisor_id: Identifier
    name: str = Field(max_length=120)
    focus: str = Field(max_length=200, description="专长方向，如实习申请 / 读研规划")
    slots: tuple[AdvisorSlot, ...] = ()


class AdvisorRegistration(CampusPathModel):
    """R8-1：Advisor 自助注册。学校聘请的顾问人员流动，名录不写死——
    新顾问注册后自动获得未来 10 个工作日的标准时段库存。"""

    name: str = Field(min_length=1, max_length=120)
    focus: str = Field(min_length=1, max_length=200)


class AdvisorUpdate(CampusPathModel):
    """B9（2026-08-01 用户裁定）：注册信息可查看/编辑——姓名与专长方向可改。"""

    name: str = Field(min_length=1, max_length=120)
    focus: str = Field(min_length=1, max_length=200)


class SlotAvailabilityUpdate(CampusPathModel):
    """R8-1：Advisor 设置某时段开放 / 不在。已被预约的时段不能标记不在
    （先处理预约，见 409）。"""

    available: bool


class AdvisorSummary(CampusPathModel):
    """Advisor 会后写给学生的几条关键建议。"""

    summary_id: Identifier
    booking_id: Identifier
    key_advice: tuple[str, ...] = Field(min_length=1, max_length=5)
    created_at: datetime

    @model_validator(mode="after")
    def _advice_lines_are_bounded(self) -> "AdvisorSummary":
        for line in self.key_advice:
            if not line.strip() or len(line) > 500:
                raise ValueError("每条建议 1–500 字符，不接受空行")
        return self


class AdvisorBooking(CampusPathModel):
    """学生发起的 Advisor 预约。

    激活条件（Spec 用户裁定）：大一下学期起可用——服务端按年级把关，
    Year 1 上学期请求被拒时给出解释而不是静默失败。
    """

    booking_id: Identifier
    student_id: StudentId
    #: Q：接入名录后预约指向具体顾问的具体时段。旧数据 None 兼容。
    advisor_id: Identifier | None = None
    slot_id: Identifier | None = None
    requested_slot: TimeRange
    topic: str = Field(min_length=1, max_length=500, description="学生想讨论什么")
    status: AdvisorBookingStatus = AdvisorBookingStatus.REQUESTED
    created_at: datetime
    #: 会后总结。Advisor 写完后由服务端挂上；学生端由此看到关键建议。
    summary: AdvisorSummary | None = None

    @model_validator(mode="after")
    def _completed_needs_summary(self) -> "AdvisorBooking":
        if self.status is AdvisorBookingStatus.COMPLETED and self.summary is None:
            raise ValueError("completed 的预约必须带会后总结——没有总结就还没完成")
        return self
