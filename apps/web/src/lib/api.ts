/**
 * `/v1` 的类型化客户端。
 *
 * 两条纪律：
 *
 * 1. **响应类型全部来自 `contracts/generated/campuspath-api.d.ts`**——
 *    那份文件由同一份 OpenAPI 生成。前端不允许自己再声明一遍后端的形状，
 *    否则契约就有了第二个版本。
 * 2. **404 / 503 不是"错误"，是有含义的答案**：503 表示"这条路做完了但依赖不可用"
 *    （没有 ADC 的 A5），404 表示"这个学生现在真的没有这个东西"。
 *    把两者都渲染成"加载失败"会让人以为前端坏了。
 */

import type { components } from "@contracts/campuspath-api";

export type Schemas = components["schemas"];

export type StudentProfile = Schemas["StudentProfile"];
export type EvidenceRecord = Schemas["EvidenceRecord"];
export type Note = Schemas["Note"];
export type ExperienceRecord = Schemas["ExperienceRecord"];
export type Goal = Schemas["Goal"];
export type AvailabilityBlock = Schemas["AvailabilityBlock"];
export type MemoryEntry = Schemas["MemoryEntry"];
export type ProfileUpdateProposal = Schemas["ProfileUpdateProposal"];
export type AcademicState = Schemas["AcademicState"];
export type DegreeProgress = Schemas["DegreeProgress"];
export type AnnotatedCourseCandidate = Schemas["AnnotatedCourseCandidate"];
export type DynamicGapMap = Schemas["DynamicGapMap"];
export type GrowthTrajectory = Schemas["GrowthTrajectory"];
export type CapacitySnapshot = Schemas["CapacitySnapshot"];
export type WellbeingCapacitySignal = Schemas["WellbeingCapacitySignal"];
export type Opportunity = Schemas["Opportunity"];
export type MatchResult = Schemas["MatchResult"];
export type EligibilityExplanation = Schemas["EligibilityExplanation"];
export type PathwayVersion = Schemas["PathwayVersion"];
export type PlanItem = Schemas["PlanItem"];
export type ScheduleProposal = Schemas["ScheduleProposal"];
export type ActionEvent = Schemas["ActionEvent"];
export type AffectedScope = Schemas["AffectedScope"];
export type ReplanRequest = Schemas["ReplanRequest"];
export type Reflection = Schemas["Reflection"];
export type ReflectionResult = Schemas["ReflectionResult"];
export type ProfileChangeEvent = Schemas["ProfileChangeEvent"];
export type CalendarAction = Schemas["CalendarAction"];
export type ConsentRecord = Schemas["ConsentRecord"];
export type ConsentUpdateRequest = Schemas["ConsentUpdateRequest"];
export type CourseCatalogItem = Schemas["CourseCatalogItem"];
export type AvailabilityBlockPatch = Schemas["AvailabilityBlockPatch"];
export type CourseRecommendation = Schemas["CourseRecommendation"];
export type ProfileSelfEdit = Schemas["ProfileSelfEdit"];
export type ImportantContacts = Schemas["ImportantContacts"];
export type ProfileExtras = Schemas["ProfileExtras"];
export type WellbeingEscalation = Schemas["WellbeingEscalation"];
export type WellbeingAssessmentResult = Schemas["WellbeingAssessmentResult"];
export type RoutineRequest = Schemas["RoutineRequest"];
export type GoalDecomposition = Schemas["GoalDecomposition"];
export type LocalizedText = Schemas["LocalizedText"];
export type SourceHealth = Schemas["SourceHealth"];
export type ResourceCoverageAggregate = Schemas["ResourceCoverageAggregate"];
export type EventQualityAggregate = Schemas["EventQualityAggregate"];
export type WellbeingOutreachRequest = Schemas["WellbeingOutreachRequest"];
export type WellbeingReminderEvent = Schemas["WellbeingReminderEvent"];
export type PublicationSubmission = Schemas["PublicationSubmission"];
export type ModerationDecision = Schemas["ModerationDecision"];

/** 同源代理，见 `next.config.ts` 的 rewrites。浏览器因此不需要 CORS。 */
export const API_BASE = "/api";

/** 授权层的角色声明头。真实部署换成从 IAM 断言取，判定逻辑不变。 */
export const ROLE_HEADER = "X-CampusPath-Role";

/**
 * 当前会话的角色。**默认 student**——忘了设等于权限最小。
 *
 * 这是 Demo 的角色切换，不是登录：真实部署里角色来自 IAM 断言，
 * 前端根本无权声明。放在模块级而不是每个调用点传，是为了让
 * "这次请求用什么身份"只有一个出处——散在各处的 role 参数
 * 迟早会有一处忘了改，而那一处就是隔离测试测不到的地方。
 */
let _role = "student";

export function setRole(role: string): void {
  _role = role;
}

export function currentRole(): string {
  return _role;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly body: unknown,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
  /** 服务端做完了，但它依赖的东西现在不可用（例如没有 ADC 的 Vertex 后端）。 */
  get isUnavailable() {
    return this.status === 503;
  }
  /** 这个学生现在真的没有这个东西——空状态，不是故障。 */
  get isMissing() {
    return this.status === 404;
  }
}

async function request<T>(
  path: string,
  init: RequestInit & { role?: string } = {},
): Promise<T> {
  const { role = _role, ...rest } = init;
  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      [ROLE_HEADER]: role,
      ...(rest.headers ?? {}),
    },
  });
  const text = await response.text();
  const body = text ? safeJson(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, body, `${response.status} ${path}`);
  }
  return body as T;
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

const s = (studentId: string) => `/v1/students/${encodeURIComponent(studentId)}`;

/** 校方 / Publisher 侧的端点。角色由 setRole 决定，这里不再各自传。 */
export const institution = {
  sourceHealth: () => request<SourceHealth[]>("/v1/ops/source-health"),
  /** 活动实时评分统计（D 批）：去标识聚合，低于阈值抑制 */
  qualitySummary: () =>
    request<Schemas["OccurrenceQualitySummary"][]>("/v1/ops/opportunities/quality-summary"),
  /** 每活动唯一签到码（二维码内容 = checkin_url） */
  checkinInfo: (opportunityId: string) =>
    request<Schemas["EventCheckinInfo"]>(
      `/v1/ops/opportunities/${encodeURIComponent(opportunityId)}/checkin`),
  /** 周期报告（仅 career_center_admin）：后台任务 + 轮询 */
  startQualityReport: (period: string) =>
    request<Schemas["QualityReportJob"]>(
      `/v1/ops/quality-reports/${period}`, { method: "POST" }),
  qualityReportStatus: (period: string) =>
    request<Schemas["QualityReportJob"]>(`/v1/ops/quality-reports/${period}`),
  /** 官方信息源注册表（C，2026-08-02）：真实/mock 同表、is_real_fetch 如实区分 */
  sources: () => request<Schemas["RegisteredSource"][]>("/v1/ops/sources"),
  /** 真实抓取 + 变更检测；官方白名单源变更直发广场，政策源变更出提醒卡 */
  refreshSource: (sourceId: string) =>
    request<Schemas["RegisteredSource"]>(
      `/v1/ops/sources/${encodeURIComponent(sourceId)}/refresh`,
      { method: "POST" },
    ),
  /** 一键巡检全部真实源（2026-08-02 用户需求 C）：后台任务 + 轮询进度 */
  startSourcesSweep: () =>
    request<Schemas["SourcesSweepJob"]>("/v1/ops/sources/refresh-all",
      { method: "POST" }),
  sourcesSweepStatus: () =>
    request<Schemas["SourcesSweepJob"]>("/v1/ops/sources/refresh-all"),
  advisorQueue: () => request<Schemas["AdvisorBooking"][]>("/v1/advising/bookings"),
  registerAdvisor: (registration: Schemas["AdvisorRegistration"]) =>
    request<Schemas["Advisor"]>("/v1/advising/advisors", {
      method: "POST",
      body: JSON.stringify(registration),
    }),
  updateAdvisor: (advisorId: string, update: Schemas["AdvisorUpdate"]) =>
    request<Schemas["Advisor"]>(
      `/v1/advising/advisors/${encodeURIComponent(advisorId)}`,
      { method: "PUT", body: JSON.stringify(update) },
    ),
  deleteAdvisor: (advisorId: string) =>
    request<Schemas["Advisor"]>(
      `/v1/advising/advisors/${encodeURIComponent(advisorId)}`,
      { method: "DELETE" },
    ),
  editOpportunity: (opportunityId: string, edit: Schemas["OpportunityAdminEdit"]) =>
    request<Schemas["Opportunity"]>(
      `/v1/catalog/opportunities/${encodeURIComponent(opportunityId)}`,
      { method: "PUT", body: JSON.stringify(edit) },
    ),
  withdrawOpportunity: (opportunityId: string) =>
    request<Schemas["Opportunity"]>(
      `/v1/catalog/opportunities/${encodeURIComponent(opportunityId)}`,
      { method: "DELETE" },
    ),
  setSlotAvailability: (advisorId: string, slotId: string, available: boolean) =>
    request<Schemas["AdvisorSlot"]>(
      `/v1/advising/advisors/${encodeURIComponent(advisorId)}/slots/${encodeURIComponent(slotId)}/availability`,
      { method: "POST", body: JSON.stringify({ available }) },
    ),
  confirmBooking: (bookingId: string) =>
    request<Schemas["AdvisorBooking"]>(
      `/v1/advising/bookings/${encodeURIComponent(bookingId)}/confirm`,
      { method: "POST" },
    ),
  submitAdvisorSummary: (bookingId: string, summary: Schemas["AdvisorSummary"]) =>
    request<Schemas["AdvisorBooking"]>(
      `/v1/advising/bookings/${encodeURIComponent(bookingId)}/summary`,
      { method: "POST", body: JSON.stringify(summary) },
    ),
  resourceCoverage: () =>
    request<ResourceCoverageAggregate[]>("/v1/insights/resource-coverage"),
  eventQuality: () => request<EventQualityAggregate[]>("/v1/insights/event-quality"),
  outreachQueue: () =>
    request<WellbeingOutreachRequest[]>("/v1/wellbeing/outreach-queue"),
  counselingHours: () =>
    request<Schemas["CounselingHours"]>("/v1/wellbeing/counseling-admin/hours"),
  setCounselingHours: (hours: Schemas["CounselingHours"]) =>
    request<Schemas["CounselingHours"]>("/v1/wellbeing/counseling-admin/hours", {
      method: "POST",
      body: JSON.stringify(hours),
    }),
  counselingBookings: () =>
    request<Schemas["CounselingBooking"][]>(
      "/v1/wellbeing/counseling-admin/bookings"),
  submit: (submission: PublicationSubmission) =>
    request<PublicationSubmission>("/v1/publisher/submissions", {
      method: "POST",
      body: JSON.stringify(submission),
    }),
  mySubmissions: () =>
    request<Schemas["PublicationSubmission"][]>("/v1/publisher/submissions"),
  reviewQueue: () =>
    request<PublicationSubmission[]>("/v1/review/submissions"),
  decide: (submissionId: string, decision: ModerationDecision) =>
    request<ModerationDecision>(
      `/v1/review/submissions/${encodeURIComponent(submissionId)}/decisions`,
      { method: "POST", body: JSON.stringify(decision) },
    ),
};

export const api = {
  profile: (id: string) => request<StudentProfile>(`${s(id)}/profile`),
  wellbeingEscalation: (id: string) =>
    request<WellbeingEscalation>(`${s(id)}/wellbeing/escalation`),
  wellbeingAssessment: (id: string, body: Schemas["WellbeingAssessmentRequest"]) =>
    request<WellbeingAssessmentResult>(`${s(id)}/wellbeing/assessment`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  counselingSlots: () =>
    request<Schemas["CounselingSlot"][]>("/v1/wellbeing/counseling/slots"),
  bookCounseling: (id: string, booking: Schemas["CounselingBooking"]) =>
    request<Schemas["CounselingBooking"]>(`${s(id)}/counseling-bookings`, {
      method: "POST",
      body: JSON.stringify(booking),
    }),
  emergencyAccess: (id: string) =>
    request<Schemas["EmergencyAccessResult"]>(`${s(id)}/wellbeing/emergency`, {
      method: "POST",
    }),
  profileExtras: (id: string) =>
    request<ProfileExtras>(`${s(id)}/profile/extras`),
  saveProfileExtras: (id: string, extras: ProfileExtras) =>
    request<ProfileExtras>(`${s(id)}/profile/extras`, {
      method: "POST",
      body: JSON.stringify(extras),
    }),
  contacts: (id: string) =>
    request<ImportantContacts>(`${s(id)}/contacts`),
  saveContacts: (id: string, contacts: ImportantContacts) =>
    request<ImportantContacts>(`${s(id)}/contacts`, {
      method: "POST",
      body: JSON.stringify(contacts),
    }),
  selfEditProfile: (id: string, edit: Partial<ProfileSelfEdit>) =>
    request<StudentProfile>(`${s(id)}/profile/self-edit`, {
      method: "POST",
      body: JSON.stringify(edit),
    }),
  /** Demo 运行时状态/启停（F1，2026-08-02）：Vertex Agent Engine 顶栏控制 */
  agentRuntime: () =>
    request<Schemas["AgentRuntimeStatus"]>("/v1/ops/agent-runtime"),
  agentRuntimeCommand: (action: "start" | "stop") =>
    request<Schemas["AgentRuntimeStatus"]>("/v1/ops/agent-runtime", {
      method: "POST",
      body: JSON.stringify({ action }),
    }),
  /** 现场 AI 拆解（A4，2026-08-02）：服务端后台任务，切页/关页不中断 */
  startDecompositionResearch: (id: string, goalId: string) =>
    request<Schemas["DecompositionResearchJob"]>(
      `${s(id)}/goals/${encodeURIComponent(goalId)}/decomposition/research`,
      { method: "POST" },
    ),
  decompositionResearchStatus: (id: string, goalId: string) =>
    request<Schemas["DecompositionResearchJob"]>(
      `${s(id)}/goals/${encodeURIComponent(goalId)}/decomposition/research`,
    ),
  /** 国际学生规则包求值（B，2026-08-02）：信封 + Rules 签发凭据 */
  contextPackEvaluation: (id: string, opportunityId?: string) =>
    request<Schemas["ContextPackEvaluation"]>(
      `${s(id)}/context-pack/evaluation${
        opportunityId ? `?opportunity_id=${encodeURIComponent(opportunityId)}` : ""
      }`,
    ),
  proposals: (id: string) =>
    request<ProfileUpdateProposal[]>(`${s(id)}/profile/proposals`),
  evidence: (id: string) => request<EvidenceRecord[]>(`${s(id)}/evidence`),
  uploadEvidence: (id: string, record: EvidenceRecord) =>
    request<EvidenceRecord>(`${s(id)}/evidence`, {
      method: "POST",
      body: JSON.stringify(record),
    }),
  notes: (id: string) => request<Note[]>(`${s(id)}/notes`),
  experiences: (id: string) => request<ExperienceRecord[]>(`${s(id)}/experiences`),
  goals: (id: string) => request<Goal[]>(`${s(id)}/goals`),
  setGoal: (id: string, goal: Goal) =>
    request<Goal>(`${s(id)}/goals`, { method: "POST", body: JSON.stringify(goal) }),
  availability: (id: string) =>
    request<AvailabilityBlock[]>(`${s(id)}/availability`),
  createBlock: (id: string, block: AvailabilityBlock) =>
    request<AvailabilityBlock>(`${s(id)}/availability`, {
      method: "POST",
      body: JSON.stringify(block),
    }),
  updateBlock: (id: string, blockId: string, patch: AvailabilityBlockPatch) =>
    request<AvailabilityBlock>(
      `${s(id)}/availability/${encodeURIComponent(blockId)}/update`,
      { method: "POST", body: JSON.stringify(patch) },
    ),
  removeBlock: (id: string, blockId: string) =>
    request<AvailabilityBlock>(
      `${s(id)}/availability/${encodeURIComponent(blockId)}/remove`,
      { method: "POST" },
    ),
  submitRoutine: (id: string, routine: RoutineRequest) =>
    request<CapacitySnapshot>(`${s(id)}/routine`, {
      method: "POST",
      body: JSON.stringify(routine),
    }),
  memory: (id: string) => request<MemoryEntry[]>(`${s(id)}/memory`),
  correctMemory: (id: string, memoryId: string, content: string) =>
    request<MemoryEntry>(
      `${s(id)}/memory/${encodeURIComponent(memoryId)}/correction`,
      {
        method: "POST",
        body: JSON.stringify({ memory_id: memoryId, corrected_content: content }),
      },
    ),
  lockMemory: (id: string, memoryId: string) =>
    request<MemoryEntry>(`${s(id)}/memory/${encodeURIComponent(memoryId)}/lock`, {
      method: "POST",
    }),
  forgetMemory: (id: string, memoryId: string) =>
    request<Schemas["MemoryForgetReceipt"]>(
      `${s(id)}/memory/${encodeURIComponent(memoryId)}/forget`,
      { method: "POST" },
    ),
  exportMyData: (id: string) =>
    request<Schemas["StudentDataExport"]>(`${s(id)}/export`),
  requestDeletion: (id: string) =>
    request<Schemas["DeletionReceipt"]>(`${s(id)}/deletion-request`, {
      method: "POST",
    }),
  academicState: (id: string) => request<AcademicState>(`${s(id)}/academic-state`),
  degreeProgress: (id: string) => request<DegreeProgress>(`${s(id)}/degree-progress`),
  courseCandidates: (id: string, limit = 100) =>
    request<AnnotatedCourseCandidate[]>(`${s(id)}/course-candidates?limit=${limit}`),
  gapMap: (id: string) => request<DynamicGapMap>(`${s(id)}/gap-map`),
  programs: () =>
    request<Schemas["ProgramCurriculum"][]>("/v1/catalog/programs"),
  courseRecommendations: (id: string) =>
    request<CourseRecommendation[]>(`${s(id)}/course-recommendations`),
  catalogCourses: (subject?: string, limit = 500) =>
    request<CourseCatalogItem[]>(
      `/v1/catalog/courses?limit=${limit}${
        subject ? `&subject=${encodeURIComponent(subject)}` : ""
      }`,
    ),
  goalDecomposition: (id: string, goalId: string) =>
    request<GoalDecomposition>(
      `${s(id)}/goals/${encodeURIComponent(goalId)}/decomposition`,
    ),
  growthTrajectory: (id: string) =>
    request<GrowthTrajectory>(`${s(id)}/growth-trajectory`),
  vgaSummary: (id: string) =>
    request<Schemas["VgaSummary"]>(`${s(id)}/vga-summary`),
  capacitySnapshot: (id: string) =>
    request<CapacitySnapshot>(`${s(id)}/capacity-snapshot`),
  wellbeingSignals: (id: string) =>
    request<WellbeingCapacitySignal[]>(`${s(id)}/wellbeing/signals`),
  wellbeingReminders: (id: string) =>
    request<WellbeingReminderEvent[]>(`${s(id)}/wellbeing/reminders`),
  requestOutreach: (id: string, req: WellbeingOutreachRequest) =>
    request<WellbeingOutreachRequest>(`${s(id)}/wellbeing/outreach`, {
      method: "POST",
      body: JSON.stringify(req),
    }),
  uploadResume: (id: string, upload: Schemas["ResumeUpload"]) =>
    request<ProfileUpdateProposal>(`${s(id)}/resume`, {
      method: "POST",
      body: JSON.stringify(upload),
    }),
  bookAdvisor: (id: string, booking: Schemas["AdvisorBooking"]) =>
    request<Schemas["AdvisorBooking"]>(`${s(id)}/advisor/bookings`, {
      method: "POST",
      body: JSON.stringify(booking),
    }),
  myAdvisorBookings: (id: string) =>
    request<Schemas["AdvisorBooking"][]>(`${s(id)}/advisor/bookings`),
  advisors: () => request<Schemas["Advisor"][]>("/v1/advising/advisors"),
  cancelAdvisorBooking: (id: string, bookingId: string) =>
    request<Schemas["AdvisorBooking"]>(
      `${s(id)}/advisor/bookings/${encodeURIComponent(bookingId)}/cancel`,
      { method: "POST" },
    ),
  markAdvisorNoShow: (bookingId: string) =>
    request<Schemas["AdvisorBooking"]>(
      `/v1/advising/bookings/${encodeURIComponent(bookingId)}/no-show`,
      { method: "POST" },
    ),
  myReflections: (id: string) =>
    request<Reflection[]>(`${s(id)}/reflections`),
  submitEventFeedback: (id: string, form: Schemas["StudentEventFeedbackForm"]) =>
    request<Schemas["EventQualityFeedback"]>(`${s(id)}/event-feedback`, {
      method: "POST",
      body: JSON.stringify(form),
    }),
  submitReflection: (id: string, reflection: Reflection) =>
    request<ReflectionResult>(`${s(id)}/reflections`, {
      method: "POST",
      body: JSON.stringify(reflection),
    }),
  decideProposal: (id: string, proposalId: string,
                   decision: "confirmed" | "edited" | "rejected") =>
    request<ProfileChangeEvent>(
      `${s(id)}/profile/proposals/${encodeURIComponent(proposalId)}` +
        `/decision?decision=${decision}`,
      { method: "POST" },
    ),
  writeCalendarAction: (id: string, action: CalendarAction) =>
    request<CalendarAction>(`${s(id)}/calendar-actions`, {
      method: "POST",
      body: JSON.stringify(action),
    }),
  updateConsent: (id: string, body: ConsentUpdateRequest) =>
    request<ConsentRecord>(`${s(id)}/consents`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  matches: (id: string) => request<MatchResult[]>(`${s(id)}/matches`),
  refreshMatches: (id: string) =>
    request<MatchResult[]>(`${s(id)}/matches/refresh`, { method: "POST" }),
  declinePlanItem: (id: string, planItemId: string) =>
    request<PathwayVersion>(
      `${s(id)}/pathway/items/${encodeURIComponent(planItemId)}`,
      { method: "DELETE" }),
  pathway: (id: string, intensity?: string) =>
    request<PathwayVersion>(
      `${s(id)}/pathway${intensity ? `?intensity=${intensity}` : ""}`),
  scheduleProposals: (id: string) =>
    request<ScheduleProposal[]>(`${s(id)}/schedule-proposals`),
  actions: (id: string) => request<ActionEvent[]>(`${s(id)}/actions`),
  recordAction: (id: string, event: ActionEvent) =>
    request<ActionEvent>(`${s(id)}/actions`, {
      method: "POST",
      body: JSON.stringify(event),
    }),
  proposeSchedule: (id: string, proposal: ScheduleProposal) =>
    request<ScheduleProposal>(`${s(id)}/schedule-proposals`, {
      method: "POST",
      body: JSON.stringify(proposal),
    }),
  replanPreview: (id: string, req: ReplanRequest) =>
    request<AffectedScope>(`${s(id)}/replan-preview`, {
      method: "POST",
      body: JSON.stringify(req),
    }),
  catalog: (limit = 500, includeExpired = false, view: "live" | "archive" = "live") =>
    request<Opportunity[]>(
      `/v1/catalog/opportunities?limit=${limit}` +
        (includeExpired ? "&include_expired=true" : "") +
        (view !== "live" ? `&view=${view}` : ""),
    ),
  /** 扫码签到（D 批，2026-08-02）：token 来自活动二维码 */
  checkin: (id: string, body: Schemas["CheckinRequest"]) =>
    request<Schemas["CheckinResult"]>(`${s(id)}/checkin`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  whyNotRecommended: (opportunityId: string, studentId: string) =>
    request<EligibilityExplanation>(
      `/v1/catalog/opportunities/${encodeURIComponent(opportunityId)}` +
        `/why-not-recommended?student_id=${encodeURIComponent(studentId)}`,
    ),
};
