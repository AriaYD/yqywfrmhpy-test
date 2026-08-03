"""把 HKUST Engage 的**真实公开活动**接进资讯广场。

与课程目录同理：这是学校的公开活动预告页，没有任何学生数据，
可以直接用。合成的实习/竞赛仍然保留——真实活动以讲座、研讨会为主，
覆盖不到"投递实习"这条主线，两者是互补不是替代。

**真实条目一律带 `source_id="hkust_engage"`**，界面据此打"官方"标记；
合成条目的组织者名字里带（Demo）。学生任何时候都能分清哪条是真的。

三条不做的事：

* 不猜译名。来源只给一种语言时 ``title_localized`` 就留空，UI 回落到
  原标题。活动名会被学生拿去搜索、报名、写进简历，翻错的代价不是
  读起来别扭而已。
* 不编 deadline。来源没有报名截止就是没有——凭空造一个会让
  "本轮不可报"这类判定建立在虚构事实上。
* 不编 workload。同理，缺就是缺，`MatchResult.uncertainty` 会显形。
"""

from __future__ import annotations

import datetime as _datetime
import json
import pathlib
import re

from campuspath_contracts.common import LocalizedText, Provenance
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.opportunity import (
    OrganizerCategory,
    Opportunity,
    OpportunityType,
    PublicationStatus,
)

RAW_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "raw" / "hkust_events" / "events.json"
)

SOURCE_ID = "hkust_engage"

#: 站点类别 → 契约的机会类型。命中不了就归 EVENT——
#: **不新造类型**，枚举是契约的一部分。
_TYPE_BY_KEYWORD = (
    ("workshop", OpportunityType.WORKSHOP),
    ("工作坊", OpportunityType.WORKSHOP),
    ("competition", OpportunityType.COMPETITION),
    ("比赛", OpportunityType.COMPETITION),
    ("seminar", OpportunityType.EVENT),
    ("lecture", OpportunityType.EVENT),
    ("talk", OpportunityType.EVENT),
    ("conference", OpportunityType.EVENT),
)

#: 类别 → 该活动**可能**覆盖的要求类别。保守：只给明显成立的那一条。
#: 宁可少标，也不要让 Gap Coverage 的分母被虚高的覆盖撑大。
_REQUIREMENT_BY_KEYWORD = (
    ("workshop", RequirementCategory.TECHNICAL_SKILL),
    ("工作坊", RequirementCategory.TECHNICAL_SKILL),
    ("competition", RequirementCategory.PROJECT_PORTFOLIO),
    ("比赛", RequirementCategory.PROJECT_PORTFOLIO),
    ("seminar", RequirementCategory.NETWORK),
    ("lecture", RequirementCategory.NETWORK),
    ("talk", RequirementCategory.COMMUNICATION),
    ("演讲", RequirementCategory.COMMUNICATION),
    ("讲座", RequirementCategory.NETWORK),
    ("研讨会", RequirementCategory.NETWORK),
)


def _classify(category_en: str, category_zh: str) -> tuple[OpportunityType, tuple]:
    blob = f"{category_en} {category_zh}".lower()
    kind = OpportunityType.EVENT
    for keyword, mapped in _TYPE_BY_KEYWORD:
        if keyword in blob:
            kind = mapped
            break
    requirements = tuple(
        sorted(
            {mapped for keyword, mapped in _REQUIREMENT_BY_KEYWORD if keyword in blob},
            key=lambda c: c.value,
        )
    )
    return kind, requirements


def _parse_date(text: str | None, retrieved: _datetime.datetime):
    """把 "4 August 2026" / "2026 年 8 月 4 日" 解成日期。

    解不出来就返回 None——**不回落到今天**。一个猜出来的开始时间会
    直接进日程冲突计算，比没有时间更糟。
    """
    if not text:
        return None
    zh = re.search(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text)
    if zh:
        y, m, d = (int(g) for g in zh.groups())
        return _datetime.datetime(y, m, d, 9, tzinfo=_datetime.timezone.utc)
    en = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text)
    if en:
        day, month_name, year = en.groups()
        try:
            month = _datetime.datetime.strptime(month_name[:3], "%b").month
        except ValueError:
            return None
        return _datetime.datetime(int(year), month, int(day), 9,
                                  tzinfo=_datetime.timezone.utc)
    return None


def _localized(values: dict[str, str]) -> LocalizedText | None:
    zh, en = values.get("zh_Hans", "").strip(), values.get("en", "").strip()
    if not zh and not en:
        return None
    if zh == en:
        return None          # 来源两边给的是同一串：没有译名，别假装有
    return LocalizedText(zh_Hans=zh or en, en=en or zh)


def load_campus_events(retrieved_at: _datetime.datetime) -> list[Opportunity]:
    """读取抓取产物。文件不存在时返回空列表——真实源缺失不该让 seed 崩。"""
    if not RAW_PATH.exists():
        return []
    rows = json.loads(RAW_PATH.read_text(encoding="utf-8"))

    out: list[Opportunity] = []
    for index, row in enumerate(rows):
        title_en = (row.get("title", {}).get("en") or "").strip()
        title_zh = (row.get("title", {}).get("zh_Hans") or "").strip()
        title = title_en or title_zh
        if not title:
            continue
        category_en = (row.get("category", {}).get("en") or "").strip()
        category_zh = (row.get("category", {}).get("zh_Hans") or "").strip()
        kind, requirements = _classify(category_en, category_zh)

        starts_at = _parse_date(row.get("date"), retrieved_at)
        organizer = (row.get("organizer") or "HKUST").strip()

        out.append(Opportunity(
            opportunity_id=f"OPP-ENG-{index + 1:03d}",
            type=kind,
            title=title[:300],
            title_localized=_localized(row.get("title", {})),
            organizer=organizer[:200],
            organizer_localized=None,
            category_tags=tuple(
                t for t in {category_en.lower(), "hkust_engage"} if t
            ),
            requirement_categories=requirements,
            # 来源没有报名截止与工作量，就**空着**
            deadline=None,
            starts_at=starts_at,
            ends_at=None,
            workload_hours_total=None,
            skills=(),
            official_url=row.get("source_url", "https://calendar.hkust.edu.hk/"),
            source_id=SOURCE_ID,
            provenance=Provenance(
                source=SOURCE_ID,
                source_url=row.get("source_url"),
                retrieved_at=retrieved_at,
                parser_version="hkust-engage/0.1",
                evidence_snippet=f"{title} · {row.get('location', '')}"[:2000],
                confidence=1.0,
            ),
            # 学校官网直发，等同官方发布，无需再过审核状态机
            publication_status=PublicationStatus.PUBLISHED,
            organizer_category=OrganizerCategory.CAMPUS_OFFICIAL,
            last_verified_at=retrieved_at,
        ))
    return out
