"""机会池：实习/工作、活动、实验室、竞赛。

每条机会都带 **生成规则**（``OpportunityMeta.generation_rule``），
这是 Spec §11.5「每条机会保存生成规则与 Gold Label」的前半段；
后半段（四态资格的 Gold Label）在 :mod:`campuspath_seed.goldset`，
因为资格是「学生 × 机会」的函数，不属于机会本身。

资格规则尽量引用**真实课程代码**，这样"先修未满足"这类判定在
Rules Engine 里走的是真实先修表达式，而不是编造的占位符。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

from campuspath_contracts.common import LocalizedText, Provenance
from campuspath_contracts.goals import RequirementCategory
from campuspath_contracts.opportunity import (
    OrganizerCategory,
    EligibilityRule,
    EligibilityRuleKind,
    Opportunity,
    OpportunityType,
    PublicationStatus,
)

from .catalog import Catalog
from .config import SEED_TODAY
from .rng import pick, sample, stream

_TZ = timezone.utc


def _dt(d: date, hour: int = 23) -> datetime:
    return datetime(d.year, d.month, d.day, hour, 59, tzinfo=_TZ)


@dataclasses.dataclass
class OpportunityMeta:
    """机会的生成规则与失败样本标记。不进 Catalog，只进 Seed 的元数据文件。"""

    opportunity_id: str
    generation_rule: str
    failure_kind: str | None = None


#: (zh, en) 对。数据身份仍是中文那一侧——``organizer`` 字段保持中文原值，
#: 英文只进 ``organizer_localized``，见 seed/1.3.0 变更记录。
ORGANIZERS: tuple[tuple[str, str], ...] = (
    ("合成科技公司 Alpha（Demo）", "Synthetic Tech Company Alpha (Demo)"),
    ("合成金融科技公司（Demo）", "Synthetic FinTech Company (Demo)"),
    ("合成物流集团（Demo）", "Synthetic Logistics Group (Demo)"),
    ("合成咨询事务所（Demo）", "Synthetic Consulting Firm (Demo)"),
    ("合成医疗数据公司（Demo）", "Synthetic Health Data Company (Demo)"),
    ("校友创办的合成初创（Demo）", "Synthetic Alumni-Founded Startup (Demo)"),
    ("HKUST 合成职业发展中心（Demo）", "HKUST Synthetic Career Development Center (Demo)"),
    ("合成运筹实验室（Demo）", "Synthetic Operations Research Lab (Demo)"),
    ("合成人机交互实验室（Demo）", "Synthetic Human-Computer Interaction Lab (Demo)"),
    ("合成学生创业社（Demo）", "Synthetic Student Entrepreneurship Society (Demo)"),
)

_SOURCES = (
    ("SRC-career-center", "career_center_feed"),
    ("SRC-lab-site", "lab_website"),
    ("SRC-club-portal", "publisher_portal"),
    ("SRC-partner-ats", "partner_ats"),
    ("SRC-events-calendar", "campus_events_calendar"),
)

#: (zh, en) 对，见 ``ORGANIZERS`` 同样的口径。
_INTERNSHIP_TITLES: tuple[tuple[str, str], ...] = (
    ("数据分析实习生", "Data Analyst Intern"),
    ("后端开发实习生", "Backend Developer Intern"),
    ("产品运营实习生", "Product Operations Intern"),
    ("供应链分析实习生", "Supply Chain Analyst Intern"),
    ("机器学习实习生", "Machine Learning Intern"),
    ("商业分析实习生", "Business Analyst Intern"),
    ("前端开发实习生", "Frontend Developer Intern"),
    ("量化研究实习生", "Quantitative Research Intern"),
    ("用户研究实习生", "User Research Intern"),
    ("运营策略实习生", "Operations Strategy Intern"),
    ("平台工程实习生", "Platform Engineering Intern"),
    ("风控建模实习生", "Risk Modeling Intern"),
)

_EVENT_TITLES: tuple[tuple[str, str], ...] = (
    ("简历工作坊", "Resume Workshop"),
    ("行业分享会", "Industry Sharing Session"),
    ("技术开放日", "Tech Open Day"),
    ("校友职业对谈", "Alumni Career Talk"),
    ("产品经理入门讲座", "Intro to Product Management Talk"),
    ("数据可视化实操课", "Data Visualization Hands-On Class"),
    ("面试模拟演练", "Mock Interview Practice"),
    ("创业者交流夜", "Founders Networking Night"),
    ("开源贡献入门", "Intro to Open Source Contribution"),
    ("职场沟通训练", "Workplace Communication Training"),
    ("行业趋势圆桌", "Industry Trends Roundtable"),
    ("作品集诊断会", "Portfolio Review Clinic"),
    # 审计蓝色供给缺口（2026-08-02）：全库零游戏类活动——换一个游戏向
    # 目标就会暴露"推荐与目标无关"。补三条游戏开发向的合成活动。
    ("游戏开发工作坊：Unity 入门", "Game Dev Workshop: Intro to Unity"),
    ("独立游戏制作分享会", "Indie Game Development Sharing Session"),
    ("48 小时游戏创作马拉松", "48-Hour Game Jam"),
)

_LAB_TITLES: tuple[tuple[str, str], ...] = (
    ("本科研究助理：排班优化", "Undergraduate Research Assistant: Scheduling Optimization"),
    ("本科研究助理：推荐系统", "Undergraduate Research Assistant: Recommender Systems"),
    ("本科研究助理：人机交互", "Undergraduate Research Assistant: Human-Computer Interaction"),
    ("暑期研究计划：图神经网络", "Summer Research Program: Graph Neural Networks"),
    ("本科研究助理：运筹与物流", "Undergraduate Research Assistant: Operations Research & Logistics"),
)

_COMPETITION_TITLES: tuple[tuple[str, str], ...] = (
    ("校园数据建模挑战赛", "Campus Data Modeling Challenge"),
    ("金融科技创新大赛", "FinTech Innovation Competition"),
    ("供应链优化挑战", "Supply Chain Optimization Challenge"),
    ("AI 应用黑客松", "AI Applications Hackathon"),
    ("商业案例分析赛", "Business Case Analysis Competition"),
    ("开源贡献马拉松", "Open Source Contribution Marathon"),
)

_CATEGORY_TAGS = (
    "internship", "workshop", "competition", "research", "career_talk",
    "networking", "scholarship", "volunteer",
)


def _dedupe_tags(*tags: str) -> tuple[str, ...]:
    """去重保序。类型词（internship/workshop）也在随机标签池里——
    撞上就会生成 ('internship','internship') 这种重复标签，
    前端拿标签当 React key 直接报错（2026-07-31 用户报障，根因在此）。"""
    return tuple(dict.fromkeys(tags))



def _provenance(source_id: str, source: str, offset_days: int) -> Provenance:
    retrieved = SEED_TODAY - timedelta(days=offset_days)
    return Provenance(
        source=source,
        source_url=f"https://example.invalid/{source_id.lower()}/{offset_days}",
        retrieved_at=_dt(retrieved, 6),
        published_at=_dt(retrieved - timedelta(days=3), 6),
        parser_version="seed/1.0.0",
        evidence_snippet="合成机会条目（Demo）",
        confidence=0.9,
    )


def _loc(zh: str, en: str) -> LocalizedText:
    """两侧都是我们自己写的合成文案，因此总是能给出 ``LocalizedText``——
    和 ``campus_events.py`` 里"来源可能只给一种语言"的场景不一样。"""
    return LocalizedText(zh_Hans=zh, en=en)


#: 主办方 → 八大类（OrganizerCategory）。名字与类别一处维护，别散在构造点。
_ORGANIZER_CATEGORY: dict[str, OrganizerCategory] = {
    "合成科技公司 Alpha（Demo）": OrganizerCategory.ENTERPRISE,
    "合成金融科技公司（Demo）": OrganizerCategory.ENTERPRISE,
    "合成物流集团（Demo）": OrganizerCategory.ENTERPRISE,
    "合成咨询事务所（Demo）": OrganizerCategory.PARTNER_ENTERPRISE,
    "合成医疗数据公司（Demo）": OrganizerCategory.PARTNER_ENTERPRISE,
    "校友创办的合成初创（Demo）": OrganizerCategory.ALUMNI,
    "HKUST 合成职业发展中心（Demo）": OrganizerCategory.CAREER_CENTER,
    "合成运筹实验室（Demo）": OrganizerCategory.SCHOOL_FACULTY,
    "合成人机交互实验室（Demo）": OrganizerCategory.SCHOOL_FACULTY,
    "合成学生创业社（Demo）": OrganizerCategory.STUDENT_CLUB,
}


def _organizer(rng, *, lab_only: bool = False) -> tuple[str, str]:
    pool = [o for o in ORGANIZERS if not lab_only or "实验室" in o[0]]
    return pick(rng, pool)


def _orgcat(organizer_zh: str) -> OrganizerCategory:
    return _ORGANIZER_CATEGORY[organizer_zh]


def _year_rule(expr: str, tier: str = "organizer_structured") -> EligibilityRule:
    return EligibilityRule(
        kind=EligibilityRuleKind.YEAR_LEVEL, expression=expr, source_tier=tier, mandatory=True
    )


def build_opportunities(
    catalog: Catalog,
    *,
    internships: int,
    events: int,
    labs: int,
    competitions: int,
) -> tuple[list[Opportunity], list[OpportunityMeta]]:
    rng = stream("opportunities")
    course_codes = sorted(catalog.courses)
    out: list[Opportunity] = []
    meta: list[OpportunityMeta] = []

    def add(opp: Opportunity, rule: str, failure_kind: str | None = None) -> None:
        out.append(opp)
        meta.append(OpportunityMeta(opp.opportunity_id, rule, failure_kind))

    # ── 实习 / 工作 ────────────────────────────────────────────────
    for i in range(internships):
        oid = f"OPP-INT-{i + 1:03d}"
        source_id, source = _SOURCES[i % len(_SOURCES)]
        title_zh, title_en = _INTERNSHIP_TITLES[i % len(_INTERNSHIP_TITLES)]
        title = f"{title_zh}（{i + 1}）"
        deadline_offset = pick(rng, [-40, -12, -3, 7, 14, 21, 35, 60, 95, 140])
        deadline = SEED_TODAY + timedelta(days=deadline_offset)

        rules: list[EligibilityRule] = []
        # 年级要求：三分之一限大三及以上 → 大一大二得到 future_eligible 而非被删除
        year_roll = rng.random()
        if year_roll < 0.35:
            rules.append(_year_rule("Year 3 or above"))
            rule_note = "年级门槛 Year3+，低年级应判 future_eligible"
        elif year_roll < 0.5:
            rules.append(
                EligibilityRule(
                    kind=EligibilityRuleKind.YEAR_LEVEL,
                    expression="Penultimate-year students preferred",
                    source_tier="official_page_text",
                    mandatory=False,
                )
            )
            rule_note = "年级表述含糊，应判 needs_confirmation"
        else:
            rule_note = "无年级门槛"

        if rng.random() < 0.4:
            required_course = pick(rng, [c for c in course_codes if c.startswith(("COMP", "ISOM", "IEDA"))])
            rules.append(
                EligibilityRule(
                    kind=EligibilityRuleKind.PREREQUISITE_COURSE,
                    expression=f"Completed {required_course}",
                    source_tier="organizer_structured",
                    mandatory=True,
                )
            )
        if rng.random() < 0.25:
            rules.append(
                EligibilityRule(
                    kind=EligibilityRuleKind.WORK_AUTHORIZATION,
                    expression="Must hold valid HK work authorisation for the internship period",
                    source_tier="organizer_structured",
                    mandatory=True,
                )
            )
        if rng.random() < 0.2:
            rules.append(
                EligibilityRule(
                    kind=EligibilityRuleKind.GPA, expression="CGPA >= 3.0",
                    source_tier="official_page_text", mandatory=True,
                )
            )

        workload = None if rng.random() < 0.12 else float(rng.randrange(120, 400, 20))
        failure_kind = "missing_workload_field" if workload is None else None
        organizer_zh, organizer_en = _organizer(rng)

        add(
            Opportunity(
                opportunity_id=oid,
                type=OpportunityType.INTERNSHIP if i % 5 else OpportunityType.JOB,
                title=title,
                title_localized=_loc(title, f"{title_en} ({i + 1})"),
                organizer=organizer_zh,
                organizer_localized=_loc(organizer_zh, organizer_en),
                organizer_category=_orgcat(organizer_zh),
                category_tags=_dedupe_tags("internship", pick(rng, list(_CATEGORY_TAGS))),
                requirement_categories=tuple(
                    sorted(set(sample(rng, list(RequirementCategory), rng.randrange(1, 4))),
                           key=lambda c: c.value)
                ),
                eligibility_rules=tuple(rules),
                deadline=_dt(deadline),
                starts_at=_dt(deadline + timedelta(days=45), 9),
                ends_at=_dt(deadline + timedelta(days=105), 18),
                workload_hours_total=workload,
                skills=tuple(sorted(set(sample(rng, [
                    "programming", "statistics", "databases", "business_analysis",
                    "machine_learning", "communication", "optimization", "user_research",
                ], rng.randrange(2, 4))))),
                official_url=f"https://example.invalid/opportunity/{oid.lower()}",
                source_id=source_id,
                provenance=_provenance(source_id, source, rng.randrange(1, 60)),
                publication_status=PublicationStatus.PUBLISHED,
                last_verified_at=_dt(SEED_TODAY - timedelta(days=rng.randrange(0, 45)), 6),
            ),
            f"internship #{i + 1}；{rule_note}；截止日偏移 {deadline_offset} 天",
            failure_kind,
        )

    # ── 活动 / 工作坊 ──────────────────────────────────────────────
    for i in range(events):
        oid = f"OPP-EVT-{i + 1:03d}"
        source_id, source = _SOURCES[(i + 2) % len(_SOURCES)]
        event_zh, event_en = _EVENT_TITLES[i % len(_EVENT_TITLES)]
        session_no = i // len(_EVENT_TITLES) + 1
        event_title = f"{event_zh}（第 {session_no} 期）"
        start = SEED_TODAY + timedelta(days=pick(rng, [-20, -6, 3, 9, 16, 24, 40, 65]))
        organizer_zh, organizer_en = _organizer(rng)
        add(
            Opportunity(
                opportunity_id=oid,
                type=pick(rng, [OpportunityType.WORKSHOP, OpportunityType.EVENT,
                                OpportunityType.CLUB_ACTIVITY, OpportunityType.MENTORSHIP]),
                title=event_title,
                title_localized=_loc(event_title, f"{event_en} (Session {session_no})"),
                organizer=organizer_zh,
                organizer_localized=_loc(organizer_zh, organizer_en),
                organizer_category=_orgcat(organizer_zh),
                occurrence_id=f"OCC-EVT-{i + 1:03d}",
                series_id=f"SER-{event_zh}",
                category_tags=_dedupe_tags("workshop", pick(rng, list(_CATEGORY_TAGS))),
                requirement_categories=tuple(
                    sorted(set(sample(rng, list(RequirementCategory), rng.randrange(1, 3))),
                           key=lambda c: c.value)
                ),
                eligibility_rules=(),
                deadline=_dt(start - timedelta(days=2)),
                starts_at=_dt(start, 14),
                ends_at=_dt(start, 17),
                workload_hours_total=float(rng.randrange(2, 12)),
                skills=tuple(sorted(set(sample(rng, [
                    "communication", "user_research", "business_analysis", "programming",
                ], rng.randrange(1, 3))))),
                official_url=f"https://example.invalid/opportunity/{oid.lower()}",
                source_id=source_id,
                provenance=_provenance(source_id, source, rng.randrange(1, 30)),
                publication_status=PublicationStatus.PUBLISHED,
                last_verified_at=_dt(SEED_TODAY - timedelta(days=rng.randrange(0, 20)), 6),
            ),
            f"event #{i + 1}；系列第 {i // len(_EVENT_TITLES) + 1} 届，用于届次分层聚合",
        )

    # ── 实验室 / 研究 ──────────────────────────────────────────────
    for i in range(labs):
        oid = f"OPP-LAB-{i + 1:03d}"
        required_course = pick(rng, [c for c in course_codes if c.startswith(("COMP", "MATH", "IEDA"))])
        lab_zh, lab_en = _LAB_TITLES[i % len(_LAB_TITLES)]
        lab_title = f"{lab_zh}（{i + 1}）"
        organizer_zh, organizer_en = _organizer(rng, lab_only=True)
        add(
            Opportunity(
                opportunity_id=oid,
                type=OpportunityType.RESEARCH_POSITION,
                title=lab_title,
                title_localized=_loc(lab_title, f"{lab_en} ({i + 1})"),
                organizer=organizer_zh,
                organizer_localized=_loc(organizer_zh, organizer_en),
                organizer_category=_orgcat(organizer_zh),
                category_tags=("research",),
                requirement_categories=(RequirementCategory.RESEARCH_EXPERIENCE,
                                        RequirementCategory.TECHNICAL_SKILL),
                eligibility_rules=(
                    _year_rule("Year 2 or above"),
                    EligibilityRule(
                        kind=EligibilityRuleKind.PREREQUISITE_COURSE,
                        expression=f"Completed {required_course}",
                        source_tier="institution_confirmed", mandatory=True,
                    ),
                ),
                deadline=_dt(SEED_TODAY + timedelta(days=pick(rng, [10, 25, 45, 80]))),
                starts_at=_dt(SEED_TODAY + timedelta(days=95), 9),
                workload_hours_total=float(rng.randrange(120, 260, 20)),
                skills=("programming", "optimization", "machine_learning"),
                official_url=f"https://example.invalid/opportunity/{oid.lower()}",
                source_id="SRC-lab-site",
                provenance=_provenance("SRC-lab-site", "lab_website", rng.randrange(5, 90)),
                publication_status=PublicationStatus.PUBLISHED,
                last_verified_at=_dt(SEED_TODAY - timedelta(days=rng.randrange(0, 60)), 6),
            ),
            f"lab #{i + 1}；先修要求引用真实课程 {required_course}",
        )

    # ── 竞赛 / 创业 ────────────────────────────────────────────────
    for i in range(competitions):
        oid = f"OPP-CMP-{i + 1:03d}"
        cmp_zh, cmp_en = _COMPETITION_TITLES[i % len(_COMPETITION_TITLES)]
        cmp_year = 2026 + i // len(_COMPETITION_TITLES)
        cmp_title = f"{cmp_zh}（{cmp_year}）"
        organizer_zh, organizer_en = _organizer(rng)
        add(
            Opportunity(
                opportunity_id=oid,
                type=OpportunityType.COMPETITION,
                title=cmp_title,
                title_localized=_loc(cmp_title, f"{cmp_en} ({cmp_year})"),
                organizer=organizer_zh,
                organizer_localized=_loc(organizer_zh, organizer_en),
                organizer_category=_orgcat(organizer_zh),
                occurrence_id=f"OCC-CMP-{i + 1:03d}",
                series_id=f"SER-{cmp_zh}",
                category_tags=("competition", "networking"),
                requirement_categories=(RequirementCategory.PROJECT_PORTFOLIO,
                                        RequirementCategory.TEAMWORK_EVIDENCE),
                eligibility_rules=(
                    EligibilityRule(
                        kind=EligibilityRuleKind.MEMBERSHIP,
                        expression="Team of 3–5 currently enrolled students",
                        source_tier="organizer_structured", mandatory=True,
                    ),
                ),
                deadline=_dt(SEED_TODAY + timedelta(days=pick(rng, [-9, 12, 30, 55, 88]))),
                starts_at=_dt(SEED_TODAY + timedelta(days=70), 9),
                ends_at=_dt(SEED_TODAY + timedelta(days=72), 18),
                workload_hours_total=float(rng.randrange(20, 80, 5)),
                skills=("programming", "communication", "statistics"),
                official_url=f"https://example.invalid/opportunity/{oid.lower()}",
                source_id="SRC-club-portal",
                provenance=_provenance("SRC-club-portal", "publisher_portal", rng.randrange(1, 40)),
                publication_status=PublicationStatus.PUBLISHED,
                last_verified_at=_dt(SEED_TODAY - timedelta(days=rng.randrange(0, 30)), 6),
            ),
            f"competition #{i + 1}；团队要求 3–5 人",
        )

    return out, meta
