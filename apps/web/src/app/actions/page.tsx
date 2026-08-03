"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized } from "@/i18n";
import { api, ApiError, type ScheduleProposal } from "@/lib/api";
import { AdvisorBookingPanel } from "@/components/advisor-booking";
import { PlanHub } from "@/components/plan-hub";
import {
  NEAR_WINDOW_DAYS,
  planActivities,
  planAnchor,
  storedIntensity,
  withinWindow,
} from "@/lib/plan-window";
import { useResource } from "@/lib/useResource";
import {
  Card,
  CredentialChip,
  Empty,
  Failure,
  Loading,
  PageHeader,
  SectionTitle,
} from "@/components/ui";

/**
 * 预览 → 批准 → 执行，**三步分开**。
 *
 * 这一页不做"一键全部批准"。回执是对**你看过的那份内容**做的指纹，
 * 批量批准会让"看过"这件事失去含义——而回执的全部价值就在这里。
 */
export default function ActionsPage() {
  // R4-L：/actions 深链接落在合并页的"行动中心"分页
  return <PlanHub initial="actions" />;
}

/** 国际生提醒条（B3）：证件到期 ≤90 天 → 显著提醒；规则包准备项带提前量。
 * 阈值是产品规则（写死 90/60 天），数据全部来自档案与确定性求值信封。 */
function IntlReminderBanner({ studentId }: { studentId: string }) {
  const { t } = useI18n();
  const profile = useResource(() => api.profile(studentId), [studentId]);
  const intl = profile.data?.intl_context ?? null;
  const evaluation = useResource(
    () => (intl ? api.contextPackEvaluation(studentId) : Promise.resolve(null)),
    [studentId, Boolean(intl)],
  );
  if (!intl) return null;
  const daysLeft = Math.floor(
    (new Date(intl.permission_expiry_date).getTime() - Date.now()) / 86400000,
  );
  const expirySoon = daysLeft <= 90;
  const preps = evaluation.data?.consented
    ? evaluation.data.preparation_actions
    : [];
  if (!expirySoon && preps.length === 0) return null;
  const sources = evaluation.data?.consented ? evaluation.data.source_links : [];
  const anchor = intl.intended_start_date ?? intl.permission_expiry_date;
  return (
    <div className="intl-note t-meta mb-5" data-intl-reminder
         style={{ color: "var(--color-mist-700)" }}>
      {/* 评测 UI-3（2026-08-03）：横幅加显式标题——此前内容在、辨识度弱 */}
      <div className="t-body mb-1 font-medium">{t("actions.intl.title")}</div>
      {expirySoon && (
        <p data-intl-expiry-warning className="font-medium">
          {t("actions.intl.expiry")}: {intl.permission_expiry_date}
          {"（"}{daysLeft}{t("actions.intl.daysLeft")}{"）"}
        </p>
      )}
      {/* fix/intl-chain：准备项带具体目标日（锚点 = 计划开始日期，缺则证件
          到期日——与规划注入同一口径），并给官方来源链接；这些条目已作为
          带 Rules 凭据的计划项进入下方「课外活动规划」四档 */}
      {preps.slice(0, 3).map((prep) => (
        <p key={prep.preparation_action_id} className="mt-1" data-intl-prep-row>
          · {prep.title}
          {prep.recommended_lead_time_days && anchor
            ? `（${t("actions.intl.due")} ${anchor} · ${t("actions.intl.lead")} ${prep.recommended_lead_time_days} ${t("actions.intl.days")}）`
            : prep.recommended_lead_time_days
              ? `（${t("actions.intl.lead")} ${prep.recommended_lead_time_days} ${t("actions.intl.days")}）`
              : ""}
        </p>
      ))}
      {/* TODO（codex #8 记待办）：此提示假定 pathway 注入成功——严格做法是
          确认下方规划数据里真的有 PI-INTL-* 再显示；两者读同一服务端状态，
          实际不一致只会发生在 pathway 请求失败时，暂不为此多拉一次接口 */}
      {preps.length > 0 && (
        <p className="t-micro mt-1 opacity-80" data-intl-in-plan-note>
          {t("actions.intl.inPlan")}
        </p>
      )}
      {sources.length > 0 && (
        <p className="t-micro mt-1" data-intl-sources>
          {t("actions.intl.sources")}:{" "}
          {sources.slice(0, 3).map((link, index) => (
            <span key={link.source_id}>
              {index > 0 && " · "}
              <a href={link.url} target="_blank" rel="noopener noreferrer"
                 className="underline underline-offset-2">
                {link.title}
              </a>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

export function ActionsContent() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [outcome, setOutcome] = useState<
    Record<string, "written" | "approved_no_write" | "rejected">
  >({});
  // 写入被拒且原因是缺 calendar_write 同意 → 就地给授权入口（N，2026-07-31）
  const [consentDenied, setConsentDenied] = useState<Record<string, boolean>>({});

  /** 逐时段写日历。返回 written 与"失败是否因为缺同意"。 */
  async function writeSlots(proposal: ScheduleProposal) {
    let written = true;
    let missingConsent = false;
    // R4-M：写进日历的标题用活动全名，不用内部 id——周日历上要看得懂
    const opp = opportunityOf(proposal.proposal_id, [...proposal.plan_item_ids]);
    const eventTitle = opp
      ? (localized(opp.title_localized, locale) || opp.title)
      : `CampusPath Plan · ${proposal.proposal_id.replace(/^SP-(APPLY-)?/, "")}`;
    for (const slot of proposal.proposed_slots) {
      try {
        await api.writeCalendarAction(studentId, {
          action_id: `CAL-${proposal.proposal_id}-${slot.plan_item_id}`,
          student_id: studentId,
          provider: "fixture",
          action: "create",
          draft: {
            event_title: eventTitle,
            span: slot.span,
            reminder_minutes_before: null,
          },
          idempotency_key: `CAL-${proposal.proposal_id}-${slot.plan_item_id}`,
          approval_receipt_id: `RCPT-${proposal.proposal_id}`,
          external_event_id: null,
          result: "pending",
          failure_reason: null,
        });
      } catch (err) {
        written = false; // 403 = 未授权写日历，如实展示
        if (
          err instanceof ApiError &&
          err.status === 403 &&
          typeof err.body === "object" &&
          err.body !== null &&
          (err.body as { detail?: { error?: string } }).detail?.error ===
            "consent_missing"
        ) {
          missingConsent = true;
        }
      }
    }
    return { written, missingConsent };
  }

  const proposals = useResource(() => api.scheduleProposals(studentId), [studentId]);
  // 强度必须与课外规划页同源（storedIntensity）——两页才读的是同一份规划
  const [intensity] = useState<string>(storedIntensity);
  const pathway = useResource(
    () => api.pathway(studentId, intensity), [studentId, intensity]);
  // 审计红-3（2026-08-02）：批准时日历写入 403 的恢复入口曾是组件内存态，
  // 离开页面即永久丢失。现从服务端可观测状态**派生**：已批准的提案 ∩
  // 日历里没有对应 AB-…plan-OPP-… 真实块 ⇒ 「待写入日历」，页面加载即渲染。
  const availabilityRows = useResource(() => api.availability(studentId), [studentId]);
  // O：行程卡要展示活动详情（截止/时间线/投入/前置要求/备考提前量）
  const catalog = useResource(() => api.catalog(500, true), []);
  const opportunityOf = (proposalId: string, planItemIds: string[]) => {
    // id 形如 SP-APPLY-OPP-EVT-046 / PI-APPLY-OPP-… / SP-OPP-…——
    // 直接抽取 OPP- 起的尾段，而不是按前缀剥（剥法漏掉 APPLY- 段，
    // 正是"等你批准卡显示代码名"的根因，用户报障 2026-08-01）
    const ids = [proposalId, ...planItemIds]
      .map((x) => x.match(/OPP-.+$/)?.[0])
      .filter((x): x is string => Boolean(x));
    return (catalog.data ?? []).find((o) => ids.includes(o.opportunity_id)) ?? null;
  };

  const pending = (proposals.data ?? []).filter(
    (p) => p.student_decision === "pending",
  );
  const writtenOpps = new Set(
    (availabilityRows.data ?? [])
      .map((b) => b.block_id.match(/plan-(OPP-.*?)(?:-PI-|$)/)?.[1])
      .filter((x): x is string => Boolean(x)),
  );
  const approvedUnwritten = (proposals.data ?? []).filter((p) => {
    if (p.student_decision !== "approved") return false;
    const opp = [p.proposal_id, ...p.plan_item_ids]
      .map((x) => x.match(/OPP-.+$/)?.[0])
      .find((x): x is string => Boolean(x));
    return opp !== undefined && !writtenOpps.has(opp);
  });

  return (
    <>
      <PageHeader titleKey="actions.title" leadKey="actions.lead" />

      {/* Q（2026-07-31）：Advisor 预约挪到行动中心置顶——它就是一个"要去做的行动" */}
      <AdvisorBookingPanel />

      {/* 国际生证件/政策提醒（B3，2026-08-02）：确定性派生自规则包求值
          （permission_expiry 阈值 + preparation lead time），非模型推断 */}
      <IntlReminderBanner studentId={studentId} />


      <SectionTitle>{t("actions.pending")}</SectionTitle>
      {/* 同意回执注脚放在「等你批准」标题正下方——它就是对批准行为的注释
          （用户复裁定 2026-08-01） */}
      <p className="t-micro mb-3 max-w-[76ch] text-fg-faint" data-receipt-note>
        {t("actions.receipt")} — {t("actions.receipt.explain")}
      </p>
      {proposals.loading && <Loading />}
      {proposals.error && <Failure error={proposals.error} onRetry={proposals.reload} />}
      {pending.length === 0 && !proposals.loading && (
        <Empty messageKey="actions.empty" />
      )}

      <ul className="mb-8 flex flex-col gap-3">
        {pending.map((proposal) => {
          const blocking = proposal.proposed_slots.flatMap((slot) =>
            slot.conflicts.filter((c) => c.blocking),
          );
          const done = outcome[proposal.proposal_id];
          return (
            <Card key={proposal.proposal_id} as="li">
              <div data-schedule-proposal={proposal.proposal_id}>
                {/* 标题必须是活动原名，不是 SP-APPLY 代码（用户裁定 2026-08-01）；
                    proposal id 降为溯源子行 */}
                {(() => {
                  const titled = opportunityOf(proposal.proposal_id,
                                               [...proposal.plan_item_ids]);
                  return (
                    <>
                      <div className="t-section text-fg" data-proposal-title>
                        {titled
                          ? localized(titled.title_localized, locale) || titled.title
                          : proposal.proposal_id}
                      </div>
                      <div className="t-mono mt-0.5 text-fg-faint">
                        {proposal.proposal_id}
                      </div>
                    </>
                  );
                })()}
                <ul className="mt-3 flex flex-col gap-1.5">
                  {proposal.proposed_slots.map((slot) => (
                    <li key={slot.plan_item_id} className="t-mono text-fg-muted">
                      {slot.plan_item_id}: {slot.span.start.slice(0, 16)} →{" "}
                      {slot.span.end.slice(11, 16)}
                    </li>
                  ))}
                </ul>

                {(() => {
                  const opp = opportunityOf(proposal.proposal_id,
                                            [...proposal.plan_item_ids]);
                  if (!opp) return null;
                  const deadline = opp.deadline ? opp.deadline.slice(0, 10) : null;
                  // 准备提前量（确定性估算，界面注明）：
                  // 比赛/工作坊/含证书要求的，按投入量折算备考期（14–60 天封顶）；
                  // 实习/工作类活动本身就是投入，报名材料准备固定留 14 天。
                  const needsStudyPrep =
                    ["competition", "workshop", "scholarship"].includes(opp.type) ||
                    opp.requirement_categories.includes("credential");
                  const prepDays = needsStudyPrep && opp.workload_hours_total
                    ? Math.min(60, Math.max(14, Math.ceil(opp.workload_hours_total / 10)))
                    : 14;
                  const prepStart = deadline
                    ? new Date(new Date(opp.deadline!).getTime()
                        - prepDays * 86400000).toISOString().slice(0, 10)
                    : null;
                  return (
                    <div className="mt-3 rounded-md border border-line bg-bg-sunk p-3"
                         data-activity-detail={opp.opportunity_id}>
                      <div className="t-body text-fg">
                        {localized(opp.title_localized, locale) || opp.title}
                      </div>
                      <div className="t-meta mt-1 flex flex-wrap gap-x-4 gap-y-1 text-fg-muted">
                        {deadline && (
                          <span data-detail-deadline>
                            {t("actions.detail.deadline")}: {deadline}
                          </span>
                        )}
                        {opp.starts_at && (
                          <span data-detail-span>
                            {t("actions.detail.span")}: {opp.starts_at.slice(0, 10)}
                            {opp.ends_at ? ` → ${opp.ends_at.slice(0, 10)}` : ""}
                          </span>
                        )}
                        {opp.workload_hours_total != null && (
                          <span>
                            {t("actions.detail.workload")}: {opp.workload_hours_total}h
                          </span>
                        )}
                      </div>
                      {opp.eligibility_rules.length > 0 && (
                        <div className="mt-2">
                          <div className="t-micro text-fg-faint">
                            {t("actions.detail.prereqs")}
                          </div>
                          <ul className="mt-0.5 flex flex-col gap-0.5">
                            {opp.eligibility_rules.slice(0, 4).map((rule, index) => (
                              <li key={index} className="t-mono text-fg-muted">
                                {rule.expression}
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {prepStart && (
                        <p className="ai-note t-meta mt-2" style={{ color: "var(--hatch-ink)" }}
                           data-prep-hint>
                          {t("actions.detail.prep")
                            .replace("{date}", prepStart)
                            .replace("{days}", String(prepDays))}
                        </p>
                      )}
                    </div>
                  );
                })()}

                {blocking.length > 0 && (
                  <p
                    className="t-meta mt-3 rounded-md p-3"
                    data-blocking-conflict
                    style={{
                      border: "1px solid var(--color-clay-500)",
                      color: "var(--color-clay-600)",
                      background: "var(--color-clay-100)",
                    }}
                  >
                    {t("actions.conflict.blocking")}
                  </p>
                )}

                {/* 用户裁定 B（2026-08-02）：与课程/普通忙碌重叠 → 显式警示但
                    可仍批准；批准后条目与日历块带 ⚠️ 标记 */}
                {(() => {
                  const soft = proposal.proposed_slots.flatMap((slot) =>
                    slot.conflicts.filter((c) => !c.blocking));
                  if (soft.length === 0 || blocking.length > 0) return null;
                  return (
                    <div
                      className="t-meta mt-3 rounded-md p-3"
                      data-soft-conflict
                      style={{
                        border: "1px solid var(--hatch)",
                        color: "var(--hatch-ink)",
                        background: "color-mix(in srgb, var(--hatch) 10%, transparent)",
                      }}
                    >
                      <p className="font-medium">
                        ⚠️ {t("actions.conflict.soft").replace("{n}", String(soft.length))}
                      </p>
                      <ul className="mt-1 flex flex-col gap-0.5">
                        {soft.slice(0, 3).map((c, index) => (
                          <li key={index} className="t-micro">
                            · {(c.detail && localized(c.detail, locale))
                               || c.with_block_id || c.conflict_type}
                          </li>
                        ))}
                      </ul>
                      <p className="t-micro mt-1 opacity-80">
                        {t("actions.conflict.softNote")}
                      </p>
                    </div>
                  );
                })()}

                <div className="mt-4 flex items-center gap-2">
                  <button
                    type="button"
                    data-approve={proposal.proposal_id}
                    disabled={blocking.length > 0 || !!done}
                    onClick={async () => {
                      // 批准 = 服务端记录决定；随后逐个时段写日历。
                      // 回执指向刚刚批准的这份预览（Spec §15.4 规则 8）。
                      await api.proposeSchedule(studentId, {
                        ...proposal,
                        student_decision: "approved",
                      });
                      const { written, missingConsent } = await writeSlots(proposal);
                      setConsentDenied((prev) => ({
                        ...prev,
                        [proposal.proposal_id]: missingConsent,
                      }));
                      setOutcome((prev) => ({
                        ...prev,
                        [proposal.proposal_id]: written
                          ? "written"
                          : "approved_no_write",
                      }));
                    }}
                    className="pressable btn btn-primary t-meta font-medium disabled:opacity-40"
                  >
                    {t("actions.approve")}
                  </button>
                  <button
                    type="button"
                    data-reject={proposal.proposal_id}
                    disabled={!!done}
                    onClick={async () => {
                      await api.proposeSchedule(studentId, {
                        ...proposal,
                        student_decision: "rejected",
                      });
                      setOutcome((prev) => ({
                        ...prev,
                        [proposal.proposal_id]: "rejected",
                      }));
                    }}
                    className="pressable btn btn-secondary t-meta"
                  >
                    {t("actions.reject")}
                  </button>
                  {done === "written" && (
                    <span className="t-meta" style={{ color: "var(--color-moss-600)" }}
                          data-calendar-written>
                      {t("actions.written")}
                    </span>
                  )}
                  {done === "approved_no_write" && (
                    <span className="t-meta" style={{ color: "var(--hatch-ink)" }}
                          data-calendar-denied>
                      {t("actions.writeDenied")}
                    </span>
                  )}
                  {done === "approved_no_write" &&
                    consentDenied[proposal.proposal_id] && (
                      <button
                        type="button"
                        data-grant-calendar-write={proposal.proposal_id}
                        title={t("actions.grantWrite.hint")}
                        onClick={async () => {
                          await api.updateConsent(studentId, {
                            scope: "calendar_write",
                            granted: true,
                          });
                          const { written, missingConsent } =
                            await writeSlots(proposal);
                          setConsentDenied((prev) => ({
                            ...prev,
                            [proposal.proposal_id]: missingConsent,
                          }));
                          setOutcome((prev) => ({
                            ...prev,
                            [proposal.proposal_id]: written
                              ? "written"
                              : "approved_no_write",
                          }));
                        }}
                        className="pressable btn btn-secondary t-meta font-medium"
                        style={{ color: "var(--accent-deep)" }}
                      >
                        {t("actions.grantWrite")}
                      </button>
                    )}
                  {done === "rejected" && (
                    <span className="t-meta text-fg-muted">{t("actions.rejected")}</span>
                  )}
                </div>
              </div>
            </Card>
          );
        })}
      </ul>

      {/* 审计红-3：已批准但日历写入未成功的提案——持久恢复入口，
          刷新/换页后仍在，直到真实块写进日历为止 */}
      {approvedUnwritten.length > 0 && (
        <>
          <SectionTitle>{t("actions.unwritten.title")}</SectionTitle>
          <p className="t-micro mb-3 max-w-[76ch] text-fg-faint">
            {t("actions.unwritten.lead")}
          </p>
          <ul className="mb-8 flex flex-col gap-2" data-unwritten-list>
            {approvedUnwritten.map((proposal) => {
              const titled = opportunityOf(proposal.proposal_id,
                                           [...proposal.plan_item_ids]);
              return (
                <Card key={proposal.proposal_id} as="li">
                  <div className="flex flex-wrap items-center gap-3"
                       data-unwritten={proposal.proposal_id}>
                    <span className="t-body text-fg">
                      {titled
                        ? localized(titled.title_localized, locale) || titled.title
                        : proposal.proposal_id}
                    </span>
                    <button
                      type="button"
                      data-grant-calendar-write={proposal.proposal_id}
                      title={t("actions.grantWrite.hint")}
                      onClick={async () => {
                        await api.updateConsent(studentId, {
                          scope: "calendar_write", granted: true,
                        });
                        const { written } = await writeSlots(proposal);
                        if (written) {
                          availabilityRows.reload();
                          proposals.reload();
                        }
                      }}
                      className="pressable btn btn-secondary t-meta font-medium"
                      style={{ color: "var(--accent-deep)" }}
                    >
                      {t("actions.grantWrite")}
                    </button>
                  </div>
                </Card>
              );
            })}
          </ul>
        </>
      )}

      {/* 计划项本身也是"要做的事"，只是它们的批准动作在时间线上。
          口径与课外活动规划共用 plan-window（2026-08-03 用户报障：
          旧筛法 status==="in_progress" 是夹具时代残留，A5 条目全是
          proposed → 该区恒空，与规划页近两周互相矛盾） */}
      <SectionTitle>{t("timeline.range.near")}</SectionTitle>
      {pathway.loading && <Loading />}
      {pathway.error && <Failure error={pathway.error} emptyKey="timeline.empty" />}
      {(() => {
        if (!pathway.data) return null;
        const activities = planActivities(pathway.data.plan_items);
        const anchor = planAnchor(activities);
        const near = activities.filter((item) =>
          withinWindow(item, NEAR_WINDOW_DAYS, anchor));
        if (!near.length) return <Empty messageKey="timeline.empty" />;
        return (
          <ul className="flex flex-col gap-2">
            {near.map((item) => (
              <Card key={item.plan_item_id} as="li" className="!p-4">
                <div
                  data-action-item={item.plan_item_id}
                  className="flex flex-wrap items-center justify-between gap-3"
                >
                  <div>
                    <div className="t-body text-fg">{localized(item.title, locale)}</div>
                    <div className="t-mono mt-0.5 text-fg-faint">
                      {item.date_range.start} → {item.date_range.end ?? "—"}
                    </div>
                  </div>
                  <CredentialChip validationId={item.validation_id} />
                </div>
              </Card>
            ))}
          </ul>
        );
      })()}
    </>
  );
}
