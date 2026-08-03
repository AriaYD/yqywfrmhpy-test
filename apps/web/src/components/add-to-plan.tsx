"use client";

/**
 * 「加入日程」的三步：**排程预览 → 冲突高亮 → 学生决定要不要重排**。
 *
 * 三步分开是有意的，与 Action Center 同一条原则：
 *
 * 1. 先算——POST schedule-proposals，**冲突由服务端算**，前端只负责显示；
 * 2. 再看——与保护时段撞车是 blocking（学生自己划下的睡眠/用餐/照护），
 *    与普通忙碌撞车只是提示（哪个能翘学生自己清楚）；
 * 3. 最后才问要不要重排。**默认不重排。** §16.9 的局部重排意味着
 *    原主路线为主、新加的东西围着它排；但即使如此，动学生的计划
 *    也得他点头——replan-preview 端点因此没有任何写入。
 */

import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { useI18n, localized } from "@/i18n";
import {
  api,
  type AffectedScope,
  type Opportunity,
  type ScheduleProposal,
} from "@/lib/api";
import { Drawer } from "./ui";

type Phase = "idle" | "checking" | "review" | "replanning" | "done";

/** 来源没给开始时间时的兜底时段：明天 15:00–17:00。
 *  **明确标出来是我们选的**，不假装来源说了。 */
function fallbackSlot(): { start: string; end: string } {
  const start = new Date();
  start.setUTCDate(start.getUTCDate() + 1);
  start.setUTCHours(15, 0, 0, 0);
  const end = new Date(start.getTime() + 2 * 3600_000);
  return { start: start.toISOString(), end: end.toISOString() };
}

/** 一次排程最多占这么久。超过就不是"一个时段"了。 */
const MAX_SLOT_HOURS = 8;

/**
 * 把机会的起止换算成**一个可排的时段**。
 *
 * 实习的 `starts_at → ends_at` 是**整段实习期**（好几个月），不是一次日程。
 * 第一版直接把它当成一个 span 塞进排程预览，于是一条实习和这一周的
 * 每一个区块都"冲突"——76 条冲突、36 条阻断，界面被淹掉，
 * 而真正该看的信息一条也读不出来。
 *
 * 超过 MAX_SLOT_HOURS 的，只排**第一天的两小时**作为起点，
 * 并在界面上说明这是长期承诺——剩下的属于计划项，不属于某一格日历。
 */
function slotFor(opportunity: Opportunity): {
  span: { start: string; end: string };
  assumed: boolean;
  longRunning: boolean;
} {
  if (!opportunity.starts_at) {
    return { span: fallbackSlot(), assumed: true, longRunning: false };
  }
  const start = new Date(opportunity.starts_at);
  const declaredEnd = opportunity.ends_at ? new Date(opportunity.ends_at) : null;
  const hours = declaredEnd
    ? (declaredEnd.getTime() - start.getTime()) / 3600_000
    : 2;
  if (hours > MAX_SLOT_HOURS) {
    return {
      span: {
        start: start.toISOString(),
        end: new Date(start.getTime() + 2 * 3600_000).toISOString(),
      },
      assumed: false,
      longRunning: true,
    };
  }
  return {
    span: {
      start: start.toISOString(),
      end: (declaredEnd ?? new Date(start.getTime() + 2 * 3600_000)).toISOString(),
    },
    assumed: false,
    longRunning: false,
  };
}

export function AddToPlan({
  opportunity,
  studentId,
  onAdded,
}: {
  opportunity: Opportunity;
  studentId: string;
  onAdded?: () => void;
}) {
  const { t, locale } = useI18n();
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<Phase>("idle");
  const [proposal, setProposal] = useState<ScheduleProposal | null>(null);
  const [scope, setScope] = useState<AffectedScope | null>(null);
  const [error, setError] = useState<string | null>(null);

  const { span: slot, assumed, longRunning } = slotFor(opportunity);

  const conflicts = (proposal?.proposed_slots ?? []).flatMap((s) => s.conflicts);
  const blocking = conflicts.filter((c) => c.blocking);

  async function check() {
    setPhase("checking");
    setError(null);
    try {
      const result = await api.proposeSchedule(studentId, {
        proposal_id: `SP-${opportunity.opportunity_id}`,
        student_id: studentId,
        plan_item_ids: [`PI-${opportunity.opportunity_id}`],
        proposed_slots: [
          {
            plan_item_id: `PI-${opportunity.opportunity_id}`,
            span: slot,
            conflicts: [],
          },
        ],
        assumptions: [],
        student_decision: "pending",
        calendar_action_ids: [],
      });
      setProposal(result);
      setPhase("review");
    } catch (err) {
      setError((err as Error).message);
      setPhase("idle");
    }
  }

  async function confirmAdd(withReplan: boolean) {
    setPhase("replanning");
    try {
      await api.recordAction(studentId, {
        event_id: `ACT-add-${opportunity.opportunity_id}`,
        student_id: studentId,
        action_type: "add_to_pathway",
        subject_id: opportunity.opportunity_id,
        plan_item_id: null,
        approval_receipt_id: null,
        timestamp: new Date().toISOString(),
        // ActionEvent.result 没有 pending：动作发生了就是 succeeded，
        // "还没结果"的东西不该被记成一次行动（tsc 拦下来的）
        result: "succeeded",
        evidence_ids: [],
        verified_growth: false,
      });
      if (withReplan) {
        setScope(
          await api.replanPreview(studentId, {
            student_id: studentId,
            trigger_type: "student_added_opportunity",
            source: opportunity.opportunity_id,
            detected_at: new Date().toISOString(),
            request_id: `RQ-${opportunity.opportunity_id}`,
          }),
        );
      }
      setPhase("done");
      onAdded?.();
    } catch (err) {
      setError((err as Error).message);
      setPhase("review");
    }
  }

  return (
    <>
      <button
        type="button"
        data-add-to-plan={opportunity.opportunity_id}
        onClick={check}
        disabled={phase === "checking"}
        className="pressable btn btn-secondary t-meta disabled:opacity-50"
       
      >
        {t(phase === "checking" ? "app.loading" : "square.addToPlan")}
      </button>

      <Drawer
        open={phase !== "idle" && phase !== "checking"}
        onClose={() => setPhase("idle")}
        title={t("square.addToPlan")}
      >
        <h2 className="t-title text-fg">{t("square.addToPlan")}</h2>
        <p className="t-body mt-1 text-fg-muted">
          {localized(opportunity.title_localized, locale) || opportunity.title}
        </p>
        <p className="t-mono mt-1 text-fg-faint">
          {slot.start.slice(0, 16).replace("T", " ")} →{" "}
          {slot.end.slice(11, 16)}
          {assumed ? ` · ${t("square.slotAssumed")}` : ""}
        </p>
        {longRunning && (
          <p className="t-meta mt-2 text-fg-muted" data-long-running>
            {t("square.longRunning")}
          </p>
        )}

        {/* ── 冲突高亮 ─────────────────────────────────────── */}
        {conflicts.length > 0 && (
          <ul className="mt-5 flex flex-col gap-2" data-schedule-conflicts>
            {conflicts.map((conflict, index) => (
              <motion.li
                key={index}
                data-conflict-blocking={String(conflict.blocking)}
                className="rounded-md p-3"
                initial={reduce ? { opacity: 0 } : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={
                  reduce
                    ? { duration: 0.12 }
                    : { type: "spring", bounce: 0, duration: 0.34, delay: index * 0.04 }
                }
                style={{
                  border: `1px solid ${conflict.blocking ? "var(--color-clay-500)" : "var(--hatch)"}`,
                  background: conflict.blocking
                    ? "var(--color-clay-100)"
                    : "color-mix(in srgb, var(--hatch) 8%, transparent)",
                  color: conflict.blocking
                    ? "var(--color-clay-600)"
                    : "var(--hatch-ink)",
                }}
              >
                <div className="t-micro">
                  {t(
                    conflict.blocking
                      ? "actions.conflict.blocking"
                      : "square.conflict.soft",
                  )}
                </div>
                <p className="t-meta mt-1">{localized(conflict.detail, locale)}</p>
              </motion.li>
            ))}
          </ul>
        )}

        {conflicts.length === 0 && phase === "review" && (
          <p className="t-meta mt-5 text-fg-muted" data-no-conflicts>
            {t("square.noConflicts")}
          </p>
        )}

        {/* ── 由学生决定要不要重排 ─────────────────────────── */}
        {phase === "review" && (
          <div className="mt-6">
            <p className="t-meta mb-3 max-w-[52ch] text-fg-muted">
              {t("square.replan.explain")}
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-add-without-replan
                disabled={blocking.length > 0}
                onClick={() => confirmAdd(false)}
                className="pressable btn btn-secondary t-meta disabled:opacity-40"
              >
                {t("square.addOnly")}
              </button>
              <button
                type="button"
                data-add-with-replan
                disabled={blocking.length > 0}
                onClick={() => confirmAdd(true)}
                className="pressable btn btn-primary t-meta font-medium disabled:opacity-40"
              >
                {t("square.addAndReplan")}
              </button>
            </div>
            {blocking.length > 0 && (
              <p
                className="t-meta mt-3"
                data-blocked-by-protected
                style={{ color: "var(--color-clay-600)" }}
              >
                {t("square.blockedByProtected")}
              </p>
            )}
          </div>
        )}

        {/* ── 重排范围：只算了会动哪些，还没动 ─────────────── */}
        {phase === "done" && (
          <div className="mt-6" data-replan-result>
            <p className="t-body text-fg">{t("square.added")}</p>
            <a
              href="/actions"
              data-goto-actions
              className="t-meta mt-2 inline-block underline"
              style={{ color: "var(--accent-deep)" }}
            >
              {t("square.gotoActions")}
            </a>
            {scope && (
              <div className="mt-3 rounded-md border border-line bg-bg-sunk p-3">
                <div className="t-micro text-fg-faint">{t("square.replan.scope")}</div>
                <div className="t-meta mt-1 text-fg">
                  {t("square.replan.willMove")}: {scope.affected_plan_item_ids.length}
                  {" · "}
                  {t("square.replan.untouched")}:{" "}
                  {scope.unaffected_plan_item_ids.length}
                </div>
                {scope.rationale && (
                  <p className="t-meta mt-2 text-fg-muted">
                    {localized(scope.rationale, locale)}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {error && (
          <p className="t-mono mt-4 text-fg-faint" data-add-error>
            {error}
          </p>
        )}

        <button
          type="button"
          onClick={() => setPhase("idle")}
          className="pressable btn btn-secondary t-meta mt-6"
        >
          {t("square.whyNot.close")}
        </button>
      </Drawer>
    </>
  );
}
