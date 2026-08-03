#!/usr/bin/env python3
"""抓取 HKUST Engage 的**公开**校园活动（calendar.hkust.edu.hk）。

与 `scrape_hkust_catalog.py` 同一套纪律：磁盘缓存、1 秒礼貌间隔、
声明身份的 UA。这里抓的同样是公开信息——活动预告，无任何学生数据。

四个栏目各抓一遍（活动推介 / 近期活动 / 进行中 / 非科大主办），
**中英各一份**：CampusPath 全站双语，资讯广场的活动标题若只有一种语言，
切到另一种语言时就会露出一整页外语——那不是"回退"，那是没做。

站点是 Drupal Views，卡片结构稳定：每张 `views-row` 里的
`views-field-<字段名>` 就是字段。解析按这个结构走，不靠 CSS 类名的
视觉部分（那些会随改版变）。
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

BASE = "https://calendar.hkust.edu.hk"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CampusPath-research/1.0"
DELAY = 1.0  # 秒；礼貌间隔，别改小

#: 站点的四个栏目。`featured` 是编辑推荐，其余按时间/主办方划分。
SECTIONS = ("featured-events", "recent", "ongoing", "non-hkust")

#: 语言前缀 → 输出里的 locale 标签。契约的 LocalizedText 只认这两个。
LOCALES = {"zh-hans": "zh_Hans", "": "en"}

OUT_DIR = pathlib.Path(__file__).parent / "raw" / "hkust_events"
CACHE_DIR = OUT_DIR / "_cache"


def fetch(url: str, cache_key: str) -> str:
    """带磁盘缓存的 GET（C2 起委托共享抓取器，行为不变：缓存命中不发请求）。"""
    return _shared_fetch(url, CACHE_DIR, cache_key, delay=DELAY)


def _import_shared_fetch():
    try:
        from campuspath_connector.fetcher import fetch as shared
    except ImportError:  # 脚本用系统 python3 直跑时，包不在 sys.path
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "connector"))
        from campuspath_connector.fetcher import fetch as shared
    return shared


_shared_fetch = _import_shared_fetch()


class EventListParser(HTMLParser):
    """把一张活动卡片（``views-row``）拆成字段。

    ⚠️ **栏目页与首页的 HTML 不是一套。** 首页用 Drupal 默认的
    ``views-field-<name>`` 包装；四个栏目页用的是主题化后的
    ``.image / .detail / .category / h2 / .venue / .date``。
    第一版按首页写的解析器在栏目页上拿到 7 张卡片、0 个字段——
    结构对了、字段全空，而"跑完没报错"看起来像成功。
    覆盖率打印就是为了让这种失败当场现形。

    卡片里有**两个** ``.venue``：第一个是主办方（"Organized by …"），
    第二个才是地点。按出现顺序区分，不靠文案前缀——英文版写
    "Organized by"，中文版不写。
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None
        self._buf: list[str] = []
        self._venues: list[str] = []
        self._in_h2 = False

    @staticmethod
    def _classes(attrs) -> set[str]:
        for name, value in attrs:
            if name == "class" and value:
                return set(value.split())
        return set()

    @staticmethod
    def _attr(attrs, key) -> str | None:
        for name, value in attrs:
            if name == key:
                return value
        return None

    def handle_starttag(self, tag, attrs):
        cls = self._classes(attrs)

        if "views-row" in cls:
            self._flush_event()
            self._cur = {}
            self._venues = []
            return
        if self._cur is None:
            return

        if tag == "a" and "category" in cls:
            self._capture, self._buf = "category", []
        elif tag == "h2":
            self._in_h2 = True
            self._capture, self._buf = "title", []
        elif tag == "div" and "venue" in cls:
            self._capture, self._buf = "venue", []
        elif tag == "div" and "date" in cls:
            self._capture, self._buf = "date", []
        elif tag == "a" and self._in_h2:
            href = self._attr(attrs, "href")
            if href and "/events/" in href:
                self._cur.setdefault("path", href)
        elif tag == "a" and self._cur.get("path") is None:
            href = self._attr(attrs, "href")
            if href and "/events/" in href:
                self._cur.setdefault("path", href)

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag == "h2":
            self._in_h2 = False
        if not self._capture:
            return
        # category 与 title 分别结束于 </a> 与 </h2>；venue/date 结束于 </div>
        closes = {"category": "a", "title": "h2", "venue": "div", "date": "div"}
        if closes.get(self._capture) != tag:
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        field, self._capture, self._buf = self._capture, None, []
        if not text or self._cur is None:
            return
        if field == "venue":
            # 第一个是主办方，第二个是地点
            self._venues.append(text)
            key = "organizer" if len(self._venues) == 1 else "location"
            self._cur.setdefault(key, text)
        else:
            self._cur.setdefault(field, text)

    def _flush_event(self):
        if self._cur and self._cur.get("title") and self._cur.get("path"):
            # slug 即稳定 id：站点没在列表页暴露 nid
            self._cur["slug"] = self._cur["path"].rstrip("/").split("/")[-1]
            self.events.append(self._cur)
        self._cur = None

    def close(self):
        self._flush_event()
        super().close()


def scrape(section: str, lang: str) -> list[dict]:
    prefix = f"/{lang}" if lang else ""
    url = f"{BASE}{prefix}/events/{section}"
    parser = EventListParser()
    parser.feed(fetch(url, f"{section}-{lang or 'en'}"))
    parser.close()
    for event in parser.events:
        event["section"] = section
        event["source_url"] = f"{BASE}{event.get('path', '')}"
    return parser.events


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    #: nid → 事件。两种语言合并到同一条上，标题/类别各存一份。
    merged: dict[str, dict] = {}

    for lang, locale in LOCALES.items():
        for section in SECTIONS:
            try:
                events = scrape(section, lang)
            except Exception as exc:  # noqa: BLE001
                print(f"  {section:16s} {locale:8s} ✗ {type(exc).__name__}: {exc}")
                continue
            for event in events:
                row = merged.setdefault(
                    event["slug"],
                    {"slug": event["slug"], "title": {}, "category": {},
                     "sections": []},
                )
                row["title"][locale] = event.get("title", "")
                row["category"][locale] = event.get("category", "")
                # 场地、时间、链接与语言无关，取第一次见到的
                for key in ("organizer", "location", "date", "source_url"):
                    if event.get(key) and key not in row:
                        row[key] = event[key]
                if event["section"] not in row["sections"]:
                    row["sections"].append(event["section"])
            print(f"  {section:16s} {locale:8s} {len(events):3d} 条")

    rows = sorted(merged.values(), key=lambda r: r["slug"])
    (OUT_DIR / "events.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 覆盖率——用来判断解析是否可靠，而不是"跑完就算成功"
    n = len(rows) or 1
    print(f"\n共 {len(rows)} 条活动，写入 {OUT_DIR}/events.json")
    print("字段覆盖率：")
    for key in ("title", "category", "organizer", "location", "date", "source_url"):
        have = sum(
            1 for r in rows
            if (r.get(key) if not isinstance(r.get(key), dict)
                else all(r[key].get(loc) for loc in LOCALES.values()))
        )
        print(f"  {key:14s} {have:4d}  {have / n * 100:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
