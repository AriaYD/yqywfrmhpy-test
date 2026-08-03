"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { usePersona } from "@/app/providers";
import { PlanHub } from "@/components/plan-hub";
import { useI18n, localized, pickLang } from "@/i18n";
import { api } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Bar,
  Card,
  Empty,
  Failure,
  Loading,
  PageHeader,
  SectionTitle,
  TriState,
  type TriValue,
} from "@/components/ui";

/**
 * 先修状态是**三值**的，界面必须原样呈现。
 *
 * 把 UNKNOWN 折叠成 NOT_MET 是这个产品最不能犯的错：
 * 解析器读不懂一句话，学生就被告知"你不够格"。
 * 所以 UNKNOWN 有自己的斜纹样式，而且在计数里单独一栏。
 */
const TRI: Record<string, TriValue> = {
  met: "met",
  not_met: "not_met",
  unknown: "unknown",
};

/**
 * 专业课程地图——C 抓的真实 HKUST 四年要求。
 *
 * G（2026-07-31）：**只显示登录学生自己的专业**，下拉选择器移除——
 * 其他专业只存在于教务系统（Moodle 沙箱）里，不堆在这个平台上。
 * 学生的专业没抓到沙箱时如实说明，不显示别的专业冒充。
 * 主列表只铺**必修组**的课程码；选修课全校可选，只给学分/门数摘要。
 */
/** R4-J：学期档标签（大一上→大四下）。 */
const TERM_LABEL: Record<string, { zh: string; en: string }> = {
  Y1_FALL: { zh: "大一上", en: "Y1 Fall" },
  Y1_SPRING: { zh: "大一下", en: "Y1 Spring" },
  Y2_FALL: { zh: "大二上", en: "Y2 Fall" },
  Y2_SPRING: { zh: "大二下", en: "Y2 Spring" },
  Y3_FALL: { zh: "大三上", en: "Y3 Fall" },
  Y3_SPRING: { zh: "大三下", en: "Y3 Spring" },
  Y4_FALL: { zh: "大四上", en: "Y4 Fall" },
  Y4_SPRING: { zh: "大四下", en: "Y4 Spring" },
};

function ProgramMap({
  studentId,
  studentProgramId,
  studentYear,
}: {
  studentId: string;
  studentProgramId: string | null;
  studentYear: number | null;
}) {
  const { t, locale } = useI18n();
  const programs = useResource(() => api.programs(), []);
  // 2026-08-03 用户裁定：大几学期不让学生自选——学期视图由**教务侧**派生
  // （年级 = 校方记录 year；季别 = 教务学期码，如 2026-27_FALL → FALL）。
  // 接真实系统时这两项都来自教务系统；派生不出（如暑冬学期）就只给总览。
  const academic = useResource(() => api.academicState(studentId), [studentId]);
  const season = academic.data?.current_term?.match(/_(FALL|SPRING)$/)?.[1] ?? null;
  const term =
    studentYear !== null && studentYear >= 1 && studentYear <= 4 && season !== null
      ? `Y${studentYear}_${season}`
      : null;
  const chosen = studentProgramId
    ? (programs.data ?? []).find((p) => studentProgramId.endsWith(p.program_id))
    : undefined;

  if (programs.loading) return <Loading />;
  if (!chosen) {
    return (
      <Card className="mb-5" data-program-missing>
        <SectionTitle>{t("planner.programMap")}</SectionTitle>
        <p className="t-meta text-fg-muted">{t("planner.noProgramData")}</p>
      </Card>
    );
  }
  return (
    <Card className="mb-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SectionTitle>{t("planner.programMap")}</SectionTitle>
        <span className="flex flex-wrap items-center gap-2">
          <span className="t-meta text-fg-muted" data-program-own>
            {chosen.name}
          </span>
          {/* 学期不再自选（2026-08-03 用户裁定）：徽标显示教务侧派生的
              本学期，选择器已撤 */}
          {term !== null && (
            <span className="chip chip-mist t-micro" data-term-derived={term}>
              {pickLang(locale, TERM_LABEL[term].zh, TERM_LABEL[term].en)}
              <span className="t-mono ms-1.5 opacity-70">
                {academic.data?.current_term}
              </span>
            </span>
          )}
        </span>
      </div>
      <p className="t-meta mt-1 text-fg-muted">
        {chosen.school}
        {chosen.total_credits_required
          ? ` · ${t("planner.totalCredits")}: ${chosen.total_credits_required}`
          : ""}
        {chosen.substituted_for
          ? ` · ${t("planner.substitutedFor")}: ${chosen.substituted_for}`
          : ""}
      </p>

      {/* 学期视图：教务侧派生的本学期必修安排 + 择一说明；来源如实注明 */}
      {term !== null && (
        <div className="mt-4" data-term-view={term}>
          {(() => {
            const plan = chosen.term_plans.find((p) => p.term_key === term);
            if (!plan) {
              // Demo 模拟（2026-08-02 用户裁定）：官方学期计划/先修关系
              // 公开渠道找不到的专业，按 (专业,学期) 确定性抽 7 门必修
              // 作参考展示——同一学期刷新不跳变，换学期换一批。
              const pool = [...new Set(
                chosen.requirement_groups
                  .filter((g) => g.type === "required")
                  .flatMap((g) => g.course_codes),
              )];
              if (pool.length === 0) {
                return <p className="t-meta text-fg-muted">{t("app.empty")}</p>;
              }
              let seed = 0;
              for (const ch of `${chosen.program_id}|${term}`) {
                seed = (seed * 31 + ch.charCodeAt(0)) >>> 0;
              }
              const rand = () => {
                seed = (seed * 1664525 + 1013904223) >>> 0;
                return seed / 4294967296;
              };
              const shuffled = [...pool];
              for (let i = shuffled.length - 1; i > 0; i--) {
                const j = Math.floor(rand() * (i + 1));
                [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
              }
              const mock = shuffled.slice(0, 7);
              return (
                <div className="rounded-md border border-line bg-bg-sunk p-3.5"
                     data-term-mock={term}>
                  <div className="t-body font-medium text-fg">
                    {pickLang(locale, TERM_LABEL[term].zh, TERM_LABEL[term].en)}
                    <span className="t-meta ms-2 font-normal text-fg-muted">
                      {t("planner.term.mockRequired")}
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {mock.map((code) => (
                      <span key={code}
                            className="t-mono rounded-sm border border-line px-1.5 py-0.5 text-fg-muted">
                        {code}
                      </span>
                    ))}
                  </div>
                  <p className="t-micro mt-2 max-w-[76ch] text-fg-faint"
                     data-term-mock-note>
                    {t("planner.term.mockNote")}
                  </p>
                </div>
              );
            }
            return (
              <div className="rounded-md border border-line bg-bg-sunk p-3.5">
                <div className="t-body font-medium text-fg">
                  {pickLang(locale, TERM_LABEL[term].zh, TERM_LABEL[term].en)}
                  <span className="t-meta ms-2 font-normal text-fg-muted">
                    {t("planner.term.required")}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {plan.required.map((code) => (
                    <span key={code}
                          className="t-mono rounded-sm border border-line px-1.5 py-0.5 text-fg-muted">
                      {code}
                    </span>
                  ))}
                  {plan.required.length === 0 && (
                    <span className="t-meta text-fg-faint">{t("planner.term.none")}</span>
                  )}
                </div>
                {plan.notes && (
                  <p className="t-meta mt-2 max-w-[76ch] text-fg-muted">{plan.notes}</p>
                )}
              </div>
            );
          })()}
          {chosen.term_plan_note && (
            <p className="t-micro mt-2 text-fg-faint" data-term-source>
              {t("planner.term.source")}
              {locale.startsWith("zh") ? "：" : ": "}
              {chosen.term_plan_note}
            </p>
          )}
        </div>
      )}

      {/* 全部要求（按组）总览常驻——学期视图不再与它二选一 */}
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        {chosen.requirement_groups.map((group, index) => (
          <div key={index}
               className="rounded-md border border-line bg-bg-sunk p-3"
               data-program-group={group.type}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="t-body text-fg">{group.group_name}</span>
              <span
                className="t-micro rounded-sm px-2 py-0.5"
                style={{
                  border: "1px solid var(--line-strong)",
                  color: group.type === "required"
                    ? "var(--color-clay-600)" : "var(--fg-muted)",
                }}
              >
                {t(`planner.groupType.${group.type}` as Parameters<typeof t>[0])}
              </span>
            </div>
            <div className="t-mono mt-1 text-fg-faint">
              {group.credits_required != null &&
                `${t("planner.credits")}: ${group.credits_required}  `}
              {group.courses_required != null &&
                `${t("planner.coursesRequired")}: ${group.courses_required}  `}
              {group.has_or_logic && t("planner.orLogic")}
            </div>
            {/* 只有必修组铺课程码；选修组全校可选，铺出来没有信息量 */}
            {group.type === "required" && group.course_codes.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {group.course_codes.slice(0, 16).map((code) => (
                  <span key={code}
                        className="t-mono rounded-sm border border-line px-1.5 py-0.5 text-fg-muted">
                    {code}
                  </span>
                ))}
                {group.course_codes.length > 16 && (
                  <span className="t-mono text-fg-faint">
                    +{group.course_codes.length - 16}
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {chosen.university_graduation_requirements.length > 0 && (
        <div className="mt-4">
          <div className="t-micro text-fg-faint">{t("planner.gradReqs")}</div>
          <ul className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
            {chosen.university_graduation_requirements.map((req) => (
              <li key={req} className="t-mono text-fg-muted">{req}</li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export default function PlannerPage() {
  // R4-L：行动中心 / 课外活动规划 / 选修课推荐 合并为一页三分页。
  // /planner 深链接落在"选修课推荐"分页。
  return <PlanHub initial="electives" />;
}

/** R4-K：选修课推荐——规则初筛 + AI 复筛，每门都有理由；必修课不出现。 */
/** 「本学期已选课程」折叠模块（用户增补 2026-08-02）。
 * 交互复刻职业发展顾问预约面板：默认折叠成 accent-soft 凸显色单行，
 * 点击展开明细。数据 = SIS/LMS 授权后同步的 StudentCourseRecord（Moodle 链）；
 * 未授权时如实显示去「开通与授权」的引导，不留空白。 */
function EnrolledCoursesPanel({ studentId }: { studentId: string }) {
  const { t, locale } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const profile = useResource(() => api.profile(studentId), [studentId]);
  const academic = useResource(() => api.academicState(studentId), [studentId]);
  const catalog = useResource(() => api.catalogCourses(undefined, 2000), []);

  const hasConsent = (profile.data?.consent ?? []).some(
    (c) => (c.scope === "sis_records" || c.scope === "lms_records") &&
      c.granted && !c.revoked_at,
  );
  const titleById = new Map(
    (catalog.data ?? []).map((c) => [c.course_id, c.title]),
  );
  const enrolled = (academic.data?.course_records ?? []).filter(
    (r) => r.status === "enrolled",
  );

  return (
    <Card
      className="mb-5"
      data-enrolled-courses
      data-enrolled-expanded={expanded ? "true" : "false"}
    >
      <button
        type="button"
        data-enrolled-toggle
        aria-expanded={expanded}
        onClick={() => setExpanded((v) => !v)}
        className="pressable -m-2 flex w-[calc(100%+1rem)] items-center justify-between gap-2 rounded-md p-2 text-start"
        style={{ background: expanded ? "transparent" : "var(--accent-soft)" }}
      >
        <span
          className="t-section"
          style={{ color: expanded ? "var(--fg)" : "var(--accent-deep)" }}
        >
          {t("planner.enrolled.title")}
          {hasConsent && enrolled.length > 0 && (
            <span className="t-micro ms-2 font-semibold opacity-70 tabular-nums">
              {enrolled.length}
            </span>
          )}
        </span>
        <span aria-hidden className="t-meta text-fg-faint">
          {expanded ? "︿" : "﹀"}
        </span>
      </button>
      {expanded && (
        <div className="mt-3">
          {!hasConsent ? (
            <p className="t-meta text-fg-muted" data-enrolled-no-consent>
              {t("planner.enrolled.noConsent")}{" "}
              <Link href="/onboarding" className="underline underline-offset-2">
                {t("planner.enrolled.goConsent")}
              </Link>
            </p>
          ) : academic.loading ? (
            <Loading />
          ) : enrolled.length === 0 ? (
            <Empty />
          ) : (
            <ul className="flex flex-col gap-2">
              {enrolled.map((record) => (
                <li
                  key={record.course_id}
                  data-enrolled-course={record.course_id}
                  className="t-meta flex flex-wrap items-baseline gap-x-3 rounded-md border border-line bg-bg-sunk px-3 py-2"
                >
                  <span className="t-mono text-fg">{record.course_id}</span>
                  <span className="min-w-0 flex-1 text-fg-muted">
                    {titleById.get(record.course_id) ?? ""}
                  </span>
                  <span className="t-micro tabular-nums text-fg-faint">
                    {record.credits} {t("planner.enrolled.credits")}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <p className="t-micro mt-2 text-fg-faint">
            {t("planner.enrolled.source")}
          </p>
        </div>
      )}
    </Card>
  );
}

export function PlannerContent() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [query, setQuery] = useState("");

  const recommendations = useResource(
    () => api.courseRecommendations(studentId),
    [studentId],
  );
  const degree = useResource(() => api.degreeProgress(studentId), [studentId]);
  const profile = useResource(() => api.profile(studentId), [studentId]);

  const shown = useMemo(() => {
    const rows = recommendations.data ?? [];
    if (!query.trim()) return rows;
    const needle = query.trim().toLowerCase();
    return rows.filter(
      (row) =>
        row.course_id.toLowerCase().includes(needle) ||
        row.title.toLowerCase().includes(needle) ||
        row.skill_tags.some((tag) => tag.toLowerCase().includes(needle)),
    );
  }, [recommendations.data, query]);

  return (
    <>
      <PageHeader titleKey="planner.title" leadKey="planner.lead" />
      {/* 本学期已选课程（用户增补 2026-08-02）：默认折叠、凸显色单行 */}
      <EnrolledCoursesPanel studentId={studentId} />
      <ProgramMap
        studentId={studentId}
        studentProgramId={profile.data?.program_id ?? null}
        studentYear={profile.data?.year ?? null}
      />

      {degree.data && (
        <Card className="mb-5">
          <SectionTitle>{t("planner.requirement")}</SectionTitle>
          <div className="t-meta mb-2 flex justify-between text-fg-muted">
            <span className="tabular-nums">
              {degree.data.total_earned_credits} / {degree.data.total_required_credits}{" "}
              {t("planner.credits")}
            </span>
            <span className="tabular-nums">
              {t("planner.remaining")}{" "}
              {degree.data.total_required_credits - degree.data.total_earned_credits}
            </span>
          </div>
          <Bar
            ratio={
              degree.data.total_earned_credits / degree.data.total_required_credits
            }
          />
        </Card>
      )}

      <Card className="mb-5">
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex-1">
            <span className="sr-only">{t("planner.search")}</span>
            <input
              type="search"
              data-course-search
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("planner.search")}
              className="field t-body w-full text-fg placeholder:text-fg-faint"
            />
          </label>
          {/* R4-K：唯一保留的标记——AI 复筛后仍拿不准、但可能相关的课 */}
          <span className="t-meta text-fg-muted" data-confirm-count>
            {t("planner.needsConfirm")}{" "}
            {(recommendations.data ?? []).filter(
              (r) => r.verdict === "needs_user_confirmation",
            ).length}
          </span>
        </div>
      </Card>

      <SectionTitle>{t("planner.recommended.title")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[72ch] text-fg-muted">
        {t("planner.recommended.lead")}
      </p>
      {recommendations.loading && <Loading />}
      {recommendations.error && (
        <Failure error={recommendations.error} onRetry={recommendations.reload} />
      )}
      {shown.length === 0 && !recommendations.loading && <Empty />}

      <ul className="flex flex-col gap-2">
        {shown.map((rec) => (
          <Card key={rec.course_id} as="li" className="!p-4">
            <div
              data-course={rec.course_id}
              data-course-verdict={rec.verdict}
              className="flex flex-wrap items-start justify-between gap-3"
            >
              <div className="min-w-0 flex-1">
                <div className="t-section text-fg">
                  {rec.course_id}
                  <span className="ms-2 font-normal">{rec.title}</span>
                  <span className="t-meta ms-2 text-fg-faint">
                    {rec.credits} {t("planner.credits")}
                  </span>
                </div>
                {rec.description && (
                  <p
                    className="t-meta mt-1.5 max-w-[76ch] text-fg-muted"
                    style={{
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    {rec.description}
                  </p>
                )}
                <p className="t-meta mt-1.5 max-w-[76ch]" data-course-reason>
                  {t("planner.why")}
                  {locale.startsWith("zh") ? "：" : ": "}
                  {localized(rec.reason, locale)}
                  {rec.reason_source === "rules" && (
                    <span className="t-micro ms-1.5 text-fg-faint">
                      （{t("timeline.reason.rule")}）
                    </span>
                  )}
                </p>
                {rec.prerequisite_note && (
                  <p className="t-micro mt-1.5 max-w-[76ch]" data-prereq-note
                     style={{ color: "var(--hatch-ink)" }}>
                    {localized(rec.prerequisite_note, locale)}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {rec.skill_tags.slice(0, 5).map((tag) => (
                    <span key={tag}
                          className="t-micro rounded-sm border border-line px-1.5 py-0.5 text-fg-faint">
                      {tag}
                    </span>
                  ))}
                  {rec.official_url && (
                    <a href={rec.official_url} target="_blank" rel="noreferrer"
                       data-course-official={rec.course_id}
                       className="t-micro underline underline-offset-2"
                       style={{ color: "var(--accent-deep)" }}>
                      {t("planner.officialPage")} ↗
                    </a>
                  )}
                </div>
              </div>
              {rec.verdict === "needs_user_confirmation" && (
                <span
                  className="t-meta shrink-0 rounded-sm border px-2 py-1"
                  data-needs-confirm
                  style={{ borderColor: "var(--hatch)", color: "var(--hatch-ink)" }}
                >
                  {t("planner.needsConfirm")}
                </span>
              )}
            </div>
          </Card>
        ))}
      </ul>
    </>
  );
}
