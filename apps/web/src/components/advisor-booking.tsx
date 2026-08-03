"use client";

import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, type MessageKey } from "@/i18n";
import { api, ApiError, type Schemas } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Card, Empty, Loading, SectionTitle } from "@/components/ui";

type Advisor = Schemas["Advisor"];
type Slot = Advisor["slots"][number];

/**
 * Career Center Advisor 预约（Q，2026-07-31 从反思页挪到行动中心置顶）。
 *
 * 时段库存是实时的：被约走的时段不可选，取消（提前 ≥1 天）即释放。
 * 违约规则明示在面板上：预约必到；一学期爽约 3 次暂停预约资格。
 * 接入真实 Career Center 系统时，名录数据源替换，本面板不变。
 */
export function AdvisorBookingPanel() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  // 用户裁定（2026-08-01）：默认折叠成一行，点击标题行展开
  const [expanded, setExpanded] = useState(false);
  const directory = useResource(() => api.advisors(), []);
  const bookings = useResource(() => api.myAdvisorBookings(studentId), [studentId]);

  const [picked, setPicked] = useState<{ advisor: Advisor; slot: Slot } | null>(null);
  const [topic, setTopic] = useState("");
  const [note, setNote] = useState<
    "idle" | "sent" | "blocked" | "taken" | "blacklisted"
  >("idle");
  const [cancelNote, setCancelNote] = useState<string | null>(null);

  async function book() {
    if (!picked) return;
    setNote("idle");
    try {
      await api.bookAdvisor(studentId, {
        booking_id: `ADV-${studentId}-${Date.now()}`,
        student_id: studentId,
        advisor_id: picked.advisor.advisor_id,
        slot_id: picked.slot.slot_id,
        requested_slot: picked.slot.span,
        topic: topic.trim(),
        status: "requested",
        created_at: new Date().toISOString(),
        summary: null,
      });
      setNote("sent");
      setTopic("");
      setPicked(null);
      directory.reload();
      bookings.reload();
    } catch (err) {
      const detail =
        err instanceof ApiError &&
        typeof err.body === "object" &&
        err.body !== null
          ? (err.body as { detail?: { error?: string } }).detail?.error
          : undefined;
      if (detail === "slot_taken") {
        setNote("taken");
        directory.reload(); // 占用是实时的——把最新库存拉回来
      } else if (detail === "no_show_blacklisted") setNote("blacklisted");
      else setNote("blocked");
    }
  }

  async function cancel(bookingId: string) {
    setCancelNote(null);
    try {
      await api.cancelAdvisorBooking(studentId, bookingId);
      bookings.reload();
      directory.reload();
    } catch {
      // 不足 1 天：服务端拒绝并说明爽约后果——如实转述
      setCancelNote(t("advisor.cancelTooLate"));
    }
  }

  const fmt = (iso: string) =>
    new Date(iso).toLocaleString(locale, {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      timeZone: "UTC",
    });
  /** B9：预约按一小时时间段——显示区间，不显示孤零零的时间点。 */
  const fmtRange = (span: { start: string; end: string }) =>
    `${fmt(span.start)}–${new Date(span.end).toLocaleTimeString(locale, {
      hour: "2-digit", minute: "2-digit", timeZone: "UTC",
    })}`;

  return (
    <Card
      className="mb-5"
      data-advisor-booking-panel
      data-advisor-booking-expanded={expanded ? "true" : "false"}
    >
      <button
        type="button"
        data-advisor-booking-toggle
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="pressable -m-2 flex w-[calc(100%+1rem)] items-center justify-between gap-2 rounded-md p-2 text-start"
        style={{ background: expanded ? "transparent" : "var(--accent-soft)" }}
      >
        <span
          className="t-section"
          style={{ color: expanded ? "var(--fg)" : "var(--accent-deep)" }}
        >
          {t("advisor.collapsedTitle")}
        </span>
        <span
          aria-hidden
          className="t-meta text-fg-faint transition-transform duration-200"
          style={{ transform: expanded ? "rotate(90deg)" : "none" }}
        >
          ›
        </span>
      </button>
      {expanded && (
        <div className="mt-3">
      <p className="t-meta mb-1 max-w-[70ch] text-fg-muted">
        {t("advisor.sectionLead")}
      </p>
      <p
        className="t-meta mb-3 max-w-[70ch] rounded-md border p-2.5"
        data-advisor-policy
        style={{ borderColor: "var(--hatch)", color: "var(--fg-muted)" }}
      >
        {t("advisor.policy")}
      </p>

      {directory.loading && <Loading />}
      <div className="grid gap-3 lg:grid-cols-3">
        {(directory.data ?? []).map((advisor) => (
          <div
            key={advisor.advisor_id}
            data-advisor={advisor.advisor_id}
            className="rounded-md border border-line bg-bg-sunk p-3"
          >
            <div className="t-body font-medium text-fg">{advisor.name}</div>
            <div className="t-micro mt-0.5 text-fg-faint">{advisor.focus}</div>
            <div className="mt-2 flex max-h-[132px] flex-wrap gap-1 overflow-y-auto">
              {advisor.slots.map((slot) => {
                const active = picked?.slot.slot_id === slot.slot_id;
                return (
                  <button
                    key={slot.slot_id}
                    type="button"
                    data-slot={slot.slot_id}
                    data-slot-booked={slot.booked ? "true" : "false"}
                    disabled={slot.booked}
                    onClick={() => setPicked({ advisor, slot })}
                    className="pressable t-micro rounded-sm border px-1.5 py-0.5 disabled:cursor-not-allowed disabled:line-through disabled:opacity-40"
                    style={{
                      borderColor: active ? "var(--accent)" : "var(--line)",
                      background: active ? "var(--accent-deep)" : "transparent",
                      color: active ? "var(--accent-fg)" : "var(--fg-muted)",
                    }}
                  >
                    {fmtRange(slot.span)}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="block min-w-[240px] flex-1">
          <span className="t-micro block text-fg-faint">{t("advisor.topic")}</span>
          <input
            type="text"
            data-advisor-topic
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder={t("advisor.topicPlaceholder")}
            className="field t-meta mt-1 w-full"
          />
        </label>
        <button
          type="button"
          data-book-advisor
          disabled={!topic.trim() || !picked}
          onClick={book}
          className="pressable btn btn-primary t-meta font-medium disabled:opacity-40"
        >
          {picked
            ? `${t("advisor.book")} · ${fmtRange(picked.slot.span)}`
            : t("advisor.pickSlotFirst")}
        </button>
      </div>
      {note === "sent" && (
        <p className="t-meta mt-2" style={{ color: "var(--color-moss-600)" }} data-booking-sent>
          {t("advisor.booked")}
        </p>
      )}
      {note === "taken" && (
        <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }} data-booking-taken>
          {t("advisor.slotTaken")}
        </p>
      )}
      {note === "blacklisted" && (
        <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }} data-booking-blacklisted>
          {t("advisor.blacklisted")}
        </p>
      )}
      {note === "blocked" && (
        <p className="t-meta mt-2" style={{ color: "var(--hatch-ink)" }}>
          {t("advisor.notYet")}
        </p>
      )}

      <ul className="mt-4 flex flex-col gap-2" data-my-bookings>
        {(bookings.data ?? []).length === 0 && !bookings.loading && <Empty />}
        {(bookings.data ?? []).map((b) => (
          <li
            key={b.booking_id}
            className="rounded-md border border-line bg-bg-sunk p-3"
            data-my-booking={b.booking_id}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="t-body text-fg">{b.topic}</span>
              <span className="flex items-center gap-2">
                <span className="t-mono text-fg-faint">
                  {fmt(b.requested_slot.start)} ·{" "}
                  {t(`advisor.status.${b.status}` as MessageKey)}
                </span>
                {(b.status === "requested" || b.status === "confirmed") && (
                  <button
                    type="button"
                    data-cancel-booking={b.booking_id}
                    onClick={() => cancel(b.booking_id)}
                    className="pressable btn btn-danger t-micro"
                  >
                    {t("advisor.cancel")}
                  </button>
                )}
              </span>
            </div>
            {b.summary && (
              <div className="mt-2" data-advisor-advice>
                <div className="t-micro text-fg-faint">{t("advisor.adviceTitle")}</div>
                <ul className="mt-1 flex flex-col gap-1">
                  {b.summary.key_advice.map((line, index) => (
                    <li key={index} className="t-meta text-fg-muted">
                      · {line}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </li>
        ))}
      </ul>
      {cancelNote && (
        <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }} data-cancel-denied>
          {cancelNote}
        </p>
      )}
        </div>
      )}
    </Card>
  );
}
