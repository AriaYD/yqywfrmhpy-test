"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized, pickLang, type MessageKey } from "@/i18n";
import { api, type Goal, type GoalDecomposition } from "@/lib/api";
import { EVIDENCE_BY_ID } from "@/lib/evidence-catalog";
import {
  LAYERS,
  LAYER_KEY,
  categoryFromRequirementId,
  categoryLabel,
  layerOf,
} from "@/lib/requirementLayers";
import { useResource } from "@/lib/useResource";
import {
  Bar,
  Card,
  Empty,
  Failure,
  Grid,
  Loading,
  PageHeader,
  SectionTitle,
} from "@/components/ui";

/**
 * G3：1 主目标 + 1 候选目标，界面同时显示**共享要求**与**分叉点**——
 * 只列两个目标而不说它们哪里重合，学生就得不到"先做共享部分"这个结论。
 *
 * 设定目标是**两步，顺序不能反**：
 *
 *   1. 先选五类方向之一（就业 / 深造 / 创业 / 探索中 / 发展个人特长）；
 *   2. 再在那个框架下写下具体终点（"入职某公司"、"做某个岗位"）。
 *
 * 反过来先让人填空，得到的是一句没有框架的话——"入职某公司"与
 * "读某个博士项目"在要求图上根本不是同一类东西；方向定不下来，
 * A3 就没有依据去建 Requirement Graph。
 *
 * **"探索中"是一等选项**，不是"还没想好"的占位（Spec §16.1）：
 * 不确定是合法状态，所以选它之后**不要求填终点**。
 */
const MODES = [
  { value: "employment", labelKey: "goals.mode.employment", targetType: "role" },
  { value: "academia", labelKey: "goals.mode.academia", targetType: "program" },
  {
    value: "entrepreneurship",
    labelKey: "goals.mode.entrepreneurship",
    targetType: "industry",
  },
  {
    value: "exploration",
    labelKey: "goals.mode.exploration",
    targetType: "exploration",
  },
  {
    value: "personal_interest",
    labelKey: "goals.mode.personal_interest",
    targetType: "skill",
  },
] as const;

type Mode = (typeof MODES)[number]["value"];

const MODE_HINT: Record<Mode, MessageKey> = {
  employment: "goals.hint.employment",
  academia: "goals.hint.academia",
  entrepreneurship: "goals.hint.entrepreneurship",
  exploration: "goals.hint.exploration",
  personal_interest: "goals.hint.personalInterest",
};


/**
 * 取证来源解析：生产端格式为 `「公司 · 岗位」URL`（zh）/ `[公司 · 岗位] URL`
 * （en，见 live_market_research.py）。URL 只进 href；标签剥掉括号。
 * 没有 URL 的来源（编制期取证）原文作纯文本药丸。
 */
function evidenceSourceParts(text: string): { label: string; url: string | null } {
  const match = text.match(/https?:\/\/\S+/i);
  if (!match) return { label: text.trim(), url: null };
  const label = text
    .replace(match[0], "")
    .replace(/[「」[\]]/g, "")
    .trim()
    .replace(/[（(]$/, "");
  return { label: label || new URL(match[0]).hostname, url: match[0] };
}

/**
 * 目标拆解面板（D）：硬性 / 软性（带取证来源）/ 特殊约束三层。
 * 内容来自人群 Pack（A3 确定性产出）；探索中/个人兴趣方向 422——
 * 面板如实显示"该方向暂无拆解 Pack"，不塞别人的模板。
 */
function GoalDecompositionPanel({
  studentId,
  goalId,
  cached,
  onLoaded,
}: {
  studentId: string;
  goalId: string;
  cached: GoalDecomposition | null | undefined;
  onLoaded: (d: GoalDecomposition | null) => void;
}) {
  const { t, locale } = useI18n();
  useEffect(() => {
    if (cached !== undefined) return;
    api
      .goalDecomposition(studentId, goalId)
      .then(onLoaded)
      .catch(() => onLoaded(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId, goalId]);

  // A4（2026-08-02）：现场 AI 拆解——任务在服务端，切页/关页不中断；
  // 挂载时先查有没有跑着的任务，有就直接续接进度条。
  type ResearchJob = Awaited<ReturnType<typeof api.decompositionResearchStatus>>;
  const [job, setJob] = useState<ResearchJob | null>(null);
  const [startErr, setStartErr] = useState<string | null>(null);
  useEffect(() => {
    let stop = false;
    api.decompositionResearchStatus(studentId, goalId)
      .then((j) => { if (!stop) setJob(j); })
      .catch(() => {});
    return () => { stop = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studentId, goalId]);
  useEffect(() => {
    if (job?.state !== "running") return;
    const timer = setInterval(async () => {
      try {
        const next = await api.decompositionResearchStatus(studentId, goalId);
        setJob(next);
        if (next.state === "done") {
          const fresh = await api.goalDecomposition(studentId, goalId);
          onLoaded(fresh);
        }
      } catch { /* 下一轮再试 */ }
    }, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.state, studentId, goalId]);
  async function startResearch() {
    setStartErr(null);
    try {
      setJob(await api.startDecompositionResearch(studentId, goalId));
    } catch (err) {
      const status = (err as { status?: number }).status;
      setStartErr(
        status === 429 ? t("goals.research.limit")
        : status === 503 ? t("goals.research.noModel")
        : t("goals.research.failed"),
      );
    }
  }

  // 评测 UI-1（2026-08-03）：加载中渲染骨架而不是空——慢网下"市场证据
  // 好像不存在"的空窗误读源于这里的 return null
  if (cached === undefined) return <Loading />;
  if (cached === null) {
    return (
      <p className="t-meta mt-4 text-fg-faint" data-decomp-none>
        {t("goals.decomp.none")}
      </p>
    );
  }
  /**
   * 三层分类的排版（用户裁定 2026-08-01）：分类头要突出、细则用 bullet 罗列。
   * 每层一个 pastel 色块分区（Vibrant & Block-based）：
   * 硬性=mist 蓝 / 软实力=sage 绿 / 特殊约束=blossom 粉，
   * 100 做底 700 做字（双主题各自达标，对比度脚本钉住）。
   */
  const groups: Array<{
    kind: "hard" | "soft" | "constraint";
    key: MessageKey;
    tone: "mist" | "sage" | "blossom";
  }> = [
    { kind: "hard", key: "goals.decomp.hard", tone: "mist" },
    { kind: "soft", key: "goals.decomp.soft", tone: "sage" },
    { kind: "constraint", key: "goals.decomp.constraint", tone: "blossom" },
  ];
  return (
    <div className="mt-5 flex flex-col gap-3" data-decomposition={goalId}>
      {/* 现场 AI 拆解：真流水线入口。
          2026-08-02 用户裁定：已有实采结果时**保留复用**并继续显示按钮——
          再点 = 忠实重新采集分析并覆盖旧结果（不是藏起按钮）。
          审计红-2 后半：**命中编制画像也照样给入口**——画像只是缓存，
          学生觉得不准可现场拆解，live 结果取代编制口径。 */}
      {job?.state !== "running" && (() => {
        const hasLive = cached.facets.some((f) => f.origin === "ai_live");
        const matched = cached.role_profile !== null && !hasLive;
        return (
        <div className="flex flex-wrap items-center gap-2" data-research-entry>
          <button
            type="button"
            data-research-start
            onClick={startResearch}
            className="pressable btn btn-secondary t-meta"
            style={{ borderColor: "var(--accent)", color: "var(--accent-deep)" }}
          >
            {t(hasLive ? "goals.research.rerun" : "goals.research.button")}
          </button>
          <span className="t-micro text-fg-faint">
            {t(hasLive ? "goals.research.existing"
               : matched ? "goals.research.whyMatched" : "goals.research.why")}
          </span>
          {job?.state === "failed" && (
            <span className="t-micro" style={{ color: "var(--color-clay-600)" }}>
              {t("goals.research.jobFailed")}
            </span>
          )}
          {startErr && (
            <span className="t-micro" style={{ color: "var(--color-clay-600)" }}>
              {startErr}
            </span>
          )}
        </div>
        );
      })()}
      {job?.state === "running" && (
        <div
          data-research-progress
          className="rounded-md border border-line bg-bg-sunk p-3"
        >
          <div className="t-micro mb-1.5 flex justify-between text-fg-muted">
            <span>{localized(job.stage, locale)}</span>
            <span className="tabular-nums" data-research-pct>{job.progress}%</span>
          </div>
          <Bar ratio={job.progress / 100} />
          <p className="t-micro mt-1.5 text-fg-faint">
            {t("goals.research.persistent")}
          </p>
        </div>
      )}
      {groups.map(({ kind, key, tone }) => {
        const facets = cached.facets.filter((f) => f.kind === kind);
        if (!facets.length) return null;
        return (
          <section
            key={kind}
            className="rounded-md p-3"
            style={{ background: `var(--color-${tone}-100)` }}
          >
            <h3
              className="t-meta font-bold"
              style={{ color: `var(--color-${tone}-700)` }}
            >
              {t(key)}
              <span className="t-micro ms-2 font-semibold opacity-70 tabular-nums">
                {facets.length}
              </span>
            </h3>
            <ul className="mt-2 flex flex-col gap-2">
              {facets.map((facet, index) => (
                <li key={index} className="flex gap-2" data-facet={facet.kind}>
                  <span
                    aria-hidden
                    className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: `var(--color-${tone}-700)` }}
                  />
                  <div className="min-w-0">
                    <div className="t-meta text-fg">
                      <span
                        className="t-mono me-1.5 rounded-[3px] px-1 py-[1px]"
                        style={{
                          background: "color-mix(in srgb, var(--card) 55%, transparent)",
                          color: `var(--color-${tone}-700)`,
                        }}
                      >
                        {facet.category}
                      </span>
                      {facet.origin === "ai_live" && (
                        <span className="chip chip-neutral t-micro me-1.5"
                              data-ai-live-tag
                              title={t("goals.research.aiLiveWhy")}>
                          {t("goals.research.aiLiveTag")}
                        </span>
                      )}
                      {/* A（2026-08-02）：市场证据加权的重点项加粗 + 下划线 */}
                      {facet.priority === "core" ? (
                        <span
                          data-core-facet
                          className="font-bold"
                          style={{
                            textDecorationLine: "underline",
                            textDecorationColor: "var(--accent)",
                            textDecorationThickness: "2px",
                            textUnderlineOffset: "3px",
                          }}
                        >
                          {localized(facet.description, locale)}
                        </span>
                      ) : (
                        localized(facet.description, locale)
                      )}
                    </div>
                    {facet.market_note && (
                      <div className="ai-note t-micro mt-1 text-fg-muted" data-market-note>
                        {/* 现场流水线的证据来自实时采集，标注与编制期区分 */}
                        {t(facet.origin === "ai_live"
                          ? "goals.decomp.marketNoteLive"
                          : "goals.decomp.marketNote")}：
                        {localized(facet.market_note, locale)}
                      </div>
                    )}
                    {facet.evidence_sources.length > 0 && (
                      <div className="t-micro mt-1 min-w-0 text-fg-muted">
                        {/* 2026-08-04 用户报障：接地跳转 URL 长达数百字符，
                            整段直出会溢出卡片。改为紧凑药丸——标签是
                            「公司 · 岗位」，URL 收进 href 不上屏 */}
                        <span className="me-1">{t("goals.decomp.evidence")}:</span>
                        <span className="inline-flex max-w-full flex-wrap gap-1.5 align-top"
                              data-evidence-sources>
                          {facet.evidence_sources.map((e, i) => {
                            const { label, url } = evidenceSourceParts(
                              localized(e, locale));
                            return url ? (
                              <a key={i} href={url} target="_blank" rel="noreferrer"
                                 data-evidence-source-link
                                 className="pressable max-w-full truncate rounded-sm border border-line px-1.5 py-0.5 text-fg-muted underline-offset-2 hover:text-fg hover:underline">
                                {label} ↗
                              </a>
                            ) : (
                              <span key={i}
                                    className="max-w-full break-words rounded-sm border border-line px-1.5 py-0.5">
                                {label}
                              </span>
                            );
                          })}
                        </span>
                        {/* 审计黄-12：接地阅读回退产出的取证 URL 是搜索
                            工具的跳转域，不是公司直链——如实注明来历 */}
                        {facet.evidence_sources.some((e) =>
                          /vertexaisearch/i.test(
                            (e.zh_Hans ?? "") + (e.en ?? ""))) && (
                          <span className="ms-1 text-fg-faint">
                            {t("goals.research.redirectNote")}
                          </span>
                        )}
                      </div>
                    )}
                    {facet.evidence_refs.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1.5" data-evidence-refs>
                        {facet.evidence_refs.map((refId) => {
                          const entry = EVIDENCE_BY_ID.get(refId);
                          if (!entry) return null;
                          return (
                            <a
                              key={refId}
                              href={entry.official_url}
                              target="_blank"
                              rel="noreferrer"
                              data-evidence-ref={refId}
                              className="pressable t-micro rounded-sm border border-line px-1.5 py-0.5 text-fg-muted hover:text-fg"
                              title={entry.note_zh}
                            >
                              {pickLang(locale, entry.name_zh, entry.name_en)}
                              <span className="ms-1 opacity-70">
                                {t(`goals.tier.${entry.tier}` as Parameters<typeof t>[0])}
                              </span>
                            </a>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        );
      })}
      {/* 国际生准备列（用户增补 B，2026-08-02）：Pack 注入后追加第四区。
          内容全部派生自确定性求值信封，待政策复核徽章 + 非法律建议免责声明
          是队友 Pack frontend boundary 的硬要求。 */}
      {cached.intl_facets.length > 0 && (
        <section
          className="rounded-md p-3"
          data-intl-column
          style={{ background: "var(--color-terra-100)" }}
        >
          <h3 className="t-meta font-bold" style={{ color: "var(--color-terra-700)" }}>
            {t("goals.decomp.intl")}
            <span className="t-micro ms-2 font-semibold opacity-70 tabular-nums">
              {cached.intl_facets.length}
            </span>
            {cached.intl_review_required && (
              <span
                className="t-micro ms-2 rounded-sm px-1.5 py-0.5 font-medium"
                data-intl-review-badge
                style={{ border: "1px solid var(--color-terra-700)" }}
              >
                {t("goals.intl.reviewRequired")}
              </span>
            )}
          </h3>
          {/* fix/intl-chain（2026-08-02 审计 #5）：按信封来源分组渲染——
              准备/约束（eligibility_status）与待补信息（credential）分小节，
              替代此前把三类内容混成一列的扁平列表 */}
          {([
            ["eligibility_status", "goals.intl.groupPrep"],
            ["credential", "goals.intl.groupMissing"],
          ] as const).map(([category, labelKey]) => {
            const group = cached.intl_facets.filter(
              (facet) => facet.category === category,
            );
            if (group.length === 0) return null;
            return (
              <div key={category} className="mt-2" data-intl-group={category}>
                <div className="t-micro font-semibold text-fg-muted">
                  {t(labelKey)}
                </div>
                <ul className="mt-1 flex flex-col gap-2">
                  {group.map((facet, index) => (
                    <li key={index} className="flex gap-2" data-facet="intl">
                      <span
                        aria-hidden
                        className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full"
                        style={{ background: "var(--color-terra-700)" }}
                      />
                      <div className="t-meta min-w-0 text-fg">
                        {localized(facet.description, locale)}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
          <p className="t-micro mt-2 text-fg-muted" data-intl-disclaimer>
            {t("goals.intl.disclaimer")}
            {cached.intl_pack_version &&
              ` · Pack v${cached.intl_pack_version}`}
          </p>
        </section>
      )}
    </div>
  );
}

export default function GoalsPage() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const goals = useResource(() => api.goals(studentId), [studentId]);
  const [decomps, setDecomps] = useState<Record<string, GoalDecomposition | null>>({});
  const gapMap = useResource(() => api.gapMap(studentId), [studentId]);
  // 国际生引导要读档案状态（学期/年级不再让学生自述——2026-08-03 用户
  // 裁定撤除，全局以教务侧为准）
  const profile = useResource(() => api.profile(studentId), [studentId]);

  const [mode, setMode] = useState<Mode | null>(null);
  const [targetName, setTargetName] = useState("");
  const [role, setRole] = useState<"primary" | "candidate">("primary");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const primary = goals.data?.find((g) => g.role === "primary");
  const candidate = goals.data?.find((g) => g.role === "candidate");
  const chosen = MODES.find((m) => m.value === mode);
  const canSave =
    Boolean(mode) && (mode === "exploration" || targetName.trim().length > 0);

  async function save() {
    if (!chosen) return;
    setSaving(true);
    setSaveError(null);
    try {
      const goal: Goal = {
        goal_id: `GOAL-${studentId}-${role}`,
        student_id: studentId,
        role,
        development_mode: chosen.value,
        target_type: chosen.targetType,
        target_name: targetName.trim() || t("goals.mode.exploration"),
        horizon: "long_term",
        confidence: 0.5,
        status: role === "primary" ? "active" : "candidate",
        alternatives: [],
        created_at: new Date().toISOString(),
        last_reviewed: null,
      };
      await api.setGoal(studentId, goal);
      setTargetName("");
      setMode(null);
      goals.reload();
      gapMap.reload();
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <PageHeader titleKey="goals.title" leadKey="goals.lead">
        {/* R10-7：目标设定之后 AI 才有规划依据——「开始规划」从开通页搬来 */}
        <Link
          href="/planner"
          data-start-planning
          className="pressable btn btn-primary t-body font-medium"
        >
          {t("goals.startPlanning")}
        </Link>
      </PageHeader>

      {/* ── 国际生引导（单入口在档案页）。学期选择器已撤（2026-08-03
          用户裁定：学期/年级以教务侧为准，不让学生自述）── */}
      {profile.data && (
        <Card className="mb-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            {!profile.data.intl_context && (
              <Link
                href="/profile"
                data-intl-hint
                className="t-meta text-fg-muted underline underline-offset-2 hover:text-fg"
              >
                {t("goals.intlHint")}
              </Link>
            )}
            {profile.data.intl_context && (
              <span className="chip chip-mist t-micro" data-intl-on>
                {t("goals.intlOn")}
              </span>
            )}
          </div>
        </Card>
      )}

      {/* ── 第一步：方向 ────────────────────────────────────── */}
      <Card className="mb-5">
        <SectionTitle>{t("goals.step1")}</SectionTitle>
        <p className="t-meta mb-4 max-w-[62ch] text-fg-muted">
          {t("goals.step1.lead")}
        </p>
        <ul className="flex flex-wrap gap-2" data-mode-picker>
          {MODES.map((m) => {
            const active = mode === m.value;
            return (
              <li key={m.value}>
                <button
                  type="button"
                  data-mode={m.value}
                  aria-pressed={active}
                  onClick={() => setMode(active ? null : m.value)}
                  className="pressable t-body rounded-md border px-3.5 py-2"
                  style={{
                    borderColor: active ? "var(--accent)" : "var(--line-strong)",
                    background: active ? "var(--accent-deep)" : "transparent",
                    color: active ? "var(--accent-fg)" : "var(--fg-muted)",
                    fontWeight: active ? 600 : 450,
                  }}
                >
                  {t(m.labelKey)}
                </button>
              </li>
            );
          })}
        </ul>

        {/* ── 第二步：在这个方向下写下终点 ─────────────────── */}
        {mode && (
          <div className="mt-6" data-goal-form>
            <SectionTitle>{t("goals.step2")}</SectionTitle>
            <p className="t-meta mb-3 max-w-[62ch] text-fg-muted">
              {t(MODE_HINT[mode])}
            </p>
            {mode !== "exploration" && (
              <input
                type="text"
                data-goal-target
                value={targetName}
                maxLength={200}
                onChange={(e) => setTargetName(e.target.value)}
                placeholder={t(MODE_HINT[mode])}
                className="field t-body w-full max-w-[52ch] placeholder:text-fg-faint"
              />
            )}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <div className="inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5">
                {(["primary", "candidate"] as const).map((r) => (
                  <button
                    key={r}
                    type="button"
                    data-goal-role-option={r}
                    aria-pressed={role === r}
                    onClick={() => setRole(r)}
                    className="pressable t-meta rounded-sm px-3 py-1.5"
                    style={{
                      background: role === r ? "var(--accent-deep)" : "transparent",
                      color: role === r ? "var(--accent-fg)" : "var(--fg-muted)",
                      fontWeight: role === r ? 600 : 500,
                    }}
                  >
                    {t(r === "primary" ? "goals.primary" : "goals.candidate")}
                  </button>
                ))}
              </div>
              <button
                type="button"
                data-goal-save
                disabled={!canSave || saving}
                onClick={save}
                className="pressable btn btn-primary t-body font-medium disabled:opacity-40"
              >
                {t("goals.save")}
              </button>
              {saveError && (
                <span className="t-mono text-fg-faint" data-goal-save-error>
                  {saveError}
                </span>
              )}
            </div>
          </div>
        )}
      </Card>

      {goals.loading && <Loading />}
      {goals.error && <Failure error={goals.error} onRetry={goals.reload} />}

      {/* 主/副目标推荐配比（2026-08-02 用户需求）：两个目标都在时才显示。
          写入档案 candidate_goal_share，推荐（For You 配额 + 选修加权）即时生效 */}
      {primary && candidate && profile.data && (
        <Card className="mb-5" data-goal-split-card>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <SectionTitle>{t("goals.split.title")}</SectionTitle>
              <p className="t-meta text-fg-muted">{t("goals.split.hint")}</p>
            </div>
            <select
              aria-label={t("goals.split.title")}
              data-goal-split
              className="field t-meta max-w-[220px]"
              value={String(Math.round((profile.data.candidate_goal_share ?? 0.2) * 100))}
              onChange={async (e) => {
                await api.selfEditProfile(studentId, {
                  candidate_goal_share: Number(e.target.value) / 100,
                });
                profile.reload();
              }}
            >
              {[10, 20, 30, 40, 50].map((pct) => (
                <option key={pct} value={String(pct)}>
                  {t("goals.split.primary")} {100 - pct}% / {t("goals.split.candidate")} {pct}%
                </option>
              ))}
            </select>
          </div>
        </Card>
      )}

      {/* 主/候选目标固定两列各半，与上下模块整宽对齐（用户裁定 2026-08-01） */}
      <div className="grid gap-5 lg:grid-cols-2">
        {[
          { goal: primary, roleKey: "goals.primary" as MessageKey },
          { goal: candidate, roleKey: "goals.candidate" as MessageKey },
        ].map(({ goal, roleKey }) => (
          <Card key={roleKey} as="article">
            <div className="t-micro text-fg-faint">{t(roleKey)}</div>
            {goal ? (
              <div data-goal={goal.goal_id} data-goal-role={goal.role}>
                <div
                  className="chip chip-peach t-micro mt-2 inline-flex"
                  data-goal-mode={goal.development_mode}
                >
                  {t(`goals.mode.${goal.development_mode}` as MessageKey)}
                </div>
                <div className="t-title mt-2 text-fg">{goal.target_name}</div>
                <div className="t-meta mt-1 text-fg-muted">
                  {goal.target_type} · {t("goals.horizon")}: {goal.horizon}
                </div>
                {/* 2026-08-02 用户裁定：信心条撤下——goal.confidence 是创建时
                    写死的 0.5/种子常数，没有任何学生输入口与计算依据，
                    显示一个没有出处的百分比是误导（宁缺毋假） */}
                {goal.alternatives.length > 0 && (
                  <ul className="mt-4 flex flex-wrap gap-2">
                    {goal.alternatives.map((alt) => (
                      <li
                        key={alt}
                        className="t-meta rounded-sm border border-line px-2 py-0.5 text-fg-muted"
                      >
                        {alt}
                      </li>
                    ))}
                  </ul>
                )}

                <GoalDecompositionPanel
                  studentId={studentId}
                  goalId={goal.goal_id}
                  cached={decomps[goal.goal_id]}
                  onLoaded={(d) =>
                    setDecomps((prev) => ({ ...prev, [goal.goal_id]: d }))
                  }
                />
              </div>
            ) : (
              <div className="mt-2">
                <Empty />
              </div>
            )}
          </Card>
        ))}
      </div>

      {/* K（2026-07-31）：共享要求与分叉点都按目标拆解的三层归类呈现。
          「共同要求」标题已经说明两条路都需要——每条不再重复这句话。 */}
      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <SectionTitle>{t("goals.shared")}</SectionTitle>
          {gapMap.loading && <Loading />}
          {gapMap.error && <Failure error={gapMap.error} />}
          {gapMap.data?.shared_gaps.length === 0 && <Empty />}
          {LAYERS.map((layer) => {
            // R4-H：同一类别的多条共享缺口在展示层合并成一行，计数相加——
            // 数据里"学位要求的课程修读"和"Pack 的课程修读"是两条，但对
            // 学生来说都是"课程修读"，列两行只会让人以为写重了。
            const merged = new Map<string, { primary: number; candidate: number }>();
            for (const shared of gapMap.data?.shared_gaps ?? []) {
              if (layerOf(shared.category) !== layer) continue;
              const entry = merged.get(shared.category) ?? { primary: 0, candidate: 0 };
              entry.primary += shared.requirement_ids_primary.length;
              entry.candidate += shared.requirement_ids_candidate.length;
              merged.set(shared.category, entry);
            }
            if (!merged.size) return null;
            return (
              <div key={layer} className="mb-4 last:mb-0" data-shared-layer={layer}>
                <div className="t-micro mb-1.5 font-medium text-fg-muted">
                  {t(LAYER_KEY[layer])}
                </div>
                <ul className="flex flex-col gap-2">
                  {[...merged.entries()].map(([category, counts]) => (
                    <li
                      key={category}
                      data-shared-gap={category}
                      className="flex items-center justify-between rounded-md border border-line bg-bg-sunk px-3 py-2"
                    >
                      <span className="t-body text-fg">
                        {categoryLabel(category, locale)}
                      </span>
                      <span
                        className="t-mono text-fg-faint"
                        title={t("goals.shared.countHint")}
                      >
                        {counts.primary} ↔ {counts.candidate}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </Card>

        <Card>
          <SectionTitle>{t("goals.fork")}</SectionTitle>
          <p className="t-meta mb-3 max-w-[52ch] text-fg-faint">
            {t("goals.fork.explain")}
          </p>
          {gapMap.data?.divergence_points.length === 0 && (
            <Empty messageKey="gaps.forkPending" />
          )}
          {gapMap.data?.divergence_points.map((fork, index) => {
            const sides = [
              { ids: fork.primary_only_requirement_ids, key: "goals.fork.primaryOnly" as const },
              { ids: fork.candidate_only_requirement_ids, key: "goals.fork.candidateOnly" as const },
            ];
            return (
              <div
                key={index}
                data-divergence-point={fork.at_term ?? String(index)}
                className="hatch-unknown mb-3 rounded-md border p-3 last:mb-0"
                style={{ borderColor: "var(--hatch)" }}
              >
                <div className="t-micro" style={{ color: "var(--hatch-ink)" }}>
                  {fork.at_term ?? "—"}
                </div>
                {sides.map(({ ids, key }) => {
                  if (!ids.length) return null;
                  const cats = ids.map(categoryFromRequirementId);
                  return (
                    <div key={key} className="mt-2">
                      <div className="t-micro text-fg-faint">{t(key)}</div>
                      {LAYERS.map((layer) => {
                        const inLayer = cats.filter((c) => layerOf(c) === layer);
                        if (!inLayer.length) return null;
                        return (
                          <div key={layer} className="mt-1 flex flex-wrap items-center gap-1.5">
                            <span className="t-micro text-fg-muted">
                              {t(LAYER_KEY[layer])}{locale.startsWith("zh") ? "：" : ": "}
                            </span>
                            {inLayer.map((c) => (
                              <span
                                key={c}
                                className="t-meta rounded-sm border border-line px-2 py-0.5 text-fg"
                              >
                                {categoryLabel(c, locale)}
                              </span>
                            ))}
                          </div>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            );
          })}
        </Card>
      </div>
    </>
  );
}
