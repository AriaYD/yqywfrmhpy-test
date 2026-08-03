"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, type MessageKey } from "@/i18n";
import { api, type ConsentUpdateRequest } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Card, Loading, PageHeader, SyntheticBadge, Toggle } from "@/components/ui";

/**
 * D1 的 Onboarding & Consent。
 *
 * 授权**逐项独立**：关掉任何一项，其余功能照常。这不是文案上的礼貌，
 * 是 Spec §15 的要求——"拒绝一项等于不能用"会把同意变成胁迫。
 * outreach 与 calendar_write 默认关闭：前者把信息送出校内系统，
 * 后者对学生的日历视图做写入。
 *
 * 开关**落库**（N，2026-07-31）：此前是纯本地 state，页面一刷新就回到默认，
 * 服务端根本不知道你开过什么。现在初始态来自 Canonical Profile 的
 * consent 记录，每次切换都调 `/consents` 并拿回服务端回执。
 */
type Scope = ConsentUpdateRequest["scope"];

type ConsentItem = {
  id: string;
  /** 一个 UI 开关对应的契约同意范围；academic 一次开关 SIS+LMS 两项。 */
  scopes: readonly Scope[];
  labelKey: MessageKey;
  detailKey: MessageKey;
  defaultOn: boolean;
};

const CONSENTS: readonly ConsentItem[] = [
  {
    id: "academic",
    scopes: ["sis_records", "lms_records"],
    labelKey: "onboarding.consent.academic",
    detailKey: "onboarding.consent.academic.detail",
    defaultOn: true,
  },
  {
    id: "calendar",
    scopes: ["calendar_freebusy"],
    labelKey: "onboarding.consent.calendar",
    detailKey: "onboarding.consent.calendar.detail",
    defaultOn: true,
  },
  {
    // 二级日历授权：**默认关闭**，而且明说关着也不影响其余功能。
    // 放在一级日历后面，是因为它只有在一级已开时才有意义。
    id: "calendar_titles",
    scopes: ["calendar_event_titles"],
    labelKey: "calendar.consent.titles",
    detailKey: "calendar.consent.titles.detail",
    defaultOn: false,
  },
  {
    id: "calendar_write",
    scopes: ["calendar_write"],
    labelKey: "onboarding.consent.calendarWrite",
    detailKey: "onboarding.consent.calendarWrite.detail",
    defaultOn: false,
  },
  {
    id: "wellbeing",
    scopes: ["self_reported_wellbeing"],
    labelKey: "onboarding.consent.wellbeing",
    detailKey: "onboarding.consent.wellbeing.detail",
    defaultOn: true,
  },
  {
    id: "outreach",
    scopes: ["wellbeing_outreach"],
    labelKey: "onboarding.consent.outreach",
    detailKey: "onboarding.consent.outreach.detail",
    defaultOn: false,
  },
];

export default function OnboardingPage() {
  const { t } = useI18n();
  const { studentId } = usePersona();
  const profile = useResource(() => api.profile(studentId), [studentId]);

  const [granted, setGranted] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(CONSENTS.map((c) => [c.id, c.defaultOn])),
  );
  const [saving, setSaving] = useState<Record<string, "saving" | "failed">>({});
  // R5-E2：重要联系人——每个班不一样，不写死；学期内任意时间可改
  const contactsRes = useResource(() => api.contacts(studentId), [studentId]);
  const [contactDraft, setContactDraft] = useState<
    Record<string, { name: string; email: string; phone: string }>
  >({
    tutor: { name: "", email: "", phone: "" },
    class_teacher: { name: "", email: "", phone: "" },
    monitor: { name: "", email: "", phone: "" },
  });
  const [contactState, setContactState] =
    useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    if (!contactsRes.data) return;
    setContactDraft((prev) => {
      const next = { ...prev };
      for (const c of contactsRes.data!.contacts) {
        next[c.role] = { name: c.name, email: c.email ?? "", phone: c.phone ?? "" };
      }
      return next;
    });
  }, [contactsRes.data]);

  async function saveContacts() {
    setContactState("saving");
    try {
      await api.saveContacts(studentId, {
        student_id: studentId,
        contacts: (Object.entries(contactDraft) as Array<
          [("tutor" | "class_teacher" | "monitor"), { name: string; email: string; phone: string }]
        >)
          .filter(([, v]) => v.name.trim())
          .map(([role, v]) => ({
            role,
            name: v.name.trim(),
            email: v.email.trim() || null,
            phone: v.phone.trim() || null,
          })),
        updated_at: new Date().toISOString(),
      });
      setContactState("saved");
      contactsRes.reload();
    } catch {
      setContactState("error");
    }
  }

  // 初始态来自服务端记录；记录里没有的范围保持文案上的默认值
  useEffect(() => {
    if (!profile.data) return;
    const active = new Set(
      profile.data.consent
        .filter((c) => c.granted && !c.revoked_at)
        .map((c) => c.scope),
    );
    const recorded = new Set(profile.data.consent.map((c) => c.scope));
    setGranted(
      Object.fromEntries(
        CONSENTS.map((c) => [
          c.id,
          c.scopes.some((s) => recorded.has(s))
            ? c.scopes.every((s) => active.has(s))
            : c.defaultOn,
        ]),
      ),
    );
  }, [profile.data]);

  async function toggle(item: ConsentItem, next: boolean) {
    const before = granted[item.id];
    setGranted((prev) => ({ ...prev, [item.id]: next }));
    setSaving((prev) => ({ ...prev, [item.id]: "saving" }));
    try {
      for (const scope of item.scopes) {
        await api.updateConsent(studentId, { scope, granted: next });
      }
      setSaving((prev) => {
        const { [item.id]: _done, ...rest } = prev;
        return rest;
      });
    } catch {
      // 失败就回滚显示，并如实标"保存失败"——本地假装成功是最糟的结局
      setGranted((prev) => ({ ...prev, [item.id]: before }));
      setSaving((prev) => ({ ...prev, [item.id]: "failed" }));
    }
  }

  return (
    <>
      <PageHeader titleKey="onboarding.title" leadKey="onboarding.lead">
        <SyntheticBadge full />
      </PageHeader>

      <Card>
        <h2 className="t-section mb-4 text-fg">{t("onboarding.consent.title")}</h2>
        {profile.loading && <Loading />}
        <ul className="flex flex-col gap-5">
          {CONSENTS.map((consent) => {
            const on = granted[consent.id];
            const state = saving[consent.id];
            const labelId = `consent-${consent.id}-label`;
            return (
              <li
                key={consent.id}
                data-consent={consent.id}
                data-consent-granted={on ? "true" : "false"}
                className="flex items-start gap-4"
              >
                <Toggle
                  checked={on}
                  labelledBy={labelId}
                  onChange={(next) => toggle(consent, next)}
                />
                <div className="min-w-0">
                  <div id={labelId} className="t-body font-medium text-fg">
                    {t(consent.labelKey)}
                  </div>
                  <p className="t-meta mt-1 max-w-[58ch] text-fg-muted">
                    {t(consent.detailKey)}
                  </p>
                  <span
                    className="t-micro mt-1.5 inline-block"
                    data-consent-state={state ?? (on ? "on" : "off")}
                    style={{
                      color:
                        state === "failed"
                          ? "var(--color-clay-600)"
                          : on
                            ? "var(--accent-deep)"
                            : "var(--fg-faint)",
                    }}
                  >
                    {state === "saving"
                      ? t("onboarding.consent.saving")
                      : state === "failed"
                        ? t("onboarding.consent.saveFailed")
                        : t(on ? "onboarding.consent.on" : "onboarding.consent.off")}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>

        {/* R5-E2：重要联系人（辅导员/班主任/班长）——自填、随时可改 */}
        <div className="mt-8" data-contacts-card>
          <h2 className="t-section mb-1 text-fg">{t("onboarding.contacts.title")}</h2>
          <p className="t-meta mb-3 max-w-[62ch] text-fg-muted">
            {t("onboarding.contacts.lead")}
          </p>
          <div className="flex flex-col gap-3">
            {(["tutor", "class_teacher", "monitor"] as const).map((role) => (
              <div key={role} className="flex flex-wrap items-end gap-2" data-contact-row={role}>
                <span className="t-meta w-20 text-fg">
                  {t(`onboarding.contacts.${role}` as Parameters<typeof t>[0])}
                </span>
                {(["name", "email", "phone"] as const).map((field) => (
                  <input
                    key={field}
                    type="text"
                    data-contact={`${role}-${field}`}
                    value={contactDraft[role][field]}
                    placeholder={t(`onboarding.contacts.${field}` as Parameters<typeof t>[0])}
                    onChange={(e) =>
                      setContactDraft((prev) => ({
                        ...prev,
                        [role]: { ...prev[role], [field]: e.target.value },
                      }))
                    }
                    className="field t-meta px-2.5 py-1.5"
                  />
                ))}
              </div>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              data-save-contacts
              disabled={contactState === "saving"}
              onClick={saveContacts}
              className="pressable btn btn-primary t-meta font-medium disabled:opacity-50"
            >
              {t("onboarding.contacts.save")}
            </button>
            {contactState === "saved" && (
              <span className="t-meta" data-contacts-saved
                    style={{ color: "var(--color-moss-600)" }}>
                {t("onboarding.contacts.saved")}
              </span>
            )}
            {contactState === "error" && (
              <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
                {t("app.error")}
              </span>
            )}
          </div>
        </div>

        {/* R10-7：「开始规划」搬去目标工作室——上传 resume、设定目标之后
            AI 才有规划依据；这里只指路，不越位。 */}
        <p className="t-meta mt-7 text-fg-muted" data-onboarding-next>
          {t("onboarding.nextGoals")}
        </p>
      </Card>
    </>
  );
}
