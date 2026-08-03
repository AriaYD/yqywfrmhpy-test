"use client";

import { useEffect, useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n, localized } from "@/i18n";
import { institution, type Schemas } from "@/lib/api";
import {
  Bar, Card, Empty, Loading, Metric, PageHeader, SectionTitle, Segmented,
} from "@/components/ui";

/**
 * 活动反馈可视化数据报告（D 批，2026-08-02 用户裁定）。
 *
 * **仅 career_center_admin**——服务端 RBAC 是真正的栅栏（其他角色 403，
 * 有回归测试钉住），这页只是它的展示面。统计全部确定性（阈值抑制照旧）；
 * 唯一的模型产物是叙事段，输入只有聚合 JSON。
 * 「立即生成」起服务端后台任务：切页/关页不中断，回来轮询接上进度。
 */
type Period = "weekly" | "monthly" | "term" | "year";
type ReportJob = Schemas["QualityReportJob"];
type GroupRow = Schemas["ReportGroupRow"];

const PERIODS: Period[] = ["weekly", "monthly", "term", "year"];

function GroupTable({ titleKey, rows, labelFromKey }: {
  titleKey: Parameters<ReturnType<typeof useI18n>["t"]>[0];
  rows: readonly GroupRow[];
  labelFromKey?: (key: string) => string;
}) {
  const { t, locale } = useI18n();
  if (!rows.length) return null;
  return (
    <div className="mt-4" data-report-table={titleKey}>
      <p className="t-meta mb-2 font-semibold text-fg">{t(titleKey)}</p>
      <div className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.key} className="rounded-md border border-line bg-bg-sunk p-2.5"
               data-report-row={row.key}>
            <div className="t-meta flex flex-wrap items-baseline justify-between gap-2">
              <span className="min-w-0 text-fg">
                {row.label ? localized(row.label, locale)
                  : labelFromKey ? labelFromKey(row.key) : row.key}
              </span>
              <span className="t-micro flex flex-wrap gap-3 text-fg-muted">
                <span>{t("reports.col.activities")}: {row.activities_n}</span>
                <span>{t("reports.col.feedback")}: {row.feedback_n}</span>
                <span>{t("reports.col.verified")}: {row.verified_n}</span>
                <span>{t("reports.col.attend")}: {row.attend_count}</span>
                {row.favorable_rate != null && (
                  <span className="font-semibold" style={{ color: "var(--accent-deep)" }}>
                    {t("reports.col.favorable")}: {Math.round(row.favorable_rate * 100)}%
                  </span>
                )}
              </span>
            </div>
            {row.avg_overall != null ? (
              <div className="mt-1.5 flex items-center gap-2">
                <div className="min-w-0 flex-1"><Bar ratio={row.avg_overall / 5} /></div>
                <span className="t-micro tabular-nums text-fg-muted">
                  {row.avg_overall.toFixed(1)}/5
                </span>
              </div>
            ) : (
              <span className="hatch-unknown t-micro mt-1.5 inline-block rounded-sm px-1.5 py-0.5">
                {t("console.insufficient")}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function QualityReportsPage() {
  const { t, locale } = useI18n();
  const { role } = useRole();
  const [period, setPeriod] = useState<Period>("weekly");
  const [jobs, setJobs] = useState<Partial<Record<Period, ReportJob | null>>>({});
  const [startErr, setStartErr] = useState<string | null>(null);
  const job = jobs[period];
  const canSee = role === "career_center_admin";

  // 挂载/切分页：读该周期最近一次任务（404 = 还没生成过，合法空态）
  useEffect(() => {
    if (!canSee) return;
    let stop = false;
    institution.qualityReportStatus(period)
      .then((j) => { if (!stop) setJobs((prev) => ({ ...prev, [period]: j })); })
      .catch(() => { if (!stop) setJobs((prev) => ({ ...prev, [period]: null })); });
    return () => { stop = true; };
  }, [period, canSee]);
  // 运行中轮询（任务在服务端，切页/关页不中断）
  useEffect(() => {
    if (job?.state !== "running") return;
    const timer = setInterval(async () => {
      try {
        const next = await institution.qualityReportStatus(period);
        setJobs((prev) => ({ ...prev, [period]: next }));
      } catch { /* 下一轮再试 */ }
    }, 2000);
    return () => clearInterval(timer);
  }, [job?.state, period]);

  async function generate() {
    setStartErr(null);
    try {
      const started = await institution.startQualityReport(period);
      setJobs((prev) => ({ ...prev, [period]: started }));
    } catch (err) {
      setStartErr((err as Error).message);
    }
  }

  const report = job?.state === "done" ? job.report : null;
  return (
    <>
      <PageHeader titleKey="reports.title" leadKey="reports.lead">
        <span className="t-micro rounded-full px-2.5 py-1" data-active-role={role}
              style={{ border: "1px solid var(--accent)", color: "var(--accent-deep)" }}>
          {t("console.actingAs")}: {role}
        </span>
      </PageHeader>

      {!canSee ? (
        <Card><p className="t-body text-fg-muted" data-role-hint>
          {t("reports.adminOnly")}
        </p></Card>
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <Segmented
              ariaLabel={t("reports.title")}
              value={period}
              onChange={setPeriod}
              options={PERIODS.map((p) => ({
                value: p, label: t(`reports.period.${p}` as Parameters<typeof t>[0]),
              }))}
            />
            <span className="flex items-center gap-2">
              {startErr && (
                <span className="t-micro" style={{ color: "var(--color-clay-600)" }}>
                  {startErr}
                </span>
              )}
              <button type="button" data-report-generate
                      disabled={job?.state === "running"}
                      onClick={generate}
                      className="pressable btn btn-primary t-meta font-medium">
                {t("reports.generate")}
              </button>
            </span>
          </div>

          {job?.state === "running" && (
            <Card className="mb-5" data-report-progress>
              <div className="t-micro mb-1.5 flex justify-between text-fg-muted">
                <span>{localized(job.stage, locale)}</span>
                <span className="tabular-nums" data-report-pct>{job.progress}%</span>
              </div>
              <Bar ratio={job.progress / 100} />
              <p className="t-micro mt-1.5 text-fg-faint">{t("reports.persistent")}</p>
            </Card>
          )}
          {job?.state === "failed" && (
            <Card className="mb-5"><p className="t-meta" style={{ color: "var(--color-clay-600)" }}>
              {t("reports.failed")}: {job.error}
            </p></Card>
          )}
          {job === null && <Card className="mb-5"><Empty messageKey="reports.none" /></Card>}
          {job === undefined && <Loading />}

          {report && (
            <Card data-report={report.report_id}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <SectionTitle>
                  {t(`reports.period.${report.period}` as Parameters<typeof t>[0])}
                  {" · "}{report.window_start} → {report.window_end}
                </SectionTitle>
                <span className="t-micro text-fg-faint">
                  {t("reports.generatedAt")}: {new Date(report.generated_at).toLocaleString()}
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-8">
                <Metric label={t("reports.totalActivities")} value={report.activities_total} />
                <Metric label={t("reports.totalFeedback")} value={report.feedback_total} />
                <Metric label={t("reports.totalVerified")} value={report.verified_total} tone="good" />
                <Metric label={t("reports.totalAttend")} value={report.attend_total} />
              </div>

              {report.narrative && (
                <div className="ai-note mt-4" data-report-narrative>
                  <p className="t-micro mb-1 text-fg-muted">{t("reports.narrative")}</p>
                  <p className="t-meta whitespace-pre-wrap text-fg">
                    {localized(report.narrative, locale)}
                  </p>
                </div>
              )}

              <GroupTable titleKey="reports.byOrganizer" rows={report.by_organizer}
                labelFromKey={(k) => t(`square.orgcat.${k}` as Parameters<typeof t>[0])} />
              <GroupTable titleKey="reports.byType" rows={report.by_type} />
              <GroupTable titleKey="reports.bySchool" rows={report.by_school} />
              <GroupTable titleKey="reports.topActivities" rows={report.top_activities} />

              {report.coverage_gaps.length > 0 && (
                <div className="mt-4" data-report-gaps>
                  <p className="t-meta mb-1.5 font-semibold text-fg">{t("reports.gaps")}</p>
                  <ul className="flex flex-col gap-1">
                    {report.coverage_gaps.map((gap, index) => (
                      <li key={index} className="t-meta text-fg-muted">
                        · {localized(gap, locale)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="mt-4 border-t border-line pt-2">
                {report.data_notes.map((note, index) => (
                  <p key={index} className="t-micro text-fg-faint">
                    {localized(note, locale)}
                  </p>
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </>
  );
}
