"use client";

import { useRole } from "@/app/providers";
import { useI18n } from "@/i18n";
import { Card, PageHeader } from "@/components/ui";
import { ReviewQueueCard } from "@/components/review-queue";

/**
 * 审核页（用户裁定 2026-08-01）：审核队列从控制台拎出，独立成导航项——
 * 裁决是一项高频职责，不该埋在监控面板中间。
 * 队列端点仍在 /v1/review/ 栅栏内（reviewer + career_center_admin）。
 */
export default function ReviewPage() {
  const { t } = useI18n();
  const { role } = useRole();
  const canReview = role === "career_center_admin" || role === "reviewer";

  return (
    <>
      <PageHeader titleKey="console.reviewQueue" leadKey="console.reviewQueue.explain">
        <span
          className="t-micro rounded-full px-2.5 py-1"
          data-active-role={role}
          style={{ border: "1px solid var(--accent)", color: "var(--accent-deep)" }}
        >
          {t("console.actingAs")}: {role}
        </span>
      </PageHeader>

      {!canReview && (
        <Card className="mb-5">
          <p className="t-body text-fg-muted" data-role-hint>
            {t("console.needCurator")}
          </p>
        </Card>
      )}

      <ReviewQueueCard />
    </>
  );
}
