#!/usr/bin/env python3
"""
抓取 HKUST 公开本科课程目录 → 结构化 JSON。

来源：https://prog-crs.hkust.edu.hk/ugcourse/<TERM>/<SUBJECT>
这是学校公开的课程目录，只含课程信息（代码、名称、学分、先修、互斥、描述、
学习成果），**不含任何学生数据**。

礼貌抓取：串行 + 每次请求间隔，不并发压站；结果落盘缓存，重复运行不重抓。

用法：
    python3 seed/scrape_hkust_catalog.py                  # 全部学科
    python3 seed/scrape_hkust_catalog.py COMP MATH ELEC   # 指定学科
    python3 seed/scrape_hkust_catalog.py --list           # 只列学科代码
"""

from __future__ import annotations

import json
import pathlib
import re
import sys
import time
import urllib.request
from html.parser import HTMLParser

BASE = "https://prog-crs.hkust.edu.hk"
TERM = "2026-27"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CampusPath-research/1.0"
DELAY = 1.0  # 秒；礼貌间隔，别改小

OUT_DIR = pathlib.Path(__file__).parent / "raw" / "hkust_catalog"
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


def list_subjects() -> list[dict]:
    """从目录首页取学科代码与名称。"""
    html = fetch(f"{BASE}/ugcourse", "_index")
    # <a href="/ugcourse/2026-27/ACCT/" title="ACCT - Accounting">
    pat = re.compile(
        r'href="/ugcourse/' + re.escape(TERM) + r'/([A-Z]{2,6})/"\s+title="([^"]*)"'
    )
    seen, out = set(), []
    for code, title in pat.findall(html):
        if code in seen:
            continue
        seen.add(code)
        name = title.split(" - ", 1)[1].strip() if " - " in title else title.strip()
        out.append({"code": code, "name": name})
    return out


class CourseParser(HTMLParser):
    """
    按 class 属性提取。目标结构：
      li.crse
        div.crse-code / div.crse-title / div.crse-unit
        div.data-row > div.header + div.data      （Exclusion(s) / Prerequisite(s) / Description …）
        li.cilo > div.cilo-seq + div.cilo-desc    （intended learning outcomes）
    """

    FIELDS = {"crse-code", "crse-title", "crse-unit", "header", "data", "cilo-desc"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.courses: list[dict] = []
        self._cur: dict | None = None
        self._capture: str | None = None
        self._buf: list[str] = []
        self._last_header: str | None = None

    @staticmethod
    def _classes(attrs) -> set[str]:
        for k, v in attrs:
            if k == "class" and v:
                return set(v.split())
        return set()

    def handle_starttag(self, tag, attrs):
        cls = self._classes(attrs)

        if "crse" in cls:                      # 新课程开始
            self._flush_course()
            self._cur = {"cilo": []}

        for f in self.FIELDS:
            if f in cls:
                self._flush_field()
                self._capture = f
                self._buf = []
                break

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if self._capture:
            self._flush_field()

    def _flush_field(self):
        if not self._capture or self._cur is None:
            self._capture = None
            return
        text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
        f, self._capture, self._buf = self._capture, None, []
        if not text:
            return

        if f == "crse-code":
            self._cur["code"] = text
        elif f == "crse-title":
            self._cur["title"] = text
        elif f == "crse-unit":
            self._cur["units_raw"] = text
            m = re.search(r"([\d.]+)", text)
            if m:
                self._cur["credits"] = float(m.group(1))
        elif f == "header":
            self._last_header = text.rstrip(":").strip()
        elif f == "data":
            if self._last_header:
                key = (
                    self._last_header.lower()
                    .replace("(s)", "")
                    .replace(" ", "_")
                    .replace("/", "_")
                )
                self._cur[key] = text
                self._last_header = None
        elif f == "cilo-desc":
            self._cur["cilo"].append(text)

    def _flush_course(self):
        if self._cur and self._cur.get("code"):
            self.courses.append(self._cur)
        self._cur = None

    def close(self):
        self._flush_field()
        self._flush_course()
        super().close()


def scrape_subject(code: str) -> list[dict]:
    html = fetch(f"{BASE}/ugcourse/{TERM}/{code}", code)
    p = CourseParser()
    p.feed(html)
    p.close()
    for c in p.courses:
        c["subject"] = code
        c["term"] = TERM
    return p.courses


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]

    subjects = list_subjects()
    if "--list" in sys.argv:
        print(f"{len(subjects)} 个学科：")
        for s in subjects:
            print(f"  {s['code']:6s} {s['name']}")
        return 0

    targets = [s for s in subjects if s["code"] in args] if args else subjects
    if args and not targets:
        print(f"✗ 未找到学科 {args}，用 --list 查看可用代码")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_courses: list[dict] = []

    for i, s in enumerate(targets, 1):
        try:
            courses = scrape_subject(s["code"])
        except Exception as e:                                  # noqa: BLE001
            print(f"  [{i}/{len(targets)}] {s['code']:6s} ✗ {type(e).__name__}: {e}")
            continue
        all_courses.extend(courses)
        print(f"  [{i}/{len(targets)}] {s['code']:6s} {len(courses):3d} 门  {s['name'][:44]}")

    (OUT_DIR / "subjects.json").write_text(
        json.dumps(subjects, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "courses.json").write_text(
        json.dumps(all_courses, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 字段覆盖率——用于判断解析是否可靠，而不是"跑完就算成功"
    keys: dict[str, int] = {}
    for c in all_courses:
        for k in c:
            keys[k] = keys.get(k, 0) + 1
    n = len(all_courses) or 1
    print(f"\n共 {len(all_courses)} 门课，写入 {OUT_DIR}/courses.json")
    print("字段覆盖率：")
    for k, v in sorted(keys.items(), key=lambda x: -x[1]):
        print(f"  {k:28s} {v:5d}  {v / n * 100:5.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
