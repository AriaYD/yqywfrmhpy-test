"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized, pickLang, type Locale, type MessageKey } from "@/i18n";
import { api, type Opportunity, type PlanItem } from "@/lib/api";
import {
  NEAR_WINDOW_DAYS,
  planActivities,
  planAnchor,
  storedIntensity,
  withinWindow,
} from "@/lib/plan-window";
import { useResource } from "@/lib/useResource";
import { PlanHub } from "@/components/plan-hub";
import {
  Bar,
  Card,
  CredentialChip,
  Empty,
  Failure,
  Loading,
  Metric,
  PageHeader,
  SectionTitle,
  Segmented,
} from "@/components/ui";

/**
 * 课外活动规划（I，2026-07-31 由"路径时间线"改名并收窄范围）。
 *
 * 只呈现**课外**条目——比赛、实习、工作坊、证书、语言考试。
 * 课程一律不进本页：必修与选修都在「选课与学位规划」分页（用户裁定）。
 * 四种跨度读同一个 PathwayVersion，数据同源，不可能互相矛盾。
 */
type Range = "near" | "month" | "term" | "year";

const RANGE_DAYS: Record<Range, number> = {
  near: NEAR_WINDOW_DAYS, month: 30, term: 150, year: 365,
};
const RANGE_KEY: Record<Range, MessageKey> = {
  near: "timeline.range.near",
  month: "timeline.range.month",
  term: "timeline.range.term",
  year: "timeline.range.year",
};

const STATUS_KEY: Record<string, MessageKey> = {
  proposed: "timeline.item.pending",
  accepted: "timeline.item.pending",
  in_progress: "timeline.item.active",
  completed: "timeline.item.done",
  skipped: "timeline.item.pending",
  blocked: "timeline.item.pending",
};


export default function TimelinePage() {
  // R4-L：/timeline 深链接落在合并页的"课外活动规划"分页
  return <PlanHub initial="activities" />;
}

/** J：活动卡的推荐理由与详情。理由优先取 A5 的匹配理由；没有就按规则生成并如实标注。 */
function activityReason(
  item: PlanItem,
  opp: Opportunity | null,
  matchReason: string | null,
  t: (k: MessageKey) => string,
  locale: Locale,
): { text: string; ruleGenerated: boolean } {
  if (matchReason) return { text: matchReason, ruleGenerated: false };
  const cats = (opp?.requirement_categories ?? []).join(" / ");
  const skills = (opp?.skills ?? []).slice(0, 3).join(", ");
  const what = cats || skills;
  const zhFirst = what
    ? `这项${opp ? "" : "计划"}覆盖你目标要求中的 ${what}。`
    : "这一项在你批准的路径里，服务于你当前的目标方向。";
  const zhSecond = skills && cats
    ? `完成后可积累 ${skills} 相关证据。`
    : "完成后会作为证据挂到对应的能力条目下。";
  const enFirst = what
    ? `This item covers ${what} from your goal requirements.`
    : "This item sits on your approved pathway and serves your current goal.";
  const enSecond = skills && cats
    ? ` Completing it builds evidence for ${skills}.`
    : " Completing it becomes evidence under the matching requirement.";
  return {
    text: pickLang(locale, `${zhFirst}${zhSecond}`, `${enFirst}${enSecond}`),
    ruleGenerated: true,
  };
}

function DeclineButton({ studentId, planItemId, onDone }: {
  studentId: string; planItemId: string; onDone: () => void;
}) {
  const { t } = useI18n();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  if (!confirming) {
    return (
      <button type="button" data-decline={planItemId}
              title={t("timeline.decline.hint")}
              aria-label={t("timeline.decline.hint")}
              onClick={() => setConfirming(true)}
              className="pressable btn btn-ghost t-meta"
              style={{ color: "var(--fg-faint)", padding: "4px 8px" }}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round"
             aria-hidden>
          <path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
          <path d="M10 11v6M14 11v6" />
        </svg>
      </button>
    );
  }
  return (
    <span className="flex items-center gap-1.5" data-decline-confirm={planItemId}>
      <button type="button" data-decline-yes={planItemId} disabled={busy}
              onClick={async () => {
                setBusy(true);
                try { await api.declinePlanItem(studentId, planItemId); onDone(); }
                finally { setBusy(false); setConfirming(false); }
              }}
              className="pressable btn btn-danger t-micro">
        {t("timeline.decline.confirm")}
      </button>
      <button type="button" onClick={() => setConfirming(false)}
              className="pressable btn btn-ghost t-micro">
        {t("calendar.editor.cancel")}
      </button>
    </span>
  );
}

export function ActivityPlanContent({ standalone = false }: { standalone?: boolean }) {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [range, setRange] = useState<Range>("term");
  // S1 三档强度（2026-08-03 用户问出缺口）：三变体一直在后台生成，
  // 现在学生可选——选择持久化，A5 按档重出课程计划
  const [intensity, setIntensity] = useState<string>(storedIntensity);
  const pathway = useResource(
    () => api.pathway(studentId, intensity), [studentId, intensity]);
  const trajectory = useResource(() => api.growthTrajectory(studentId), [studentId]);
  // J：卡片要挂活动详情与官方链接——从目录取；推荐理由——从 A5 的匹配结果取
  const catalog = useResource(() => api.catalog(500, true), []);
  const matches = useResource(() => api.matches(studentId), [studentId]);

  const oppOf = (item: PlanItem): Opportunity | null =>
    (catalog.data ?? []).find((o) => o.opportunity_id === item.subject_id) ?? null;
  const matchReasonOf = (item: PlanItem): string | null => {
    const m = (matches.data ?? []).find((x) => x.opportunity_id === item.subject_id);
    if (!m || !m.reasons.length) return null;
    return localized(m.reasons[0], locale);
  };

  const items = pathway.data?.plan_items ?? [];
  // 课程不进本页（I）；窗口口径与行动中心共用 plan-window，单一出处
  const activities = planActivities(items);
  const from = planAnchor(activities);
  const shown = activities.filter((item) =>
    withinWindow(item, RANGE_DAYS[range], from),
  );
  const coursesHidden = items.length - activities.length;


  return (
    <>
      <PageHeader titleKey="timeline.title" leadKey="timeline.lead">
        <Segmented
          ariaLabel={t("timeline.title")}
          value={range}
          onChange={setRange}
          options={(["near", "month", "term", "year"] as Range[]).map((r) => ({
            value: r,
            label: t(RANGE_KEY[r]),
          }))}
        />
      </PageHeader>

      {/* S1 三档强度选择（2026-08-03，用户复裁定样式）：**不是导航**，
          不用 Segmented——mist 色系标签药丸与分页控件明确区隔；
          选择本地持久化，A5 按档重出课程计划 */}
      <div className="mb-4 flex flex-wrap items-center gap-2" data-intensity-picker>
        <span className="t-meta text-fg-muted">{t("timeline.intensity")}</span>
        {(["low_load", "balanced", "ambitious"] as const).map((v) => {
          const active = intensity === v;
          return (
            <button key={v} type="button" data-intensity={v}
                    aria-pressed={active}
                    onClick={() => { setIntensity(v);
                      window.localStorage.setItem("campuspath.intensity", v); }}
                    className="pressable chip t-meta"
                    style={{
                      borderColor: active ? "var(--color-mist-500)" : "var(--line)",
                      background: active ? "var(--color-mist-100)" : "transparent",
                      color: active ? "var(--color-mist-700)" : "var(--fg-muted)",
                      fontWeight: active ? 500 : 400,
                    }}>
              {t(`timeline.intensity.${v}` as Parameters<typeof t>[0])}
            </button>
          );
        })}
        {pathway.data?.course_plan && (
          <span className="t-micro text-fg-faint" data-intensity-note>
            {t("timeline.intensity.note")}: {pathway.data.course_plan.course_items.length}
          </span>
        )}
      </div>

      {/* G4 成长曲线 */}
      <Card className="mb-5">
        <SectionTitle>{t("timeline.trajectory")}</SectionTitle>
        {trajectory.loading && <Loading />}
        {trajectory.error && <Failure error={trajectory.error} />}
        {trajectory.data && (
          <>
            {/* 2026-08-02 用户质询后收口：只显示口径可回溯的指标——
                「已关闭差距」判定链未接入、「目标信心」是无输入口的固定值，
                两者都撤下不展示（宁缺毋假） */}
            <div className="flex flex-wrap gap-8" data-trajectory>
              <Metric
                label={t("timeline.trajectory.evidenceAdded")}
                value={trajectory.data.points.reduce(
                  (n, p) => n + p.new_confirmed_evidence,
                  0,
                )}
              />
            </div>
            {/* 逐学期的柱：数值就是 verified_growth_actions，不做平滑、不做插值 */}
            <ul className="mt-5 flex items-end gap-3" data-trajectory-chart>
              {trajectory.data.points.map((point) => {
                const peak = Math.max(
                  1,
                  ...trajectory.data!.points.map((p) => p.verified_growth_actions),
                );
                return (
                  <li key={point.term} className="max-w-[84px] flex-1">
                    <div
                      className="rounded-t-[4px]"
                      style={{
                        height: `${(point.verified_growth_actions / peak) * 76 + 4}px`,
                        background: "var(--accent)",
                      }}
                      title={`${point.term}: ${point.verified_growth_actions}`}
                    />
                    <div className="t-micro mt-1.5 text-fg-faint">{point.term}</div>
                    <div className="t-micro text-fg-faint tabular-nums">
                      {t("timeline.trajectory.coursesN")} {point.verified_growth_actions}
                      {point.new_confirmed_evidence > 0 &&
                        ` · ${t("timeline.trajectory.evidenceN")} ${point.new_confirmed_evidence}`}
                    </div>
                  </li>
                );
              })}
            </ul>
            <p className="t-micro mt-3 text-fg-faint" data-trajectory-method>
              {t("timeline.trajectory.method")}
            </p>
          </>
        )}
      </Card>

      {pathway.loading && <Loading />}
      {pathway.error && (
        <Failure
          error={pathway.error}
          emptyKey="timeline.empty"
          onRetry={pathway.reload}
        />
      )}

      {pathway.data && (
        <>
          {pathway.data.trigger === "demo_fixture" && (
            <p
              className="t-meta mb-4 rounded-md border p-3"
              data-pathway-fixture
              style={{
                borderColor: "var(--hatch)",
                color: "var(--hatch-ink)",
                background: "color-mix(in srgb, var(--hatch) 8%, transparent)",
              }}
            >
              {localized(pathway.data.assumptions[0], locale)}
            </p>
          )}
          {coursesHidden > 0 && (
            <p className="t-micro mb-3 text-fg-faint" data-courses-elsewhere>
              {t("timeline.coursesElsewhere")}
            </p>
          )}
          {shown.length === 0 && <Empty messageKey="timeline.empty" />}
          <ol className="relative flex flex-col gap-3" data-plan-items>
            {shown.map((item) => {
              const opp = oppOf(item);
              const reason = activityReason(item, opp, matchReasonOf(item), t, locale);
              const brief = opp
                ? [
                    opp.organizer_localized
                      ? localized(opp.organizer_localized, locale)
                      : opp.organizer,
                    opp.type,
                    ...(opp.category_tags.length ? [opp.category_tags.join(" · ")] : []),
                  ].join(" · ")
                : null;
              const snippet = opp?.provenance.evidence_snippet ?? null;
              const timeText = opp?.starts_at
                ? `${opp.starts_at.slice(0, 10)} → ${opp.ends_at?.slice(0, 10) ?? "—"}`
                : `${item.date_range.start} → ${item.date_range.end ?? "—"}`;
              return (
                <Card key={item.plan_item_id} as="li">
                  <div
                    data-plan-item={item.plan_item_id}
                    className="flex flex-wrap items-start justify-between gap-3"
                  >
                    <div className="min-w-0">
                      <div className="t-micro text-fg-faint">
                        {t("timeline.card.time")}{locale.startsWith("zh") ? "：" : ": "}{timeText}
                      </div>
                      <div className="t-section mt-1 text-fg">
                        {opp && opp.title_localized
                          ? localized(opp.title_localized, locale)
                          : (opp?.title ?? localized(item.title, locale))}
                      </div>
                      <div className="t-meta mt-1 text-fg-muted">
                        {item.kind} · {item.workload_hours.toFixed(0)}
                        {t("calendar.hours")}
                        {brief ? ` · ${brief}` : ""}
                      </div>
                      {snippet && (
                        <p className="t-meta mt-2 max-w-[70ch] text-fg-muted" data-activity-brief>
                          {t("timeline.card.brief")}{locale.startsWith("zh") ? "：" : ": "}{snippet}
                        </p>
                      )}
                      {/* 国际生 Pack 派生项（2026-08-02 用户裁定）：不贴通用
                          "规则生成"复读——标注为国际生提前准备事项，并把
                          assumptions 里的官方指引渲染成可点链接 */}
                      {item.plan_item_id.startsWith("PI-INTL-") ? (
                        <div className="intl-note t-meta mt-2 max-w-[70ch]"
                             data-intl-plan-note
                             style={{ color: "var(--color-mist-700)" }}>
                          <span className="font-medium">
                            {t("timeline.reason.intl")}
                          </span>
                          {item.assumptions.map((line, i) => {
                            const text = localized(line, locale);
                            const url = text.match(/https?:\/\/\S+/)?.[0];
                            return (
                              <p key={i} className="mt-1" data-intl-guidance>
                                {url ? (
                                  <>
                                    {text.slice(0, text.indexOf(url))}
                                    <a href={url} target="_blank" rel="noreferrer"
                                       className="underline underline-offset-2 break-all">
                                      {url}
                                    </a>
                                  </>
                                ) : text}
                              </p>
                            );
                          })}
                        </div>
                      ) : (
                        <p className="ai-note t-meta mt-2 max-w-[70ch]" data-activity-reason
                           style={{ color: "var(--fg)" }}>
                          {t("timeline.card.reason")}{locale.startsWith("zh") ? "：" : ": "}{reason.text}
                          {reason.ruleGenerated && (
                            <span className="t-micro ms-2 text-fg-faint">
                              （{t("timeline.reason.rule")}）
                            </span>
                          )}
                        </p>
                      )}
                      {opp?.official_url && (
                        <a
                          href={opp.official_url}
                          target="_blank"
                          rel="noreferrer"
                          data-activity-official={item.plan_item_id}
                          className="t-meta mt-2 inline-block underline underline-offset-2"
                          style={{ color: "var(--accent-deep)" }}
                        >
                          {t("timeline.card.official")} ↗
                        </a>
                      )}
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      <span className="t-meta text-fg-muted">
                        {t(STATUS_KEY[item.status] ?? "timeline.item.pending")}
                      </span>
                      <CredentialChip validationId={item.validation_id} />
                      {/* 「不参加」（2026-08-03 用户需求）：仅活动类条目；
                          破坏性动作走二段确认，删除=规划+日历一并移除 */}
                      {item.kind === "opportunity" && (
                        <DeclineButton
                          studentId={studentId}
                          planItemId={item.plan_item_id}
                          onDone={() => pathway.reload()}
                        />
                      )}
                    </div>
                  </div>
                  <div className="mt-3">
                    <Bar
                      ratio={
                        item.status === "completed"
                          ? 1
                          : item.status === "in_progress"
                            ? 0.45
                            : 0.08
                      }
                    />
                  </div>
                </Card>
              );
            })}
          </ol>
        </>
      )}
      {/* standalone 深链接与 planner 分页共用同一份内容 */}
      {standalone ? null : null}
    </>
  );
}
