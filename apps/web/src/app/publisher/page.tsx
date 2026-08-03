"use client";

import { useRef, useState } from "react";
import { useRole } from "@/app/providers";
import { useI18n } from "@/i18n";
import { institution, type Schemas } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import { Card, PageHeader, SectionTitle } from "@/components/ui";

/**
 * Publisher 投稿台（D5 / R7-B）。
 *
 * **这一页只属于投稿人。** 审核队列在 Career Center 控制台（/console）——
 * 投稿人看不到队列，也看不到别人的投稿；这不是省一块 UI，是 B7 的
 * 职责分离在界面层的落点（服务端 /v1/review/ 栅栏独立成立）。
 *
 * R7-B 扩展：投稿除标题/组织/分类外，还要自报**申请人与联系方式、
 * 活动详细介绍、报名方式**，并可附一份文档（demo 存元数据与 vault
 * 引用，不存 blob——与学生证据上传同一纪律）。
 *
 * Seed 里的授权只覆盖 `ORG-career-center`；选别的组织就会撞上 403
 * scope_violation，那正是给人看的（越权被拦截**且记录**）。
 */
const CATEGORIES = ["workshop", "career_talk", "internship"] as const;

/** 主办方分类（十大类，2026-08-02 用户裁定 E：投稿台同步吃新枚举）。
    与广场筛选同一套 i18n 词条（square.orgcat.*）。 */
const ORGANIZER_CATEGORIES = [
  "campus_official", "school_faculty", "career_center",
  "entrepreneurship_center", "student_club", "alumni",
  "enterprise", "partner_enterprise", "policy", "intl_policy",
] as const;

type Outcome = { kind: "ok" | "refused" | "error"; message: string };
type Attachment = Schemas["SubmissionAttachment"];

export default function PublisherPage() {
  const { t, locale } = useI18n();
  const { role } = useRole();

  const [title, setTitle] = useState("合成职涯工作坊（Demo）");
  // 组织不再由界面选择（与主办方分类重合，用户裁定删除）；固定已授权组织
  const organisation = "ORG-career-center" as const;
  const [category, setCategory] = useState<string>("workshop");
  const [organizerCategory, setOrganizerCategory] =
    useState<(typeof ORGANIZER_CATEGORIES)[number]>("career_center");
  const [applicantName, setApplicantName] = useState("");
  const [applicantContact, setApplicantContact] = useState("");
  const [description, setDescription] = useState("");
  const [signupMethod, setSignupMethod] = useState("");
  const [attachment, setAttachment] = useState<Attachment | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  /** 本会话提交过什么，原样快照（用户裁定 2026-08-01：列表要能看回
      当初提交的内容）。审核态在 Career Center，这里不越权查询。 */
  type SubmittedSnapshot = {
    id: string;
    title: string;
    category: string;
    organisation: string;
    applicantName: string;
    applicantContact: string;
    description: string;
    signupMethod: string;
    attachmentName: string | null;
    submittedAt: string;
  };
  const [submitted, setSubmitted] = useState<SubmittedSnapshot[]>([]);
  const [openSubmission, setOpenSubmission] = useState<string | null>(null);
  /** B13：状态以服务端为准——「退回修改」在这里可见，可同 id 重投。 */
  const mine = useResource(() => institution.mySubmissions(), []);
  const [resubmitId, setResubmitId] = useState<string | null>(null);
  // 已批准活动的签到二维码（批准回执连带能力，D 批用户细化）
  const [qr, setQr] = useState<{
    forId: string; dataUrl: string; url: string; count: number;
    opensOn: string | null; countingOpen: boolean;
  } | null>(null);
  async function showQr(opportunityId: string) {
    try {
      const info = await institution.checkinInfo(opportunityId);
      const absolute = `${window.location.origin}${info.checkin_url}`;
      const QRCode = (await import("qrcode")).default;
      const dataUrl = await QRCode.toDataURL(absolute, { width: 140, margin: 1 });
      setQr({ forId: opportunityId, dataUrl, url: absolute,
              count: info.attend_count, opensOn: info.opens_on ?? null,
              countingOpen: info.counting_open });
    } catch { setQr(null); }
  }

  function onPickFile(files: FileList | null) {
    const file = files?.[0];
    if (!file) return setAttachment(null);
    setAttachment({
      file_name: file.name,
      content_type: file.type || "application/octet-stream",
      size_bytes: file.size,
      object_ref: `publisher/${organisation}/${file.name}`,
    });
  }

  async function submit() {
    setOutcome(null);
    // 详情字段由门户强制填写——契约层保持可选（不逼历史投稿补字段）
    if (!title.trim() || !applicantName.trim() || !description.trim() ||
        !signupMethod.trim()) {
      setOutcome({ kind: "error", message: t("publisher.missingFields") });
      return;
    }
    const id = resubmitId ?? `SUB-${Date.now()}`;
    const now = new Date().toISOString();
    try {
      await institution.submit({
        submission_id: id,
        owner_principal_id: `PUB-${organisation}`,
        organization_id: organisation,
        draft_version: 1,
        content: {
          opportunity_id: `OPP-${id}`,
          type: "workshop",
          title,
          organizer: organisation,
          occurrence_id: null,
          series_id: null,
          category_tags: [category],
          requirement_categories: [],
          eligibility_rules: [],
          deadline: null,
          starts_at: null,
          ends_at: null,
          workload_hours_total: null,
          skills: [],
          official_url: "https://example.invalid/demo",
          source_id: "publisher_portal",
          provenance: {
            source: "publisher_portal",
            source_url: null,
            retrieved_at: now,
            published_at: null,
            parser_version: "portal/0.2",
            evidence_snippet: title,
            confidence: 1.0,
          },
          publication_status: "draft",
          last_verified_at: null,
          title_localized: null,
          organizer_localized: null,
          organizer_category: organizerCategory,
          accepts_international: "unknown",
          sponsorship_support: null,
          language_requirements: [],
        },
        category_tags: [category],
        status: "draft",
        auto_check_issues: [],
        current_reviewer_id: null,
        source_evidence: [],
        submitted_at: null,
        applicant_name: applicantName,
        applicant_contact: applicantContact || null,
        event_description: description,
        signup_method: signupMethod,
        attachment,
      });
      setSubmitted((prev) => [
        ...prev,
        {
          id,
          title,
          category,
          organisation,
          applicantName,
          applicantContact,
          description,
          signupMethod,
          attachmentName: attachment?.file_name ?? null,
          submittedAt: now,
        },
      ]);
      setOutcome({ kind: "ok", message: t("publisher.submitted") });
      setResubmitId(null);
      mine.reload();
    } catch (err) {
      const status = (err as { status?: number }).status;
      // 403 不是"出错了"，是**闸门起作用了**。文案要说清楚这个区别，
      // 否则演示时看起来像系统坏了，而它恰恰是在正常工作。
      setOutcome(
        status === 403
          ? { kind: "refused", message: t("publisher.scopeViolation") }
          : { kind: "error", message: (err as Error).message },
      );
    }
  }

  const inputStyle = "field t-body w-full px-3 py-2 placeholder:text-fg-faint";

  const field = (labelKey: Parameters<typeof t>[0], node: React.ReactNode) => (
    <label className="block">
      <span className="t-micro text-fg-faint">{t(labelKey)}</span>
      {node}
    </label>
  );

  const STATUS_KEY: Record<string, Parameters<typeof t>[0]> = {
    submitted: "publisher.inReviewNote",
    auto_checked: "publisher.inReviewNote",
    in_review: "publisher.status.in_review",
    changes_requested: "publisher.status.changes_requested",
    approved: "publisher.status.approved",
    published: "publisher.status.approved",
    rejected: "publisher.status.rejected",
  };

  /** 退回后点「修改并重新提交」：把原投稿内容填回表单，同 id 重投。 */
  function loadForResubmit(row: Schemas["PublicationSubmission"]) {
    setTitle(row.content.title);
    setCategory(row.category_tags[0] ?? "workshop");
    setApplicantName(row.applicant_name ?? "");
    setApplicantContact(row.applicant_contact ?? "");
    setDescription(row.event_description ?? "");
    setSignupMethod(row.signup_method ?? "");
    setResubmitId(row.submission_id);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  return (
    <>
      <PageHeader titleKey="publisher.title" leadKey="publisher.lead">
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

      <Card className="mb-5">
        <SectionTitle>{t("publisher.newSubmission")}</SectionTitle>
        {role !== "publisher" && (
          <p className="t-meta mb-4 text-fg-muted" data-need-publisher>
            {t("publisher.needPublisher")}
          </p>
        )}
        <div className="flex flex-col gap-3">
          {field("publisher.opportunityTitle",
            <input data-submission-title className={`${inputStyle} mt-1`}
              value={title} onChange={(e) => setTitle(e.target.value)} />)}
          {/* 「组织」下拉已删（用户裁定 2026-08-02：与主办方分类重合）。
              organisation 固定为已授权组织；B7 越权拦截的演示改由
              services/publishing 回归测试与 API 佐证（403 scope_violation 仍在）。 */}
          {field("publisher.category",
            <select data-submission-category className={`${inputStyle} mt-1`}
              value={category} onChange={(e) => setCategory(e.target.value)}>
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>)}
          {field("publisher.organizerCategory",
            <select data-submission-orgcat className={`${inputStyle} mt-1`}
              value={organizerCategory}
              onChange={(e) =>
                setOrganizerCategory(e.target.value as typeof organizerCategory)
              }>
              {ORGANIZER_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(`square.orgcat.${c}` as Parameters<typeof t>[0])}
                </option>
              ))}
            </select>)}
          {field("publisher.applicant",
            <input data-submission-applicant className={`${inputStyle} mt-1`}
              placeholder={t("publisher.applicantHint")}
              value={applicantName}
              onChange={(e) => setApplicantName(e.target.value)} />)}
          {field("publisher.applicantContact",
            <input data-submission-contact className={`${inputStyle} mt-1`}
              placeholder={t("publisher.applicantContactHint")}
              value={applicantContact}
              onChange={(e) => setApplicantContact(e.target.value)} />)}
          {field("publisher.description",
            <textarea data-submission-description rows={4}
              className={`${inputStyle} mt-1`}
              placeholder={t("publisher.descriptionHint")}
              value={description}
              onChange={(e) => setDescription(e.target.value)} />)}
          {field("publisher.signupMethod",
            <input data-submission-signup className={`${inputStyle} mt-1`}
              placeholder={t("publisher.signupMethodHint")}
              value={signupMethod}
              onChange={(e) => setSignupMethod(e.target.value)} />)}

          {/* 附件：demo 只登记元数据与 vault 引用，界面明说不存文件本体。
              入口是真按钮（用户裁定 2026-08-01）——原生 file input 藏起来
              但保持可聚焦可用（sr-only），与档案页 Resume 上传同一手法。 */}
          <div>
            <span className="t-micro text-fg-faint">{t("publisher.attachment")}</span>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <label className="pressable btn btn-secondary t-meta cursor-pointer font-medium">
                <span aria-hidden>↑</span>
                {t("publisher.chooseFile")}
                <input ref={fileRef} type="file" data-submission-file
                  className="sr-only"
                  onChange={(e) => onPickFile(e.target.files)} />
              </label>
              {attachment && (
                <span className="chip chip-neutral t-meta gap-1" data-attachment-picked>
                  {attachment.file_name}
                  <button type="button" data-attachment-clear
                    className="pressable text-fg-faint"
                    aria-label={t("app.clear")}
                    onClick={() => {
                      setAttachment(null);
                      if (fileRef.current) fileRef.current.value = "";
                    }}>
                    ×
                  </button>
                </span>
              )}
            </div>
            <p className="t-micro mt-1 text-fg-faint">{t("publisher.attachmentNote")}</p>
          </div>
        </div>

        <button
          type="button"
          data-submit
          onClick={submit}
          className="pressable btn btn-primary t-body mt-4 px-4 py-2 font-medium"
        >
          {t("publisher.submit")}
        </button>

        {outcome && (
          <p
            className="t-meta mt-4 rounded-md p-3"
            data-submit-outcome={outcome.kind}
            style={{
              border: `1px solid ${
                outcome.kind === "ok"
                  ? "var(--color-moss-500)"
                  : "var(--color-clay-500)"
              }`,
              color:
                outcome.kind === "ok"
                  ? "var(--color-moss-600)"
                  : "var(--color-clay-600)",
              background:
                outcome.kind === "ok"
                  ? "var(--color-moss-100)"
                  : "var(--color-clay-100)",
            }}
          >
            {outcome.message}
          </p>
        )}
      </Card>

      {/* 投稿去向说明：审核在 Career Center，那边批不批这里不可见。 */}
      <Card>
        <SectionTitle>{t("publisher.mySubmissions")}</SectionTitle>
        {(mine.data ?? []).length === 0 && submitted.length === 0 ? (
          <p className="t-meta text-fg-muted">{t("publisher.noSubmissionsYet")}</p>
        ) : (
          <ul className="flex flex-col gap-2" data-my-submissions>
            {(mine.data ?? []).map((row) => {
              const snap = submitted.find((x) => x.id === row.submission_id);
              const sub = {
                id: row.submission_id,
                title: row.content.title,
                category: row.category_tags[0] ?? "",
                organisation: row.organization_id,
                applicantName: row.applicant_name ?? "",
                applicantContact: row.applicant_contact ?? "",
                description: row.event_description ?? "",
                signupMethod: row.signup_method ?? "",
                attachmentName: row.attachment?.file_name ?? null,
                submittedAt: row.submitted_at ?? snap?.submittedAt ?? "",
                status: row.status as string,
              };
              const open = openSubmission === sub.id;
              return (
                <li key={sub.id} className="rounded-md border border-line bg-bg-sunk"
                    data-my-submission={sub.id}>
                  <button
                    type="button"
                    data-my-submission-toggle={sub.id}
                    aria-expanded={open}
                    onClick={() => setOpenSubmission(open ? null : sub.id)}
                    className="pressable flex w-full flex-wrap items-baseline justify-between gap-2 rounded-md p-3 text-start"
                    title={t("publisher.expandHint")}
                  >
                    <span className="min-w-0">
                      <span className="t-body font-medium text-fg">{sub.title}</span>
                      <span className="chip chip-neutral t-micro ms-2 align-middle">
                        {sub.category}
                      </span>
                    </span>
                    <span className="t-micro flex items-center gap-2 text-fg-faint">
                      {sub.submittedAt && (
                        <>
                          {t("publisher.submittedAt")}{" "}
                          {new Date(sub.submittedAt).toLocaleString(locale, {
                            month: "2-digit", day: "2-digit",
                            hour: "2-digit", minute: "2-digit",
                          })}
                          {" · "}
                        </>
                      )}
                      <span data-my-submission-status={sub.status}>
                        {t(STATUS_KEY[sub.status] ?? "publisher.inReviewNote")}
                      </span>
                      <span aria-hidden className="transition-transform duration-200"
                            style={{ transform: open ? "rotate(90deg)" : "none" }}>
                        ›
                      </span>
                    </span>
                  </button>
                  {sub.status === "changes_requested" && (
                    <div className="px-3 pb-3">
                      <button
                        type="button"
                        data-resubmit={sub.id}
                        onClick={() => loadForResubmit(row)}
                        className="pressable btn btn-primary t-meta font-medium"
                      >
                        {t("publisher.resubmit")}
                      </button>
                    </div>
                  )}
                  {/* D 批用户细化（2026-08-02）：批准回执连带签到二维码——
                      主办方从这里拿码在活动现场投屏；开始当天才开始计数 */}
                  {(sub.status === "approved" || sub.status === "published") && (
                    <div className="px-3 pb-3" data-publisher-qr={sub.id}>
                      {qr?.forId === row.content.opportunity_id ? (
                        <div className="mt-1 flex items-start gap-4">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={qr.dataUrl} alt="check-in QR" width={140}
                               height={140} className="rounded-md"
                               data-publisher-qr-image={sub.id} />
                          <div className="t-micro flex flex-col gap-1 text-fg-muted">
                            <span>{t("console.plaza.attendN")}: {qr.count}</span>
                            {qr.opensOn && (
                              <span>{t("publisher.qrOpens")}: {qr.opensOn}</span>
                            )}
                            {!qr.countingOpen && (
                              <span className="font-medium"
                                    style={{ color: "var(--accent-deep)" }}>
                                {t("publisher.qrNotOpen")}
                              </span>
                            )}
                            <span className="max-w-[280px] break-all">{qr.url}</span>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          data-publisher-qr-show={sub.id}
                          onClick={() => showQr(row.content.opportunity_id)}
                          className="pressable btn btn-secondary t-meta"
                        >
                          {t("publisher.qrShow")}
                        </button>
                      )}
                    </div>
                  )}
                  {open && (
                    <dl className="t-meta flex flex-col gap-1.5 px-3 pb-3 text-fg-muted"
                        data-my-submission-detail={sub.id}>
                      <div><dt className="t-micro inline text-fg-faint">{t("publisher.organizer")}：</dt>
                        <dd className="inline">{sub.organisation}</dd></div>
                      <div><dt className="t-micro inline text-fg-faint">{t("publisher.applicant")}：</dt>
                        <dd className="inline">{sub.applicantName}
                          {sub.applicantContact ? ` · ${sub.applicantContact}` : ""}</dd></div>
                      <div><dt className="t-micro inline text-fg-faint">{t("publisher.description")}：</dt>
                        <dd className="inline whitespace-pre-wrap">{sub.description}</dd></div>
                      <div><dt className="t-micro inline text-fg-faint">{t("publisher.signupMethod")}：</dt>
                        <dd className="inline">{sub.signupMethod}</dd></div>
                      {sub.attachmentName && (
                        <div><dt className="t-micro inline text-fg-faint">{t("publisher.attachment")}：</dt>
                          <dd className="inline">{sub.attachmentName}</dd></div>
                      )}
                      <div className="t-mono text-fg-faint">{sub.id}</div>
                    </dl>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        <p className="t-micro mt-3 text-fg-faint">{t("publisher.reviewElsewhere")}</p>
      </Card>
    </>
  );
}
