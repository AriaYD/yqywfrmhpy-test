"use client";

import { useMemo, useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, type MessageKey } from "@/i18n";
import { api, type Schemas } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Card,
  Empty,
  Failure,
  Loading,
  PageHeader,
  SectionTitle,
} from "@/components/ui";

/**
 * 原文留在私有域。
 *
 * 页面上那句"只有评分与结构化标签会向下游传递"不是承诺，是类型层事实：
 * Aggregation 只接受 `EventQualityFeedback`，自由文本在类型上就传不过去（B10）。
 *
 * R4-D/E/F（2026-07-31）：
 * · 两个分页：写一条反思 / 反思记录（整洁）；
 * · 记录页把普通反思、种子笔记、Advisor 会面**合并成一个列表**，
 *   搜索框旁按五类标签 + 三维评分下限 + 匹配标签筛选；
 * · Advisor 的关键建议**先写会面反思才解锁**——先记下自己的收获，
 *   再看别人给你的总结。
 */
type Subject = {
  id: string;
  label: string;
  kindKey: MessageKey;
  detail?: string;
};

type RecordCategory =
  | "advisor" | "lecture_course" | "internship_job" | "lab_research" | "other";

const CATEGORY_KEY: Record<RecordCategory, MessageKey> = {
  advisor: "reflections.cat.advisor",
  lecture_course: "reflections.cat.lecture",
  internship_job: "reflections.cat.internship",
  lab_research: "reflections.cat.lab",
  other: "reflections.cat.other",
};

type Booking = Schemas["AdvisorBooking"];
type ReflectionRow = Schemas["Reflection"];
type NoteRow = Schemas["Note"];

export default function ReflectionsPage() {
  const { t } = useI18n();
  const [tab, setTab] = useState<"compose" | "records">("compose");
  const [preselect, setPreselect] = useState<string | null>(null);

  return (
    <>
      <PageHeader titleKey="reflections.title" leadKey="reflections.lead" />
      <div
        className="mb-5 inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
        data-page-tabs
      >
        {(["compose", "records"] as const).map((tabKey) => (
          <button
            key={tabKey}
            type="button"
            data-page-tab={tabKey}
            aria-pressed={tab === tabKey}
            onClick={() => setTab(tabKey)}
            className="pressable t-meta rounded-sm px-3 py-1.5"
            style={{
              background: tab === tabKey ? "var(--accent-deep)" : "transparent",
              color: tab === tabKey ? "var(--accent-fg)" : "var(--fg-muted)",
              fontWeight: tab === tabKey ? 600 : 500,
            }}
          >
            {t(tabKey === "compose" ? "reflections.tab.compose" : "reflections.tab.records")}
          </button>
        ))}
      </div>
      {tab === "compose" ? (
        <ComposeTab initialSubject={preselect} onSaved={() => setPreselect(null)} />
      ) : (
        <RecordsTab
          onWriteFor={(subjectId) => {
            setPreselect(subjectId);
            setTab("compose");
          }}
        />
      )}
    </>
  );
}

/* ────────────────────────── 写一条反思 ────────────────────────── */

function ComposeTab({
  initialSubject,
  onSaved,
}: {
  initialSubject: string | null;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const { studentId } = usePersona();
  const [draft, setDraft] = useState("");
  const [ratings, setRatings] = useState({ depth: 3, learned: 3, organization: 3, expectation: 3 });
  const [fit, setFit] = useState<"good_fit" | "too_basic_for_me" | "too_advanced_for_me" | "wrong_format_for_me" | "schedule_mismatch">("good_fit");
  const [subjectId, setSubjectId] = useState<string>(initialSubject ?? "");
  const [saveState, setSaveState] = useState<"idle" | "saving" | "saved" | "error">(
    "idle",
  );
  const [kindFilter, setKindFilter] = useState<"all" | "experience" | "course" | "opportunity" | "advisor">("all");

  const bookings = useResource(() => api.myAdvisorBookings(studentId), [studentId]);
  const experiences = useResource(() => api.experiences(studentId), [studentId]);
  const academic = useResource(() => api.academicState(studentId), [studentId]);
  const pathway = useResource(() => api.pathway(studentId), [studentId]);
  const catalog = useResource(() => api.catalog(500), []);
  const actions = useResource(() => api.actions(studentId), [studentId]);

  const subjects = useMemo<Subject[]>(() => {
    const out: Subject[] = [];

    for (const e of experiences.data ?? []) {
      out.push({
        id: e.experience_id,
        label: `${e.organization} · ${e.role}`,
        kindKey: "reflections.kind.experience",
        detail: `${e.period.start}${e.period.end ? ` → ${e.period.end}` : ""}`,
      });
    }

    // 只列**修过或在修**的课。对一门没上过的课写反思没有意义。
    for (const r of academic.data?.course_records ?? []) {
      if (r.status !== "completed" && r.status !== "enrolled") continue;
      out.push({
        id: r.course_id,
        label: r.course_id,
        kindKey: "reflections.kind.course",
        detail: r.term,
      });
    }

    // 进了计划的机会 + **报名/批准过的活动**（R 报告 P1-1：闭环最后一环）
    const engaged = new Set(
      (pathway.data?.plan_items ?? [])
        .filter((i) => i.kind === "opportunity")
        .map((i) => i.subject_id),
    );
    for (const a of actions.data ?? []) {
      if (a.action_type === "apply" && a.subject_id.startsWith("OPP-")) {
        engaged.add(a.subject_id);
      }
    }
    for (const o of catalog.data ?? []) {
      if (!engaged.has(o.opportunity_id)) continue;
      out.push({
        id: o.opportunity_id,
        label: o.title,
        kindKey: "reflections.kind.opportunity",
        detail: o.organizer,
      });
    }

    // 见过 Advisor 之后，这次会面本身就是一个值得反思的对象
    for (const b of bookings.data ?? []) {
      if (b.status !== "completed") continue;
      out.push({
        id: b.booking_id,
        label: `Advisor · ${b.topic}`,
        kindKey: "reflections.kind.advisor",
        detail: b.requested_slot.start.slice(0, 10),
      });
    }
    return out;
  }, [experiences.data, academic.data, pathway.data, catalog.data,
      bookings.data, actions.data]);

  const shown =
    kindFilter === "all"
      ? subjects
      : subjects.filter((s) => s.kindKey.endsWith(kindFilter));

  const chosen = subjects.find((s) => s.id === subjectId);
  const canSave = Boolean(subjectId) && draft.trim().length > 0;

  return (
    <Card className="mb-5">
      <SectionTitle>{t("reflections.new")}</SectionTitle>

      {/* D 批（2026-08-02 用户裁定 B）：promotion 高亮语——说清两条反馈回路的价值 */}
      <div className="ai-note t-meta mb-3 flex flex-col gap-1 text-fg" data-reflection-promo>
        <span>{t("reflections.promo1")}</span>
        <span>{t("reflections.promo2")}</span>
      </div>

      <div className="t-micro mb-2 text-fg-faint">{t("reflections.subject")}</div>
      <div className="mb-3 flex flex-wrap gap-1.5" data-subject-filters>
        {(["all", "experience", "course", "opportunity", "advisor"] as const).map((k) => (
          <button
            key={k}
            type="button"
            data-subject-filter={k}
            aria-pressed={kindFilter === k}
            onClick={() => setKindFilter(k)}
            className="pressable t-meta rounded-sm border px-2.5 py-1"
            style={{
              borderColor: kindFilter === k ? "var(--accent)" : "var(--line)",
              color: kindFilter === k ? "var(--accent-deep)" : "var(--fg-muted)",
            }}
          >
            {t(
              k === "all"
                ? "gaps.filter.all"
                : (`reflections.kind.${k}` as MessageKey),
            )}
          </button>
        ))}
      </div>

      {(experiences.loading || academic.loading) && <Loading />}
      {shown.length === 0 && !experiences.loading && (
        <Empty messageKey="reflections.noSubjects" />
      )}

      <ul className="mb-5 flex max-h-[220px] flex-col gap-1.5 overflow-y-auto" data-subject-list>
        {shown.map((s) => {
          const active = subjectId === s.id;
          return (
            <li key={`${s.kindKey}-${s.id}`}>
              <button
                type="button"
                data-subject-option={s.id}
                aria-pressed={active}
                onClick={() => setSubjectId(active ? "" : s.id)}
                className="pressable flex w-full items-center justify-between gap-3 rounded-md border px-3 py-2 text-start"
                style={{
                  borderColor: active ? "var(--accent)" : "var(--line)",
                  background: active ? "var(--accent-soft)" : "transparent",
                }}
              >
                <span className="min-w-0">
                  <span className="t-body block truncate text-fg">{s.label}</span>
                  {s.detail && (
                    <span className="t-mono text-fg-faint">{s.detail}</span>
                  )}
                </span>
                <span className="t-micro shrink-0 text-fg-faint">{t(s.kindKey)}</span>
              </button>
            </li>
          );
        })}
      </ul>

      <label className="block">
        <span className="t-micro text-fg-faint">
          {t("reflections.body")}
          {chosen ? ` — ${chosen.label}` : ""}
        </span>
        <textarea
          data-reflection-input
          rows={4}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="field t-body mt-1.5 w-full p-3 placeholder:text-fg-faint"
          placeholder={
            chosen ? t("reflections.body") : t("reflections.pickSubjectFirst")
          }
          disabled={!subjectId}
        />
      </label>

      {/* 多维评分：质量维度进聚合，个人匹配走 FitTag——两者不混（§17.4） */}
      {[
        { key: "depth", labelKey: "reflections.rate.depth" },
        { key: "learned", labelKey: "reflections.rate.learned" },
        { key: "organization", labelKey: "reflections.rate.organization" },
        { key: "expectation", labelKey: "reflections.rate.expectation" },
      ].map(({ key, labelKey }) => (
        <div className="mt-4" key={key}>
          <span className="t-micro text-fg-faint">{t(labelKey as Parameters<typeof t>[0])}</span>
          <div className="mt-1.5 flex gap-1.5" role="radiogroup"
               aria-label={t(labelKey as Parameters<typeof t>[0])}>
            {[1, 2, 3, 4, 5].map((value) => {
              const active = ratings[key as keyof typeof ratings] === value;
              return (
                <button
                  key={value}
                  type="button"
                  role="radio"
                  aria-checked={active}
                  data-rating={`${key}-${value}`}
                  onClick={() => setRatings((prev) => ({ ...prev, [key]: value }))}
                  className="pressable t-meta h-9 w-9 rounded-md border tabular-nums"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--line)",
                    background: active ? "var(--accent-deep)" : "transparent",
                    color: active ? "var(--accent-fg)" : "var(--fg-muted)",
                  }}
                >
                  {value}
                </button>
              );
            })}
          </div>
        </div>
      ))}

      <div className="mt-4">
        <span className="t-micro text-fg-faint">{t("reflections.rate.fit")}</span>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {(["good_fit", "too_basic_for_me", "too_advanced_for_me",
             "wrong_format_for_me", "schedule_mismatch"] as const).map((tag) => (
            <button
              key={tag}
              type="button"
              data-fit={tag}
              aria-pressed={fit === tag}
              onClick={() => setFit(tag)}
              className="pressable t-meta rounded-md border px-2.5 py-1"
              style={{
                borderColor: fit === tag ? "var(--accent)" : "var(--line)",
                background: fit === tag ? "var(--accent-soft)" : "transparent",
                color: fit === tag ? "var(--accent-deep)" : "var(--fg-muted)",
              }}
            >
              {t(`reflections.fit.${tag}` as Parameters<typeof t>[0])}
            </button>
          ))}
        </div>
      </div>

      <p
        className="t-meta mt-4 rounded-md p-3"
        data-reflection-boundary
        style={{
          border: "1px dashed var(--hatch)",
          color: "var(--hatch-ink)",
          background: "color-mix(in srgb, var(--hatch) 7%, transparent)",
        }}
      >
        {t("reflections.boundary")}
      </p>

      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          data-reflection-save
          disabled={!canSave || saveState === "saving"}
          onClick={async () => {
            setSaveState("saving");
            try {
              // 原文只进 private_text；评分留一份自用副本（私有域），
              // 出域的仍是 event-feedback 的去标识那份。
              await api.submitReflection(studentId, {
                reflection_id: `REFL-${studentId}-${Date.now()}`,
                student_id: studentId,
                subject_id: subjectId,
                personal_learning: null,
                preference_delta: [],
                goal_delta: [],
                energy_cost: "moderate",
                next_action: null,
                private_text: draft,
                profile_candidate_ids: [],
                created_at: new Date().toISOString(),
                rating_content_depth: ratings.depth,
                rating_practical_value: ratings.learned,
                rating_organization: ratings.organization,
                rating_expectation_match: ratings.expectation,
                fit_tag: fit,
              });
              if (chosen?.kindKey === "reflections.kind.opportunity") {
                await api.submitEventFeedback(studentId, {
                  subject_id: subjectId,
                  content_depth: ratings.depth,
                  practical_value: ratings.learned,
                  organization: ratings.organization,
                  expectation_match: ratings.expectation,
                  fit,
                  attended_verified: false,
                });
              }
              setSaveState("saved");
              setDraft("");
              onSaved();
            } catch {
              setSaveState("error");
            }
          }}
          className="pressable btn btn-primary t-body font-medium disabled:opacity-40"
        >
          {saveState === "saving" ? t("app.loading") : t("reflections.save")}
        </button>
        {/* 审计黄-11：按钮置灰要说清缺什么，不许让学生猜 */}
        {!canSave && saveState !== "saving" && (
          <span className="t-micro text-fg-faint" data-save-hint>
            {t(subjectId ? "reflections.save.needText"
               : "reflections.save.needSubject")}
          </span>
        )}
        {saveState === "saved" && (
          <span className="t-meta" style={{ color: "var(--color-moss-600)" }}
                data-reflection-saved>
            {t("reflections.saved")}
          </span>
        )}
        {saveState === "error" && (
          <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
            {t("reflections.saveFailed")}
          </span>
        )}
      </div>
    </Card>
  );
}

/* ────────────────────────── 反思记录 ────────────────────────── */

type RecordEntry = {
  id: string;
  date: string;
  subjectId: string | null;
  category: RecordCategory;
  text: string;
  ratings: { depth: number; learned: number; organization: number } | null;
  fit: string | null;
  booking: Booking | null;
  myReflection?: string | null;
};

function RecordsTab({ onWriteFor }: { onWriteFor: (subjectId: string) => void }) {
  const { t } = useI18n();
  const { studentId } = usePersona();
  const [searchTerm, setSearchTerm] = useState("");
  const [category, setCategory] = useState<"all" | RecordCategory>("all");
  const [minScores, setMinScores] = useState({ depth: 0, learned: 0, organization: 0 });

  const notes = useResource(() => api.notes(studentId), [studentId]);
  const reflections = useResource(() => api.myReflections(studentId), [studentId]);
  const bookings = useResource(() => api.myAdvisorBookings(studentId), [studentId]);
  const experiences = useResource(() => api.experiences(studentId), [studentId]);
  const catalog = useResource(() => api.catalog(500, true), []);

  function categorize(subjectId: string | null): RecordCategory {
    if (!subjectId) return "other";
    if (subjectId.startsWith("ADV")) return "advisor";
    if (/^[A-Z]{4} \d{4}/.test(subjectId)) return "lecture_course";
    const opp = (catalog.data ?? []).find((o) => o.opportunity_id === subjectId);
    if (opp) {
      if (opp.type === "internship" || opp.type === "job") return "internship_job";
      if (opp.type === "research_position") return "lab_research";
      return "other";
    }
    const exp = (experiences.data ?? []).find((e) => e.experience_id === subjectId);
    if (exp) {
      if (exp.type === "internship" || exp.type === "part_time") return "internship_job";
      if (exp.type === "research") return "lab_research";
      return "other";
    }
    return "other";
  }

  // R4-E：三种来源合并成一个列表。
  // R6-C（2026-08-01）：同一次 Advisor 会面**只出一条**——预约条目吸收
  // 学生对它写的反思（topic + 时间 + 我的反思 + Advisor 建议在同一卡上），
  // 被吸收的反思不再单独成条，避免同一件事在列表里出现两次。
  const entries = useMemo<RecordEntry[]>(() => {
    const out: RecordEntry[] = [];
    const bookingIds = new Set(
      ((bookings.data ?? []) as Booking[]).map((b) => b.booking_id),
    );
    const reflectionByBooking = new Map<string, ReflectionRow>();
    for (const r of (reflections.data ?? []) as ReflectionRow[]) {
      if (bookingIds.has(r.subject_id)) {
        // 同一会面多条反思时取最新一条并入卡片
        const existing = reflectionByBooking.get(r.subject_id);
        if (!existing || r.created_at > existing.created_at) {
          reflectionByBooking.set(r.subject_id, r);
        }
        continue;                            // 不单独成条
      }
      out.push({
        id: r.reflection_id,
        date: r.created_at.slice(0, 10),
        subjectId: r.subject_id,
        category: categorize(r.subject_id),
        text: r.private_text ?? r.personal_learning ?? "",
        ratings:
          r.rating_content_depth != null
            ? {
                depth: r.rating_content_depth,
                learned: r.rating_practical_value ?? 0,
                organization: r.rating_organization ?? 0,
              }
            : null,
        fit: r.fit_tag ?? null,
        booking: null,
      });
    }
    for (const note of (notes.data ?? []) as NoteRow[]) {
      out.push({
        id: note.note_id,
        date: note.created_at.slice(0, 10),
        subjectId: note.linked_entities[0] ?? null,
        category: categorize(note.linked_entities[0] ?? null),
        text: note.text ?? "",
        ratings: null,
        fit: null,
        booking: null,
      });
    }
    for (const b of (bookings.data ?? []) as Booking[]) {
      const mine = reflectionByBooking.get(b.booking_id);
      out.push({
        id: b.booking_id,
        date: b.requested_slot.start.slice(0, 10),
        subjectId: b.booking_id,
        category: "advisor",
        text: b.topic,
        ratings:
          mine?.rating_content_depth != null
            ? {
                depth: mine.rating_content_depth,
                learned: mine.rating_practical_value ?? 0,
                organization: mine.rating_organization ?? 0,
              }
            : null,
        fit: mine?.fit_tag ?? null,
        booking: b,
        myReflection: mine?.private_text ?? mine?.personal_learning ?? null,
      });
    }
    return out.sort((a, b) => b.date.localeCompare(a.date));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reflections.data, notes.data, bookings.data, catalog.data, experiences.data]);

  const reflectedSubjects = useMemo(
    () => new Set((reflections.data ?? []).map((r) => r.subject_id)),
    [reflections.data],
  );

  const scoreActive =
    minScores.depth > 0 || minScores.learned > 0 || minScores.organization > 0;
  const shown = entries.filter((entry) => {
    if (category !== "all" && entry.category !== category) return false;
    if (scoreActive) {
      if (!entry.ratings) return false;      // 没有评分的条目不可能满足评分下限
      if (entry.ratings.depth < minScores.depth) return false;
      if (entry.ratings.learned < minScores.learned) return false;
      if (entry.ratings.organization < minScores.organization) return false;
    }
    if (searchTerm.trim()) {
      const needle = searchTerm.trim().toLowerCase();
      return (
        entry.text.toLowerCase().includes(needle) ||
        (entry.subjectId ?? "").toLowerCase().includes(needle)
      );
    }
    return true;
  });

  return (
    <>
      <Card className="mb-4">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="search"
            data-reflection-search
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder={t("reflections.search")}
            className="field t-body w-full max-w-[320px] px-3 py-2 placeholder:text-fg-faint"
          />
          {/* 五类标签筛选（E） */}
          <div className="flex flex-wrap gap-1.5" data-category-filters>
            {(["all", "advisor", "lecture_course", "internship_job",
               "lab_research", "other"] as const).map((c) => (
              <button
                key={c}
                type="button"
                data-category-filter={c}
                aria-pressed={category === c}
                onClick={() => setCategory(c)}
                className="pressable t-meta rounded-sm border px-2.5 py-1"
                style={{
                  borderColor: category === c ? "var(--accent)" : "var(--line)",
                  color: category === c ? "var(--accent-deep)" : "var(--fg-muted)",
                }}
              >
                {t(c === "all" ? "gaps.filter.all" : CATEGORY_KEY[c])}
              </button>
            ))}
          </div>
        </div>
        {/* 评分下限筛选（E）：回顾时把收获大的经历快速捞出来 */}
        <div className="mt-3 flex flex-wrap items-center gap-3" data-score-filters>
          {(
            [
              ["depth", "reflections.rate.depth"],
              ["learned", "reflections.rate.learned"],
              ["organization", "reflections.rate.organization"],
            ] as const
          ).map(([key, labelKey]) => (
            <label key={key} className="t-micro flex items-center gap-1.5 text-fg-faint">
              {t(labelKey)}
              <select
                data-score-filter={key}
                value={minScores[key]}
                onChange={(e) =>
                  setMinScores((prev) => ({ ...prev, [key]: Number(e.target.value) }))
                }
                className="field t-meta px-1.5 py-0.5 text-fg"
              >
                <option value={0}>{t("gaps.filter.all")}</option>
                {[3, 4, 5].map((n) => (
                  <option key={n} value={n}>≥ {n}</option>
                ))}
              </select>
            </label>
          ))}
        </div>
      </Card>

      {(notes.loading || reflections.loading) && <Loading />}
      {notes.error && <Failure error={notes.error} onRetry={notes.reload} />}
      {shown.length === 0 && !notes.loading && <Empty messageKey="reflections.empty" />}

      <ul className="flex flex-col gap-3" data-record-list>
        {shown.map((entry) => (
          <Card key={entry.id} as="li">
            <div data-record={entry.id} data-record-category={entry.category}>
              <div className="t-micro flex justify-between text-fg-faint">
                <span>{t(CATEGORY_KEY[entry.category])}</span>
                <span>{entry.date}</span>
              </div>
              {entry.subjectId && !entry.booking && (
                <div className="t-mono mt-1.5 text-fg-muted" data-note-subject>
                  {t("reflections.subject")}: {entry.subjectId}
                </div>
              )}
              {entry.booking ? (
                <div data-advisor-merged={entry.booking.booking_id}>
                  <p className="t-body mt-1.5 font-medium text-fg">
                    {t("advisor.topic")}
                    {": "}{entry.booking.topic}
                  </p>
                  <p className="t-mono mt-0.5 text-fg-faint">
                    {entry.booking.requested_slot.start.slice(0, 16).replace("T", " ")}
                    {" · "}
                    {t(`advisor.status.${entry.booking.status}` as MessageKey)}
                  </p>
                  {entry.myReflection && (
                    <div className="mt-2" data-my-meeting-reflection>
                      <div className="t-micro text-fg-faint">
                        {t("reflections.mine")}
                      </div>
                      <p className="t-body mt-0.5 whitespace-pre-wrap text-fg">
                        {entry.myReflection}
                      </p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="t-body mt-2 whitespace-pre-wrap text-fg">{entry.text}</p>
              )}
              {entry.ratings && (
                <div className="t-micro mt-2 flex flex-wrap gap-3 text-fg-faint"
                     data-record-ratings>
                  <span>{t("reflections.rate.depth")} {entry.ratings.depth}/5</span>
                  <span>{t("reflections.rate.learned")} {entry.ratings.learned}/5</span>
                  <span>{t("reflections.rate.organization")} {entry.ratings.organization}/5</span>
                  {entry.fit && (
                    <span>{t(`reflections.fit.${entry.fit}` as MessageKey)}</span>
                  )}
                </div>
              )}

              {/* D：Advisor 关键建议——写完这次会面的反思才解锁 */}
              {entry.booking?.summary && (
                reflectedSubjects.has(entry.booking.booking_id) ? (
                  <div className="mt-2" data-advisor-advice>
                    <div className="t-micro text-fg-faint">{t("advisor.adviceTitle")}</div>
                    <ul className="mt-1 flex flex-col gap-1">
                      {entry.booking.summary.key_advice.map((line, index) => (
                        <li key={index} className="t-meta text-fg-muted">· {line}</li>
                      ))}
                    </ul>
                  </div>
                ) : (
                  <div
                    className="mt-2 rounded-md border p-3"
                    data-advice-locked={entry.booking.booking_id}
                    style={{ borderColor: "var(--hatch)" }}
                  >
                    <p className="t-meta" style={{ color: "var(--hatch-ink)" }}>
                      {t("advisor.adviceLocked")}
                    </p>
                    <button
                      type="button"
                      data-write-for-booking={entry.booking.booking_id}
                      onClick={() => onWriteFor(entry.booking!.booking_id)}
                      className="pressable btn btn-primary t-meta mt-2 font-medium"
                    >
                      {t("advisor.writeReflection")}
                    </button>
                  </div>
                )
              )}
              {entry.booking && !entry.booking.summary && (
                <div className="t-micro mt-2 text-fg-faint">
                  {t(`advisor.status.${entry.booking.status}` as MessageKey)}
                </div>
              )}
            </div>
          </Card>
        ))}
      </ul>
    </>
  );
}
