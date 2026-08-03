"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n } from "@/i18n";
import { api } from "@/lib/api";
import { Card, PageHeader } from "@/components/ui";

/** 扫码签到落地页（D 批，2026-08-02）。
 * 活动现场投屏二维码 → 学生手机扫码到这里 → 确认一下即完成签到；
 * 之后该活动的评分自动带「已验证出勤」，好评率分母因此是真人。 */
function CheckinInner() {
  const { t } = useI18n();
  const { studentId } = usePersona();
  const params = useSearchParams();
  const opportunityId = params.get("opp") ?? "";
  const token = params.get("token") ?? "";
  const [state, setState] = useState<"idle" | "busy" | "done" | "dup" | "error">("idle");
  const [detail, setDetail] = useState<string | null>(null);

  async function go() {
    setState("busy");
    try {
      const result = await api.checkin(studentId, {
        opportunity_id: opportunityId,
        token,
      });
      setState(result.already_checked_in ? "dup" : "done");
      setDetail(`${t("checkin.attendNow")}: ${result.attend_count}`);
    } catch (err) {
      setState("error");
      setDetail((err as Error).message);
    }
  }

  const valid = opportunityId && token;
  return (
    <>
      <PageHeader titleKey="checkin.title" leadKey="checkin.lead" />
      <Card>
        {!valid ? (
          <p className="t-body text-fg-muted" data-checkin-invalid>
            {t("checkin.invalidLink")}
          </p>
        ) : (
          <div className="flex flex-col items-start gap-3">
            <p className="t-mono text-fg-faint">{opportunityId}</p>
            {(state === "idle" || state === "busy") && (
              <button
                type="button"
                data-checkin-go
                disabled={state === "busy"}
                onClick={go}
                className="pressable btn btn-primary t-body font-medium"
              >
                {state === "busy" ? t("checkin.busy") : t("checkin.confirm")}
              </button>
            )}
            {state === "done" && (
              <p className="t-body font-medium" data-checkin-done
                 style={{ color: "var(--color-moss-600)" }}>
                ✓ {t("checkin.done")}
              </p>
            )}
            {state === "dup" && (
              <p className="t-body text-fg-muted" data-checkin-dup>
                {t("checkin.already")}
              </p>
            )}
            {state === "error" && (
              <p className="t-body" style={{ color: "var(--color-clay-600)" }}>
                {t("checkin.failed")} {detail}
              </p>
            )}
            {detail && state !== "error" && (
              <p className="t-meta text-fg-muted">{detail}</p>
            )}
          </div>
        )}
      </Card>
    </>
  );
}

export default function CheckinPage() {
  return (
    <Suspense fallback={null}>
      <CheckinInner />
    </Suspense>
  );
}
