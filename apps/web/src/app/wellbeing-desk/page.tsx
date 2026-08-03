"use client";

import { useEffect, useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n } from "@/i18n";
import { institution, type Schemas } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Card, Failure, Loading, PageHeader, SectionTitle } from "@/components/ui";

/**
 * 心理咨询室工作台（R7-A）。wellbeing_coordinator 是**学校心理咨询室部门**——
 * 此前这个岗位登录后连一个自己的页面都没有，落在投稿台上。
 *
 * 这一页只做一件事：呈现 outreach 队列（B13——每一封都出自学生本人
 * 一键确认的外联请求，带同意回执）。队列端点被 RBAC 独占给本岗位：
 * Career Center 与 advisor 访问同一路径都是 403（console 的隔离探针
 * 从对面验证这一点）。
 *
 * **全链零 LLM**：这里显示的触发分类来自 Rules 阈值，文案是固定模板。
 */
export default function WellbeingDeskPage() {
  const { t } = useI18n();
  const { role } = useRole();
  const queue = useResource(() => institution.outreachQueue(), [role]);

  return (
    <>
      <PageHeader titleKey="wellbeingDesk.title" leadKey="wellbeingDesk.lead">
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

      {/* R8-3：工作时段设置——学生端可预约时段的唯一来源 */}
      <HoursCard />

      {/* R8-3：第二层分流的预约队列（姓名/专业/年级/班级/联系方式） */}
      <BookingsCard />

      <Card>
        <SectionTitle>{t("wellbeingDesk.queue")}</SectionTitle>
        <p className="t-meta mb-4 max-w-[64ch] text-fg-muted">
          {t("wellbeingDesk.queue.explain")}
        </p>
        {queue.loading && <Loading />}
        {queue.error && <Failure error={queue.error} onRetry={queue.reload} />}
        {queue.data?.length === 0 && (
          <p className="t-meta text-fg-muted" data-outreach-empty>
            {t("wellbeingDesk.empty")}
          </p>
        )}
        <ul className="flex flex-col gap-3" data-outreach-queue>
          {queue.data?.map((request) => (
            <li
              key={request.request_id}
              data-outreach-item={request.request_id}
              className="rounded-md border border-line bg-bg-sunk p-4"
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="t-section text-fg">{request.student_id}</span>
                <span className="t-micro rounded-sm border border-line px-2 py-0.5 text-fg-faint">
                  {request.trigger_category}
                </span>
              </div>
              <div className="t-meta mt-2 flex flex-col gap-1 text-fg-muted">
                <span data-outreach-consent className="t-mono">
                  {t("wellbeingDesk.consentReceipt")}: {request.consent_id}
                </span>
                <span>
                  {t("wellbeingDesk.requestedAt")}:{" "}
                  {new Date(request.requested_at).toLocaleString()}
                </span>
                <span data-outreach-confirmed>
                  {request.email_fields.student_requested_contact
                    ? t("wellbeingDesk.studentConfirmed")
                    : t("wellbeingDesk.notConfirmed")}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}

type CounselingHours = Schemas["CounselingHours"];

/**
 * R8-3：咨询室工作时段设置。这里开放什么，学生端就只能约什么——
 * 时段生成在服务端，从这份配置出发，前端两侧都无权虚构。
 */
function HoursCard() {
  const { t } = useI18n();
  const hours = useResource(() => institution.counselingHours(), []);
  const [draft, setDraft] = useState<CounselingHours | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");

  useEffect(() => {
    if (hours.data && draft === null) setDraft(hours.data);
  }, [hours.data, draft]);

  if (!draft) {
    return (
      <Card className="mb-5" data-hours-card>
        <SectionTitle>{t("wellbeingDesk.hours")}</SectionTitle>
        {hours.loading && <Loading />}
        {hours.error && <Failure error={hours.error} onRetry={hours.reload} />}
      </Card>
    );
  }

  const inputCls = "field t-meta px-1.5 py-1";
  const setWindow = (
    index: number, field: "weekday" | "start" | "end", value: string,
  ) =>
    setDraft({
      ...draft,
      windows: draft.windows.map((w, i) =>
        i === index
          ? { ...w, [field]: field === "weekday" ? Number(value) : value }
          : w),
    });

  async function save() {
    if (!draft) return;
    setState("saving");
    try {
      await institution.setCounselingHours(draft);
      setState("done");
      hours.reload();
    } catch {
      setState("error");
    }
  }

  return (
    <Card className="mb-5" data-hours-card>
      <SectionTitle>{t("wellbeingDesk.hours")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[64ch] text-fg-muted">
        {t("wellbeingDesk.hours.lead")}
      </p>
      <ul className="flex flex-col gap-1.5">
        {draft.windows.map((w, index) => (
          <li key={index} className="flex flex-wrap items-center gap-1.5"
              data-hours-row={index}>
            <select value={w.weekday} data-hours-weekday={index}
              onChange={(e) => setWindow(index, "weekday", e.target.value)}
              className={inputCls}>
              {Array.from({ length: 7 }, (_, d) => (
                <option key={d} value={d}>
                  {t(`wellbeingDesk.weekday.${d}` as Parameters<typeof t>[0])}
                </option>
              ))}
            </select>
            <input type="time" value={w.start} data-hours-start={index}
              onChange={(e) => setWindow(index, "start", e.target.value)}
              className={inputCls} />
            –
            <input type="time" value={w.end} data-hours-end={index}
              onChange={(e) => setWindow(index, "end", e.target.value)}
              className={inputCls} />
            <button type="button" data-hours-remove={index}
              onClick={() => setDraft({
                ...draft,
                windows: draft.windows.filter((_, i) => i !== index),
              })}
              className="pressable t-meta text-fg-faint">×</button>
          </li>
        ))}
      </ul>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button type="button" data-hours-add
          onClick={() => setDraft({
            ...draft,
            windows: [...draft.windows,
                      { weekday: 0, start: "10:00", end: "12:00" }],
          })}
          className="pressable btn btn-secondary t-meta px-2.5 py-1">
          + {t("wellbeingDesk.hours.add")}
        </button>
        <label className="t-meta flex items-center gap-1.5 text-fg-muted">
          {t("wellbeingDesk.hours.slotMinutes")}
          <select value={draft.slot_minutes} data-hours-slot-minutes
            onChange={(e) =>
              setDraft({ ...draft, slot_minutes: Number(e.target.value) })}
            className={inputCls}>
            {[30, 45, 60].map((m) => <option key={m} value={m}>{m}</option>)}
          </select>
        </label>
        <button type="button" data-hours-save onClick={save}
          disabled={state === "saving" || draft.windows.length === 0}
          className="pressable btn btn-primary t-meta font-medium disabled:opacity-50">
          {t("wellbeingDesk.hours.save")}
        </button>
        {state === "done" && (
          <span className="t-meta" data-hours-saved
                style={{ color: "var(--color-moss-600)" }}>
            {t("wellbeingDesk.hours.saved")}
          </span>
        )}
        {state === "error" && (
          <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
            {t("app.error")}
          </span>
        )}
      </div>
    </Card>
  );
}

/** R8-3：第二层分流的预约队列。五项信息给咨询室，别处不可见。 */
function BookingsCard() {
  const { t } = useI18n();
  const bookings = useResource(() => institution.counselingBookings(), []);
  return (
    <Card className="mb-5" data-bookings-card>
      <SectionTitle>{t("wellbeingDesk.bookings")}</SectionTitle>
      {bookings.loading && <Loading />}
      {bookings.error && <Failure error={bookings.error} onRetry={bookings.reload} />}
      {bookings.data?.length === 0 && (
        <p className="t-meta text-fg-muted" data-bookings-empty>
          {t("wellbeingDesk.bookings.empty")}
        </p>
      )}
      <ul className="flex flex-col gap-2">
        {bookings.data?.map((booking) => (
          <li key={booking.booking_id}
              data-booking-item={booking.booking_id}
              className="rounded-md border border-line bg-bg-sunk p-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="t-body font-medium text-fg">
                {booking.student_name}
              </span>
              <span className="t-mono t-micro text-fg-faint">
                {booking.slot_id}
              </span>
            </div>
            <div className="t-meta mt-1 text-fg-muted">
              {booking.program} · {t("wellbeingDesk.bookings.year")}{booking.year}
              {booking.class_label ? ` · ${booking.class_label}` : ""} ·{" "}
              {booking.contact}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}
