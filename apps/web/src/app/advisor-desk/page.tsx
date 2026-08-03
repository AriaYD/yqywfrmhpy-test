"use client";

import { useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n } from "@/i18n";
import { api, institution, type Schemas } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Card, Empty, Failure, Loading, PageHeader, SectionTitle } from "@/components/ui";

/**
 * Advisor 工作台（校方门户）。Advisor 只见预约与学生想聊的主题——
 * 反思原文、成绩、日历对这个角色是 403，由契约生成的 RBAC 表保证。
 */
export default function AdvisorDeskPage() {
  const { t } = useI18n();
  const { role } = useRole();
  const queue = useResource(() => institution.advisorQueue(), [role]);
  const directory = useResource(() => api.advisors(), [role]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  /** B9（2026-08-01 用户裁定）：注册信息管理独立成分页。 */
  const [deskTab, setDeskTab] = useState<"desk" | "registry">("desk");

  const notAdvisor = role !== "advisor";

  return (
    <>
      <PageHeader titleKey="advisor.deskTitle" leadKey="advisor.deskLead" />

      {!notAdvisor && (
        <div
          className="mb-5 inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
          data-desk-tabs
        >
          {(["desk", "registry"] as const).map((tabKey) => (
            <button
              key={tabKey}
              type="button"
              data-desk-tab={tabKey}
              aria-pressed={deskTab === tabKey}
              onClick={() => setDeskTab(tabKey)}
              className="pressable t-meta rounded-sm px-3 py-1.5"
              style={{
                background: deskTab === tabKey ? "var(--accent-deep)" : "transparent",
                color: deskTab === tabKey ? "var(--accent-fg)" : "var(--fg-muted)",
                fontWeight: deskTab === tabKey ? 600 : 500,
              }}
            >
              {t(tabKey === "desk" ? "advisorDesk.tab.desk" : "advisorDesk.tab.registry")}
            </button>
          ))}
        </div>
      )}

      {notAdvisor && (
        <Card className="mb-5">
          <p className="t-body text-fg-muted" data-advisor-wrong-role>
            {t("advisor.wrongRole")}
          </p>
        </Card>
      )}

      {!notAdvisor && deskTab === "registry" && (
        <>
          {/* R8-1：Advisor 自助注册——顾问人员流动，名录不写死 */}
          <RegistrationCard onRegistered={() => directory.reload()} />

          {/* B9：已注册顾问的查看 / 编辑 / 删除 */}
          <RegistryCard
            advisors={directory.data ?? []}
            onChanged={() => directory.reload()}
          />
        </>
      )}

      {!notAdvisor && deskTab === "desk" && (
        <>
          {/* R8-1：时段管理——查看已被预约状态；标记"不在"的时段学生端不可见 */}
          <ScheduleCard
            advisors={directory.data ?? []}
            onChanged={() => directory.reload()}
          />

          {/* Q：时段占用统计——哪个顾问的哪些时段已被约走（占用实时，取消即释放） */}
          <Card className="mb-5" data-occupancy-stats>
            <SectionTitle>{t("advisor.occupancy")}</SectionTitle>
            {directory.loading && <Loading />}
            <div className="flex flex-wrap gap-6">
              {(directory.data ?? []).map((advisor) => {
                const total = advisor.slots.length;
                const booked = advisor.slots.filter((slot) => slot.booked).length;
                return (
                  <div key={advisor.advisor_id} data-occupancy={advisor.advisor_id}>
                    <div className="t-meta text-fg">{advisor.name}</div>
                    <div className="t-mono mt-0.5 text-fg-muted">
                      {booked} / {total}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>

          {queue.loading && <Loading />}
          {queue.error && <Failure error={queue.error} onRetry={queue.reload} />}
          {queue.data?.length === 0 && <Empty messageKey="advisor.queueEmpty" />}

          <ul className="flex flex-col gap-3">
            {queue.data?.map((booking) => (
              <Card key={booking.booking_id} as="li">
                <div data-booking={booking.booking_id}>
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="t-section text-fg">{booking.student_id}</span>
                    <span className="t-mono text-fg-faint">{booking.status}</span>
                  </div>
                  <div className="t-mono mt-1 text-fg-muted">
                    {booking.requested_slot.start.slice(0, 16)} →{" "}
                    {booking.requested_slot.end.slice(11, 16)}
                  </div>
                  <p className="t-body mt-2 text-fg">{booking.topic}</p>

                  {booking.status === "requested" && (
                    <button
                      type="button"
                      data-confirm-booking={booking.booking_id}
                      disabled={busy === booking.booking_id}
                      onClick={async () => {
                        setBusy(booking.booking_id);
                        try {
                          await institution.confirmBooking(booking.booking_id);
                          queue.reload();
                        } finally {
                          setBusy(null);
                        }
                      }}
                      className="pressable btn btn-primary t-meta mt-3 font-medium"
                    >
                      {t("advisor.confirm")}
                    </button>
                  )}

                  {(booking.status === "requested" ||
                    booking.status === "confirmed") && (
                    <button
                      type="button"
                      data-mark-no-show={booking.booking_id}
                      disabled={busy === booking.booking_id}
                      onClick={async () => {
                        setBusy(booking.booking_id);
                        try {
                          await api.markAdvisorNoShow(booking.booking_id);
                          queue.reload();
                          directory.reload();
                        } finally {
                          setBusy(null);
                        }
                      }}
                      className="pressable btn btn-danger t-meta ms-2 mt-3"
                    >
                      {t("advisor.markNoShow")}
                    </button>
                  )}

                  {booking.status === "confirmed" && (
                    <div className="mt-3">
                      <SectionTitle>{t("advisor.summarize")}</SectionTitle>
                      <p className="t-meta mb-2 text-fg-faint">
                        {t("advisor.summarizeHint")}
                      </p>
                      <textarea
                        data-summary-input={booking.booking_id}
                        rows={3}
                        value={drafts[booking.booking_id] ?? ""}
                        onChange={(e) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [booking.booking_id]: e.target.value,
                          }))
                        }
                        className="field t-body w-full p-3 placeholder:text-fg-faint"
                        placeholder={t("advisor.summaryPlaceholder")}
                      />
                      <button
                        type="button"
                        data-send-summary={booking.booking_id}
                        disabled={
                          busy === booking.booking_id ||
                          !(drafts[booking.booking_id] ?? "").trim()
                        }
                        onClick={async () => {
                          setBusy(booking.booking_id);
                          try {
                            const lines = (drafts[booking.booking_id] ?? "")
                              .split("\n")
                              .map((line) => line.trim())
                              .filter(Boolean)
                              .slice(0, 5);
                            await institution.submitAdvisorSummary(booking.booking_id, {
                              summary_id: `ADVS-${booking.booking_id}`,
                              booking_id: booking.booking_id,
                              key_advice: lines,
                              created_at: new Date().toISOString(),
                            });
                            queue.reload();
                          } finally {
                            setBusy(null);
                          }
                        }}
                        className="pressable btn btn-primary t-meta mt-2 font-medium disabled:opacity-40"
                      >
                        {t("advisor.sendSummary")}
                      </button>
                    </div>
                  )}

                  {booking.status === "completed" && booking.summary && (
                    <ul className="mt-3 flex flex-col gap-1" data-sent-advice>
                      {booking.summary.key_advice.map((line, index) => (
                        <li key={index} className="t-meta text-fg-muted">
                          · {line}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </Card>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

/** R8-1：Advisor 自助注册。注册即获得未来 10 个工作日的标准时段库存。 */
function RegistrationCard({ onRegistered }: { onRegistered: () => void }) {
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [focus, setFocus] = useState("");
  const [created, setCreated] = useState<string | null>(null);
  const [error, setError] = useState(false);

  async function register() {
    if (!name.trim() || !focus.trim()) return;
    setError(false);
    try {
      const advisor = await institution.registerAdvisor({
        name: name.trim(), focus: focus.trim(),
      });
      setCreated(`${advisor.name} · ${advisor.advisor_id}`);
      setName(""); setFocus("");
      onRegistered();
    } catch {
      setError(true);
    }
  }

  const inputCls = "field t-meta px-2.5 py-1.5 placeholder:text-fg-faint";
  return (
    <Card className="mb-5" data-advisor-register>
      <SectionTitle>{t("advisor.register")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[64ch] text-fg-muted">
        {t("advisor.register.lead")}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <input type="text" data-register-name value={name}
          placeholder={t("advisor.register.name")}
          onChange={(e) => setName(e.target.value)} className={inputCls} />
        <input type="text" data-register-focus value={focus}
          placeholder={t("advisor.register.focus")}
          onChange={(e) => setFocus(e.target.value)}
          className={inputCls} style={{ width: "18rem" }} />
        <button type="button" data-register-submit onClick={register}
          className="pressable btn btn-primary t-meta font-medium">
          {t("advisor.register.submit")}
        </button>
      </div>
      {created && (
        <p className="t-meta mt-2" data-register-done
           style={{ color: "var(--color-moss-600)" }}>
          {t("advisor.register.done")} · {created}
        </p>
      )}
      {error && (
        <p className="t-meta mt-2" style={{ color: "var(--color-clay-600)" }}>
          {t("app.error")}
        </p>
      )}
    </Card>
  );
}

/**
 * R8-1：时段管理。选一位已注册顾问，逐时段看状态：
 * 已约（不可动）/ 开放（点击 → 标记不在）/ 不在（点击 → 恢复开放）。
 * 学生端只看得到"开放"的时段——过滤在服务端，不在前端。
 */
function ScheduleCard({
  advisors,
  onChanged,
}: {
  advisors: Schemas["Advisor"][];
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [advisorId, setAdvisorId] = useState<string | null>(null);
  const [busySlot, setBusySlot] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const selected =
    advisors.find((a) => a.advisor_id === advisorId) ?? advisors[0];

  async function toggle(slot: Schemas["AdvisorSlot"]) {
    if (!selected || slot.booked) return;
    setBusySlot(slot.slot_id);
    setNotice(null);
    try {
      await institution.setSlotAvailability(
        selected.advisor_id, slot.slot_id, slot.blocked);
      onChanged();
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusySlot(null);
    }
  }

  if (!selected) return null;
  const byDay = new Map<string, Schemas["AdvisorSlot"][]>();
  for (const slot of selected.slots) {
    const key = slot.span.start.slice(0, 10);
    byDay.set(key, [...(byDay.get(key) ?? []), slot]);
  }

  return (
    <Card className="mb-5" data-schedule-card>
      <SectionTitle>{t("advisor.schedule")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[64ch] text-fg-muted">
        {t("advisor.schedule.lead")}
      </p>
      <select data-schedule-advisor value={selected.advisor_id}
        onChange={(e) => setAdvisorId(e.target.value)}
        className="field t-meta mb-3 px-2.5 py-1.5">
        {advisors.map((advisor) => (
          <option key={advisor.advisor_id} value={advisor.advisor_id}>
            {advisor.name}
          </option>
        ))}
      </select>
      <div className="flex flex-col gap-2">
        {[...byDay.entries()].map(([day, slots]) => (
          <div key={day} className="flex flex-wrap items-center gap-1.5"
               data-schedule-day={day}>
            <span className="t-micro w-24 text-fg-faint">{day}</span>
            {slots.map((slot) => {
              const state = slot.booked ? "booked"
                : slot.blocked ? "blocked" : "open";
              return (
                <button key={slot.slot_id} type="button"
                  data-schedule-slot={slot.slot_id}
                  data-slot-state={state}
                  disabled={slot.booked || busySlot === slot.slot_id}
                  title={t(`advisor.slot.${state}` as Parameters<typeof t>[0])}
                  onClick={() => toggle(slot)}
                  className="pressable t-micro rounded-sm border px-2 py-1 tabular-nums disabled:cursor-not-allowed"
                  style={{
                    borderColor: state === "booked" ? "var(--accent)"
                      : state === "blocked" ? "var(--color-clay-500)"
                      : "var(--line)",
                    background: state === "booked" ? "var(--accent-soft)"
                      : state === "blocked" ? "var(--color-clay-100)"
                      : "transparent",
                    color: state === "blocked" ? "var(--color-clay-600)"
                      : "var(--fg-muted)",
                    textDecoration: state === "blocked" ? "line-through" : "none",
                  }}>
                  {slot.span.start.slice(11, 16)}–{slot.span.end.slice(11, 16)}
                </button>
              );
            })}
          </div>
        ))}
      </div>
      <p className="t-micro mt-2 text-fg-faint">{t("advisor.schedule.legend")}</p>
      {notice && (
        <p className="t-meta mt-2" data-schedule-notice
           style={{ color: "var(--color-clay-600)" }}>{notice}</p>
      )}
    </Card>
  );
}

/**
 * B9（2026-08-01 用户裁定）：已注册顾问的查看 / 编辑 / 删除。
 * 删除受服务端保护：有未完结预约（requested/confirmed）时 409——
 * 界面照实转述"先处理预约再删"，不吞错误。
 */
function RegistryCard({
  advisors,
  onChanged,
}: {
  advisors: Schemas["Advisor"][];
  onChanged: () => void;
}) {
  const { t } = useI18n();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ name: "", focus: "" });
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);

  async function save(advisorId: string) {
    if (!draft.name.trim() || !draft.focus.trim()) return;
    setBusy(advisorId);
    setNotice(null);
    try {
      await institution.updateAdvisor(advisorId, {
        name: draft.name.trim(),
        focus: draft.focus.trim(),
      });
      setEditing(null);
      onChanged();
    } catch (err) {
      setNotice((err as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function remove(advisorId: string) {
    setBusy(advisorId);
    setNotice(null);
    try {
      await institution.deleteAdvisor(advisorId);
      setConfirmingDelete(null);
      onChanged();
    } catch (err) {
      // M3（审查）：服务端 detail 是单语中文，只当日志——界面按错误码走 i18n
      const code =
        typeof (err as { body?: unknown }).body === "object"
          ? (err as { body: { detail?: { error?: string } } }).body?.detail?.error
          : undefined;
      setNotice(
        code === "advisor_has_active_bookings"
          ? t("advisor.registry.deleteBlocked")
          : t("app.error"),
      );
      setConfirmingDelete(null);
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="mb-5" data-advisor-registry>
      <SectionTitle>{t("advisor.registry.title")}</SectionTitle>
      <ul className="flex flex-col gap-2" data-registry-list>
        {advisors.map((advisor) => {
          const isEditing = editing === advisor.advisor_id;
          return (
            <li
              key={advisor.advisor_id}
              data-registry-row={advisor.advisor_id}
              className="rounded-md border border-line bg-bg-sunk p-3"
            >
              {!isEditing ? (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="min-w-0">
                    <span className="t-body font-medium text-fg">{advisor.name}</span>
                    <span className="t-meta ms-2 text-fg-muted">{advisor.focus}</span>
                    <span className="t-mono ms-2 text-fg-faint">{advisor.advisor_id}</span>
                  </span>
                  <span className="flex gap-2">
                    <button
                      type="button"
                      data-registry-edit={advisor.advisor_id}
                      onClick={() => {
                        setEditing(advisor.advisor_id);
                        setDraft({ name: advisor.name, focus: advisor.focus });
                      }}
                      className="pressable btn btn-secondary t-meta"
                    >
                      {t("profile.edit")}
                    </button>
                    <button
                      type="button"
                      data-registry-delete={advisor.advisor_id}
                      disabled={busy === advisor.advisor_id}
                      onClick={() => setConfirmingDelete(advisor.advisor_id)}
                      className="pressable btn btn-danger t-meta disabled:opacity-40"
                    >
                      {t("advisor.registry.delete")}
                    </button>
                  </span>
                </div>
              ) : (
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    type="text"
                    data-registry-name={advisor.advisor_id}
                    value={draft.name}
                    onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                    className="field t-meta px-2.5 py-1.5"
                  />
                  <input
                    type="text"
                    data-registry-focus={advisor.advisor_id}
                    value={draft.focus}
                    onChange={(e) => setDraft((d) => ({ ...d, focus: e.target.value }))}
                    className="field t-meta px-2.5 py-1.5"
                    style={{ width: "18rem" }}
                  />
                  <button
                    type="button"
                    data-registry-save={advisor.advisor_id}
                    disabled={busy === advisor.advisor_id || !draft.name.trim() || !draft.focus.trim()}
                    onClick={() => save(advisor.advisor_id)}
                    className="pressable btn btn-primary t-meta font-medium disabled:opacity-40"
                  >
                    {t("profile.edit.save")}
                  </button>
                  <button
                    type="button"
                    data-registry-cancel={advisor.advisor_id}
                    onClick={() => setEditing(null)}
                    className="pressable btn btn-ghost t-meta"
                  >
                    {t("calendar.editor.cancel")}
                  </button>
                </div>
              )}
              {confirmingDelete === advisor.advisor_id && (
                <div
                  className="mt-2 flex flex-wrap items-center gap-2 rounded-md p-2.5"
                  role="alertdialog"
                  data-registry-delete-confirm={advisor.advisor_id}
                  style={{
                    border: "1px solid var(--color-clay-500)",
                    background: "var(--color-clay-100)",
                  }}
                >
                  <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                    {t("settings.delete.confirm")}
                  </span>
                  <button
                    type="button"
                    data-registry-delete-go={advisor.advisor_id}
                    disabled={busy === advisor.advisor_id}
                    onClick={() => remove(advisor.advisor_id)}
                    className="pressable t-meta rounded-md px-3 py-1.5 font-medium"
                    style={{
                      background: "var(--color-clay-600)",
                      color: "var(--color-clay-100)",
                    }}
                  >
                    {t("advisor.registry.delete")}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmingDelete(null)}
                    className="pressable btn btn-ghost t-meta"
                  >
                    {t("calendar.editor.cancel")}
                  </button>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {notice && (
        <p className="t-meta mt-2" data-registry-notice
           style={{ color: "var(--color-clay-600)" }}>{notice}</p>
      )}
    </Card>
  );
}
