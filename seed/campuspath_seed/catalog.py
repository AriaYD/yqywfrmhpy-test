"""课程目录、开课与培养方案。

课程数据是**真实的 HKUST 公开目录**（`seed/raw/hkust_catalog/courses.json`），
包括先修表达式原文如 ``(COMP 2011 OR COMP 2012 OR COMP 2012H) AND (COMP 2711 OR ...)``。
Rules Engine 的先修解析拿真实表达式当测试素材，远好过编造。

开课时段（section / 上课时间 / 名额）与培养方案是**合成**的：
学校不公开这些，且我们需要可控的冲突与满额情形来做失败样本。
两者的界线在 ``CourseCatalogItem.source`` 与 ``CourseOffering`` 上分得很清楚。

培养方案里的每一个课程代码都会被 :func:`load_catalog` 断言存在于真实目录中——
写错一个代码不会静默变成"这门课不存在"，而是直接报错。
"""

from __future__ import annotations

import dataclasses
import json
import pathlib
from datetime import datetime, timezone

from campuspath_contracts.academic import (
    AcademicProgram,
    CapacityStatus,
    CourseCatalogItem,
    CourseOffering,
    DegreeRequirement,
    MeetingSlot,
    OfferingPattern,
)
from campuspath_contracts.common import Provenance

from .config import CURRENT_TERM, FUTURE_TERMS, SEED_TODAY, TERMS
from .rng import stream

RAW_PATH = pathlib.Path(__file__).resolve().parent.parent / "raw" / "hkust_catalog" / "courses.json"

_RETRIEVED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


@dataclasses.dataclass(frozen=True)
class RequirementGroupSpec:
    """一个毕业要求组。``course_codes`` 为空表示"该组从某学科任选"。"""

    group_id: str
    group: str
    rule: str
    required_credits: float
    course_codes: tuple[str, ...] = ()
    subject_pool: tuple[str, ...] = ()
    min_level: int = 1


# --------------------------------------------------------------------------
# 三个培养方案（Spec §11.2 要求 3–5 个）
#
# 课程组合参考真实开课结构，但**学分要求与组划分是合成的**：
# 我们需要一个能被 Rules Engine 完整校验、且能造出"职业目标满足但毕业学分不足"
# 这类失败样本的方案，而不是逐字复刻校方 handbook。
# --------------------------------------------------------------------------

_COMP_GROUPS = (
    RequirementGroupSpec(
        "BSC-COMP.CORE", "Major Required Core",
        "全部修读并及格", 30.0,
        ("COMP 2011", "COMP 2012", "COMP 2611", "COMP 2711", "COMP 3111",
         "COMP 3311", "COMP 3511", "COMP 3711"),
    ),
    RequirementGroupSpec(
        "BSC-COMP.INTRO", "Programming Foundation",
        "COMP 1021 与 COMP 1023 择一", 3.0,
        ("COMP 1021", "COMP 1023"),
    ),
    RequirementGroupSpec(
        "BSC-COMP.MATH", "Mathematics Requirement",
        "微积分 + 线性代数 + 概率统计各一", 12.0,
        ("MATH 1013", "MATH 1014", "MATH 2111", "MATH 2121", "MATH 2411"),
    ),
    RequirementGroupSpec(
        "BSC-COMP.ELECT", "Major Elective",
        "任选满 15 学分", 15.0,
        ("COMP 3021", "COMP 3031", "COMP 3211", "COMP 3213", "COMP 3631",
         "COMP 3721", "COMP 2211"),
    ),
    RequirementGroupSpec(
        "BSC-COMP.SCHOOL", "School of Engineering Requirement",
        "工程导论与实践", 7.0,
        ("ENGG 1100", "ENGG 1200", "ENGG 2800"),
    ),
    RequirementGroupSpec(
        "BSC-COMP.CC", "Common Core",
        "人文、社科与语言各修满", 27.0,
        subject_pool=("HUMA", "SOSC", "LANG"),
    ),
    RequirementGroupSpec(
        "BSC-COMP.FREE", "Free Elective", "任选", 26.0, subject_pool=("ENTR", "ISOM", "IEDA")
    ),
)

_ISOM_GROUPS = (
    RequirementGroupSpec(
        "BBA-ISOM.CORE", "Major Required Core", "全部修读并及格", 22.0,
        ("ISOM 2010", "ISOM 2500", "ISOM 2700", "ISOM 3210", "ISOM 3260", "ISOM 3400"),
    ),
    RequirementGroupSpec(
        "BBA-ISOM.ELECT", "Major Elective", "任选满 15 学分", 15.0,
        ("ISOM 3310", "ISOM 3350", "ISOM 3360", "ISOM 3370", "ISOM 3390",
         "ISOM 3530", "ISOM 3900"),
    ),
    RequirementGroupSpec(
        "BBA-ISOM.QUANT", "Quantitative Foundation", "统计与建模", 7.0,
        ("ISOM 2600", "ISOM 3710", "MATH 1013"),
    ),
    RequirementGroupSpec(
        "BBA-ISOM.CC", "Common Core", "人文、社科与语言", 27.0,
        subject_pool=("HUMA", "SOSC", "LANG"),
    ),
    RequirementGroupSpec(
        "BBA-ISOM.FREE", "Free Elective", "任选", 49.0, subject_pool=("ENTR", "COMP", "IEDA")
    ),
)

_IEDA_GROUPS = (
    RequirementGroupSpec(
        "BENG-IEDA.CORE", "Major Required Core", "全部修读并及格", 21.0,
        ("IEDA 1180", "IEDA 2010", "IEDA 2410", "IEDA 3010", "IEDA 3230", "IEDA 3300"),
    ),
    RequirementGroupSpec(
        "BENG-IEDA.ELECT", "Major Elective", "任选满 12 学分", 12.0,
        ("IEDA 3130", "IEDA 3250", "IEDA 3270", "IEDA 3330", "IEDA 3410", "IEDA 3560"),
    ),
    RequirementGroupSpec(
        "BENG-IEDA.MATH", "Mathematics Requirement", "微积分与线性代数", 10.0,
        ("MATH 1013", "MATH 1014", "MATH 2121"),
    ),
    RequirementGroupSpec(
        "BENG-IEDA.SCHOOL", "School of Engineering Requirement", "工程导论与实践", 7.0,
        ("ENGG 1100", "ENGG 1200", "ENGG 2800"),
    ),
    RequirementGroupSpec(
        "BENG-IEDA.CC", "Common Core", "人文、社科与语言", 27.0,
        subject_pool=("HUMA", "SOSC", "LANG"),
    ),
    RequirementGroupSpec(
        "BENG-IEDA.FREE", "Free Elective", "任选", 43.0, subject_pool=("ENTR", "COMP", "ISOM")
    ),
)

PROGRAM_SPECS: dict[str, tuple[str, str, str, tuple[RequirementGroupSpec, ...]]] = {
    "BSC-COMP": ("BSc", "Computer Science", "2024-25", _COMP_GROUPS),
    "BBA-ISOM": ("BBA", "Information Systems", "2024-25", _ISOM_GROUPS),
    "BENG-IEDA": ("BEng", "Industrial Engineering and Decision Analytics", "2024-25", _IEDA_GROUPS),
}

TOTAL_CREDITS = 120.0


@dataclasses.dataclass
class Catalog:
    courses: dict[str, CourseCatalogItem]
    offerings: list[CourseOffering]
    programs: list[AcademicProgram]
    requirements: list[DegreeRequirement]

    def by_group(self, group_id: str) -> list[str]:
        for req in self.requirements:
            if req.requirement_id == group_id:
                return list(req.alternatives)
        raise KeyError(group_id)

    def offerings_for(self, course_id: str, term: str) -> list[CourseOffering]:
        return [o for o in self.offerings if o.course_id == course_id and o.term == term]


def _skill_tags(raw: dict) -> tuple[str, ...]:
    """从课程标题与描述映射技能标签。

    真实系统里这一步由 A2 做语义映射；Seed 用关键词表给出**初版标签**，
    A2 的产出会覆盖它。这里只需要标签在跨表引用上自洽。
    """
    text = f"{raw['title']} {raw.get('description', '')}".lower()
    table = {
        "programming": ("programming", "python", "java", "c++", "coding"),
        "data_structures": ("data structure", "algorithm"),
        "databases": ("database", "sql"),
        "machine_learning": ("machine learning", "artificial intelligence", "deep learning"),
        "statistics": ("statistic", "probability", "regression"),
        "optimization": ("optimization", "linear program", "operations research"),
        "software_engineering": ("software engineering", "requirement", "testing"),
        "systems": ("operating system", "computer organization", "network"),
        "communication": ("presentation", "writing", "communication"),
        "business_analysis": ("business", "management", "supply chain", "e-commerce"),
        "user_research": ("user", "human-computer", "interface", "survey"),
        "security": ("security", "cryptograph", "cybersecurity"),
    }
    return tuple(sorted(tag for tag, needles in table.items() if any(n in text for n in needles)))


def _offering_pattern(code: str, rng_value: float) -> OfferingPattern:
    """低阶课每学期开，高阶课按学期轮换，少数不规律——用于"课程不开设"失败样本。"""
    level = int(code.split()[1][0])
    if level <= 2:
        return OfferingPattern.EVERY_TERM
    if rng_value < 0.15:
        return OfferingPattern.IRREGULAR
    return OfferingPattern.FALL_ONLY if rng_value < 0.55 else OfferingPattern.SPRING_ONLY


def _terms_for(pattern: OfferingPattern, term: str) -> bool:
    is_fall = term.endswith("_FALL")
    return {
        OfferingPattern.EVERY_TERM: True,
        OfferingPattern.FALL_ONLY: is_fall,
        OfferingPattern.SPRING_ONLY: not is_fall,
        OfferingPattern.ALTERNATE_YEARS: is_fall,
        OfferingPattern.IRREGULAR: False,
        OfferingPattern.UNKNOWN: False,
    }[pattern]


_WEEKDAYS = ("MO", "TU", "WE", "TH", "FR")
_START_TIMES = ("09:00", "10:30", "12:00", "13:30", "15:00", "16:30")
_VENUES = ("Rm 2464", "Rm 4502", "Lecture Theatre A", "Rm 1409", "Rm 5583")


def _read_raw() -> list[dict]:
    if not RAW_PATH.exists():
        raise FileNotFoundError(
            f"缺少 {RAW_PATH}。先跑：python3 seed/scrape_hkust_catalog.py "
            "COMP MATH ELEC ISOM IEDA ENGG ENTR LANG HUMA SOSC DSCT"
        )
    return json.loads(RAW_PATH.read_text(encoding="utf-8"))


def load_catalog(programs: tuple[str, ...] | None = None) -> Catalog:
    """构建目录。

    ``programs`` 限定要构建哪些培养方案（tiny 档只建一个）。
    **不提供"只保留 N 门课"的选项**：那会让培养方案引用到被裁掉的课程，
    造出跨表不一致的数据——正是 Spec §11.5 明令禁止的那种矛盾。
    要更小的数据集，就少建几个培养方案。
    """
    raw = {c["code"]: c for c in _read_raw()}
    rng = stream("catalog.offerings")
    specs = {
        pid: spec for pid, spec in PROGRAM_SPECS.items()
        if programs is None or pid in programs
    }

    required_codes: set[str] = set()
    for _, _, _, groups in specs.values():
        for group in groups:
            required_codes.update(group.course_codes)

    missing = sorted(required_codes - set(raw))
    if missing:
        raise ValueError(
            f"培养方案引用了真实目录中不存在的课程：{missing}。"
            "要么代码写错了，要么该学科还没抓取。"
        )

    # 池子：**整份公开目录**（58 个学科 1500+ 门）。
    #
    # 曾经这里只按学科各取 6 门，凑出百来门。那样够渲染页面，但不够
    # 回答产品真正的问题——"这门课和你的目标有多大关系"、"和毕业要求
    # 有多大关系"——那要靠 description 与 ILO 的覆盖面，样本一小就退化成
    # 在几十门课里挑。目录是公开数据，没有理由自己给自己设上限。
    #
    # 学分为 0 的（纯挂名、实习登记之类）不进池：它们进不了学分计算，
    # 留在里面只会让"还差多少学分"这类算式多一堆恒为 0 的项。
    pool_codes = set(required_codes) | {
        code for code, c in raw.items() if c["credits"] > 0
    }

    selected = sorted(pool_codes)

    courses: dict[str, CourseCatalogItem] = {}
    offerings: list[CourseOffering] = []
    for code in selected:
        item = raw[code]
        pattern = _offering_pattern(code, rng.random())
        courses[code] = CourseCatalogItem(
            course_id=code,
            subject=item["subject"],
            title=item["title"],
            description=(item.get("description") or None),
            credits=float(item["credits"]),
            prerequisite_expression=item.get("prerequisite"),
            corequisite_expression=item.get("corequisite"),
            exclusion_expression=item.get("exclusion"),
            previous_course_code=item.get("previous_course_code"),
            offering_pattern=pattern,
            skill_tags=_skill_tags(item),
            intended_learning_outcomes=tuple(item.get("cilo", ())[:6]),
            source=Provenance(
                source="hkust_ugcourse",
                source_url=f"https://prog-crs.hkust.edu.hk/ugcourse/{item['term']}/{item['subject']}",
                retrieved_at=_RETRIEVED_AT,
                parser_version="hkust-catalog/0.1",
                evidence_snippet=item["title"],
                confidence=1.0,
            ),
        )

        for term in (CURRENT_TERM, *FUTURE_TERMS):
            if not _terms_for(pattern, term):
                continue
            section_count = 2 if int(code.split()[1][0]) <= 2 else 1
            for index in range(section_count):
                weekday = _WEEKDAYS[rng.randrange(len(_WEEKDAYS))]
                start = _START_TIMES[rng.randrange(len(_START_TIMES))]
                end_hour = int(start[:2]) + 1
                capacity = CapacityStatus.OPEN
                roll = rng.random()
                if roll < 0.08:
                    capacity = CapacityStatus.FULL       # 「满额」失败样本的素材
                elif roll < 0.16:
                    capacity = CapacityStatus.WAITLIST
                term_end = TERMS[term][1]
                offerings.append(
                    CourseOffering(
                        offering_id=f"{code.replace(' ', '')}-{term}-L{index + 1}",
                        course_id=code,
                        term=term,
                        section=f"L{index + 1}",
                        schedule=(
                            MeetingSlot(
                                weekday=weekday,
                                start_time=start,
                                end_time=f"{end_hour:02d}:{start[3:]}",
                                venue=_VENUES[rng.randrange(len(_VENUES))],
                            ),
                        ),
                        capacity_status=capacity,
                        instructor=None,
                        delivery_mode="in_person",
                        exam_time=datetime(
                            term_end.year, term_end.month, term_end.day, 8 + index * 3,
                            tzinfo=timezone.utc,
                        ),
                        updated_at=datetime(
                            SEED_TODAY.year, SEED_TODAY.month, SEED_TODAY.day, tzinfo=timezone.utc
                        ),
                    )
                )

    programs: list[AcademicProgram] = []
    requirements: list[DegreeRequirement] = []
    for program_id, (degree, major, catalog_year, groups) in sorted(specs.items()):
        programs.append(
            AcademicProgram(
                program_id=program_id,
                degree=degree,
                major=major,
                catalog_year=catalog_year,
                total_credits=TOTAL_CREDITS,
                requirement_group_ids=tuple(g.group_id for g in groups),
                policy_source=Provenance(
                    source="synthetic_degree_audit",
                    retrieved_at=_RETRIEVED_AT,
                    parser_version="seed/1.0.0",
                    evidence_snippet="合成培养方案，非校方 handbook",
                    confidence=0.6,
                ),
            )
        )
        for group in groups:
            alternatives = group.course_codes
            if not alternatives and group.subject_pool:
                alternatives = tuple(
                    sorted(
                        code for code in courses
                        if courses[code].subject in group.subject_pool
                    )
                )
            requirements.append(
                DegreeRequirement(
                    requirement_id=group.group_id,
                    program_id=program_id,
                    group=group.group,
                    rule=group.rule,
                    required_credits=group.required_credits,
                    alternatives=alternatives,
                )
            )

    return Catalog(
        courses=courses, offerings=offerings, programs=programs, requirements=requirements
    )
