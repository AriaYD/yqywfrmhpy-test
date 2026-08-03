"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized, type MessageKey } from "@/i18n";
import { api, type WellbeingCapacitySignal } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Bar,
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
 * 全链零 LLM 的那一页。
 *
 * 页面上的每一句话要么来自 i18n 资源，要么来自后端的固定模板；
 * 数字来自阈值运算。**没有任何一段文案是模型生成的**，
 * 也因此"不代表任何医学诊断"这句免责声明 100% 出现——
 * 它不依赖模型记得说。
 */
const SIGNAL_KEY: Record<string, MessageKey> = {
  sleep_opportunity_compressed: "wellbeing.signal.sleep",
  self_reported_short_sleep: "wellbeing.signal.continuous",
  activity_opportunity_low: "wellbeing.signal.abandon",
  recovery_block_absent: "wellbeing.signal.recovery",
  capacity_overload: "wellbeing.signal.overload",
};

/** severity 是三档，不是布尔。`info` 是"记一笔"，不是"出事了"。 */
const SEVERITY_KEY: Record<string, MessageKey> = {
  info: "wellbeing.severity.info",
  attention: "wellbeing.severity.attention",
  blocking: "wellbeing.severity.blocking",
};

export default function WellbeingPage() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [requested, setRequested] = useState(false);
  const [outreachError, setOutreachError] = useState<string | null>(null);

  /**
   * **真的调端点，不是置个本地 state。**
   *
   * 这个按钮之前只把 `requested` 设成 true——界面显示"请求已记录"，
   * 而实际上什么都没发生。那比按钮坏掉更糟：学生以为自己求助了。
   *
   * 服务端会验同意（B13）：没有有效同意直接 403，界面照实说，
   * 不把它伪装成成功。
   */
  // 用契约自己的联合类型，不要 string——枚举值猜错在这个项目里已经栽过三次
  type SignalType = WellbeingCapacitySignal["signal_type"];

  async function askForOutreach(signalType: SignalType) {
    setOutreachError(null);
    try {
      const now = new Date().toISOString();
      await api.requestOutreach(studentId, {
        request_id: `REQ-${studentId}-${Date.now()}`,
        // R8-2：同意按学生 seed——写死 CONSENT-DEMO 时只有 STU-B 能按这个按钮
        consent_id: `CONSENT-DEMO-${studentId}`,
        student_id: studentId,
        trigger_category: signalType,
        email_fields: {
          internal_student_ref: `ref-${studentId}`,
          student_requested_contact: true,
          trigger_category: signalType,
          triggered_at: now,
          consent_receipt_id: `CONSENT-DEMO-${studentId}`,
          acknowledgement_url: "https://example.invalid/ack",
        },
        requested_at: now,
        delivery_status: "queued",
        // 这两项在契约里必填且**必须为空**：谁接手、怎么处理，
        // 由 Counseling 那边填，学生这一侧无权预设。
        disposition: null,
        human_owner: null,
      });
      setRequested(true);
    } catch (err) {
      setOutreachError((err as Error).message);
    }
  }

  const signals = useResource(() => api.wellbeingSignals(studentId), [studentId]);
  const reminders = useResource(
    () => api.wellbeingReminders(studentId), [studentId],
  );
  // 「睡眠-负荷平衡」周合计（2026-08-02 用户裁定）：审计红-6 修正——
  // 不再取「最近 7 个有数据的日子」（会被未来已批准活动块拉飞），改锚定
  // **最近登记睡眠所在的周一对齐整周**，与日历页同一种「整周」语义；
  // 统计周范围随卡片明示。该周无块则显示无数据态，不冒充 0.0。
  const availability = useResource(() => api.availability(studentId), [studentId]);
  const weekStats = (() => {
    const rows = availability.data ?? [];
    if (!rows.length) return null;
    const sleepDays = rows
      .filter((b) => b.block_id.includes("sleep"))
      .map((b) => b.span.start.slice(0, 10));
    const daysAll = [...new Set(rows.map((b) => b.span.start.slice(0, 10)))].sort();
    const anchorStr = sleepDays.length ? sleepDays.sort().at(-1)! : daysAll.at(-1)!;
    const anchor = new Date(`${anchorStr}T00:00:00`);
    const monday = new Date(anchor);
    monday.setDate(anchor.getDate() - ((anchor.getDay() + 6) % 7));
    // 审查 M8：用本地日期格式化——toISOString 会转 UTC，在 UTC+ 时区
    // 整周前移一天（周日起），与「周一对齐」的口径矛盾
    const localYmd = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const week = new Set(
      Array.from({ length: 7 }, (_, i) => {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        return localYmd(d);
      }),
    );
    const weekLabel = `${[...week].sort()[0]} → ${[...week].sort().at(-1)}`;
    if (!rows.some((b) => week.has(b.span.start.slice(0, 10)))) return null;
    const hoursOf = (b: (typeof rows)[number]) => {
      const ms = new Date(b.span.end).getTime() - new Date(b.span.start).getTime();
      return (ms > 0 ? ms : ms + 86_400_000) / 3_600_000;
    };
    let sleep = 0, course = 0, busy = 0, buffer = 0, flexible = 0, prot = 0;
    for (const b of rows) {
      if (!week.has(b.span.start.slice(0, 10))) continue;
      const dur = hoursOf(b);
      if (b.block_id.includes("sleep")) sleep += dur;
      else if ((b as { source?: string }).source === "course_timetable") course += dur;
      else if (b.type === "busy") busy += dur;
      else if (b.type === "buffer") buffer += dur;
      else if (b.type === "flexible") flexible += dur;
      else if (b.type === "protected") prot += dur;
    }
    const disposable =
      168 - sleep - course - busy - flexible - buffer - prot - 24.5;
    return { sleep, course, busy, buffer, disposable, weekLabel,
             scheduledRatio: (busy + course) / 66 };
  })();

  return (
    <>
      <PageHeader titleKey="wellbeing.title" leadKey="wellbeing.lead">
        <span
          className="t-micro inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
          data-zero-llm
          style={{
            border: "1px solid var(--color-moss-500)",
            color: "var(--color-moss-600)",
            background: "var(--color-moss-100)",
          }}
          title={t("wellbeing.noLLM.explain")}
        >
          {t("wellbeing.noLLM")}
        </span>
      </PageHeader>

      {/* 2026-08-02 用户裁定：容量模块改为「睡眠-负荷平衡」周合计五项 +
          已安排率（(忙+课程)/66，11h×6 天硬上限）——取代原容量超载卡的
          缓冲比口径。数字来自日历原始块的算术，零 LLM。 */}
      {weekStats && (
        <Card className="mb-3" data-balance-card>
          <SectionTitle>{t("wellbeing.balance.title")}</SectionTitle>
          {/* 审计红-6：统计周范围明示——与日历页「当前显示周」区分口径 */}
          <p className="t-micro text-fg-muted" data-balance-week>
            {t("wellbeing.balance.week")}: {weekStats.weekLabel}
          </p>
          <Grid min={150}>
            <Metric label={t("calendar.week.sleep")}
                    value={weekStats.sleep.toFixed(1)} unit={t("calendar.hours")}
                    tone={weekStats.sleep >= 49 ? "good" : "default"} />
            <Metric label={t("calendar.week.course")}
                    value={weekStats.course.toFixed(1)} unit={t("calendar.hours")} />
            <Metric label={t("calendar.week.busy")}
                    value={weekStats.busy.toFixed(1)} unit={t("calendar.hours")} />
            <Metric label={t("calendar.week.disposable")}
                    value={weekStats.disposable.toFixed(1)} unit={t("calendar.hours")}
                    tone={weekStats.disposable < 0 ? "warn" : "good"} />
            <Metric label={t("calendar.week.buffer")}
                    value={weekStats.buffer.toFixed(1)} unit={t("calendar.hours")} />
          </Grid>
          <div className="mt-4">
            <div className="t-micro mb-1.5 flex justify-between text-fg-faint">
              <span>{t("wellbeing.balance.scheduled")}</span>
              <span className="tabular-nums">
                {(weekStats.busy + weekStats.course).toFixed(1)} / 66
              </span>
            </div>
            <Bar ratio={Math.min(1, weekStats.scheduledRatio)}
                 tone={weekStats.scheduledRatio > 1 ? "warn" : "accent"} />
          </div>
          <p className="t-micro mt-2 text-fg-faint" data-balance-method>
            {t("calendar.week.method")}
          </p>
        </Card>
      )}

      {signals.loading && <Loading />}
      {signals.error && <Failure error={signals.error} onRetry={signals.reload} />}
      {signals.data?.length === 0 && <Empty />}
      {/* 容量超载已由上方平衡卡承载；其余信号无数据时如实说明，不装看板 */}
      {signals.data &&
        signals.data.filter((s) => s.signal_type !== "capacity_overload")
          .length === 0 && (
        <p className="t-meta mb-3 text-fg-faint" data-signals-pending-note>
          {t("wellbeing.signalsPending")}
        </p>
      )}

      <ul className="flex flex-col gap-3">
        {signals.data?.filter((s) => s.signal_type !== "capacity_overload")
          .map((signal) => {
          // observed_value / reference_line 是**模板填出来的文字**，不是数字。
          // 后端刻意这么做：五个信号的量纲各不相同，硬凑成一个百分比
          // 会得到一个看起来精确、其实没有含义的数。这里照原样呈现。
          const triggered = signal.severity !== "info";
          const coverage =
            signal.data_coverage.window_days > 0
              ? signal.data_coverage.days_with_data /
                signal.data_coverage.window_days
              : 0;
          return (
            <Card key={signal.signal_id} as="li">
              <div
                data-signal={signal.signal_type}
                data-signal-triggered={triggered ? "true" : "false"}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="t-section text-fg">
                    {t(SIGNAL_KEY[signal.signal_type] ?? "wellbeing.signal.overload")}
                  </span>
                  <span
                    className="t-meta rounded-sm px-2 py-1"
                    style={{
                      border: `1px solid ${triggered ? "var(--color-clay-500)" : "var(--color-moss-500)"}`,
                      color: triggered
                        ? "var(--color-clay-600)"
                        : "var(--color-moss-600)",
                      background: triggered
                        ? "var(--color-clay-100)"
                        : "var(--color-moss-100)",
                    }}
                  >
                    {t(SEVERITY_KEY[signal.severity] ?? "wellbeing.severity.info")}
                  </span>
                </div>

                <dl className="mt-3 flex flex-col gap-1.5">
                  <div className="flex gap-2">
                    <dt className="t-micro shrink-0 pt-0.5 text-fg-faint">
                      {t("wellbeing.observed")}
                    </dt>
                    <dd className="t-meta text-fg">
                      {localized(signal.observed_value, locale)}
                    </dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="t-micro shrink-0 pt-0.5 text-fg-faint">
                      {t("wellbeing.threshold")}
                    </dt>
                    <dd className="t-meta text-fg-muted">
                      {localized(signal.reference_line, locale)}
                    </dd>
                  </div>
                </dl>

                <div className="mt-4">
                  <div className="t-micro mb-1.5 flex justify-between text-fg-faint">
                    <span>{t("wellbeing.coverage")}</span>
                    <span className="tabular-nums">
                      {signal.data_coverage.days_with_data}/
                      {signal.data_coverage.window_days}
                    </span>
                  </div>
                  {/* 覆盖率单独画：数据只覆盖了 2/7 天的"结论"和覆盖 7/7 的
                      不该看起来一样有分量 */}
                  <Bar ratio={coverage} tone={triggered ? "warn" : "accent"} />
                </div>

                <div className="t-mono mt-3 text-fg-faint">
                  {signal.rule_id} · {signal.period_start} → {signal.period_end}
                </div>
              </div>
            </Card>
          );
        })}
      </ul>

      {/* ── 两次提醒状态机（§16.8.3）───────────────────────────
          **上限就是两次。** 界面把"已发几次、还会不会再发"直接说出来，
          因为学生有权知道这套东西会不会一直找他。 */}
      <Card className="mt-5">
        <SectionTitle>{t("wellbeing.reminder")}</SectionTitle>
        {reminders.loading && <Loading />}
        {reminders.error && <Failure error={reminders.error} />}
        {reminders.data?.length === 0 && (
          <Empty messageKey="wellbeing.reminder.none" />
        )}
        <ul className="flex flex-col gap-2" data-reminders>
          {reminders.data?.map((reminder) => (
            <li
              key={reminder.reminder_id}
              data-reminder={reminder.reminder_number}
              data-low-load={String(reminder.low_load_mode)}
              className="rounded-md border border-line bg-bg-sunk p-3"
            >
              <div className="t-meta flex flex-wrap items-center gap-2 text-fg">
                <span>
                  {t(
                    reminder.reminder_number === 1
                      ? "wellbeing.reminder.first"
                      : "wellbeing.reminder.second",
                  )}
                </span>
                {reminder.low_load_mode && (
                  <span
                    className="t-micro rounded-sm px-1.5 py-0.5"
                    style={{
                      border: "1px solid var(--accent)",
                      color: "var(--accent-deep)",
                    }}
                  >
                    {t("wellbeing.reminder.lowLoad")}
                  </span>
                )}
              </div>
              <div className="t-mono mt-1 text-fg-faint">
                {reminder.delivered_at.slice(0, 16).replace("T", " ")}
                {reminder.reevaluate_after
                  ? ` · ${t("wellbeing.reminder.reevaluate")} ${reminder.reevaluate_after.slice(0, 16).replace("T", " ")}`
                  : ""}
              </div>
            </li>
          ))}
        </ul>
        {(reminders.data?.length ?? 0) >= 2 && (
          <p className="t-meta mt-3 text-fg-muted" data-reminder-capped>
            {t("wellbeing.reminder.capped")}
          </p>
        )}
      </Card>

      {/* 免责声明来自 i18n 常量，不来自任何生成过程 */}
      <p className="t-meta mt-5 text-fg-faint" data-wellbeing-disclaimer>
        {t("wellbeing.disclaimer")}
      </p>

      {/* R5-E：升级判定 + ISI/PSS-10 两层自评（零 LLM；外联仍需学生确认） */}
      <AssessmentCard studentId={studentId} />

      <Card className="mt-5">
        <SectionTitle>{t("wellbeing.outreach")}</SectionTitle>
        <p className="t-meta mb-4 max-w-[60ch] text-fg-muted">
          {t("wellbeing.outreach.explain")}
        </p>
        <div className="flex items-center gap-3">
          <button
            type="button"
            data-outreach-request
            onClick={() =>
              askForOutreach(signals.data?.[0]?.signal_type ?? "capacity_overload")
            }
            className="pressable btn btn-primary t-body font-medium"
          >
            {t("wellbeing.outreach")}
          </button>
          {requested && (
            <span className="t-meta text-fg-muted" data-outreach-sent>
              {t("wellbeing.outreach.sent")}
            </span>
          )}
          {outreachError && (
            <span
              className="t-mono"
              data-outreach-error
              style={{ color: "var(--color-clay-600)" }}
            >
              {outreachError}
            </span>
          )}
        </div>
      </Card>

      {/* 紧急求助沉底（用户裁定 2026-08-01）：它是最后的兜底通道，
          不该插在自评与常规外联之间打断阅读序。 */}
      <EmergencyCard studentId={studentId} />
    </>
  );
}


/** R5-E：升级判定卡 + ISI / PSS-10 自评。计分与分流全在服务端（零 LLM）。 */
function AssessmentCard({ studentId }: { studentId: string }) {
  const { t, locale } = useI18n();
  const escalation = useResource(
    () => api.wellbeingEscalation(studentId),
    [studentId],
  );
  const [open, setOpen] = useState(false);
  const [isi, setIsi] = useState<number[]>(Array(7).fill(0));
  const [pss, setPss] = useState<number[]>(Array(10).fill(0));
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof api.wellbeingAssessment>
  > | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "error">("idle");

  async function submit() {
    setState("saving");
    try {
      setResult(await api.wellbeingAssessment(studentId, {
        student_id: studentId,
        isi_answers: isi,
        pss10_answers: pss,
      }));
      setState("idle");
    } catch {
      setState("error");
    }
  }

  const scaleRow = (
    label: string, value: number, onPick: (v: number) => void, tag: string,
  ) => (
    <div key={tag} className="flex flex-wrap items-center justify-between gap-2 py-1.5"
         data-scale-item={tag}>
      <span className="t-meta max-w-[46ch] text-fg">{label}</span>
      <span className="flex gap-1">
        {[0, 1, 2, 3, 4].map((v) => (
          <button
            key={v} type="button" data-scale-pick={`${tag}-${v}`}
            aria-pressed={value === v}
            onClick={() => onPick(v)}
            className="pressable t-meta h-8 w-8 rounded-sm border tabular-nums"
            style={{
              borderColor: value === v ? "var(--accent)" : "var(--line)",
              background: value === v ? "var(--accent-deep)" : "transparent",
              color: value === v ? "var(--accent-fg)" : "var(--fg-muted)",
            }}
          >
            {v}
          </button>
        ))}
      </span>
    </div>
  );

  return (
    <Card className="mt-5" data-assessment-card>
      <SectionTitle>{t("wellbeing.assess.title")}</SectionTitle>
      {escalation.data && (
        <div className="t-meta mb-2 text-fg-muted" data-escalation-tier={escalation.data.tier}>
          {t(`wellbeing.assess.tier.${escalation.data.tier}` as Parameters<typeof t>[0])}
          {escalation.data.declared_sleep_hours === null && (
            <span className="t-micro ms-2 text-fg-faint">
              {t("wellbeing.assess.noSleepWindow")}
            </span>
          )}
        </div>
      )}
      <p className="t-meta mb-3 max-w-[70ch] text-fg-muted">
        {t("wellbeing.assess.lead")}
      </p>
      {!open ? (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button" data-assessment-start
            onClick={() => setOpen(true)}
            className="pressable btn btn-primary t-meta font-medium"
          >
            {t("wellbeing.assess.start")}
          </button>
          {/* R8-3 触发面之一：睡够 10h 仍极度疲惫——自报即评估（不推断） */}
          <button
            type="button" data-fatigue-selfreport
            onClick={() => setOpen(true)}
            className="pressable btn btn-secondary t-meta"
          >
            {t("wellbeing.assess.fatigueSelfReport")}
          </button>
        </div>
      ) : (
        <div data-assessment-form>
          <div className="t-body mt-2 font-medium text-fg">ISI</div>
          <p className="t-micro mb-1 text-fg-faint">{t("wellbeing.assess.isiScale")}</p>
          {Array.from({ length: 7 }, (_, i) =>
            scaleRow(t(`wellbeing.isi.q${i + 1}` as Parameters<typeof t>[0]),
                     isi[i],
                     (v) => setIsi((prev) => prev.map((x, j) => (j === i ? v : x))),
                     `isi-${i + 1}`))}
          <div className="t-body mt-4 font-medium text-fg">PSS-10</div>
          <p className="t-micro mb-1 text-fg-faint">{t("wellbeing.assess.pssScale")}</p>
          {Array.from({ length: 10 }, (_, i) =>
            scaleRow(t(`wellbeing.pss.q${i + 1}` as Parameters<typeof t>[0]),
                     pss[i],
                     (v) => setPss((prev) => prev.map((x, j) => (j === i ? v : x))),
                     `pss-${i + 1}`))}
          <button
            type="button" data-assessment-submit
            disabled={state === "saving"}
            onClick={submit}
            className="pressable btn btn-primary t-meta mt-4 font-medium disabled:opacity-50"
          >
            {t("wellbeing.assess.submit")}
          </button>
          {state === "error" && (
            <span className="t-meta ms-3" style={{ color: "var(--color-clay-600)" }}>
              {t("app.error")}
            </span>
          )}
        </div>
      )}

      {result && (
        <div className="mt-4 rounded-md border border-line bg-bg-sunk p-3.5"
             data-assessment-result data-assessment-routing={result.routing}>
          <div className="t-body text-fg">
            ISI {result.isi_score}/28（{t(`wellbeing.isi.band.${result.isi_band}` as Parameters<typeof t>[0])}）
            · PSS-10 {result.pss10_score}/40（{t(`wellbeing.pss.band.${result.pss10_band}` as Parameters<typeof t>[0])}）
          </div>
          <p className="t-meta mt-2 text-fg" data-routing-copy>
            {t(`wellbeing.assess.route.${result.routing}` as Parameters<typeof t>[0])}
            {result.recommended_contact_name ? `：${result.recommended_contact_name}` : ""}
          </p>
          {/* R8-3 第一层：系统已自动联系自填 tutor（提交量表即知情动作） */}
          {result.auto_contact_sent && (
            <p className="t-meta mt-2 rounded-sm p-2.5"
               data-auto-contacted={result.auto_contact_email ?? ""}
               style={{ border: "1px solid var(--color-moss-500)",
                        color: "var(--color-moss-600)",
                        background: "var(--color-moss-100)" }}>
              {t("wellbeing.assess.autoContacted")} {result.auto_contact_email}
            </p>
          )}
          {/* R8-3 第二层：重度失眠 + 高压力 → 自选时段预约心理咨询 */}
          {result.routing === "counseling_center" && (
            <CounselingBookingPanel studentId={studentId} />
          )}
          <p className="t-micro mt-2 text-fg-faint">
            {localized(result.disclaimer, locale)}
          </p>
        </div>
      )}
    </Card>
  );
}

/**
 * R8-3 第二层预约面板。时段**只**来自校方 wellbeing-desk 开放的工作时段；
 * 专业与年级由服务端从 Profile 回填，这里只收学生自填的姓名/班级/联系方式。
 */
function CounselingBookingPanel({ studentId }: { studentId: string }) {
  const { t } = useI18n();
  const slots = useResource(() => api.counselingSlots(), [studentId]);
  const [slotId, setSlotId] = useState<string | null>(null);
  const [name, setName] = useState(`${studentId} (Synthetic)`);
  const [classLabel, setClassLabel] = useState("");
  const [contact, setContact] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function book() {
    if (!slotId || !name.trim() || !contact.trim()) {
      setError(t("wellbeing.booking.missing"));
      return;
    }
    setError(null);
    try {
      const saved = await api.bookCounseling(studentId, {
        booking_id: `CB-${studentId}-${Date.now()}`,
        student_id: studentId,
        slot_id: slotId,
        student_name: name,
        program: "pending", // 服务端回填
        year: 1,            // 服务端回填
        class_label: classLabel || null,
        contact,
        created_at: new Date().toISOString(),
      });
      setDone(`${saved.slot_id}`);
      slots.reload();
    } catch (err) {
      setError((err as Error).message);
      slots.reload();
    }
  }

  const inputCls = "field t-meta px-2.5 py-1.5";
  const open = (slots.data ?? []).filter((s) => !s.booked).slice(0, 8);

  return (
    <div className="mt-3 rounded-md border p-3"
         data-counseling-booking
         style={{ borderColor: "var(--accent)" }}>
      <p className="t-body font-medium text-fg">{t("wellbeing.booking.title")}</p>
      <p className="t-micro mt-1 text-fg-faint">{t("wellbeing.booking.lead")}</p>
      {done ? (
        <p className="t-meta mt-2" data-booking-done
           style={{ color: "var(--color-moss-600)" }}>
          {t("wellbeing.booking.done")} · {done}
        </p>
      ) : (
        <>
          <div className="mt-2 flex flex-wrap gap-1.5" data-slot-options>
            {open.map((slot) => (
              <button key={slot.slot_id} type="button"
                data-counseling-slot={slot.slot_id}
                aria-pressed={slotId === slot.slot_id}
                onClick={() => setSlotId(slot.slot_id)}
                className="pressable t-micro rounded-sm border px-2 py-1 tabular-nums"
                style={{
                  borderColor: slotId === slot.slot_id ? "var(--accent)" : "var(--line)",
                  background: slotId === slot.slot_id ? "var(--accent-soft)" : "transparent",
                  color: "var(--fg-muted)",
                }}>
                {slot.start.slice(5, 10)} {slot.start.slice(11, 16)}
              </button>
            ))}
            {open.length === 0 && !slots.loading && (
              <span className="t-meta text-fg-muted">{t("wellbeing.booking.noSlots")}</span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <input type="text" data-booking-name value={name}
              placeholder={t("wellbeing.booking.name")}
              onChange={(e) => setName(e.target.value)} className={inputCls} />
            <input type="text" data-booking-class value={classLabel}
              placeholder={t("wellbeing.booking.classLabel")}
              onChange={(e) => setClassLabel(e.target.value)} className={inputCls} />
            <input type="text" data-booking-contact value={contact}
              placeholder={t("wellbeing.booking.contact")}
              onChange={(e) => setContact(e.target.value)} className={inputCls} />
            <button type="button" data-booking-submit onClick={book}
              className="pressable btn btn-primary t-meta font-medium">
              {t("wellbeing.booking.submit")}
            </button>
          </div>
          {error && (
            <p className="t-meta mt-2" data-booking-error
               style={{ color: "var(--color-clay-600)" }}>{error}</p>
          )}
        </>
      )}
    </div>
  );
}

/**
 * R8-3 第三层：紧急红按钮。跳过一切排队直连值班室电话；
 * 每学期 2 次，第 3 次起停用一学期——但拒绝信息里仍带校园热线。
 */
function EmergencyCard({ studentId }: { studentId: string }) {
  const { t, locale } = useI18n();
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof api.emergencyAccess>> | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function press() {
    // 审查修复：双击=烧掉整学期 2 次配额——in-flight 期间必须禁用
    if (pending) return;
    setPending(true);
    setBlocked(null);
    try {
      setResult(await api.emergencyAccess(studentId));
    } catch (err) {
      setResult(null);
      // 拉黑响应里带校园热线——安全底线：挡特权不挡求助信息，
      // 所以要把服务端 detail 原文亮出来，不能只给 "403"
      const body = (err as { body?: { detail?: { detail?: string } } }).body;
      setBlocked(body?.detail?.detail ?? (err as Error).message);
    } finally {
      setPending(false);
    }
  }

  return (
    <Card className="mt-5" data-emergency-card>
      <SectionTitle>{t("wellbeing.emergency.title")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[70ch] text-fg-muted">
        {t("wellbeing.emergency.lead")}
      </p>
      <button type="button" data-emergency-press onClick={press}
        disabled={pending}
        className="pressable t-body rounded-md px-5 py-2.5 font-semibold disabled:opacity-60"
        style={{ background: "var(--color-clay-600)", color: "var(--color-clay-100)" }}>
        {t("wellbeing.emergency.button")}
      </button>
      {result && (
        <div className="t-body mt-3 rounded-md p-3" data-emergency-result
             style={{ border: "1px solid var(--color-clay-500)",
                      background: "var(--color-clay-100)",
                      color: "var(--color-clay-600)" }}>
          <strong data-duty-phone>{result.duty_phone}</strong>
          <p className="t-meta mt-1">{localized(result.note, locale)}</p>
          <p className="t-micro mt-1">
            {t("wellbeing.emergency.uses")}: {result.uses_this_term} / 2
          </p>
        </div>
      )}
      {blocked && (
        <p className="t-meta mt-3 rounded-md p-3" data-emergency-blocked
           style={{ border: "1px solid var(--color-clay-500)",
                    color: "var(--color-clay-600)" }}>
          {blocked}
        </p>
      )}
    </Card>
  );
}
