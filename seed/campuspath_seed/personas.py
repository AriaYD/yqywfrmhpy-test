"""学生 Persona、学业记录、经历与证据。

**全部合成。** 没有真实姓名、邮箱、学号或成绩（Spec §11.5、Plan §9）。
契约里的 ``StudentProfile`` 本来就没有姓名字段，展示用的化名单独放在
``demo_display`` 里，且一望即知是化名。

三个深度 Persona 各自承担一组必须被演示到的情形，不是"三个差不多的学生"：

* **A · Explorer**（BSc COMP，大二）—— 目标未定：主目标 + 候选目标（G3），
  缺口多、证据少。**没有设置睡眠窗口**，因此是 B6 的反例样本：
  日历再忙也不得产生 wellbeing 升级。
* **B · Sprinter**（BBA ISOM，大三）—— 目标明确、日历极满、已设睡眠窗口。
  Wellbeing 垂直切片与容量超载重规划都跑在她身上。
* **C · Pivoter**（BEng IEDA，大三）—— 目标信心下滑、正在转向，
  主目标与候选目标的分叉点清晰，用于 Goal Review 与课程取舍。
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, time, timedelta, timezone

from campuspath_contracts.academic import CourseStatus, RecordSource, StudentCourseRecord
from campuspath_contracts.common import DateRange, DevelopmentModeType, LocalizedText
from campuspath_contracts.goals import (
    Goal,
    GoalRole,
    GoalStatus,
    Horizon,
)
from campuspath_contracts.profile import (
    Achievement,
    ConsentRecord,
    ConsentScope,
    DevelopmentMode,
    EnergyProfile,
    EvidenceRecord,
    ExperienceRecord,
    ExperienceType,
    Note,
    ProjectOutcome,
    SkillLevel,
    SkillRecord,
    SkillSourceType,
    StudentConstraint,
    StudentProfile,
)
from campuspath_contracts.common import IntensityMode, VerificationStatus, Visibility

from .catalog import Catalog
from .config import CURRENT_TERM, INSTITUTION, PAST_TERMS, SEED_TODAY, TERMS
from .rng import pick, stream

_TZ = timezone.utc


def _dt(d: date, hour: int = 9) -> datetime:
    return datetime(d.year, d.month, d.day, hour, tzinfo=_TZ)


NOW = _dt(SEED_TODAY)


@dataclasses.dataclass
class PersonaBundle:
    profile: StudentProfile
    display: dict[str, str]
    course_records: list[StudentCourseRecord]
    experiences: list[ExperienceRecord]
    projects: list[ProjectOutcome]
    achievements: list[Achievement]
    skills: list[SkillRecord]
    evidence: list[EvidenceRecord]
    notes: list[Note]
    goals: list[Goal]
    is_deep: bool


def _consents(
    *, calendar: bool, wellbeing: bool, aggregation: bool = True,
    calendar_titles: bool = False,
) -> tuple[ConsentRecord, ...]:
    """``calendar_titles`` 是**二级**日历授权，默认关。

    Demo 需要两种状态都存在：只有一级的学生看到色块，开了二级的学生
    看到标题。三个 Persona 都开着二级，就演示不出这个区别了。
    """
    records = [
        ConsentRecord(scope=ConsentScope.SIS_RECORDS, granted=True, granted_at=NOW,
                      receipt_id="rcpt-sis"),
        ConsentRecord(scope=ConsentScope.LMS_RECORDS, granted=True, granted_at=NOW,
                      receipt_id="rcpt-lms"),
        ConsentRecord(scope=ConsentScope.MEMORY_RETENTION, granted=True, granted_at=NOW,
                      receipt_id="rcpt-mem"),
    ]
    if calendar:
        records.append(
            ConsentRecord(scope=ConsentScope.CALENDAR_FREEBUSY, granted=True, granted_at=NOW,
                          receipt_id="rcpt-cal")
        )
        if calendar_titles:
            records.append(
                ConsentRecord(scope=ConsentScope.CALENDAR_EVENT_TITLES, granted=True,
                              granted_at=NOW, receipt_id="rcpt-cal-titles")
            )
            # 二级授权的 Persona 同时授权**写入**：F06 的"确认后创建计划事件"
            # 需要至少一个学生能走通写路径，而其余学生保持未授权——
            # 403 分支同样要有人能演示（§15.4 规则 8 的两面）。
            records.append(
                ConsentRecord(scope=ConsentScope.CALENDAR_WRITE, granted=True,
                              granted_at=NOW, receipt_id="rcpt-cal-write")
            )
    if wellbeing:
        records.append(
            ConsentRecord(scope=ConsentScope.SELF_REPORTED_WELLBEING, granted=True,
                          granted_at=NOW, receipt_id="rcpt-wb")
        )
    if aggregation:
        records.append(
            ConsentRecord(scope=ConsentScope.ANONYMOUS_AGGREGATION, granted=True,
                          granted_at=NOW, receipt_id="rcpt-agg")
        )
    return tuple(records)


def _course_history(
    catalog: Catalog,
    program_id: str,
    student_id: str,
    terms: tuple[str, ...],
    per_term: int,
    *,
    include_current: bool = True,
) -> list[StudentCourseRecord]:
    """按培养方案顺序把课排进过去的学期。

    不随机挑课——挑课要满足先修顺序，否则会造出"没修 COMP 2011 就修了 COMP 2012"
    这种自相矛盾的数据，而 Spec §11.5 明确禁止"互相矛盾却无法解释的数据"。
    """
    rng = stream(f"records.{student_id}")
    ordered: list[str] = []
    for req in catalog.requirements:
        if req.program_id != program_id:
            continue
        ordered.extend(code for code in req.alternatives if code in catalog.courses)
    # 按课程层级排序即近似满足先修顺序（HKUST 编码规则：首位数字即层级）
    ordered = sorted(dict.fromkeys(ordered), key=lambda c: (int(c.split()[1][0]), c))

    records: list[StudentCourseRecord] = []
    cursor = 0
    for term in terms:
        for _ in range(per_term):
            if cursor >= len(ordered):
                break
            code = ordered[cursor]
            cursor += 1
            records.append(
                StudentCourseRecord(
                    record_id=f"{student_id}-{code.replace(' ', '')}-{term}",
                    student_id=student_id,
                    course_id=code,
                    term=term,
                    status=CourseStatus.COMPLETED,
                    credits=catalog.courses[code].credits,
                    grade_scope="letter",
                    grade=pick(rng, ["A", "A-", "B+", "B", "B-", "C+"]),
                    source=RecordSource.SIS,
                    updated_at=_dt(TERMS[term][1]),
                )
            )
    if include_current:
        for _ in range(4):
            if cursor >= len(ordered):
                break
            code = ordered[cursor]
            cursor += 1
            records.append(
                StudentCourseRecord(
                    record_id=f"{student_id}-{code.replace(' ', '')}-{CURRENT_TERM}",
                    student_id=student_id,
                    course_id=code,
                    term=CURRENT_TERM,
                    status=CourseStatus.ENROLLED,
                    credits=catalog.courses[code].credits,
                    grade_scope="not_released",
                    grade=None,
                    source=RecordSource.SIS,
                    updated_at=NOW,
                )
            )
    return records


# --------------------------------------------------------------------------
# Persona A · Explorer
# --------------------------------------------------------------------------


def _persona_a(catalog: Catalog) -> PersonaBundle:
    sid = "STU-A"
    profile = StudentProfile(
        student_id=sid,
        institution=INSTITUTION,
        program_id="BSC-COMP",
        level="undergraduate",
        year=2,
        expected_graduation=date(2029, 6, 30),
        development_modes=(
            DevelopmentMode(mode=DevelopmentModeType.EXPLORATION, weight=0.5, confidence=0.4),
            DevelopmentMode(mode=DevelopmentModeType.EMPLOYMENT, weight=0.4, confidence=0.35),
            DevelopmentMode(mode=DevelopmentModeType.PERSONAL_INTEREST, weight=0.1, confidence=0.6),
        ),
        interests=("web development", "game design", "generative ai"),
        constraints=(
            StudentConstraint(kind="commute", description="住宿舍，通勤 10 分钟", hard=False),
        ),
        energy_profile=EnergyProfile(
            weekly_discretionary_hours=14.0,
            preferred_intensity=IntensityMode.BALANCED,
            max_parallel_commitments=2,
            social_preference="small_group",
            min_buffer_ratio=0.25,
            # 刻意不设睡眠窗口与恢复偏好：B6 的反例前提
            sleep_window_start=None,
            sleep_window_end=None,
            recovery_preference_defined=False,
        ),
        consent=_consents(calendar=True, wellbeing=False),
        version=3,
        updated_at=NOW,
    )
    evidence = [
        # R4-C：source 会被档案页当条目标题显示——写成人能读的名字，
        # 公开课链接指向真实课程公开页（公开资源，非个人数据），证书本体仍合成
        EvidenceRecord(
            evidence_id="EV-A-1", student_id=sid, evidence_type="link",
            source="Coursera · Introduction to Generative AI（Google Cloud）",
            uri="https://www.coursera.org/learn/introduction-to-generative-ai",
            obtained_at=date(2026, 5, 20),
            verification_status=VerificationStatus.SELF_REPORTED,
        ),
        EvidenceRecord(
            evidence_id="EV-A-2", student_id=sid, evidence_type="certificate",
            source="校内黑客松参赛证书（Synthetic）",
            object_ref=f"vault/{sid}/hackathon-cert.pdf",
            issuer="HKUST Student Union Hackathon", obtained_at=date(2026, 3, 15),
            verification_status=VerificationStatus.SELF_REPORTED,
        ),
    ]
    projects = [
        ProjectOutcome(
            project_id="PRJ-A-1", student_id=sid, project_type="hackathon",
            title="校内黑客松：课表冲突可视化工具",
            contribution="负责前端与数据清洗，24 小时内完成可用原型",
            artifacts=("https://example.invalid/a/repo",),
            measurable_result="现场演示获参与奖",
            evidence_ids=("EV-A-2",),
        ),
    ]
    skills = [
        SkillRecord(skill_id="programming", student_id=sid, level=SkillLevel.PRACTICING,
                    source_type=SkillSourceType.COURSE, evidence_ids=(),
                    last_used_at=date(2026, 5, 1), confidence=0.7, student_confirmed=True),
        SkillRecord(skill_id="user_research", student_id=sid, level=SkillLevel.AWARE,
                    source_type=SkillSourceType.AGENT_INFERRED, evidence_ids=("EV-A-2",),
                    last_used_at=date(2026, 3, 15), confidence=0.35, student_confirmed=False),
    ]
    goals = [
        Goal(goal_id="GOAL-A-P", student_id=sid, role=GoalRole.PRIMARY,
             development_mode=DevelopmentModeType.EMPLOYMENT, target_type="role",
             target_name="Software Engineer (Product)", horizon=Horizon.LONG_TERM,
             confidence=0.45, status=GoalStatus.ACTIVE,
             alternatives=("Frontend Engineer",), created_at=_dt(date(2026, 2, 10))),
        Goal(goal_id="GOAL-A-C", student_id=sid, role=GoalRole.CANDIDATE,
             development_mode=DevelopmentModeType.EMPLOYMENT, target_type="role",
             target_name="Data Analyst", horizon=Horizon.LONG_TERM, confidence=0.3,
             status=GoalStatus.CANDIDATE, created_at=_dt(date(2026, 4, 2))),
    ]
    return PersonaBundle(
        profile=profile,
        display={"zh-Hans": "Persona A · 探索者（合成）", "en": "Persona A · Explorer (synthetic)"},
        course_records=_course_history(catalog, "BSC-COMP", sid, PAST_TERMS[:2], 4),
        experiences=[
            ExperienceRecord(
                experience_id="EXP-A-1", student_id=sid, type=ExperienceType.CLUB,
                organization="HKUST Computer Society（合成）", role="干事",
                period=DateRange(start=date(2025, 9, 1), end=None),
                responsibilities=("组织每月技术分享",),
                outcomes=("累计到场约 60 人",), skills=("communication",),
                evidence_ids=(), note_ids=("NOTE-A-1",),
                verification_status=VerificationStatus.SELF_REPORTED,
            ),
        ],
        projects=projects,
        achievements=[],
        skills=skills,
        evidence=evidence,
        notes=[
            Note(note_id="NOTE-A-1", student_id=sid, author="student",
                 text="社团活动很有意思但和求职关系不大，明年要不要继续待考虑。",
                 linked_entities=("EXP-A-1",), visibility=Visibility.PRIVATE,
                 created_at=_dt(date(2026, 6, 1))),
        ],
        goals=goals,
        is_deep=True,
    )


# --------------------------------------------------------------------------
# Persona B · Sprinter
# --------------------------------------------------------------------------


def _persona_b(catalog: Catalog) -> PersonaBundle:
    sid = "STU-B"
    profile = StudentProfile(
        student_id=sid,
        institution=INSTITUTION,
        program_id="BBA-ISOM",
        level="undergraduate",
        year=3,
        expected_graduation=date(2028, 6, 30),
        development_modes=(
            DevelopmentMode(mode=DevelopmentModeType.EMPLOYMENT, weight=0.85, confidence=0.8),
            DevelopmentMode(mode=DevelopmentModeType.PERSONAL_INTEREST, weight=0.15, confidence=0.5),
        ),
        interests=("product analytics", "fintech", "consulting"),
        constraints=(
            StudentConstraint(kind="caregiving", description="每周六需回家照顾家人", hard=True),
            StudentConstraint(kind="financial", description="需保留兼职时段", hard=False),
        ),
        energy_profile=EnergyProfile(
            weekly_discretionary_hours=9.0,
            preferred_intensity=IntensityMode.SPRINT,
            max_parallel_commitments=3,
            social_preference="mixed",
            min_buffer_ratio=0.15,
            sleep_window_start="00:30",   # 显式设置 → wellbeing 信号才有前提
            sleep_window_end="07:30",
            recovery_preference_defined=True,
        ),
        consent=_consents(calendar=True, wellbeing=True, calendar_titles=True),
        version=7,
        updated_at=NOW,
    )
    evidence = [
        EvidenceRecord(
            evidence_id="EV-B-1", student_id=sid, evidence_type="reference",
            source="employer", object_ref=f"vault/{sid}/internship-reference.pdf",
            issuer="合成金融科技公司（Demo）", obtained_at=date(2026, 8, 20),
            verification_status=VerificationStatus.SOURCE_IMPORTED,
        ),
        EvidenceRecord(
            evidence_id="EV-B-2", student_id=sid, evidence_type="link",
            source="Coursera · SQL for Data Science（UC Davis）",
            uri="https://www.coursera.org/learn/sql-for-data-science",
            obtained_at=date(2026, 8, 12),
            verification_status=VerificationStatus.SELF_REPORTED,
        ),
        EvidenceRecord(
            evidence_id="EV-B-3", student_id=sid, evidence_type="certificate",
            source="issuer", object_ref=f"vault/{sid}/sql-cert.pdf",
            issuer="合成认证机构（Demo）", obtained_at=date(2025, 7, 1),
            expires_at=date(2026, 7, 1),   # 已过期：失败样本素材
            verification_status=VerificationStatus.EXPIRED,
        ),
    ]
    return PersonaBundle(
        profile=profile,
        display={"zh-Hans": "Persona B · 冲刺者（合成）", "en": "Persona B · Sprinter (synthetic)"},
        course_records=_course_history(catalog, "BBA-ISOM", sid, PAST_TERMS, 4),
        experiences=[
            ExperienceRecord(
                experience_id="EXP-B-1", student_id=sid, type=ExperienceType.INTERNSHIP,
                organization="合成金融科技公司（Demo）", role="Data Analyst Intern",
                period=DateRange(start=date(2026, 6, 8), end=date(2026, 8, 15)),
                responsibilities=("搭建留存分析看板", "整理埋点口径"),
                outcomes=("看板被团队每周使用",),
                skills=("statistics", "business_analysis", "databases"),
                evidence_ids=("EV-B-1", "EV-B-2"),
                verification_status=VerificationStatus.SOURCE_IMPORTED,
            ),
            ExperienceRecord(
                experience_id="EXP-B-2", student_id=sid, type=ExperienceType.PART_TIME,
                organization="校内数据中心（合成）", role="学生助理",
                period=DateRange(start=date(2025, 10, 1), end=None),
                responsibilities=("每周 8 小时数据整理",),
                outcomes=(), skills=("databases",),
                verification_status=VerificationStatus.SELF_REPORTED,
            ),
        ],
        projects=[
            ProjectOutcome(
                project_id="PRJ-B-1", student_id=sid, project_type="course",
                title="课程项目：校园二手交易平台的定价分析",
                contribution="负责数据建模与结论撰写",
                artifacts=("https://example.invalid/b/report",),
                measurable_result="课程评分 A-",
                evidence_ids=("EV-B-2",),
            ),
        ],
        achievements=[
            Achievement(
                achievement_id="ACH-B-1", student_id=sid, achievement_type="scholarship",
                issuer="合成院系奖学金（Demo）", level="department", result="获得",
                issued_at=date(2025, 11, 1),
                verification_status=VerificationStatus.INSTITUTION_VERIFIED,
                evidence_ids=(),
            ),
        ],
        skills=[
            SkillRecord(skill_id="statistics", student_id=sid, level=SkillLevel.PROFICIENT,
                        source_type=SkillSourceType.EXPERIENCE, evidence_ids=("EV-B-1",),
                        last_used_at=date(2026, 8, 15), confidence=0.85, student_confirmed=True),
            SkillRecord(skill_id="databases", student_id=sid, level=SkillLevel.PROFICIENT,
                        source_type=SkillSourceType.CERTIFICATE, evidence_ids=("EV-B-3",),
                        last_used_at=date(2026, 8, 15), confidence=0.6, student_confirmed=True),
            SkillRecord(skill_id="business_analysis", student_id=sid, level=SkillLevel.PRACTICING,
                        source_type=SkillSourceType.EXPERIENCE, evidence_ids=("EV-B-1",),
                        last_used_at=date(2026, 8, 15), confidence=0.7, student_confirmed=True),
        ],
        evidence=evidence,
        notes=[
            Note(note_id="NOTE-B-1", student_id=sid, author="student",
                 text="实习最后两周太赶了，回来不想再同时接三件事。",
                 linked_entities=("EXP-B-1",), visibility=Visibility.PRIVATE,
                 created_at=_dt(date(2026, 8, 18))),
        ],
        goals=[
            Goal(goal_id="GOAL-B-P", student_id=sid, role=GoalRole.PRIMARY,
                 development_mode=DevelopmentModeType.EMPLOYMENT, target_type="role",
                 target_name="Product / Business Analyst", horizon=Horizon.THIS_TERM,
                 confidence=0.75, status=GoalStatus.ACTIVE,
                 alternatives=("Data Analyst",), created_at=_dt(date(2025, 9, 20)),
                 last_reviewed=_dt(date(2026, 8, 25))),
        ],
        is_deep=True,
    )


# --------------------------------------------------------------------------
# Persona C · Pivoter
# --------------------------------------------------------------------------


def _persona_c(catalog: Catalog) -> PersonaBundle:
    sid = "STU-C"
    profile = StudentProfile(
        student_id=sid,
        institution=INSTITUTION,
        program_id="BENG-IEDA",
        level="undergraduate",
        year=3,
        expected_graduation=date(2028, 6, 30),
        development_modes=(
            DevelopmentMode(mode=DevelopmentModeType.EMPLOYMENT, weight=0.6, confidence=0.55),
            DevelopmentMode(mode=DevelopmentModeType.ACADEMIA, weight=0.3, confidence=0.4),
            DevelopmentMode(mode=DevelopmentModeType.EXPLORATION, weight=0.1, confidence=0.5),
        ),
        interests=("optimization", "machine learning", "operations research"),
        constraints=(
            StudentConstraint(kind="visa", description="非本地生，需留意实习工作授权",
                              hard=True),
        ),
        energy_profile=EnergyProfile(
            weekly_discretionary_hours=12.0,
            preferred_intensity=IntensityMode.BALANCED,
            max_parallel_commitments=2,
            social_preference="solo",
            min_buffer_ratio=0.3,
            sleep_window_start="01:00",
            sleep_window_end="08:00",
            recovery_preference_defined=True,
        ),
        consent=_consents(calendar=True, wellbeing=False),
        version=5,
        updated_at=NOW,
    )
    return PersonaBundle(
        profile=profile,
        display={"zh-Hans": "Persona C · 转向者（合成）", "en": "Persona C · Pivoter (synthetic)"},
        course_records=_course_history(catalog, "BENG-IEDA", sid, PAST_TERMS, 4),
        experiences=[
            ExperienceRecord(
                experience_id="EXP-C-1", student_id=sid, type=ExperienceType.RESEARCH,
                organization="合成运筹实验室（Demo）", role="本科研究助理",
                period=DateRange(start=date(2026, 1, 15), end=date(2026, 6, 30)),
                responsibilities=("排班优化模型实现", "实验结果整理"),
                outcomes=("产出一份内部技术报告",),
                skills=("optimization", "programming"),
                evidence_ids=("EV-C-1",), note_ids=("NOTE-C-1",),
                verification_status=VerificationStatus.INSTITUTION_VERIFIED,
            ),
        ],
        projects=[
            ProjectOutcome(
                project_id="PRJ-C-1", student_id=sid, project_type="research",
                title="排班优化模型在合成校园场景下的对比实验",
                contribution="独立实现两种启发式算法并做对比",
                artifacts=("https://example.invalid/c/report",),
                measurable_result="较基线缩短求解时间约 30%",
                evidence_ids=("EV-C-1",),
            ),
        ],
        achievements=[
            Achievement(
                achievement_id="ACH-C-1", student_id=sid, achievement_type="competition",
                issuer="合成数据建模竞赛（Demo）", level="regional", result="二等奖",
                issued_at=date(2025, 12, 10),
                verification_status=VerificationStatus.SOURCE_IMPORTED,
                evidence_ids=("EV-C-2",),
            ),
        ],
        skills=[
            SkillRecord(skill_id="optimization", student_id=sid, level=SkillLevel.ADVANCED,
                        source_type=SkillSourceType.EXPERIENCE, evidence_ids=("EV-C-1",),
                        last_used_at=date(2026, 6, 30), confidence=0.9, student_confirmed=True),
            SkillRecord(skill_id="programming", student_id=sid, level=SkillLevel.PROFICIENT,
                        source_type=SkillSourceType.PROJECT, evidence_ids=("EV-C-1",),
                        last_used_at=date(2026, 6, 30), confidence=0.75, student_confirmed=True),
            SkillRecord(skill_id="machine_learning", student_id=sid, level=SkillLevel.AWARE,
                        source_type=SkillSourceType.SELF_ASSESSED, evidence_ids=(),
                        last_used_at=None, confidence=0.3, student_confirmed=True),
        ],
        evidence=[
            EvidenceRecord(
                evidence_id="EV-C-1", student_id=sid, evidence_type="artifact",
                source="lab", object_ref=f"vault/{sid}/tech-report.pdf",
                issuer="合成运筹实验室（Demo）", obtained_at=date(2026, 6, 30),
                verification_status=VerificationStatus.INSTITUTION_VERIFIED,
            ),
            EvidenceRecord(
                evidence_id="EV-C-2", student_id=sid, evidence_type="award_letter",
                source="organizer", uri="https://example.invalid/c/award",
                issuer="合成数据建模竞赛（Demo）", obtained_at=date(2025, 12, 10),
                verification_status=VerificationStatus.SOURCE_IMPORTED,
            ),
        ],
        notes=[
            Note(note_id="NOTE-C-1", student_id=sid, author="student",
                 text="做优化很顺，但招聘看的都是机器学习。要不要换方向，还没想好。",
                 linked_entities=("EXP-C-1",), visibility=Visibility.PRIVATE,
                 created_at=_dt(date(2026, 7, 5))),
        ],
        goals=[
            Goal(goal_id="GOAL-C-P", student_id=sid, role=GoalRole.PRIMARY,
                 development_mode=DevelopmentModeType.EMPLOYMENT, target_type="role",
                 target_name="Supply Chain Analyst", horizon=Horizon.LONG_TERM,
                 confidence=0.35, status=GoalStatus.ACTIVE,
                 created_at=_dt(date(2025, 3, 1)), last_reviewed=_dt(date(2026, 7, 10))),
            Goal(goal_id="GOAL-C-C", student_id=sid, role=GoalRole.CANDIDATE,
                 development_mode=DevelopmentModeType.ACADEMIA, target_type="role",
                 target_name="Data Scientist", horizon=Horizon.LONG_TERM, confidence=0.55,
                 status=GoalStatus.CANDIDATE, created_at=_dt(date(2026, 7, 5))),
        ],
        is_deep=True,
    )


# --------------------------------------------------------------------------
# 精简学生：只造到"足够支撑分组聚合与失败样本"的程度
# --------------------------------------------------------------------------

_SLIM_SPECS: tuple[tuple[str, str, int, DevelopmentModeType], ...] = (
    ("STU-D", "BSC-COMP", 1, DevelopmentModeType.EXPLORATION),
    ("STU-E", "BSC-COMP", 3, DevelopmentModeType.EMPLOYMENT),
    ("STU-F", "BSC-COMP", 4, DevelopmentModeType.ACADEMIA),
    ("STU-G", "BBA-ISOM", 2, DevelopmentModeType.EMPLOYMENT),
    ("STU-H", "BBA-ISOM", 4, DevelopmentModeType.ENTREPRENEURSHIP),
    ("STU-I", "BENG-IEDA", 1, DevelopmentModeType.EXPLORATION),
    ("STU-J", "BENG-IEDA", 2, DevelopmentModeType.EMPLOYMENT),
    ("STU-K", "BENG-IEDA", 4, DevelopmentModeType.EMPLOYMENT),
    ("STU-L", "BBA-ISOM", 3, DevelopmentModeType.PERSONAL_INTEREST),
)


def _slim(catalog: Catalog, sid: str, program_id: str, year: int,
          mode: DevelopmentModeType) -> PersonaBundle:
    rng = stream(f"slim.{sid}")
    terms = PAST_TERMS[: max(0, min(len(PAST_TERMS), (year - 1) * 2))]
    profile = StudentProfile(
        student_id=sid,
        institution=INSTITUTION,
        program_id=program_id,
        level="undergraduate",
        year=year,
        expected_graduation=date(2026 + (5 - year), 6, 30),
        development_modes=(DevelopmentMode(mode=mode, weight=0.8, confidence=0.5),),
        interests=(),
        constraints=(),
        energy_profile=EnergyProfile(
            weekly_discretionary_hours=float(rng.randrange(8, 18)),
            preferred_intensity=pick(rng, list(IntensityMode)),
            min_buffer_ratio=0.2,
        ),
        consent=_consents(calendar=False, wellbeing=False),
        version=1,
        updated_at=NOW,
    )
    return PersonaBundle(
        profile=profile,
        display={"zh-Hans": f"{sid}（合成·精简）", "en": f"{sid} (synthetic, slim)"},
        course_records=_course_history(catalog, program_id, sid, terms, 4),
        experiences=[], projects=[], achievements=[], skills=[], evidence=[], notes=[],
        goals=[
            Goal(goal_id=f"GOAL-{sid}", student_id=sid, role=GoalRole.PRIMARY,
                 # 探索中是一等状态，不是"还没填"——所以 mode 也明写出来
                 development_mode=DevelopmentModeType.EXPLORATION,
                 target_type="exploration", target_name="待澄清", horizon=Horizon.LONG_TERM,
                 confidence=0.3, status=GoalStatus.ACTIVE, created_at=NOW),
        ],
        is_deep=False,
    )


def build_personas(catalog: Catalog, deep: int, slim: int) -> list[PersonaBundle]:
    deep_builders = (_persona_a, _persona_b, _persona_c)
    bundles = [builder(catalog) for builder in deep_builders[:deep]]
    for sid, program_id, year, mode in _SLIM_SPECS[:slim]:
        bundles.append(_slim(catalog, sid, program_id, year, mode))
    return bundles
