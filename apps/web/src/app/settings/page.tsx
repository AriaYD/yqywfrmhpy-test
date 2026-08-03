"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { usePersona, useSession } from "@/app/providers";
import { LOCALES, useI18n, type MessageKey } from "@/i18n";
import { api } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Card,
  PageHeader,
  SectionTitle,
  Segmented,
  SyntheticBadge,
  Toggle,
} from "@/components/ui";

/** 与契约 ConsentScope 枚举逐一对应（审查 S2：旧表混着三个不存在的
    key、漏了 memory_retention / anonymous_aggregation / calendar_write，
    漏网项回落成分区标题，用户不知道自己在授权什么）。 */
const CONSENT_KEY: Record<string, MessageKey> = {
  sis_records: "onboarding.consent.academic",
  lms_records: "onboarding.consent.academic",
  calendar_freebusy: "onboarding.consent.calendar",
  calendar_event_titles: "calendar.consent.titles",
  calendar_write: "onboarding.consent.calendarWrite",
  self_reported_wellbeing: "onboarding.consent.wellbeing",
  wellbeing_outreach: "onboarding.consent.outreach",
  memory_retention: "settings.consent.memoryRetention",
  anonymous_aggregation: "settings.consent.anonymousAggregation",
};

const INTENSITY_KEY = {
  gentle: "settings.intensity.gentle",
  balanced: "settings.intensity.balanced",
  sprint: "settings.intensity.sprint",
} as const;

/**
 * 删除是**唯一**用确认对话框的动作。
 *
 * ui-ux-pro-max confirmation-dialogs：确认框只留给真正不可逆的事；到处都用，
 * 人就会训练出"闭眼点确定"的手感，那时它对真正危险的操作也不再有效。
 */
export default function SettingsPage() {
  const { t, locale, setLocale } = useI18n();
  const { studentId } = usePersona();
  const { logout } = useSession();
  const router = useRouter();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  // S1（审查）：开关此前是空 onChange 的假按钮。走与 onboarding 同一条
  // /consents 路径，服务端签发回执；失败如实标红，不本地假装成功。
  const [consentSaving, setConsentSaving] =
    useState<Record<string, "saving" | "failed">>({});

  const profile = useResource(() => api.profile(studentId), [studentId]);

  async function toggleConsent(scope: string, next: boolean) {
    setConsentSaving((prev) => ({ ...prev, [scope]: "saving" }));
    try {
      await api.updateConsent(studentId, {
        scope: scope as Parameters<typeof api.updateConsent>[1]["scope"],
        granted: next,
      });
      setConsentSaving((prev) => {
        const { [scope]: _done, ...rest } = prev;
        return rest;
      });
      profile.reload();
    } catch {
      setConsentSaving((prev) => ({ ...prev, [scope]: "failed" }));
    }
  }

  return (
    <>
      <PageHeader titleKey="settings.title" leadKey="settings.lead" />

      <div className="flex flex-col gap-5">
        <Card>
          <SectionTitle>{t("settings.section.consent")}</SectionTitle>
          <ul className="flex flex-col gap-4">
            {profile.data?.consent.map((record) => (
              <li
                key={record.scope}
                data-consent-scope={record.scope}
                data-consent-granted={String(record.granted)}
                className="flex items-start gap-4"
              >
                <Toggle
                  checked={record.granted}
                  onChange={(next) => toggleConsent(record.scope, next)}
                />
                <div>
                  <div className="t-body text-fg">
                    {t(CONSENT_KEY[record.scope] ?? "settings.section.consent")}
                  </div>
                  <div className="t-mono mt-0.5 text-fg-faint">
                    {record.scope}
                    {record.receipt_id ? ` · ${record.receipt_id}` : ""}
                  </div>
                  {consentSaving[record.scope] && (
                    <span
                      className="t-micro mt-0.5 inline-block"
                      data-consent-saving={consentSaving[record.scope]}
                      style={{
                        color:
                          consentSaving[record.scope] === "failed"
                            ? "var(--color-clay-600)"
                            : "var(--fg-faint)",
                      }}
                    >
                      {t(
                        consentSaving[record.scope] === "failed"
                          ? "onboarding.consent.saveFailed"
                          : "onboarding.consent.saving",
                      )}
                    </span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <SectionTitle>{t("settings.section.appearance")}</SectionTitle>
          <div className="flex flex-col gap-4">
            <div>
              <div className="t-micro mb-1.5 text-fg-faint">{t("chrome.language")}</div>
              <Segmented
                ariaLabel={t("chrome.language")}
                value={locale}
                onChange={setLocale}
                options={LOCALES.map((code) => ({
                  value: code,
                  label:
                    code === "zh-Hans"
                      ? "简体中文"
                      : code === "zh-Hant"
                        ? "繁體中文"
                        : "English",
                }))}
              />
            </div>
            {/* 主题控件已撤（2026-08-03 用户裁定：全站唯一浅色） */}
            {profile.data && (
              <div>
                <div className="t-micro mb-1.5 text-fg-faint">
                  {t("settings.intensity")}
                </div>
                <span className="t-body text-fg" data-intensity>
                  {t(
                    INTENSITY_KEY[
                      profile.data.energy_profile
                        .preferred_intensity as keyof typeof INTENSITY_KEY
                    ] ?? "settings.intensity.balanced",
                  )}
                </span>
              </div>
            )}
          </div>
        </Card>

        <Card>
          <SectionTitle>{t("settings.section.data")}</SectionTitle>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              data-export-data
              onClick={async () => {
                const data = await api.exportMyData(studentId);
                const blob = new Blob([JSON.stringify(data, null, 2)], {
                  type: "application/json",
                });
                const url = URL.createObjectURL(blob);
                const link = document.createElement("a");
                link.href = url;
                link.download = `campuspath-export-${studentId}.json`;
                link.click();
                URL.revokeObjectURL(url);
              }}
              className="pressable btn btn-secondary t-meta"
            >
              {t("settings.export")}
            </button>
            <button
              type="button"
              data-delete-data
              onClick={() => setConfirmingDelete(true)}
              className="pressable btn btn-danger t-meta"
            >
              {t("settings.delete")}
            </button>
          </div>

          {confirmingDelete && (
            <div
              className="mt-4 rounded-md p-4"
              role="alertdialog"
              data-delete-confirm
              style={{
                border: "1px solid var(--color-clay-500)",
                background: "var(--color-clay-100)",
              }}
            >
              <p className="t-body" style={{ color: "var(--color-clay-600)" }}>
                {t("settings.delete.confirm")}
              </p>
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  onClick={() => setConfirmingDelete(false)}
                  className="pressable btn btn-secondary t-meta"
                >
                  {t("settings.delete.cancel")}
                </button>
                <button
                  type="button"
                  data-delete-go
                  onClick={async () => {
                    // 服务端即刻清除该学生的进程内数据；随后结束本地会话。
                    await api.requestDeletion(studentId);
                    logout();
                    router.replace("/login");
                  }}
                  className="pressable t-meta rounded-md px-3 py-1.5 font-medium"
                  style={{
                    background: "var(--color-clay-600)",
                    color: "var(--color-clay-100)",
                  }}
                >
                  {t("settings.delete.go")}
                </button>
              </div>
            </div>
          )}
        </Card>

        <Card>
          <SectionTitle>{t("settings.section.about")}</SectionTitle>
          <p className="t-meta text-fg-muted">{t("settings.about.dataNotice")}</p>
          <div className="mt-3">
            <SyntheticBadge full />
          </div>
        </Card>
      </div>
    </>
  );
}
