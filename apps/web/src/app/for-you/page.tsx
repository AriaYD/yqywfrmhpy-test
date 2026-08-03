"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized, type MessageKey } from "@/i18n";
import { api } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { isOfficialLive } from "@/lib/real-sources";
import {
  Bar,
  Card,
  CredentialChip,
  Empty,
  Failure,
  Grid,
  Loading,
  PageHeader,
  TriState,
  type TriValue,
} from "@/components/ui";

/**
 * 唯一被允许做取舍的那个 Agent（A5）的输出。
 *
 * 排序与资格判定零模型（确定性加权和 + Rules 凭据），模型只写理由文案；
 * 因此没有 Vertex 后端时 `/matches` **不会 503**——照常返回排序结果，
 * 理由退回规则生成的兜底文案（2026-08-02 审计修正：此前这里写"会 503"是错的）。
 */
/** 契约里的 EligibilityStateName 只有这四个值（opportunity.py）。
 *  `needs_confirmation` 必须映到 unknown 而**不是** not_met——
 *  §16.2：待确认永远不能被当成淘汰依据。 */
const STATE_TRI: Record<string, TriValue> = {
  eligible_now: "met",
  future_eligible: "unknown",
  needs_confirmation: "unknown",
  ineligible_current_cycle: "not_met",
};

const STATE_KEY: Record<string, MessageKey> = {
  eligible_now: "forYou.state.eligibleNow",
  future_eligible: "forYou.state.futureEligible",
  needs_confirmation: "state.needsConfirmation",
  ineligible_current_cycle: "forYou.state.ineligibleCycle",
};

export default function ForYouPage() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  // cacheKey：切回本页命中即渲染、后台静默核新（2026-08-03 用户报障：
  // 每次切页回来都要等骨架屏，说好的缓存形同虚设）
  const matches = useResource(() => api.matches(studentId), [studentId],
    { cacheKey: "matches" });
  // 已报名状态以服务端 ActionEvent 为准（用户报障：本地 state 一刷新就丢）
  const actionEvents = useResource(() => api.actions(studentId), [studentId],
    { cacheKey: "actions" });
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNote, setRefreshNote] = useState<"idle" | "done" | "limited">("idle");
  const [applied, setApplied] = useState<Record<string, boolean>>({});
  const appliedOnServer = new Set(
    (actionEvents.data ?? [])
      .filter((e) => e.action_type === "apply")
      .map((e) => e.subject_id),
  );
  const isApplied = (id: string) => Boolean(applied[id]) || appliedOnServer.has(id);

  async function refresh() {
    setRefreshing(true);
    setRefreshNote("idle");
    try {
      await api.refreshMatches(studentId);
      matches.reload();
      setRefreshNote("done");
    } catch (err) {
      // 429 = 今天 3 次用完；结果仍是缓存的，如实告诉学生
      setRefreshNote((err as { status?: number }).status === 429 ? "limited" : "idle");
    } finally {
      setRefreshing(false);
    }
  }

  async function apply(opportunityId: string, url: string | null) {
    await api.recordAction(studentId, {
      event_id: `ACT-apply-${opportunityId}-${Date.now()}`,
      student_id: studentId,
      action_type: "apply",
      subject_id: opportunityId,
      plan_item_id: null,
      approval_receipt_id: null,
      timestamp: new Date().toISOString(),
      result: "succeeded",
      evidence_ids: [],
      verified_growth: false,
    });
    // O（2026-07-31）：报名同步进行动中心——生成一份 pending 排程提议，
    // 批准/写日历仍在行动中心走三步（预览→批准→执行），这里不越权。
    const opp = (catalog.data ?? []).find((o) => o.opportunity_id === opportunityId);
    const start = opp?.starts_at ?? opp?.deadline ?? null;
    const end =
      opp?.ends_at ??
      (start ? new Date(new Date(start).getTime() + 2 * 3_600_000).toISOString() : null);
    if (start && end) {
      try {
        await api.proposeSchedule(studentId, {
          proposal_id: `SP-APPLY-${opportunityId}`,
          student_id: studentId,
          plan_item_ids: [`PI-APPLY-${opportunityId}`],
          proposed_slots: [
            {
              plan_item_id: `PI-APPLY-${opportunityId}`,
              span: { start, end },
              conflicts: [],
            },
          ],
          assumptions: [],
          student_decision: "pending",
          calendar_action_ids: [],
        });
      } catch {
        /* 行动中心同步失败不吞掉报名本身；卡片仍显示已报名 */
      }
    }
    setApplied((prev) => ({ ...prev, [opportunityId]: true }));
    actionEvents.reload();
    // P3-6：合成机会的官方链接是占位符（example.invalid）——打开是死链，
    // 不如不开；带真实官方源的活动（Engage 66 条）照常打开
    if (url && !url.includes("example.invalid")) {
      window.open(url, "_blank", "noopener");
    }
  }
  // MatchResult 只带 opportunity_id。标题要从目录里取——
  // 卡片上放一串 id 等于让学生自己去查表。
  const catalog = useResource(() => api.catalog(500), [],
    { cacheKey: "catalog-500" });
  const titleById = new Map(
    (catalog.data ?? []).map((o) => [
      o.opportunity_id,
      localized(o.title_localized, locale) || o.title,
    ]),
  );
  const urlById = new Map(
    (catalog.data ?? []).map((o) => [o.opportunity_id, o.official_url ?? null]),
  );
  const sourceById = new Map(
    (catalog.data ?? []).map((o) => [o.opportunity_id, o.source_id ?? null]),
  );
  // fix/intl-chain（2026-08-02）：国际生注记改由 /matches 服务端逐卡派生
  // （MatchResult.intl_notes），本页不再单独拉求值信封复读第一条准备项。

  return (
    <>
      <PageHeader titleKey="forYou.title" leadKey="forYou.lead">
        <div className="flex items-center gap-2">
          {refreshNote === "done" && (
            <span className="t-meta text-fg-muted">{t("forYou.refreshed")}</span>
          )}
          {refreshNote === "limited" && (
            <span className="t-meta" style={{ color: "var(--hatch-ink)" }}>
              {t("forYou.refreshLimit")}
            </span>
          )}
          <button
            type="button"
            data-refresh-matches
            disabled={refreshing}
            onClick={refresh}
            className="pressable btn btn-secondary t-meta disabled:opacity-40"
          >
            {refreshing ? t("app.loading") : t("forYou.refresh")}
          </button>
        </div>
      </PageHeader>
      <p className="t-meta -mt-4 mb-6 text-fg-faint">{t("forYou.cacheNote")}</p>

      {matches.loading && (
        <>
          <Loading />
          {/* P2-4：首访冷启动 ~20–35s——不说清楚，学生会以为页面坏了 */}
          <p className="t-meta mt-2 text-fg-faint" data-cold-start-note>
            {t("forYou.coldStart")}
          </p>
        </>
      )}
      {matches.error && <Failure error={matches.error} onRetry={matches.reload} />}
      {matches.data?.length === 0 && <Empty />}

      <Grid min={310}>
        {matches.data?.map((match) => (
          <Card key={match.match_id} as="article">
            <div data-match={match.opportunity_id}>
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="t-section text-fg">
                    {titleById.get(match.opportunity_id) ?? match.opportunity_id}
                  </h3>
                  <div className="t-mono mt-0.5 flex items-center gap-2 text-fg-faint">
                    {match.opportunity_id}
                    {/* 真实/合成如实标注（用户裁定 D）：推荐卡也要分得清 */}
                    {isOfficialLive({
                      source_id: sourceById.get(match.opportunity_id) ?? null,
                      opportunity_id: match.opportunity_id,
                    }) ? (
                      <span
                        className="t-micro rounded-sm px-1.5 py-0.5"
                        data-official-source
                        style={{
                          border: "1px solid var(--accent)",
                          color: "var(--accent-deep)",
                        }}
                      >
                        {t("square.official")}
                      </span>
                    ) : (
                      <span className="t-micro" data-synthetic-tag>
                        {t("square.syntheticTag")}
                      </span>
                    )}
                  </div>
                </div>
                <TriState
                  value={STATE_TRI[match.eligibility.state] ?? "unknown"}
                  label={t(STATE_KEY[match.eligibility.state] ?? "state.unknown")}
                />
              </div>

              {match.reasons.length > 0 && (
                <div className="ai-note mt-4">
                  <div className="t-micro text-fg-muted">{t("forYou.why")}</div>
                  <ul className="mt-1 flex flex-col gap-1.5">
                    {match.reasons.map((reason, index) => (
                      <li key={index} className="t-meta text-fg-muted">
                        {localized(reason, locale)}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 国际生注记（特殊色 .intl-note，用户裁定 B/F）：服务端从
                  该机会自己的三态字段 + 规则包信封逐卡派生（fix/intl-chain），
                  没有可依据的字段就没有注记——不复读、不编造 */}
              {/* `?? []`：web/api 分开部署，切换窗口内新前端可能读到还没有
                  该字段的旧 api 响应——没有这层守卫整页会炸（审查发现） */}
              {(match.intl_notes ?? []).length > 0 && (
                <div className="intl-note t-micro mt-2" data-intl-note
                     style={{ color: "var(--color-mist-700)" }}>
                  <div>{t("forYou.intlNote")}</div>
                  <ul className="mt-1 flex flex-col gap-1">
                    {(match.intl_notes ?? []).map((note, index) => (
                      <li key={index}>{localized(note, locale)}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* 黄-8（2026-08-02）：主/副目标配比对学生可见——这张卡在
                  为哪个目标服务，一眼可查（80/20 不再是黑箱） */}
              {(match.goal_role ?? null) !== null && (
                <span className="chip t-micro mt-2" data-goal-role={match.goal_role}
                      style={{ borderColor: "var(--line)",
                               color: "var(--fg-muted)" }}>
                  {t(match.goal_role === "candidate"
                     ? "forYou.goalRole.candidate" : "forYou.goalRole.primary")}
                </span>
              )}

              <div className="mt-4">
                <div className="t-micro mb-1.5 flex justify-between text-fg-faint">
                  <span>{t("forYou.fit")}</span>
                  <span className="tabular-nums">{Math.round(match.score * 100)}%</span>
                </div>
                <Bar ratio={match.score} />
              </div>

              <div className="t-meta mt-3 flex flex-wrap gap-3 text-fg-muted">
                <span>
                  {t("forYou.effort")}: {match.workload_fit}
                </span>
                <span>
                  {t("forYou.closesGap")}: {match.covered_requirement_ids.length}
                </span>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-2">
                <CredentialChip validationId={match.eligibility.validation_id} />
                {match.eligibility.state === "eligible_now" && (
                  <button
                    type="button"
                    data-apply={match.opportunity_id}
                    disabled={isApplied(match.opportunity_id)}
                    onClick={() =>
                      apply(
                        match.opportunity_id,
                        urlById.get(match.opportunity_id) ?? null,
                      )
                    }
                    className="pressable btn btn-primary t-meta font-medium disabled:opacity-60"
                  >
                    {isApplied(match.opportunity_id)
                      ? t("app.appliedTag")
                      : t("forYou.apply")}
                  </button>
                )}
              </div>
            </div>
          </Card>
        ))}
      </Grid>
    </>
  );
}
