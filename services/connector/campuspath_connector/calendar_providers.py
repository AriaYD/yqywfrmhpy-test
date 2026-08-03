"""CalendarProvider 的两个实现：夹具与 Google。

Plan 的降级路径 R3 说的就是这件事——**接口一份，实现两个**，界面按接口写。
现在跑的是夹具（无需 OAuth 同意屏幕，Demo 随时可跑），换成 Google 时
上层一行不用改。

两个实现共享同一条纪律：

* **token 不出这一层**。返回值里只有 ``BusyInterval``，没有凭据字段，
  也没有任何能拼出凭据的东西（架构第 3 条）。
* **按被告知的层级取数，自己不猜**。Provider 不知道学生授权了什么——
  那是 Capacity & Calendar Service 的职责。传进来 ``FREE_BUSY_ONLY``
  就绝不返回标题，哪怕上游 API 明明给了。
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timedelta, timezone

from campuspath_contracts.calendar import CalendarDetailLevel

from .adapters import BusyInterval

#: 夹具生成的一周作息骨架：(weekday, 起始小时, 时长小时, 标题)。
#: 标题是**合成的**，用来演示二级授权能看到什么；它不代表任何真人的日程。
_WEEKLY_SKELETON: tuple[tuple[int, int, int, str], ...] = (
    (0, 9, 2, "COMP 2011 Lecture"),
    (0, 14, 1, "Team standup"),
    (1, 10, 3, "COMP 2012 Lab"),
    (1, 19, 2, "Gym"),
    (2, 9, 2, "COMP 2011 Tutorial"),
    (2, 13, 1, "Society weekly meeting"),
    (3, 11, 2, "MATH 2411 Lecture"),
    (3, 18, 3, "Part-time shift"),
    (4, 9, 2, "COMP 2012 Lecture"),
    (4, 15, 2, "Career workshop"),
    (5, 10, 2, "Volunteering"),
    (6, 20, 1, "Family call"),
)


@dataclasses.dataclass
class FixtureCalendarProvider:
    """确定性夹具。**页面上必须标出来它是夹具**（D1 的数据标记要求）。

    同一个 student_id + 同一周永远得到同一份忙碌区间——
    Demo 重跑两次看到的日历不一样，讲的人会当场卡住。
    """

    #: 让不同学生的作息错开，但仍然确定性
    salt: str = "campuspath-fixture"

    def _offset(self, student_id: str) -> int:
        digest = hashlib.sha256(f"{self.salt}|{student_id}".encode()).hexdigest()
        return int(digest[:2], 16) % 3          # 0–2 小时的个体差异

    def free_busy(
        self,
        student_id: str,
        start: datetime,
        end: datetime,
        *,
        detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY,
    ) -> list[BusyInterval]:
        shift = self._offset(student_id)
        out: list[BusyInterval] = []
        day = start.date()
        while day <= end.date():
            for weekday, hour, length, title in _WEEKLY_SKELETON:
                if day.weekday() != weekday:
                    continue
                begin = datetime.combine(
                    day, datetime.min.time(), tzinfo=start.tzinfo or timezone.utc
                ) + timedelta(hours=hour + shift)
                finish = begin + timedelta(hours=length)
                if finish <= start or begin >= end:
                    continue
                out.append(BusyInterval(
                    start=begin,
                    end=finish,
                    # **层级判断只在这一处**。写成三元而不是"先取再过滤"，
                    # 是因为后者一旦有人删掉过滤就静默泄漏。
                    title=(
                        title
                        if detail_level is CalendarDetailLevel.EVENT_TITLES
                        else None
                    ),
                ))
            day += timedelta(days=1)
        return sorted(out, key=lambda i: i.start)

    def create_event(
        self, student_id: str, title: str, start: datetime, end: datetime,
        *, idempotency_key: str,
    ) -> str:
        """夹具不真的写日历，但返回一个确定性的外部 id，让幂等能被测。"""
        return "fixture-" + hashlib.sha256(
            f"{student_id}|{idempotency_key}".encode()
        ).hexdigest()[:16]


@dataclasses.dataclass
class GoogleCalendarProvider:
    """真实实现的骨架。**尚未接线**——需要 OAuth 同意屏幕与 Secret Manager 里的
    client secret，两者都要由项目所有者在 GCP 上操作。

    刻意先写出来，是为了让"换成真实源"是替换一个构造函数，
    而不是回头重写调用方。方法体在拿到凭据前抛 ``NotImplementedError``，
    **不返回空列表**——空列表会被上游当成"这周没有安排"，
    那是一句会被信以为真的谎。
    """

    calendar_id: str = "primary"

    def free_busy(
        self,
        student_id: str,
        start: datetime,
        end: datetime,
        *,
        detail_level: CalendarDetailLevel = CalendarDetailLevel.FREE_BUSY_ONLY,
    ) -> list[BusyInterval]:
        raise NotImplementedError(
            "Google Calendar 尚未接线：需要 OAuth 同意屏幕与 Secret Manager 中的 "
            "client secret。当前请用 FixtureCalendarProvider（Plan 降级路径 R3）。"
            "注意实现时：FREE_BUSY_ONLY 必须走 freeBusy.query 端点，"
            "**不是**取回 events 再丢掉标题——后者已经把详情收进了进程内存。"
        )

    def create_event(
        self, student_id: str, title: str, start: datetime, end: datetime,
        *, idempotency_key: str,
    ) -> str:
        raise NotImplementedError("Google Calendar 尚未接线")
