"use client";

import { useEffect, useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n, localized, pickLang } from "@/i18n";
import { api, institution, type ModerationDecision } from "@/lib/api";
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
} from "@/components/ui";

/**
 * Career Center Console（D5 校方端）。
 *
 * **这一页存在的价值一半在于它看不到什么。** D5 的隔离验证要求：
 * 以 Career Center 身份登录，确认看不到任何 wellbeing 事件、
 * Reflection 原文、个体日历。所以页面底部有一块「越权探针」——
 * 它主动去请求那些**本该被拒**的端点，并把状态码显示出来。
 *
 * 把隔离做成一块看得见的面板，而不是一句承诺：演示时它是证据，
 * 出问题时它是第一个变红的地方。
 */
/** 源注册表分组顺序（业务重要度，不是字母序） */
const SOURCE_CATEGORY_ORDER = [
  "central_calendar",
  "career_internship",
  "entrepreneurship",
  "research_urop",
  "exchange_cross_uni",
  "school_academic",
  "club_alumni",
  "admin_department",
  "policy",
  "education_system",
] as const;

const FORBIDDEN_PROBES = [
  { id: "profile", path: "/v1/students/STU-A/profile" },
  { id: "notes", path: "/v1/students/STU-A/notes" },
  { id: "availability", path: "/v1/students/STU-A/availability" },
  { id: "wellbeing", path: "/v1/students/STU-A/wellbeing/signals" },
  { id: "outreach-queue", path: "/v1/wellbeing/outreach-queue" },
] as const;

export default function ConsolePage() {
  const { t, locale } = useI18n();
  const { role } = useRole();

  const sources = useResource(() => institution.sources(), [role]);
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [refreshErr, setRefreshErr] = useState<string | null>(null);
  // 一键巡检（2026-08-02 用户需求 C）：服务端后台任务 + 2s 轮询，切页不中断
  type SweepJob = Awaited<ReturnType<typeof institution.sourcesSweepStatus>>;
  const [sweep, setSweep] = useState<SweepJob | null>(null);
  useEffect(() => {
    let stop = false;
    institution.sourcesSweepStatus()
      .then((job) => { if (!stop) setSweep(job); })
      .catch(() => {});   // 404 = 还没跑过，静默
    return () => { stop = true; };
  }, [role]);
  useEffect(() => {
    if (sweep?.state !== "running") return;
    const timer = setInterval(async () => {
      try {
        const job = await institution.sourcesSweepStatus();
        setSweep(job);
        if (job.state !== "running") sources.reload();
      } catch { /* 保持上一次状态 */ }
    }, 2000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sweep?.state]);
  async function startSweep() {
    setRefreshErr(null);
    try {
      setSweep(await institution.startSourcesSweep());
    } catch (err) {
      setRefreshErr(`refresh-all: ${(err as Error).message}`);
    }
  }
  async function refreshOne(sourceId: string) {
    setRefreshing(sourceId);
    setRefreshErr(null);
    try {
      await institution.refreshSource(sourceId);
      sources.reload();
    } catch (err) {
      // 审查 #10：403/409/网络错不许看起来像成功
      setRefreshErr(`${sourceId}: ${(err as Error).message}`);
    } finally {
      setRefreshing(null);
    }
  }
  // fix/intl-chain（审计 B）：源 → 在架条目数，只数**现行在架**
  // （codex #7：含过期/下架会虚报运营指标），按 source_id 聚合。
  const catalog = useResource(() => api.catalog(1000, false), [role]);
  const onShelfBySource = new Map<string, number>();
  for (const o of catalog.data ?? []) {
    if (o.source_id) {
      onShelfBySource.set(o.source_id, (onShelfBySource.get(o.source_id) ?? 0) + 1);
    }
  }
  // 审查 #3：Source Health 八项指标面板不可随注册表卡消失（F22 零删减）
  const health = useResource(() => institution.sourceHealth(), [role]);
  const coverage = useResource(() => institution.resourceCoverage(), [role]);
  const quality = useResource(() => institution.eventQuality(), [role]);
  const probes = useResource(
    () =>
      Promise.all(
        FORBIDDEN_PROBES.map(async (probe) => {
          const response = await fetch(`/api${probe.path}`, {
            headers: { "X-CampusPath-Role": role },
          });
          return { id: probe.id, path: probe.path, status: response.status };
        }),
      ),
    [role],
  );

  const needsCurator = role !== "curator" && role !== "connector_admin" && role !== "career_center_admin";

  return (
    <>
      <PageHeader titleKey="console.title" leadKey="console.lead">
        <span
          className="t-micro rounded-full px-2.5 py-1"
          data-active-role={role}
          style={{
            border: "1px solid var(--accent)",
            color: "var(--accent-deep)",
          }}
        >
          {t("console.actingAs")}: {role}
        </span>
      </PageHeader>

      {needsCurator && (
        <Card className="mb-5">
          <p className="t-body text-fg-muted" data-role-hint>
            {t("console.needCurator")}
          </p>
        </Card>
      )}

      {/* ── 官方信息源注册表（C，2026-08-02）：真实/mock 如实标注，
             刷新按钮触发真实抓取 + 变更检测（不再只是 reload 假按钮） ── */}
      <Card className="mb-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <SectionTitle>{t("console.sources")}</SectionTitle>
          {/* 一键刷新（2026-08-02 用户需求 C）：模块右上角 */}
          <div className="flex items-center gap-2">
            {sweep?.state === "running" && (
              <span className="t-meta tabular-nums text-fg-muted" data-sweep-progress>
                {t("console.sweep.running")} {sweep.done}/{sweep.total}
              </span>
            )}
            {sweep && sweep.state !== "running" && (
              <span className="t-micro text-fg-faint" data-sweep-summary>
                {t("console.sweep.last")}: Δ{sweep.changed} · {t("console.sweep.errors")} {sweep.errors}
              </span>
            )}
            <button
              type="button"
              data-sources-sweep
              disabled={sweep?.state === "running"}
              onClick={startSweep}
              className="pressable btn btn-secondary t-meta disabled:opacity-40"
            >
              ↻ {t("console.sweep.start")}
            </button>
          </div>
        </div>
        <p className="t-meta mb-3 text-fg-faint">{t("console.sources.explain")}</p>
        {refreshErr && (
          <p className="t-meta mb-2" data-refresh-error
             style={{ color: "var(--color-clay-600)" }}>{refreshErr}</p>
        )}
        {sources.loading && <Loading />}
        {sources.error && <Failure error={sources.error} onRetry={sources.reload} />}
        {sources.data?.length === 0 && <Empty />}
        <div className="flex flex-col gap-4">
          {SOURCE_CATEGORY_ORDER.filter(
            (cat) => (sources.data ?? []).some((s) => s.category === cat),
          ).map((cat) => (
            <div key={cat} data-source-group={cat}>
              <p className="t-meta mb-2 font-semibold text-fg-muted">
                {t(`console.srccat.${cat}` as Parameters<typeof t>[0])}
                <span className="t-mono ms-2 text-fg-faint">
                  {(sources.data ?? []).filter((s) => s.category === cat).length}
                </span>
              </p>
              <div className="flex flex-col gap-2">
                {(sources.data ?? [])
                  .filter((s) => s.category === cat)
                  .map((source) => (
                    <div
                      key={source.source_id}
                      data-registered-source={source.source_id}
                      className="rounded-md border border-line bg-bg-sunk p-3"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="flex min-w-0 items-center gap-2">
                          {/* 状态灯（2026-08-02 用户需求 C）：绿=最近抓取 ok，
                              红=不可达，灰=未抓取过/mock 源 */}
                          <span
                            aria-hidden
                            data-src-light={source.last_fetch_status}
                            className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                            style={{
                              background:
                                source.last_fetch_status === "ok"
                                  ? "var(--color-moss-600)"
                                  : source.last_fetch_status === "unreachable"
                                    ? "var(--color-clay-600)"
                                    : "var(--color-bark-300)",
                            }}
                          />
                          <span className="t-section text-fg">
                            {pickLang(locale, source.name.zh_Hans, source.name.en)}
                          </span>
                          <span className="t-mono ms-2 text-fg-faint">
                            {source.priority.toUpperCase()}
                          </span>
                        </span>
                        <span className="flex flex-wrap items-center gap-2">
                          {/* 真实/合成如实标注（用户裁定 D） */}
                          {source.is_real_fetch ? (
                            <span className="chip chip-sage t-micro" data-src-real>
                              {t("console.src.real")}
                            </span>
                          ) : (
                            <span className="chip chip-neutral t-micro" data-src-mock>
                              {t("console.src.mock")}
                            </span>
                          )}
                          {source.kind === "policy_source" ? (
                            <span className="chip chip-blossom t-micro" data-src-policy>
                              {t("console.src.policyBadge")}
                            </span>
                          ) : (
                            <span className="chip chip-mist t-micro">
                              {source.extraction_depth === "full_chain"
                                ? t("console.src.fullchain")
                                : t("console.src.monitor")}
                            </span>
                          )}
                          {source.last_fetch_status !== "unknown" && (
                            <span
                              className="t-meta rounded-sm px-2 py-0.5"
                              style={{
                                border: `1px solid ${
                                  source.last_fetch_status === "ok"
                                    ? "var(--color-moss-500)"
                                    : "var(--color-clay-500)"
                                }`,
                                color:
                                  source.last_fetch_status === "ok"
                                    ? "var(--color-moss-600)"
                                    : "var(--color-clay-600)",
                              }}
                            >
                              {source.last_fetch_status}
                            </span>
                          )}
                          {source.is_real_fetch && (
                            <button
                              type="button"
                              data-source-refresh={source.source_id}
                              title={t("console.source.refresh.hint")}
                              disabled={refreshing === source.source_id}
                              onClick={() => refreshOne(source.source_id)}
                              className="pressable btn btn-ghost t-micro"
                            >
                              {refreshing === source.source_id
                                ? t("console.src.refreshing")
                                : `↻ ${t("console.source.refresh")}`}
                            </button>
                          )}
                        </span>
                      </div>
                      <div className="t-micro mt-2 flex flex-wrap gap-4 text-fg-faint">
                        <span className="t-mono">{source.source_id}</span>
                        <span>
                          {t("console.src.lastChecked")}:{" "}
                          {source.last_checked_at
                            ? new Date(source.last_checked_at).toLocaleString()
                            : "—"}
                        </span>
                        <span>
                          {t("console.src.lastChanged")}:{" "}
                          {source.last_changed_at
                            ? new Date(source.last_changed_at).toLocaleString()
                            : "—"}
                        </span>
                        {/* fix/intl-chain（审计 B）：抽取与上架的可观测证据 */}
                        {source.last_extracted_count !== null &&
                          source.last_extracted_count !== undefined && (
                          <span data-src-extracted>
                            {t("console.src.extracted")}:{" "}
                            <span className="tabular-nums">
                              {source.last_extracted_count}
                            </span>
                          </span>
                        )}
                        {(onShelfBySource.get(source.source_id) ?? 0) > 0 && (
                          <span data-src-onshelf>
                            {t("console.src.onShelf")}:{" "}
                            <span className="tabular-nums">
                              {onShelfBySource.get(source.source_id)}
                            </span>
                          </span>
                        )}
                      </div>
                      {/* 官方链接（审计 B：此前整卡没有任何可点的源地址） */}
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        data-src-url
                        className="t-micro mt-1 inline-block break-all underline underline-offset-2 text-fg-muted"
                      >
                        {source.url}
                      </a>
                    </div>
                  ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* ── Source Health 八项（F22）：审查 #3 还原——注册表管"有哪些源"，
             这里管"解析质量/新鲜度/断链率"的运维口径（mock 探针 + 六连接器） ── */}
      <Card className="mb-5">
        <SectionTitle>{t("console.sourceHealth")}</SectionTitle>
        {health.loading && <Loading />}
        {health.error && <Failure error={health.error} onRetry={health.reload} />}
        <div className="flex flex-col gap-2">
          {health.data?.map((source) => (
            <div key={source.source_id}
                 data-source-health={source.source_id}
                 className="t-micro flex flex-wrap items-center gap-x-5 gap-y-1 rounded-md border border-line bg-bg-sunk px-3 py-2 text-fg-muted">
              <span className="t-meta text-fg">
                {t(`source.${source.source_id}` as Parameters<typeof t>[0])}
              </span>
              <span style={{ color: source.fetch_auth_status === "ok"
                  ? "var(--color-moss-600)" : "var(--color-clay-600)" }}>
                {source.fetch_auth_status}
              </span>
              <span>{t("console.parseRate")}: {Math.round(source.parse_success_rate * 100)}%</span>
              <span>{t("console.freshness")}: {source.freshness_hours?.toFixed(1) ?? "—"}h</span>
              <span>{t("console.brokenLinks")}: {Math.round(source.broken_link_rate * 100)}%</span>
              <span>{t("console.schemaCoverage")}: {Math.round(source.schema_coverage_rate * 100)}%</span>
            </div>
          ))}
        </div>
      </Card>

      {/* ── 匿名聚合：只出总量，不可下钻 ─────────────────── */}
      <div className="mb-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <SectionTitle>{t("console.coverage")}</SectionTitle>
          <p className="t-meta mb-3 text-fg-faint">{t("console.coverage.explain")}</p>
          {coverage.loading && <Loading />}
          {coverage.error && <Failure error={coverage.error} />}
          {coverage.data?.length === 0 && <Empty />}
          <ul className="flex flex-col gap-2">
            {coverage.data?.map((row) => (
              <li
                key={row.aggregate_id}
                data-coverage={row.aggregate_id}
                className="t-meta flex justify-between text-fg-muted"
              >
                <span>
                  {row.period} · {row.scope}
                </span>
                <span className="tabular-nums">
                  n={row.cell_n} ·{" "}
                  {row.gap_coverage_rate === null
                    ? "—"
                    : `${Math.round(row.gap_coverage_rate * 100)}%`}
                </span>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <SectionTitle>{t("console.quality")}</SectionTitle>
          {quality.loading && <Loading />}
          {quality.error && <Failure error={quality.error} />}
          {quality.data?.length === 0 && <Empty />}
          <ul className="flex flex-col gap-2">
            {quality.data?.slice(0, 8).map((row) => (
              <li
                key={row.aggregate_id}
                data-quality={row.aggregate_id}
                className="t-meta flex justify-between text-fg-muted"
              >
                <span>{row.series_id ?? row.occurrence_id}</span>
                <span className="tabular-nums">n={row.verified_n}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>

      {/* ── 隔离探针：主动去撞墙，把状态码摆出来 ─────────── */}
      <Card>
        <SectionTitle>{t("console.isolation")}</SectionTitle>
        <p className="t-meta mb-4 max-w-[64ch] text-fg-muted">
          {t("console.isolation.explain")}
        </p>
        {probes.loading && <Loading />}
        <ul className="flex flex-col gap-2" data-isolation-probes>
          {probes.data?.map((probe) => {
            const blocked = probe.status === 403 || probe.status === 401;
            return (
              <li
                key={probe.id}
                data-probe={probe.id}
                data-probe-status={probe.status}
                data-probe-blocked={String(blocked)}
                className="flex items-center justify-between gap-3 rounded-md border p-3"
                style={{
                  borderColor: blocked
                    ? "var(--color-moss-500)"
                    : "var(--color-clay-500)",
                  background: blocked
                    ? "var(--color-moss-100)"
                    : "var(--color-clay-100)",
                }}
              >
                <code className="t-mono" style={{ color: "var(--fg)" }}>
                  {probe.path}
                </code>
                <span
                  className="t-meta font-medium"
                  style={{
                    color: blocked
                      ? "var(--color-moss-600)"
                      : "var(--color-clay-600)",
                  }}
                >
                  {probe.status} · {t(blocked ? "console.blocked" : "console.leaked")}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
    </>
  );
}
