"""Agent ↔ 服务的 OpenAPI 契约（Plan WP1 产出之一）。

**声明式而非从实现反推。** 常见做法是先写 FastAPI 再导出 openapi.json——
那样契约永远落后于实现一步，而 WP1 的全部意义就是让契约先于实现存在。
这里反过来：路由表在本模块里定义，WP4/WP5 的 FastAPI 应用必须实现它，
由 ``tests/test_openapi_contract.py`` 校验两者一致。

每个端点都声明 ``roles``（RBAC）与 ``errors``。其中两个错误码是硬契约：

* ``422 unbacked_validation_id`` —— A5 输出缺失或伪造凭据时 API 必须拒绝（B8）；
* ``403 scope_violation`` —— 越权投稿必须被拦截且记录（B7）。
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel

from .common import ActorRole, CONTRACTS_VERSION

SCHEMA_REF_TEMPLATE = "#/components/schemas/{model}"


@dataclasses.dataclass(frozen=True)
class Endpoint:
    method: str
    path: str
    summary: str
    response_model: str
    request_model: str | None = None
    roles: tuple[ActorRole, ...] = (ActorRole.STUDENT,)
    errors: tuple[tuple[int, str], ...] = ()
    response_is_list: bool = False


#: 学生侧
_STUDENT: tuple[Endpoint, ...] = (
    Endpoint("GET", "/v1/students/{student_id}/profile", "读取 Canonical Profile", "StudentProfile"),
    Endpoint(
        "GET", "/v1/students/{student_id}/course-recommendations",
        "推荐选修课（规则初筛→AI 复筛；必修课与先修未满足的课不出现；"
        "AI 拿不准的标'待用户确认'。当日缓存）",
        "CourseRecommendation", response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/catalog/courses",
        "课程目录详情（简介 / 先修原文 / 官方来源链接；按学科前缀过滤）",
        "CourseCatalogItem", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/profile/self-edit",
        "学生本人直接编辑档案（技能标签 / 经历；B3 挡的是 Agent 暗改，不挡本人）",
        "StudentProfile", "ProfileSelfEdit",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/wellbeing/escalation",
        "预警升级判定（确定性阈值：连续睡眠不足/超载+反复拒延；不推断未声明数据）",
        "WellbeingEscalation",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/wellbeing/assessment",
        "ISI + PSS-10 标准化自评计分与分流（零 LLM；筛查非诊断；R8-3：第一层自动联系"
        "自填 tutor——量表由学生本人提交即知情动作；第二层引导自选时段预约）",
        "WellbeingAssessmentResult", "WellbeingAssessmentRequest",
    ),
    Endpoint(
        "GET", "/v1/wellbeing/counseling/slots",
        "心理咨询可预约时段（R8-3：只从校方开放的工作时段生成）",
        "CounselingSlot", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/counseling-bookings",
        "第二层分流：预约心理咨询（专业/年级服务端回填，姓名/班级/联系方式自填）",
        "CounselingBooking", "CounselingBooking",
        errors=((409, "slot_taken"), (404, "unknown_slot")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/wellbeing/emergency",
        "第三层：紧急红按钮——跳过排队直连值班室电话；每学期 2 次，第 3 次拉黑一学期"
        "（拒绝响应仍附校园热线）",
        "EmergencyAccessResult",
        errors=((403, "emergency_blacklisted"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/profile/extras",
        "档案补充分区（教育/语言/出版物/荣誉/组织/爱好；学生自填，整体自述）",
        "ProfileExtras",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/profile/extras",
        "保存档案补充分区（整组替换；学生本人随时可改）",
        "ProfileExtras", "ProfileExtras",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/contacts",
        "重要联系人（辅导员/班主任/班长，学生自填；未填时返回空集合）",
        "ImportantContacts",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/contacts",
        "保存重要联系人（整组替换；学期内任意时间可改）",
        "ImportantContacts", "ImportantContacts",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/consents",
        "学生自助授权 / 撤销单项数据同意（服务端签发回执，B13）",
        "ConsentRecord", "ConsentUpdateRequest",
        errors=((403, "consent_scope_not_self_service"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/profile/proposals",
        "提交 Profile 更新建议（status 恒为 pending）",
        "ProfileUpdateProposal", "ProfileUpdateProposal",
        errors=((422, "unconfirmed_write"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/profile/proposals/{proposal_id}/decision",
        "学生确认 / 修改 / 拒绝（唯一的 Profile 写入入口，B3）",
        "ProfileChangeEvent", "ProfileUpdateProposal",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/profile/proposals",
        "待学生裁决的 Profile 更新提议（只读；写入仍必须走 decision）",
        "ProfileUpdateProposal", response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/evidence",
        "Evidence Portfolio（D1 页签；核验状态不被抹平）",
        "EvidenceRecord", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/evidence",
        "学生上传证据源文件（R5-C：demo 存 vault 引用与元数据；核验恒 self_reported）",
        "EvidenceRecord", "EvidenceRecord",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/notes",
        "学生自己的 Reflection 与 Note 原文。**只有学生本人这一个出口**——"
        "同一份文本向聚合方向在类型层就走不通（B10）",
        "Note", response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/experiences",
        "实习 / 社团 / 志愿等经历。反思要能挂到**具体哪一场**上，"
        "所以必须能被列出来选",
        "ExperienceRecord", response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/goals",
        "目标集合（主目标 + 候选目标，G3）", "Goal", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/goals",
        "学生**自己**设定目标：先选五类方向之一，再在该框架下写下具体终点。"
        "这不是 A1 的提议路径——目标是学生的，不需要谁来批准",
        "Goal", "Goal", errors=((409, "goal_role_conflict"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/availability",
        "五类 AvailabilityBlock。事件标题**只在学生授权了二级采集时**才出现，"
        "其余情况下只有起止、类型、来源（B5：采集不得超出授权层级）",
        "AvailabilityBlock", response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/memory",
        "Memory Center 的可见条目（查看/纠正/锁定/删除的前提）",
        "MemoryEntry", response_is_list=True,
    ),
    Endpoint("GET", "/v1/students/{student_id}/academic-state", "学业事实", "AcademicState"),
    Endpoint("GET", "/v1/students/{student_id}/degree-progress", "毕业进度", "DegreeProgress"),
    Endpoint(
        "GET", "/v1/students/{student_id}/course-candidates",
        "A2 标注的候选课程（无排序分数）", "AnnotatedCourseCandidate", response_is_list=True,
    ),
    Endpoint("GET", "/v1/students/{student_id}/gap-map", "Dynamic Gap Map（含 G3 共享缺口）", "DynamicGapMap"),
    Endpoint("GET", "/v1/students/{student_id}/growth-trajectory", "G4 成长曲线", "GrowthTrajectory"),
    Endpoint("GET", "/v1/students/{student_id}/vga-summary",
             "北极星指标 VGA 汇总（§17.1，逐月分桶）", "VgaSummary"),
    Endpoint(
        "GET", "/v1/students/{student_id}/capacity-snapshot",
        "CapacitySnapshot（Capacity & Calendar Service，零 LLM）", "CapacitySnapshot",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/matches",
        "机会匹配结果（含四态资格）；每条资格结论都须有能背书它的 validation_id",
        "MatchResult", response_is_list=True,
        errors=((422, "unbacked_validation_id"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/agent-trace",
        "A0 编排痕迹（R7-D）：最近的 WorkflowPlan 列表——已知意图走确定性路由表",
        "WorkflowPlan", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/goals/{goal_id}/decomposition/research",
        "现场 AI 拆解（用户提案 #27，2026-08-02；执行者是 A3）：起服务端后台研究任务"
        "（切页/关页不中断），"
        "产出标 ai_live 待核验；每人每日限 2 次",
        "DecompositionResearchJob",
        errors=((404, "unknown_goal"), (409, "research_already_running"),
                (429, "daily_research_limit"), (503, "model_backend_unavailable")),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/goals/{goal_id}/decomposition/research",
        "现场拆解任务进度（轮询）：三段式确定性进度汇报",
        "DecompositionResearchJob",
        errors=((404, "no_research_job"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/context-pack/evaluation",
        "国际学生规则包求值（B，2026-08-02）：信封 + Rules 签发凭据；"
        "未勾选/未同意时如实 needs_confirmation，不猜政策",
        "ContextPackEvaluation",
        errors=((404, "unknown_student"), (409, "intl_context_not_enabled")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/pathway",
        "提交 A5 生成的路径版本；每个 PlanItem 必须携带有效 validation_id",
        "PathwayVersion", "PathwayVersion",
        errors=((422, "unbacked_validation_id"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/pathway",
        "当前路径版本。D1 的三个时间视图**全部由它派生**，因此三者不可能互相矛盾",
        "PathwayVersion", errors=((404, "no_pathway_version"),),
    ),
    Endpoint(
        "DELETE", "/v1/students/{student_id}/pathway/items/{plan_item_id}",
        "「不参加」（2026-08-03）：从规划移除活动条目——留 DECLINE 审计事件、"
        "收走已写入的日历真实块、subject 入拒绝名单（重新生成不复活）",
        "PathwayVersion", errors=((404, "unknown_plan_item"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/schedule-proposals",
        "待学生裁决的排程预览（Action Center 的收件箱）",
        "ScheduleProposal", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/schedule-proposals",
        "排程预览（学生批准前不写日历）", "ScheduleProposal", "ScheduleProposal",
        errors=((409, "protected_block_conflict"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/calendar-actions",
        "经同意后写入日历（幂等）", "CalendarAction", "CalendarAction",
        errors=((403, "consent_missing"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/checkin",
        "扫码签到（D 批，2026-08-02）：验证活动 token → 记录真实参与；"
        "后续该活动的评分自动带 verified_attendance",
        "CheckinResult", "CheckinRequest",
        errors=((404, "unknown_opportunity"), (422, "invalid_checkin_token"),
                (409, "checkin_frozen"), (409, "checkin_not_open")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/actions", "记录行动事件", "ActionEvent", "ActionEvent",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/actions",
        "学生的行动事件。收藏（``save``）与加入计划（``add_to_pathway``）都在这里，"
        "**收藏列表不是另一张表**——它就是行动流的一个切片",
        "ActionEvent", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/replan-preview",
        "把一次变化换算成 AffectedScope：**只算会动哪些，不动**。"
        "学生看过之后自己决定要不要真的重排（§16.9）",
        "AffectedScope", "ReplanRequest",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/reflections",
        "我的反思记录（私有域；含自留评分，用于回看筛选）",
        "Reflection", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/reflections", "提交反思（原文留在私有域）",
        "ReflectionResult", "Reflection",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/memory/recall", "任务相关的最小召回",
        "MemoryRecallResult", "MemoryRecallQuery",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/availability",
        "学生在自己的周日历视图上添加行程（student_defined；可带标签/提醒）",
        "AvailabilityBlock", "AvailabilityBlock",
        errors=((422, "not_student_defined"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/availability/{block_id}/update",
        "学生直接编辑一个时段（起止 / 标题 / 类型 / 提醒）；改完由学生决定要不要重排近两周",
        "AvailabilityBlock", "AvailabilityBlockPatch",
        errors=((404, "unknown_block"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/routine",
        "学生显式提交日常作息（睡眠 / 三餐 → 每天的保护时段块；§16.8.2 不从日历反推）",
        "CapacitySnapshot", "RoutineRequest",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/availability/{block_id}/remove",
        "删除误占用的时段（同步进来但其实没被占用的）；幂等",
        "AvailabilityBlock", errors=((404, "unknown_block"),),
    ),
    Endpoint(
        "GET", "/v1/catalog/programs",
        "本科专业四年课程要求（真实 HKUST ugprog/PDF 抓取：必修/选修组 + 毕业要求）",
        "ProgramCurriculum", response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/goals/{goal_id}/decomposition",
        "目标拆解：硬性 / 软性（带取证来源）/ 特殊约束三层（A3 按人群 Pack 产出）",
        "GoalDecomposition",
        errors=((404, "unknown_goal"), (422, "no_pack_for_mode")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/resume",
        "上传 Resume（md/txt/pdf）→ A1 提炼候选变更 → 恒为 pending 的提案，"
        "冲突项带 old_value 由学生逐项确认（B3）",
        "ProfileUpdateProposal", "ResumeUpload",
        errors=((422, "unreadable_resume"), (503, "model_backend_unavailable")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/advisor/bookings",
        "预约 Career Center Advisor（大一下学期起可用，服务端把关并解释）",
        "AdvisorBooking", "AdvisorBooking",
        errors=((403, "advisor_not_yet_available"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/advisor/bookings",
        "我的 Advisor 预约（含会后关键建议）",
        "AdvisorBooking", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/advisor/bookings/{booking_id}/cancel",
        "取消预约（须提前 ≥1 天，时段随即释放给他人；晚于此按爽约计）",
        "AdvisorBooking",
        errors=((404, "unknown_booking"), (422, "too_late_to_cancel")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/event-feedback",
        "C 轨多维评分：学生表单 → 服务端转为去标识 EventQualityFeedback（§8.9.2）",
        "EventQualityFeedback", "StudentEventFeedbackForm",
        errors=((404, "unknown_opportunity"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/matches/refresh",
        "学生主动重算推荐（每天限 3 次；跨天后 GET 自动重算一次）",
        "MatchResult", response_is_list=True,
        errors=((429, "refresh_limit_reached"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/memory/{memory_id}/correction",
        "纠正一条记忆：产生新条目并取代旧条目，旧条目留痕（§8.6，F17）",
        "MemoryEntry", "MemoryCorrection",
        errors=((404, "unknown_memory"), (409, "memory_locked")),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/memory/{memory_id}/lock",
        "锁定一条记忆：锁定后系统不得修改或取代（student_locked）",
        "MemoryEntry", errors=((404, "unknown_memory"),),
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/memory/{memory_id}/forget",
        "忘记一条记忆：条目被移除，移除本身留回执（F17）",
        "MemoryForgetReceipt", errors=((404, "unknown_memory"),),
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/export",
        "导出这个学生自己可见域的全部记录（F01 设置页承诺）",
        "StudentDataExport",
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/deletion-request",
        "删除我的数据：Demo 环境立即清除进程内个人数据并给回执",
        "DeletionReceipt",
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/wellbeing/signals",
        "Wellbeing 容量信号（Rules 判定，零 LLM）", "WellbeingCapacitySignal",
        response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/students/{student_id}/wellbeing/reminders",
        "两次提醒状态机的当前状态（§16.8.3）。**最多两次**——第三次不是"
        "「再提醒一下」，是 Alert Overload。文案全部来自固定模板，零 LLM",
        "WellbeingReminderEvent", response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/students/{student_id}/wellbeing/outreach",
        "学生主动请求的最小化 outreach（需有效同意）",
        "WellbeingOutreachRequest", "WellbeingOutreachRequest",
        errors=((403, "consent_missing"), (422, "field_not_whitelisted")),
    ),
    Endpoint(
        "GET", "/v1/catalog/opportunities", "资讯广场公开目录（校方管理端只读监看同用此端点）",
        "Opportunity", response_is_list=True,
        roles=(ActorRole.STUDENT, ActorRole.CAREER_CENTER_ADMIN, ActorRole.CURATOR),
    ),
    Endpoint(
        "GET", "/v1/catalog/opportunities/{opportunity_id}/why-not-recommended",
        "为什么没推荐（资讯广场解释）", "EligibilityExplanation",
    ),
)

#: 规则引擎（零 LLM，A5 通过它取得 validation_id）
_RULES: tuple[Endpoint, ...] = (
    Endpoint(
        "POST", "/v1/rules/validate", "校验一条约束并签发 validation_id",
        "ConstraintValidation", "SourceRef", roles=(ActorRole.SYSTEM,),
    ),
    Endpoint(
        "GET", "/v1/rules/validations/{validation_id}", "回查已签发的校验",
        "ConstraintValidation", roles=(ActorRole.SYSTEM,),
        errors=((404, "validation_not_found"),),
    ),
)

#: Publisher / Career Center
_INSTITUTION: tuple[Endpoint, ...] = (
    Endpoint(
        "GET", "/v1/advising/advisors",
        "Career Center 顾问名录与可约时段（时段只报占用，不报占用者）",
        "Advisor", roles=(ActorRole.STUDENT, ActorRole.ADVISOR),
        response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/advising/advisors",
        "Advisor 自助注册（R8-1：顾问人员流动，注册即获得标准时段库存）",
        "Advisor", "AdvisorRegistration", roles=(ActorRole.ADVISOR,),
    ),
    Endpoint(
        "PUT", "/v1/advising/advisors/{advisor_id}",
        "B9：编辑 Advisor 注册信息（姓名/专长方向）",
        "Advisor", "AdvisorUpdate", roles=(ActorRole.ADVISOR,),
        errors=((404, "unknown_advisor"),),
    ),
    Endpoint(
        "DELETE", "/v1/advising/advisors/{advisor_id}",
        "B9：删除 Advisor 注册（有未完结预约时 409——先处理预约再删）",
        "Advisor", roles=(ActorRole.ADVISOR,),
        errors=((404, "unknown_advisor"), (409, "advisor_has_active_bookings")),
    ),
    Endpoint(
        "POST", "/v1/advising/advisors/{advisor_id}/slots/{slot_id}/availability",
        "Advisor 标记时段开放/不在（不在的时段学生端不可见；已被预约的 409）",
        "AdvisorSlot", "SlotAvailabilityUpdate", roles=(ActorRole.ADVISOR,),
        errors=((404, "unknown_slot"), (409, "slot_booked")),
    ),
    Endpoint(
        "GET", "/v1/advising/bookings",
        "Advisor 预约队列（只见预约与主题，**不见**学生反思/成绩/日历）",
        "AdvisorBooking", roles=(ActorRole.ADVISOR,), response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/advising/bookings/{booking_id}/no-show",
        "Advisor 标记爽约；一学期累计 3 次后系统拒绝该生新预约",
        "AdvisorBooking", roles=(ActorRole.ADVISOR,),
        errors=((404, "unknown_booking"),),
    ),
    Endpoint(
        "POST", "/v1/advising/bookings/{booking_id}/confirm",
        "Advisor 确认预约", "AdvisorBooking", roles=(ActorRole.ADVISOR,),
        errors=((404, "unknown_booking"),),
    ),
    Endpoint(
        "POST", "/v1/advising/bookings/{booking_id}/summary",
        "会后给学生发几条关键建议；预约随之标记 completed",
        "AdvisorBooking", "AdvisorSummary", roles=(ActorRole.ADVISOR,),
        errors=((404, "unknown_booking"), (409, "not_confirmed")),
    ),
    Endpoint(
        "POST", "/v1/publisher/submissions", "投稿", "PublicationSubmission", "PublicationSubmission",
        roles=(ActorRole.PUBLISHER,), errors=((403, "scope_violation"),),
    ),
    Endpoint(
        "GET", "/v1/publisher/submissions",
        "投稿人查看自己投稿的当前状态（退回修改在这里可见，可同 id 重投；"
        "demo 无 IdP，归属过滤随真实身份体系接入——与 advisor 归属绑定同一 backlog）",
        "PublicationSubmission", roles=(ActorRole.PUBLISHER,),
        response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/review/submissions", "审核队列（待裁决的投稿，R7-B）",
        "PublicationSubmission", roles=(ActorRole.REVIEWER, ActorRole.CAREER_CENTER_ADMIN),
        response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/review/submissions/{submission_id}/decisions", "审核决定（批准/退回/驳回）",
        "ModerationDecision", "ModerationDecision", roles=(ActorRole.REVIEWER, ActorRole.CAREER_CENTER_ADMIN),
        errors=((409, "invalid_transition"), (404, "unknown_submission")),
    ),
    Endpoint(
        "GET", "/v1/insights/resource-coverage", "资源覆盖洞察（仅聚合，低于阈值抑制）",
        "ResourceCoverageAggregate", roles=(ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN), response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/insights/event-quality", "活动质量趋势（仅聚合）",
        "EventQualityAggregate", roles=(ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN), response_is_list=True,
    ),
    Endpoint(
        "PUT", "/v1/catalog/opportunities/{opportunity_id}",
        "B10：编辑已发布活动（改期/改标题/改链接——审核批准后的生命周期管理）",
        "Opportunity", "OpportunityAdminEdit",
        roles=(ActorRole.CAREER_CENTER_ADMIN, ActorRole.CURATOR),
        errors=((404, "unknown_opportunity"),),
    ),
    Endpoint(
        "DELETE", "/v1/catalog/opportunities/{opportunity_id}",
        "B10：下架已发布活动（活动取消——从广场移除并留档，不物理删除）",
        "Opportunity",
        roles=(ActorRole.CAREER_CENTER_ADMIN, ActorRole.CURATOR),
        errors=((404, "unknown_opportunity"),),
    ),
    Endpoint(
        "GET", "/v1/ops/source-health", "Source Health 八项指标",
        "SourceHealth", roles=(ActorRole.CONNECTOR_ADMIN, ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN),
        response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/ops/opportunities/quality-summary",
        "D 批（2026-08-02）：广场活动的实时评分统计（去标识聚合，低于阈值抑制；"
        "活动结束+2 个月冻结）",
        "OccurrenceQualitySummary",
        roles=(ActorRole.CAREER_CENTER_ADMIN, ActorRole.CURATOR, ActorRole.REVIEWER),
        response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/ops/opportunities/{opportunity_id}/checkin",
        "每活动唯一签到码（二维码内容 = checkin_url）；attend_count = 真实参与人数。"
        "批准回执连带推送给 publisher（投稿台可见自己活动的二维码）",
        "EventCheckinInfo",
        roles=(ActorRole.CAREER_CENTER_ADMIN, ActorRole.CURATOR, ActorRole.PUBLISHER),
        errors=((404, "unknown_opportunity"),),
    ),
    Endpoint(
        "POST", "/v1/ops/quality-reports/{period}",
        "生成周期报告（weekly/monthly/term/year）：服务端后台任务 + 确定性分段进度，"
        "切页/关页不中断。**仅 career_center_admin**（用户裁定：其他角色一律 403）",
        "QualityReportJob",
        roles=(ActorRole.CAREER_CENTER_ADMIN,),
        errors=((404, "unknown_period"), (409, "report_already_running"),),
    ),
    Endpoint(
        "GET", "/v1/ops/quality-reports/{period}",
        "读取该周期最近一次报告任务（含完成的报告本体）。仅 career_center_admin",
        "QualityReportJob",
        roles=(ActorRole.CAREER_CENTER_ADMIN,),
        errors=((404, "no_report_job"),),
    ),
    Endpoint(
        "GET", "/v1/ops/agent-runtime",
        "Demo 运行时状态（F1）：Vertex Agent Engine 是否在跑 + 启停任务进度",
        "AgentRuntimeStatus",
        roles=(ActorRole.STUDENT, ActorRole.CAREER_CENTER_ADMIN, ActorRole.SECURITY_ADMIN),
    ),
    Endpoint(
        "POST", "/v1/ops/agent-runtime",
        "Demo 一键启停 Agent Engine（按小时计费——演示前启动、演示完关闭）。"
        "服务端后台任务，切页不中断；环境缺 gcloud/adk 时 503 如实",
        "AgentRuntimeStatus", "AgentRuntimeCommand",
        roles=(ActorRole.STUDENT, ActorRole.CAREER_CENTER_ADMIN, ActorRole.SECURITY_ADMIN),
        errors=((409, "runtime_transition_in_progress"),
                (503, "runtime_control_unavailable")),
    ),
    Endpoint(
        "GET", "/v1/ops/sources",
        "官方信息源注册表（C，2026-08-02）：真实/合成源同表登记、is_real_fetch 如实区分",
        "RegisteredSource", roles=(ActorRole.CONNECTOR_ADMIN, ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN),
        response_is_list=True,
    ),
    Endpoint(
        "POST", "/v1/ops/sources/{source_id}/refresh",
        "真实抓取该源并做内容哈希变更检测；官方域名白名单源的变更条目经 A4 抽取后直发广场"
        "（用户裁定 A），政策源变更产出政策更新提醒卡",
        "RegisteredSource", roles=(ActorRole.CONNECTOR_ADMIN, ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN),
        errors=((404, "unknown_source"), (409, "source_paused")),
    ),
    Endpoint(
        "POST", "/v1/ops/sources/refresh-all",
        "一键巡检：后台线程逐源真实抓取全部 active 真实源（2026-08-02 用户需求 C）；"
        "确定性 done/total 进度，同一时间仅一个巡检",
        "SourcesSweepJob", roles=(ActorRole.CONNECTOR_ADMIN, ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN),
        errors=((409, "sweep_already_running"),),
    ),
    Endpoint(
        "GET", "/v1/ops/sources/refresh-all",
        "一键巡检进度查询（轮询；切页不中断）",
        "SourcesSweepJob", roles=(ActorRole.CONNECTOR_ADMIN, ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN),
        errors=((404, "no_sweep_job"),),
    ),
    Endpoint(
        "GET", "/v1/wellbeing/outreach-queue", "Counseling 队列（与 Career Center 隔离）",
        "WellbeingOutreachRequest", roles=(ActorRole.WELLBEING_COORDINATOR,),
        response_is_list=True,
    ),
    Endpoint(
        "GET", "/v1/wellbeing/counseling-admin/hours",
        "咨询室工作时段（R8-3：学生端可预约时段的唯一来源）",
        "CounselingHours", roles=(ActorRole.WELLBEING_COORDINATOR,),
    ),
    Endpoint(
        "POST", "/v1/wellbeing/counseling-admin/hours",
        "设置咨询室工作时段", "CounselingHours", "CounselingHours",
        roles=(ActorRole.WELLBEING_COORDINATOR,),
    ),
    Endpoint(
        "GET", "/v1/wellbeing/counseling-admin/bookings",
        "咨询预约队列（含学生姓名/专业/年级/班级/联系方式）",
        "CounselingBooking", roles=(ActorRole.WELLBEING_COORDINATOR,),
        response_is_list=True,
    ),
)

#: Opportunity Ops Runtime（A4 的唯一出口）
_OPPORTUNITY_OPS: tuple[Endpoint, ...] = (
    Endpoint(
        "POST", "/v1/ops/opportunity-drafts", "A4 提交草稿（不等于发布）",
        "OpportunityDraft", "OpportunityDraft", roles=(ActorRole.SYSTEM,),
        errors=((422, "schema_gate_failed"),),
    ),
    Endpoint(
        "POST", "/v1/ops/sources/ingest",
        "外部源摄入（R7-D）：原始内容经 A4 抽取为草稿——唯一处理不可信输入的链路，"
        "内容只作数据块，产出止步审核队列",
        "OpportunityDraft", "SourceIngestRequest", roles=(ActorRole.SYSTEM,),
        errors=((422, "schema_gate_failed"),),
    ),
)

API_ENDPOINTS: tuple[Endpoint, ...] = _STUDENT + _RULES + _INSTITUTION + _OPPORTUNITY_OPS

#: 只有这些角色能读的端点前缀。RBAC 中间件（WP5）从这里取表。
ROLE_RESTRICTED_PREFIXES: dict[str, frozenset[ActorRole]] = {
    "/v1/insights/": frozenset({ActorRole.CURATOR, ActorRole.CAREER_CENTER_ADMIN}),
    "/v1/wellbeing/outreach-queue": frozenset({ActorRole.WELLBEING_COORDINATOR}),
    "/v1/wellbeing/counseling-admin/": frozenset({ActorRole.WELLBEING_COORDINATOR}),
    "/v1/review/": frozenset({ActorRole.REVIEWER, ActorRole.CAREER_CENTER_ADMIN}),
    "/v1/publisher/": frozenset({ActorRole.PUBLISHER}),
}


def _error_response(code: str) -> dict[str, Any]:
    return {
        "description": code,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["error"],
                    "properties": {
                        "error": {"type": "string", "const": code},
                        "detail": {"type": "string"},
                    },
                }
            }
        },
    }


def build_openapi(models: dict[str, type[BaseModel]]) -> dict[str, Any]:
    """从路由表与模型集合构建 OpenAPI 3.1 文档。

    输出是确定性的（键序固定），因此可以直接进版本库并用 diff 审查契约变更。
    """
    components: dict[str, Any] = {}
    for name in sorted(models):
        schema = models[name].model_json_schema(ref_template=SCHEMA_REF_TEMPLATE)
        for nested_name, nested in sorted(schema.pop("$defs", {}).items()):
            components.setdefault(nested_name, nested)
        components[name] = schema

    paths: dict[str, Any] = {}
    for endpoint in API_ENDPOINTS:
        if endpoint.response_model not in components:
            raise KeyError(f"{endpoint.path} 引用了未定义的模型 {endpoint.response_model}")
        response_schema: dict[str, Any] = {"$ref": SCHEMA_REF_TEMPLATE.format(model=endpoint.response_model)}
        if endpoint.response_is_list:
            response_schema = {"type": "array", "items": response_schema}

        operation: dict[str, Any] = {
            "summary": endpoint.summary,
            "operationId": f"{endpoint.method.lower()}_{endpoint.path.strip('/').replace('/', '_').replace('{', '').replace('}', '')}",
            "x-allowed-roles": [r.value for r in endpoint.roles],
            "responses": {
                "200": {
                    "description": "OK",
                    "content": {"application/json": {"schema": response_schema}},
                },
                **{str(code): _error_response(name) for code, name in endpoint.errors},
            },
        }
        if endpoint.request_model is not None:
            if endpoint.request_model not in components:
                raise KeyError(f"{endpoint.path} 引用了未定义的请求模型 {endpoint.request_model}")
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {"$ref": SCHEMA_REF_TEMPLATE.format(model=endpoint.request_model)}
                    }
                },
            }
        params = [
            {
                "name": part[1:-1],
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
            for part in endpoint.path.split("/")
            if part.startswith("{") and part.endswith("}")
        ]
        if params:
            operation["parameters"] = params
        paths.setdefault(endpoint.path, {})[endpoint.method.lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "CampusPath API",
            "version": CONTRACTS_VERSION,
            "description": (
                "契约先行：本文档由 campuspath_contracts.openapi 生成，"
                "是实现必须满足的合同，不是从实现反推的文档。"
            ),
        },
        "paths": dict(sorted(paths.items())),
        "components": {"schemas": dict(sorted(components.items()))},
    }
