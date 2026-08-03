"""CampusPath API：实现 WP1 冻结的 `/v1` 契约。

**契约是合同，这里是履约方。** 路由表在 ``campuspath_contracts.openapi``，
本模块必须逐条实现。

未实现的端点**由契约自动补成 501**，而不是靠人记得列一份 pending 名单：
覆盖率因此是构造性的——契约里有的，这里一定有路由。501 的响应体说明它在等谁。

为什么不返回空数组：前端会把 `[]` 当成"这个学生没有匹配结果"，
而事实是这条路还没接。空数组是一种会被信以为真的谎。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from campuspath_contracts.aggregation import (
    EventQualityAggregate,
    MetricTuple,
    ResourceCoverageAggregate,
)
from campuspath_contracts.academic import (
    CourseRecommendation,
    ProgramCurriculum,
    AcademicState,
    AnnotatedCourseCandidate,
    CourseCatalogItem,
    CourseStatus,
    DegreeProgress,
    DegreeRequirement,
    DegreeRequirementProgress,
    PrerequisiteStatus,
    StudentCourseRecord,
)
from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityBlockPatch,
    AvailabilityType,
    BlockSource,
    CalendarDetailLevel,
    CapacitySnapshot,
    RoutineRequest,
    RoutineWindow,
    ScheduleConflict,
)
from campuspath_contracts.goals import (
    DecompositionResearchJob,
    GoalDecomposition,
    DynamicGapMap,
    Gap,
    GapLevel,
    Goal,
    GoalRole,
    GoalSet,
    GrowthTrajectory,
    VgaMonthPoint,
    VgaSummary,
    GrowthTrajectoryPoint,
    RequirementCategory,
    SharedGap,
)
from campuspath_contracts.common import (
    CONTRACTS_VERSION,
    VerificationStatus,
    ActorRole,
    AgentId,
    DateRange,
    DevelopmentModeType,
    Locale,
    LocalizedText,
    SourceRef,
    TimeRange,
)
from campuspath_contracts.messages import render as render_message
from campuspath_contracts.openapi import API_ENDPOINTS
from campuspath_contracts.opportunity import (
    EligibilityExplanation,
    EligibilityStateName,
    MatchResult,
    Opportunity,
    OpportunityDraft,
    OrganizerCategory,
    PublicationStatus,
    SourceIngestRequest,
)
from campuspath_contracts.agents import (
    AgentRuntimeCommand,
    AgentRuntimeStatus,
    IntentId,
    WorkflowPlan,
)
from campuspath_contracts.reflection import (
    Reflection,
    ReflectionResult,
    StudentEventFeedbackForm,
)
from campuspath_contracts.pathway import PathwayVersion, enforce_validation_binding
from campuspath_contracts.memory import (
    DeletionReceipt,
    MemoryCorrection,
    MemoryEntry,
    MemoryForgetReceipt,
    MemoryOrigin,
    MemoryType,
    MemoryRecallQuery,
    MemoryRecallResult,
    StudentDataExport,
)
from campuspath_contracts.advising import (
    Advisor,
    AdvisorBooking,
    AdvisorBookingStatus,
    AdvisorRegistration,
    AdvisorSlot,
    AdvisorSummary,
    AdvisorUpdate,
    SlotAvailabilityUpdate,
)
from campuspath_contracts.calendar import CalendarAction, ScheduleProposal
from campuspath_contracts.pathway import (
    ActionEvent,
    ActionType,
    AffectedScope,
    PlanItem,
    PlanItemKind,
    PlanItemStatus,
    ReplanRequest,
)
from campuspath_contracts.profile import (
    ConsentRecord,
    EducationEntry,
    LanguageSkill,
    ProfileEntry,
    ProfileExtras,
    ContactPerson,
    ImportantContacts,
    ProfileSelfEdit,
    ConsentScope,
    ConsentUpdateRequest,
    ResumeUpload,
    EvidenceRecord,
    ExperienceRecord,
    Note,
    ProfileChangeEvent,
    ProfileUpdateProposal,
    ProposalStatus,
    StudentProfile,
)
from campuspath_contracts.publishing import (
    OpportunityAdminEdit,
    ModerationDecision,
    PublicationSubmission,
    assert_transition_allowed,
)
from campuspath_contracts.wellbeing import (
    CounselingBooking,
    CounselingHours,
    CounselingSlot,
    CounselingWindow,
    EmergencyAccessResult,
    WellbeingAssessmentRequest,
    WellbeingAssessmentResult,
    WellbeingEscalation,
    OutreachConsent,
    WellbeingOutreachRequest,
)
from campuspath_contracts.packs import ContextPackEvaluation
from campuspath_contracts.publishing import (
    CheckinRequest,
    CheckinResult,
    EventCheckinInfo,
    OccurrenceQualitySummary,
    QualityReportJob,
    RegisteredSource,
    SourceHealth,
    SourceKind,
    SourcesSweepJob,
)
from campuspath_contracts.reflection import EventQualityFeedback
from campuspath_contracts.validation import (
    ConstraintValidation,
    InMemoryValidationRegistry,
    UnbackedOutputError,
)
from campuspath_contracts.wellbeing import (
    WellbeingAssessmentRequest,
    WellbeingAssessmentResult,
    WellbeingEscalation,
    WellbeingCapacitySignal,
    WellbeingReminderEvent,
    WellbeingSignalType,
)
import logging
import os
import re

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from . import rbac


def _template_regex(template: str) -> re.Pattern[str]:
    """把 ``/v1/students/{student_id}/profile`` 编成匹配实际路径的正则。

    不走 ``app.routes`` 反查：新版 FastAPI 把 ``include_router`` 的结果包成
    ``_IncludedRouter``，子路由不在 ``app.routes`` 里。依赖框架内部结构的代码
    会在升级时静默失效——而这里失效意味着 **RBAC 中间件全程放行**。
    """
    pattern = re.sub(r"\{[^}]+\}", r"[^/]+", template)
    return re.compile(rf"^{pattern}$")

SYNTHETIC_NOTICE = "Synthetic / Demo Data"

#: 四态资格的人话标签。之前两侧都填枚举值 ``ineligible_current_cycle``，
#: 中英各"翻译"了一遍同一个机器标识符——那不是双语，是把 id 印了两次。
_STATE_LABEL = {
    EligibilityStateName.ELIGIBLE_NOW: ("现在可以报名", "Open to you now"),
    EligibilityStateName.FUTURE_ELIGIBLE: ("现在不行，将来可以", "Not yet, but reachable"),
    EligibilityStateName.NEEDS_CONFIRMATION: ("需要确认", "Needs confirmation"),
    EligibilityStateName.INELIGIBLE_CURRENT_CYCLE: (
        "本轮不可报名", "Not open this cycle"
    ),
}


#: 一键巡检的逐源礼貌间隔（秒）；测试置 0
_SWEEP_DELAY = 0.2


def _autodetect_model():
    """环境允许就接真模型，否则返回 None（依赖它的端点照旧 503）。

    **不接受"差不多能跑"**：``VertexModel`` 的构造函数会调
    ``assert_vertex_only()``，环境里但凡有一个 API key、或者
    ``GOOGLE_GENAI_USE_VERTEXAI`` 没开，它就抛异常——那种情况下
    宁可整个端点 503，也不能让请求默默走上 AI Studio 那条计费路径。
    构造失败在这里被吞掉是**故意**的：它意味着"没有可用后端"，
    不是"出错了"，两者对调用方的含义不同。
    """
    try:
        from campuspath_agents.model import VertexModel

        return VertexModel()
    except Exception:
        return None


class Deps:
    """服务实例与数据。生产环境换 Firestore 后端，接口不变。

    ``model`` 为 None 表示**没有可用的模型后端**（例如没配 ADC）。
    依赖模型的端点此时返回 **503**，不是 501——两者含义不同：
    501 是"还没做"，503 是"做了，但它依赖的东西现在不可用"。
    把两者混为一谈，会让"还剩多少没做"这个数字失去意义。
    """

    def __init__(self, profile_name: str = "full", model: object | None = None) -> None:
        self.model = model if model is not None else _autodetect_model()
        from campuspath_seed.build import build_seed

        bundle = build_seed(profile_name)
        self.validations = InMemoryValidationRegistry()
        self.students = {s["student_id"]: StudentProfile(**s) for s in bundle["students"]}
        self.snapshots: dict[str, list[CapacitySnapshot]] = {}
        for row in bundle["capacity_snapshots"]:
            snapshot = CapacitySnapshot(**row)
            self.snapshots.setdefault(snapshot.student_id, []).append(snapshot)
        # 截止日期已过的，状态推进到 **expired**，不再留在 published 里。
        #
        # 评测 T7 实测出来的：31 条早已截止的机会仍以 published 身份出现在
        # 资讯广场，学生看到的是一份 14.9% 已死的目录。Spec 允许"过期但
        # 可作未来参考"，所以**不删**——只是它不该再混在"可以报名"里。
        # 状态机本来就有 EXPIRED，缺的只是有人推进它。
        as_of = date.fromisoformat(bundle["manifest"]["as_of"])
        self.opportunities = []
        self.expired_opportunities = []
        for row in bundle["opportunities"]:
            if row["publication_status"] != PublicationStatus.PUBLISHED.value:
                continue
            opportunity = Opportunity(**row)
            if opportunity.deadline is not None and opportunity.deadline.date() < as_of:
                self.expired_opportunities.append(opportunity.model_copy(
                    update={"publication_status": PublicationStatus.EXPIRED}
                ))
            else:
                self.opportunities.append(opportunity)
        self.records: dict[str, list[StudentCourseRecord]] = {}
        for row in bundle["student_course_records"]:
            record = StudentCourseRecord(**row)
            self.records.setdefault(record.student_id, []).append(record)
        self.catalog = {c["course_id"]: CourseCatalogItem(**c) for c in bundle["courses"]}
        # course_id → 未来最早可完成日期。资格判定要靠它区分
        # 「补修就能达成」与「那门课再也不开」（docs/T1-T3-adjudication.md 原因二）。
        from campuspath_seed.config import FUTURE_TERMS, TERMS

        self.future_offerings: dict[str, date] = {}
        for row in bundle["course_offerings"]:
            if row["term"] not in FUTURE_TERMS:
                continue
            term_end = TERMS[row["term"]][1]
            course = row["course_id"]
            if course not in self.future_offerings or term_end < self.future_offerings[course]:
                self.future_offerings[course] = term_end
        self.requirements: dict[str, list[DegreeRequirement]] = {}
        for row in bundle["degree_requirements"]:
            requirement = DegreeRequirement(**row)
            self.requirements.setdefault(requirement.program_id, []).append(requirement)
        self.goals: dict[str, list[Goal]] = {}
        for row in bundle["goals"]:
            goal = Goal(**row)
            self.goals.setdefault(goal.student_id, []).append(goal)
        self.current_term = bundle["manifest"]["current_term"]
        self.today = date.fromisoformat(bundle["manifest"]["as_of"])

        # 确定性服务：一个学生一个 store，一份发布服务
        from campuspath_publishing.workflow import PublishingService
        from campuspath_state.store import InMemoryMemoryProvider, StudentStateStore

        self.stores = {
            sid: StudentStateStore(profile=profile)
            for sid, profile in self.students.items()
        }
        self.memory = InMemoryMemoryProvider()
        for row in bundle["memory_entries"]:
            self.memory.write(MemoryEntry(**row))
        self.publishing = PublishingService()
        for row in bundle["publisher_grants"]:
            from campuspath_contracts.publishing import PublisherRoleGrant

            self.publishing.register(PublisherRoleGrant(**row))
        #: 学生反思（Private Vault 的进程内形态）。原文永不出域（B4）。
        self.reflections: dict[str, list] = {}
        #: A4 提交的机会草稿。进不了 Catalog，等待人工审核（§8.9.1）。
        self.opportunity_drafts: list = []
        #: 官方信息源注册表（C，2026-08-02）——console 源列表、变更检测、
        #: 直发白名单的单一事实来源。运行期状态（哈希/时间戳）就地更新。
        from campuspath_connector.registry import load_registry

        self.registered_sources: dict[str, RegisteredSource] = {
            s.source_id: s for s in load_registry()
        }
        #: 每源最近一次抓取结果（"ok"/"unreachable"/"unknown"），供健康度呈现。
        self.source_fetch_status: dict[str, str] = {}
        #: 抓取探针，测试可替换为桩（不发真实请求）。
        from campuspath_connector import fetcher as _fetcher

        self.probe_fn = _fetcher.probe
        #: 活动签到名册（D 批，2026-08-02）：运营域，只出计数不出名单。
        self.attendance: dict[str, set[str]] = {}
        #: 签到 HMAC 密钥（审查 #1）：环境注入；未配置时每进程随机。
        import secrets as _secrets

        self.checkin_secret = os.environ.get("CHECKIN_SECRET") or _secrets.token_hex(16)
        #: 后台任务与共享字典的粗粒度锁（审查 #7：check-then-act 竞态）。
        import threading as _threading

        self.jobs_lock = _threading.Lock()
        #: Demo 运行时启停任务与状态缓存（F1）。
        self.runtime_job = None
        self.runtime_status_cache: tuple = (
            datetime.min.replace(tzinfo=timezone.utc), None)
        #: 运行时控制脚本路径；"auto" = 按仓库布局解析。测试与无脚本环境
        #: 置 None 以走 unknown 分支（探测不到 ≠ stopped，2026-08-02 审计）。
        self.runtime_script_path: object = "auto"
        #: 周期报告任务（仅 career_center_admin 端点可见）
        self.report_jobs: dict[str, QualityReportJob] = {}
        #: 一键巡检任务（2026-08-02 用户需求 C）：同一时间至多一个
        self.sweep_job: SourcesSweepJob | None = None
        #: 最近一次完成 ISI+PSS-10 的时间（身心预警弹窗据此解除）
        self.last_assessment: dict[str, datetime] = {}
        #: 现场市场研究的抓取函数覆盖点（测试注入桩；None = connector 真抓）
        self.research_fetch_fn = None
        #: 现场 AI 拆解任务（A4，2026-08-02）：跑在服务端，切页/关页不中断。
        self.research_jobs: dict[tuple[str, str], DecompositionResearchJob] = {}
        #: 每人每日已用次数，key = (student_id, date-iso)
        self.research_daily: dict[tuple[str, str], int] = {}
        #: 审查 H3：A5 生成失败的负缓存——(student_id, 目标指纹) → 失败日期
        self.a5_failed: dict[tuple[str, str], date] = {}
        #: 状态灯（2026-08-03）：云端无 adk 脚本时的 Vertex REST 探测回退；
        #: 测试注入 callable（返回 display_name 元组），生产默认走真实 REST
        self.runtime_rest_fn = None
        #: stale-while-revalidate 单飞标志（状态灯，2026-08-03）
        self.runtime_refreshing = False
        #: 「不参加」名单（2026-08-03 用户需求 B）：student_id → 被拒 subject 集合；
        #: A5 重新生成与演示夹具都要跳过——删了的活动不许复活
        self.declined: dict[str, set[str]] = {}
        #: Bug-1（2026-08-03）：研究任务发起时的目标名（规范化）——
        #: 目标改名后旧结果按此判stale，不再顶替新岗位的画像
        self.research_target: dict[tuple[str, str], str] = {}
        self.outreach_queue: list[WellbeingOutreachRequest] = []
        #: R7-B：投稿本体存这里——审核队列读它，裁决改它。
        #: PublishingService 只管状态迁移与审计，不管存储。
        self.submissions: dict[str, PublicationSubmission] = {}
        #: R7-D：A0 的编排痕迹（每学生最近 20 条）。agent-trace 端点读它。
        self.agent_traces: dict[str, list] = {}
        #: R8-3：三层心理干预的状态。
        #: 第一层自动联系 tutor 的干预台账（demo 不真发邮件，记录在案）。
        self.tutor_interventions: list[dict] = []
        #: 咨询室工作时段（校方可改）。默认工作日上午 10–12、下午 14–16。
        self.counseling_hours = CounselingHours(
            windows=tuple(
                CounselingWindow(weekday=w, start=s, end=e)
                for w in range(5)
                for s, e in (("10:00", "12:00"), ("14:00", "16:00"))
            ),
            slot_minutes=30,
            updated_at=datetime.now(timezone.utc),
        )
        self.counseling_bookings: list[CounselingBooking] = []
        #: 紧急红按钮使用计数（每学期重置；>2 即拉黑一学期）。
        self.emergency_uses: dict[str, int] = {}
        #: Advisor 预约（I）。学生只见自己的；Advisor 见队列但见不到学生私有域。
        self.advisor_bookings: list[AdvisorBooking] = []
        #: B10：下架留档（活动取消后从广场移除，但不销毁）
        self.withdrawn_opportunities: list[Opportunity] = []
        #: H1：注册 id 的单调序号（起点=初始名录数，删除不回退）
        self.advisor_seq = 3
        #: R4-K：选修推荐当日缓存（与 /matches 同一口径：每日一次 AI）
        self.course_rec_cache: dict[tuple[str, str], list] = {}
        #: R5-E2：学生自填的重要联系人（辅导员/班主任/班长）。不写死在代码里。
        # R8-2：demo 学生自带联系人 fixture（学生随时可改）。邮箱来自
        # 环境变量 GOOGLE_TEST_ACCOUNT_EMAIL——测试邮箱不进代码库（密钥纪律），
        # 没配则回落到 example.invalid 哑地址。
        import os as _os

        _demo_email = _os.getenv("GOOGLE_TEST_ACCOUNT_EMAIL",
                                 "demo-contact@example.invalid")
        self.contacts: dict[str, "ImportantContacts"] = {
            sid: ImportantContacts(
                student_id=sid,
                contacts=(
                    ContactPerson(role="tutor",
                                  name=f"{sid} 班级 Tutor (Synthetic)",
                                  email=_demo_email, phone=None),
                    ContactPerson(role="class_teacher",
                                  name=f"{sid} 班主任 (Synthetic)",
                                  email=_demo_email, phone=None),
                    ContactPerson(role="monitor",
                                  name=f"{sid} 班长 (Synthetic)",
                                  email=_demo_email, phone=None),
                ),
                updated_at=datetime.now(timezone.utc),
            )
            for sid in self.students
        }
        #: R5-B：档案补充分区（合成初值，与 seed/demo_students 档案一致；
        #: 学生可整组改写。接真实系统后由学生数据替换）。
        self.profile_extras = self._build_profile_extras()
        #: Q（2026-07-31）：合成顾问名录。接真实 Career Center 系统时换数据源即可。
        #: 时段确定性生成：今天起 10 个工作日，每人每天 9 个一小时档（工作日 8–12 / 13–18）。
        self.advisors = self._build_advisor_directory()
        #: 已投递的提醒。状态机靠它判断"这是第几次"与"该不该再发"。
        self.reminders: dict[str, list[WellbeingReminderEvent]] = {}
        # R8-2：外联同意**按学生** seed——曾只有 STU-B 有 CONSENT-DEMO，
        # 其他学生按「联系辅导员」全部 403（真机踩到）。旧 id 保留给回归测试。
        self.consents = {
            "CONSENT-DEMO": OutreachConsent(
                consent_id="CONSENT-DEMO", student_id="STU-B", scope="single_request",
                recipient_role="counseling_wellbeing_queue",
                granted_at=datetime.now(timezone.utc) - timedelta(hours=1),
            ),
            **{
                f"CONSENT-DEMO-{sid}": OutreachConsent(
                    consent_id=f"CONSENT-DEMO-{sid}", student_id=sid,
                    scope="single_request",
                    recipient_role="counseling_wellbeing_queue",
                    granted_at=datetime.now(timezone.utc) - timedelta(hours=1),
                )
                for sid in self.students
            },
        }
        self.evidence = [EvidenceRecord(**e) for e in bundle["evidence"]]
        self.experiences = [ExperienceRecord(**e) for e in bundle["experiences"]]
        self.notes = [Note(**n) for n in bundle["notes"]]
        self.availability = [
            AvailabilityBlock(**b) for b in bundle["availability_blocks"]
        ]
        #: A+M：学生**本人**通过创建/编辑端点划出的保护时段 id。
        #: 只有这些计入 protected_time_hours（从成长预算里让出的时间）；
        #: 种子/作息生成的保护块只挡排程，不改容量口径。
        self.personal_protected_ids: set[str] = set()
        self.proposals = [
            ProfileUpdateProposal(**p) for p in bundle["profile_update_proposals"]
        ]
        # R10-5（2026-08-01 用户裁定）：档案更新提议**只**基于已完成活动的
        # 证据链（闭环 PROP-EXP-*）与学生本人上传的 resume 提炼——
        # seed 的行为推断模板（"连续三次选择了…"）不再注入 store，
        # 只留在 bundle 里供事件历史（记忆中心）展示。
        #: A5 提交的路径版本与排程预览。目前只在进程内存活——
        #: 换 Firestore 后端时替换这两个容器，端点不变。
        self.pathways: dict[str, PathwayVersion] = {}
        self.schedule_proposals: dict[str, list[ScheduleProposal]] = {}
        #: /matches 的当日缓存与手动刷新计数（F：一天真正跑一次 AI，手动限 3 次）
        self.match_cache: dict[str, tuple[date, list[MatchResult]]] = {}
        self.match_refreshes: dict[tuple[str, date], int] = {}
        #: 服务端签发的批准回执：receipt_id → "student_id:proposal_id"。
        #: 日历写入只认这里签发过的回执——客户端自造的字符串不算数（B2/规则 8）。
        self.approval_receipts: dict[str, str] = {}
        #: 学生的行动流（收藏、加入计划、申请…）。收藏列表是它的一个切片。
        self.actions: dict[str, list[ActionEvent]] = {}
        self.metric_tuples = [MetricTuple(**m) for m in bundle["metric_tuples"]]
        self.quality_feedback = [
            EventQualityFeedback(**f) for f in bundle["event_quality_feedback"]
        ]
        self.as_of = date.fromisoformat(bundle["manifest"]["as_of"])

    def _build_profile_extras(self):
        """三位演示学生的补充分区初值（全合成，对齐 seed/demo_students 档案）。"""
        from campuspath_contracts.profile import (
            EducationEntry, LanguageSkill, ProfileEntry, ProfileExtras)

        now = datetime.now(timezone.utc)

        def entry(**kw):
            return ProfileEntry(**kw)

        return {
            "STU-A": ProfileExtras(
                student_id="STU-A",
                education=(
                    EducationEntry(school="HKUST", program="BSc in Computer Science",
                                   start_year="2025", end_year="2029"),
                    EducationEntry(school="合成高中（Demo）", start_year="2019",
                                   end_year="2025", note="理科方向"),
                ),
                languages=(
                    LanguageSkill(language="中文", proficiency="母语"),
                    LanguageSkill(language="英语", proficiency="流利",
                                  certification="HKDSE English Level 5"),
                ),
                honors=(entry(title="校内黑客松参与奖", issuer="HKUST Student Union",
                              date="2026-03"),),
                organizations=(entry(title="HKUST Computer Society · 干事",
                                     date="2025-09"),),
                hobbies=("像素游戏制作", "吉他"),
                updated_at=now,
            ),
            "STU-B": ProfileExtras(
                student_id="STU-B",
                education=(
                    EducationEntry(school="HKUST", program="BBA in Information Systems",
                                   start_year="2024", end_year="2028"),
                    EducationEntry(school="合成高中（Demo）", start_year="2018",
                                   end_year="2024"),
                ),
                languages=(
                    LanguageSkill(language="中文", proficiency="母语"),
                    LanguageSkill(language="英语", proficiency="流利",
                                  certification="IELTS 7.0"),
                ),
                honors=(entry(title="院系奖学金（合成）", issuer="HKUST Business School",
                              date="2025-11"),),
                organizations=(entry(title="学生会 · 干事（合成）", date="2024-10"),),
                hobbies=("羽毛球", "烘焙"),
                updated_at=now,
            ),
            "STU-C": ProfileExtras(
                student_id="STU-C",
                education=(
                    EducationEntry(school="HKUST",
                                   program="BEng in Industrial Engineering and "
                                           "Decision Analytics",
                                   start_year="2024", end_year="2028"),
                    EducationEntry(school="合成国际高中（Demo）", start_year="2018",
                                   end_year="2024", note="国际生"),
                ),
                languages=(
                    LanguageSkill(language="中文", proficiency="母语"),
                    LanguageSkill(language="英语", proficiency="接近母语",
                                  certification="TOEFL 108"),
                ),
                publications=(entry(
                    title="校内数据建模竞赛技术报告（合成）",
                    issuer="合成运筹实验室（Demo）", date="2026-06"),),
                honors=(entry(title="数据建模竞赛二等奖（合成）", date="2025-12"),),
                organizations=(entry(title="运筹学社 · 成员（合成）", date="2024-11"),),
                hobbies=("摄影", "长跑"),
                updated_at=now,
            ),
        }

    def standard_advisor_slots(self, advisor_id: str):
        """标准时段库存：未来 10 个工作日 × 正常工作日的**一小时**档
        （上午 8–12、下午 13–18，共 9 档/天，用户裁定 2026-08-01）。
        确定性生成。R8-1：自助注册的新顾问也用同一份口径。
        B9：预约按时间段不按时间点——一次一小时。"""
        from campuspath_contracts.advising import AdvisorSlot

        slots = []
        day, added = self.today, 0
        while added < 10:
            day += timedelta(days=1)
            if day.weekday() >= 5:
                continue
            added += 1
            for hour in (8, 9, 10, 11, 13, 14, 15, 16, 17):
                start = datetime(day.year, day.month, day.day, hour,
                                 tzinfo=timezone.utc)
                slots.append(AdvisorSlot(
                    slot_id=f"SLOT-{advisor_id}-{day.isoformat()}-{hour:02d}",
                    advisor_id=advisor_id,
                    span=TimeRange(start=start,
                                   end=start + timedelta(hours=1)),
                ))
        return tuple(slots)

    def next_advisor_id(self) -> str:
        """H1 修复（审查 2026-08-01）：id 用单调计数器，不再取 len+1——
        删除会让 len 回退，新注册会撞上仍存在的 id，从此两位顾问共用
        一套确定性 slot_id（新顾问的空档显示成已约、编辑/删除落错人）。"""
        self.advisor_seq += 1
        candidate = f"ADV-{self.advisor_seq:02d}"
        while any(a.advisor_id == candidate for a in self.advisors):
            self.advisor_seq += 1
            candidate = f"ADV-{self.advisor_seq:02d}"
        return candidate

    def _build_advisor_directory(self):
        """三位合成顾问起步；R8-1 起名录可通过自助注册增长。"""
        from campuspath_contracts.advising import Advisor

        roster = (
            ("ADV-01", "Advisor Chan (Synthetic)", "实习申请 · 简历与面试 / Internships & interviews"),
            ("ADV-02", "Advisor Lee (Synthetic)", "读研与科研规划 / Postgraduate & research"),
            ("ADV-03", "Advisor Wong (Synthetic)", "创业与职业转型 / Entrepreneurship & pivots"),
        )
        return [
            Advisor(advisor_id=advisor_id, name=name, focus=focus,
                    slots=self.standard_advisor_slots(advisor_id))
            for advisor_id, name, focus in roster
        ]


def create_app(deps: Deps | None = None) -> FastAPI:
    deps = deps or Deps()
    app = FastAPI(
        title="CampusPath API",
        version=CONTRACTS_VERSION,
        description=(
            "实现 `campuspath_contracts.openapi` 冻结的契约。**全部数据为合成数据。**\n\n"
            "角色通过 `X-CampusPath-Role` 声明——这是授权层不是认证层，"
            "真实部署时换成从 IAM 断言取角色，判定逻辑不变。"
        ),
    )
    router = APIRouter(prefix="/v1")
    implemented: set[tuple[str, str]] = set()

    def implements(method: str, path: str, **kwargs: Any):
        """注册一个真实实现，并记账。未被注册的契约端点稍后自动补成 501。"""
        implemented.add((method.upper(), f"/v1{path}"))

        def decorator(fn):
            router.add_api_route(path, fn, methods=[method.upper()], **kwargs)
            return fn

        return decorator

    # ── 学生：Profile 与容量 ────────────────────────────────────────
    @implements("GET", "/students/{student_id}/profile", response_model=StudentProfile)
    def profile(student_id: str) -> StudentProfile:
        found = deps.students.get(student_id)
        if found is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        return found

    @implements("POST", "/students/{student_id}/profile/self-edit",
                response_model=StudentProfile)
    def profile_self_edit(student_id: str,
                          edit: ProfileSelfEdit) -> StudentProfile:
        """R4-G：学生本人直接编辑档案（技能标签 / 经历）。

        B3 挡的是 Agent 暗改；本人编辑与"学生自己设目标"同一先例。
        编辑后的经历核验状态回落 self_reported——改过的内容不继承学校认证。
        """
        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        if edit.interests is not None:
            deps.students[student_id] = StudentProfile.model_validate({
                **student.model_dump(),
                "interests": tuple(x.strip() for x in edit.interests if x.strip()),
                "version": student.version + 1,
                "updated_at": datetime.now(timezone.utc),
            })
        if edit.experiences is not None:
            for exp in edit.experiences:
                if exp.student_id != student_id:
                    raise HTTPException(422, "经历记录的学生与路径不一致")
            replaced = [
                exp.model_copy(update={"verification_status":
                                       VerificationStatus.SELF_REPORTED})
                for exp in edit.experiences
            ]
            deps.experiences[:] = [
                e for e in deps.experiences if e.student_id != student_id
            ] + replaced
        # ── 国际学生上下文（B/F，2026-08-02：档案页唯一入口）──────────
        # 提供 = 整体替换；clear = 取消勾选（上下文清空；context_pack 同意的
        # 撤销走 /consents 既有回路，前端两步都做——这里不越权代撤）。
        if edit.clear_intl_context:
            deps.students[student_id] = deps.students[student_id].model_copy(update={
                "intl_context": None,
                # 审查 #6：取消勾选时服务端顺带撤销同意，不依赖前端补第二刀
                "consent": tuple(
                    c.model_copy(update={"granted": False,
                                         "revoked_at": datetime.now(timezone.utc)})
                    if c.scope is ConsentScope.CONTEXT_PACK and c.granted else c
                    for c in deps.students[student_id].consent
                ),
                "version": deps.students[student_id].version + 1,
                "updated_at": datetime.now(timezone.utc),
            })
        elif edit.intl_context is not None:
            # 审查 #6：敏感自述（证件/语言/城市）落库前必须已有 context_pack 同意
            if not deps.students[student_id].has_consent(ConsentScope.CONTEXT_PACK):
                raise HTTPException(403, {
                    "error": "context_pack_consent_required",
                    "detail": "先授予 context_pack 同意再保存国际生信息",
                })
            deps.students[student_id] = deps.students[student_id].model_copy(update={
                "intl_context": edit.intl_context,
                "version": deps.students[student_id].version + 1,
                "updated_at": datetime.now(timezone.utc),
            })
        # ── 主/副目标推荐配比（2026-08-02 用户需求）────────────────────
        if edit.candidate_goal_share is not None:
            deps.students[student_id] = deps.students[student_id].model_copy(update={
                "candidate_goal_share": edit.candidate_goal_share,
                "version": deps.students[student_id].version + 1,
                "updated_at": datetime.now(timezone.utc),
            })
        # codex 审查 #3（fix/intl-chain）：intl 状态或推荐配比变了就作废
        # 当日推荐缓存——否则新设置停留到次日或手动刷新才生效
        if (edit.clear_intl_context or edit.intl_context is not None
                or edit.candidate_goal_share is not None):
            deps.match_cache.pop(student_id, None)
        # （曾有的「我现在大几」自述学期通道已撤：2026-08-03 用户裁定，
        # 学期/年级全局只认教务侧——契约 extra=forbid 会直接拒收该字段）
        return deps.students[student_id]

    @implements("GET", "/students/{student_id}/wellbeing/escalation",
                response_model=WellbeingEscalation)
    def wellbeing_escalation(student_id: str) -> WellbeingEscalation:
        """R5-E：升级判定，全部确定性阈值（写在契约 docstring 里）。

        睡眠只看学生**显式声明**的窗口与日历里占用它的安排——
        未声明就不推断（§16.8.2），如实返回 None 与 0 覆盖天数。
        """
        student = _known_student(student_id)
        ep = student.energy_profile

        declared_hours: float | None = None
        if ep.sleep_window_start and ep.sleep_window_end:
            sh, sm = (int(x) for x in ep.sleep_window_start.split(":"))
            eh, em = (int(x) for x in ep.sleep_window_end.split(":"))
            minutes = (eh * 60 + em) - (sh * 60 + sm)
            if minutes <= 0:
                minutes += 24 * 60          # 跨午夜
            declared_hours = round(minutes / 60.0, 2)

        # ── 「睡眠-负荷平衡」计数模型（2026-08-02 用户裁定，取代连续 streak）──
        # 合格日 = 有效睡眠 <7h 且 学习工作（忙+课程，即全部 BUSY 块）>11h；
        # 滚动 14 天 ≥10 → warning；滚动 28 天 ≥20 → assessment。
        # 依据（工程化简化，非医疗建议）：ATUS 3.5h 生理固定成本、
        # WHO/ILO 周 55h 过劳阈值、Scarcity 15–20% 缓冲共识——见 Spec v4.1.14。
        SLEEP_REF, STUDY_LIMIT = 7.0, 11.0
        deficit_streak = 0
        coverage = 0
        qualifying_14 = qualifying_28 = 0
        if declared_hours is not None:
            busy_blocks = [b for b in deps.availability
                           if b.student_id == student_id
                           and b.type is AvailabilityType.BUSY]
            intrusion_by_day: dict[str, float] = {}
            study_by_day: dict[str, float] = {}
            for b in busy_blocks:
                day = b.span.start.date().isoformat()
                s_min = b.span.start.hour * 60 + b.span.start.minute
                e_min = b.span.end.hour * 60 + b.span.end.minute
                dur = (e_min - s_min) if e_min > s_min else (e_min + 24 * 60 - s_min)
                study_by_day[day] = study_by_day.get(day, 0.0) + dur / 60.0
                # 侵入声明睡眠窗口的忙碌分钟数（同日近似：只算与窗口重叠部分）
                w_s = int(ep.sleep_window_start.split(":")[0]) * 60 +                     int(ep.sleep_window_start.split(":")[1])
                w_e = w_s + int(declared_hours * 60)
                overlap = max(0, min(e_min + (24 * 60 if e_min < s_min else 0), w_e)
                              - max(s_min, w_s))
                intrusion_by_day[day] = intrusion_by_day.get(day, 0.0) + overlap / 60.0
            days = sorted({b.span.start.date() for b in
                           (x for x in deps.availability
                            if x.student_id == student_id)})
            coverage = len(days)

            def _qualifies(day) -> bool:
                key = day.isoformat()
                effective = declared_hours - intrusion_by_day.get(key, 0.0)
                return (effective < SLEEP_REF
                        and study_by_day.get(key, 0.0) > STUDY_LIMIT)

            streak = 0
            for day in days:
                if _qualifies(day):
                    streak += 1
                else:
                    streak = 0
            deficit_streak = streak
            if days:
                anchor = days[-1]           # 数据最新一天为窗口锚点（demo 固定日期）
                win14 = {d for d in days if 0 <= (anchor - d).days < 14}
                win28 = {d for d in days if 0 <= (anchor - d).days < 28}
                qualifying_14 = sum(1 for d in win14 if _qualifies(d))
                qualifying_28 = sum(1 for d in win28 if _qualifies(d))

        snapshot_rows = deps.snapshots.get(student_id) or []
        overload_now = bool(snapshot_rows and snapshot_rows[0].overload_signal)
        refused = sum(
            1 for p in deps.schedule_proposals.get(student_id, ())
            if p.student_decision == "rejected"
        )

        reasons: list[LocalizedText] = []
        tier = "none"
        if qualifying_14 >= 10:
            tier = "warning"
            reasons.append(LocalizedText(
                zh_Hans=f"最近 14 天里有 {qualifying_14} 天睡眠不足 7 小时且"
                        f"学习工作超过 11 小时（阈值 10 天）",
                en=f"{qualifying_14} of the last 14 days had under 7h sleep "
                   f"and over 11h of study/work (threshold 10)"))
        if qualifying_28 >= 20:
            tier = "assessment"
            reasons.append(LocalizedText(
                zh_Hans=f"最近 28 天里有 {qualifying_28} 天睡眠不足 7 小时且"
                        f"学习工作超过 11 小时（阈值 20 天）——建议完成两份"
                        f"自测量表，帮自己确认一下状态",
                en=f"{qualifying_28} of the last 28 days had under 7h sleep "
                   f"and over 11h of study/work (threshold 20) — please take "
                   f"the two short self-assessments"))
        return WellbeingEscalation(
            student_id=student_id,
            declared_sleep_hours=declared_hours,
            sleep_deficit_consecutive_days=deficit_streak,
            data_coverage_days=coverage,
            qualifying_days_14=qualifying_14,
            qualifying_days_28=qualifying_28,
            last_assessment_at=deps.last_assessment.get(student_id),
            overload_now=overload_now,
            refused_or_deferred_30d=refused,
            tier=tier,
            reasons=tuple(reasons),
        )

    @implements("POST", "/students/{student_id}/wellbeing/assessment",
                response_model=WellbeingAssessmentResult)
    def wellbeing_assessment(student_id: str,
                             request: WellbeingAssessmentRequest
                             ) -> WellbeingAssessmentResult:
        """R5-E：ISI + PSS-10 计分与分流（wellbeing 服务，零 LLM）。

        R8-3（2026-08-01 用户裁定，Spec §16.8 同步）：第一层分流
        （routing=tutor）**自动**联系学生自填的班级 tutor——量表由学生
        本人主动提交，提交动作即知情动作，B13 的"学生请求"语义据此覆盖
        第一层。第二层（counseling_center）不自动：引导学生自选时段预约。
        """
        from campuspath_wellbeing.assessment import score_assessment

        _known_student(student_id)
        if request.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        try:
            score = score_assessment(list(request.isi_answers),
                                     list(request.pss10_answers))
        except ValueError as exc:
            raise HTTPException(422, str(exc))

        contact_name: str | None = None
        auto_sent = False
        auto_email: str | None = None
        if score.routing == "tutor":
            saved = deps.contacts.get(student_id)
            tutor = next(
                (c for c in (saved.contacts if saved else ())
                 if c.role == "tutor"), None)
            if tutor is not None:
                contact_name = tutor.name
                if tutor.email:
                    # 固定模板、零 LLM；记录在案（干预台账），demo 不真发邮件
                    deps.tutor_interventions.append({
                        "student_id": student_id, "to": tutor.email,
                        "tutor_name": tutor.name,
                        "isi": score.isi_score, "pss10": score.pss10_score,
                        "at": datetime.now(timezone.utc).isoformat(),
                    })
                    auto_sent, auto_email = True, tutor.email
        elif score.routing == "counseling_center":
            contact_name = "学校心理咨询中心 / Campus Counseling Center"

        # 2026-08-02 弹窗模型：完成量表的时间落档——assessment 级弹窗据此解除
        deps.last_assessment[student_id] = datetime.now(timezone.utc)

        return WellbeingAssessmentResult(
            student_id=student_id,
            isi_score=score.isi_score, isi_band=score.isi_band,
            pss10_score=score.pss10_score, pss10_band=score.pss10_band,
            routing=score.routing,
            recommended_contact_name=contact_name,
            auto_contact_sent=auto_sent,
            auto_contact_email=auto_email,
            disclaimer=LocalizedText(
                zh_Hans=score.disclaimer_zh, en=score.disclaimer_en),
        )

    @implements("GET", "/students/{student_id}/profile/extras",
                response_model=ProfileExtras)
    def get_profile_extras(student_id: str) -> ProfileExtras:
        """R5-B：补充分区。没有记录时返回空集合——空是合法状态。"""
        _known_student(student_id)
        found = deps.profile_extras.get(student_id)
        if found is None:
            return ProfileExtras(student_id=student_id,
                                 updated_at=datetime.now(timezone.utc))
        return found

    @implements("POST", "/students/{student_id}/profile/extras",
                response_model=ProfileExtras)
    def save_profile_extras(student_id: str,
                            extras: ProfileExtras) -> ProfileExtras:
        """整组替换；学生本人随时可改（B3 挡 Agent，不挡本人）。"""
        _known_student(student_id)
        if extras.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        normalized = extras.model_copy(
            update={"updated_at": datetime.now(timezone.utc)})
        deps.profile_extras[student_id] = normalized
        return normalized

    @implements("GET", "/students/{student_id}/contacts",
                response_model=ImportantContacts)
    def get_contacts(student_id: str) -> ImportantContacts:
        """R5-E2：未填过返回空集合——空是合法状态，不是 404。"""
        _known_student(student_id)
        found = deps.contacts.get(student_id)
        if found is None:
            return ImportantContacts(
                student_id=student_id, contacts=(),
                updated_at=datetime.now(timezone.utc))
        return found

    @implements("POST", "/students/{student_id}/contacts",
                response_model=ImportantContacts)
    def save_contacts(student_id: str,
                      contacts: ImportantContacts) -> ImportantContacts:
        """整组替换；学期内任意时间可改（联系人变动频繁，不做审批流）。"""
        _known_student(student_id)
        if contacts.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        normalized = contacts.model_copy(
            update={"updated_at": datetime.now(timezone.utc)})
        deps.contacts[student_id] = normalized
        return normalized

    @implements("POST", "/students/{student_id}/consents",
                response_model=ConsentRecord)
    def update_consent(student_id: str, request: ConsentUpdateRequest) -> ConsentRecord:
        """学生自助开关单项同意（N，2026-07-31）。

        此前 calendar_write 只存在于种子里——STU-B 有，其他人**没有任何入口**
        能授出这个权，于是行动中心永远停在「已批准，但日历写入未获授权」。
        修的是入口，不是闸门：写入路径的同意检查一行未动。
        回执由服务端签发（B13），撤销即时生效且留下 revoked_at。
        """
        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        now = datetime.now(timezone.utc)
        record = ConsentRecord(
            scope=request.scope,
            granted=request.granted,
            granted_at=now if request.granted else None,
            revoked_at=None if request.granted else now,
            receipt_id=f"CONSENT-RCPT-{student_id}-{request.scope.value}",
        )
        others = tuple(c for c in student.consent if c.scope is not request.scope)
        # 重新校验而不是 model_copy(update=)——后者绕过全部 validator（坑 §10.2）
        deps.students[student_id] = StudentProfile.model_validate({
            **student.model_dump(),
            "consent": (*others, record.model_dump()),
            "version": student.version + 1,
            "updated_at": now,
        })
        # codex 审查 #3（fix/intl-chain）：context_pack 同意开关直接影响
        # intl_notes 的有无——当日推荐缓存跟着作废
        if request.scope is ConsentScope.CONTEXT_PACK:
            deps.match_cache.pop(student_id, None)
        return record

    def _eligibility_assessment(opportunity, outcome, validation, now):
        """把 Rules 的判定包成契约模型。``validation_id`` 是 Rules 签发的那一个——
        这里不新造、不改判，只是换个容器。"""
        from campuspath_contracts.opportunity import (
            EligibilityAssessment,
            EligibilityReason,
            EligibilityRuleKind,
        )

        return EligibilityAssessment(
            assessment_id=f"EA-{opportunity.opportunity_id}-{validation.validation_id[4:12]}",
            opportunity_id=opportunity.opportunity_id,
            state=outcome.state,
            reasons=tuple(
                EligibilityReason(
                    rule_kind=EligibilityRuleKind.OTHER,
                    # Rules 现在直接给 LocalizedText，不再需要把中文塞两侧
                    detail=reason,
                    source_tier="rules_engine",
                )
                for reason in outcome.reasons
            ),
            next_eligibility_date=outcome.next_eligibility_date,
            validation_id=validation.validation_id,
            evaluated_at=now,
        )

    def _match_rationale(model, student_id: str, rows) -> dict[str, tuple]:
        """向模型要一句话理由。**排序已经定了**，它改不了顺序。

        失败时返回空——理由缺失只是少一行文案，而排序、资格与凭据
        都不依赖它。让一次模型抖动带走整个 For You 页面是不可接受的。
        """
        from campuspath_agents.model import ModelRequest

        # 摘要必须带**实质内容**（标题、类型、技能、覆盖的要求类别）。
        # 第一版只给了 id 与分数，模型于是只能把分数复述一遍
        #   "分数0.592，因此排在最高分机会之首"
        # ——一句对学生零价值的话。理由的信息量上限由输入决定，不由提示词决定。
        summary = "\n".join(
            "\t".join([
                o.opportunity_id, o.type, o.title,
                "技能:" + ("/".join(o.skills[:4]) or "未标注"),
                "覆盖:" + ("/".join(c.value for c in o.requirement_categories[:3]) or "未标注"),
                f"投入:{o.workload_hours_total or '未知'}h",
                f"状态:{outcome.state.value}",
            ])
            for _, o, outcome, _, _ in rows
        )
        try:
            raw = model.generate(ModelRequest(
                system=(
                    "下面每行是一个已经排好序的机会。为每一行写一句不超过 30 字的中文理由"
                    "和一句不超过 20 词的英文理由，说明它**对这个学生**的价值——"
                    "用它的技能、覆盖的要求类别或投入量来说，"
                    "**不要复述分数或名次**。不要改变顺序，不要评论资格。"
                    "每行输出格式：opportunity_id<TAB>中文理由<TAB>英文理由"
                ),
                data=(summary,),
                purpose=f"match_rationale:{student_id}",
            ))
        except Exception:
            return {}
        out: dict[str, tuple] = {}
        for line in raw.splitlines():
            # 三段：id、中文、英文。英文缺席时回落中文——照实显示，
            # 不再把中文复制进 en 假装是双语（agents 行为核验发现的既有缺陷）
            parts = [x.strip() for x in line.split("\t")]
            if len(parts) >= 2 and parts[0]:
                zh = parts[1][:500]
                en = (parts[2] if len(parts) >= 3 and parts[2] else zh)[:500]
                out[parts[0]] = (LocalizedText(zh_Hans=zh, en=en),)
        return out

    def _known_student(student_id: str) -> StudentProfile:
        found = deps.students.get(student_id)
        if found is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        return found

    # ── 学生自己的只读出口 ─────────────────────────────────────────
    # D1 要求这些页面的数据**全部来自 Seed**（"改 Seed 后前端跟随变化"），
    # 所以它们必须有读端点。写入路径一个都没放宽：Profile 仍只能经
    # decision 改，Reflection 原文仍只有这一个出口——向聚合方向
    # 走不通这件事，是类型层挡的，不是靠这里少写一个路由。
    @implements("GET", "/students/{student_id}/profile/proposals",
                response_model=list[ProfileUpdateProposal])
    def profile_proposals(student_id: str) -> list[ProfileUpdateProposal]:
        _known_student(student_id)
        # R10-5：只出证据型提议（闭环经历 + resume 提炼，均在 store）。
        # seed 的行为推断历史不再混进这一页——它们的痕迹在记忆中心。
        return list(_store(student_id).proposals())

    @implements("POST", "/students/{student_id}/evidence",
                response_model=EvidenceRecord)
    def upload_evidence(student_id: str, record: EvidenceRecord) -> EvidenceRecord:
        """R5-C：学生上传证据源文件（demo 存 vault 引用与元数据，不存 blob）。

        核验状态**强制** self_reported——上传一份文件不等于学校认证，
        这个区别在类型层就不给抹平的机会。幂等：同 id 重放原样返回。
        """
        _known_student(student_id)
        if record.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        existing = next(
            (e for e in deps.evidence if e.evidence_id == record.evidence_id), None)
        if existing is not None:
            return existing
        normalized = record.model_copy(update={
            "verification_status": VerificationStatus.SELF_REPORTED,
            "visibility": "private",
        })
        deps.evidence.append(normalized)
        return normalized

    @implements("GET", "/students/{student_id}/evidence",
                response_model=list[EvidenceRecord])
    def evidence(student_id: str) -> list[EvidenceRecord]:
        _known_student(student_id)
        return [e for e in deps.evidence if e.student_id == student_id]

    @implements("GET", "/students/{student_id}/notes", response_model=list[Note])
    def notes(student_id: str) -> list[Note]:
        _known_student(student_id)
        return [n for n in deps.notes if n.student_id == student_id]

    @implements("GET", "/students/{student_id}/experiences",
                response_model=list[ExperienceRecord])
    def experiences(student_id: str) -> list[ExperienceRecord]:
        _known_student(student_id)
        return [e for e in deps.experiences if e.student_id == student_id]

    @implements("GET", "/students/{student_id}/goals", response_model=list[Goal])
    def goals(student_id: str) -> list[Goal]:
        _known_student(student_id)
        return list(deps.goals.get(student_id, ()))

    @implements("POST", "/students/{student_id}/goals", response_model=Goal)
    def set_goal(student_id: str, goal: Goal) -> Goal:
        """学生自己设目标。**不走 A1 的提议→裁决路径**。

        B3 挡的是"Agent 悄悄改学生档案"；学生写下自己的目标不在其列，
        再套一层"提议等你批准"只会让人多点一次而已。

        同一个 role 只能有一个（G3：1 主 + 1 候选），重复设定是**替换**，
        不是追加——否则界面上会同时出现两个主目标，而契约里没有这种东西。
        """
        _known_student(student_id)
        if goal.student_id != student_id:
            raise HTTPException(422, "目标中的学生与路径不一致")
        existing = deps.goals.setdefault(student_id, [])
        previous = next(
            (g for g in existing
             if g.role is goal.role or g.goal_id == goal.goal_id), None)
        existing[:] = [
            g for g in existing
            if g.role is not goal.role and g.goal_id != goal.goal_id
        ]
        existing.append(goal)
        # Bug-1/2（2026-08-03 评测）：「换目标」的失效清单必须完整——
        # pathway 靠 trigger 指纹自愈、research 靠 research_target 判 stale，
        # 但 matches 与选修推荐的**当日缓存**要在这里当场清空；
        # 同名重存不清（现场结果复用语义不受伤）。
        def _norm(name: str | None) -> str:
            return (name or "").strip().lower()
        if previous is None or _norm(previous.target_name) != _norm(goal.target_name):
            deps.match_cache.pop(student_id, None)
            for key in [k for k in deps.course_rec_cache if k[0] == student_id]:
                del deps.course_rec_cache[key]
        return goal

    @implements("GET", "/students/{student_id}/availability",
                response_model=list[AvailabilityBlock])
    def availability(student_id: str) -> list[AvailabilityBlock]:
        """五类时段。**标题按学生的授权层级决定给不给。**

        授权判定在这里做，不在 Provider 里：Provider 只按被告知的层级取数，
        "学生同意了什么"是 Profile 上的事实。两者分开，是为了让
        "谁决定层级"这个问题只有一个答案。

        参与人、地点、备注在任何层级都没有——契约里就没有那些字段。
        """
        student = _known_student(student_id)
        granted = any(
            c.scope is ConsentScope.CALENDAR_EVENT_TITLES and c.granted
            and c.revoked_at is None
            for c in student.consent
        )
        blocks = [b for b in deps.availability if b.student_id == student_id]
        if granted:
            return blocks
        # 没有二级授权：**主动抹掉**标题而不是相信数据里本来就没有。
        # Seed 或将来的真实 Provider 若给多了，这里是最后一道闸。
        # 两类例外（B5 管的是"从私人日历采集"）：
        # ① 学生自己写的标签（privacy_level=student_defined）——本人笔迹；
        # ② 课表块（source=course_timetable）——教务公开数据，不是日历详情。
        return [
            b if b.title is None
            or b.privacy_level == "student_defined"
            or b.source is BlockSource.COURSE_TIMETABLE
            else b.model_copy(update={
                "title": None,
                "detail_level": CalendarDetailLevel.FREE_BUSY_ONLY,
            })
            for b in blocks
        ]

    @implements("GET", "/students/{student_id}/memory",
                response_model=list[MemoryEntry])
    def memory_entries(student_id: str) -> list[MemoryEntry]:
        _known_student(student_id)
        return list(deps.memory.list_for(student_id))

    @implements("GET", "/students/{student_id}/capacity-snapshot",
                response_model=CapacitySnapshot)
    def capacity_snapshot(student_id: str) -> CapacitySnapshot:
        rows = deps.snapshots.get(student_id)
        if not rows:
            raise HTTPException(404, f"{student_id} 没有容量快照——可能尚未连接日历")
        return rows[0]

    @implements("GET", "/students/{student_id}/wellbeing/signals",
                response_model=list[WellbeingCapacitySignal])
    def wellbeing_signals(student_id: str) -> list[WellbeingCapacitySignal]:
        """由 Rules & Constraint Engine 判定，**零 LLM**。

        缺前置数据时返回空列表是正确的：§16.8.2 要求没有学生显式设置
        就不生成信号。这与"端点没接"不同，所以它不在 501 之列。
        """
        from campuspath_rules.wellbeing import WellbeingInputs, evaluate_signals

        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        rows = deps.snapshots.get(student_id) or []
        if not rows:
            return []
        snapshot = rows[0]
        return evaluate_signals(
            WellbeingInputs(
                student_id=student_id,
                period_start=snapshot.period_start,
                period_end=snapshot.period_end,
                energy_profile=student.energy_profile,
                capacity=snapshot,
            ),
            now=datetime.now(timezone.utc),
        )

    # ── 学业事实（A2 的产出形状）────────────────────────────────────
    def _records(student_id: str) -> list[StudentCourseRecord]:
        rows = deps.records.get(student_id)
        if rows is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        return rows

    @implements("GET", "/students/{student_id}/academic-state",
                response_model=AcademicState)
    def academic_state(student_id: str) -> AcademicState:
        rows = _records(student_id)
        current = [r for r in rows if r.term == deps.current_term]
        return AcademicState(
            student_id=student_id, as_of=datetime.now(timezone.utc),
            current_term=deps.current_term, course_records=tuple(rows),
            current_term_credits=sum(r.credits for r in current),
        )

    @implements("GET", "/students/{student_id}/degree-progress",
                response_model=DegreeProgress)
    def degree_progress(student_id: str) -> DegreeProgress:
        """纯算术：已修学分按要求组归集。**不排序、不推荐**——那是 A5 的事。"""
        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        completed = {
            r.course_id: r for r in _records(student_id)
            if r.status is CourseStatus.COMPLETED
        }
        progress: list[DegreeRequirementProgress] = []
        total_earned = 0.0
        for requirement in deps.requirements.get(student.program_id, []):
            matched = [c for c in requirement.alternatives if c in completed]
            earned = sum(completed[c].credits for c in matched)
            total_earned += earned
            required = requirement.required_credits or 0.0
            progress.append(DegreeRequirementProgress(
                requirement_id=requirement.requirement_id,
                satisfied_by=tuple(completed[c].record_id for c in matched),
                earned_credits=earned,
                remaining_credits=max(required - earned, 0.0),
                satisfied=earned >= required > 0,
            ))
        return DegreeProgress(
            student_id=student_id, program_id=student.program_id,
            as_of=datetime.now(timezone.utc),
            total_earned_credits=total_earned, total_required_credits=120.0,
            requirement_progress=tuple(progress),
        )

    def _course_candidates_for(
        student_id: str, limit: int = 100,
    ) -> list[AnnotatedCourseCandidate]:
        """A2 的候选构建（事实与标注，无排序）。/course-candidates 与
        R4-K 的选修推荐共用这一份，不各算各的。

        R7-D：构造经过 ``AcademicAgent`` 类本体——先修判定仍是 Rules 给的
        事实，A2 只负责把事实组装成候选；契约上没有分数字段，
        "顺手排个序"在类型层就做不到。
        """
        from campuspath_agents.model import ScriptedModel
        from campuspath_agents.roster import AcademicAgent
        from campuspath_agents.tools import belt_for
        from campuspath_rules.prerequisites import AcademicRecord, Verdict, evaluate, parse

        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        rows = _records(student_id)
        done = frozenset(
            r.course_id for r in rows if r.status is CourseStatus.COMPLETED
        )
        grades = {r.course_id: r.grade for r in rows if r.grade}
        record = AcademicRecord(completed=done, grades=grades)
        a2 = AcademicAgent(
            AgentId.A2_ACADEMIC, belt_for(AgentId.A2_ACADEMIC, {}),
            deps.model or ScriptedModel(),   # annotate 不调模型，桩只为满足构造
        )

        out: list[AnnotatedCourseCandidate] = []
        for requirement in deps.requirements.get(student.program_id, []):
            for course_id in requirement.alternatives:
                if course_id in done or course_id not in deps.catalog:
                    continue
                course = deps.catalog[course_id]
                verdict = evaluate(parse(course.prerequisite_expression), record).verdict
                out.append(a2.annotate_course(
                    candidate_id=f"CC-{student_id}-{course_id.replace(' ', '')}",
                    course_id=course_id,
                    satisfies_groups=(requirement.requirement_id,),
                    prerequisite_status={
                        Verdict.MET: PrerequisiteStatus.MET,
                        Verdict.NOT_MET: PrerequisiteStatus.NOT_MET,
                        Verdict.UNKNOWN: PrerequisiteStatus.UNKNOWN,
                    }[verdict],
                    skill_tags=course.skill_tags,
                    source=course.source,
                ))
                if len(out) >= limit:
                    return out
        return out

    @implements("GET", "/students/{student_id}/course-candidates",
                response_model=list[AnnotatedCourseCandidate])
    def course_candidates(
        student_id: str, limit: int = Query(20, ge=1, le=100),
    ) -> list[AnnotatedCourseCandidate]:
        """A2 的产出：事实与标注，**无排序分数**（§8.1）。"""
        return _course_candidates_for(student_id, limit)

    # ── G3 / G4 ─────────────────────────────────────────────────────
    @implements("GET", "/students/{student_id}/gap-map", response_model=DynamicGapMap)
    def gap_map(student_id: str) -> DynamicGapMap:
        """主目标 + 候选目标（G3）。共享缺口按**要求类别**比对。"""
        goals = deps.goals.get(student_id)
        if not goals:
            raise HTTPException(404, f"{student_id} 尚未设定目标")
        primary = next((g for g in goals if g.role is GoalRole.PRIMARY), None)
        if primary is None:
            raise HTTPException(404, f"{student_id} 没有主目标")
        candidate = next((g for g in goals if g.role is GoalRole.CANDIDATE), None)

        # 缺口由**学位要求进度**确定性派生：没修够的就是缺口，
        # 差多少决定 missing / partial。这里没有排序分数，也没有取舍——
        # priority 只是"还差多少"的分档（A3 的职责范围），
        # "值不值得为它花时间"仍然只有 A5 能说。
        progress = degree_progress(student_id)
        gaps: list[Gap] = []
        for row in progress.requirement_progress:
            if row.satisfied:
                continue
            total = row.earned_credits + row.remaining_credits
            done_ratio = row.earned_credits / total if total > 0 else 0.0
            gaps.append(Gap(
                gap_id=f"GAP-{student_id}-{row.requirement_id}",
                student_id=student_id,
                requirement_id=row.requirement_id,
                goal_id=primary.goal_id,
                gap_level=GapLevel.PARTIAL if row.earned_credits > 0 else GapLevel.MISSING,
                priority=max(1, min(5, 5 - int(round(done_ratio * 4)))),
                estimated_reach_term=deps.current_term,
            ))

        # 未知项照搬 A2 报上来的数据不确定性。**不折叠成缺口**：
        # "读不出来"与"你还差着"是两件事，混在一起会让学生以为自己欠得更多。
        unknowns = tuple(
            u.detail or LocalizedText(zh_Hans=u.field_path, en=u.field_path)
            for u in progress.uncertainties
        )

        shared: list[SharedGap] = []
        if candidate is not None and gaps:
            # 两个目标同属一个学位，学位要求对两者都成立——
            # 这是**结构性共享**，不是推断出来的相似性。
            ids = tuple(g.requirement_id for g in gaps)
            shared.append(SharedGap(
                requirement_ids_primary=ids,
                requirement_ids_candidate=ids,
                category=RequirementCategory.COURSEWORK,
                description=LocalizedText(
                    zh_Hans=f"{len(ids)} 条学位要求对两个目标同时成立——先做这部分，两条路都不亏。",
                    en=(f"{len(ids)} degree requirements apply to both goals — "
                        "work here counts either way."),
                ),
            ))
        # 分叉点由 A3 从两个目标各自的 RequirementGraph 确定性对比得出：
        # 方向 → 非课程要求类别的映射是内容表（MODE_REQUIREMENT_CATEGORIES），
        # 只属于一条路的类别就是分叉。没有候选目标就没有分叉。
        divergence: tuple = ()
        if candidate is not None:
            from campuspath_agents.model import ScriptedModel
            from campuspath_agents.roster import GoalGapAgent
            from campuspath_agents.tools import belt_for
            from campuspath_contracts.common import AgentId

            a3 = GoalGapAgent(
                AgentId.A3_GOAL_GAP, belt_for(AgentId.A3_GOAL_GAP, {}),
                deps.model or ScriptedModel(),   # 这些方法不调模型，桩只为满足构造
            )
            now = datetime.now(timezone.utc)
            graph_p = a3.requirement_graph_for_mode(
                primary, graph_id=f"RG-{primary.goal_id}", now=now)
            graph_c = a3.requirement_graph_for_mode(
                candidate, graph_id=f"RG-{candidate.goal_id}", now=now)
            divergence = a3.derive_divergence(
                graph_p, graph_c, at_term=deps.current_term)
            mode_map = a3.compare_goals(
                GoalSet(student_id=student_id, primary=primary, candidate=candidate),
                graph_p, graph_c, gaps=(),
                map_id=f"GM-MODE-{student_id}", now=now,
            )
            shared.extend(mode_map.shared_gaps)
        return DynamicGapMap(
            map_id=f"GM-{student_id}", student_id=student_id,
            generated_at=datetime.now(timezone.utc),
            primary_goal_id=primary.goal_id,
            candidate_goal_id=candidate.goal_id if candidate else None,
            gaps=tuple(gaps),
            shared_gaps=tuple(shared),
            unknowns=unknowns,
            divergence_points=divergence,
        )

    def _term_of_date(d: date) -> str:
        """日期 → HKUST 学期码（确定性映射，与课程目录 term 编码同构）：
        9–12 月 = 当学年 FALL；1 月 = WINTER；2–5 月 = SPRING；6–8 月 = SUMMER。"""
        if d.month >= 9:
            return f"{d.year}-{str(d.year + 1)[2:]}_FALL"
        season = ("WINTER" if d.month == 1
                  else "SPRING" if d.month <= 5 else "SUMMER")
        return f"{d.year - 1}-{str(d.year)[2:]}_{season}"

    @implements("GET", "/students/{student_id}/growth-trajectory",
                response_model=GrowthTrajectory)
    def growth_trajectory(student_id: str) -> GrowthTrajectory:
        """G4（§17.3.1）：**纯确定性派生视图，不需要额外 Agent。**

        口径（2026-08-02 用户质询后固定，逐项可回溯）：
        - ``verified_growth_actions[term]`` = 该学期 **status=completed 的课程数**
          （教务记录，唯一出处 SIS 同步）；
        - ``new_confirmed_evidence[term]`` = 该学期 ``obtained_at`` 落入的
          **证据档案条目数**（EvidenceRecord，含自述——校验状态在证据档案页逐条可见）；
        - ``goal_confidence`` = 主目标当前的把握度（学生在目标工作室自设/调整，
          0–1；本端点原样透传，不做逐期演化——没有历史快照就不编历史曲线）；
        - ``gaps_closed`` 维持 0：差距↔证据的关闭判定链未接入，宁缺毋假，
          前端不展示该指标（撤下假 0，等判定链落地再上）。
        """
        goals = deps.goals.get(student_id)
        if not goals:
            raise HTTPException(404, f"{student_id} 尚未设定目标")
        primary = next((g for g in goals if g.role is GoalRole.PRIMARY), goals[0])
        by_term: dict[str, int] = {}
        for record in _records(student_id):
            if record.status is CourseStatus.COMPLETED:
                by_term[record.term] = by_term.get(record.term, 0) + 1
        evidence_by_term: dict[str, int] = {}
        for ev in deps.evidence:
            if ev.student_id == student_id:
                term = _term_of_date(ev.obtained_at)
                evidence_by_term[term] = evidence_by_term.get(term, 0) + 1
        terms = sorted(set(by_term) | set(evidence_by_term))
        points = tuple(
            GrowthTrajectoryPoint(
                term=term, gaps_closed=0,
                new_confirmed_evidence=evidence_by_term.get(term, 0),
                goal_confidence=primary.confidence,
                verified_growth_actions=by_term.get(term, 0),
            )
            for term in terms
        )
        if not points:
            raise HTTPException(404, f"{student_id} 尚无可聚合的学期记录")
        return GrowthTrajectory(
            student_id=student_id, goal_id=primary.goal_id, points=points,
            computed_at=datetime.now(timezone.utc),
        )

    @implements("GET", "/students/{student_id}/vga-summary",
                response_model=VgaSummary)
    def vga_summary(student_id: str) -> VgaSummary:
        """北极星指标 VGA（Spec §17.1，2026-08-04 落地）：纯确定性派生。

        分子来源唯一：Event Store 里 ``verified_growth=True`` 且
        ``result=succeeded`` 的行动事件（生产者=反思闭环，契约校验器强制
        挂证据）。按事件 ``timestamp`` 的自然月分桶——事件是实时铸的，
        这里用真实时钟而非演示时钟（evidence 的 obtained_at=deps.today
        与本指标无关）。**0 是事实不是缺数据**：没有事件也返回 200 空桶。
        """
        _known_student(student_id)
        events = [a for a in deps.actions.get(student_id, ())
                  if a.verified_growth and a.result == "succeeded"]
        buckets: dict[str, int] = {}
        for event in events:
            key = event.timestamp.strftime("%Y-%m")
            buckets[key] = buckets.get(key, 0) + 1
        now = datetime.now(timezone.utc)
        current = now.strftime("%Y-%m")
        return VgaSummary(
            student_id=student_id,
            current_month=current,
            current_month_count=buckets.get(current, 0),
            total_count=len(events),
            months=tuple(VgaMonthPoint(month=m, count=c)
                         for m, c in sorted(buckets.items())),
            computed_at=now,
        )

    # ── B3：Profile 的唯一写入路径 ──────────────────────────────────
    def _store(student_id: str):
        store = deps.stores.get(student_id)
        if store is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        return store

    @implements("POST", "/students/{student_id}/profile/proposals",
                response_model=ProfileUpdateProposal)
    def submit_proposal(student_id: str, proposal: ProfileUpdateProposal
                        ) -> ProfileUpdateProposal:
        """A1 提交更新建议。**status 必须是 pending**——Store 拒绝其余状态。"""
        from campuspath_state.store import UnconfirmedWrite

        try:
            _store(student_id).submit_proposal(proposal)
        except UnconfirmedWrite as exc:
            raise HTTPException(422, {"error": "unconfirmed_write",
                                      "detail": str(exc)}) from exc
        return proposal

    @implements("POST", "/students/{student_id}/profile/proposals/{proposal_id}/decision",
                response_model=ProfileChangeEvent)
    def decide_proposal(student_id: str, proposal_id: str, decision: str = Query(...),
                        ) -> ProfileChangeEvent:
        """学生的决定是**唯一**能改变 Profile 版本的动作（B3）。

        拒绝也会写事件，只是不 bump 版本——"为什么这条没写进去"要能回答。
        """
        from campuspath_state.store import ProposalNotFound, UnconfirmedWrite

        try:
            status = ProposalStatus(decision)
        except ValueError as exc:
            raise HTTPException(422, f"未知决定 {decision}") from exc
        try:
            # 审查 M7：审计事件的 changed_fields 要答得上「哪些字段变了」——
            # 按提案里实际出现的 entity_type 派生，不再恒写 ("skills",)
            _pending = next(
                (p for p in _store(student_id).proposals()
                 if p.proposal_id == proposal_id), None)
            _field_of = {
                "skill": "skills", "experience": "experiences",
                "education": "extras.education", "language": "extras.languages",
                "honor": "extras.honors", "certificate": "evidence",
            }
            fields = tuple(dict.fromkeys(
                _field_of.get(c.entity_type, c.entity_type)
                for c in (_pending.proposed_changes if _pending else ())
            )) if status is ProposalStatus.CONFIRMED else ()
            event = _store(student_id).apply_decision(
                proposal_id, status, decided_at=datetime.now(timezone.utc),
                changed_fields=fields,
            )
            # R5-G2：确认的变更物化进档案（总览的经历分区与标签池读它）。
            # 2026-08-02 用户报障修复三处：① Resume 经历不带 period（A1 不猜
            # 时间段）——此前 DateRange(start=None) 直接 500，回落到确认日并在
            # outcomes 注明"时间段待补充"；② 同一提案多条经历共用一个 EXP-id
            # 只落第一条——id 加序号；③ 技能类 add 此前根本没有写回路径——
            # 并入 interests 自述标签池（大小写不敏感去重、保序）。
            if status is ProposalStatus.CONFIRMED:
                proposal = next(
                    (p for p in _store(student_id).proposals()
                     if p.proposal_id == proposal_id), None)
                if proposal is not None:
                    decided_on = datetime.now(timezone.utc).date()
                    exp_index = 0
                    skill_adds: list[str] = []
                    # D 裁定（1.32.0）：模板解析新增四类的物化缓冲
                    edu_adds: list[dict] = []
                    lang_adds: list[dict] = []
                    honor_adds: list[dict] = []
                    cert_adds: list[dict] = []
                    for change in proposal.proposed_changes:
                        if (change.entity_type == "skill"
                                and change.operation == "add"
                                and isinstance(change.new_value, str)
                                and change.new_value.strip()):
                            skill_adds.append(change.new_value.strip())
                            continue
                        if change.operation == "add" and isinstance(
                                change.new_value, dict):
                            if change.entity_type == "education":
                                edu_adds.append(change.new_value)
                                continue
                            if change.entity_type == "language":
                                lang_adds.append(change.new_value)
                                continue
                            if change.entity_type == "honor":
                                honor_adds.append(change.new_value)
                                continue
                            if change.entity_type == "certificate":
                                # 审查 M6：自述证书 → extras（无伪造 Vault
                                # 引用；证书编号进 note 不再冒充颁发方）
                                value = change.new_value
                                cert_adds.append({
                                    "title": value.get("title", ""),
                                    "date": (value.get("obtained") or "")[:10]
                                    or None,
                                    "note": (f"编号：{value['credential_id']}"
                                             if value.get("credential_id")
                                             else None),
                                })
                                continue
                        if change.entity_type != "experience" or                                 change.operation != "add":
                            continue
                        exp_index += 1
                        value = change.new_value or {}
                        exp_id = f"EXP-{proposal_id}-{exp_index}"
                        if any(e.experience_id == exp_id
                               for e in deps.experiences):
                            continue        # 幂等
                        period_start = value.get("period_start") or decided_on
                        outcomes = tuple(value.get("outcomes", ()))
                        if not value.get("period_start"):
                            outcomes = outcomes + ("时间段未从 Resume 解析，待补充",)
                        deps.experiences.append(ExperienceRecord(
                            experience_id=exp_id,
                            student_id=student_id,
                            type=value.get("type", "other"),
                            organization=value.get("organization", ""),
                            role=value.get("role", ""),
                            period={"start": period_start,
                                    "end": value.get("period_end")},
                            outcomes=outcomes,
                            skills=tuple(value.get("skills", ())),
                        ))
                    if skill_adds:
                        current = deps.students[student_id]
                        seen = {t.lower() for t in current.interests}
                        merged = list(current.interests)
                        for tag in skill_adds:
                            if tag.lower() not in seen:
                                merged.append(tag)
                                seen.add(tag.lower())
                        if len(merged) != len(current.interests):
                            deps.students[student_id] = StudentProfile.model_validate({
                                **current.model_dump(),
                                "interests": tuple(merged),
                                "version": current.version + 1,
                                "updated_at": datetime.now(timezone.utc),
                            })
                    if edu_adds or lang_adds or honor_adds or cert_adds:
                        # 教育/语言/荣誉/证书并入 extras（自述分区；语义键去重）
                        found = deps.profile_extras.get(student_id)
                        base = found or ProfileExtras(
                            student_id=student_id,
                            updated_at=datetime.now(timezone.utc))
                        edu = list(base.education)
                        edu_keys = {(e.school.lower(),
                                     (e.program or "").lower()) for e in edu}
                        for v in edu_adds:
                            key = (str(v.get("school", "")).lower(),
                                   str(v.get("program") or "").lower())
                            if v.get("school") and key not in edu_keys:
                                edu.append(EducationEntry.model_validate(v))
                                edu_keys.add(key)
                        langs = list(base.languages)
                        lang_keys = {l.language.lower() for l in langs}
                        for v in lang_adds:
                            if (v.get("language")
                                    and str(v["language"]).lower()
                                    not in lang_keys):
                                langs.append(LanguageSkill.model_validate(v))
                                lang_keys.add(str(v["language"]).lower())
                        honors = list(base.honors)
                        honor_keys = {h.title.lower() for h in honors}
                        for v in honor_adds:
                            if (v.get("title")
                                    and str(v["title"]).lower()
                                    not in honor_keys):
                                honors.append(ProfileEntry.model_validate(v))
                                honor_keys.add(str(v["title"]).lower())
                        certs = list(base.certificates)
                        cert_keys = {c.title.lower() for c in certs}
                        for v in cert_adds:
                            if (v.get("title")
                                    and str(v["title"]).lower()
                                    not in cert_keys):
                                certs.append(ProfileEntry.model_validate(v))
                                cert_keys.add(str(v["title"]).lower())
                        deps.profile_extras[student_id] = base.model_copy(
                            update={"education": tuple(edu[:10]),
                                    "languages": tuple(langs[:10]),
                                    "honors": tuple(honors[:20]),
                                    "certificates": tuple(certs[:20]),
                                    "updated_at": datetime.now(timezone.utc)})
            return event
        except ProposalNotFound as exc:
            raise HTTPException(404, f"未知提案 {proposal_id}") from exc
        except UnconfirmedWrite as exc:
            raise HTTPException(422, str(exc)) from exc

    @implements("POST", "/students/{student_id}/memory/recall",
                response_model=MemoryRecallResult)
    def recall_memory(student_id: str, query: MemoryRecallQuery) -> MemoryRecallResult:
        """按当前任务召回最小上下文，不把完整人生记录塞进每次 Prompt。"""
        if query.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        return deps.memory.recall(query, now=datetime.now(timezone.utc))

    def _owned_memory(student_id: str, memory_id: str) -> MemoryEntry:
        entry = deps.memory.entries.get(memory_id)
        if entry is None or entry.student_id != student_id:
            # 别人的记忆对这个学生来说等于不存在——404 而不是 403，
            # 403 会泄露"这个 id 存在"这一事实
            raise HTTPException(404, {"error": "unknown_memory",
                                      "detail": f"未知记忆 {memory_id}"})
        return entry

    @implements("POST", "/students/{student_id}/memory/{memory_id}/correction",
                response_model=MemoryEntry)
    def correct_memory(student_id: str, memory_id: str,
                       correction: MemoryCorrection) -> MemoryEntry:
        """纠正 = 新条目取代旧条目，旧条目留痕（§8.6：不静默覆盖）。"""
        from campuspath_contracts.memory import MemoryOrigin
        from campuspath_state.store import MemoryLocked

        _known_student(student_id)
        old = _owned_memory(student_id, memory_id)
        if correction.memory_id != memory_id:
            raise HTTPException(422, "路径中的记忆与请求体不一致")
        corrected = MemoryEntry(
            memory_id=f"{memory_id}-corr-{deps.memory.next_sequence()}",
            student_id=student_id,
            type=old.type,
            origin=MemoryOrigin.STUDENT_STATEMENT,   # 纠正是学生原话
            content=correction.corrected_content,
            source_event_id=old.source_event_id,
            confidence=0.9,
            valid_from=datetime.now(timezone.utc),
            supersedes=memory_id,
        )
        try:
            deps.memory.write(corrected)
        except MemoryLocked as exc:
            raise HTTPException(409, {"error": "memory_locked",
                                      "detail": str(exc)}) from exc
        return corrected

    @implements("POST", "/students/{student_id}/memory/{memory_id}/lock",
                response_model=MemoryEntry)
    def lock_memory(student_id: str, memory_id: str) -> MemoryEntry:
        _known_student(student_id)
        _owned_memory(student_id, memory_id)
        return deps.memory.lock(memory_id)

    @implements("POST", "/students/{student_id}/memory/{memory_id}/forget",
                response_model=MemoryForgetReceipt)
    def forget_memory(student_id: str, memory_id: str) -> MemoryForgetReceipt:
        """忘记 = 真正移除；移除这件事本身留回执。

        **幂等**：忘记一条已经不存在的记忆同样成功——"它已经不在了"
        正是学生想要的终态，重复请求不该变成错误。
        属于别的学生的记忆仍是 404（对这个学生它等于不存在）。
        """
        _known_student(student_id)
        entry = deps.memory.entries.get(memory_id)
        if entry is not None:
            if entry.student_id != student_id:
                raise HTTPException(404, {"error": "unknown_memory",
                                          "detail": f"未知记忆 {memory_id}"})
            deps.memory.forget(memory_id)
        return MemoryForgetReceipt(
            memory_id=memory_id, student_id=student_id,
            forgotten_at=datetime.now(timezone.utc),
        )

    @implements("GET", "/students/{student_id}/export",
                response_model=StudentDataExport)
    def export_my_data(student_id: str) -> StudentDataExport:
        """设置页「导出我的数据」。只装**这个学生自己**可见域的记录。"""
        student = _known_student(student_id)
        return StudentDataExport(
            student_id=student_id,
            exported_at=datetime.now(timezone.utc),
            profile=student,
            evidence=tuple(e for e in deps.evidence if e.student_id == student_id),
            notes=tuple(n for n in deps.notes if n.student_id == student_id),
            experiences=tuple(
                e for e in deps.experiences if e.student_id == student_id),
            goals=tuple(deps.goals.get(student_id, ())),
            memory_entries=tuple(deps.memory.list_for(student_id)),
            reflections=tuple(deps.reflections.get(student_id, ())),
            proposals=tuple(_store(student_id).proposals()),
            course_records=tuple(deps.records.get(student_id, ())),
            availability=tuple(
                b for b in deps.availability if b.student_id == student_id),
            capacity_snapshots=tuple(deps.snapshots.get(student_id, ())),
            schedule_proposals=tuple(
                deps.schedule_proposals.get(student_id, ())),
            actions=tuple(deps.actions.get(student_id, ())),
            reminders=tuple(deps.reminders.get(student_id, ())),
            consents_on_record=tuple(
                c for c in deps.consents.values() if c.student_id == student_id),
        )

    @implements("POST", "/students/{student_id}/deletion-request",
                response_model=DeletionReceipt)
    def delete_my_data(student_id: str) -> DeletionReceipt:
        """删除我的数据。Demo 环境立即生效：进程内个人数据即刻清除。

        清完之后这个学生的一切端点都是 404——这不是故障，是删除的含义。
        **幂等**：对已删除（或从未存在）的 id 再次请求同样返回回执——
        回执只声明"这个 id 名下已无个人数据"，这在两种情况下都为真。
        """
        deps.students.pop(student_id, None)
        deps.stores.pop(student_id, None)
        deps.records.pop(student_id, None)
        deps.goals.pop(student_id, None)
        deps.snapshots.pop(student_id, None)
        deps.reflections.pop(student_id, None)
        deps.reminders.pop(student_id, None)
        deps.schedule_proposals.pop(student_id, None)
        deps.pathways.pop(student_id, None)
        deps.actions.pop(student_id, None)
        deps.evidence[:] = [e for e in deps.evidence if e.student_id != student_id]
        deps.notes[:] = [n for n in deps.notes if n.student_id != student_id]
        deps.experiences[:] = [
            e for e in deps.experiences if e.student_id != student_id]
        deps.proposals[:] = [
            p for p in deps.proposals if p.student_id != student_id]
        deps.availability[:] = [
            b for b in deps.availability if b.student_id != student_id]
        for memory_id in [e.memory_id for e in deps.memory.list_for(student_id)]:
            deps.memory.forget(memory_id)
        # 审查抓到的残留：同意记录与 outreach 队列也属于个人数据
        deps.consents = {
            k: c for k, c in deps.consents.items() if c.student_id != student_id
        }
        # 第二次审查（2026-08-01）又抓到四处——R8 新增状态没进删除清单：
        # tutor 干预台账（含 ISI/PSS 原始分，最敏感）、咨询预约（姓名/联系方式）、
        # 紧急通道计数、A0 编排痕迹、联系人
        deps.tutor_interventions[:] = [
            r for r in deps.tutor_interventions if r["student_id"] != student_id]
        deps.counseling_bookings[:] = [
            b for b in deps.counseling_bookings if b.student_id != student_id]
        deps.emergency_uses.pop(student_id, None)
        deps.agent_traces.pop(student_id, None)
        deps.contacts.pop(student_id, None)
        deps.outreach_queue[:] = [
            r for r in deps.outreach_queue if r.student_id != student_id
        ]
        return DeletionReceipt(
            student_id=student_id, requested_at=datetime.now(timezone.utc),
        )

    # ── Action & Consent：批准之前什么都不写 ────────────────────────
    @implements("POST", "/students/{student_id}/actions", response_model=ActionEvent)
    def record_action(student_id: str, event: ActionEvent) -> ActionEvent:
        """记录行动。**收藏会顺带写一条偏好记忆。**

        为什么收藏要进 Memory：学生反复收藏同一类机会，是他自己给出的
        偏好证据，比任何推断都硬。它写成 ``observed`` 权威级的条目——
        不是"我们猜你喜欢"，是"你收藏过 N 次"。学生随时能在记忆中心
        看到、纠正、锁定或删除它（D2）。
        """
        if event.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        _known_student(student_id)
        queue = deps.actions.setdefault(student_id, [])
        # 同一个 event_id 重复提交是覆盖：收藏按钮点两下不该出现两条记录
        queue[:] = [a for a in queue if a.event_id != event.event_id]
        queue.append(event)

        if event.action_type is ActionType.SAVE:
            from campuspath_state.store import MemoryLocked

            saved = [a for a in queue if a.action_type is ActionType.SAVE]
            try:
                deps.memory.write(MemoryEntry(
                    memory_id=f"MEM-{student_id}-saved-{event.subject_id}",
                    student_id=student_id,
                    type=MemoryType.PREFERENCE,
                    # 学生自己点的收藏 = 学生的陈述，不是系统推断。
                    # 这个区分决定了记忆中心里它显示成"你说过"还是"我们猜的"。
                    origin=MemoryOrigin.STUDENT_STATEMENT,
                    content=f"收藏了 {event.subject_id}（累计收藏 {len(saved)} 个机会）",
                    source_event_id=event.event_id,
                    confidence=1.0,
                    valid_from=event.timestamp,
                    # authority 恒为 advisory：记忆永远只是参考，
                    # 不能凌驾于 Rules 的判定之上。契约把它写死成 Literal。
                ))
            except MemoryLocked:
                # 学生锁定了这条收藏记忆 → 尊重锁，收藏动作本身照常记录
                pass

        if event.action_type is ActionType.UNSAVE:
            # 取消收藏 → 对应的偏好记忆一并移除；学生锁定过的除外（锁最大）
            memory_id = f"MEM-{student_id}-saved-{event.subject_id}"
            entry = deps.memory.entries.get(memory_id)
            if entry is not None and not entry.student_locked:
                deps.memory.forget(memory_id)
        return event

    @implements("GET", "/students/{student_id}/actions",
                response_model=list[ActionEvent])
    def list_actions(student_id: str) -> list[ActionEvent]:
        _known_student(student_id)
        return list(deps.actions.get(student_id, ()))

    @implements("POST", "/students/{student_id}/calendar-actions",
                response_model=CalendarAction)
    def write_calendar(student_id: str, action: CalendarAction) -> CalendarAction:
        """§15.4 规则 8：学生批准后才写日历。

        契约层已经要求 ``approval_receipt_id``；这里补一条**同意范围**检查——
        学生可能授权了读 free/busy 却没授权写。
        """
        from campuspath_contracts.profile import ConsentScope

        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        if action.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        if not student.has_consent(ConsentScope.CALENDAR_WRITE):
            raise HTTPException(403, {"error": "consent_missing",
                                      "detail": "学生未授权写入日历"})
        # 回执必须是服务端在批准时签发的，且属于这个学生（审查抓到的伪造洞：
        # 此前任何非空字符串都过闸）。写入内容还要能对上被批准预览里的某个时段。
        issued = deps.approval_receipts.get(action.approval_receipt_id or "")
        if issued is None or not issued.startswith(f"{student_id}:"):
            raise HTTPException(403, {"error": "unbacked_approval_receipt",
                                      "detail": "回执从未被签发或不属于该学生"})
        proposal_id = issued.split(":", 1)[1]
        approved = next(
            (p for p in deps.schedule_proposals.get(student_id, ())
             if p.proposal_id == proposal_id and p.student_decision == "approved"),
            None,
        )
        if approved is None:
            raise HTTPException(403, {"error": "unbacked_approval_receipt",
                                      "detail": "回执指向的预览不存在或未被批准"})
        if action.draft is not None and not any(
            slot.span == action.draft.span for slot in approved.proposed_slots
        ):
            raise HTTPException(422, {"error": "draft_not_in_approved_preview",
                                      "detail": "写入时段不在被批准的预览里"})
        # R4-M（2026-07-31）：写入成功 = 周日历上真的出现这一块。
        # 标题是学生批准写入的内容（CalendarWriteDraft.event_title），
        # 不是从谁的日历里采集来的——所以带完整活动名不碰 B5。
        if action.action == "create" and action.draft is not None:
            import re as _re
            oid_match = _re.search(r"(OPP-[A-Za-z0-9-]+)",
                                   action.action_id + " " + (action.idempotency_key or ""))
            block_id = (f"AB-{student_id}-plan-{oid_match.group(1)}"
                        if oid_match else f"AB-{student_id}-plan-{action.action_id}")
            # 用户裁定 B（2026-08-02）：带非阻断冲突批准的写入，日历块标 ⚠️
            soft_conflicts = any(
                not c.blocking for slot in approved.proposed_slots
                for c in slot.conflicts)
            event_title = action.draft.event_title
            if soft_conflicts and not event_title.startswith("⚠️"):
                event_title = f"⚠️ {event_title}"
            if not any(b.block_id == block_id for b in deps.availability):
                deps.availability.append(AvailabilityBlock(
                    block_id=block_id, student_id=student_id,
                    span=action.draft.span,
                    type=AvailabilityType.BUSY,
                    source=BlockSource.DERIVED,
                    detail_level=CalendarDetailLevel.EVENT_TITLES,
                    title=event_title,
                    privacy_level="student_defined",
                    reminder_minutes_before=action.draft.reminder_minutes_before,
                ))
                _rebuild_snapshot(student_id)
        return action

    @implements("POST", "/students/{student_id}/schedule-proposals",
                response_model=ScheduleProposal)
    def propose_schedule(student_id: str, proposal: ScheduleProposal) -> ScheduleProposal:
        """B2：含 blocking 冲突的排程不得进入 approved。

        契约层已经挡住"approved + blocking"这种对象；这里把它翻译成 409，
        让调用方知道是冲突而不是格式错误。
        """
        # **冲突由服务端算**。让前端自己报冲突，等于把"有没有撞车"
        # 交给最没资格判断的一层——它看不到保护区块的完整定义。
        proposal = _with_detected_conflicts(student_id, proposal)
        blocking = [c for slot in proposal.proposed_slots
                    for c in slot.conflicts if c.blocking]
        if blocking and proposal.student_decision == "approved":
            raise HTTPException(409, {"error": "protected_block_conflict",
                                      "detail": f"{len(blocking)} 项 blocking 冲突"})
        queue = deps.schedule_proposals.setdefault(student_id, [])
        # 同一个 proposal_id 重复提交是覆盖，不是排两条队——
        # 否则 Action Center 会给学生看到同一件事的两个版本。
        queue[:] = [p for p in queue if p.proposal_id != proposal.proposal_id]
        queue.append(proposal)
        if proposal.student_decision == "approved":
            # 学生刚刚批准的这份预览 = 回执的锚点。回执由**服务端**登记，
            # 日历写入时对照——客户端编一个 RCPT-xxx 字符串换不来写入权。
            deps.approval_receipts[f"RCPT-{proposal.proposal_id}"] = (
                f"{student_id}:{proposal.proposal_id}"
            )
            _absorb_approved_into_pathway(student_id, proposal)
        return proposal

    def _absorb_approved_into_pathway(student_id: str,
                                      proposal: ScheduleProposal) -> None:
        """R4-M（2026-07-31）：批准的活动进入 pathway。

        此前批准只发回执——课外活动规划读的是 pathway，于是学生批准了
        什么都看不见。吸收规则：从 proposal id 里认出机会 id，用与
        /matches 同一个 Rules 入口签发资格凭据（B8 不豁免），追加为
        accepted 的 opportunity 计划项。幂等：同 subject 不重复吸收。
        """
        import re as _re

        from campuspath_rules.eligibility import StudentEligibilityFacts
        from campuspath_rules.engine import RulesEngine
        from campuspath_rules.prerequisites import AcademicRecord

        match = _re.search(r"(OPP-[A-Za-z0-9-]+)", proposal.proposal_id)
        if match is None:
            for pid in proposal.plan_item_ids:
                match = _re.search(r"(OPP-[A-Za-z0-9-]+)", pid)
                if match:
                    break
        if match is None:
            return
        oid = match.group(1)
        opportunity = next(
            (o for o in deps.opportunities if o.opportunity_id == oid), None)
        if opportunity is None:
            return

        student = deps.students.get(student_id)
        if student is None:
            return
        # pathway 不存在就先造夹具，吸收进同一份数据源（四档跨度同源）
        found = deps.pathways.get(student_id)
        if found is None:
            from .demo_pathway import build_demo_pathway
            found = build_demo_pathway(deps, student_id)
            if found is None:
                return
        if any(i.subject_id == oid for i in found.plan_items):
            return                          # 幂等：已吸收过

        rows = deps.records.get(student_id, [])
        facts = StudentEligibilityFacts(
            student_id=student_id, year_level=student.year,
            program_id=student.program_id,
            academic=AcademicRecord(
                completed=frozenset(
                    r.course_id for r in rows
                    if r.status is CourseStatus.COMPLETED),
                grades={r.course_id: r.grade for r in rows if r.grade},
            ),
            has_visa_constraint=any(c.kind == "visa" for c in student.constraints),
            future_offerings=getattr(deps, "future_offerings", None),
        )
        engine = RulesEngine(registry=deps.validations)
        _outcome, validation = engine.validate_eligibility(
            opportunity, facts, deps.today, datetime.now(timezone.utc))
        from campuspath_contracts.validation import BACKING_VERDICTS
        if validation.verdict not in BACKING_VERDICTS:
            return                          # 判定背不了书就不进计划，不造假凭据

        slot = proposal.proposed_slots[0] if proposal.proposed_slots else None
        start = slot.span.start.date() if slot else deps.today
        end = slot.span.end.date() if slot else deps.today
        # 用户裁定 B（2026-08-02）：无视非阻断冲突仍批准 → 条目带 ⚠️ 标记，
        # 冲突事实跟着计划项走，不消失
        soft_conflicts = [c for s in proposal.proposed_slots
                          for c in s.conflicts if not c.blocking]
        title = (opportunity.title_localized
                 or LocalizedText(zh_Hans=opportunity.title, en=opportunity.title))
        assumptions = [LocalizedText(
            zh_Hans="由你在行动中心批准加入", en="Approved by you in the Action Center")]
        if soft_conflicts:
            title = LocalizedText(zh_Hans=f"⚠️ {title.zh_Hans}",
                                  en=f"⚠️ {title.en}")
            assumptions.append(LocalizedText(
                zh_Hans=f"批准时与 {len(soft_conflicts)} 个现有日程重叠（你已知悉并批准）",
                en=f"Approved despite {len(soft_conflicts)} overlapping "
                   "schedule item(s)"))
        item = PlanItem(
            plan_item_id=f"PI-{student_id}-{oid}",
            kind=PlanItemKind.OPPORTUNITY,
            subject_id=oid,
            title=title,
            date_range=DateRange(start=start, end=end),
            workload_hours=float(opportunity.workload_hours_total or 20.0),
            status=PlanItemStatus.ACCEPTED,
            assumptions=tuple(assumptions),
            validation_id=validation.validation_id,
        )
        deps.pathways[student_id] = found.model_copy(
            update={"plan_items": (*found.plan_items, item)})

    def _with_detected_conflicts(student_id: str, proposal: ScheduleProposal
                                 ) -> ScheduleProposal:
        """按学生的实际时段算冲突，重建 proposal。

        与保护区块重叠 → **blocking**：那是学生自己划下的睡眠/用餐/照护时间，
        静默排进去是 B2 明令禁止的。与普通忙碌重叠 → 提示但不阻断：
        课与讲座撞车，学生自己知道哪个能翘。
        """
        blocks = [b for b in deps.availability if b.student_id == student_id]
        slots = []
        for slot in proposal.proposed_slots:
            start, end = slot.span.start, slot.span.end
            conflicts = []
            for block in blocks:
                if block.span.start >= end or block.span.end <= start:
                    continue
                if block.type is AvailabilityType.PROTECTED:
                    conflicts.append(ScheduleConflict(
                        conflict_type="protected_block", blocking=True,
                        with_block_id=block.block_id,
                        detail=render_message("sched.protected_overlap",
                                              block=block.block_id),
                    ))
                elif block.type is AvailabilityType.BUSY:
                    conflicts.append(ScheduleConflict(
                        conflict_type="busy_overlap", blocking=False,
                        with_block_id=block.block_id,
                        detail=render_message("sched.busy_overlap",
                                              block=block.block_id),
                    ))
            slots.append(slot.model_copy(update={"conflicts": tuple(conflicts)}))
        return proposal.model_copy(update={"proposed_slots": tuple(slots)})

    @implements("POST", "/students/{student_id}/replan-preview",
                response_model=AffectedScope)
    def replan_preview(student_id: str, request: ReplanRequest) -> AffectedScope:
        """**只算，不动。**

        §16.9 的局部重排：学生自己加一个机会，只该动近期行动层，
        长期目标不受牵连。这里把"会动哪些"算出来交给学生看，
        真正要不要重排由他点了才发生——所以本端点没有任何写入。
        """
        from campuspath_monitor.replan import ChangeEvent, compute_scope

        _known_student(student_id)
        if request.student_id != student_id:
            raise HTTPException(422, "请求中的学生与路径不一致")
        pathway = deps.pathways.get(student_id) or current_pathway(student_id)
        event = ChangeEvent(
            event_id=request.request_id or f"RQ-{request.source}",
            student_id=student_id,
            trigger_type=request.trigger_type,
            subject_id=request.source, detected_at=request.detected_at,
        )
        # 每个计划项属于哪个时间尺度——**必须说清楚**，compute_scope 不接受省略：
        # 缺了它，"局部重排不波及长期目标"这条保护会静默失效。
        # 里程碑 id 形如 MS-<student>-<horizon>，是 pathway 里唯一记着这个的地方。
        horizon_of: dict[str, str] = {}
        for milestone in pathway.milestones:
            horizon = milestone.milestone_id.rsplit("-", 1)[-1]
            for item_id in milestone.plan_item_ids:
                horizon_of[item_id] = horizon
        for item in pathway.plan_items:
            horizon_of.setdefault(item.plan_item_id, "this_term")
        return compute_scope(event, pathway, horizon_of=horizon_of)

    @implements("GET", "/students/{student_id}/schedule-proposals",
                response_model=list[ScheduleProposal])
    def list_schedule_proposals(student_id: str) -> list[ScheduleProposal]:
        _known_student(student_id)
        return list(deps.schedule_proposals.get(student_id, ()))

    @implements("GET", "/students/{student_id}/wellbeing/reminders",
                response_model=list[WellbeingReminderEvent])
    def wellbeing_reminders(student_id: str) -> list[WellbeingReminderEvent]:
        """跑一次状态机，返回**至今为止**的提醒。

        §16.8.3 的两条不变式都由 composer 保证，这里只是把它接出来：

        * 还能靠自动重排消除的信号**不发提醒**——先交给 A5 出 Low-load 计划；
        * 最多两次。第三次不是"再提醒一下"，是 Alert Overload。

        文案来自 `templates.py` 的固定槽位，**零 LLM**：这条链路上
        一个模型都不会被调用，而免责声明因此 100% 出现，不靠谁记得说。
        """
        from campuspath_wellbeing.composer import compose_reminder, decide

        _known_student(student_id)
        signals = wellbeing_signals(student_id)
        history = deps.reminders.setdefault(student_id, [])
        now = datetime.now(timezone.utc)

        # A5 的 Low-load 试算（确定性算术，零 LLM——这条链路允许的唯一 LLM
        # 是 A5 生成替代计划本身，"能不能重排"是容量算术，不是语义判断）：
        # 只有当**全部**信号都是 capacity_overload、且把当前路径里可延期项
        # （非里程碑、未完成/未进行中）全部延后足以覆盖超载量时，才判 True。
        # 睡眠/恢复类信号不可能靠重排消除，掺一个就必须提醒。
        # 判 True 时必须同时生成一份可见的 Low-load 排程预览——
        # "系统替你自救了"而学生看不到任何东西，等于没自救。
        possible = False
        if signals and all(
            s.signal_type is WellbeingSignalType.CAPACITY_OVERLOAD for s in signals
        ):
            pathway = deps.pathways.get(student_id)
            snapshots = deps.snapshots.get(student_id, [])
            latest = max(snapshots, key=lambda s: s.period_start) if snapshots else None
            if pathway is not None and latest is not None:
                excess = max(0.0, -latest.discretionary_capacity_hours)
                deferrable = [
                    item for item in pathway.plan_items
                    if item.kind is not PlanItemKind.MILESTONE
                    and item.status in {PlanItemStatus.PROPOSED, PlanItemStatus.ACCEPTED}
                    and item.workload_hours > 0
                ]
                deferrable_hours = sum(item.workload_hours for item in deferrable)
                if excess > 0 and deferrable_hours >= excess:
                    possible = True
                    proposal_id = f"SCHED-LOWLOAD-{student_id}"
                    proposals = deps.schedule_proposals.setdefault(student_id, [])
                    if not any(p.proposal_id == proposal_id for p in proposals):
                        proposals.append(ScheduleProposal(
                            proposal_id=proposal_id,
                            student_id=student_id,
                            plan_item_ids=tuple(
                                item.plan_item_id for item in deferrable
                            ),
                            assumptions=(render_message(
                                "wellbeing.lowload_assumption",
                                hours=f"{deferrable_hours:.1f}",
                                excess=f"{excess:.1f}",
                            ),),
                        ))
        decision = decide(
            signals, auto_rescheduling_possible=possible,
            previous_reminders=history, now=now,
        )
        if decision.send and decision.reminder_number is not None:
            event, _template = compose_reminder(
                signals[0], reminder_number=decision.reminder_number,
                locale=Locale.ZH_HANS,
                has_standing_consent=any(
                    c.scope is ConsentScope.WELLBEING_OUTREACH and c.granted
                    for c in deps.students[student_id].consent
                ),
                now=now,
            )
            history.append(event)
        return list(history)

    # ── Wellbeing outreach：没有有效同意就不发 ──────────────────────
    @implements("POST", "/students/{student_id}/wellbeing/outreach",
                response_model=WellbeingOutreachRequest)
    def request_outreach(student_id: str, request: WellbeingOutreachRequest
                         ) -> WellbeingOutreachRequest:
        """B13：每封 outreach 可追溯到有效同意，字段在白名单内。"""
        from campuspath_wellbeing.composer import OutreachWithoutConsent, build_outreach

        if request.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        consent = deps.consents.get(request.consent_id)
        if consent is None:
            raise HTTPException(403, {"error": "consent_missing",
                                      "detail": f"未知同意 {request.consent_id}"})
        if not consent.is_valid_at(datetime.now(timezone.utc)):
            raise HTTPException(403, {"error": "consent_missing",
                                      "detail": "同意已撤销或已过期"})
        if consent.student_id != student_id:
            raise HTTPException(403, {"error": "consent_missing",
                                      "detail": "同意记录属于另一个学生"})
        deps.outreach_queue.append(request)
        return request

    @implements("GET", "/wellbeing/outreach-queue",
                response_model=list[WellbeingOutreachRequest])
    def outreach_queue() -> list[WellbeingOutreachRequest]:
        """Counseling 队列。RBAC 已经把 Career Center 角色挡在外面。"""
        return deps.outreach_queue

    # ── R8-3：三层心理干预（第二层预约 + 第三层紧急通道）──────────
    @implements("GET", "/wellbeing/counseling-admin/hours",
                response_model=CounselingHours)
    def get_counseling_hours() -> CounselingHours:
        return deps.counseling_hours

    @implements("POST", "/wellbeing/counseling-admin/hours",
                response_model=CounselingHours)
    def set_counseling_hours(hours: CounselingHours) -> CounselingHours:
        """校方设置工作时段——学生端可预约时段的**唯一来源**。

        审查修复：改时段不得静默孤儿化已有预约——"以为约上了其实没约上"
        在心理咨询这条链上代价太高。命中失效窗口的预约先处理再改。
        """
        previous = deps.counseling_hours
        deps.counseling_hours = hours.model_copy(
            update={"updated_at": datetime.now(timezone.utc)})
        surviving = {s.slot_id for s in _counseling_slots()}
        orphaned = [b.booking_id for b in deps.counseling_bookings
                    if b.slot_id not in surviving]
        if orphaned:
            deps.counseling_hours = previous
            raise HTTPException(409, {
                "error": "bookings_would_be_orphaned",
                "detail": "以下预约位于将被撤销的时段，先联系学生改约或取消："
                          + ", ".join(orphaned)})
        return deps.counseling_hours

    def _counseling_slots() -> list[CounselingSlot]:
        """从工作时段确定性生成未来 14 天的 slot；已订的标 booked。"""
        booked = {b.slot_id for b in deps.counseling_bookings}
        hours = deps.counseling_hours
        out: list[CounselingSlot] = []
        for offset in range(14):
            day = deps.today + timedelta(days=offset)
            for window in hours.windows:
                if day.weekday() != window.weekday:
                    continue
                sh, sm = (int(x) for x in window.start.split(":"))
                eh, em = (int(x) for x in window.end.split(":"))
                cursor = datetime(day.year, day.month, day.day, sh, sm,
                                  tzinfo=timezone.utc)
                window_end = datetime(day.year, day.month, day.day, eh, em,
                                      tzinfo=timezone.utc)
                step = timedelta(minutes=hours.slot_minutes)
                while cursor + step <= window_end:
                    slot_id = f"CS-{cursor:%Y%m%d-%H%M}"
                    out.append(CounselingSlot(
                        slot_id=slot_id, start=cursor, end=cursor + step,
                        booked=slot_id in booked))
                    cursor += step
        return out

    @implements("GET", "/wellbeing/counseling/slots",
                response_model=list[CounselingSlot])
    def counseling_slots() -> list[CounselingSlot]:
        """第二层分流的预约面。校方没开放的时间在这里物理上不存在。"""
        return _counseling_slots()

    @implements("POST", "/students/{student_id}/counseling-bookings",
                response_model=CounselingBooking)
    def book_counseling(student_id: str,
                        booking: CounselingBooking) -> CounselingBooking:
        """预约心理咨询。专业与年级由服务端从 Profile 回填（不可伪造）；
        姓名/班级/联系方式学生自填——给咨询室看的是这五项（R8-3）。"""
        student = _known_student(student_id)
        if booking.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        # 审查修复：booking_id 判重——同 id 双写会让咨询室队列无法定位记录
        if any(b.booking_id == booking.booking_id
               for b in deps.counseling_bookings):
            raise HTTPException(409, {
                "error": "duplicate_booking",
                "detail": f"预约 {booking.booking_id} 已存在"})
        slots = {s.slot_id: s for s in _counseling_slots()}
        slot = slots.get(booking.slot_id)
        if slot is None:
            raise HTTPException(404, {"error": "unknown_slot",
                                      "detail": f"未知时段 {booking.slot_id}"})
        if slot.booked:
            raise HTTPException(409, {"error": "slot_taken",
                                      "detail": "该时段已被预约，请换一个"})
        normalized = booking.model_copy(update={
            "program": student.program_id,
            "year": student.year,
            "created_at": datetime.now(timezone.utc),
        })
        deps.counseling_bookings.append(normalized)
        return normalized

    @implements("GET", "/wellbeing/counseling-admin/bookings",
                response_model=list[CounselingBooking])
    def counseling_booking_queue() -> list[CounselingBooking]:
        return deps.counseling_bookings

    #: 合成号码——demo 全站 Synthetic，真实部署换学校值班室配置
    _DUTY_PHONE = "+852 5555 0000（Synthetic 心理咨询室值班）"
    _CAMPUS_HOTLINE = "+852 5555 0001（Synthetic 校园 24h 热线）"

    @implements("POST", "/students/{student_id}/wellbeing/emergency",
                response_model=EmergencyAccessResult)
    def emergency_access(student_id: str) -> EmergencyAccessResult:
        """第三层：紧急红按钮——跳过一切排队，直连值班室电话。

        防滥用（用户裁定 2026-08-01）：每学期最多 2 次，第 3 次起拉黑
        一学期。安全底线：拒绝响应里**仍然带**校园热线号码——
        挡的是"跳过排队"的特权，不挡求助信息本身。
        """
        _known_student(student_id)
        used = deps.emergency_uses.get(student_id, 0)
        # 审查修复：被拒的按压不计数——计数器只记"真正用掉的直连次数"
        if used >= 2:
            raise HTTPException(403, {
                "error": "emergency_blacklisted",
                "detail": ("本学期紧急直连已用满 2 次，通道停用一学期。"
                           f"如需紧急求助请拨校园热线 {_CAMPUS_HOTLINE}，"
                           "或直接前往咨询室值班台。"),
            })
        deps.emergency_uses[student_id] = used + 1
        return EmergencyAccessResult(
            student_id=student_id,
            duty_phone=_DUTY_PHONE,
            uses_this_term=used + 1,
            blacklisted=False,
            note=LocalizedText(
                zh_Hans=("已为你直连心理咨询室值班负责人，请立即拨打上面的电话。"
                         "此通道跳过排队，每学期最多使用 2 次，请留给真正紧急的时刻。"),
                en=("Direct line to the counseling duty officer — call now. "
                    "This channel skips the queue and allows at most 2 uses "
                    "per term; keep it for real emergencies."),
            ),
        )

    # ── Publisher / Review ──────────────────────────────────────────
    @implements("POST", "/publisher/submissions", response_model=PublicationSubmission)
    def submit_publication(submission: PublicationSubmission) -> PublicationSubmission:
        """B7：越权投稿被拦截**且记录**。"""
        from campuspath_publishing.workflow import ScopeDenied

        # 审查修复（2026-08-01）：重投同 id 曾把**已裁决**的投稿悄悄打回队列，
        # 且 owner 来自请求体——别组织的 publisher 能顶掉别人的投稿。
        # 已存在的投稿：只有"退回修改"状态允许重投，且 owner 必须与存量一致。
        stored = deps.submissions.get(submission.submission_id)
        if stored is not None:
            if stored.owner_principal_id != submission.owner_principal_id:
                raise HTTPException(403, {
                    "error": "scope_violation",
                    "detail": "该投稿属于另一位投稿人，不能覆盖。"})
            # 未裁决状态下同主重放 = 幂等（原样返回存量，不重跑状态机）；
            # 已裁决的投稿只有"退回修改"允许重投，其余 409。
            if stored.status in {PublicationStatus.AUTO_CHECKED,
                                 PublicationStatus.IN_REVIEW}:
                return stored
            if stored.status is not PublicationStatus.CHANGES_REQUESTED:
                raise HTTPException(409, {
                    "error": "duplicate_submission",
                    "detail": f"投稿 {submission.submission_id} 已存在"
                              f"（状态 {stored.status.value}），不能重投覆盖。"})
        try:
            at = datetime.now(timezone.utc)
            submitted = deps.publishing.submit(submission, when=deps.today, at=at)
            # 提交即跑确定性 auto-check（零 LLM：契约校验在入口已过，
            # 这里只做状态推进），落在 auto_checked 等人裁决。
            assert_transition_allowed(submitted.status, PublicationStatus.AUTO_CHECKED)
            checked = submitted.model_copy(
                update={"status": PublicationStatus.AUTO_CHECKED})
            deps.submissions[checked.submission_id] = checked
            return checked
        except ScopeDenied as exc:
            raise HTTPException(403, {"error": "scope_violation",
                                      "detail": str(exc)}) from exc

    @implements("GET", "/publisher/submissions",
                response_model=list[PublicationSubmission])
    def my_submissions() -> list[PublicationSubmission]:
        """B13（旅程筛查发现的死角）：投稿人要能看到自己投稿的**当前状态**——
        「退回修改」若只存在于审核端，投稿人那边就是一条死路。
        demo 无 IdP，返回全部投稿（归属过滤随真实身份体系接入，
        与 advisor 归属绑定同一 backlog）。"""
        return list(deps.submissions.values())

    @implements("GET", "/review/submissions",
                response_model=list[PublicationSubmission])
    def review_queue() -> list[PublicationSubmission]:
        """R7-B：待裁决的投稿。RBAC（/v1/review/ 前缀）把 publisher 挡在外面：
        投稿人看不到别人的投稿，也看不到自己的进队列后长什么样。"""
        # submitted 在存储里不可达（提交即推进 auto_checked）——不列，
        # 免得队列口径与实际状态机对不上（审查指出）
        pending = {PublicationStatus.AUTO_CHECKED, PublicationStatus.IN_REVIEW}
        return [s for s in deps.submissions.values() if s.status in pending]

    @implements("POST", "/review/submissions/{submission_id}/decisions",
                response_model=ModerationDecision)
    def review_submission(submission_id: str, decision: ModerationDecision
                          ) -> ModerationDecision:
        """审核决定。裁决作用在**存着的投稿**上：状态机迁移非法时返回 409，
        而不是静默接受；投稿不存在返回 404，而不是假装裁了。"""
        from campuspath_contracts.publishing import TransitionNotAllowed
        from campuspath_publishing.workflow import ScopeDenied

        if decision.submission_id != submission_id:
            raise HTTPException(422, "路径中的投稿与请求体不一致")
        stored = deps.submissions.get(submission_id)
        if stored is None:
            raise HTTPException(404, {"error": "unknown_submission",
                                      "detail": f"未知投稿 {submission_id}"})
        at = datetime.now(timezone.utc)
        try:
            # auto_checked 不能直接 request_changes——审核人先把它领进
            # in_review（审核责任落到人头），三种裁决才全部合法。
            if stored.status is PublicationStatus.AUTO_CHECKED:
                assert_transition_allowed(stored.status, PublicationStatus.IN_REVIEW)
                stored = stored.model_copy(update={
                    "status": PublicationStatus.IN_REVIEW,
                    "current_reviewer_id": decision.reviewer_id,
                })
            updated = deps.publishing.apply_decision(stored, decision, at=at,
                                                     when=deps.today)
        except TransitionNotAllowed as exc:
            raise HTTPException(409, {"error": "invalid_transition",
                                      "detail": str(exc)}) from exc
        except ScopeDenied as exc:
            raise HTTPException(403, {"error": "scope_violation",
                                      "detail": str(exc)}) from exc
        deps.submissions[submission_id] = updated
        return decision

    # ── 为什么没推荐（资讯广场的解释）───────────────────────────────
    @implements("GET", "/catalog/opportunities/{opportunity_id}/why-not-recommended",
                response_model=EligibilityExplanation)
    def why_not_recommended(opportunity_id: str, student_id: str = Query(...)
                            ) -> EligibilityExplanation:
        """D1：可复现「AI 未推荐但学生主动发现」+「为什么没推荐？」。

        解释来自 Rules 的四态判定，**不是模型编的理由**——每条都带 validation_id。
        """
        from campuspath_rules.eligibility import StudentEligibilityFacts
        from campuspath_rules.engine import RulesEngine
        from campuspath_rules.prerequisites import AcademicRecord

        student = deps.students.get(student_id)
        if student is None:
            raise HTTPException(404, f"未知学生 {student_id}")
        opportunity = next(
            (o for o in deps.opportunities if o.opportunity_id == opportunity_id), None
        )
        if opportunity is None:
            raise HTTPException(404, f"未知机会 {opportunity_id}")

        rows = deps.records.get(student_id, [])
        facts = StudentEligibilityFacts(
            student_id=student_id, year_level=student.year,
            program_id=student.program_id,
            academic=AcademicRecord(
                completed=frozenset(
                    r.course_id for r in rows if r.status is CourseStatus.COMPLETED
                ),
                grades={r.course_id: r.grade for r in rows if r.grade},
            ),
            has_visa_constraint=any(c.kind == "visa" for c in student.constraints),
            future_offerings=deps.future_offerings,
        )
        engine = RulesEngine(registry=deps.validations)
        outcome, validation = engine.validate_eligibility(
            opportunity, facts, deps.today, datetime.now(timezone.utc)
        )
        return EligibilityExplanation(
            opportunity_id=opportunity_id, state=outcome.state,
            summary=LocalizedText(
                zh_Hans=f"当前状态：{_STATE_LABEL[outcome.state][0]}",
                en=f"Current state: {_STATE_LABEL[outcome.state][1]}",
            ),
            what_is_missing=tuple(outcome.reasons),
            when_reachable=(
                LocalizedText(
                    zh_Hans=f"预计 {outcome.next_eligibility_date} 可申请",
                    en=f"Reachable around {outcome.next_eligibility_date}",
                ) if outcome.next_eligibility_date else None
            ),
            validation_id=validation.validation_id,
        )

    # ── 资讯广场 ────────────────────────────────────────────────────
    @implements("GET", "/catalog/opportunities", response_model=list[Opportunity])
    def catalog(
        limit: int = Query(200, ge=1, le=1000),
        include_expired: bool = Query(
            False, description="是否连同已截止的一并返回（默认不返回）"
        ),
        view: str = Query(
            "live", description="live=在架（默认，排除结束超两月的归档）；archive=只看归档"
        ),
    ) -> list[Opportunity]:
        """广场展示全部审核通过的资源，**不依赖个性化排序**（D1）。

        已截止的默认**不在**返回里，但也没被删——``include_expired=true``
        可以取回，状态是 ``expired``。Spec 允许"过期但可作未来参考"，
        所以它们该能被找到；只是不该混在"现在可以报名"里，
        那会让整份目录看起来比实际新。

        D 批（2026-08-02）：活动结束 + 2 个月 = **归档视图**——从在架列表
        （学生与管理端默认视图）移除；``view=archive`` 取回（plaza-admin
        的 Archive 分页用）。派生判定不改物理存储，幂等可复现。
        """
        now = datetime.now(timezone.utc)
        rows = deps.opportunities + (
            deps.expired_opportunities + deps.withdrawn_opportunities
            if include_expired else []
        )
        if view == "archive":
            # 审查 #4：withdrawn 是管理动作产物，只在 include_expired（管理端
            # 监看口径）下拼入——普通学生的 archive 视图看不到已下架条目
            pool = deps.opportunities + deps.expired_opportunities + (
                deps.withdrawn_opportunities if include_expired else [])
            rows = [o for o in pool if _stats_frozen_at(o, now)]
        else:
            rows = [o for o in rows if not _stats_frozen_at(o, now)]
        return rows[:limit]

    @implements("PUT", "/catalog/opportunities/{opportunity_id}",
                response_model=Opportunity)
    def admin_edit_opportunity(opportunity_id: str,
                               edit: "OpportunityAdminEdit") -> Opportunity:
        """B10（用户裁定 2026-08-01）：批准后的生命周期管理——改期/改名/改链接。
        只改给了值的字段；model_copy 走重校验（common.py 覆写），改坏即 422。"""
        patch = {k: v for k, v in edit.model_dump().items() if v is not None}
        if "title" in patch:
            # 展示层优先读 title_localized——改了 title 不清掉旧双语值，
            # 界面会继续显示旧名（实测踩到）。清空后回落到新 title。
            patch["title_localized"] = None
        for pool in (deps.opportunities, deps.expired_opportunities):
            for index, opp in enumerate(pool):
                if opp.opportunity_id == opportunity_id:
                    edited = opp.model_copy(update={
                        **patch,
                        "last_verified_at": datetime.now(timezone.utc),
                    })
                    pool[index] = edited
                    return edited
        raise HTTPException(404, {"error": "unknown_opportunity",
                                  "detail": f"未知活动 {opportunity_id}"})

    @implements("DELETE", "/catalog/opportunities/{opportunity_id}",
                response_model=Opportunity)
    def admin_withdraw_opportunity(opportunity_id: str) -> Opportunity:
        """B10：下架（活动取消）。从广场默认目录移除、进下架档——
        不物理删除（状态机本有 withdrawn 态，include_expired 仍可审计到）。
        **幂等**：重复下架返回同一份存档（Plan §10.2 第 11 条：同一输入同一结果）。"""
        for opp in deps.withdrawn_opportunities:
            if opp.opportunity_id == opportunity_id:
                return opp
        for pool in (deps.opportunities, deps.expired_opportunities):
            for index, opp in enumerate(pool):
                if opp.opportunity_id == opportunity_id:
                    withdrawn = opp.model_copy(
                        update={"publication_status": "withdrawn"})
                    pool.pop(index)
                    deps.withdrawn_opportunities.append(withdrawn)
                    return withdrawn
        raise HTTPException(404, {"error": "unknown_opportunity",
                                  "detail": f"未知活动 {opportunity_id}"})

    # ── Rules：签发与回查凭据 ───────────────────────────────────────
    @implements("POST", "/rules/validate", response_model=ConstraintValidation)
    def validate(subject: SourceRef,
                 student_id: str | None = Query(None)) -> ConstraintValidation:
        """审查抓到的高危缺陷：此前这里忽略目录里的真实先修表达式，
        对任何课程都按「无先修」评估——COMP 2012 曾拿到一张真实签发的
        satisfied 凭据并能背书计划项（B8 被架空）。

        现在：表达式从目录取权威值；学业记录来自 `student_id`（可选），
        不传学生 = 空记录，先修课程只能得到 not_met / unknown，绝不凭空 satisfied。
        """
        from campuspath_rules.engine import RulesEngine
        from campuspath_rules.prerequisites import AcademicRecord

        engine = RulesEngine(registry=deps.validations)
        if subject.entity_type != "course":
            raise HTTPException(422, "当前只实现了课程先修校验；其余规则待 WP6 接入")
        course = deps.catalog.get(subject.entity_id)
        if course is None:
            raise HTTPException(404, f"未知课程 {subject.entity_id}")
        record = AcademicRecord()
        if student_id is not None:
            _known_student(student_id)
            rows = deps.records.get(student_id, [])
            record = AcademicRecord(
                completed=frozenset(
                    r.course_id for r in rows if r.status is CourseStatus.COMPLETED
                ),
                grades={r.course_id: r.grade for r in rows if r.grade},
            )
        return engine.validate_prerequisite(
            subject.entity_id, course.prerequisite_expression, record,
        )

    @implements("GET", "/rules/validations/{validation_id}",
                response_model=ConstraintValidation)
    def get_validation(validation_id: str) -> ConstraintValidation:
        found = deps.validations.get(validation_id)
        if found is None:
            raise HTTPException(404, {"error": "validation_not_found"})
        return found

    # ── B8 闸门 ─────────────────────────────────────────────────────
    @implements("POST", "/students/{student_id}/pathway", response_model=PathwayVersion)
    def submit_pathway(student_id: str, pathway: PathwayVersion) -> PathwayVersion:
        """Spec §8.9.3：API 层拒绝缺失、伪造或无法背书的 ``validation_id``。

        这是 B8 在**部署边界**上的落点。契约层保证字段存在且形状合法；
        这里保证它真的被 Rules 签发过、而且判定能用来背书。
        """
        if pathway.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        try:
            enforce_validation_binding(pathway, deps.validations)
        except UnbackedOutputError as exc:
            raise HTTPException(
                422, {"error": "unbacked_validation_id", "detail": str(exc)}
            ) from exc
        deps.pathways[student_id] = pathway
        return pathway

    @implements("GET", "/students/{student_id}/pathway", response_model=PathwayVersion)
    def current_pathway(student_id: str,
                        intensity: str = Query("balanced"),
                        ) -> PathwayVersion:
        """D1 的三个时间视图都读这一个对象，所以它们不可能互相矛盾。

        没有版本时返回 **404 而不是空路径**：空路径会被前端渲染成
        "你没什么要做的"，而真相是"A5 还没跑过"。
        """
        _known_student(student_id)
        found = deps.pathways.get(student_id)
        # 审计 E（2026-08-02）：A5 类本体接进线上路径——模型可用时优先真实
        # 生成（PathwayAgent.build_pathway 修复循环 + generate_course_plans
        # 三变体；取舍输入=matches 确定性分 + 记忆 advisory 摘要）；模型理由
        # 调用失败即回落夹具并如实标注——**拿不到模型就不冒充 A5**。
        # trigger 携带目标指纹：换目标 → 指纹变 → 下次读取自动重生成；
        # 已批准吸收的条目跨版本携带，不因重规划消失。
        if deps.model is not None:
            from campuspath_contracts.academic import CoursePlanVariant
            from .a5_pathway import build_a5_pathway, goal_fingerprint

            try:
                variant = CoursePlanVariant(intensity)
            except ValueError:
                raise HTTPException(422, {"error": "unknown_intensity",
                                          "detail": intensity})
            goals = deps.goals.get(student_id, ())
            fp = goal_fingerprint(goals) if goals else None
            expected_trigger = f"a5:{fp}:{variant.value}"
            stale = (found is None or found.trigger == "demo_fixture"
                     or (found.trigger.startswith("a5:")
                         and found.trigger != expected_trigger))
            # 审查 H3：失败负缓存——A5 生成失败（模型不可用等）后，同一
            # 目标指纹当日不再重试，否则每次 GET 都白烧 matches 理由 +
            # A5 两轮模型调用（GET 是最高频读端点）。
            failed_key = (student_id, expected_trigger)
            if (fp is not None and stale
                    and deps.a5_failed.get(failed_key) != date.today()):
                today = deps.today
                cached = deps.match_cache.get(student_id)
                try:
                    if cached and cached[0] == today:
                        matches = cached[1]
                    else:
                        matches = _compute_matches(student_id, 50)
                        # 审查 H3：算了就回写日缓存（此前只算不存，与
                        # /matches 端点行为不一致）
                        deps.match_cache[student_id] = (today, matches)
                except Exception:
                    matches = []
                memory_notes: tuple[str, ...] = ()
                try:
                    recall = deps.memory.recall(
                        MemoryRecallQuery(student_id=student_id,
                                          task_context="pathway planning",
                                          top_k=5),
                        now=datetime.now(timezone.utc))
                    memory_notes = tuple(
                        r.entry.content[:200] for r in recall.recalled
                        if not r.stale)
                except Exception:
                    memory_notes = ()
                approved_opps = {
                    m.group(0)
                    for p in deps.schedule_proposals.get(student_id, ())
                    if p.student_decision == "approved"
                    for m in (
                        re.search(r"OPP-.+$", x)
                        for x in (p.proposal_id, *p.plan_item_ids))
                    if m is not None}
                carry = tuple(
                    i for i in (found.plan_items if found else ())
                    if i.subject_id in approved_opps)
                built = None
                if matches:
                    # 读端点不许 500（与审查 M10 同一条纪律）：生成器内部
                    # 虽有防护，这里再兜一层——任何异常都回落夹具并计入
                    # 失败负缓存，否则每次 GET 重烧模型再炸一遍
                    # （2026-08-03 用户报障：y1s2 撞名炸出的正是这条路）
                    try:
                        built = build_a5_pathway(
                            deps, student_id, matches=matches, model=deps.model,
                            memory_notes=memory_notes, carry_over=carry,
                            version=(found.version + 1 if found else 1),
                            intensity=variant)
                    except Exception:
                        logging.getLogger("campuspath").exception(
                            "A5 生成抛出未预期异常，回落夹具 "
                            f"(student={student_id}, intensity={variant.value})")
                        built = None
                if built is not None:
                    # 审查 M10：B8 闸门是这条路上唯一可能抛出的调用——
                    # 凭据绑定对不上时回落夹具并留日志，读端点不许 500
                    try:
                        enforce_validation_binding(built, deps.validations)
                    except Exception:
                        logging.getLogger("campuspath").exception(
                            "A5 路径未过 B8 闸门，回落夹具")
                        built = None
                if built is not None:
                    deps.pathways[student_id] = built
                    found = built
                else:
                    deps.a5_failed[failed_key] = date.today()
        if found is None:
            # 演示夹具：确定性生成，凭据由 Rules 真实签发，trigger 标明来历。
            # 它同样要过 B8 闸门——自己都过不了闸门的演示数据没有演示价值。
            from .demo_pathway import build_demo_pathway

            fixture = build_demo_pathway(deps, student_id)
            if fixture is not None:
                enforce_validation_binding(fixture, deps.validations)
                deps.pathways[student_id] = fixture
                found = fixture
        if found is None:
            raise HTTPException(404, {"error": "no_pathway_version"})
        return _augment_pathway_with_intl(found, student_id)

    @implements("DELETE", "/students/{student_id}/pathway/items/{plan_item_id}",
                response_model=PathwayVersion)
    def decline_plan_item(student_id: str, plan_item_id: str) -> PathwayVersion:
        """「不参加」（2026-08-03 用户需求）：从规划移除该活动条目。

        四件事一次做完：①当前版本剔除条目与里程碑引用；②留 DECLINE
        审计事件（append-only）；③已写入的日历真实块（AB-…plan-<subject>）
        一并移除——日历上不能残留一个学生已声明不去的活动；④subject 记入
        拒绝名单，A5 重新生成与演示夹具都跳过它。学生反悔 = 回广场重新
        报名（走正常报名→批准链）。
        """
        _known_student(student_id)
        found = deps.pathways.get(student_id)
        item = next((i for i in (found.plan_items if found else ())
                     if i.plan_item_id == plan_item_id), None)
        if item is None:
            raise HTTPException(404, {"error": "unknown_plan_item",
                                      "detail": plan_item_id})
        subject = item.subject_id
        updated = found.model_copy(update={
            "plan_items": tuple(i for i in found.plan_items
                                if i.plan_item_id != plan_item_id),
            "milestones": tuple(
                m.model_copy(update={"plan_item_ids": tuple(
                    x for x in m.plan_item_ids if x != plan_item_id)})
                for m in found.milestones),
        })
        deps.pathways[student_id] = updated
        deps.declined.setdefault(student_id, set()).add(subject)
        deps.availability[:] = [
            b for b in deps.availability
            if not (b.student_id == student_id
                    and f"plan-{subject}" in b.block_id)]
        deps.actions.setdefault(student_id, []).append(ActionEvent(
            event_id=f"AE-DECLINE-{subject}-{deps.memory.next_sequence()}",
            student_id=student_id, action_type=ActionType.DECLINE,
            subject_id=subject, plan_item_id=plan_item_id,
            timestamp=datetime.now(timezone.utc),
        ))
        return _augment_pathway_with_intl(updated, student_id)

    def _augment_pathway_with_intl(pathway: PathwayVersion,
                                   student_id: str) -> PathwayVersion:
        """国际生准备/核实动作 → 规划四档（2026-08-02 修复批）。

        与 `_augment_with_intl`（拆解列）同一模式：**读时注入、不落缓存**——
        取消勾选后下次读取自然消失，缓存里的原始版本不被污染。
        每条 PlanItem 的凭据由 Rules 经 Pack 桥真实签发（B8 主体逐字对齐，
        kind=action）；日期为确定性推导，锚点与公式随行注明，零 LLM。
        """
        from campuspath_contracts.common import DateRange
        from campuspath_contracts.pathway import PlanItem, PlanItemKind
        from campuspath_rules.context_pack import issue_prep_item_validation
        from campuspath_rules.engine import RulesEngine

        profile = deps.students.get(student_id)
        if profile is None or profile.intl_context is None:
            return pathway
        evaluation = evaluate_intl_pack(profile)
        if not evaluation.consented:
            return pathway

        engine = RulesEngine(registry=deps.validations)
        now = datetime.now(timezone.utc)
        today = deps.today
        intl = profile.intl_context
        # 提前量锚点：优先「计划开始日期」（转换发生在入职/开学前），
        # 缺了退回证件到期日——两者都是学生自述的结构化字段，不猜。
        anchor = intl.intended_start_date or intl.permission_expiry_date
        review_note = (LocalizedText(
            zh_Hans="内容待人工政策复核，以复核后为准（不构成法律建议）",
            en="Pending human policy review; not legal advice"),
        ) if evaluation.review_required else ()

        def _official_guidance(text: str) -> tuple[LocalizedText, ...]:
            """找官方信息类动作 → 官方链接指引（2026-08-02 用户需求）。

            先查 Pack 内问答对照表（人工整理、链接与源注册表同源）；
            未命中再查广场政策卡（政策/官方通知两分类）；都没有就不写——
            **只给官方链接指引，不转述政策内容**（解读归人工复核，零 LLM）。
            """
            from campuspath_packs import match_official_answer

            answer = match_official_answer(text)
            if answer is not None:
                return tuple(
                    LocalizedText(
                        zh_Hans=f"官方指引：{link['title_zh']} → {link['url']}",
                        en=f"Official guidance: {link['title_en']} → {link['url']}",
                    ) for link in answer["links"][:3])
            # 广场政策卡回退：词面命中标题即回链官方原文
            words = {w for w in text.lower().replace("_", " ").split() if len(w) >= 3}
            for card in deps.opportunities:
                if card.type.value != "policy_update" or not card.official_url:
                    continue
                title = (card.title_localized.zh_Hans + " "
                         + card.title_localized.en).lower()
                if sum(1 for w in words if w in title) >= 2:
                    return (LocalizedText(
                        zh_Hans=f"官方指引（广场政策卡）：{card.title_localized.zh_Hans}"
                                f" → {card.official_url}",
                        en=f"Official guidance (policy card): {card.title_localized.en}"
                           f" → {card.official_url}"),)
            return ()

        def _mk(item_id: str, subject_id: str, title: LocalizedText,
                start, end) -> PlanItem:
            assumptions = review_note + _official_guidance(
                f"{subject_id} {title.zh_Hans} {title.en}")
            if end < start:
                # codex #5：目标日已过不许被悄悄改成未来——保留事实、显式标注
                assumptions = assumptions + (LocalizedText(
                    zh_Hans=f"原目标日 {end} 已过——列为需尽快处理并与相关部门确认",
                    en=f"Original target date {end} has passed — treat as "
                       "overdue and confirm with the relevant office"),)
                end = start
            validation = issue_prep_item_validation(
                engine, subject_id=subject_id, student_id=student_id,
                detail=title.zh_Hans, pack_digest=evaluation.pack_digest,
                pack_version=evaluation.pack_version, now=now,
            )
            return PlanItem(
                plan_item_id=item_id, kind=PlanItemKind.ACTION,
                subject_id=subject_id, title=title,
                date_range=DateRange(start=start, end=end),
                workload_hours=0.0,
                fallback=LocalizedText(
                    zh_Hans="未按期完成时：先与学校国际学生支持部门确认时间线",
                    en="If delayed: confirm the timeline with the "
                       "international student office first"),
                assumptions=assumptions,
                validation_id=validation.validation_id,
            )

        extra: list[PlanItem] = []
        week = timedelta(days=7)
        # codex #2：subject_id 前缀学生 id——B8 的主体校验只看 (kind, subject_id)，
        # 不带前缀时 A 学生的凭据能背书 B 学生同名动作的计划项
        for index, prep in enumerate(evaluation.preparation_actions):
            lead = prep.recommended_lead_time_days or 30
            due = (anchor - timedelta(days=0)) if anchor else today + timedelta(days=lead)
            start = max(today + timedelta(days=3),
                        due - timedelta(days=lead) - week)
            extra.append(_mk(
                f"PI-INTL-PREP-{index + 1}",
                f"{student_id}-{prep.preparation_action_id}"[:64],
                LocalizedText(
                    zh_Hans=f"{prep.title}（建议提前 {lead} 天）",
                    en=f"{prep.title} ({lead}d recommended lead)"),
                start, due))
        for index, missing in enumerate(evaluation.missing_information[:4]):
            extra.append(_mk(
                f"PI-INTL-VERIFY-{index + 1}",
                f"{student_id}-intl-verify-{missing}"[:64],
                LocalizedText(
                    zh_Hans=f"核实/补充信息：{missing}",
                    en=f"Verify or provide: {missing}"),
                today + timedelta(days=3), today + timedelta(days=30)))
        for index, constraint in enumerate(evaluation.constraints[:2]):
            extra.append(_mk(
                f"PI-INTL-CONFIRM-{index + 1}",
                f"{student_id}-intl-confirm-{index + 1}",
                LocalizedText(zh_Hans=constraint, en=constraint),  # 不猜译
                today + timedelta(days=3), today + timedelta(days=45)))
        if not extra:
            return pathway
        augmented = pathway.model_copy(update={
            "plan_items": pathway.plan_items + tuple(extra),
        })
        # 注入项同样要过 B8——自己签的凭据也要能被闸门背书，当场验证
        enforce_validation_binding(augmented, deps.validations)
        return augmented

    # ── 校方：只出聚合，不可下钻 ────────────────────────────────────
    @implements("GET", "/insights/resource-coverage",
                response_model=list[ResourceCoverageAggregate])
    def resource_coverage(
        cohort: str | None = Query(None, description="分组维度，如 school"),
    ) -> list[ResourceCoverageAggregate]:
        from campuspath_aggregation.aggregate import (
            aggregate_all_cells,
            aggregate_resource_coverage,
        )

        now = datetime.now(timezone.utc)
        period = deps.metric_tuples[0].period if deps.metric_tuples else "2026-27_FALL"
        if cohort:
            return aggregate_all_cells(
                deps.metric_tuples, period=period, scope="school",
                cohort_dimensions=(cohort,), computed_at=now,
            )
        return [
            aggregate_resource_coverage(
                deps.metric_tuples, period=period, scope="institution", computed_at=now,
            )
        ]

    @implements("GET", "/insights/event-quality",
                response_model=list[EventQualityAggregate])
    def event_quality() -> list[EventQualityAggregate]:
        from campuspath_aggregation.aggregate import aggregate_event_quality

        now = datetime.now(timezone.utc)
        series = sorted({f.series_id for f in deps.quality_feedback if f.series_id})
        return [
            aggregate_event_quality(
                deps.quality_feedback, series_id=s, now=now, aggregate_id=f"Q-{s}"
            )
            for s in series
        ]

    @implements("GET", "/ops/source-health", response_model=list[SourceHealth])
    def source_health() -> list[SourceHealth]:
        from campuspath_mock_campus.store import source_health as probe

        return probe(datetime.now(timezone.utc))

    # ── Demo 运行时控制（F1，2026-08-02 用户裁定）────────────────────
    # 顶栏一键启停 Vertex Agent Engine（按小时计费——按钮的意义就是
    # 演示前启动、演示完关闭）。实现 = 后台线程跑 infra/agent_engine.sh；
    # 环境没有脚本/adk（如云端容器）时 503 如实，不假装能控。

    def _runtime_script() -> Path | None:
        if deps.runtime_script_path != "auto":
            return deps.runtime_script_path  # type: ignore[return-value]
        script = Path(__file__).resolve().parents[3] / "infra" / "agent_engine.sh"
        return script if script.exists() else None

    def _runtime_probe() -> tuple[str, tuple[str, ...]]:
        """status 子命令 → (running|stopped|unknown, display_names)。

        **探测不到 ≠ 已停止**：云端容器没有 infra/adk 时引擎可能正在别处运行
        （2026-08-02 审计实锤：两个引擎运行中，这里却报 stopped，顶栏按钮说谎）。
        脚本缺失或执行失败一律 unknown，如实承认"本环境看不见"。
        """
        import subprocess

        def _rest_fallback() -> tuple[str, tuple[str, ...]]:
            rest = deps.runtime_rest_fn
            if rest is None and not os.environ.get("PYTEST_CURRENT_TEST"):
                rest = _runtime_rest_probe   # 生产默认真 REST；测试不触网
            if rest is None:
                return "unknown", ()
            try:
                names = tuple(rest())
            except Exception:
                return "unknown", ()
            return ("running" if names else "stopped"), names

        script = _runtime_script()
        if script is None:
            return _rest_fallback()
        try:
            probe = subprocess.run(
                ["bash", str(script), "status"], capture_output=True,
                text=True, timeout=60, cwd=script.parents[1],
            )
        except Exception:
            return _rest_fallback()
        if probe.returncode != 0:
            return _rest_fallback()
        names = tuple(line.strip()[2:] for line in probe.stdout.splitlines()
                      if line.strip().startswith("- "))
        return ("running" if names else "stopped"), names

    def _runtime_rest_probe() -> tuple[str, ...]:
        """云端回退（状态灯，2026-08-03）：用容器 ADC 直接列
        us-central1 的 ReasoningEngine——引擎在哪都看得见，顶栏
        绿灯 = 正在计费。任何失败抛出，由调用方如实归 unknown。"""
        import json as _json
        import urllib.request

        import google.auth
        import google.auth.transport.requests

        credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"])
        credentials.refresh(google.auth.transport.requests.Request())
        req = urllib.request.Request(
            f"https://us-central1-aiplatform.googleapis.com/v1beta1/"
            f"projects/{project}/locations/us-central1/reasoningEngines",
            headers={"Authorization": f"Bearer {credentials.token}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read())
        return tuple(e.get("displayName", e.get("name", ""))
                     for e in data.get("reasoningEngines", []))

    @implements("GET", "/ops/agent-runtime", response_model=AgentRuntimeStatus)
    def agent_runtime_status() -> AgentRuntimeStatus:
        now = datetime.now(timezone.utc)
        with deps.jobs_lock:
            job = deps.runtime_job
        if job is not None and job.state in ("starting", "stopping"):
            return job.model_copy(update={"checked_at": now})
        # 状态灯（2026-08-03）：探测可能要几十秒（脚本路径），而顶栏在
        # 30s 轮询——改 stale-while-revalidate：有缓存**立刻**返回，过期就
        # 起后台线程刷新（单飞），请求永不被慢探测阻塞；只有第一次冷启动
        # 同步探测一回。
        def _fresh_status() -> AgentRuntimeStatus:
            state, names = _runtime_probe()
            return AgentRuntimeStatus(
                state=state, runtimes=names,
                progress=100 if state == "running" else 0,
                checked_at=datetime.now(timezone.utc),
                error=job.error if job else None,
            )

        cached_at, cached = deps.runtime_status_cache
        if cached is None:
            status = _fresh_status()
            deps.runtime_status_cache = (status.checked_at, status)
            return status
        if (now - cached_at).total_seconds() >= 60 and not deps.runtime_refreshing:
            deps.runtime_refreshing = True

            def _revalidate() -> None:
                try:
                    fresh = _fresh_status()
                    deps.runtime_status_cache = (fresh.checked_at, fresh)
                finally:
                    deps.runtime_refreshing = False

            import threading
            threading.Thread(target=_revalidate, daemon=True).start()
        return cached.model_copy(update={"checked_at": now})

    @implements("POST", "/ops/agent-runtime", response_model=AgentRuntimeStatus)
    def agent_runtime_command(command: "AgentRuntimeCommand") -> AgentRuntimeStatus:
        import os as _os
        import subprocess

        # 护栏（2026-08-02）：测试进程里绝不触发真实启停——adk deploy 是
        # 按小时计费的真实云资源；曾出现引擎被意外重建的事故，成因待查，
        # 先把最大的暴露面（测试遍历端点）在类型层焊死。
        if _os.environ.get("PYTEST_CURRENT_TEST"):
            raise HTTPException(503, {
                "error": "runtime_control_unavailable",
                "detail": "测试环境禁用真实运行时启停",
            })
        script = _runtime_script()
        if script is None or not (script.parents[1] / ".venv" / "bin" / "adk").exists():
            raise HTTPException(503, {
                "error": "runtime_control_unavailable",
                "detail": "此环境没有 infra 脚本或 adk CLI（demo 控制只在本地演示机可用）",
            })
        now = datetime.now(timezone.utc)
        target = "starting" if command.action == "start" else "stopping"
        with deps.jobs_lock:
            job = deps.runtime_job
            if job is not None and job.state in ("starting", "stopping"):
                raise HTTPException(409, {"error": "runtime_transition_in_progress",
                                          "detail": job.state})
            job = AgentRuntimeStatus(
                state=target, progress=5,
                stage=LocalizedText(
                    zh_Hans="正在启动 Agent Engine（约 5–10 分钟/运行时）…"
                    if target == "starting" else "正在关闭并删除运行时…",
                    en="Starting Agent Engine (≈5–10 min per runtime)…"
                    if target == "starting" else "Stopping and deleting runtimes…",
                ),
                checked_at=now,
            )
            deps.runtime_job = job
            deps.runtime_status_cache = (datetime.min.replace(tzinfo=timezone.utc), None)

        def _run() -> None:
            def finish(**fields):
                with deps.jobs_lock:
                    deps.runtime_job = deps.runtime_job.model_copy(update={
                        **fields, "checked_at": datetime.now(timezone.utc)})
                    deps.runtime_status_cache = (
                        datetime.min.replace(tzinfo=timezone.utc), None)
            try:
                mode = "start" if target == "starting" else "stop"
                finish(progress=25)
                result = subprocess.run(
                    ["bash", str(script), mode], capture_output=True, text=True,
                    timeout=1800, cwd=script.parents[1],
                )
                if result.returncode != 0:
                    raise RuntimeError((result.stderr or result.stdout)[-300:])
                state, names = _runtime_probe()
                finish(state=state, runtimes=names,
                       progress=100, stage=None, error=None)
            except Exception as exc:
                # 失败如实：回到探测态并带错误说明
                state, names = _runtime_probe()
                finish(state=state, runtimes=names, progress=100,
                       stage=None, error=str(exc)[:300])

        import threading

        threading.Thread(target=_run, daemon=True).start()
        return deps.runtime_job

    # ── 官方信息源注册表（C，2026-08-02）────────────────────────────

    @implements("GET", "/ops/sources", response_model=list[RegisteredSource])
    def list_sources() -> list[RegisteredSource]:
        order = {"p0": 0, "p1": 1, "p2": 2}
        return sorted(
            deps.registered_sources.values(),
            key=lambda s: (order[s.priority], s.category.value, s.source_id),
        )

    def _publish_policy_card(source: RegisteredSource, excerpt: str, now: datetime) -> None:
        """政策源变更 → 「政策更新提醒卡」直发广场（用户裁定 G）。

        卡片只报「官方页面有更新」并回链原文——**不转述政策内容**，
        转述属于政策解读，归 Context Pack 的人工复核流程，不归抓取器。
        同一源同一天只发一张（id 带日期，重复刷新不刷屏）。
        """
        from campuspath_contracts.common import Provenance

        card_id = f"OPP-POL-{source.source_id}-{now:%Y%m%d}"
        if any(o.opportunity_id == card_id
               for o in [*deps.opportunities, *deps.expired_opportunities,
                         *deps.withdrawn_opportunities]):
            return   # 审查 #15：下架的当日政策卡不复活
        provenance = Provenance(
            source=source.source_id,
            source_url=source.url,
            retrieved_at=now,
            published_at=None,
            parser_version="policy-watch/1.0",
            evidence_snippet=excerpt[:200] or source.url,
            confidence=1.0,   # 「页面变了」是哈希实测，不是推断
        )
        deps.opportunities.append(Opportunity(
            opportunity_id=card_id,
            type="policy_update",
            title=f"政策页面更新：{source.name.zh_Hans}",
            organizer=source.name.zh_Hans,
            occurrence_id=None, series_id=None,
            category_tags=("policy",),
            requirement_categories=(), eligibility_rules=(),
            deadline=None, starts_at=None, ends_at=None,
            workload_hours_total=None, skills=(),
            official_url=source.url,
            source_id=source.source_id,
            provenance=provenance,
            publication_status=PublicationStatus.PUBLISHED,
            last_verified_at=now,
            title_localized=LocalizedText(
                zh_Hans=f"政策页面更新：{source.name.zh_Hans}",
                en=f"Policy page updated: {source.name.en}",
            ),
            organizer_localized=source.name,
            # 双政策分类（2026-08-02 修复批）：受众跟着 registry 的
            # policy_audience 走——all → policy（所有人可见），
            # intl / 未标注 → intl_policy（收敛默认：宁可少见，不放大受众）。
            organizer_category=(
                "policy" if source.policy_audience == "all" else "intl_policy"
            ),
        ))

    _EVENT_PARSER_MODULE: dict[str, object] = {}

    def _calendar_parser_module():
        """加载 seed/scrape_hkust_events.py 的解析器（复用同一套 HTML 解析，
        不复制代码）。脚本本体在仓库内，API 也只在仓库内跑——demo 口径。"""
        if "module" not in _EVENT_PARSER_MODULE:
            import importlib.util

            script = Path(__file__).resolve().parents[3] / "seed" / "scrape_hkust_events.py"
            spec = importlib.util.spec_from_file_location("hkust_events_scraper", script)
            module = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(module)
            _EVENT_PARSER_MODULE["module"] = module
        return _EVENT_PARSER_MODULE["module"]

    def _refresh_full_chain(source: RegisteredSource, now: datetime) -> int:
        """全链源（活动日历）：抓列表页 → 逐条解析 → 官方直发广场。

        用户裁定 A：能上学校官网的信息本身已被学校筛过一遍，
        HKUST 官方域名白名单内的条目**直接 Published**，不走人工审核队列。
        判重与既有目录按（标题, 主办方）精确比对；单语言来源不猜译名
        （campus_events.py 的三条纪律照旧）。
        """
        from campuspath_connector import fetcher as _f
        from campuspath_contracts.common import Provenance

        published = 0
        try:
            module = _calendar_parser_module()   # 审查 #9：加载失败不 500 整个请求
            # 审查 #8：基址取自注册表 source.url（白名单校验的就是它），
            # 不再用 seed 脚本里写死的域名
            origin = source.url.rstrip("/")
            if origin.endswith("/events"):
                origin = origin[: -len("/events")]
            html = _f.fetch(f"{origin}/events/recent")
        except Exception:
            return 0   # 列表页抓不到/解析器加载失败 → 只记变更，不硬造条目
        parser = module.EventListParser()
        parser.feed(html)
        parser.close()
        for event in parser.events:
            title = event.get("title")
            if not title:
                continue
            organizer = event.get("organizer", "HKUST")
            # 判重扫全部三个列表（审查 #15：只扫在架会让下架的当日复活）
            if any(o.title == title and o.organizer == organizer
                   for o in [*deps.opportunities, *deps.expired_opportunities,
                             *deps.withdrawn_opportunities]):
                continue
            # id = 内容哈希（审查 #2：位置序号在跨轮抓取时会碰撞——
            # 列表顶部新增一条，后面的条目全体换号，同 id 指向两个对象）
            import hashlib as _hl
            fingerprint = _hl.sha256(
                f"{source.source_id}|{event.get('path', title)}".encode("utf-8")
            ).hexdigest()[:12]
            provenance = Provenance(
                source=source.source_id,
                source_url=f"{origin}{event.get('path', '')}",
                retrieved_at=now,
                published_at=None,
                parser_version="calendar-live/1.0",
                evidence_snippet=title[:200],
                confidence=0.9,   # 结构化解析自官方列表页
            )
            deps.opportunities.append(Opportunity(
                opportunity_id=f"OPP-LIVE-{fingerprint}",
                type="event",
                title=title,
                organizer=organizer,
                occurrence_id=None, series_id=None,
                category_tags=(event.get("category", "event").lower().replace(" ", "_")[:40] or "event",),
                requirement_categories=(), eligibility_rules=(),
                deadline=None,   # 来源没给截止就是没有，不编（campus_events 纪律）
                starts_at=None, ends_at=None,
                workload_hours_total=None, skills=(),
                official_url=f"{origin}{event.get('path', '')}",
                source_id=source.source_id,
                provenance=provenance,
                publication_status=PublicationStatus.PUBLISHED,
                last_verified_at=now,
                title_localized=None,      # 单语言来源不猜译名
                organizer_localized=None,
                organizer_category="campus_official",
            ))
            published += 1
        return published

    # ── 活动数据闭环（D 批，2026-08-02）────────────────────────────
    # 学生四维匿名评分 → 实时统计上 plaza-admin；二维码真实签到；周期报告。
    # 隐私口径照旧：聚合载荷无 student_id，低于 MIN_CELL_N 抑制分数。

    _STATS_FREEZE_DAYS = 60   # 活动结束 + 2 个月停止统计并转归档视图

    def _event_end(o: Opportunity) -> datetime | None:
        return o.ends_at or o.starts_at or o.deadline

    def _stats_frozen_at(o: Opportunity, now: datetime) -> bool:
        end = _event_end(o)
        return end is not None and end + timedelta(days=_STATS_FREEZE_DAYS) < now

    def _checkin_token(opportunity_id: str) -> str:
        """HMAC(server_secret, opportunity_id)——审查 #1：旧版 sha256(常量盐+公开 id)
        可离线伪造，验证出勤会被灌水。secret 从环境注入（Cloud Run 走 Secret
        Manager）；未配置时每进程随机——token 重启会变，但 QR 每次都是现取的。"""
        import hashlib
        import hmac

        digest = hmac.new(deps.checkin_secret.encode("utf-8"),
                          opportunity_id.encode("utf-8"),
                          hashlib.sha256).hexdigest()
        return f"chk_{digest[:32]}"

    def _find_opportunity(opportunity_id: str) -> Opportunity | None:
        return next(
            (o for o in [*deps.opportunities, *deps.expired_opportunities,
                         *deps.withdrawn_opportunities]
             if o.opportunity_id == opportunity_id), None)

    @implements("GET", "/ops/opportunities/{opportunity_id}/checkin",
                response_model=EventCheckinInfo)
    def opportunity_checkin(opportunity_id: str,
                            request: Request) -> EventCheckinInfo:
        opportunity = _find_opportunity(opportunity_id)
        if opportunity is None:
            raise HTTPException(404, {"error": "unknown_opportunity",
                                      "detail": opportunity_id})
        # 审查 #5：publisher 只能取**投稿链路产物**的签到码（demo 的 RBAC 只有
        # 角色没有个体身份，先钉住"必须来自投稿"这半边；真实部署按
        # principal 归属校验——记待办）
        role = request.headers.get("X-CampusPath-Role", "")
        if role == "publisher" and not any(
            sub.content.opportunity_id == opportunity_id
            for sub in deps.submissions.values()
        ):
            raise HTTPException(403, {"error": "not_your_submission",
                                      "detail": "publisher 只能查看自己投稿活动的签到码"})
        token = _checkin_token(opportunity_id)
        now = datetime.now(timezone.utc)
        opens_on = opportunity.starts_at.date() if opportunity.starts_at else None
        return EventCheckinInfo(
            opportunity_id=opportunity_id,
            token=token,
            checkin_url=f"/checkin?opp={opportunity_id}&token={token}",
            attend_count=len(deps.attendance.get(opportunity_id, set())),
            stats_frozen=_stats_frozen_at(opportunity, now),
            opens_on=opens_on,
            counting_open=(opens_on is None or now.date() >= opens_on)
                          and not _stats_frozen_at(opportunity, now),
        )

    @implements("POST", "/students/{student_id}/checkin",
                response_model=CheckinResult)
    def student_checkin(student_id: str, request: CheckinRequest) -> CheckinResult:
        """扫码签到 = 真实参与的唯一登记口。token 不对 → 422（防口口相传刷签）。"""
        _known_student(student_id)
        opportunity = _find_opportunity(request.opportunity_id)
        if opportunity is None:
            raise HTTPException(404, {"error": "unknown_opportunity",
                                      "detail": request.opportunity_id})
        if request.token != _checkin_token(request.opportunity_id):
            raise HTTPException(422, {"error": "invalid_checkin_token",
                                      "detail": "签到码不匹配"})
        now = datetime.now(timezone.utc)
        if _stats_frozen_at(opportunity, now):
            raise HTTPException(409, {"error": "checkin_frozen",
                                      "detail": "活动结束超过两个月，签到已关闭"})
        if opportunity.starts_at is not None and now.date() < opportunity.starts_at.date():
            raise HTTPException(409, {"error": "checkin_not_open",
                                      "detail": "签到从活动开始当天起才开始计数"})
        roster = deps.attendance.setdefault(request.opportunity_id, set())
        already = student_id in roster
        roster.add(student_id)
        return CheckinResult(
            opportunity_id=request.opportunity_id,
            accepted=True, already_checked_in=already,
            attend_count=len(roster),
        )

    def _occurrence_summary(o: Opportunity, fb: list, now: datetime) -> "OccurrenceQualitySummary":
        from campuspath_aggregation.aggregate import aggregate_event_quality
        from campuspath_contracts.aggregation import MIN_CELL_N

        verified = [f for f in fb if f.verified_attendance]
        avg_overall = None
        favorable = None
        dimensions = ()
        fit_distribution = ()
        if len(verified) >= MIN_CELL_N:
            # 契合分布（2026-08-04 用户裁定上呈现层）：个人判断不折进
            # 质量分（§17.4），但分布是主办方的有效信号；与维度分同受
            # k-匿名阈值约束（契约 validator 双保险）
            from campuspath_contracts.publishing import FitShare
            fit_counts: dict = {}
            fit_total = 0
            for f in verified:
                for tag in f.fit_tags:
                    fit_counts[tag] = fit_counts.get(tag, 0) + 1
                    fit_total += 1
            if fit_total:
                fit_distribution = tuple(
                    FitShare(fit=tag, share=round(n / fit_total, 4))
                    for tag, n in sorted(fit_counts.items(),
                                         key=lambda kv: -kv[1]))
            # 审查 #12：均分与好评率统一用 verified 子集，与 data_notes 口径一致
            aggregate = aggregate_event_quality(
                verified, occurrence_id=o.occurrence_id or o.opportunity_id,
                now=now, aggregate_id=f"QLIVE-{o.opportunity_id}")
            dimensions = aggregate.dimensions
            if dimensions:
                avg_overall = round(
                    sum(d.weighted_score for d in dimensions) / len(dimensions), 2)
            per_fb_avg = [
                sum(r.rating for r in f.dimensions) / len(f.dimensions)
                for f in verified
            ]
            favorable = round(
                sum(1 for a in per_fb_avg if a >= 4) / len(per_fb_avg), 2)
        end = _event_end(o)
        return OccurrenceQualitySummary(
            opportunity_id=o.opportunity_id,
            feedback_n=len(fb), verified_n=len(verified),
            attend_count=len(deps.attendance.get(o.opportunity_id, set())),
            avg_overall=avg_overall, favorable_rate=favorable,
            dimensions=dimensions,
            fit_distribution=fit_distribution,
            stats_frozen=_stats_frozen_at(o, now),
            stats_until=(end + timedelta(days=_STATS_FREEZE_DAYS)) if end else None,
        )

    @implements("GET", "/ops/opportunities/quality-summary",
                response_model=list[OccurrenceQualitySummary])
    def quality_summary() -> list[OccurrenceQualitySummary]:
        now = datetime.now(timezone.utc)
        fb_by_occ: dict[str, list] = {}
        for f in deps.quality_feedback:
            fb_by_occ.setdefault(f.occurrence_id, []).append(f)
        rows = []
        for o in [*deps.opportunities, *deps.expired_opportunities]:
            fb = fb_by_occ.get(o.occurrence_id or o.opportunity_id, [])
            # 统计位常驻（2026-08-04 用户裁定）：零反馈零签到也返回行——
            # 0 是如实值，前端据此显示 0 + Insufficient；旧的整行跳过让
            # 校方广场的四维统计区在新实例上整块蒸发，像功能不存在。
            rows.append(_occurrence_summary(o, fb, now))
        return rows

    # ── 周期报告（仅 career_center_admin，RBAC 表由契约生成）──────────

    _REPORT_WINDOW_DAYS = {"weekly": 7, "monthly": 30, "term": 180, "year": 365}

    def _report_rows(pairs: dict[str, list], attend_of, label_of=None) -> tuple:
        from campuspath_contracts.aggregation import MIN_CELL_N
        from campuspath_contracts.publishing import ReportGroupRow

        rows = []
        for key, items in sorted(pairs.items()):
            fb = [f for _, fs in items for f in fs]
            verified = [f for f in fb if f.verified_attendance]
            avg = None
            favorable = None
            if len(verified) >= MIN_CELL_N:
                per = [sum(r.rating for r in f.dimensions) / len(f.dimensions)
                       for f in verified]
                avg = round(sum(per) / len(per), 2)
                favorable = round(sum(1 for a in per if a >= 4) / len(per), 2)
            rows.append(ReportGroupRow(
                key=key, label=label_of(key) if label_of else None,
                activities_n=len(items), feedback_n=len(fb),
                verified_n=len(verified),
                attend_count=sum(attend_of(o) for o, _ in items),
                avg_overall=avg, favorable_rate=favorable,
            ))
        rows.sort(key=lambda r: (-(r.avg_overall or 0), -r.feedback_n))
        return tuple(rows)

    def _build_quality_report(period: str, now: datetime) -> "QualityReport":
        from campuspath_contracts.publishing import QualityReport, ReportPeriod

        window = timedelta(days=_REPORT_WINDOW_DAYS[period])
        start = now - window
        fb_in_window = [f for f in deps.quality_feedback
                        if start <= f.submitted_at <= now]
        fb_by_occ: dict[str, list] = {}
        for f in fb_in_window:
            fb_by_occ.setdefault(f.occurrence_id, []).append(f)
        activities = [
            (o, fb_by_occ.get(o.occurrence_id or o.opportunity_id, []))
            for o in [*deps.opportunities, *deps.expired_opportunities]
            if fb_by_occ.get(o.occurrence_id or o.opportunity_id)
        ]
        attend_of = lambda o: len(deps.attendance.get(o.opportunity_id, set()))  # noqa: E731

        by_org: dict[str, list] = {}
        by_type: dict[str, list] = {}
        for o, fb in activities:
            by_org.setdefault(
                o.organizer_category.value if o.organizer_category else "uncategorized",
                []).append((o, fb))
            by_type.setdefault(o.type.value, []).append((o, fb))
        # 专业分组走 cohort_dims.school（粗粒度，B10 口径不破）
        by_school_fb: dict[str, list] = {}
        for f in fb_in_window:
            by_school_fb.setdefault(f.cohort_dims.school, []).append(f)
        # 审查 #11：按学院的活动数=去重 occurrence 数；签到无法按学院归因 → None
        by_school = tuple(
            row.model_copy(update={
                "activities_n": len({f.occurrence_id for f in by_school_fb[row.key]}),
                "attend_count": None,
            })
            for row in _report_rows(
                {k: [(None, v)] for k, v in by_school_fb.items()},
                attend_of=lambda o: 0)
        )
        top = _report_rows(
            {o.opportunity_id: [(o, fb)] for o, fb in activities},
            attend_of=attend_of,
            label_of=lambda oid: LocalizedText(
                zh_Hans=next(o.title for o, _ in activities if o.opportunity_id == oid)[:80],
                en=next(o.title for o, _ in activities if o.opportunity_id == oid)[:80]),
        )[:10]

        # 供给缺口（确定性检出）：本窗口零反馈的主办方类别
        all_categories = {c.value for c in OrganizerCategory} - {"policy", "intl_policy"}
        gaps = tuple(
            LocalizedText(
                zh_Hans=f"「{cat}」类主办方本周期内没有任何获得反馈的活动——供给或触达可能存在缺口",
                en=f"Organizer category '{cat}' produced no activities with feedback this period",
            )
            for cat in sorted(all_categories - set(by_org))
        )[:4]

        report = QualityReport(
            report_id=f"QR-{period}-{now:%Y%m%d%H%M%S}",
            period=ReportPeriod(period),
            window_start=start.date(), window_end=now.date(),
            generated_at=now,
            activities_total=len(activities),
            feedback_total=len(fb_in_window),
            verified_total=sum(1 for f in fb_in_window if f.verified_attendance),
            attend_total=sum(attend_of(o) for o, _ in activities),
            by_organizer=_report_rows(by_org, attend_of),
            by_type=_report_rows(by_type, attend_of),
            by_school=by_school,
            top_activities=top,
            coverage_gaps=gaps,
            data_notes=(
                LocalizedText(
                    zh_Hans="低于样本阈值的分组不显示分数（Insufficient evidence）；"
                            "好评率分母只算扫码验证的真实参与者；活动结束超两月停止统计",
                    en="Groups below the sample threshold show no scores; favorable "
                       "rate counts verified attendees only; stats freeze 2 months "
                       "after an event ends",
                ),
            ),
        )
        # 模型叙事：输入只有本报告的聚合 JSON（无任何个体数据）。无后端→如实为 None
        if deps.model is not None:
            try:
                from campuspath_agents.model import ModelRequest

                raw = deps.model.generate(ModelRequest(
                    purpose=f"quality-report:{period}",
                    system=(
                        "你是高校 Career Center 的数据分析师。基于给定的活动反馈聚合"
                        "统计（无个人数据），用 4-6 句话给校方管理者写结论：哪些类型/"
                        "主办方的活动更受欢迎、哪里可能有资源缺口值得查缺补漏、哪些高"
                        "质量活动值得资源倾斜。只依据给定数字，不编造。先输出中文段，"
                        "再输出 <EN> 标记后的英文段。"
                    ),
                    data=(report.model_dump_json(exclude={"narrative"}),),
                ))
                zh, _, en = raw.partition("<EN>")
                if zh.strip():
                    report = report.model_copy(update={"narrative": LocalizedText(
                        zh_Hans=zh.strip()[:2000],
                        en=(en.strip() or zh.strip())[:2000])})
            except Exception:
                pass   # 叙事失败不拖垮统计——报告照出，叙事为 None
        if report.narrative is None:
            report = report.model_copy(update={"data_notes": report.data_notes + (
                LocalizedText(zh_Hans="本次未生成 AI 叙事（模型后端不可用或调用失败）",
                              en="No AI narrative this run (model backend unavailable)"),
            )})
        return report

    @implements("POST", "/ops/quality-reports/{period}",
                response_model=QualityReportJob)
    def start_quality_report(period: str) -> QualityReportJob:
        from campuspath_contracts.publishing import ReportPeriod

        if period not in _REPORT_WINDOW_DAYS:
            raise HTTPException(404, {"error": "unknown_period", "detail": period})
        now = datetime.now(timezone.utc)
        with deps.jobs_lock:   # 审查 #7：查状态与建 job 原子化
            existing = deps.report_jobs.get(period)
            if existing is not None and existing.state == "running":
                raise HTTPException(409, {"error": "report_already_running",
                                          "detail": existing.job_id})
            job = QualityReportJob(
            job_id=f"QRJOB-{period}-{int(now.timestamp())}",
            period=ReportPeriod(period), state="running", progress=10,
            stage=LocalizedText(zh_Hans="汇总周期内反馈…",
                                en="Collecting feedback in window…"),
                started_at=now,
            )
            deps.report_jobs[period] = job

        def _run() -> None:
            def update(**fields):
                with deps.jobs_lock:
                    deps.report_jobs[period] = deps.report_jobs[period].model_copy(
                        update=fields)
            try:
                update(progress=45, stage=LocalizedText(
                    zh_Hans="分组统计与抑制检查…", en="Grouping and suppression…"))
                report = _build_quality_report(period, datetime.now(timezone.utc))
                update(progress=90, stage=LocalizedText(
                    zh_Hans="生成叙事结论…", en="Writing the narrative…"))
                update(state="done", progress=100, report=report,
                       finished_at=datetime.now(timezone.utc),
                       stage=LocalizedText(zh_Hans="完成", en="Done"))
            except Exception as exc:
                update(state="failed", progress=100, error=str(exc)[:300],
                       finished_at=datetime.now(timezone.utc),
                       stage=LocalizedText(zh_Hans="生成失败", en="Failed"))

        import threading

        threading.Thread(target=_run, daemon=True).start()
        return job

    @implements("GET", "/ops/quality-reports/{period}",
                response_model=QualityReportJob)
    def quality_report_status(period: str) -> QualityReportJob:
        job = deps.report_jobs.get(period)
        if job is None:
            raise HTTPException(404, {"error": "no_report_job",
                                      "detail": f"{period} 尚未生成过报告"})
        return job

    @implements("POST", "/ops/sources/{source_id}/refresh", response_model=RegisteredSource)
    def refresh_source(source_id: str) -> RegisteredSource:
        source = deps.registered_sources.get(source_id)
        if source is None:
            raise HTTPException(404, {"error": "unknown_source", "detail": source_id})
        if source.status != "active":
            raise HTTPException(409, {"error": "source_paused", "detail": source_id})
        return _do_refresh_source(source)

    def _do_refresh_source(source: RegisteredSource) -> RegisteredSource:
        """单源刷新核心：逐源端点与「一键巡检」共用同一条路径。"""
        source_id = source.source_id
        now = datetime.now(timezone.utc)
        if not source.is_real_fetch:
            # mock 源没有可抓的网页——只登记核查时间，不假装抓取（用户裁定 D）
            updated = source.model_copy(update={"last_checked_at": now})
            deps.registered_sources[source_id] = updated
            deps.source_fetch_status[source_id] = "unknown"
            return updated
        result = deps.probe_fn(source.url, source.content_hash)
        update: dict = {"last_checked_at": now}
        if result.outcome == "error":
            deps.source_fetch_status[source_id] = "unreachable"
            update["last_fetch_status"] = "unreachable"
        else:
            deps.source_fetch_status[source_id] = "ok"
            update["last_fetch_status"] = "ok"
            update["content_hash"] = result.new_hash
            if result.outcome == "changed":
                update["last_changed_at"] = now
        updated = source.model_copy(update=update)
        deps.registered_sources[source_id] = updated
        if result.outcome == "changed":
            if updated.kind is SourceKind.POLICY_SOURCE:
                _publish_policy_card(updated, result.text_excerpt or "", now)
            elif (updated.opportunity_bearing and updated.official_hkust
                  and updated.extraction_depth == "full_chain"):
                extracted = _refresh_full_chain(updated, now)
                # 审查 #13：抽取计数可观测——changed 但 0 条 = 解析器可能被
                # 上游改版打断，console 据此显形
                updated = updated.model_copy(update={
                    "last_extracted_count": extracted})
                deps.registered_sources[source_id] = updated
        return updated

    @implements("POST", "/ops/sources/refresh-all", response_model=SourcesSweepJob)
    def start_sources_sweep() -> SourcesSweepJob:
        """一键巡检（2026-08-02 用户需求 C）：后台线程逐源真实抓取。

        进度 = done/total 确定性计数；同一时间只允许一个巡检（409）；
        单源失败计入 errors 不中断整轮（与每日 Job 同口径，≤ 全量的失败照单报告）。
        """
        import threading
        import time as _time

        now = datetime.now(timezone.utc)
        targets = [s.source_id for s in deps.registered_sources.values()
                   if s.is_real_fetch and s.status == "active"]
        with deps.jobs_lock:
            existing = deps.sweep_job
            if existing is not None and existing.state == "running":
                raise HTTPException(409, {"error": "sweep_already_running",
                                          "detail": existing.job_id})
            job = SourcesSweepJob(
                job_id=f"SWEEP-{int(now.timestamp())}", state="running",
                total=len(targets), done=0, changed=0, errors=0, started_at=now,
            )
            deps.sweep_job = job

        def _update(**fields):
            with deps.jobs_lock:
                deps.sweep_job = deps.sweep_job.model_copy(update=fields)

        def _run() -> None:
            done = changed = errors = 0
            try:
                for source_id in targets:
                    source = deps.registered_sources.get(source_id)
                    if source is None or source.status != "active":
                        done += 1
                        continue
                    before = source.last_changed_at
                    try:
                        after = _do_refresh_source(source)
                        if after.last_fetch_status == "unreachable":
                            errors += 1
                        elif after.last_changed_at != before:
                            changed += 1
                    except Exception:
                        errors += 1
                    done += 1
                    _update(done=done, changed=changed, errors=errors)
                    if _SWEEP_DELAY:   # 礼貌间隔（fetcher 内部另有同域名间隔）
                        _time.sleep(_SWEEP_DELAY)
                _update(state="done", finished_at=datetime.now(timezone.utc))
            except Exception as exc:   # pragma: no cover - 兜底
                _update(state="failed", error=str(exc)[:300],
                        finished_at=datetime.now(timezone.utc))

        threading.Thread(target=_run, daemon=True).start()
        return job

    @implements("GET", "/ops/sources/refresh-all", response_model=SourcesSweepJob)
    def sources_sweep_status() -> SourcesSweepJob:
        job = deps.sweep_job
        if job is None:
            raise HTTPException(404, {"error": "no_sweep_job",
                                      "detail": "尚未发起过一键巡检"})
        return job

    # ── 依赖模型的端点：有后端就跑，没有就 503 ──────────────────────
    def _require_model():
        if deps.model is None:
            raise HTTPException(503, {
                "error": "model_backend_unavailable",
                "detail": (
                    "本端点需要模型后端。配好 Vertex（见 .env.example）并提供 ADC 后可用。"
                    "这不是「未实现」——结构与契约已就位，缺的是运行时依赖。"
                ),
            })
        return deps.model

    #: 签证/工作许可真正相关的机会类型——讲座、工作坊这类校内公开活动
    #: 通常不涉身份限制，发布方又没标注时**不硬贴注记**（治"每张卡一句废话"）。
    _VISA_SENSITIVE_TYPES = frozenset(
        {"internship", "job", "research_position", "mentorship"})

    def _intl_match_notes(opportunity, evaluation, today) -> tuple:
        """逐机会国际生注记：只从该机会自己的字段 + Pack 信封确定性派生。

        三态如实：True/False 转述发布方标注；None 且属签证敏感类型 →
        "未标注，建议确认"（缺就是缺，不猜）。提前量注记用**这个机会的**
        开始日期对齐 Pack 准备动作，逐卡数字不同。零 LLM。
        """
        if opportunity.type.value == "policy_update":
            return ()
        notes: list[LocalizedText] = []
        accepts = opportunity.accepts_international.value
        visa_sensitive = opportunity.type.value in _VISA_SENSITIVE_TYPES
        # 资格三态永远排第一（codex #4：担保/语言注记不构成资格证据，
        # 不许把「未标注」警示挤没或挤出前三条）
        if accepts == "accepts":
            notes.append(LocalizedText(
                zh_Hans="发布方标注：接受国际学生",
                en="Marked by publisher: accepts international students"))
        elif accepts == "not_accepted":
            notes.append(LocalizedText(
                zh_Hans="发布方标注：不面向国际学生",
                en="Marked by publisher: not open to international students"))
        elif visa_sensitive:   # unknown × 签证敏感类型
            notes.append(LocalizedText(
                zh_Hans="发布方未标注是否面向国际学生——建议报名前向主办方确认",
                en="Publisher did not mark international eligibility — "
                   "confirm with the organizer before applying"))
        if opportunity.sponsorship_support is not None:
            notes.append(LocalizedText(
                zh_Hans=f"工作担保：{opportunity.sponsorship_support.zh_Hans}",
                en=f"Sponsorship: {opportunity.sponsorship_support.en}"))
        if opportunity.language_requirements:
            joined_zh = "、".join(
                l.zh_Hans for l in opportunity.language_requirements[:3])
            joined_en = ", ".join(
                l.en for l in opportunity.language_requirements[:3])
            notes.append(LocalizedText(
                zh_Hans=f"语言要求：{joined_zh}", en=f"Language: {joined_en}"))
        if visa_sensitive and opportunity.starts_at is not None:
            days = (opportunity.starts_at.date() - today).days
            for prep in evaluation.preparation_actions:
                lead = prep.recommended_lead_time_days
                if not lead:
                    continue
                if days >= lead:
                    notes.append(LocalizedText(
                        zh_Hans=(f"距开始还有 {days} 天，可先完成"
                                 f"「{prep.title}」（建议提前 {lead} 天）"),
                        en=(f"{days}d before start — time to finish "
                            f"“{prep.title}” ({lead}d recommended lead)")))
                elif days >= 0:
                    notes.append(LocalizedText(
                        zh_Hans=(f"距开始仅 {days} 天，短于「{prep.title}」"
                                 f"的建议提前量 {lead} 天"),
                        en=(f"Only {days}d before start — under the {lead}d "
                            f"recommended lead for “{prep.title}”")))
                break
        return tuple(notes[:3])

    def _compute_matches(student_id: str, limit: int) -> list[MatchResult]:
        """A5 是唯一排序者。资格来自 Rules 且带 validation_id（B8）。

        分工见 `matching.py`：**资格判定零模型**，模型只写理由文案。
        分数是确定性加权和，因此固定 Seed 刷新两次结果一致（D6.7）。
        """
        from campuspath_rules.eligibility import StudentEligibilityFacts
        from campuspath_rules.engine import RulesEngine
        from campuspath_rules.prerequisites import AcademicRecord

        from .matching import (
            build_match, personal_fit_modifier, score_breakdown, weighted_score)

        # 排序与资格判定**零模型**（确定性加权和 + Rules 凭据）；模型只写理由文案，
        # 且 _match_rationale 自带失败兜底。没有后端时照常出排序结果、理由为空——
        # 让一次模型不可用带走整个 For You 页面是不可接受的。
        model = deps.model
        student = _known_student(student_id)

        rows = deps.records.get(student_id, [])
        facts = StudentEligibilityFacts(
            student_id=student_id, year_level=student.year,
            program_id=student.program_id,
            academic=AcademicRecord(
                completed=frozenset(
                    r.course_id for r in rows if r.status is CourseStatus.COMPLETED
                ),
                grades={r.course_id: r.grade for r in rows if r.grade},
            ),
            has_visa_constraint=any(c.kind == "visa" for c in student.constraints),
            future_offerings=deps.future_offerings,
        )
        interests = frozenset(i.lower() for i in student.interests)
        open_categories = frozenset(
            c.value for c in RequirementCategory
        )  # 无 RequirementGraph 时不假装知道哪些类别已关闭（A3 接入后收窄）
        weekly = student.energy_profile.weekly_discretionary_hours
        engine = RulesEngine(registry=deps.validations)
        now = datetime.now(timezone.utc)

        # ── 反思闭环回流（审计黄-8/B 缺口，2026-08-02）────────────────
        # 全体维度：匿名四维评分按活动聚合（样本 ≥3 才生效，与聚合抑制
        # 阈值同口径）→ 第六维；个人维度：学生自己反思的 fit_tag 按类别
        # 修正偏好维。两者全确定性、零模型。
        from campuspath_contracts.aggregation import MIN_CELL_N

        quality_sum: dict[str, list[float]] = {}
        for fb in deps.quality_feedback:
            ratings = [r.rating for r in fb.dimensions]
            if ratings:
                quality_sum.setdefault(fb.occurrence_id, []).append(
                    sum(ratings) / len(ratings))

        def _quality_of(opportunity) -> float | None:
            key = opportunity.occurrence_id or opportunity.opportunity_id
            samples = quality_sum.get(key, [])
            # 审查 H2：阈值必须与聚合抑制同一出处（MIN_CELL_N=5），
            # 不许在推荐路径开一条更小样本的旁路
            if len(samples) < MIN_CELL_N:
                return None
            return (sum(samples) / len(samples) - 1.0) / 4.0   # 1–5 → 0–1

        categories_of = {o.opportunity_id: tuple(o.category_tags)
                         for o in deps.opportunities}
        my_reflections = deps.reflections.get(student_id, [])

        scored = []
        for opportunity in deps.opportunities:
            outcome, validation = engine.validate_eligibility(
                opportunity, facts, deps.today, now
            )
            breakdown = score_breakdown(
                opportunity, interest_tags=interests,
                open_requirement_categories=open_categories,
                weekly_capacity_hours=weekly, today=deps.today,
                quality_score=_quality_of(opportunity),
            )
            scored.append((
                weighted_score(
                    breakdown, outcome.state,
                    personal_fit=personal_fit_modifier(
                        tuple(opportunity.category_tags), my_reflections,
                        categories_of)),
                opportunity, outcome, validation, breakdown,
            ))
        # 排序键里带 opportunity_id：分数相同时顺序也必须确定，
        # 否则同一份 Seed 两次调用的 diff 永远不为空。
        scored.sort(key=lambda row: (-row[0], row[1].opportunity_id))

        # ── 主/副目标推荐配比（2026-08-02 用户需求）─────────────────────
        # 学生同时有 primary + candidate 目标时，按 candidate_goal_share
        # （默认 0.2 = 主80/副20）给副目标**保留名额**：与副目标 target_name
        # 词级相关的最优机会占 ceil(limit×share) 席，其余按总分。确定性配额
        # 选择而非分数乘法——份额语义直给，可解释也可测。
        goals = deps.goals.get(student_id, ())
        candidate_goal = next(
            (g for g in goals if g.role is GoalRole.CANDIDATE
             and g.status.value in ("active", "candidate")), None)
        top = scored[:limit]
        candidate_ids: set[str] = set()   # 黄-8：卡片标注服务于哪个目标
        if candidate_goal is not None and student.candidate_goal_share > 0:
            cand_words = {w for w in candidate_goal.target_name.lower()
                          .replace("_", " ").split() if len(w) >= 2}

            def _hits_candidate(opportunity) -> bool:
                text_words = {
                    w for text in (opportunity.title, *opportunity.skills,
                                   *opportunity.category_tags)
                    for w in str(text).lower().replace("_", " ").split()
                }
                return bool(cand_words & text_words)

            # 前缀成比例交织：结果被缓存后按任意 limit 切片，所以份额必须对
            # **每个前缀**都成立——任意前 k 条里副目标相关 ≈ ceil(k×share)，
            # 而不是只在总表里凑数（否则前 10 名把副目标全挤掉）。
            import math as _math
            share = student.candidate_goal_share
            cand_q = [row for row in scored if _hits_candidate(row[1])]
            rest_q = [row for row in scored if not _hits_candidate(row[1])]
            candidate_ids = {row[1].opportunity_id for row in cand_q}
            merged: list = []
            ci = ri = 0
            while len(merged) < limit and (ci < len(cand_q) or ri < len(rest_q)):
                need = _math.ceil((len(merged) + 1) * share)
                if ci < len(cand_q) and (ci < need or ri >= len(rest_q)):
                    merged.append(cand_q[ci]); ci += 1
                else:
                    merged.append(rest_q[ri]); ri += 1
            top = merged

        # 模型只做一件事：给已经排好的候选写理由。它拿到的是结构化摘要，
        # 不是机会原文——外部内容只走 data 通道（§8.9.1 第 1 条）。
        rationale_by_id = _match_rationale(model, student_id, top) if model else {}

        # 国际生逐卡注记（2026-08-02 修复批）：信封整页求值一次，
        # 注记逐机会派生——修掉"同一句话贴满全页"的复读 bug。
        intl_eval = None
        if student.intl_context is not None:
            evaluated = evaluate_intl_pack(student)
            if evaluated.consented:
                intl_eval = evaluated

        out: list[MatchResult] = []
        for _, opportunity, outcome, validation, breakdown in top:
            eligibility = _eligibility_assessment(opportunity, outcome, validation, now)
            # 契约要求每条结果至少一条理由。模型缺席或漏答时给确定性兜底，
            # 并写明它是规则生成——不能让兜底文案冒充模型解释。
            fallback = render_message(
                "match.reason_deterministic",
                categories=str(len(opportunity.requirement_categories)),
                workload=(f"{opportunity.workload_hours_total:.0f}h"
                          if opportunity.workload_hours_total
                          else LocalizedText(zh_Hans="未知", en="unknown")),
            )
            out.append(build_match(
                opportunity, eligibility=eligibility, breakdown=breakdown,
                weekly_capacity_hours=weekly,
                covered_requirement_ids=tuple(
                    c.value for c in opportunity.requirement_categories
                ),
                rationale=rationale_by_id.get(opportunity.opportunity_id)
                or (fallback,),
                risks=(),
                today=deps.today, now=now,
                intl_notes=(_intl_match_notes(opportunity, intl_eval, deps.today)
                            if intl_eval is not None else ()),
                goal_role=(None if candidate_goal is None
                           else "candidate"
                           if opportunity.opportunity_id in candidate_ids
                           else "primary"),
            ))
        return out

    @implements("GET", "/students/{student_id}/matches",
                response_model=list[MatchResult])
    def matches(student_id: str, limit: int = Query(10, ge=1, le=50)) -> list[MatchResult]:
        """缓存版：每天最多为一个学生真正跑一次 A5（用户裁定，省 token 也省等待）。

        缓存命中 = 当天已算过；跨天后第一次访问自动重算（相当于"每日刷新一次"，
        无需常驻定时器）。学生手动重算走 `POST /matches/refresh`，每天限 3 次。
        """
        _known_student(student_id)
        today = date.today()
        cached = deps.match_cache.get(student_id)
        if cached is None or cached[0] != today:
            # R7-D：编排走 A0 的确定性路由表（不调模型，T9 不受影响），
            # 痕迹落在 agent-trace，演示时能亲眼看到"谁被派了活"。
            _trace_route(student_id, IntentId.FIND_OPPORTUNITIES)
            deps.match_cache[student_id] = (today, _compute_matches(student_id, 50))
        return deps.match_cache[student_id][1][:limit]

    def _trace_route(student_id: str, intent: IntentId) -> None:
        """R7-D：A0 上线的落点。已知意图 → 确定性路由表 → WorkflowPlan。"""
        from campuspath_agents.model import ScriptedModel
        from campuspath_agents.roster import OrchestratorAgent
        from campuspath_agents.tools import belt_for

        a0 = OrchestratorAgent(
            AgentId.A0_ORCHESTRATOR, belt_for(AgentId.A0_ORCHESTRATOR, {}),
            deps.model or ScriptedModel(),   # route 不调模型，桩只为满足构造
        )
        rows = deps.agent_traces.setdefault(student_id, [])
        rows.append(a0.route(
            student_id, intent,
            plan_id=f"WF-{student_id}-{intent.value}-{len(rows) + 1}",
            now=datetime.now(timezone.utc),
        ))
        del rows[:-20]

    @implements("GET", "/students/{student_id}/agent-trace",
                response_model=list[WorkflowPlan])
    def agent_trace(student_id: str) -> list[WorkflowPlan]:
        """R7-D：A0 编排痕迹。``deterministic_route`` = 这次没调模型。"""
        _known_student(student_id)
        return deps.agent_traces.get(student_id, [])

    # ── 国际学生规则包求值（B，2026-08-02）────────────────────────────

    #: Goal.development_mode → Pack goal_type。employment 之外的方向
    #: Pack 的 applicability 不覆盖（goal_types 只有实习/兼职/毕业就业），
    #: 求值器会如实返回 not applicable → needs_confirmation，不硬套。
    _PACK_GOAL_TYPE = {"employment": "graduate_employment"}

    def _intl_profile_context(profile: StudentProfile) -> dict:
        """StudentProfile + InternationalStudentContext → 求值器输入。
        institution/programme_level/graduation 从档案本体派生（一份事实一个出处）。"""
        intl = profile.intl_context
        assert intl is not None
        goal_type = None
        for goal in deps.goals.get(profile.student_id, []):
            mapped = _PACK_GOAL_TYPE.get(goal.development_mode.value)
            if mapped:
                goal_type = mapped
                break
        return {
            "student_cohort": "international",
            "study_jurisdiction": intl.study_jurisdiction,
            "intended_work_jurisdiction": intl.intended_work_jurisdiction,
            "institution": profile.institution,
            "programme_level": profile.level,
            "study_mode": intl.study_mode,
            "goal_type": goal_type,
            "permission_category": intl.permission_category,
            "permission_expiry_date": intl.permission_expiry_date.isoformat(),
            "expected_graduation_date": profile.expected_graduation.isoformat(),
            "intended_start_date": (
                intl.intended_start_date.isoformat() if intl.intended_start_date else None
            ),
            "school_approval": intl.school_approval,
            "employer_sponsorship": intl.employer_sponsorship_expected,
            "language_evidence": list(intl.language_evidence),
            "consent_context_pack": profile.has_consent(ConsentScope.CONTEXT_PACK),
        }

    def evaluate_intl_pack(profile: StudentProfile, opportunity: Opportunity | None = None):
        """求值 + Rules 签发。返回契约化信封（消费点共用：端点 / A3 / A5）。"""
        from campuspath_rules.context_pack import evaluate_context_pack
        from campuspath_rules.engine import RulesEngine
        from campuspath_contracts.packs import (
            ContextPackEvaluation, PackPathwayImpact, PackPreparationAction,
            PackSourceLink, PackSupportItem,
        )

        opportunity_ctx = None
        if opportunity is not None:
            opportunity_ctx = {
                "opportunity_id": opportunity.opportunity_id,
                "opportunity_type": opportunity.type.value,
                # 我们的 Opportunity 没有 location/hours 字段——缺就是缺，
                # 求值器把它们列进 missing_information，不编造
                "employer_sponsorship": (
                    True if opportunity.sponsorship_support is not None else None
                ),
            }
        engine = RulesEngine(registry=deps.validations)
        envelope, validation = evaluate_context_pack(
            engine, _intl_profile_context(profile), opportunity_ctx,
            today=datetime.now(timezone.utc).date(),
            subject_context=profile.student_id,   # 审查 #16：凭据绑定学生，与资格判定同口径
        )
        return ContextPackEvaluation(
            installed=envelope["pack_status"]["installed"],
            applicable=envelope["pack_status"]["applicable"],
            consented=envelope["pack_status"]["consented"],
            pack_current=envelope["pack_status"]["current"],
            eligibility_state=envelope["eligibility_state"],
            headline_key=envelope["headline_key"],
            jurisdiction=envelope["jurisdiction"],
            pack_version=envelope["pack_version"],
            last_verified_at=envelope["last_verified_at"],
            applicable_rule_ids=tuple(envelope["applicable_rule_ids"]),
            constraints=tuple(envelope["constraints"]),
            missing_information=tuple(envelope["missing_information"]),
            required_evidence=tuple(envelope["required_evidence"]),
            preparation_actions=tuple(
                PackPreparationAction(
                    preparation_action_id=a["preparation_action_id"],
                    category=a["category"], title=a["title"],
                    description=a["description"],
                    recommended_lead_time_days=a.get("recommended_lead_time_days"),
                    mandatory=bool(a.get("mandatory", False)),
                    source_ids=tuple(a.get("source_ids", ())),
                ) for a in envelope["preparation_actions"]
            ),
            support_items=tuple(
                PackSupportItem(
                    support_item_id=s["support_item_id"], category=s["category"],
                    title=s["title"], provider=s["provider"],
                    eligibility_summary=s["eligibility_summary"],
                    application_required=bool(s.get("application_required", False)),
                    deadline=s.get("deadline"),
                    source_ids=tuple(s.get("source_ids", ())),
                ) for s in envelope["support_items"]
            ),
            source_links=tuple(
                PackSourceLink(
                    source_id=l["source_id"], title=l["title"], url=l["url"],
                    last_checked_at=l["last_checked_at"],
                ) for l in envelope["source_links"]
            ),
            pathway_impacts=tuple(
                PackPathwayImpact(
                    impact_id=i["impact_id"], rule_ids=tuple(i["rule_ids"]),
                    pathway_segment_id=i["pathway_segment_id"],
                    impact_type=i["impact_type"], summary=i["summary"],
                ) for i in envelope["pathway_impacts"]
            ),
            pack_digest=envelope["validation_id"],
            rules_validation_id=validation.validation_id,
            review_required=envelope["review_required"],
            evaluated_at=datetime.now(timezone.utc),
        )

    @implements("GET", "/students/{student_id}/context-pack/evaluation",
                response_model=ContextPackEvaluation)
    def context_pack_evaluation(
        student_id: str, opportunity_id: str | None = None
    ):
        profile = _known_student(student_id)
        if profile.intl_context is None:
            raise HTTPException(409, {
                "error": "intl_context_not_enabled",
                "detail": "档案页勾选「我是国际生」并填写结构化信息后才有求值",
            })
        opportunity = None
        if opportunity_id is not None:
            opportunity = next(
                (o for o in deps.opportunities + deps.expired_opportunities
                 if o.opportunity_id == opportunity_id), None)
        return evaluate_intl_pack(profile, opportunity)

    def _owned_block(student_id: str, block_id: str) -> int:
        for index, block in enumerate(deps.availability):
            if block.block_id == block_id and block.student_id == student_id:
                return index
        raise HTTPException(404, {"error": "unknown_block",
                                  "detail": f"未知时段 {block_id}"})

    def _rebuild_snapshot(student_id: str) -> None:
        """M（2026-07-31）：日程一变，容量快照按新视图重算。

        口径（§16.6/§16.7，回答"保护时段怎么算"）：
        * 睡眠与三餐**不进** protected_time_hours——每周可支配小时数本来就
          不含它们，再扣一次人人都是负容量；它们只生成保护块挡排程（B2）。
        * 学生**额外**划的个人保护时段（非作息块）才计入 protected_time_hours，
          从可支配容量里扣——那是从成长预算里让出来的时间。
        """
        from datetime import time as _time

        from campuspath_capacity.capacity import StudentBoundaries, build_snapshot

        student = deps.students.get(student_id)
        rows = deps.snapshots.get(student_id)
        if student is None or not rows:
            return
        old = rows[0]
        blocks = [b for b in deps.availability if b.student_id == student_id]
        # 跨午夜的个人保护块拆成两个同日窗口——(23:00, 07:30) 直接进
        # 容量计算会得出负时长（审查后真机踩到：快照 -15.5h 直接 500）
        def windows_of(b):
            start_d, end_d = b.span.start.date(), b.span.end.date()
            s = _time(b.span.start.hour, b.span.start.minute)
            e = _time(b.span.end.hour, b.span.end.minute)
            if end_d > start_d and e != _time(0, 0):
                return [(b.span.start.weekday(), s, _time(23, 59)),
                        (b.span.end.weekday(), _time(0, 0), e)]
            return [(b.span.start.weekday(), s, e)]

        personal_protected = tuple(
            window
            for b in blocks
            if b.type is AvailabilityType.PROTECTED
            and b.block_id in deps.personal_protected_ids
            for window in windows_of(b)
        )
        rows[0] = build_snapshot(
            student_id, old.period_start, blocks, student.energy_profile,
            old.planned_load_hours,
            boundaries=StudentBoundaries(unavailable_windows=personal_protected),
            snapshot_id=old.snapshot_id,
        )

    @implements("POST", "/students/{student_id}/availability",
                response_model=AvailabilityBlock)
    def create_block(student_id: str, block: AvailabilityBlock) -> AvailabilityBlock:
        """A（2026-07-31）：学生在自己的周日历上直接添加行程。

        只允许 ``student_defined`` 来源——日历同步块由 Connector 管，
        学生不能以"添加"的名义伪造一条 provider 数据。标题是学生自己写的
        （privacy_level=student_defined），与 B5 管的"读取采集"是两回事。
        """
        _known_student(student_id)
        if block.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        if block.source is not BlockSource.STUDENT_DEFINED:
            raise HTTPException(422, {"error": "not_student_defined",
                                      "detail": "手动添加的时段必须是 student_defined 来源"})
        if any(b.block_id == block.block_id for b in deps.availability):
            return block                    # 幂等：同 id 重放不重复添加
        deps.availability.append(block)
        if block.type is AvailabilityType.PROTECTED:
            deps.personal_protected_ids.add(block.block_id)
        _rebuild_snapshot(student_id)
        return block

    @implements("POST", "/students/{student_id}/availability/{block_id}/update",
                response_model=AvailabilityBlock)
    def update_block(student_id: str, block_id: str,
                     patch: AvailabilityBlockPatch) -> AvailabilityBlock:
        """A/H：学生直接编辑时段（起止/标题/类型/提醒）。改的是**自己的视图**，
        权威日历不动。补丁套上后整块重校验——B5 的标题授权约束照常生效。"""
        _known_student(student_id)
        index = _owned_block(student_id, block_id)
        current = deps.availability[index]
        updates: dict = {}
        if patch.span is not None:
            updates["span"] = patch.span
        if patch.type is not None:
            updates["type"] = patch.type
        if patch.reminder_minutes_before is not None:
            updates["reminder_minutes_before"] = patch.reminder_minutes_before
        if patch.title is not None:
            # 学生给自己的视图块起名：授权层级随之标为 event_titles 的
            # student_defined 内容——这是学生写入，不是超层级采集
            updates["title"] = patch.title
            updates["detail_level"] = CalendarDetailLevel.EVENT_TITLES
            updates["privacy_level"] = "student_defined"
        try:
            updated = current.model_copy(update=updates)
        except Exception as exc:            # noqa: BLE001 —— 校验失败如实 422
            raise HTTPException(422, str(exc))
        deps.availability[index] = updated
        # 作息块（routine 前缀）是睡眠/三餐——容量口径它们**不**计入个人
        # 保护时段（§16.6，每周可支配本就不含）。编辑它不改变这个归类；
        # 曾因此把 8.5h 睡眠算进 personal protected，快照直接负数 500。
        is_routine = block_id.startswith(f"AB-{student_id}-routine-")
        if patch.type is AvailabilityType.PROTECTED and \
                updated.source is BlockSource.STUDENT_DEFINED and not is_routine:
            deps.personal_protected_ids.add(block_id)
        elif patch.type is not None and patch.type is not AvailabilityType.PROTECTED:
            deps.personal_protected_ids.discard(block_id)
        _rebuild_snapshot(student_id)
        return updated

    @implements("POST", "/students/{student_id}/availability/{block_id}/remove",
                response_model=AvailabilityBlock)
    def remove_block(student_id: str, block_id: str) -> AvailabilityBlock:
        """H：删除误占用时段（日历同步进来但其实没占用的）。"""
        _known_student(student_id)
        index = _owned_block(student_id, block_id)
        removed = deps.availability.pop(index)
        deps.personal_protected_ids.discard(block_id)
        _rebuild_snapshot(student_id)
        return removed

    @implements("POST", "/students/{student_id}/routine",
                response_model=CapacitySnapshot)
    def submit_routine(student_id: str, routine: RoutineRequest) -> CapacitySnapshot:
        """M（2026-07-31）：学生显式提交日常作息（§16.8.2：不得从日历反推）。

        睡眠/三餐 → 快照周期内**每天**一个保护块（挡排程，B2），
        并写进 EnergyProfile 的睡眠窗口（Wellbeing 信号的前提）。
        幂等：重复提交先清掉旧的作息块再生成。
        """
        from datetime import time as _time

        student = _known_student(student_id)
        rows = deps.snapshots.get(student_id)
        if not rows:
            raise HTTPException(404, f"{student_id} 没有容量快照——可能尚未连接日历")
        period_start, period_end = rows[0].period_start, rows[0].period_end

        prefix = f"AB-{student_id}-routine-"
        deps.availability[:] = [
            b for b in deps.availability if not b.block_id.startswith(prefix)
        ]
        windows: list[tuple[str, RoutineWindow]] = []
        if routine.sleep is not None:
            windows.append(("sleep", routine.sleep))
        windows.extend((f"meal{i}", w) for i, w in enumerate(routine.meals))

        # 2026-08-02 用户报障修复：跨午夜睡眠窗从 period_start **前一晚**开始
        # 生成——首日凌晨那段睡眠属于前一晚的块，不补则周一 00:00–07:00 空白
        day = period_start - timedelta(days=1)
        while day <= period_end:
            for name, window in windows:
                sh, sm = (int(x) for x in window.start.split(":"))
                eh, em = (int(x) for x in window.end.split(":"))
                crosses_midnight = (eh * 60 + em) <= (sh * 60 + sm)
                if day < period_start and not (name == "sleep" and crosses_midnight):
                    continue                # 前一晚只需要跨午夜的睡眠块
                start = datetime(day.year, day.month, day.day, sh, sm,
                                 tzinfo=timezone.utc)
                end = datetime(day.year, day.month, day.day, eh, em,
                               tzinfo=timezone.utc)
                if crosses_midnight:
                    end += timedelta(days=1)
                deps.availability.append(AvailabilityBlock(
                    block_id=f"{prefix}{name}-{day.isoformat()}",
                    student_id=student_id, span=TimeRange(start=start, end=end),
                    type=AvailabilityType.PROTECTED,
                    source=BlockSource.STUDENT_DEFINED,
                ))
            day += timedelta(days=1)

        if routine.sleep is not None:
            deps.students[student_id] = StudentProfile.model_validate({
                **student.model_dump(),
                "energy_profile": {
                    **student.energy_profile.model_dump(),
                    "sleep_window_start": routine.sleep.start,
                    "sleep_window_end": routine.sleep.end,
                },
                "version": student.version + 1,
                "updated_at": datetime.now(timezone.utc),
            })

        _rebuild_snapshot(student_id)
        return deps.snapshots[student_id][0]

    @implements("GET", "/students/{student_id}/course-recommendations",
                response_model=list[CourseRecommendation])
    def course_recommendations(student_id: str) -> list[CourseRecommendation]:
        """R4-K：推荐**选修课**，两层筛选。

        第 1 层（规则，零模型）：排除必修组课程与已修课；只留先修 met 或
        unknown 的候选；按（兴趣+目标）词级命中初筛。
        第 2 层（AI）：一次批量调用给每门课复筛出 是/待确认/不推荐 与理由。
        边界：AI 评的是相关性，**不覆盖 Rules 的先修判定**——unknown 先修的
        课最多进"待用户确认"并附原文提示（§16.2/B8）。
        模型不可用 → 规则降级，理由如实自报 rules。当日缓存。
        """
        student = _known_student(student_id)
        cache_key = (student_id, deps.today.isoformat())
        cached = deps.course_rec_cache.get(cache_key)
        if cached is not None:
            return cached
        _trace_route(student_id, IntentId.PLAN_COURSES)   # R7-D：A0 痕迹

        # —— 第 1 层：确定性筛选 ————————————————————————
        import json as _json
        import pathlib
        ppath = (pathlib.Path(__file__).resolve().parents[3]
                 / "seed" / "raw" / "hkust_programs" / "programs.json")
        required_codes: set[str] = set()
        program_rows = (
            _json.loads(ppath.read_text(encoding="utf-8"))
            if ppath.exists() else [])
        manual_path = ppath.parent / "manual_isom_ieda.json"
        if manual_path.exists():   # P1-2：人工转录的 ISOM/IEDA 一并生效
            known = {r["program_id"] for r in program_rows}
            program_rows += [
                r for r in _json.loads(manual_path.read_text(encoding="utf-8"))
                if r["program_id"] not in known]
        if program_rows:
            for row in program_rows:
                if student.program_id.endswith(row["program_id"]):
                    # 只排除**无择一逻辑**的纯必修组——带择一逻辑的必修组
                    # （如 COMP 的 6 学分组里挑课）学生本来就要做选择，
                    # 正是推荐该帮忙的地方
                    required_codes = {
                        code for g in row.get("requirement_groups", ())
                        if g.get("type") == "required"
                        and not g.get("has_or_logic")
                        for code in g.get("course_codes", ())
                    }
        completed = {r.course_id for r in deps.records.get(student_id, [])}
        goals = deps.goals.get(student_id, [])
        # 主/副目标配比（2026-08-02 用户需求）：主目标 + 兴趣词满权重，
        # 副（candidate）目标词按 share/(1-share)（默认 0.2/0.8=0.25）计权——
        # 副目标进推荐但不与主目标平起平坐。
        def _words_of(texts) -> set[str]:
            return {w for text in texts
                    for w in text.lower().replace("_", " ").split() if len(w) >= 2}
        primary_words = _words_of([
            *student.interests,
            *(g.target_name for g in goals if g.role is not GoalRole.CANDIDATE)])
        cand_words = _words_of(
            g.target_name for g in goals if g.role is GoalRole.CANDIDATE)
        cand_ratio = (student.candidate_goal_share
                      / max(1e-9, 1 - student.candidate_goal_share))

        candidates = _course_candidates_for(student_id)
        pool = []
        for row in candidates:
            if row.course_id in required_codes or row.course_id in completed:
                continue
            if row.prerequisite_status not in (
                    PrerequisiteStatus.MET, PrerequisiteStatus.UNKNOWN):
                continue                      # 未满足的下学期再说，不堆在这里
            course = deps.catalog.get(row.course_id)
            if course is None:
                continue
            tag_words = {
                w for tag in (*row.skill_tags, course.title)
                for w in tag.lower().replace("_", " ").split()
            }
            hits = sorted((primary_words | cand_words) & tag_words)
            weight = (len(primary_words & tag_words)
                      + cand_ratio * len(cand_words & tag_words - primary_words))
            pool.append((row, course, hits, weight))
        # P2-3（2026-08-01 用户批准）：词级命中优先，但**无命中 ≠ 无关**——
        # 语义相关性正是第 2 层 AI 的活。命中的排前面（按加权命中分），
        # 剩余名额回填无命中候选一起进同一次批量调用（成本不变）。
        pool.sort(key=lambda item: (-item[3], item[0].course_id))
        # 副目标保底名额：只要存在副目标命中课，池子里至少留 ceil(25×share) 席
        if cand_words:
            import math as _math
            quota = max(1, _math.ceil(25 * student.candidate_goal_share))
            cand_pool = [p for p in pool if cand_words & {
                w for tag in (*p[0].skill_tags, p[1].title)
                for w in tag.lower().replace("_", " ").split()}][:quota]
            cand_ids = {p[0].course_id for p in cand_pool}
            head = [p for p in pool if p[0].course_id not in cand_ids][:25 - len(cand_pool)]
            pool = sorted([*cand_pool, *head],
                          key=lambda item: (-item[3], item[0].course_id))
        pool = [(row, course, hits) for row, course, hits, _ in pool]
        pool = pool[:25]                      # 一次模型调用的上限

        # —— 第 2 层：AI 复筛（批量一次；不可用则规则降级） ——————
        verdicts: dict[str, tuple[str, str, str]] = {}
        used_model = False
        if deps.model is not None and pool:
            from campuspath_agents.model import ModelRequest
            lines = "\n".join(
                f"{row.course_id}\t{course.title}\t"
                f"{','.join(row.skill_tags)}\t{(course.description or '')[:200]}"
                for row, course, _hits in pool
            )
            goal_text = "；".join(
                f"{g.development_mode}:{g.target_name}" for g in goals) or "未设目标"
            try:
                raw = deps.model.generate(ModelRequest(
                    system=(
                        "你在为一名学生复筛选修课。数据块第一段是学生的目标与兴趣，"
                        "第二段是候选课（每行：课程码\\t课名\\t标签\\t简介）。"
                        "对每一行输出：课程码\\tyes|unsure|no\\t一句中文推荐理由"
                        "\\t一句英文理由。yes=明确有助于其目标能力；unsure=可能相关"
                        "但没把握；no=无关。只输出这些行。"
                    ),
                    data=(f"目标与兴趣：{goal_text}；{', '.join(student.interests)}",
                          lines),
                    purpose=f"course-rec:{student_id}",
                ))
                for line in raw.splitlines():
                    parts = line.split("\t")
                    if len(parts) >= 4 and parts[1].strip() in {"yes", "unsure", "no"}:
                        verdicts[parts[0].strip()] = (
                            parts[1].strip(), parts[2].strip(), parts[3].strip())
                used_model = bool(verdicts)
            except Exception:
                verdicts = {}

        out: list[CourseRecommendation] = []
        for row, course, hits in pool:
            verdict_raw = verdicts.get(row.course_id)
            if verdict_raw is not None:
                kind, zh, en = verdict_raw
                if kind == "no":
                    continue
                verdict = "recommended" if kind == "yes" else "needs_user_confirmation"
                reason = LocalizedText(zh_Hans=zh[:500], en=en[:500])
                source = "model"
            else:
                if not hits:
                    continue    # 降级态下无词级依据的课不硬编理由（P2-3）
                # 规则降级：词级命中即"待用户确认"——规则不冒充 AI 的判断
                verdict = "needs_user_confirmation"
                reason = LocalizedText(
                    zh_Hans=f"课程标签 {', '.join(hits[:3])} 与你的目标/兴趣重合"
                            "（规则初筛，AI 复筛暂不可用）",
                    en=f"Tags {', '.join(hits[:3])} overlap your goals/interests "
                       "(rule prefilter; AI pass unavailable)",
                )
                source = "rules"
            note = None
            if row.prerequisite_status is PrerequisiteStatus.UNKNOWN:
                # AI 不改判先修——读不懂的规则原样给学生，判定归 Rules/教务
                verdict = "needs_user_confirmation"
                expr = course.prerequisite_expression or ""
                note = LocalizedText(
                    zh_Hans=f"先修规则原文无法机读，请与教务确认：{expr}"[:500],
                    en=f"Prerequisite text could not be parsed — confirm with "
                       f"the registry: {expr}"[:500],
                )
            out.append(CourseRecommendation(
                course_id=row.course_id, title=course.title,
                credits=course.credits, description=course.description,
                verdict=verdict, reason=reason,
                reason_source="model" if (used_model and verdict_raw) else "rules",
                prerequisite_note=note,
                skill_tags=row.skill_tags,
                official_url=course.source.source_url,
            ))
        deps.course_rec_cache[cache_key] = out
        return out

    @implements("GET", "/catalog/courses", response_model=list[CourseCatalogItem])
    def catalog_courses(
        subject: str | None = Query(default=None),
        limit: int = Query(default=500, ge=1, le=2000),
    ) -> list[CourseCatalogItem]:
        """H（2026-07-31）：课程详情——全名 / 简介 / 先修原文 / 官方来源链接。

        选课页据此把"COMP 2012"从一个缩写变成一门看得懂的课。
        导师字段目录里没有，如实不提供（offering.instructor 在种子里为空）。
        """
        rows = sorted(deps.catalog.values(), key=lambda c: c.course_id)
        if subject:
            needle = subject.strip().upper()
            rows = [c for c in rows if c.subject.upper() == needle]
        return rows[:limit]

    @implements("GET", "/catalog/programs", response_model=list[ProgramCurriculum])
    def program_curricula() -> list[ProgramCurriculum]:
        """K②：专业四年课程要求（C 抓取的真实数据）。空缺字段是 None，不编造。"""
        import json as _json
        import pathlib

        path = (pathlib.Path(__file__).resolve().parents[3]
                / "seed" / "raw" / "hkust_programs" / "programs.json")
        if not path.exists():
            return []
        rows = _json.loads(path.read_text(encoding="utf-8"))
        # P1-2（2026-08-01 用户拍板方案②）：ISOM/IEDA 无公开 ugprog PDF——
        # 由官方页面人工转录补充，条目自带 provenance.method=manual_transcription；
        # 缺闭合课程清单的组（如 ISOM 的区间型 IS Electives）如实缺席，不编造。
        manual = path.parent / "manual_isom_ieda.json"
        if manual.exists():
            existing = {r["program_id"] for r in rows}
            rows += [r for r in _json.loads(manual.read_text(encoding="utf-8"))
                     if r["program_id"] not in existing]
        # R4-J：按学期的建议修读安排（官方 PDF + 先修链推断，来源注明）
        term_path = path.parent / "term_plans.json"
        term_data = (_json.loads(term_path.read_text(encoding="utf-8"))
                     .get("programs", {}) if term_path.exists() else {})
        out: list[ProgramCurriculum] = []
        for row in rows:
            group_fields = ("group_name", "credits_required", "courses_required",
                            "estimated_credits_sum", "has_or_logic",
                            "course_codes", "source_url")
            groups = [
                {
                    **{k: g.get(k) for k in group_fields},
                    "type": g["type"] if g.get("type") in
                    {"required", "elective", "school_requirement"} else "other",
                }
                for g in row.get("requirement_groups", ())
            ]
            out.append(ProgramCurriculum(
                program_id=row["program_id"], name=row["name"],
                school=row.get("school", ""),
                normative_duration=row.get("normative_duration"),
                total_credits_required=row.get("total_credits_required"),
                substituted_for=row.get("substituted_for"),
                university_graduation_requirements=tuple(
                    f"{key}: {value}" for key, value in
                    (row.get("university_graduation_requirements") or {}).items()
                ),
                requirement_groups=tuple(groups),
                source_urls=tuple(row.get("source_urls", ())),
                term_plans=tuple(
                    {"term_key": key, "required": tuple(term.get("required", ())),
                     "notes": term.get("notes")}
                    for key, term in
                    (term_data.get(row["program_id"], {}).get("terms") or {}).items()
                ),
                term_plan_note=term_data.get(row["program_id"], {}).get("source_note"),
            ))
        return out

    @implements("GET", "/students/{student_id}/goals/{goal_id}/decomposition",
                response_model=GoalDecomposition)
    def goal_decomposition(student_id: str, goal_id: str) -> GoalDecomposition:
        """D：目标 → 三层要求拆解。内容来自人群 Pack（确定性），产出方是 A3。

        Pack 未覆盖的方向（探索中/个人兴趣）422 并说明——探索中的学生
        不该被塞一份求职清单。
        """
        from campuspath_agents.model import ScriptedModel
        from campuspath_agents.roster import GoalGapAgent
        from campuspath_agents.tools import belt_for
        from campuspath_contracts.common import AgentId

        _known_student(student_id)
        goal = next(
            (g for g in deps.goals.get(student_id, ()) if g.goal_id == goal_id),
            None,
        )
        if goal is None:
            raise HTTPException(404, {"error": "unknown_goal",
                                      "detail": f"未知目标 {goal_id}"})
        a3 = GoalGapAgent(
            AgentId.A3_GOAL_GAP, belt_for(AgentId.A3_GOAL_GAP, {}),
            deps.model or ScriptedModel(),
        )
        try:
            decomposition = a3.decompose_goal(goal)
        except KeyError as exc:
            raise HTTPException(422, {"error": "no_pack_for_mode",
                                      "detail": str(exc)}) from exc
        decomposition = _augment_with_intl(decomposition, student_id)
        # A4（2026-08-02）：现场研究任务完成后，ai_live facets 并入拆解
        # （origin 字段区分显示，「AI 现场拆解·待核验」不冒充编制数据）。
        # 审计红-2 后半（用户裁定）：编制画像只是缓存、现场拆解才是产品
        # 能力——学生对**已命中画像**的岗位显式重跑后，live 结果成为唯一
        # 口径：带市场证据的编制 facets 被取代（不叠加混排），约束/占位
        # 条目保留；未命中画像时仍是「通用 Pack + live 附加」。
        job = _research_job_if_current(student_id, goal_id)
        if job is not None and job.state == "done" and job.facets:
            base_facets = tuple(
                f for f in decomposition.facets
                if f.origin == "ai_live" or not (
                    decomposition.role_profile is not None
                    and f.origin == "compiled" and f.market_note is not None))
            decomposition = decomposition.model_copy(update={
                "facets": base_facets + job.facets,
            })
        return decomposition

    _RESEARCH_DAILY_LIMIT = 2

    @implements("POST", "/students/{student_id}/goals/{goal_id}/decomposition/research",
                response_model=DecompositionResearchJob)
    def start_decomposition_research(student_id: str, goal_id: str) -> DecompositionResearchJob:
        """现场 AI 拆解：服务端后台任务——学生切页/关页不中断。

        2026-08-02 用户裁定重建：这里跑的是**真流水线**（接地搜索在招 JD →
        服务端逐条真实抓取原文 → 模型逐行拆解归类 → 确定性加权出市场证据），
        与离线编译器同一方法论同一词表；进度条对应真实阶段。
        慢是应该的——这是平台核心功能，宁慢勿假。每人每日限 2 次。"""
        from campuspath_agents.live_market_research import run_live_market_research

        _known_student(student_id)
        goal = next(
            (g for g in deps.goals.get(student_id, ()) if g.goal_id == goal_id), None)
        if goal is None:
            raise HTTPException(404, {"error": "unknown_goal", "detail": goal_id})
        if deps.model is None:
            raise HTTPException(503, {"error": "model_backend_unavailable",
                                      "detail": "现场拆解需要模型后端（Vertex ADC）"})
        key = (student_id, goal_id)
        now = datetime.now(timezone.utc)
        day_key = (student_id, now.date().isoformat())
        with deps.jobs_lock:   # 审查 #7：闸门 + 配额扣减原子化
            existing = deps.research_jobs.get(key)
            if existing is not None and existing.state == "running":
                raise HTTPException(409, {"error": "research_already_running",
                                          "detail": existing.job_id})
            used = deps.research_daily.get(day_key, 0)
            if used >= _RESEARCH_DAILY_LIMIT:
                raise HTTPException(429, {"error": "daily_research_limit",
                                          "detail": f"每日限 {_RESEARCH_DAILY_LIMIT} 次"})
            deps.research_daily[day_key] = used + 1
            # 只留今天的 key（审查 #20：长跑进程按天累积）
            for stale in [k for k in deps.research_daily
                          if k[1] != now.date().isoformat()]:
                del deps.research_daily[stale]
        remaining = _RESEARCH_DAILY_LIMIT - used - 1
        job = DecompositionResearchJob(
            job_id=f"RJOB-{student_id}-{goal_id}-{int(now.timestamp())}",
            student_id=student_id, goal_id=goal_id,
            state="running", progress=5,
            stage=LocalizedText(zh_Hans="收集岗位要求…",
                                en="Collecting role requirements…"),
            started_at=now, daily_remaining=remaining,
        )
        deps.research_jobs[key] = job
        deps.research_target[key] = (goal.target_name or "").strip().lower()

        def _run() -> None:
            def update(**fields):
                with deps.jobs_lock:
                    deps.research_jobs[key] = deps.research_jobs[key].model_copy(
                        update=fields)

            def report(pct: int, zh: str, en: str) -> None:
                update(progress=min(99, max(1, pct)),
                       stage=LocalizedText(zh_Hans=zh, en=en))

            def fetch_text(url: str) -> str | None:
                """S2 的抓取步：connector 共享抓取器（归一化正文，礼貌间隔）。"""
                if deps.research_fetch_fn is not None:   # 测试桩
                    return deps.research_fetch_fn(url)
                from campuspath_connector import fetcher as _fetcher
                try:
                    return _fetcher.normalize_text(_fetcher.fetch(url))
                except Exception:
                    return None   # 抓不到 → 流水线如实跳过该公司

            try:
                outcome = run_live_market_research(
                    deps.model, goal,
                    fetch_text=fetch_text, progress=report, today=deps.today)
                _trace_route(student_id, IntentId.VIEW_GAP_MAP)   # 审查 #14：审计链
                done_zh = (f"完成：实采 {len(outcome.companies)} 家在招 JD"
                           + (f"，{len(outcome.skipped)} 家抓取失败已跳过"
                              if outcome.skipped else ""))
                done_en = (f"Done: {len(outcome.companies)} open JDs collected"
                           + (f", {len(outcome.skipped)} skipped (unfetchable)"
                              if outcome.skipped else ""))
                update(state="done", progress=100, facets=outcome.facets,
                       finished_at=datetime.now(timezone.utc),
                       stage=LocalizedText(zh_Hans=done_zh, en=done_en))
            except Exception as exc:   # 失败如实报告，不留悬空 running
                update(state="failed", progress=100, error=str(exc)[:300],
                       finished_at=datetime.now(timezone.utc),
                       stage=LocalizedText(zh_Hans="研究失败", en="Research failed"))
                with deps.jobs_lock:   # 审查 #20：失败不吞配额
                    deps.research_daily[day_key] = max(
                        0, deps.research_daily.get(day_key, 1) - 1)

        import threading

        threading.Thread(target=_run, daemon=True).start()
        return job

    def _research_job_if_current(student_id: str, goal_id: str):
        """Bug-1（2026-08-03）：研究结果只在**目标名未变**时可见。

        任务按 (student, goal_id) 存储，目标改名后同 id 挂着旧岗位的实采
        结果——live-覆盖语义会拿它顶替新岗位画像（评测实录：产品经理目标下
        出现「机器人抓取项目经验」）。发起时记录的目标名与当前不一致 → 视为
        不存在；无记录的历史任务保持可见（不误伤既有注入型测试与旧数据）。
        """
        key = (student_id, goal_id)
        job = deps.research_jobs.get(key)
        if job is None:
            return None
        stored = deps.research_target.get(key)
        if stored is None:
            return job
        goal = next((g for g in deps.goals.get(student_id, ())
                     if g.goal_id == goal_id), None)
        current = ((goal.target_name if goal else "") or "").strip().lower()
        return job if current == stored else None

    @implements("GET", "/students/{student_id}/goals/{goal_id}/decomposition/research",
                response_model=DecompositionResearchJob)
    def decomposition_research_status(student_id: str, goal_id: str) -> DecompositionResearchJob:
        _known_student(student_id)
        job = _research_job_if_current(student_id, goal_id)
        if job is None:
            raise HTTPException(404, {"error": "no_research_job",
                                      "detail": "该目标没有进行中或完成的研究任务"})
        return job

    def _augment_with_intl(decomposition: GoalDecomposition,
                           student_id: str) -> GoalDecomposition:
        """国际生准备列（用户增补 B）：Pack 已勾选+已同意时，把求值信封的
        preparation_actions / constraints / 缺失证据派生成第四列 facets。
        全部来自确定性求值，**不是模型现猜**；Pack 内容为英文原文时
        双语字段同文——不猜译（campus_events「不猜译名」同一纪律）。"""
        from campuspath_contracts.goals import RequirementCategory, RequirementFacet

        profile = deps.students.get(student_id)
        if profile is None or profile.intl_context is None:
            return decomposition
        evaluation = evaluate_intl_pack(profile)
        if not evaluation.consented:
            return decomposition
        facets: list[RequirementFacet] = []
        for action in evaluation.preparation_actions:
            lead = (
                f"（建议提前 {action.recommended_lead_time_days} 天）"
                if action.recommended_lead_time_days else ""
            )
            facets.append(RequirementFacet(
                category=RequirementCategory.ELIGIBILITY_STATUS,
                kind="constraint",
                description=LocalizedText(
                    zh_Hans=f"{action.title}{lead}",
                    en=action.title + (
                        f" (lead time {action.recommended_lead_time_days}d)"
                        if action.recommended_lead_time_days else ""
                    ),
                ),
                evidence_sources=(),
            ))
        for constraint in evaluation.constraints:
            facets.append(RequirementFacet(
                category=RequirementCategory.ELIGIBILITY_STATUS,
                kind="constraint",
                description=LocalizedText(zh_Hans=constraint, en=constraint),
                evidence_sources=(),
            ))
        if evaluation.missing_information:
            joined = "、".join(evaluation.missing_information[:6])
            facets.append(RequirementFacet(
                category=RequirementCategory.CREDENTIAL,
                kind="constraint",
                description=LocalizedText(
                    zh_Hans=f"待补充/待确认信息：{joined}",
                    en="Pending information: " + ", ".join(
                        evaluation.missing_information[:6]),
                ),
                evidence_sources=(),
            ))
        return decomposition.model_copy(update={
            "intl_facets": tuple(facets),
            "intl_pack_version": evaluation.pack_version,
            "intl_review_required": evaluation.review_required,
        })

    @implements("POST", "/students/{student_id}/resume",
                response_model=ProfileUpdateProposal)
    def upload_resume(student_id: str, upload: "ResumeUpload") -> ProfileUpdateProposal:
        """Resume → A1 提炼 → **恒为 pending** 的提案（B3）。

        与现有档案冲突的条目 operation=update 并带 old_value——
        「是否更新为新上传的版本」由学生在档案页逐项决定，系统不代答。
        原文不落库：解析完就丢，档案里只进学生确认过的结构化条目。
        """
        import base64
        import io

        from campuspath_agents.model import ModelRequest
        from campuspath_agents.roster import StudentContextAgent
        from campuspath_agents.tools import belt_for
        from campuspath_contracts.common import AgentId
        from campuspath_contracts.profile import ProposedChange

        student = _known_student(student_id)
        text = upload.content_text
        if text is None:
            try:
                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(base64.b64decode(upload.content_base64)))
                text = "\n".join(page.extract_text() or "" for page in reader.pages)
            except Exception as exc:
                raise HTTPException(422, {"error": "unreadable_resume",
                                          "detail": f"PDF 解析失败：{type(exc).__name__}"})
        if not text or not text.strip():
            raise HTTPException(422, {"error": "unreadable_resume",
                                      "detail": "文件里没有可解析的文本"})
        # D 裁定（2026-08-02）：模板化 Resume，**零模型**——确定性解析器
        # 逐节提取（教育/实习/项目/社团/技能/证书/荣誉/语言全覆盖，无行数
        # 上限）。不符合模板 → 422 + 模板小节清单。模型调用整段移除。
        from campuspath_api.resume_template import (
            TemplateError, parse_resume_template)
        try:
            changes = parse_resume_template(text[:60_000])
        except TemplateError as exc:
            raise HTTPException(422, {
                "error": "resume_not_in_template",
                "detail": str(exc),
                "expected_sections": TemplateError.EXPECTED,
            }) from exc
        # 档案页展示的"技能"来自 interests；经历上另挂 skills——两处都算已有。
        # 已有同名技能 → 标 update 并带旧值，学生决定（口径与模型时代一致）
        existing_skills = {s.lower() for s in student.interests}
        for experience in deps.experiences:
            if experience.student_id == student_id:
                existing_skills.update(s.lower() for s in experience.skills)
        changes = [
            (ProposedChange(
                entity_type="skill", operation="update",
                field_path="skills[]",
                old_value=c.new_value, new_value=c.new_value)
             if (c.entity_type == "skill"
                 and str(c.new_value).lower() in existing_skills) else c)
            for c in changes
        ]
        a1 = StudentContextAgent(
            AgentId.A1_STUDENT_CONTEXT,
            belt_for(AgentId.A1_STUDENT_CONTEXT, {}), deps.model,
        )
        proposal = a1.propose_profile_update(
            student_id, tuple(changes),
            reason=f"来自 Resume「{upload.filename}」的候选变更"
                   f"（模板规则解析·零 AI，待确认）",
            proposal_id=f"PROP-RESUME-{deps.memory.next_sequence()}",
            now=datetime.now(timezone.utc),
        )
        _store(student_id).submit_proposal(proposal)
        return proposal

    # ── Advisor（I/Q）：学生端预约，Advisor 端确认与会后建议，两端不混 ──
    def _slot_taken(slot_id: str) -> bool:
        """时段库存：requested/confirmed 占用；取消或爽约后释放。"""
        return any(
            b.slot_id == slot_id
            and b.status in (AdvisorBookingStatus.REQUESTED,
                             AdvisorBookingStatus.CONFIRMED)
            for b in deps.advisor_bookings
        )

    def _no_show_count(student_id: str) -> int:
        return sum(1 for b in deps.advisor_bookings
                   if b.student_id == student_id
                   and b.status is AdvisorBookingStatus.NO_SHOW)

    @implements("GET", "/advising/advisors", response_model=list[Advisor])
    def advisor_directory(
        role: str | None = Header(default=None, alias="X-CampusPath-Role"),
    ) -> list[Advisor]:
        """名录 + 实时占用。时段只报 booked 布尔——谁约的不在这里。

        R8-1：学生端**只**看到 Advisor 开放的时段——标记"不在"的时段
        在这里被服务端滤掉，不是前端隐藏；Advisor 端看全量（否则解除不了）。

        注意（审查确认）：这里读 header 只做**展示层过滤**——header 是
        声明式授权层，伪造它最多看到 blocked 时段的存在；真正的边界在
        ``book_advisor``：blocked 时段无论谁来订都是 409。
        """
        student_view = role == ActorRole.STUDENT.value
        return [
            Advisor.model_validate({
                **advisor.model_dump(),
                "slots": tuple(
                    {**slot.model_dump(), "booked": _slot_taken(slot.slot_id)}
                    for slot in advisor.slots
                    if not (student_view and slot.blocked)
                ),
            })
            for advisor in deps.advisors
        ]

    @implements("POST", "/advising/advisors", response_model=Advisor)
    def register_advisor(registration: "AdvisorRegistration") -> Advisor:
        """R8-1：Advisor 自助注册——顾问人员流动，名录不写死。
        注册即获得标准时段库存（与初始名录同一口径）。"""
        advisor_id = deps.next_advisor_id()
        advisor = Advisor(
            advisor_id=advisor_id,
            name=registration.name,
            focus=registration.focus,
            slots=deps.standard_advisor_slots(advisor_id),
        )
        deps.advisors.append(advisor)
        return advisor

    @implements("PUT", "/advising/advisors/{advisor_id}", response_model=Advisor)
    def update_advisor(advisor_id: str, update: "AdvisorUpdate") -> Advisor:
        """B9：编辑注册信息（姓名/专长方向）。时段与预约不受影响。"""
        for index, advisor in enumerate(deps.advisors):
            if advisor.advisor_id == advisor_id:
                edited = advisor.model_copy(update={
                    "name": update.name, "focus": update.focus,
                })
                deps.advisors[index] = edited
                return edited
        raise HTTPException(404, {"error": "unknown_advisor",
                                  "detail": f"未知顾问 {advisor_id}"})

    @implements("DELETE", "/advising/advisors/{advisor_id}", response_model=Advisor)
    def delete_advisor(advisor_id: str) -> Advisor:
        """B9：删除注册。有未完结预约（requested/confirmed）时 409——
        先处理学生的预约再删，不允许把别人的会面一起删掉。"""
        active = [
            b for b in deps.advisor_bookings
            if b.advisor_id == advisor_id
            and b.status in (AdvisorBookingStatus.REQUESTED,
                             AdvisorBookingStatus.CONFIRMED)
        ]
        if active:
            raise HTTPException(409, {
                "error": "advisor_has_active_bookings",
                "detail": f"该顾问还有 {len(active)} 条未完结预约——"
                          "先确认或取消这些预约再删除。",
            })
        for index, advisor in enumerate(deps.advisors):
            if advisor.advisor_id == advisor_id:
                deps.advisors.pop(index)
                return advisor
        raise HTTPException(404, {"error": "unknown_advisor",
                                  "detail": f"未知顾问 {advisor_id}"})

    @implements("POST", "/advising/advisors/{advisor_id}/slots/{slot_id}/availability",
                response_model=AdvisorSlot)
    def set_slot_availability(advisor_id: str, slot_id: str,
                              update: "SlotAvailabilityUpdate") -> AdvisorSlot:
        """R8-1：标记时段开放/不在。已被预约的时段 409——先处理预约再关门。"""
        for index, advisor in enumerate(deps.advisors):
            if advisor.advisor_id != advisor_id:
                continue
            for slot in advisor.slots:
                if slot.slot_id != slot_id:
                    continue
                if not update.available and _slot_taken(slot_id):
                    raise HTTPException(409, {
                        "error": "slot_booked",
                        "detail": "该时段已有学生预约——请先处理预约（确认/取消）"
                                  "再标记不在。",
                    })
                updated = slot.model_copy(update={"blocked": not update.available})
                deps.advisors[index] = advisor.model_copy(update={
                    "slots": tuple(
                        updated if s.slot_id == slot_id else s
                        for s in advisor.slots
                    ),
                })
                return updated
        raise HTTPException(404, {"error": "unknown_slot",
                                  "detail": f"未知时段 {advisor_id}/{slot_id}"})

    @implements("POST", "/students/{student_id}/advisor/bookings",
                response_model=AdvisorBooking)
    def book_advisor(student_id: str, booking: AdvisorBooking) -> AdvisorBooking:
        """大一下学期起可用。Year 1 被拒时给解释，不静默失败。

        Q（2026-07-31）：预约指向名录里的具体时段——被占的时段 409；
        一学期爽约满 3 次的学生 403（预约必到；不能来就提前 ≥1 天取消）。
        """
        student = _known_student(student_id)
        if booking.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        if student.year < 2:
            # Demo 时钟固定在秋季学期——Year 1 学生尚未到"下学期"
            raise HTTPException(403, {
                "error": "advisor_not_yet_available",
                "detail": "Advisor 服务从大一下学期起开放。你可以先用目标工作室"
                          "梳理方向，开放后再来预约。",
            })
        if _no_show_count(student_id) >= 3:
            raise HTTPException(403, {
                "error": "no_show_blacklisted",
                "detail": "本学期已累计 3 次预约未到，暂停预约资格至学期结束。"
                          "预约了不能来，请至少提前 1 天取消——那个时段本可以留给别人。",
            })
        if booking.slot_id is not None:
            known = any(
                slot.slot_id == booking.slot_id
                for advisor in deps.advisors for slot in advisor.slots
            )
            if not known:
                raise HTTPException(404, {"error": "unknown_slot",
                                          "detail": f"未知时段 {booking.slot_id}"})
            # R8-1：Advisor 标记"不在"的时段不可约——学生端本来看不到它，
            # 直连 API 也一样被拒（前端隐藏不是边界，服务端才是）
            if any(slot.slot_id == booking.slot_id and slot.blocked
                   for advisor in deps.advisors for slot in advisor.slots):
                raise HTTPException(409, {
                    "error": "slot_unavailable",
                    "detail": "该时段 Advisor 不开放预约。",
                })
            if _slot_taken(booking.slot_id):
                raise HTTPException(409, {
                    "error": "slot_taken",
                    "detail": "这个时段刚被别人约走了——名录里的占用是实时的，换一个吧。",
                })
        normalized = booking.model_copy(update={
            "status": AdvisorBookingStatus.REQUESTED, "summary": None,
        })
        deps.advisor_bookings.append(normalized)
        return normalized

    @implements("POST",
                "/students/{student_id}/advisor/bookings/{booking_id}/cancel",
                response_model=AdvisorBooking)
    def cancel_advisor_booking(student_id: str, booking_id: str) -> AdvisorBooking:
        """取消须提前 ≥1 天；时段随即释放。幂等：已取消再取消原样返回。"""
        _known_student(student_id)
        index = next(
            (i for i, b in enumerate(deps.advisor_bookings)
             if b.booking_id == booking_id and b.student_id == student_id),
            None,
        )
        if index is None:
            raise HTTPException(404, {"error": "unknown_booking",
                                      "detail": f"未知预约 {booking_id}"})
        booking = deps.advisor_bookings[index]
        if booking.status is AdvisorBookingStatus.CANCELLED:
            return booking
        if booking.status in (AdvisorBookingStatus.COMPLETED,
                              AdvisorBookingStatus.NO_SHOW):
            raise HTTPException(422, {"error": "too_late_to_cancel",
                                      "detail": "会面已结束，无法取消。"})
        now = datetime.now(timezone.utc)
        if booking.requested_slot.start - now < timedelta(days=1):
            raise HTTPException(422, {
                "error": "too_late_to_cancel",
                "detail": "距会面不足 1 天，无法取消。届时未到会按爽约记录"
                          "（一学期 3 次将暂停预约资格）。",
            })
        cancelled = booking.model_copy(
            update={"status": AdvisorBookingStatus.CANCELLED})
        deps.advisor_bookings[index] = cancelled
        return cancelled

    @implements("POST", "/advising/bookings/{booking_id}/no-show",
                response_model=AdvisorBooking)
    def mark_no_show(booking_id: str) -> AdvisorBooking:
        """Advisor 标记爽约。时段随即释放；该生计数 +1，满 3 次暂停预约。"""
        index = next(
            (i for i, b in enumerate(deps.advisor_bookings)
             if b.booking_id == booking_id), None,
        )
        if index is None:
            raise HTTPException(404, {"error": "unknown_booking",
                                      "detail": f"未知预约 {booking_id}"})
        booking = deps.advisor_bookings[index]
        if booking.status is AdvisorBookingStatus.NO_SHOW:
            return booking
        marked = booking.model_copy(
            update={"status": AdvisorBookingStatus.NO_SHOW})
        deps.advisor_bookings[index] = marked
        return marked

    @implements("GET", "/students/{student_id}/advisor/bookings",
                response_model=list[AdvisorBooking])
    def my_advisor_bookings(student_id: str) -> list[AdvisorBooking]:
        _known_student(student_id)
        return [b for b in deps.advisor_bookings if b.student_id == student_id]

    @implements("GET", "/advising/bookings", response_model=list[AdvisorBooking])
    def advisor_queue() -> list[AdvisorBooking]:
        """Advisor 只看到预约本身（时段+学生想聊的主题）。

        反思原文、成绩、日历对这个角色是 403——由契约生成的 RBAC 表保证，
        与 curator 的隔离面板同一套机制。
        """
        return list(deps.advisor_bookings)

    def _find_booking(booking_id: str) -> int:
        for index, booking in enumerate(deps.advisor_bookings):
            if booking.booking_id == booking_id:
                return index
        raise HTTPException(404, {"error": "unknown_booking",
                                  "detail": f"未知预约 {booking_id}"})

    @implements("POST", "/advising/bookings/{booking_id}/confirm",
                response_model=AdvisorBooking)
    def confirm_booking(booking_id: str) -> AdvisorBooking:
        index = _find_booking(booking_id)
        confirmed = deps.advisor_bookings[index].model_copy(
            update={"status": AdvisorBookingStatus.CONFIRMED})
        deps.advisor_bookings[index] = confirmed
        return confirmed

    @implements("POST", "/advising/bookings/{booking_id}/summary",
                response_model=AdvisorBooking)
    def advisor_summary(booking_id: str, summary: AdvisorSummary) -> AdvisorBooking:
        """写总结 = 完成。契约禁止没有总结的 completed——顺序在类型层就定死了。"""
        index = _find_booking(booking_id)
        booking = deps.advisor_bookings[index]
        if summary.booking_id != booking_id:
            raise HTTPException(422, "路径中的预约与请求体不一致")
        if booking.status is not AdvisorBookingStatus.CONFIRMED:
            raise HTTPException(409, {"error": "not_confirmed",
                                      "detail": "先确认预约、完成会面，再写总结"})
        completed = booking.model_copy(update={
            "status": AdvisorBookingStatus.COMPLETED, "summary": summary,
        })
        deps.advisor_bookings[index] = completed
        return completed

    @implements("POST", "/students/{student_id}/event-feedback",
                response_model=EventQualityFeedback)
    def submit_event_feedback(student_id: str,
                              form: "StudentEventFeedbackForm") -> EventQualityFeedback:
        """C 轨多维评分。转换发生在服务端（A1 的职责位）：

        进聚合的载荷**没有 student_id、没有自由文本**——cohort 三维全是
        受约束类型，个人匹配只以 FitTag 枚举出域（Personal-vs-Global 分离）。
        """
        from campuspath_contracts.reflection import (
            CohortDims, DimensionRating, QualityDimension,
        )

        student = _known_student(student_id)
        opportunity = next(
            (o for o in [*deps.opportunities, *deps.expired_opportunities]
             if o.opportunity_id == form.subject_id), None,
        )
        if opportunity is None:
            raise HTTPException(404, {"error": "unknown_opportunity",
                                      "detail": f"未知机会 {form.subject_id}"})
        program = student.program_id.upper()
        school = ("ENGG" if program.startswith("BENG")
                  else "SCI" if program.startswith("BSC") else "BM")
        modes = getattr(student, "development_modes", ())
        development_mode = (
            max(modes, key=lambda m: m.weight).mode if modes
            else DevelopmentModeType.EXPLORATION
        )
        ratings = [
            DimensionRating(dimension=QualityDimension.CONTENT_DEPTH,
                            rating=form.content_depth),
            DimensionRating(dimension=QualityDimension.PRACTICAL_VALUE,
                            rating=form.practical_value),
        ]
        if form.organization is not None:
            ratings.append(DimensionRating(
                dimension=QualityDimension.ORGANIZATION, rating=form.organization))
        # 第 4 维（D 批）：预期兑现
        if form.expectation_match is not None:
            ratings.append(DimensionRating(
                dimension=QualityDimension.EXPECTATION_MATCH,
                rating=form.expectation_match))
        # 活动结束 + 2 个月停止收集统计（D 批用户裁定）
        if _stats_frozen_at(opportunity, datetime.now(timezone.utc)):
            raise HTTPException(409, {
                "error": "stats_frozen",
                "detail": "该活动已结束超过两个月，评分统计已停止收集",
            })
        # 扫码签到过 → 服务端回填「已验证出勤」（学生不用自证）
        verified = form.attended_verified or (
            student_id in deps.attendance.get(opportunity.opportunity_id, set())
        )
        feedback = EventQualityFeedback(
            feedback_id=f"FB-{form.subject_id}-{deps.memory.next_sequence()}",
            occurrence_id=opportunity.occurrence_id or opportunity.opportunity_id,
            series_id=opportunity.series_id,
            verified_attendance=verified,
            dimensions=tuple(sorted(ratings, key=lambda r: r.dimension.value)),
            fit_tags=(form.fit,),
            cohort_dims=CohortDims(
                school=school, year_level=student.year,
                development_mode=development_mode,
            ),
            submitted_at=datetime.now(timezone.utc),
        )
        deps.quality_feedback.append(feedback)
        return feedback

    @implements("POST", "/students/{student_id}/matches/refresh",
                response_model=list[MatchResult])
    def refresh_matches(student_id: str,
                        limit: int = Query(10, ge=1, le=50)) -> list[MatchResult]:
        """学生主动刷新。每天 3 次——推荐的变化来自数据变化，不来自反复摇骰子。"""
        _known_student(student_id)
        today = date.today()
        used = deps.match_refreshes.get((student_id, today), 0)
        if used >= 3:
            raise HTTPException(429, {
                "error": "refresh_limit_reached",
                "detail": "今天的手动刷新已用完（3 次）。明天会自动重算一次。",
            })
        deps.match_refreshes[(student_id, today)] = used + 1
        deps.match_cache[student_id] = (today, _compute_matches(student_id, 50))
        return deps.match_cache[student_id][1][:limit]

    @implements("GET", "/students/{student_id}/reflections",
                response_model=list[Reflection])
    def my_reflections(student_id: str) -> list[Reflection]:
        """R4-E：学生回看自己的反思（私有域唯一出口，与 /notes 同性质）。"""
        _known_student(student_id)
        return list(deps.reflections.get(student_id, ()))

    @implements("POST", "/students/{student_id}/reflections",
                response_model=ReflectionResult)
    def submit_reflection(student_id: str, reflection: Reflection) -> ReflectionResult:
        """A1 的三轨输出。原文留在 Private Vault，只有结构化产物出域。

        **保存反思不依赖模型**——存档是确定性动作，模型只做增值：
        有后端时，A1 从**非私有**字段（private_text 不进模型）提炼
        Profile 候选，产出一条恒为 pending 的提案（B3 由 A1 的方法签名保证）。
        模型不可用或输出不可解析 → 反思照存，提案为空，不装作提炼过。
        """
        if reflection.student_id != student_id:
            raise HTTPException(422, "路径中的学生与请求体不一致")
        _store(student_id)          # 学生必须存在
        deps.reflections.setdefault(student_id, []).append(reflection)

        # O（2026-07-31）：活动闭环的最后一步——参加过的活动**写完反思**才算完成，
        # 完成即落一条证据记录；成长动态跟踪按活动的要求类别把它挂到能力条目下。
        # 幂等：同一条反思只产生一条证据。verification 如实为 self_reported。
        if reflection.subject_id.startswith("OPP-"):
            evidence_id = f"EV-REFL-{reflection.reflection_id}"
            if not any(e.evidence_id == evidence_id for e in deps.evidence):
                subject = next(
                    (o for o in deps.opportunities
                     if o.opportunity_id == reflection.subject_id), None)
                deps.evidence.append(EvidenceRecord(
                    evidence_id=evidence_id,
                    student_id=student_id,
                    evidence_type="other",
                    source=reflection.subject_id,
                    # 证据的实体是那条反思本身，留在 Private Vault，按学生前缀隔离
                    object_ref=f"{student_id}/reflections/{reflection.reflection_id}",
                    issuer=subject.organizer if subject is not None else None,
                    obtained_at=deps.today,
                ))
                # 北极星指标 VGA（Spec §17.1，2026-08-04 落地）：反思闭环是
                # "行动+证据"齐备的唯一确定性链——完成活动且写下反思，才铸
                # 一条 verified_growth 事件（契约校验器强制挂证据）。点击/
                # 收藏/报名不进这里，正合"不奖励忙碌本身"。幂等：与证据同
                # 一个 if 块，同反思重交不重复计。
                deps.actions.setdefault(student_id, []).append(ActionEvent(
                    event_id=f"ACT-VGA-{reflection.reflection_id}",
                    student_id=student_id,
                    action_type=ActionType.COMPLETE,
                    subject_id=reflection.subject_id,
                    timestamp=datetime.now(timezone.utc),
                    evidence_ids=(evidence_id,),
                    verified_growth=True,
                ))
                # R5-G2（2026-08-01）：闭环记录同时**确定性**生成一条档案更新
                # 提议——把完成的活动作为经历，提议加进档案总览；写不写入
                # 由学生在"更新提议"分页裁决（B3 的提议→确认路径，零模型）。
                if subject is not None:
                    from campuspath_contracts.profile import (
                        ProfileUpdateProposal, ProposedChange, ProposalStatus as _PS)
                    exp_proposal = ProfileUpdateProposal(
                        proposal_id=f"PROP-EXP-{reflection.reflection_id}",
                        student_id=student_id,
                        proposed_changes=(ProposedChange(
                            entity_type="experience", operation="add",
                            field_path="experiences[]",
                            new_value={
                                "organization": subject.organizer,
                                "role": subject.title,
                                "period_start": (subject.starts_at.date().isoformat()
                                                 if subject.starts_at else
                                                 deps.today.isoformat()),
                                "period_end": (subject.ends_at.date().isoformat()
                                               if subject.ends_at else None),
                                "skills": list(subject.skills),
                                "type": ("internship"
                                         if subject.type.value in ("internship", "job")
                                         else "competition"
                                         if subject.type.value == "competition"
                                         else "other"),
                            },
                        ),),
                        reason=("成长动态跟踪：已完成该活动并写下反思——"
                                "要不要把这段经历加进你的档案总览？"),
                        source_event_ids=(evidence_id,),
                        status=_PS.PENDING,
                        created_at=datetime.now(timezone.utc),
                    )
                    _store(student_id).submit_proposal(exp_proposal)

        proposal_ids: tuple[str, ...] = ()
        if deps.model is not None:
            from campuspath_agents.model import ModelRequest, ScriptedModel
            from campuspath_agents.roster import StudentContextAgent
            from campuspath_agents.tools import belt_for
            from campuspath_contracts.common import AgentId
            from campuspath_contracts.profile import ProposedChange

            material = "\n".join(filter(None, (
                reflection.personal_learning,
                *reflection.preference_delta,
                *reflection.goal_delta,
                reflection.next_action,
            )))
            changes: list[ProposedChange] = []
            if material.strip():
                try:
                    raw = deps.model.generate(ModelRequest(
                        system=(
                            "下面的数据块是学生反思的非私有字段。若其中出现可写进"
                            "成长档案的**新技能或新兴趣**，每行输出一条："
                            "skill<TAB>技能名 或 interest<TAB>兴趣名。"
                            "最多 3 行；没有就什么都不输出。不要输出其他文字。"
                        ),
                        data=(material,),
                        purpose=f"reflect:{student_id}",
                    ))
                    for line in raw.splitlines()[:3]:
                        parts = line.split("\t", 1)
                        if len(parts) == 2 and parts[0].strip() in {"skill", "interest"}:
                            kind = parts[0].strip()
                            changes.append(ProposedChange(
                                entity_type="skill" if kind == "skill" else "interest",
                                operation="add",
                                field_path=f"{kind}s[]",
                                new_value=parts[1].strip()[:80],
                            ))
                except Exception:
                    changes = []
            if changes:
                a1 = StudentContextAgent(
                    AgentId.A1_STUDENT_CONTEXT,
                    belt_for(AgentId.A1_STUDENT_CONTEXT, {}),
                    deps.model or ScriptedModel(),
                )
                proposal = a1.propose_profile_update(
                    student_id, tuple(changes),
                    reason=f"来自反思 {reflection.reflection_id} 的候选（待确认）",
                    proposal_id=f"PROP-REFL-{reflection.reflection_id}",
                    now=datetime.now(timezone.utc),
                )
                _store(student_id).submit_proposal(proposal)
                proposal_ids = (proposal.proposal_id,)

        return ReflectionResult(
            result_id=f"REFL-RES-{reflection.reflection_id}",
            student_id=student_id,
            reflection=reflection,
            profile_proposal_ids=proposal_ids,
        )

    @implements("POST", "/ops/opportunity-drafts", response_model=OpportunityDraft)
    def submit_draft(draft: OpportunityDraft) -> OpportunityDraft:
        """A4 的唯一出口。草稿进不了 Catalog，也进不了任何学生上下文。"""
        if draft.extracted.publication_status not in {
            PublicationStatus.DRAFT, PublicationStatus.SUBMITTED
        }:
            raise HTTPException(422, {"error": "schema_gate_failed",
                                      "detail": "A4 没有发布权（§8.9.1）"})
        # 抽取发生在连接器侧（extract_draft，见 WP3 摄入链）；这里是 A4 的出口：
        # 落草稿、判重，然后停在审核队列。判重是确定性的（与目录标题精确比对），
        # 不需要模型——"这条已经有了"必须每次都得出同一个结论。
        duplicate = next(
            (o.opportunity_id for o in deps.opportunities
             if o.title == draft.extracted.title
             and o.organizer == draft.extracted.organizer),
            None,
        )
        if duplicate is not None and draft.duplicate_of is None:
            draft = draft.model_copy(update={"duplicate_of": duplicate})
            draft = type(draft).model_validate(draft.model_dump())
        deps.opportunity_drafts.append(draft)
        return draft

    @implements("POST", "/ops/sources/ingest", response_model=OpportunityDraft)
    def ingest_source(request: SourceIngestRequest) -> OpportunityDraft:
        """R7-D：摄入链上线——原始内容经 **A4 类本体**抽取为草稿。

        字段解析是确定性的（``key: value`` 行）；模型只收数据块——
        外部内容一个字都进不了 system prompt（§8.9.1）。产出走与
        submit_draft 同一道闸门：判重、状态门、止步审核队列。
        """
        from campuspath_agents.model import ScriptedModel
        from campuspath_agents.roster import OpportunityAgent
        from campuspath_agents.tools import belt_for
        from campuspath_contracts.common import Provenance

        fields: dict[str, str] = {}
        for line in request.raw_content.splitlines():
            key, sep, value = line.partition(":")
            if sep and key.strip().lower() in {
                "title", "organizer", "category", "url"
            }:
                fields.setdefault(key.strip().lower(), value.strip())
        title = fields.get("title")
        if not title:
            raise HTTPException(422, {"error": "schema_gate_failed",
                                      "detail": "原始内容没有可辨识的 title 行"})

        now = datetime.now(timezone.utc)
        seq = len(deps.opportunity_drafts) + 1
        provenance = Provenance(
            source=request.source_id,
            source_url=request.source_url,
            retrieved_at=now,
            published_at=None,
            parser_version="ops-ingest/0.1",
            evidence_snippet=request.raw_content[:200],
            confidence=0.6,   # 行解析：结构可靠、语义未审
        )
        extracted = Opportunity(
            opportunity_id=f"OPP-ING-{seq:04d}",
            type="event",
            title=title,
            organizer=fields.get("organizer", "未知来源组织"),
            occurrence_id=None, series_id=None,
            category_tags=(fields.get("category", "workshop"),),
            requirement_categories=(), eligibility_rules=(),
            deadline=None, starts_at=None, ends_at=None,
            workload_hours_total=None, skills=(),
            official_url=fields.get("url") or request.source_url
            or "https://example.invalid/ingest",
            source_id=request.source_id,
            provenance=provenance,
            publication_status=PublicationStatus.DRAFT,
            last_verified_at=None,
            title_localized=None, organizer_localized=None,
            organizer_category="student_club",
        )
        # 无真实模型时给 extract 一个预设应答：字段来源是上面的确定性
        # 行解析，模型应答只是语义辅助——降级不改变产出，也不假装调过。
        a4 = OpportunityAgent(
            AgentId.A4_OPPORTUNITY, belt_for(AgentId.A4_OPPORTUNITY, {}),
            deps.model
            or ScriptedModel({f"extract:{request.source_id}": "ack"}),
        )
        draft = a4.extract_draft(
            request.source_id, request.raw_content, extracted,
            draft_id=f"DRAFT-ING-{seq:04d}", provenance=provenance,
        )
        return submit_draft(draft)

    # ── 契约里其余端点：自动补成 501 ────────────────────────────────
    def _register_pending(method: str, full_path: str) -> None:
        path = full_path.removeprefix("/v1")

        async def handler(request: Request) -> JSONResponse:
            return JSONResponse(
                status_code=501,
                content={
                    "error": "not_implemented",
                    "detail": (
                        f"{method} {full_path} 已在契约中声明，但实现尚未接入"
                        "（多数依赖 A0–A5，见 WP6）。"
                        "刻意返回 501 而不是空数组——空数组会被当成「没有结果」。"
                    ),
                },
            )

        router.add_api_route(path, handler, methods=[method],
                             name=f"pending_{method}_{path}", include_in_schema=True)

    pending: list[tuple[str, str]] = []
    for endpoint in API_ENDPOINTS:
        key = (endpoint.method.upper(), endpoint.path)
        if key in implemented:
            continue
        pending.append(key)
        _register_pending(*key)

    # 路由索引：`(method, 模板, 正则)`。中间件按它判定，
    # 因此"新加端点忘了配角色"会在 rbac.check 里被拒，而不是悄悄放行。
    route_index: list[tuple[str, str, re.Pattern[str]]] = [
        (method, path, _template_regex(path))
        for method, path in sorted(implemented | set(pending))
    ]

    # ── RBAC + 合成标记 ─────────────────────────────────────────────
    @app.middleware("http")
    async def enforce_role(request: Request, call_next):
        template = _template_for(request)
        if template is not None:
            decision = rbac.check(
                request.method, template,
                rbac.parse_role(request.headers.get(rbac.ROLE_HEADER)),
            )
            if not decision.allowed:
                return JSONResponse(
                    status_code=403,
                    content={"error": "role_denied", "detail": decision.reason},
                    headers={"X-CampusPath-Data": SYNTHETIC_NOTICE},
                )
        response = await call_next(request)
        response.headers["X-CampusPath-Data"] = SYNTHETIC_NOTICE
        return response

    def _template_for(request: Request) -> str | None:
        for method, template, pattern in route_index:
            if request.method == method and pattern.match(request.url.path):
                return template
        return None

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {
            "status": "ok",
            "contracts_version": CONTRACTS_VERSION,
            "declared_endpoints": len(API_ENDPOINTS),
            "implemented": len(implemented),
            "pending": sorted(f"{m} {p}" for m, p in pending),
            # 模型后端是否可用。三个端点依赖它，没有就返回 503 而非 501。
            "model_backend": "configured" if deps.model is not None else "unavailable",
            "notice": SYNTHETIC_NOTICE,
        }

    app.include_router(router)
    app.state.implemented = frozenset(implemented)
    app.state.pending = frozenset(pending)
    #: 契约覆盖的证据。测试用它做双向断言，不去猜框架把路由放哪了。
    app.state.route_index = tuple((m, p) for m, p, _ in route_index)
    return app


app = create_app()
