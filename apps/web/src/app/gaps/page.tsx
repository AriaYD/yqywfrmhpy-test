"use client";

import { useEffect, useState } from "react";
import { usePersona } from "@/app/providers";
import { useI18n, localized } from "@/i18n";
import {
  api,
  type EvidenceRecord,
  type GoalDecomposition,
  type Opportunity,
} from "@/lib/api";
import { LAYERS, LAYER_KEY, layerOf } from "@/lib/requirementLayers";
import { useResource } from "@/lib/useResource";
import {
  Card,
  Empty,
  Failure,
  Loading,
  PageHeader,
} from "@/components/ui";

/**
 * 成长动态跟踪（L，2026-07-31 由"动态差距图"改造）。
 *
 * 不再罗列必修课，不再按完成状态筛选——必修人人都要修，区分不了学生。
 * 真正拉开差距的是**选修课与课外活动**。本页把主目标拆解出的能力细则
 * 按 硬性条件 / 软实力 / 特殊约束 三层列出，每条能力下面挂学生自己的
 * 证据链：写完反思的活动（O 的闭环终点）与已完成的选修课。
 */
export default function GapsPage() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();

  const goals = useResource(() => api.goals(studentId), [studentId]);
  const evidence = useResource(() => api.evidence(studentId), [studentId]);
  // 北极星指标 VGA（Spec §17.1，2026-08-04 落地）：汇总走服务端派生端点，
  // 行动清单读事件流里 verified_growth 的条目（证据可回溯）
  const vga = useResource(() => api.vgaSummary(studentId), [studentId]);
  const actionEvents = useResource(() => api.actions(studentId), [studentId]);
  const academic = useResource(() => api.academicState(studentId), [studentId]);
  const catalog = useResource(() => api.catalog(500, true), []);
  const programs = useResource(() => api.programs(), []);
  const profile = useResource(() => api.profile(studentId), [studentId]);

  const primary = goals.data?.find((g) => g.role === "primary");
  const [decomp, setDecomp] = useState<GoalDecomposition | null | undefined>(
    undefined,
  );
  useEffect(() => {
    if (!primary) return;
    let cancelled = false;
    api
      .goalDecomposition(studentId, primary.goal_id)
      .then((d) => !cancelled && setDecomp(d))
      .catch(() => !cancelled && setDecomp(null));
    return () => {
      cancelled = true;
    };
  }, [studentId, primary?.goal_id]); // eslint-disable-line react-hooks/exhaustive-deps

  // 活动证据：反思闭环落下的 EvidenceRecord（source = OPP-…）→ 按活动的
  // requirement_categories 挂到对应能力条目下。
  const oppById = new Map<string, Opportunity>(
    (catalog.data ?? []).map((o) => [o.opportunity_id, o]),
  );
  const activityEvidence = (evidence.data ?? []).filter((e) =>
    e.source.startsWith("OPP-"),
  );
  const evidenceForCategory = (category: string): EvidenceRecord[] =>
    activityEvidence.filter((e) => {
      const opp = oppById.get(e.source);
      return opp?.requirement_categories.includes(
        category as Opportunity["requirement_categories"][number],
      );
    });

  // 审计黄-9（2026-08-02）：学生档案里的经历也是证据——此前「项目作品集」
  // 条目在学生刚确认了三个项目经历后仍显示"暂无证据"（信息未利用）。
  // 类型 → 能力类别的映射是确定性的；恒标「自述」，不冒充已核验。
  const experiences = useResource(() => api.experiences(studentId), [studentId]);
  // 审查 L14：以 ExperienceType 枚举全集为准——缺省写显式空数组，
  // 日后加枚举时这里会显式缺键而不是静默漏挂
  const EXP_CATEGORY: Record<string, string[]> = {
    project: ["project_portfolio"],
    research: ["project_portfolio", "research_experience"],
    competition: ["project_portfolio", "teamwork_evidence"],
    entrepreneurship: ["project_portfolio", "industry_experience"],
    internship: ["industry_experience"],
    part_time: ["industry_experience"],
    club: ["teamwork_evidence"],
    volunteer: ["teamwork_evidence"],
    exchange: [],
    other: [],
  };
  const experiencesForCategory = (category: string) =>
    (experiences.data ?? []).filter((x) =>
      (EXP_CATEGORY[x.type] ?? []).includes(category),
    );

  // 已完成选修课：完成的课程里去掉本专业必修组覆盖的（必修不进本页）。
  // 专业培养要求没抓到沙箱时，如实全部显示并不加"选修"断言。
  const programMap = (programs.data ?? []).find((p) =>
    (profile.data?.program_id ?? "").endsWith(p.program_id),
  );
  const requiredCodes = new Set(
    (programMap?.requirement_groups ?? [])
      .filter((g) => g.type === "required")
      .flatMap((g) => g.course_codes),
  );
  const completedCourses = (academic.data?.course_records ?? []).filter(
    (r) => r.status === "completed",
  );
  const completedElectives = programMap
    ? completedCourses.filter((r) => !requiredCodes.has(r.course_id))
    : completedCourses;

  const facets = decomp?.facets ?? [];

  return (
    <>
      <PageHeader titleKey="gaps.title" leadKey="gaps.lead" />

      {/* ── 北极星指标 VGA（Spec §17.1）：可爱质感星星 + 本月数（用户裁定
          样式）。数字全部来自服务端派生端点，0 如实显示 0。 ── */}
      <Card className="mb-5" data-vga>
        <div className="flex flex-wrap items-center gap-x-10 gap-y-4">
          <div className="flex items-center gap-4">
            <svg width="56" height="56" viewBox="0 0 64 64" aria-hidden="true"
                 style={{ filter: "drop-shadow(0 3px 7px rgb(240 181 69 / 0.45))" }}>
              {/* 金黄配色为用户看图裁定（2026-08-04）：亮金渐变、暖琥珀描边 */}
              <defs>
                <radialGradient id="vga-star" cx="0.42" cy="0.34" r="0.85">
                  <stop offset="0%" stopColor="#ffedb3" />
                  <stop offset="55%" stopColor="#fbd776" />
                  <stop offset="100%" stopColor="#f0b545" />
                </radialGradient>
              </defs>
              <path
                d="M32 6l7.6 15.9 17.5 2.2-12.9 12 3.4 17.3L32 45.1l-15.6 8.3 3.4-17.3-12.9-12 17.5-2.2z"
                fill="url(#vga-star)" stroke="#d99b2e"
                strokeWidth="2.5" strokeLinejoin="round" />
              {/* 高光：让它有点「黏土质感」的可爱 */}
              <ellipse cx="26" cy="20" rx="6" ry="3.4"
                       fill="rgb(255 255 255 / 0.65)"
                       transform="rotate(-20 26 20)" />
              <circle cx="47" cy="14" r="2" fill="#fbd776" />
              <circle cx="52" cy="20" r="1.2" fill="#fbd776" />
            </svg>
            <div>
              <div className="t-micro text-fg-faint">{t("gaps.vga.title")}</div>
              <div className="flex items-baseline gap-2">
                <span data-vga-month className="tabular-nums"
                      style={{ fontSize: "2.4rem", fontWeight: 750,
                               lineHeight: 1.1, color: "var(--hatch-ink)" }}>
                  {vga.data ? vga.data.current_month_count : "—"}
                </span>
                <span className="t-meta text-fg-muted">
                  {t("gaps.vga.thisMonth")}
                </span>
                <span className="t-meta ms-3 text-fg-muted" data-vga-total>
                  {t("gaps.vga.total")}{" "}
                  <span className="tabular-nums font-semibold text-fg">
                    {vga.data ? vga.data.total_count : "—"}
                  </span>
                </span>
              </div>
            </div>
          </div>
          {/* 逐月 mini 柱：无平滑无插值（G4 同款纪律） */}
          {(vga.data?.months.length ?? 0) > 0 && (
            <ul className="flex items-end gap-2" data-vga-months>
              {vga.data!.months.map((m) => {
                const peak = Math.max(1, ...vga.data!.months.map((x) => x.count));
                return (
                  <li key={m.month} className="text-center">
                    <div className="mx-auto w-4 rounded-t-[3px]"
                         style={{ height: `${(m.count / peak) * 34 + 4}px`,
                                  background: "var(--hatch)" }}
                         title={`${m.month}: ${m.count}`} />
                    <div className="t-micro mt-1 text-fg-faint">{m.month.slice(5)}</div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
        <p className="t-micro mt-3 max-w-[76ch] text-fg-faint">
          {t("gaps.vga.def")}
        </p>
        {vga.data && vga.data.total_count === 0 && (
          <p className="t-meta mt-1 text-fg-muted" data-vga-empty>
            {t("gaps.vga.empty")}
          </p>
        )}
        {(actionEvents.data ?? []).some((a) => a.verified_growth) && (
          <ul className="mt-3 flex flex-col gap-1.5" data-vga-rows>
            {(actionEvents.data ?? [])
              .filter((a) => a.verified_growth)
              .map((a) => (
                <li key={a.event_id} data-vga-row
                    className="t-meta flex flex-wrap items-center gap-2 text-fg">
                  <span aria-hidden style={{ color: "var(--hatch)" }}>★</span>
                  {localized(
                    oppById.get(a.subject_id)?.title_localized ?? null, locale)
                    || oppById.get(a.subject_id)?.title
                    || a.subject_id}
                  <span className="chip chip-mist t-micro">{t("gaps.vga.loop")}</span>
                  <span className="t-mono text-fg-faint">
                    {a.timestamp.slice(0, 10)}
                  </span>
                </li>
              ))}
          </ul>
        )}
      </Card>

      {(goals.loading || evidence.loading) && <Loading />}
      {goals.error && <Failure error={goals.error} onRetry={goals.reload} />}

      {!goals.loading && !primary && <Empty messageKey="gaps.noPrimary" />}
      {primary && decomp === null && (
        <p className="t-meta text-fg-faint" data-decomp-none>
          {t("goals.decomp.none")}
        </p>
      )}

      {primary && facets.length > 0 && (
        <div className="flex flex-col gap-5">
          {LAYERS.map((layer) => {
            const layerFacets = facets.filter(
              (f) => (f.kind as string) === layer || (layer === "hard" && !["soft", "constraint"].includes(f.kind as string)),
            ).filter((f, i, arr) => arr.indexOf(f) === i);
            if (!layerFacets.length) return null;
            const tone =
              layer === "hard" ? "mist" : layer === "soft" ? "sage" : "blossom";
            return (
              <Card key={layer} data-growth-layer={layer}>
                <h2 className="t-section mb-3 flex items-center gap-2 text-fg">
                  <span
                    aria-hidden
                    className="h-2.5 w-2.5 rounded-[3px]"
                    style={{ background: `var(--color-${tone}-500)` }}
                  />
                  {t(LAYER_KEY[layer])}
                </h2>
                <ul className="flex flex-col gap-4">
                  {layerFacets.map((facet, index) => {
                    const chain = evidenceForCategory(facet.category);
                    const expChain = experiencesForCategory(facet.category);
                    const isCourseFacet =
                      layerOf(facet.category) === "hard" &&
                      (facet.category === "coursework" ||
                        facet.category === "technical_skill");
                    return (
                      <li
                        key={`${facet.category}-${index}`}
                        data-growth-facet={facet.category}
                        className="rounded-md border border-line bg-bg-sunk p-3.5"
                      >
                        <div className="t-body font-medium text-fg">
                          {localized(facet.description, locale)}
                        </div>

                        {/* 证据链：写完反思的活动 */}
                        {chain.length > 0 && (
                          <ul className="mt-2.5 flex flex-col gap-1.5" data-evidence-chain>
                            {chain.map((item) => {
                              const opp = oppById.get(item.source);
                              return (
                                <li
                                  key={item.evidence_id}
                                  className="t-meta flex flex-wrap items-baseline gap-x-2 text-fg-muted"
                                >
                                  <span style={{ color: "var(--color-moss-600)" }}>✓</span>
                                  <span className="text-fg">
                                    {opp
                                      ? opp.title_localized
                                        ? localized(opp.title_localized, locale)
                                        : opp.title
                                      : item.source}
                                  </span>
                                  <span className="t-micro text-fg-faint">
                                    {item.obtained_at} ·{" "}
                                    {t(
                                      item.verification_status ===
                                        "institution_verified"
                                        ? "profile.evidence.institution_verified"
                                        : "profile.evidence.self_reported",
                                    )}
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                        )}

                        {/* 黄-9：档案经历（Resume 确认/闭环物化）也挂进证据链 */}
                        {expChain.length > 0 && (
                          <ul className="mt-2 flex flex-col gap-1" data-experience-chain>
                            {expChain.map((x) => (
                              <li key={x.experience_id}
                                  className="t-meta flex flex-wrap items-baseline gap-x-2 text-fg-muted">
                                <span style={{ color: "var(--color-moss-600)" }}>✓</span>
                                <span className="text-fg">
                                  {x.organization}{x.role ? ` · ${x.role}` : ""}
                                </span>
                                <span className="t-micro text-fg-faint">
                                  {t("gaps.fromProfile")} ·{" "}
                                  {t("profile.evidence.self_reported")}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}

                        {/* 已完成选修课（只挂在课程/技能类硬性条目下） */}
                        {isCourseFacet && completedElectives.length > 0 && (
                          <div className="mt-2.5" data-completed-electives>
                            <div className="t-micro text-fg-faint">
                              {t("gaps.completedElectives")}
                            </div>
                            <div className="mt-1 flex flex-wrap gap-1.5">
                              {completedElectives.map((r) => (
                                <span
                                  key={r.course_id}
                                  className="t-mono rounded-sm border border-line px-2 py-0.5 text-fg-muted"
                                >
                                  {r.course_id}
                                </span>
                              ))}
                            </div>
                          </div>
                        )}

                        {chain.length === 0 &&
                          !(isCourseFacet && completedElectives.length > 0) && (
                            <p className="t-meta mt-2 text-fg-faint" data-no-evidence>
                              {t("gaps.noEvidence")}
                            </p>
                          )}
                      </li>
                    );
                  })}
                </ul>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
