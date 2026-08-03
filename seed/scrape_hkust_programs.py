#!/usr/bin/env python3
"""
抓取 HKUST 本科专业的四年教学要求（Major Requirements）→ 结构化 JSON。

来源（按权威顺序）：
  1. https://prog-crs.hkust.edu.hk/ugprog/<TERM>/<CODE>   —— 官方专业目录页，
     含 Award Title / Offering unit / Curriculum Requirements 区块，后者链到
     "Major Requirements" 与（部分学院）"School Requirements" 的 PDF。
  2. https://ugadmin.hkust.edu.hk/prog_crs/ug/<TERM_NO_DASH>/pdf/<slug>.pdf
     —— 上面链接指向的权威课程要求 PDF（必修/选修分组 + 学分/门数）。
  3. https://registry.hkust.edu.hk/resource-library/academic-regulations-governing-ug-studies-<TERM>
     —— 全校性毕业规定（120 学分下限、Common Core、CGA 预警/留校察看阈值等），
     不因专业而异，抓一次全部专业共用。

风格对齐 scrape_hkust_catalog.py：requests 替换为 urllib（无第三方依赖）、磁盘缓存、
1s 礼貌间隔、固定 User-Agent。PDF 用系统 `pdftotext -layout`（poppler，本机已装）转
文本再用状态机解析成"必修/选修分组 + 课程码列表"。

用法：
    python3 seed/scrape_hkust_programs.py                # 抓 5 个目标专业
    python3 seed/scrape_hkust_programs.py --list          # 只列目标专业代码
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser

TERM = "2026-27"
TERM_NO_DASH = TERM.replace("-", "")
UGPROG_BASE = "https://prog-crs.hkust.edu.hk/ugprog"
AR_URL = (
    "https://registry.hkust.edu.hk/resource-library/"
    f"academic-regulations-governing-ug-studies-{TERM}"
)
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) CampusPath-research/1.0"
DELAY = 1.0  # 秒；礼貌间隔，别改小

OUT_DIR = pathlib.Path(__file__).parent / "raw" / "hkust_programs"
CACHE_DIR = OUT_DIR / "_cache"
CATALOG_COURSES = (
    pathlib.Path(__file__).parent / "raw" / "hkust_catalog" / "courses.json"
)

# 目标专业。LIFS/BISC（Biological Science）在 2026-27 目录中已不存在独立主修——
# Life Science 分部现在拆成 BCB / BIOT / BIBU / BMH 四个更具体的专业。按任务里
# "信息难抓可换成信息更完整的专业" 的指示，用 BCB（Biochemistry and Cell
# Biology，文档最完整、页面结构与其余专业一致）替代。
PROGRAMS = [
    {"program_id": "COMP", "ugprog_code": "COMP", "substituted_for": None},
    {"program_id": "CENG", "ugprog_code": "CENG", "substituted_for": None},
    {"program_id": "MATH", "ugprog_code": "MATH", "substituted_for": None},
    {"program_id": "MECH", "ugprog_code": "MECH", "substituted_for": None},
    # 2026-07-31 尝试补 IEDA / ISOM（演示学生 B/C 的本专业）：ugprog 页是
    # 无 PDF 链接的空壳（实测 requirement 组抓到 0 个、name 为空），
    # 按"不编造"原则不入库——选课页对这两个专业如实显示"要求未接入沙箱"。
    {
        "program_id": "BCB",
        "ugprog_code": "BCB",
        "substituted_for": (
            "Biological Science (LIFS/BISC) — no standalone major exists in the "
            f"{TERM} catalog; Life Science division offers BCB/BIOT/BIBU/BMH "
            "instead. BCB (BSc in Biochemistry and Cell Biology) chosen as the "
            "closest, best-documented match."
        ),
    },
]

# ---------------------------------------------------------------------------
# 抓取 + 缓存
# ---------------------------------------------------------------------------


def fetch_text(url: str, cache_key: str) -> str:
    """带磁盘缓存的 GET，返回文本（C2 起委托共享抓取器，行为不变）。"""
    return _shared_fetch(url, CACHE_DIR, cache_key, delay=DELAY)


def _import_shared_fetch():
    try:
        from campuspath_connector.fetcher import fetch as shared
    except ImportError:  # 脚本用系统 python3 直跑时，包不在 sys.path
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "services" / "connector"))
        from campuspath_connector.fetcher import fetch as shared
    return shared


_shared_fetch = _import_shared_fetch()


def fetch_pdf_text(url: str, cache_key: str) -> str:
    """下载 PDF（带缓存）→ pdftotext -layout 转文本（也缓存）。"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pdf_path = CACHE_DIR / f"{cache_key}.pdf"
    txt_path = CACHE_DIR / f"{cache_key}.txt"

    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8", errors="ignore")

    if not pdf_path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        pdf_path.write_bytes(data)
        time.sleep(DELAY)

    result = subprocess.run(
        ["pdftotext", "-layout", str(pdf_path), str(txt_path)],
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"pdftotext 失败 ({cache_key}): {result.stderr.decode(errors='ignore')}"
        )
    return txt_path.read_text(encoding="utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# ugprog 专业页解析（Award Title / Offering unit / Curriculum Requirements 链接）
# ---------------------------------------------------------------------------

_ROW_RE = re.compile(
    r'<div class="block-row-heading">(.*?)</div>'
    r'<div class="block-row-content">(.*?)</div></div>',
    re.S,
)
_ANCHOR_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(s: str) -> str:
    s = _TAG_RE.sub(" ", s)
    s = s.replace("&amp;", "&").replace("&rsquo;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", s).strip()


def parse_program_page(html: str) -> dict:
    fields: dict[str, str] = {}
    links: list[tuple[str, str]] = []
    for heading_html, content_html in _ROW_RE.findall(html):
        heading = _clean(heading_html)
        if heading == "Curriculum Requirements":
            for href, text in _ANCHOR_RE.findall(content_html):
                links.append((href, _clean(text)))
            fields[heading] = _clean(content_html)
        else:
            fields[heading] = _clean(content_html)

    major_pdf_url = None
    school_pdf_url = None
    for href, text in links:
        if text.startswith("Major Requirements"):
            major_pdf_url = href
        elif text.startswith("School Requirements"):
            school_pdf_url = href

    total_credits = None
    m = re.search(r"At least (\d+) credits", fields.get("Curriculum Requirements", ""))
    if m:
        total_credits = int(m.group(1))

    return {
        "award_title": fields.get("Award Title"),
        "offering_unit": fields.get("Offering unit"),
        "normative_duration": fields.get("Normative Program Duration"),
        "program_website": fields.get("Program website"),
        "major_pdf_url": major_pdf_url,
        "school_pdf_url": school_pdf_url,
        "total_credits_required": total_credits,
    }


# ---------------------------------------------------------------------------
# Major/School Requirements PDF 文本 → 分组解析
# ---------------------------------------------------------------------------

HEADER_TYPE = {
    "Major Pre-requisite course(s)": "required",
    "Engineering Fundamental Course(s)": "required",
    "Required Course(s)": "required",
    "Elective(s)": "elective",
    "Elective Course(s)": "elective",
}

_NOISE_LINES = {
    "",
    "Credit(s)",
    "attained",
    "Minimum",
    "credit(s)",
    "required",
    "Credit(s) attained",
}

_TRACK_RE = re.compile(r"^[A-Za-z][A-Za-z()/,\- ]* Track$")
_OPTION_RE = re.compile(r"^[A-Za-z][A-Za-z()/,\- ]* Option$")
_FOOTER_RE = re.compile(r"^\d{4}-\d{2} [A-Z\-&]+ \(\dY\)")
_PAGE_RE = re.compile(r"^Page \d+$")
_COURSE_RE = re.compile(r"\b([A-Z]{2,6})\s+(\d{3,4}[A-Z]{0,2})\*{0,2}\b(?!-level)")
_COUNT_RE = re.compile(r"[\(\[](\d+)\s+courses?\b", re.I)
_TRAILING_NUM_RE = re.compile(r"(\d+(?:\.\d+)?)\s*$")


class _Group:
    __slots__ = ("name", "type", "course_codes", "lines", "has_or_logic")

    def __init__(self, name: str, type_: str) -> None:
        self.name = name
        self.type = type_
        self.course_codes: set[str] = set()
        self.lines: list[str] = []
        self.has_or_logic = False


def parse_requirement_groups(text: str, source_url: str) -> list[dict]:
    """状态机解析 pdftotext -layout 输出，按 Track/Option/子表头切分成必修/选修分组。"""
    groups: dict[tuple, _Group] = {}
    order: list[tuple] = []

    active = False  # 是否已进入 "Major Requirements" 或 "School Requirements" 区
    track: str | None = None
    option: str | None = None
    subsection: str | None = None
    subsection_type: str | None = None

    for raw_line in text.splitlines():
        stripped = raw_line.strip()

        if stripped == "**Remarks on course(s):":
            break  # 尾注，不再需要

        if stripped in ("Major Requirements", "School Requirements"):
            active = True
            track = None
            option = None
            subsection = "School Requirements" if stripped == "School Requirements" else None
            subsection_type = "required" if stripped == "School Requirements" else None
            continue

        if not active:
            continue

        header_hit = None
        if stripped in HEADER_TYPE:
            header_hit = stripped
        else:
            # "Elective(s)" / "Elective Course(s)" 标题短，PDF 原版式里右侧
            # "Minimum credit(s) required" 列头会和标题共享同一行（pdftotext
            # -layout 按 y 坐标对齐），"Required Course(s)" 反而总是独占一行。
            for h in HEADER_TYPE:
                if h.startswith("Elective") and stripped.startswith(h):
                    header_hit = h
                    break
        if header_hit:
            subsection = header_hit
            subsection_type = HEADER_TYPE[header_hit]
            continue

        if stripped in ("Track Study", "Option(s)"):
            continue

        if _TRACK_RE.match(stripped) and not any(c.isdigit() for c in stripped):
            track = stripped
            subsection = None
            continue

        if _OPTION_RE.match(stripped) and not any(c.isdigit() for c in stripped):
            option = stripped
            subsection = None
            continue

        if stripped in _NOISE_LINES or _FOOTER_RE.match(stripped) or _PAGE_RE.match(stripped):
            continue

        if stripped.startswith("School of") or " - B" in stripped and stripped.startswith("School"):
            continue

        if subsection is None:
            continue  # 说明性段落（介绍文字），非分组内容

        key = (track, option, subsection)
        if key not in groups:
            name_parts = [p for p in (track, option, subsection) if p]
            g = _Group(" — ".join(name_parts), subsection_type or "required")
            groups[key] = g
            order.append(key)
        g = groups[key]
        g.lines.append(stripped)
        if "Note:" in stripped:
            g.has_or_logic = True
        for subj, num in _COURSE_RE.findall(stripped):
            g.course_codes.add(f"{subj} {num}")

    out = []
    scraped_at = datetime.now(timezone.utc).isoformat()
    for key in order:
        g = groups[key]
        if not g.course_codes and not g.lines:
            continue

        courses_required = None
        credits_required = None
        joined = " ".join(g.lines)
        m = _COUNT_RE.search(joined)
        if m:
            courses_required = int(m.group(1))
        # 显式 minimum credit：组内第一行若不是课程行本身（即该行没有匹配到课程码
        # 紧跟学分的"单课程行"模式，而是描述性汇总行），取其行尾数字。
        if g.lines:
            first = g.lines[0]
            first_is_bare_course_row = bool(
                re.match(r"^[A-Z]{2,6}(/[A-Z]{2,6})*\s+\d{3,4}", first)
            )
            if not first_is_bare_course_row:
                m2 = _TRAILING_NUM_RE.search(first)
                if m2:
                    try:
                        credits_required = float(m2.group(1))
                        if credits_required == int(credits_required):
                            credits_required = int(credits_required)
                    except ValueError:
                        credits_required = None

        # estimated_credits_sum：仅对 required 组，用"顶层行"（缩进最浅、不是
        # 嵌套 OR 备选课程）的学分数字做保守求和（区间取低值），标注为估算。
        estimated_credits_sum = None
        if g.type == "required":
            total = 0.0
            any_top = False
            for raw in g.lines:
                indent = len(raw) - len(raw.lstrip(" "))
                # 顶层行在原始（未 strip）文本里前导空格很浅；这里 raw 已 strip，
                # 改用是否含 "Note:" 或是否为纯课程行判断，缩进信息已丢失，
                # 因此改为：只对不含 "Note:" 且匹配单课程行模式的行求和，
                # 避免把同一 OR 组内的多个备选课程重复计入。
                if "Note:" in raw:
                    continue
                mrow = re.match(
                    r"^[A-Z]{2,6}(/[A-Z]{2,6})*\*{0,2}\s+\d{3,4}[A-Z]{0,2}\*{0,2}\s+.*?(\d+(?:\.\d+)?)\s*$",
                    raw,
                )
                if mrow:
                    any_top = True
                    total += float(mrow.group(2))
            if any_top:
                estimated_credits_sum = total

        out.append(
            {
                "group_name": g.name,
                "type": g.type,
                "credits_required": credits_required,
                "courses_required": courses_required,
                "estimated_credits_sum": estimated_credits_sum,
                "has_or_logic": g.has_or_logic,
                "course_codes": sorted(g.course_codes),
                "source_url": source_url,
                "scraped_at": scraped_at,
            }
        )
    return out


# ---------------------------------------------------------------------------
# 全校毕业规定（一次性抓，所有专业共用）
# ---------------------------------------------------------------------------


def parse_university_graduation_requirements(html: str) -> dict:
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = _TAG_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)

    out = {
        "total_credits_min": None,
        "common_core_required": None,
        "english_language_requirement": None,
        "legal_education_requirement": None,
        "cga_academic_warning_threshold": None,
        "cga_academic_probation_threshold": None,
        "source_url": AR_URL,
    }

    m = re.search(r"Earn at least (\d+) credits", text)
    if m:
        out["total_credits_min"] = int(m.group(1))
    out["common_core_required"] = "University Common Core Program" in text
    out["english_language_requirement"] = "University English Language Requirement" in text
    out["legal_education_requirement"] = "University Legal Education Requirement" in text

    m = re.search(r"is less than (\d+\.\d+) will be placed on Academic Warning", text)
    if m:
        out["cga_academic_warning_threshold"] = float(m.group(1))
    m = re.search(r"CGA falls below (\d+\.\d+).*?will be put on Academic Probation", text)
    if m:
        out["cga_academic_probation_threshold"] = float(m.group(1))

    return out


# ---------------------------------------------------------------------------
# 交叉核对
# ---------------------------------------------------------------------------


def load_catalog_codes() -> set[str]:
    if not CATALOG_COURSES.exists():
        return set()
    data = json.loads(CATALOG_COURSES.read_text(encoding="utf-8"))
    return {c["code"] for c in data if "code" in c}


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> int:
    if "--list" in sys.argv:
        for p in PROGRAMS:
            note = f"  (substitute for {p['substituted_for']})" if p["substituted_for"] else ""
            print(f"  {p['program_id']:6s}{note}")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print("抓取全校毕业规定（一次性，所有专业共用）...")
    ar_html = fetch_text(AR_URL, "_academic_regulations")
    university_reqs = parse_university_graduation_requirements(ar_html)

    school_pdf_cache: dict[str, list[dict]] = {}
    programs_out = []
    source_summary = []

    for i, prog in enumerate(PROGRAMS, 1):
        code = prog["ugprog_code"]
        page_url = f"{UGPROG_BASE}/{TERM}/{code}"
        print(f"  [{i}/{len(PROGRAMS)}] {code} 专业页 {page_url}")
        try:
            html = fetch_text(page_url, f"page_{code}")
        except Exception as e:  # noqa: BLE001
            print(f"    ✗ 专业页抓取失败: {type(e).__name__}: {e}")
            continue
        meta = parse_program_page(html)

        groups: list[dict] = []

        if meta["major_pdf_url"]:
            try:
                major_txt = fetch_pdf_text(meta["major_pdf_url"], f"major_{code}")
                groups.extend(parse_requirement_groups(major_txt, meta["major_pdf_url"]))
            except Exception as e:  # noqa: BLE001
                print(f"    ✗ Major Requirements PDF 解析失败: {type(e).__name__}: {e}")
        else:
            print("    ✗ 未找到 Major Requirements PDF 链接")

        if meta["school_pdf_url"]:
            if meta["school_pdf_url"] in school_pdf_cache:
                groups.extend(school_pdf_cache[meta["school_pdf_url"]])
            else:
                try:
                    slug = meta["school_pdf_url"].rsplit("/", 1)[-1].replace(".pdf", "")
                    school_txt = fetch_pdf_text(meta["school_pdf_url"], f"school_{slug}")
                    school_groups = parse_requirement_groups(
                        school_txt, meta["school_pdf_url"]
                    )
                    school_pdf_cache[meta["school_pdf_url"]] = school_groups
                    groups.extend(school_groups)
                except Exception as e:  # noqa: BLE001
                    print(f"    ✗ School Requirements PDF 解析失败: {type(e).__name__}: {e}")

        n_courses = sum(len(g["course_codes"]) for g in groups)
        print(
            f"    ✓ {meta['award_title'] or code} | {len(groups)} 个要求组 | "
            f"{n_courses} 门课引用（含重复）"
        )

        source_summary.append(
            {
                "program_id": prog["program_id"],
                "program_page": page_url,
                "major_pdf": meta["major_pdf_url"],
                "school_pdf": meta["school_pdf_url"],
                "n_groups": len(groups),
                "n_course_refs": n_courses,
            }
        )

        programs_out.append(
            {
                "program_id": prog["program_id"],
                "name": meta["award_title"],
                "school": meta["offering_unit"],
                "normative_duration": meta["normative_duration"],
                "program_website": meta["program_website"],
                "total_credits_required": meta["total_credits_required"],
                "substituted_for": prog["substituted_for"],
                "university_graduation_requirements": university_reqs,
                "requirement_groups": groups,
                "source_urls": {
                    "program_page": page_url,
                    "major_requirements_pdf": meta["major_pdf_url"],
                    "school_requirements_pdf": meta["school_pdf_url"],
                },
                "scraped_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    out_path = OUT_DIR / "programs.json"
    out_path.write_text(
        json.dumps(programs_out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- 字段覆盖率 ----------------------------------------------------
    all_groups = [g for p in programs_out for g in p["requirement_groups"]]
    n_groups = len(all_groups) or 1
    group_field_cov: dict[str, int] = {}
    for g in all_groups:
        for k, v in g.items():
            if v not in (None, [], ""):
                group_field_cov[k] = group_field_cov.get(k, 0) + 1

    n_progs = len(programs_out) or 1
    prog_field_cov: dict[str, int] = {}
    for p in programs_out:
        for k, v in p.items():
            if k == "requirement_groups":
                continue
            if v not in (None, [], ""):
                prog_field_cov[k] = prog_field_cov.get(k, 0) + 1

    print(f"\n共 {len(programs_out)} 个专业，{len(all_groups)} 个要求组，写入 {out_path}")
    print("\n专业级字段覆盖率：")
    for k, v in sorted(prog_field_cov.items(), key=lambda x: -x[1]):
        print(f"  {k:32s} {v:3d}/{n_progs}  {v / n_progs * 100:5.1f}%")
    print("\n要求组级字段覆盖率：")
    for k, v in sorted(group_field_cov.items(), key=lambda x: -x[1]):
        print(f"  {k:32s} {v:3d}/{n_groups}  {v / n_groups * 100:5.1f}%")

    # ---- 与课程目录快照交叉核对 ------------------------------------------
    catalog_codes = load_catalog_codes()
    all_refs = set()
    for g in all_groups:
        all_refs.update(g["course_codes"])
    if catalog_codes:
        hits = {c for c in all_refs if c in catalog_codes}
        rate = len(hits) / len(all_refs) * 100 if all_refs else 0.0
        print(
            f"\n课程码交叉核对：programs.json 引用 {len(all_refs)} 个不同课程码，"
            f"命中 seed/raw/hkust_catalog/courses.json 中 {len(hits)} 个（{rate:.1f}%）"
        )
        misses = sorted(all_refs - hits)
        if misses:
            print(f"  未命中 {len(misses)} 个（前 20 个示例）：")
            for c in misses[:20]:
                print(f"    {c}")
    else:
        print("\n⚠ 未找到 seed/raw/hkust_catalog/courses.json，跳过交叉核对")

    print("\n数据源：")
    for s in source_summary:
        print(f"  {s['program_id']:6s} 专业页: {s['program_page']}")
        print(f"         Major PDF: {s['major_pdf']}")
        if s["school_pdf"]:
            print(f"         School PDF: {s['school_pdf']}")
        print(f"         要求组 {s['n_groups']} 个，课程引用（含重复）{s['n_course_refs']} 条")

    return 0


if __name__ == "__main__":
    sys.exit(main())
