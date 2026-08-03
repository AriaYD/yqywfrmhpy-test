"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { pickLang, useI18n, type MessageKey } from "@/i18n";
import { api, type ExperienceRecord, type ProfileExtras as ProfileExtrasType } from "@/lib/api";
import { ProfileExtrasSections } from "@/components/profile-extras";
import { useResource } from "@/lib/useResource";
import {
  Card,
  Empty,
  Failure,
  Grid,
  Loading,
  Metric,
  PageHeader,
  SectionTitle,
  Segmented,
  TriState,
} from "@/components/ui";

const VERIFICATION_KEY: Record<string, MessageKey> = {
  self_reported: "profile.evidence.self_reported",
  source_imported: "profile.evidence.source_imported",
  institution_verified: "profile.evidence.institution_verified",
  expired: "profile.evidence.expired",
  disputed: "profile.evidence.disputed",
};

/** 核验状态映射到三值：学校认证=met，过期/争议=not_met，其余=unknown。
 *  自述**不是** not_met——"你说了但没人证实"和"证实为假"是两回事。 */
const VERIFICATION_TRI: Record<string, "met" | "not_met" | "unknown"> = {
  institution_verified: "met",
  source_imported: "met",
  self_reported: "unknown",
  expired: "not_met",
  disputed: "not_met",
};

/** R4-B：专业全名（官方项目名）。别人看不懂 BSC-COMP 这种内部码。 */
const PROGRAM_FULL_NAME: Record<string, { zh: string; en: string }> = {
  "BSC-COMP": { zh: "计算机科学理学士 (BSc in Computer Science)", en: "BSc in Computer Science" },
  "BBA-ISOM": { zh: "信息系统工商管理学士 (BBA in Information Systems)", en: "BBA in Information Systems" },
  "BENG-IEDA": {
    zh: "工业工程及决策分析工学士 (BEng in Industrial Engineering and Decision Analytics)",
    en: "BEng in Industrial Engineering and Decision Analytics",
  },
};

/** D/R5-B：LinkedIn 式分区的经历类型划分。 */
const WORK_TYPES = new Set<ExperienceRecord["type"]>([
  "internship",
  "part_time",
  "entrepreneurship",
]);
const PROJECT_TYPES = new Set<ExperienceRecord["type"]>([
  "project",
  "research",
  "competition",
]);
const VOLUNTEER_TYPES = new Set<ExperienceRecord["type"]>(["volunteer", "club"]);
const CERT_TYPES = new Set<string>(["certificate", "link"]);

function ExperienceSection({
  titleKey,
  rows,
  loading,
  editing = false,
  onAdd,
}: {
  titleKey: MessageKey;
  rows: ExperienceRecord[];
  loading: boolean;
  /** 编辑态下即使分区为空也能自添记录（用户裁定 2026-08-01） */
  editing?: boolean;
  onAdd?: (draft: { role: string; organization: string; start: string; end: string }) => void;
}) {
  const { t } = useI18n();
  const [draft, setDraft] = useState({ role: "", organization: "", start: "", end: "" });
  return (
    <Card data-experience-section={titleKey}>
      <SectionTitle>{t(titleKey)}</SectionTitle>
      {loading && <Loading />}
      {rows.length === 0 && !loading && !editing && (
        <Empty messageKey="profile.section.empty" />
      )}
      <ul className="flex flex-col gap-3">
        {rows.map((exp) => (
          <li
            key={exp.experience_id}
            data-experience={exp.experience_id}
            className="rounded-md border border-line bg-bg-sunk p-3.5"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div className="t-body font-medium text-fg">
                {exp.role}
                <span className="t-meta ms-2 font-normal text-fg-muted">
                  · {exp.organization}
                </span>
              </div>
              <span className="t-micro text-fg-faint">
                {exp.period.start} → {exp.period.end ?? t("profile.exp.present")} ·{" "}
                {t(VERIFICATION_KEY[exp.verification_status] ?? "profile.evidence.self_reported")}
              </span>
            </div>
            {exp.responsibilities.length > 0 && (
              <ul className="t-meta mt-2 list-disc ps-5 text-fg-muted">
                {exp.responsibilities.slice(0, 3).map((line, index) => (
                  <li key={index}>{line}</li>
                ))}
              </ul>
            )}
            {exp.outcomes.length > 0 && (
              <p className="t-meta mt-1.5 text-fg-muted">
                {exp.outcomes.join("；")}
              </p>
            )}
            {exp.skills.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {exp.skills.map((skill) => (
                  <span
                    key={skill}
                    className="t-micro rounded-sm border border-line px-2 py-0.5 text-fg-muted"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      {editing && onAdd && (
        <div className="mt-3 flex flex-wrap items-end gap-2" data-exp-add-row={titleKey}>
          <input type="text" data-exp-add-role placeholder={t("profile.exp.role")}
            value={draft.role}
            onChange={(e) => setDraft((d) => ({ ...d, role: e.target.value }))}
            className="field t-meta px-2.5 py-1.5" />
          <input type="text" data-exp-add-org placeholder={t("profile.exp.org")}
            value={draft.organization}
            onChange={(e) => setDraft((d) => ({ ...d, organization: e.target.value }))}
            className="field t-meta px-2.5 py-1.5" />
          <input type="month" data-exp-add-start aria-label={t("profile.exp.start")}
            value={draft.start}
            onChange={(e) => setDraft((d) => ({ ...d, start: e.target.value }))}
            className="field t-meta px-2.5 py-1.5" />
          <input type="month" data-exp-add-end aria-label={t("profile.exp.end")}
            value={draft.end}
            onChange={(e) => setDraft((d) => ({ ...d, end: e.target.value }))}
            className="field t-meta px-2.5 py-1.5" />
          <button type="button" data-exp-add-submit
            disabled={!draft.role.trim() || !draft.organization.trim() || !draft.start}
            onClick={() => {
              onAdd(draft);
              setDraft({ role: "", organization: "", start: "", end: "" });
            }}
            className="pressable btn btn-secondary t-meta disabled:opacity-40">
            + {t("profile.exp.add")}
          </button>
        </div>
      )}
    </Card>
  );
}

/** 「我是国际生」唯一入口（用户裁定 F，2026-08-02：全站只此一处开关）。
 * 勾选 = context_pack 同意 + 13 字段结构化表单落档案 → 服务端按 profile
 * 判断全局注入一次（拆解/推荐/时间线只读展示，不再各放开关）；
 * 取消 = 清空上下文 + 撤销同意（两步都做），全局卸载。 */
function IntlStudentSection({
  studentId,
  intl,
  onSaved,
}: {
  studentId: string;
  intl: NonNullable<Awaited<ReturnType<typeof api.profile>>>["intl_context"];
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const [formOpen, setFormOpen] = useState(false);
  const [state, setState] = useState<"idle" | "saving" | "error">("idle");
  const [confirmOff, setConfirmOff] = useState(false);
  const [draft, setDraft] = useState({
    study: "HK-SAR", work: "HK-SAR", mode: "full_time",
    permission: "student_visa", expiry: "", start: "", languages: "", cities: "",
  });

  async function enable() {
    if (!draft.expiry) return;
    setState("saving");
    try {
      await api.updateConsent(studentId, { scope: "context_pack", granted: true });
      await api.selfEditProfile(studentId, {
        intl_context: {
          study_jurisdiction: draft.study as "HK-SAR" | "CN-MAINLAND" | "other",
          intended_work_jurisdiction: draft.work as "HK-SAR" | "CN-MAINLAND" | "other",
          study_mode: draft.mode as "full_time" | "part_time",
          permission_category: draft.permission,
          permission_expiry_date: draft.expiry,
          intended_start_date: draft.start || null,
          school_approval: null,
          employer_sponsorship_expected: null,
          language_evidence: draft.languages
            .split(/[,，;；]/).map((s) => s.trim()).filter(Boolean),
          target_cities: draft.cities
            .split(/[,，;；]/).map((s) => s.trim()).filter(Boolean),
          updated_at: new Date().toISOString(),
        },
      });
      setFormOpen(false);
      setState("idle");
      onSaved();
    } catch {
      setState("error");
    }
  }

  async function disable() {
    setState("saving");
    try {
      await api.selfEditProfile(studentId, { clear_intl_context: true });
      await api.updateConsent(studentId, { scope: "context_pack", granted: false });
      setConfirmOff(false);
      setState("idle");
      onSaved();
    } catch {
      setState("error");
    }
  }

  const field = "field t-meta mt-1 w-full";
  return (
    <Card className="mb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="t-body flex items-center gap-2.5 font-medium text-fg">
          <input
            type="checkbox"
            data-intl-toggle
            checked={intl != null}
            onChange={(e) => {
              if (e.target.checked) {
                if (intl == null) setFormOpen(true);
              } else {
                setConfirmOff(true);
              }
            }}
          />
          {t("profile.intl.checkbox")}
        </label>
        {intl != null && (
          <span className="chip chip-mist t-micro" data-intl-enabled>
            {t("profile.intl.enabled")}
          </span>
        )}
      </div>
      <p className="t-micro mt-1.5 text-fg-faint">{t("profile.intl.lead")}</p>

      {confirmOff && (
        <div className="mt-3 flex flex-wrap items-center gap-2" data-intl-off-confirm
             role="alertdialog" aria-label={t("profile.intl.offConfirm")}>
          <span className="t-meta text-fg-muted">{t("profile.intl.offConfirm")}</span>
          <button type="button" data-intl-off-yes onClick={disable}
                  className="pressable btn btn-danger t-meta">
            {t("profile.intl.offYes")}
          </button>
          <button type="button" onClick={() => setConfirmOff(false)}
                  className="pressable btn btn-ghost t-meta">
            {t("calendar.editor.cancel")}
          </button>
        </div>
      )}

      {intl != null && !formOpen && (
        <div className="t-meta mt-3 flex flex-wrap gap-x-6 gap-y-1 text-fg-muted"
             data-intl-summary>
          <span>{t("profile.intl.work")}: {intl.intended_work_jurisdiction}</span>
          <span>{t("profile.intl.permission")}: {intl.permission_category}</span>
          <span>{t("profile.intl.expiry")}: {intl.permission_expiry_date}</span>
          {intl.language_evidence.length > 0 && (
            <span>{t("profile.intl.languages")}: {intl.language_evidence.join("、")}</span>
          )}
        </div>
      )}

      {formOpen && (
        <div className="mt-4 grid gap-3 sm:grid-cols-2" data-intl-form>
          <label className="t-meta text-fg-muted">{t("profile.intl.study")}
            <select className={field} data-intl-study value={draft.study}
                    onChange={(e) => setDraft({ ...draft, study: e.target.value })}>
              <option value="HK-SAR">{t("profile.intl.hk")}</option>
              <option value="CN-MAINLAND">{t("profile.intl.cn")}</option>
              <option value="other">{t("profile.intl.other")}</option>
            </select>
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.work")}
            <select className={field} data-intl-work value={draft.work}
                    onChange={(e) => setDraft({ ...draft, work: e.target.value })}>
              <option value="HK-SAR">{t("profile.intl.hk")}</option>
              <option value="CN-MAINLAND">{t("profile.intl.cn")}</option>
              <option value="other">{t("profile.intl.other")}</option>
            </select>
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.mode")}
            <select className={field} value={draft.mode}
                    onChange={(e) => setDraft({ ...draft, mode: e.target.value })}>
              <option value="full_time">{t("profile.intl.fullTime")}</option>
              <option value="part_time">{t("profile.intl.partTime")}</option>
            </select>
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.permission")}
            <input className={field} data-intl-permission value={draft.permission}
                   onChange={(e) => setDraft({ ...draft, permission: e.target.value })} />
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.expiry")} *
            <input type="date" className={field} data-intl-expiry value={draft.expiry}
                   onChange={(e) => setDraft({ ...draft, expiry: e.target.value })} />
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.start")}
            <input type="date" className={field} value={draft.start}
                   onChange={(e) => setDraft({ ...draft, start: e.target.value })} />
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.languages")}
            <input className={field} data-intl-languages
                   placeholder={t("profile.intl.languagesHint")}
                   value={draft.languages}
                   onChange={(e) => setDraft({ ...draft, languages: e.target.value })} />
          </label>
          <label className="t-meta text-fg-muted">{t("profile.intl.cities")}
            <input className={field} value={draft.cities}
                   onChange={(e) => setDraft({ ...draft, cities: e.target.value })} />
          </label>
          <div className="sm:col-span-2 flex items-center gap-2">
            <button type="button" data-intl-save disabled={!draft.expiry || state === "saving"}
                    onClick={enable} className="pressable btn btn-primary t-meta">
              {state === "saving" ? t("onboarding.consent.saving") : t("profile.intl.save")}
            </button>
            <button type="button" onClick={() => setFormOpen(false)}
                    className="pressable btn btn-ghost t-meta">
              {t("calendar.editor.cancel")}
            </button>
            {state === "error" && (
              <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                {t("profile.intl.failed")}
              </span>
            )}
          </div>
          <p className="t-micro sm:col-span-2 text-fg-faint">
            {t("profile.intl.disclaimer")}
          </p>
        </div>
      )}
    </Card>
  );
}

export default function ProfilePage() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [tab, setTab] = useState<"overview" | "evidence" | "proposals">("overview");
  const [resumeState, setResumeState] =
    useState<"idle" | "parsing" | "done" | "error">("idle");
  // R4-G：LinkedIn 式编辑——学生本人直接改标签与经历，保存即落库
  const [editing, setEditing] = useState(false);
  const [tagDraft, setTagDraft] = useState<string[]>([]);
  const [newTag, setNewTag] = useState("");
  const [editState, setEditState] = useState<"idle" | "saving" | "error">("idle");
  const [evidenceType, setEvidenceType] =
    useState<"certificate" | "artifact" | "transcript" | "screenshot" | "other">("certificate");
  const [evidenceNote, setEvidenceNote] =
    useState<"idle" | "saving" | "done" | "error">("idle");
  // R5-B/D：补充分区（教育/语言/出版物/荣誉/组织/爱好）——随全页 Edit 一起编辑
  const extras = useResource(() => api.profileExtras(studentId), [studentId]);
  const [extrasDraft, setExtrasDraft] = useState<ProfileExtrasType | null>(null);
  // 用户裁定（2026-08-01）：编辑态下空分区也能自添记录；保存时整表替换
  const [newExperiences, setNewExperiences] = useState<ExperienceRecord[]>([]);
  function addExperience(type: ExperienceRecord["type"]) {
    return (draft: { role: string; organization: string; start: string; end: string }) => {
      setNewExperiences((prev) => [
        ...prev,
        {
          experience_id: `EXP-${studentId}-${Date.now()}-${prev.length}`,
          student_id: studentId,
          type,
          organization: draft.organization.trim(),
          role: draft.role.trim(),
          period: {
            start: `${draft.start}-01`,
            end: draft.end ? `${draft.end}-01` : null,
          },
          responsibilities: [],
          outcomes: [],
          skills: [],
          evidence_ids: [],
          note_ids: [],
          verification_status: "self_reported",
        } as ExperienceRecord,
      ]);
    };
  }

  function enterEdit() {
    setTagDraft([...(profile.data?.interests ?? [])]);
    if (extras.data) setExtrasDraft(structuredClone(extras.data));
    setEditing(true);
  }

  async function saveEdit() {
    setEditState("saving");
    try {
      await api.selfEditProfile(studentId, {
        interests: tagDraft,
        experiences: newExperiences.length
          ? [...(experiences.data ?? []), ...newExperiences]
          : null,
      });
      if (newExperiences.length) {
        setNewExperiences([]);
        experiences.reload();
      }
      if (extrasDraft) {
        await api.saveProfileExtras(studentId, extrasDraft);
        extras.reload();
      }
      setEditing(false);
      setEditState("idle");
      profile.reload();
    } catch {
      setEditState("error");
    }
  }

  const profile = useResource(() => api.profile(studentId), [studentId]);
  const degree = useResource(() => api.degreeProgress(studentId), [studentId]);
  const evidence = useResource(() => api.evidence(studentId), [studentId]);
  const experiences = useResource(() => api.experiences(studentId), [studentId]);
  const academic = useResource(() => api.academicState(studentId), [studentId]);
  const proposals = useResource(() => api.proposals(studentId), [studentId]);

  return (
    <>
      <PageHeader titleKey="page.profile">
        {/* 编辑=对整页自述内容的编辑，所以按钮在页面右上、用主按钮显眼化
            （用户裁定 2026-08-01）；只在总览分页出现。 */}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Segmented
            ariaLabel={t("page.profile")}
            value={tab}
            onChange={setTab}
            options={[
              { value: "overview", label: t("profile.tab.overview") },
              { value: "evidence", label: t("profile.tab.evidence") },
              { value: "proposals", label: t("profile.tab.proposals") },
            ]}
          />
          {tab === "overview" && profile.data && (
            !editing ? (
              <button
                type="button"
                data-profile-edit
                onClick={enterEdit}
                className="pressable btn btn-primary t-meta font-medium"
              >
                {t("profile.edit")}
              </button>
            ) : (
              <span className="flex gap-2">
                <button
                  type="button"
                  data-profile-edit-save
                  disabled={editState === "saving"}
                  onClick={saveEdit}
                  className="pressable btn btn-primary t-meta font-medium disabled:opacity-50"
                >
                  {t("profile.edit.save")}
                </button>
                <button
                  type="button"
                  data-profile-edit-cancel
                  onClick={() => setEditing(false)}
                  className="pressable btn btn-ghost t-meta"
                >
                  {t("calendar.editor.cancel")}
                </button>
              </span>
            )
          )}
        </div>
      </PageHeader>

      {tab === "overview" && (
        <div className="flex flex-col gap-5" data-tab-panel="overview">
          {profile.loading && <Loading />}
          {profile.error && <Failure error={profile.error} onRetry={profile.reload} />}
          {profile.data && (
            <Card>
              {/* 专业名占满剩余宽度（用户裁定：不许挤成三行窄条）；
                  年级/学分/发展模式收成右侧一排紧凑指标。 */}
              <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-4">
                <div className="min-w-[240px] flex-1">
                  <div className="t-micro text-fg-faint">{t("profile.programme")}</div>
                  <div className="t-title mt-1 text-fg">
                    {PROGRAM_FULL_NAME[profile.data.program_id]
                      ? pickLang(locale,
                          PROGRAM_FULL_NAME[profile.data.program_id].zh,
                          PROGRAM_FULL_NAME[profile.data.program_id].en)
                      : profile.data.program_id}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap gap-x-10 gap-y-4">
                  <Metric label={t("profile.year")} value={profile.data.year} />
                  <Metric
                    label={t("profile.credits")}
                    value={
                      degree.data
                        ? degree.data.total_earned_credits
                        : t("profile.cgaMissing")
                    }
                  />
                  <Metric
                    label={t("goals.mode")}
                    value={
                      profile.data.development_modes?.[0]
                        ? t(
                            `goals.mode.${profile.data.development_modes[0].mode}` as MessageKey,
                          )
                        : t("profile.cgaMissing")
                    }
                  />
                </div>
              </div>
            </Card>
          )}

          {/* 「我是国际生」唯一入口（F）：勾选即全局注入约束包 */}
          {profile.data && (
            <IntlStudentSection
              studentId={studentId}
              intl={profile.data.intl_context ?? null}
              onSaved={() => profile.reload()}
            />
          )}

          <Card className="mb-5">
            <SectionTitle>{t("profile.resume.title")}</SectionTitle>
            <p className="t-meta mb-3 max-w-[62ch] text-fg-muted">
              {t("profile.resume.lead")}
            </p>
            {/* D 裁定（2026-08-02）：模板定死、零 AI——模板文件随站点分发 */}
            <p className="t-meta mb-3">
              <a href="/resume-template.md" target="_blank" rel="noreferrer"
                 className="underline" data-resume-template-link>
                {t("profile.resume.template")} ↗
              </a>
            </p>
            {/* 评委一键注入（2026-08-04 用户需求）：两份随站点分发的模板
                合规 demo 简历（专业不同），点一下即走与手动选文件完全同一条
                uploadResume 链路——评委不必自己备文件。 */}
            <div className="mb-3 flex flex-col items-start gap-1.5">
              {/* 用户裁定样式：不是按钮，是一行行的蓝色可点击文字链
                  （mist 蓝，下划线，与站内文字链一致） */}
              {([
                ["xiaohongmao", "profile.resume.demo.red"],
                ["dahuilang", "profile.resume.demo.wolf"],
              ] as const).map(([slug, key]) => (
                <button
                  key={slug}
                  type="button"
                  data-demo-resume={slug}
                  disabled={resumeState === "parsing"}
                  className="t-meta cursor-pointer underline underline-offset-2 disabled:opacity-60"
                  style={{ color: "var(--color-mist-700)" }}
                  onClick={async () => {
                    setResumeState("parsing");
                    try {
                      const res = await fetch(`/demo-resume-${slug}.md`);
                      if (!res.ok) throw new Error(String(res.status));
                      await api.uploadResume(studentId, {
                        filename: `demo-resume-${slug}.md`,
                        content_text: await res.text(),
                        content_base64: null,
                      });
                      setResumeState("done");
                      proposals.reload();
                    } catch {
                      setResumeState("error");
                    }
                  }}
                >
                  {t(key)}
                </button>
              ))}
            </div>
            {/* B（2026-07-31）：上传入口做成真正的按钮——按下即时反馈（.pressable），
                原生 file input 藏起来但保持可聚焦可用（sr-only 而不是 display:none）。 */}
            <label
              data-resume-upload-button
              className={`pressable btn btn-primary t-body cursor-pointer font-medium ${
                resumeState === "parsing" ? "opacity-60" : ""
              }`}
            >
              <span aria-hidden>↑</span>
              {resumeState === "parsing"
                ? t("profile.resume.parsing")
                : t("profile.resume.choose")}
            <input
              type="file"
              data-resume-upload
              accept=".md"
              className="sr-only"
              disabled={resumeState === "parsing"}
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                setResumeState("parsing");
                try {
                  const isPdf = file.name.toLowerCase().endsWith(".pdf");
                  let payload;
                  if (isPdf) {
                    const buffer = await file.arrayBuffer();
                    let binary = "";
                    const bytes = new Uint8Array(buffer);
                    for (let i = 0; i < bytes.length; i++) {
                      binary += String.fromCharCode(bytes[i]);
                    }
                    payload = { filename: file.name, content_text: null,
                                content_base64: btoa(binary) };
                  } else {
                    payload = { filename: file.name,
                                content_text: await file.text(),
                                content_base64: null };
                  }
                  await api.uploadResume(studentId, payload);
                  setResumeState("done");
                  proposals.reload();
                } catch {
                  setResumeState("error");
                } finally {
                  e.target.value = "";
                }
              }}
            />
            </label>
            {resumeState === "parsing" && (
              <p className="t-meta mt-2 text-fg-muted">{t("profile.resume.parsing")}</p>
            )}
            {resumeState === "done" && (
              <p className="t-meta mt-2" style={{ color: "var(--color-moss-600)" }}
                 data-resume-done>
                {t("profile.resume.done")}
              </p>
            )}
            {resumeState === "error" && (
              <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }}>
                {t("profile.resume.failed")}
              </p>
            )}
          </Card>

          {/* D（2026-07-31）：LinkedIn 式完整档案分区——项目与经历 / 实习与工作 /
              课外课程与证书。数据来自 experiences 与 evidence，两处都带核验状态，
              不把"自述"抹平成"认证"。 */}
          <ExperienceSection
            titleKey="profile.section.work"
            rows={[...(experiences.data ?? []), ...newExperiences].filter((x) => WORK_TYPES.has(x.type))}
            loading={experiences.loading}
            editing={editing}
            onAdd={addExperience("internship")}
          />
          {(editing && extrasDraft) || extras.data ? (
            <ProfileExtrasSections
              draft={(editing && extrasDraft) || extras.data!}
              editing={editing}
              onChange={(next) => setExtrasDraft(next)}
            />
          ) : null}
          <ExperienceSection
            titleKey="profile.section.projects"
            rows={[...(experiences.data ?? []), ...newExperiences].filter((x) => PROJECT_TYPES.has(x.type))}
            loading={experiences.loading}
            editing={editing}
            onAdd={addExperience("project")}
          />
          <ExperienceSection
            titleKey="profile.section.volunteering"
            rows={[...(experiences.data ?? []), ...newExperiences].filter((x) => VOLUNTEER_TYPES.has(x.type))}
            loading={experiences.loading}
            editing={editing}
            onAdd={addExperience("volunteer")}
          />
          {/* 审计红-1 兜底（2026-08-02）：type 不在三个分区集合里的经历
              （历史 other 数据等）也必须可见——落库了就不许在总览消失 */}
          {[...(experiences.data ?? []), ...newExperiences].some(
            (x) => !WORK_TYPES.has(x.type) && !PROJECT_TYPES.has(x.type)
              && !VOLUNTEER_TYPES.has(x.type)) && (
            <ExperienceSection
              titleKey="profile.section.otherExperience"
              rows={[...(experiences.data ?? []), ...newExperiences].filter(
                (x) => !WORK_TYPES.has(x.type) && !PROJECT_TYPES.has(x.type)
                  && !VOLUNTEER_TYPES.has(x.type))}
              loading={experiences.loading}
              editing={editing}
              onAdd={addExperience("other")}
            />
          )}
          {/* Courses：校内课程记录（SIS 派生，只读——出处在教务，不能自由编辑） */}
          <Card data-courses-section>
            <SectionTitle>{t("profile.section.courses")}</SectionTitle>
            <p className="t-micro mb-2 text-fg-faint">
              {t("profile.section.courses.hint")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {(academic.data?.course_records ?? [])
                .filter((r) => r.status === "completed" || r.status === "enrolled")
                .map((r) => (
                  <span key={r.record_id}
                        className="t-mono rounded-sm border border-line px-2 py-0.5 text-fg-muted"
                        title={r.term}>
                    {r.course_id}
                  </span>
                ))}
            </div>
          </Card>
          <Card data-certificates>
            <SectionTitle>{t("profile.section.certs")}</SectionTitle>
            {evidence.loading && <Loading />}
            {/* 审查 M6：Resume 模板物化的**自述**证书在 extras（无文件载体，
                不进 Evidence）；带文件的证书仍走下方 evidence 列表 */}
            {((extras.data?.certificates ?? []).length > 0) && (
              <ul className="mb-2 flex flex-col gap-1.5" data-cert-extras>
                {(extras.data?.certificates ?? []).map((c, i) => (
                  <li key={`${c.title}-${i}`}
                      className="t-meta flex flex-wrap items-baseline gap-x-2 text-fg-muted">
                    <span className="text-fg">{c.title}</span>
                    <span className="t-micro text-fg-faint">
                      {[c.date, c.note,
                        t("profile.evidence.self_reported")]
                        .filter(Boolean).join(" · ")}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {(evidence.data ?? []).filter((e) =>
              CERT_TYPES.has(e.evidence_type),
            ).length === 0 &&
              (extras.data?.certificates ?? []).length === 0 &&
              !evidence.loading && <Empty messageKey="profile.section.empty" />}
            <ul className="flex flex-col gap-2.5">
              {(evidence.data ?? [])
                .filter((e) => CERT_TYPES.has(e.evidence_type))
                .map((item) => (
                  <li
                    key={item.evidence_id}
                    data-cert={item.evidence_id}
                    className="flex flex-wrap items-baseline justify-between gap-2 rounded-md border border-line bg-bg-sunk px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <span className="t-body text-fg">{item.source}</span>
                      {item.issuer && (
                        <span className="t-meta ms-2 text-fg-muted">
                          · {item.issuer}
                        </span>
                      )}
                      {item.uri && (
                        <a
                          href={item.uri}
                          target="_blank"
                          rel="noreferrer"
                          className="t-meta ms-2 underline underline-offset-2"
                          style={{ color: "var(--accent-deep)" }}
                        >
                          ↗
                        </a>
                      )}
                    </div>
                    <span className="t-micro text-fg-faint">
                      {item.obtained_at} ·{" "}
                      {t(VERIFICATION_KEY[item.verification_status] ?? "profile.evidence.self_reported")}
                    </span>
                  </li>
                ))}
            </ul>
          </Card>

          {/* 技能与兴趣标签：放在总览最下方（用户裁定 2026-08-01）——
              它是自述标签池，不该压在学籍事实上面。编辑态随右上全页 Edit。 */}
          {profile.data && (
            <Card data-skills-card>
              <SectionTitle>{t("profile.skills")}</SectionTitle>
              <p className="t-micro mb-2 text-fg-faint" data-skills-hint>
                {t("profile.skills.hint")}
              </p>
              {!editing ? (
                <ul className="flex flex-wrap gap-2">
                  {profile.data.interests.map((interest) => (
                    <li
                      key={interest}
                      className="chip chip-neutral t-meta"
                    >
                      {interest}
                    </li>
                  ))}
                </ul>
              ) : (
                <div data-tag-editor>
                  <ul className="flex flex-wrap gap-2">
                    {tagDraft.map((tag) => (
                      <li
                        key={tag}
                        className="chip chip-peach t-meta gap-1"
                      >
                        {tag}
                        <button
                          type="button"
                          data-remove-tag={tag}
                          aria-label={`remove ${tag}`}
                          onClick={() =>
                            setTagDraft((prev) => prev.filter((x) => x !== tag))
                          }
                          className="pressable"
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-2 flex gap-2">
                    <input
                      type="text"
                      data-new-tag
                      value={newTag}
                      onChange={(e) => setNewTag(e.target.value)}
                      placeholder={t("profile.edit.addTag")}
                      className="field t-meta px-2.5 py-1.5"
                    />
                    <button
                      type="button"
                      data-add-tag
                      disabled={!newTag.trim()}
                      onClick={() => {
                        const value = newTag.trim();
                        if (value && !tagDraft.includes(value)) {
                          setTagDraft((prev) => [...prev, value]);
                        }
                        setNewTag("");
                      }}
                      className="pressable btn btn-secondary t-meta disabled:opacity-40"
                    >
                      +
                    </button>
                  </div>
                  {editState === "error" && (
                    <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }}>
                      {t("app.error")}
                    </p>
                  )}
                </div>
              )}
            </Card>
          )}

        </div>
      )}

      {tab === "proposals" && (
        <div className="flex flex-col gap-5" data-tab-panel="proposals">
          <Card>
            <SectionTitle>{t("profile.proposals")}</SectionTitle>
            <p className="t-meta mb-4 max-w-[62ch] text-fg-faint">
              {t("profile.proposals.explain")}
            </p>
            {proposals.loading && <Loading />}
            {proposals.error && <Failure error={proposals.error} />}
            {proposals.data?.length === 0 && (
              <Empty messageKey="profile.proposals.empty" />
            )}
            <ul className="flex flex-col gap-3">
              {proposals.data?.slice(0, 6).map((proposal) => (
                <li
                  key={proposal.proposal_id}
                  data-proposal={proposal.proposal_id}
                  className="rounded-md border border-line bg-bg-sunk p-3"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="t-body text-fg">{proposal.reason}</span>
                    <span className="t-mono text-fg-faint">{proposal.status}</span>
                  </div>
                  <ul className="mt-2 flex flex-col gap-1">
                    {proposal.proposed_changes.map((change, index) => (
                      <li key={index} className="t-mono text-fg-muted">
                        {change.operation} · {change.field_path} →{" "}
                        {typeof change.new_value === "object" && change.new_value !== null
                          ? Object.values(change.new_value).join(" · ")
                          : String(change.new_value ?? "")}
                      </li>
                    ))}
                  </ul>
                  {proposal.status === "pending" && (
                    <div className="mt-3 flex items-center gap-2">
                      <button
                        type="button"
                        data-proposal-confirm={proposal.proposal_id}
                        onClick={async () => {
                          try {
                            await api.decideProposal(
                              studentId, proposal.proposal_id, "confirmed",
                            );
                          } finally {
                            // 物化写进 experiences/extras/profile 三处——只刷新
                            // 提议列表会让总览分页停在批准前的快照（同页切分页
                            // 不重挂载；2026-08-04 用户报障：批准后总览纹丝不动）
                            proposals.reload();
                            experiences.reload();
                            extras.reload();
                            profile.reload();
                          }
                        }}
                        className="pressable btn btn-primary t-meta font-medium"
                      >
                        {t("profile.proposals.accept")}
                      </button>
                      <button
                        type="button"
                        data-proposal-reject={proposal.proposal_id}
                        onClick={async () => {
                          try {
                            await api.decideProposal(
                              studentId, proposal.proposal_id, "rejected",
                            );
                          } finally {
                            proposals.reload();
                          }
                        }}
                        className="pressable t-meta rounded-md border border-line px-3 py-1.5 text-fg-muted"
                      >
                        {t("profile.proposals.reject")}
                      </button>
                    </div>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}

      {tab === "evidence" && (
        <div className="flex flex-col gap-5" data-tab-panel="evidence">
          <Card>
            <p className="t-body max-w-[62ch] text-fg-muted">
              {t("profile.evidence.explain")}
            </p>
            {/* R5-C：学生上传证据源文件——demo 存引用与元数据，核验恒"自述" */}
            <div className="mt-4 flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className="t-micro text-fg-faint">{t("profile.evidence.uploadType")}</span>
                <select
                  data-evidence-type
                  value={evidenceType}
                  onChange={(e) => setEvidenceType(e.target.value as typeof evidenceType)}
                  className="t-meta rounded-md border border-line bg-card px-2 py-1.5 text-fg"
                >
                  {(["certificate", "artifact", "transcript", "screenshot", "other"] as const).map((x) => (
                    <option key={x} value={x}>{x}</option>
                  ))}
                </select>
              </label>
              <label
                data-evidence-upload-button
                className="pressable btn btn-primary t-meta cursor-pointer font-medium"
              >
                <span aria-hidden>↑</span>
                {t("profile.evidence.upload")}
                <input
                  type="file"
                  data-evidence-upload
                  className="sr-only"
                  onChange={async (e) => {
                    const file = e.target.files?.[0];
                    if (!file) return;
                    setEvidenceNote("saving");
                    try {
                      await api.uploadEvidence(studentId, {
                        evidence_id: `EV-${studentId}-up-${Date.now()}`,
                        student_id: studentId,
                        evidence_type: evidenceType,
                        source: file.name,
                        uri: null,
                        object_ref: `vault/${studentId}/uploads/${file.name}`,
                        issuer: null,
                        obtained_at: new Date().toISOString().slice(0, 10),
                        verification_status: "self_reported",
                        visibility: "private",
                        checksum: null,
                        expires_at: null,
                      });
                      setEvidenceNote("done");
                      evidence.reload();
                    } catch {
                      setEvidenceNote("error");
                    } finally {
                      e.target.value = "";
                    }
                  }}
                />
              </label>
              {evidenceNote === "done" && (
                <span className="t-meta" data-evidence-uploaded
                      style={{ color: "var(--color-moss-600)" }}>
                  {t("profile.evidence.uploaded")}
                </span>
              )}
              {evidenceNote === "error" && (
                <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                  {t("app.error")}
                </span>
              )}
            </div>
          </Card>
          {evidence.loading && <Loading />}
          {evidence.error && <Failure error={evidence.error} onRetry={evidence.reload} />}
          {evidence.data?.length === 0 && <Empty />}
          <Grid min={280}>
            {evidence.data?.map((item) => (
              <Card key={item.evidence_id} as="article">
                <div className="t-micro text-fg-faint">{item.evidence_type}</div>
                <div className="t-section mt-1 text-fg">
                  {item.issuer ?? item.source}
                </div>
                <div className="t-meta mt-1 text-fg-muted">
                  {item.obtained_at}
                  {item.expires_at ? ` → ${item.expires_at}` : ""}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <TriState
                    value={VERIFICATION_TRI[item.verification_status] ?? "unknown"}
                    label={t(
                      VERIFICATION_KEY[item.verification_status] ??
                        "profile.evidence.self_reported",
                    )}
                  />
                  <span className="t-mono text-fg-faint" lang={locale}>
                    {item.visibility}
                  </span>
                </div>
              </Card>
            ))}
          </Grid>
        </div>
      )}
    </>
  );
}
