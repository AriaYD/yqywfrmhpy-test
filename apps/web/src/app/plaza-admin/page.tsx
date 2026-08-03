"use client";

import { useMemo, useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n, localized } from "@/i18n";
import { api, institution } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Button, Input } from "@/components/primitives";
import {
  Card,
  Empty,
  Failure,
  Loading,
  Metric,
  PageHeader,
  SectionTitle,
} from "@/components/ui";

/**
 * 校方端资讯广场总览（用户裁定 2026-08-01）：
 * 管理人员清晰看到广场上有什么、有多少——没有学生端的报名/收藏操作。
 * B10 追加：搜索 + 已发布活动的**编辑/下架**（审核批准后的生命周期管理：
 * 活动取消可下架、改期可就地修改）。下架不物理删除，存档可审计。
 */
export default function PlazaAdminPage() {
  const { t, locale } = useI18n();
  const { role } = useRole();
  // D 批（2026-08-02）：在架 / Archive 两分页——活动结束 + 2 个月自动转归档视图
  const [view, setView] = useState<"live" | "archive">("live");
  // include_expired=true：管理视图连同已截止/已下架存档一并监看
  const catalog = useResource(() => api.catalog(500, true, view), [role, view]);
  // 实时评分统计（去标识聚合；低于阈值的活动分数为 null）
  const quality = useResource(() => institution.qualitySummary(), [role]);
  const qualityById = useMemo(
    () => new Map((quality.data ?? []).map((q) => [q.opportunity_id, q])),
    [quality.data],
  );
  // 二维码弹层：懒加载签到信息 + 本地生成 QR data URL（零外网依赖）
  const [qrFor, setQrFor] = useState<string | null>(null);
  const [qrData, setQrData] = useState<{ url: string; dataUrl: string; count: number } | null>(null);
  const [qrErr, setQrErr] = useState<string | null>(null);
  async function showQr(opportunityId: string) {
    setQrFor(opportunityId);
    setQrData(null);
    setQrErr(null);
    try {
      const info = await institution.checkinInfo(opportunityId);
      const absolute = `${window.location.origin}${info.checkin_url}`;
      const QRCode = (await import("qrcode")).default;
      const dataUrl = await QRCode.toDataURL(absolute, { width: 220, margin: 1 });
      setQrData({ url: absolute, dataUrl, count: info.attend_count });
    } catch (err) {
      // 审查 #10：失败要说话，不许弹层无声消失
      setQrErr((err as Error).message);
    }
  }

  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ title: "", deadline: "" });
  const [confirmingWithdraw, setConfirmingWithdraw] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const rows = catalog.data ?? [];
  const published = rows.filter((o) => o.publication_status === "published");
  const expired = rows.filter((o) => o.publication_status === "expired");

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((o) => {
      const title = (localized(o.title_localized, locale) || o.title).toLowerCase();
      const organizer = (
        localized(o.organizer_localized, locale) || o.organizer
      ).toLowerCase();
      return title.includes(q) || organizer.includes(q) ||
        o.opportunity_id.toLowerCase().includes(q);
    });
  }, [rows, query, locale]);

  async function saveEdit(opportunityId: string) {
    setBusy(opportunityId);
    setNotice(null);
    try {
      await institution.editOpportunity(opportunityId, {
        title: draft.title.trim() || null,
        deadline: draft.deadline ? `${draft.deadline}T23:59:00Z` : null,
        starts_at: null,
        ends_at: null,
        official_url: null,
      });
      setEditing(null);
      catalog.reload();
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function withdraw(opportunityId: string) {
    setBusy(opportunityId);
    setNotice(null);
    try {
      await institution.withdrawOpportunity(opportunityId);
      setConfirmingWithdraw(null);
      catalog.reload();
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <PageHeader titleKey="console.plaza.title" leadKey="console.plaza.lead">
        <span
          className="t-micro rounded-full px-2.5 py-1"
          data-active-role={role}
          style={{ border: "1px solid var(--accent)", color: "var(--accent-deep)" }}
        >
          {t("console.actingAs")}: {role}
        </span>
      </PageHeader>

      <Card className="mb-5" data-plaza-stats>
        <div className="flex flex-wrap gap-10">
          <Metric label={t("console.plaza.total")} value={rows.length} />
          <Metric label={t("console.plaza.published")} value={published.length} tone="good" />
          <Metric label={t("console.plaza.expired")} value={expired.length} />
        </div>
      </Card>

      <Card>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <span className="flex items-center gap-3">
            <SectionTitle>{t("page.square")}</SectionTitle>
            {/* 在架 / Archive 分页（全站统一分段控件样式） */}
            <div className="inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
                 data-plaza-view-tabs>
              {(["live", "archive"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  data-plaza-view={v}
                  aria-pressed={view === v}
                  onClick={() => setView(v)}
                  className="pressable t-meta rounded-sm px-3 py-1"
                  style={{
                    background: view === v ? "var(--accent-deep)" : "transparent",
                    color: view === v ? "var(--accent-fg)" : "var(--fg-muted)",
                    fontWeight: view === v ? 600 : 500,
                  }}
                >
                  {t(v === "live" ? "console.plaza.viewLive" : "console.plaza.viewArchive")}
                </button>
              ))}
            </div>
          </span>
          <Input
            type="search"
            data-plaza-search
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("console.plaza.search")}
            className="max-w-[260px]"
          />
        </div>
        {catalog.loading && <Loading />}
        {catalog.error && <Failure error={catalog.error} onRetry={catalog.reload} />}
        {visible.length === 0 && !catalog.loading && <Empty />}
        {notice && (
          <p className="t-meta mb-2" data-plaza-notice
             style={{ color: "var(--color-clay-600)" }}>{notice}</p>
        )}
        <ul className="flex flex-col gap-2" data-plaza-list>
          {visible.map((opp) => {
            const isEditing = editing === opp.opportunity_id;
            const isConfirming = confirmingWithdraw === opp.opportunity_id;
            return (
              <li
                key={opp.opportunity_id}
                data-plaza-item={opp.opportunity_id}
                className="rounded-md border border-line bg-bg-sunk px-3 py-2.5"
              >
                {!isEditing ? (
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <span className="min-w-0">
                      <span className="t-body text-fg">
                        {localized(opp.title_localized, locale) || opp.title}
                      </span>
                      <span className="t-meta ms-2 text-fg-muted">
                        {localized(opp.organizer_localized, locale) || opp.organizer}
                      </span>
                    </span>
                    <span className="t-micro flex items-center gap-2 text-fg-faint">
                      {opp.category_tags.slice(0, 2).join(" · ")}
                      {opp.deadline ? ` · ${opp.deadline.slice(0, 10)}` : ""}
                      <span
                        className="rounded-sm border border-line px-1.5 py-0.5"
                        data-plaza-status={opp.publication_status}
                      >
                        {opp.publication_status}
                      </span>
                      <Button
                        variant="ghost"
                        data-plaza-qr={opp.opportunity_id}
                        onClick={() => showQr(opp.opportunity_id)}
                      >
                        {t("console.plaza.qr")}
                      </Button>
                      {opp.publication_status !== "withdrawn" && view === "live" && (
                        <>
                          <Button
                            variant="ghost"
                            data-plaza-edit={opp.opportunity_id}
                            onClick={() => {
                              setEditing(opp.opportunity_id);
                              setConfirmingWithdraw(null);
                              setDraft({
                                title: localized(opp.title_localized, locale) || opp.title,
                                deadline: opp.deadline?.slice(0, 10) ?? "",
                              });
                            }}
                          >
                            {t("profile.edit")}
                          </Button>
                          <Button
                            variant="danger"
                            data-plaza-withdraw={opp.opportunity_id}
                            disabled={busy === opp.opportunity_id}
                            onClick={() => setConfirmingWithdraw(opp.opportunity_id)}
                          >
                            {t("console.plaza.withdraw")}
                          </Button>
                        </>
                      )}
                    </span>
                  </div>
                ) : null}
                {/* 实时反馈统计（2026-08-04 用户裁定重做）：学生评的是
                    四维分 + 个人契合标签——逐维中文标签上屏，契合分布
                    独立分区（§17.4：个人判断不折进质量分，但分布是给
                    主办方的信号）；阈值下如实 Insufficient + 说明 */}
                {!isEditing && (() => {
                  const q = qualityById.get(opp.opportunity_id);
                  if (!q) return null;
                  return (
                    <div className="t-micro mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-fg-muted"
                         data-plaza-quality={opp.opportunity_id}>
                      <span>{t("console.plaza.feedbackN")}: {q.feedback_n}</span>
                      <span>{t("console.plaza.verifiedN")}: {q.verified_n}</span>
                      <span>{t("console.plaza.attendN")}: {q.attend_count}</span>
                      {q.avg_overall != null ? (
                        <>
                          <span className="font-semibold" style={{ color: "var(--accent-deep)" }}>
                            {t("console.plaza.avg")}: {q.avg_overall.toFixed(1)}/5
                          </span>
                          {q.favorable_rate != null && (
                            <span>{t("console.plaza.favorable")}: {Math.round(q.favorable_rate * 100)}%</span>
                          )}
                          <span className="inline-flex flex-wrap gap-1.5"
                                data-plaza-dims>
                            {q.dimensions.map((d) => (
                              <span key={d.dimension}
                                    className="rounded-sm border border-line px-1.5 py-0.5"
                                    title={`CI ${d.ci_low.toFixed(1)}–${d.ci_high.toFixed(1)}`}>
                                {t(`console.plaza.dim.${d.dimension}` as Parameters<typeof t>[0])}{" "}
                                <span className="t-mono font-semibold text-fg">
                                  {d.weighted_score.toFixed(1)}
                                </span>
                              </span>
                            ))}
                          </span>
                          {q.fit_distribution.length > 0 && (
                            <span className="inline-flex flex-wrap items-center gap-1.5"
                                  data-plaza-fit>
                              <span className="text-fg-faint">
                                {t("console.plaza.fitTitle")}:
                              </span>
                              {q.fit_distribution.map((s) => (
                                <span key={s.fit} className="chip chip-mist">
                                  {t(`reflections.fit.${s.fit}` as Parameters<typeof t>[0])}{" "}
                                  {Math.round(s.share * 100)}%
                                </span>
                              ))}
                            </span>
                          )}
                        </>
                      ) : (
                        <span className="hatch-unknown rounded-sm px-1.5 py-0.5"
                              title={t("console.plaza.thresholdWhy")}>
                          {t("console.insufficient")}
                          <span className="ms-1 opacity-80">
                            · {t("console.plaza.thresholdWhy")}
                          </span>
                        </span>
                      )}
                      {q.stats_frozen && (
                        <span className="rounded-sm border border-line px-1.5 py-0.5"
                              data-stats-frozen>
                          {t("console.plaza.frozen")}
                        </span>
                      )}
                    </div>
                  );
                })()}
                {isEditing ? (
                  <div className="flex flex-wrap items-end gap-2">
                    <label className="block min-w-[220px] flex-1">
                      <span className="t-micro block text-fg-faint">
                        {t("publisher.opportunityTitle")}
                      </span>
                      <Input
                        data-plaza-edit-title={opp.opportunity_id}
                        value={draft.title}
                        onChange={(e) =>
                          setDraft((d) => ({ ...d, title: e.target.value }))
                        }
                        className="mt-1"
                      />
                    </label>
                    <label className="block">
                      <span className="t-micro block text-fg-faint">
                        {t("console.plaza.editDeadline")}
                      </span>
                      <Input
                        type="date"
                        data-plaza-edit-deadline={opp.opportunity_id}
                        value={draft.deadline}
                        onChange={(e) =>
                          setDraft((d) => ({ ...d, deadline: e.target.value }))
                        }
                        className="mt-1"
                      />
                    </label>
                    <Button
                      variant="primary"
                      data-plaza-edit-save={opp.opportunity_id}
                      disabled={busy === opp.opportunity_id || !draft.title.trim()}
                      onClick={() => saveEdit(opp.opportunity_id)}
                    >
                      {t("profile.edit.save")}
                    </Button>
                    <Button
                      variant="ghost"
                      data-plaza-edit-cancel={opp.opportunity_id}
                      onClick={() => setEditing(null)}
                    >
                      {t("calendar.editor.cancel")}
                    </Button>
                  </div>
                ) : null}

                {/* 下架是不可逆动作（对学生视图而言）——用确认两段式，
                    与 settings 删除同一纪律（审查 M1 同款要求） */}
                {isConfirming && (
                  <div
                    className="mt-2 flex flex-wrap items-center gap-2 rounded-md p-2.5"
                    role="alertdialog"
                    data-plaza-withdraw-confirm={opp.opportunity_id}
                    style={{
                      border: "1px solid var(--color-clay-500)",
                      background: "var(--color-clay-100)",
                    }}
                  >
                    <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                      {t("console.plaza.withdrawConfirm")}
                    </span>
                    <Button
                      data-plaza-withdraw-go={opp.opportunity_id}
                      disabled={busy === opp.opportunity_id}
                      onClick={() => withdraw(opp.opportunity_id)}
                      className="!bg-[var(--color-clay-600)] !text-[var(--color-clay-100)]"
                    >
                      {t("console.plaza.withdraw")}
                    </Button>
                    <Button variant="ghost" onClick={() => setConfirmingWithdraw(null)}>
                      {t("calendar.editor.cancel")}
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      {/* 二维码弹层（D 批）：现场投屏给学生扫码签到 */}
      {qrFor && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center"
          style={{ background: "color-mix(in srgb, var(--fg) 35%, transparent)" }}
          data-qr-overlay
          onClick={() => setQrFor(null)}
        >
          <div
            role="dialog"
            aria-label={t("console.plaza.qrTitle")}
            className="rounded-lg border border-line bg-card p-5 shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="t-section text-fg">{t("console.plaza.qrTitle")}</p>
            <p className="t-mono mt-0.5 text-fg-faint">{qrFor}</p>
            {qrData ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={qrData.dataUrl} alt="check-in QR" width={220} height={220}
                     className="mt-3 rounded-md" data-qr-image />
                <p className="t-micro mt-2 max-w-[240px] break-all text-fg-faint">
                  {qrData.url}
                </p>
                <p className="t-meta mt-2 text-fg-muted" data-qr-attend>
                  {t("console.plaza.attendN")}: {qrData.count}
                </p>
              </>
            ) : qrErr ? (
              <p className="t-meta mt-3 max-w-[240px]" data-qr-error
                 style={{ color: "var(--color-clay-600)" }}>{qrErr}</p>
            ) : (
              <Loading />
            )}
            <Button variant="secondary" className="mt-3" onClick={() => setQrFor(null)}>
              {t("calendar.editor.cancel")}
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
