"use client";

import { useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n, localized } from "@/i18n";
import { institution, type ModerationDecision } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Card, Failure, Loading, SectionTitle } from "@/components/ui";

/**
 * 审核队列（R7-B）。投稿人自报的申请人/详介/报名方式/附件都摆在裁决面前；
 * 三种裁决直接作用在**存着的投稿**上，裁完队列即时刷新。
 * 队列端点在 /v1/review/ 栅栏内——publisher 无论从导航还是直连都进不来。
 */
export function ReviewQueueCard() {
  const { t } = useI18n();
  const { role } = useRole();
  // /v1/review/ 只放 reviewer + career_center_admin——其他岗位不渲染，
  // 免得 curator 进控制台先看到一块 403（审查指出）
  const canReview = role === "career_center_admin" || role === "reviewer";
  const queue = useResource(
    () => (canReview ? institution.reviewQueue() : Promise.resolve([])),
    [role, canReview],
  );
  // hooks 必须无条件调用——早退 return 只能在全部 hooks 之后
  const [busy, setBusy] = useState<string | null>(null);
  const [lastDecision, setLastDecision] = useState<string | null>(null);
  if (!canReview) return null;

  async function decide(
    submissionId: string,
    kind: "approve" | "request_changes" | "reject",
  ) {
    setBusy(submissionId);
    const decision: ModerationDecision = {
      decision_id: `MOD-${Date.now()}`,
      submission_id: submissionId,
      submission_version: 1,
      // 审核员身份，不是投稿人——谁也不该批准自己的投稿
      reviewer_id: "REV-career-center",
      decision: kind,
      reasons: [{ zh_Hans: "Career Center 审核裁决", en: "Career Center decision" }],
      policy_checks: ["scope", "category", "duplicate"],
      timestamp: new Date().toISOString(),
    };
    try {
      await institution.decide(submissionId, decision);
      setLastDecision(`${submissionId}: ${kind} → 200`);
    } catch (err) {
      setLastDecision(
        `${submissionId}: ${kind} → ${(err as { status?: number }).status ?? "error"}`,
      );
    } finally {
      setBusy(null);
      queue.reload();
    }
  }

  return (
    <Card className="mb-5">
      <SectionTitle>{t("console.reviewQueue")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[64ch] text-fg-muted">
        {t("console.reviewQueue.explain")}
      </p>
      {queue.loading && <Loading />}
      {queue.error && <Failure error={queue.error} onRetry={queue.reload} />}
      {queue.data?.length === 0 && (
        <p className="t-meta text-fg-muted" data-review-queue-empty>
          {t("console.reviewQueue.empty")}
        </p>
      )}
      <ul className="flex flex-col gap-3" data-review-queue>
        {queue.data?.map((submission) => (
          <li
            key={submission.submission_id}
            data-review-item={submission.submission_id}
            className="rounded-md border border-line bg-bg-sunk p-4"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="t-section text-fg">{submission.content.title}</span>
              <span className="t-micro rounded-sm border border-line px-2 py-0.5 text-fg-faint">
                {submission.status}
              </span>
            </div>
            <div className="t-meta mt-2 flex flex-col gap-1 text-fg-muted">
              <span>
                {submission.organization_id} · {submission.category_tags.join(", ")}
              </span>
              {submission.applicant_name && (
                <span data-review-applicant>
                  {t("console.applicant")}: {submission.applicant_name}
                  {submission.applicant_contact
                    ? ` (${submission.applicant_contact})`
                    : ""}
                </span>
              )}
              {submission.event_description && (
                <span data-review-description>{submission.event_description}</span>
              )}
              {submission.signup_method && (
                <span data-review-signup>
                  {t("console.signupMethod")}: {submission.signup_method}
                </span>
              )}
              {submission.attachment && (
                <span data-review-attachment className="t-mono">
                  📎 {submission.attachment.file_name} (
                  {Math.ceil(submission.attachment.size_bytes / 1024)} KB)
                </span>
              )}
            </div>
            <div className="mt-3 flex flex-wrap gap-2">
              {(["approve", "request_changes", "reject"] as const).map((kind) => (
                <button
                  key={kind}
                  type="button"
                  data-decide={kind}
                  disabled={busy === submission.submission_id}
                  onClick={() => decide(submission.submission_id, kind)}
                  className={`pressable btn t-meta disabled:opacity-40 ${
                    kind === "approve"
                      ? "btn-primary font-medium"
                      : "btn-secondary"
                  }`}
                >
                  {t(
                    kind === "approve"
                      ? "publisher.approve"
                      : kind === "request_changes"
                        ? "publisher.requestChanges"
                        : "publisher.reject",
                  )}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ul>
      {lastDecision && (
        <p className="t-mono mt-3 text-fg-muted" data-last-decision>
          {lastDecision}
        </p>
      )}
    </Card>
  );
}
