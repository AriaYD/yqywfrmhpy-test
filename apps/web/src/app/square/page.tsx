"use client";

import { useMemo, useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized } from "@/i18n";
import { api, type EligibilityExplanation } from "@/lib/api";
import { AddToPlan } from "@/components/add-to-plan";
import { isOfficialLive } from "@/lib/real-sources";
import { useResource } from "@/lib/useResource";
import {
  Card,
  CredentialChip,
  Drawer,
  Empty,
  Failure,
  Grid,
  Loading,
  PageHeader,
  TriState,
  type TriValue,
} from "@/components/ui";

/**
 * 资讯广场：**全部已审核通过的机会，不排序**。
 *
 * 它存在的理由是"AI 未推荐但学生主动发现"这条路径必须走得通——
 * 一个只给推荐结果的产品会把没被推荐的东西变成不存在。
 * 每张卡都有「为什么没推荐？」，答案来自 Rules，不是模型的事后解释。
 */
/** 与 for-you 用同一套映射：待确认 → unknown，不是 not_met（§16.2）。 */
const ELIGIBILITY_TRI: Record<string, TriValue> = {
  eligible_now: "met",
  future_eligible: "unknown",
  needs_confirmation: "unknown",
  ineligible_current_cycle: "not_met",
};

/** 信息发布时间（2026-08-02 用户需求 B）：Provenance 的 published_at →
 *  retrieved_at → last_verified_at，第一个非空；全空 = 不显示、排最后。 */
function publishedAtOf(o: {
  provenance?: { published_at?: string | null; retrieved_at?: string | null } | null;
  last_verified_at?: string | null;
}): string | null {
  return o.provenance?.published_at ?? o.provenance?.retrieved_at
    ?? o.last_verified_at ?? null;
}

export default function SquarePage() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [typeFilter, setTypeFilter] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [organizerFilter, setOrganizerFilter] = useState("");
  const [deadlineOnly, setDeadlineOnly] = useState(false);
  const [savedOnly, setSavedOnly] = useState(false);
  const [plannedOnly, setPlannedOnly] = useState(false);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [explanation, setExplanation] = useState<EligibilityExplanation | null>(null);
  const [explaining, setExplaining] = useState(false);

  // 已截止的默认不取。学生想找"过去有过什么"时再打开——
  // Spec 允许它们作未来参考，但不该混在"现在可以报名"里。
  const [showExpired, setShowExpired] = useState(false);
  const catalog = useResource(() => api.catalog(500, showExpired), [showExpired]);
  // 收藏不是另一张表，是行动流的一个切片（action_type === "save"）
  const actions = useResource(() => api.actions(studentId), [studentId]);
  // 已报名标记与「为你推荐」同源：同一条行动流的 apply 切片（用户裁定 2026-08-01）
  const appliedOnServer = new Set(
    (actions.data ?? [])
      .filter((e) => e.action_type === "apply")
      .map((e) => e.subject_id),
  );
  // 审计红-4（2026-08-02）：「已加入日历」曾读提案存在与否——写入 403
  // 失败时也照亮，名不副实。现改为读**写入真值**：日历里存在该活动的
  // AB-…plan-OPP-… 真实块才算已加入；只有提案未写入的显示「已排入计划」。
  const schedules = useResource(() => api.scheduleProposals(studentId), [studentId]);
  const availability = useResource(() => api.availability(studentId), [studentId]);
  const proposedIds = new Set(
    (schedules.data ?? []).flatMap((proposal) =>
      [proposal.proposal_id, ...proposal.plan_item_ids]
        .map((x) => x.match(/OPP-.+$/)?.[0])
        .filter((x): x is string => Boolean(x)),
    ),
  );
  const writtenIds = new Set(
    (availability.data ?? [])
      // 块 id 形如 AB-STU-A-plan-OPP-EVT-039-PI-OPP-EVT-039
      .map((b) => b.block_id.match(/plan-(OPP-.*?)(?:-PI-|$)/)?.[1])
      .filter((x): x is string => Boolean(x)),
  );
  const plannedIds = writtenIds;
  const [savedLocal, setSavedLocal] = useState<Record<string, boolean>>({});

  const savedIds = useMemo(() => {
    // 事件流 append-only：收藏态 = 每个 subject **最新一条** save/unsave 的方向
    const latest = new Map<string, { type: string; at: string }>();
    for (const a of actions.data ?? []) {
      if (a.action_type !== "save" && a.action_type !== "unsave") continue;
      const seen = latest.get(a.subject_id);
      if (!seen || a.timestamp > seen.at) {
        latest.set(a.subject_id, { type: a.action_type, at: a.timestamp });
      }
    }
    const fromServer = [...latest.entries()]
      .filter(([, v]) => v.type === "save")
      .map(([id]) => id);
    const set = new Set(fromServer);
    for (const [id, on] of Object.entries(savedLocal)) {
      if (on) set.add(id);
      else set.delete(id);
    }
    return set;
  }, [actions.data, savedLocal]);

  async function toggleSave(opportunityId: string) {
    const next = !savedIds.has(opportunityId);
    // 乐观更新：点击必须**立刻**有反应（apple-design §1），
    // 网络回来之前先认这个状态。
    setSavedLocal((prev) => ({ ...prev, [opportunityId]: next }));
    try {
      await api.recordAction(studentId, {
        // 事件 id 必须每次唯一——toggle 是新事件，不是同一事件的重放
        event_id: `ACT-${next ? "save" : "unsave"}-${opportunityId}-${Date.now()}`,
        student_id: studentId,
        action_type: next ? "save" : "unsave",
        subject_id: opportunityId,
        plan_item_id: null,
        approval_receipt_id: null,
        timestamp: new Date().toISOString(),
        // ActionEvent.result 没有 pending：动作发生了就是 succeeded，
        // "还没结果"的东西不该被记成一次行动（tsc 拦下来的）
        result: "succeeded",
        evidence_ids: [],
        verified_growth: false,
      });
      actions.reload();
    } catch {
      setSavedLocal((prev) => ({ ...prev, [opportunityId]: !next }));
    }
  }

  // G（2026-08-02）：「留学生相关政策」筛选 chip 只对勾选了国际生的学生显示
  const profile = useResource(() => api.profile(studentId), [studentId]);
  const intlOn = Boolean(profile.data?.intl_context);
  const { types, tags, organizers } = useMemo(() => {
    const rows = catalog.data ?? [];
    // fix/intl-chain（2026-08-02）：政策两分类**恒显**，不再依赖当前数据里
    // 恰好有政策卡——政策卡是内存态+每日巡检产出，实例回收后会暂空，
    // chip 跟着消失会让学生以为功能不存在。空态另有文案说明产出节奏。
    const present = new Set(rows.map((o) => o.organizer_category ?? "uncategorized"));
    present.add("policy");
    if (intlOn) present.add("intl_policy");
    return {
      types: [...new Set(rows.map((o) => o.type))].sort(),
      tags: [...new Set(rows.flatMap((o) => o.category_tags))].sort(),
      organizers: [...present].sort().filter((v) => v !== "intl_policy" || intlOn),
    };
  }, [catalog.data, intlOn]);

  const shown = useMemo(() => {
    let rows = [...(catalog.data ?? [])];
    // 最新发布排最前（2026-08-02 用户需求 B）：发布时间取
    // provenance.published_at → retrieved_at → last_verified_at 的第一个非空
    rows.sort((a, b) =>
      (publishedAtOf(b) ?? "").localeCompare(publishedAtOf(a) ?? ""));
    // 留学生政策卡只对国际生呈现（G）：未勾选时既无 chip 也无卡
    if (!intlOn) rows = rows.filter((o) => o.organizer_category !== "intl_policy");
    if (typeFilter) rows = rows.filter((o) => o.type === typeFilter);
    if (tagFilter) rows = rows.filter((o) => o.category_tags.includes(tagFilter));
    if (organizerFilter) {
      rows = rows.filter(
        (o) => (o.organizer_category ?? "uncategorized") === organizerFilter,
      );
    }
    if (deadlineOnly) rows = rows.filter((o) => Boolean(o.deadline));
    if (savedOnly) rows = rows.filter((o) => savedIds.has(o.opportunity_id));
    if (plannedOnly) rows = rows.filter((o) => plannedIds.has(o.opportunity_id));
    const q = query.trim().toLowerCase();
    if (q) {
      rows = rows.filter((o) => {
        const title = (localized(o.title_localized, locale) || o.title).toLowerCase();
        const organizer = (
          localized(o.organizer_localized, locale) || o.organizer
        ).toLowerCase();
        return title.includes(q) || organizer.includes(q) ||
          o.opportunity_id.toLowerCase().includes(q);
      });
    }
    return rows;
  }, [catalog.data, intlOn, typeFilter, tagFilter, organizerFilter, deadlineOnly,
      savedOnly, savedIds, plannedOnly, plannedIds, query, locale]);

  async function explain(opportunityId: string) {
    setSelected(opportunityId);
    setExplanation(null);
    setExplaining(true);
    try {
      setExplanation(await api.whyNotRecommended(opportunityId, studentId));
    } catch {
      setExplanation(null);
    } finally {
      setExplaining(false);
    }
  }

  // max-w 是必要的：主办方选项里有 "由 XXX Institute for Advanced Study 主办"
  // 这种长文本，不限宽时 select 会在换行的那一行独占整排。
  const selectStyle =
    "field t-meta max-w-[190px] text-fg-muted";

  return (
    <>
      <PageHeader titleKey="square.title" leadKey="square.lead">
        <div className="flex flex-wrap items-center gap-2" data-square-filters>
          <input
            type="search"
            data-square-search
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t("square.search")}
            aria-label={t("square.search")}
            className="field t-meta max-w-[220px]"
          />
          <select
            aria-label={t("square.filter.type")}
            data-filter="type"
            className={selectStyle}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="">{t("square.filter.type")}</option>
            {types.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <select
            aria-label={t("square.filter.tag")}
            data-filter="tag"
            className={selectStyle}
            value={tagFilter}
            onChange={(e) => setTagFilter(e.target.value)}
          >
            <option value="">{t("square.filter.tag")}</option>
            {tags.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
          <select
            aria-label={t("square.filter.organizer")}
            data-filter="organizer"
            className={selectStyle}
            value={organizerFilter}
            onChange={(e) => setOrganizerFilter(e.target.value)}
          >
            <option value="">{t("square.filter.organizer")}</option>
            {organizers.map((v) => (
              <option key={v} value={v}>
                {t(`square.orgcat.${v}` as Parameters<typeof t>[0])}
              </option>
            ))}
          </select>
          <button
            type="button"
            data-clear-filters
            onClick={() => {
              setTypeFilter("");
              setTagFilter("");
              setOrganizerFilter("");
              setDeadlineOnly(false);
              setSavedOnly(false);
              setPlannedOnly(false);
              setQuery("");
            }}
            className="pressable btn btn-secondary t-meta"
          >
            {t("square.clearFilters")}
          </button>
        </div>
        {/* 第二行：状态类筛选集中排（用户裁定 2026-08-01） */}
        <div className="mt-2 flex flex-wrap items-center gap-3" data-square-filters-row2>
          <label className="t-meta flex items-center gap-1.5 text-fg-muted">
            <input
              type="checkbox"
              data-filter="deadline"
              checked={deadlineOnly}
              onChange={(e) => setDeadlineOnly(e.target.checked)}
            />
            {t("square.filter.deadline")}
          </label>
          <label className="t-meta flex items-center gap-1.5 text-fg-muted">
            <input
              type="checkbox"
              data-filter="expired"
              checked={showExpired}
              onChange={(e) => setShowExpired(e.target.checked)}
            />
            {t("square.showExpired")}
          </label>
          <label className="t-meta flex items-center gap-1.5 text-fg-muted">
            <input
              type="checkbox"
              data-filter="saved"
              checked={savedOnly}
              onChange={(e) => setSavedOnly(e.target.checked)}
            />
            {t("forYou.saved")}
          </label>
          <label className="t-meta flex items-center gap-1.5 text-fg-muted">
            <input
              type="checkbox"
              data-filter-planned
              checked={plannedOnly}
              onChange={(e) => setPlannedOnly(e.target.checked)}
            />
            {t("square.plannedOnly")}
          </label>
          <span className="t-meta tabular-nums text-fg-faint" data-square-count>
            {shown.length} {t("square.count")}
          </span>
        </div>
      </PageHeader>

      {catalog.loading && <Loading />}
      {catalog.error && <Failure error={catalog.error} onRetry={catalog.reload} />}
      {/* codex #9：请求失败时只显示失败态，不叠加"暂无内容"空态文案 */}
      {shown.length === 0 && !catalog.loading && !catalog.error && (
        (organizerFilter === "policy" || organizerFilter === "intl_policy") ? (
          <p className="t-meta text-fg-muted" data-policy-empty-note>
            {t("square.policyEmpty")}
          </p>
        ) : <Empty />
      )}

      <Grid min={290}>
        {shown.map((opportunity) => (
          <Card key={opportunity.opportunity_id} as="article">
            <div data-opportunity={opportunity.opportunity_id}>
              <div className="flex items-center gap-2">
                <span className="t-micro text-fg-faint">{opportunity.type}</span>
                {appliedOnServer.has(opportunity.opportunity_id) && (
                  <span className="chip chip-sage t-micro" data-applied-tag>
                    {t("app.appliedTag")}
                  </span>
                )}
                {plannedIds.has(opportunity.opportunity_id) && (
                  <span className="chip chip-mist t-micro" data-planned-tag>
                    {t("square.planned")}
                  </span>
                )}
                {/* 红-4：有提案但日历写入未成功 → 如实说「已排入计划」，
                    不冒充已在日历里（去行动中心可补写入） */}
                {!plannedIds.has(opportunity.opportunity_id) &&
                  proposedIds.has(opportunity.opportunity_id) && (
                  <span className="chip t-micro" data-proposed-tag
                        style={{ borderColor: "var(--hatch)",
                                 color: "var(--hatch-ink)" }}>
                    {t("square.proposedOnly")}
                  </span>
                )}
                {/* 真实的校园活动与合成条目必须一眼分得开。
                    全站都标了 Synthetic，但广场里两者混排，
                    只在页头说一句不够。 */}
                {/* 已截止的必须**一眼看得出**。既然把它留在目录里，
                    就不能让它看起来和还开着的一样。 */}
                {opportunity.publication_status === "expired" && (
                  <span
                    className="t-micro rounded-sm px-1.5 py-0.5"
                    data-expired
                    style={{
                      border: "1px solid var(--color-clay-500)",
                      color: "var(--color-clay-600)",
                    }}
                  >
                    {t("square.expired")}
                  </span>
                )}
                {isOfficialLive(opportunity) ? (
                  <span
                    className="t-micro rounded-sm px-1.5 py-0.5"
                    data-official-source
                    style={{
                      border: "1px solid var(--accent)",
                      color: "var(--accent-deep)",
                    }}
                  >
                    {t("square.official")}
                  </span>
                ) : (
                  /* 合成条目也显式标注（用户裁定 D）——不能只靠页头横幅 */
                  <span className="t-micro text-fg-faint" data-synthetic-tag>
                    {t("square.syntheticTag")}
                  </span>
                )}
              </div>
              <h3 className="t-section mt-1 text-fg">
                {localized(opportunity.title_localized, locale) || opportunity.title}
              </h3>
              {/* 国际生相关字段（B）：只显示发布者/官方源给出的事实，unknown 不显示不猜 */}
              {intlOn && (opportunity.accepts_international !== "unknown" ||
                opportunity.sponsorship_support ||
                opportunity.language_requirements.length > 0) && (
                <div className="intl-note t-micro mt-1.5 flex flex-wrap gap-x-4 gap-y-1"
                     data-intl-fields style={{ color: "var(--color-mist-700)" }}>
                  {opportunity.accepts_international === "accepts" && (
                    <span>{t("square.intl.accepts")}</span>
                  )}
                  {opportunity.accepts_international === "not_accepted" && (
                    <span>{t("square.intl.notAccepted")}</span>
                  )}
                  {opportunity.sponsorship_support && (
                    <span>{t("square.intl.sponsorship")}: {localized(opportunity.sponsorship_support, locale)}</span>
                  )}
                  {opportunity.language_requirements.map((req, i) => (
                    <span key={i}>{t("square.intl.language")}: {localized(req, locale)}</span>
                  ))}
                </div>
              )}
              <div className="t-meta mt-1 text-fg-muted">
                {localized(opportunity.organizer_localized, locale) ||
                  opportunity.organizer}
              </div>
              {opportunity.deadline && (
                <div className="t-mono mt-1.5 text-fg-faint">
                  {t("forYou.deadline")}: {opportunity.deadline.slice(0, 10)}
                </div>
              )}
              {/* 活动时间 + 信息发布时间（2026-08-02 用户需求 B） */}
              {opportunity.starts_at && (
                <div className="t-mono mt-1 text-fg-faint" data-square-event-time>
                  {t("square.eventTime")}: {opportunity.starts_at.slice(0, 16).replace("T", " ")}
                  {opportunity.ends_at
                    ? ` → ${opportunity.ends_at.slice(0, 16).replace("T", " ")}`
                    : ""}
                </div>
              )}
              {publishedAtOf(opportunity) && (
                <div className="t-mono mt-1 text-fg-faint" data-square-published>
                  {t("square.publishedAt")}: {publishedAtOf(opportunity)!.slice(0, 10)}
                </div>
              )}
              {opportunity.category_tags.length > 0 && (
                <ul className="mt-3 flex flex-wrap gap-1.5">
                  {opportunity.category_tags.slice(0, 4).map((tag) => (
                    <li
                      key={tag}
                      className="t-micro rounded-sm border border-line px-1.5 py-0.5 text-fg-faint"
                    >
                      {tag}
                    </li>
                  ))}
                </ul>
              )}
              {/* 政策提醒卡只展示与跳转官方原文——不是可报名机会，
                  收藏/加入日程/为什么没推荐 对它全部不适用 */}
              <div className="mt-4 flex flex-wrap gap-2">
                {opportunity.type === "policy_update" ? (
                  opportunity.official_url && (
                    <a
                      href={opportunity.official_url}
                      target="_blank"
                      rel="noreferrer"
                      data-policy-source-link
                      className="pressable btn btn-secondary t-meta"
                      style={{ borderColor: "var(--accent)", color: "var(--accent-deep)" }}
                    >
                      {t("square.policySourceLink")}
                    </a>
                  )
                ) : (
                <>
                <button
                  type="button"
                  data-save={opportunity.opportunity_id}
                  data-saved={String(savedIds.has(opportunity.opportunity_id))}
                  onClick={() => toggleSave(opportunity.opportunity_id)}
                  className="pressable btn btn-secondary t-meta"
                  style={{
                    borderColor: savedIds.has(opportunity.opportunity_id)
                      ? "var(--hatch)"
                      : "var(--line-strong)",
                    color: savedIds.has(opportunity.opportunity_id)
                      ? "var(--hatch-ink)"
                      : "var(--fg-muted)",
                  }}
                >
                  {t(
                    savedIds.has(opportunity.opportunity_id)
                      ? "forYou.saved"
                      : "forYou.save",
                  )}
                </button>
                <AddToPlan
                  opportunity={opportunity}
                  studentId={studentId}
                  onAdded={() => actions.reload()}
                />
                <button
                  type="button"
                  data-why-not={opportunity.opportunity_id}
                  onClick={() => explain(opportunity.opportunity_id)}
                  className="pressable btn btn-secondary t-meta"
                  style={{ borderColor: "var(--accent)", color: "var(--accent-deep)" }}
                >
                  {t("square.whyNot")}
                </button>
                </>
                )}
              </div>
            </div>
          </Card>
        ))}
      </Grid>

      <Drawer
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={t("square.whyNot.title")}
      >
        <h2 className="t-title text-fg">{t("square.whyNot.title")}</h2>
        <p className="t-mono mt-1 text-fg-faint">{selected}</p>

        {explaining && (
          <div className="mt-5">
            <Loading />
          </div>
        )}

        {explanation && (
          <div className="mt-5 flex flex-col gap-4" data-explanation>
            <TriState value={ELIGIBILITY_TRI[explanation.state] ?? "unknown"} />
            <p className="t-body text-fg">{localized(explanation.summary, locale)}</p>

            {explanation.what_is_missing.length > 0 && (
              <ul className="flex flex-col gap-2">
                {explanation.what_is_missing.map((missing, index) => (
                  <li
                    key={index}
                    className="t-meta rounded-md border border-line bg-bg-sunk p-3 text-fg-muted"
                  >
                    {localized(missing, locale)}
                  </li>
                ))}
              </ul>
            )}

            {explanation.when_reachable && (
              <p className="t-meta text-fg-muted">
                {localized(explanation.when_reachable, locale)}
              </p>
            )}

            <CredentialChip validationId={explanation.validation_id} />
          </div>
        )}

        {!explaining && !explanation && selected && (
          <div className="mt-5">
            <Empty />
          </div>
        )}

        <button
          type="button"
          onClick={() => setSelected(null)}
          className="pressable btn btn-secondary t-meta mt-6"
        >
          {t("square.whyNot.close")}
        </button>
      </Drawer>
    </>
  );
}
