"use client";

import { useMemo, useState } from "react";
import { usePersona } from "@/app/providers";
import WellbeingPage from "../wellbeing/page";
import { useI18n, localized, type MessageKey } from "@/i18n";
import { api, type AvailabilityBlock } from "@/lib/api";
import { useResource } from "@/lib/useResource";
import {
  Bar,
  Card,
  Empty,
  Failure,
  Grid,
  Loading,
  Metric,
  PageHeader,
  SectionTitle,
} from "@/components/ui";

/**
 * 具体到小时的周视图。
 *
 * **标题是否显示，由学生的授权层级决定，不由前端决定。**
 * 一级授权下 API 返回的 `title` 就是 null——界面拿不到，也就无从泄漏；
 * 二级授权下才有值，学生因此能看出"哪个时段可以挪"。
 * 参与人、地点、备注在任何层级都没有：契约里就没有那些字段。
 */
const TYPE_KEY: Record<string, MessageKey> = {
  busy: "calendar.block.busy",
  free: "calendar.block.free",
  protected: "calendar.block.protected",
  buffer: "calendar.block.buffer",
  flexible: "calendar.block.flexible",
};

const TYPE_COLOR: Record<string, string> = {
  busy: "var(--accent-deep)",
  free: "transparent",
  // 2026-08-02 用户裁定：保护色改黄（琥珀 --hatch）——原 clay-600 与「忙」
  // 的深红在图例里几乎不可分
  protected: "var(--hatch)",
  buffer: "var(--color-moss-600)",
  flexible: "var(--color-mist-700)",
};

/** 课程块（source=course_timetable，教务同步）用独立色，与普通「忙」区分
 *  ——用户裁定 B：学生要能看出日历上的课是从选课记录自动来的 */
const COURSE_COLOR = "var(--color-bark-600)";

/** 块的展示样式集中判定：课程/睡眠/规划中活动都是 id 或来源约定，不是 type */
function blockStyle(block: AvailabilityBlock): { background: string; color: string; border?: string } {
  if (block.block_id.startsWith("PLAN-")) {
    return {
      background: "color-mix(in srgb, var(--accent) 12%, transparent)",
      color: "var(--accent-deep)",
      border: "2px dashed var(--accent-deep)",
    };
  }
  if (block.block_id.includes("sleep")) {
    return { background: "var(--color-mist-100)", color: "var(--color-mist-700)" };
  }
  if ((block as { source?: string }).source === "course_timetable") {
    return { background: COURSE_COLOR, color: "var(--accent-fg)" };
  }
  if (block.type === "protected") {
    // 琥珀底配深字，白字在黄底上读不清
    return { background: TYPE_COLOR.protected, color: "var(--color-bark-900)" };
  }
  return { background: TYPE_COLOR[block.type], color: "var(--accent-fg)" };
}

/**
 * R7-C：画**整整 24 小时**。曾只画 07–24——但睡眠窗口正是被裁掉的那段：
 * 预警的睡眠不足判定看的就是学生日程里的休息时段，日历必须让人
 * 亲眼看到 23:00–07:30 的保护块，而不是把它藏在网格外。
 */
const DAY_START = 0;
const DAY_END = 24;
const HOURS = Array.from({ length: DAY_END - DAY_START }, (_, i) => DAY_START + i);
const ROW_HEIGHT = 26;

type Day = { key: string; label: string; blocks: AvailabilityBlock[] };

/**
 * M：日常作息卡。学生**显式提交**睡眠与三餐窗口（§16.8.2 禁止从日历反推），
 * 服务端为快照周期内每一天生成保护块。口径明示：作息不扣可支配容量
 * （每周可支配小时数本来就不含它们）；自己在网格上额外划的保护时段才扣。
 */
function RoutineCard({
  studentId,
  onSubmitted,
}: {
  studentId: string;
  onSubmitted: () => void;
}) {
  const { t } = useI18n();
  const [sleep, setSleep] = useState({ start: "23:00", end: "07:30" });
  const [lunch, setLunch] = useState({ on: true, start: "12:00", end: "13:00" });
  const [dinner, setDinner] = useState({ on: true, start: "18:00", end: "19:00" });
  const [breakfast, setBreakfast] = useState({ on: false, start: "08:00", end: "08:30" });
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");

  async function submit() {
    setState("saving");
    try {
      const meals = [breakfast, lunch, dinner]
        .filter((m) => m.on)
        .map(({ start, end }) => ({ start, end }));
      await api.submitRoutine(studentId, { sleep, meals });
      setState("done");
      onSubmitted();
    } catch {
      setState("error");
    }
  }

  const timeInput = (
    value: { start: string; end: string },
    set: (v: { start: string; end: string }) => void,
    tag: string,
  ) => (
    <span className="flex items-center gap-1">
      <input
        type="time" value={value.start} data-routine={`${tag}-start`}
        onChange={(e) => set({ ...value, start: e.target.value })}
        className="field t-meta px-1.5 py-1"
      />
      –
      <input
        type="time" value={value.end} data-routine={`${tag}-end`}
        onChange={(e) => set({ ...value, end: e.target.value })}
        className="field t-meta px-1.5 py-1"
      />
    </span>
  );

  return (
    <Card className="mt-5" data-routine-card>
      <SectionTitle>{t("calendar.routine.title")}</SectionTitle>
      <p className="t-meta mb-3 max-w-[70ch] text-fg-muted">
        {t("calendar.routine.lead")}
      </p>
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <label className="t-meta flex items-center gap-2 text-fg">
          {t("calendar.routine.sleep")}
          {timeInput(sleep, setSleep, "sleep")}
        </label>
        {(
          [
            ["breakfast", breakfast, setBreakfast],
            ["lunch", lunch, setLunch],
            ["dinner", dinner, setDinner],
          ] as const
        ).map(([name, meal, set]) => (
          <label key={name} className="t-meta flex items-center gap-2 text-fg">
            <input
              type="checkbox"
              checked={meal.on}
              data-routine={`${name}-on`}
              onChange={(e) => set({ ...meal, on: e.target.checked })}
            />
            {t(`calendar.routine.${name}` as MessageKey)}
            {meal.on &&
              timeInput(
                { start: meal.start, end: meal.end },
                (v) => set({ ...meal, ...v }),
                name,
              )}
          </label>
        ))}
        <button
          type="button" data-routine-submit
          disabled={state === "saving"}
          onClick={submit}
          className="pressable btn btn-primary t-meta font-medium disabled:opacity-50"
        >
          {state === "saving" ? t("app.loading") : t("calendar.routine.apply")}
        </button>
        {state === "done" && (
          <span className="t-meta" data-routine-done style={{ color: "var(--color-moss-600)" }}>
            {t("calendar.routine.done")}
          </span>
        )}
        {state === "error" && (
          <span className="t-meta" style={{ color: "var(--color-clay-600)" }}>
            {t("app.error")}
          </span>
        )}
      </div>
    </Card>
  );
}

export default function CalendarPage() {
  // M：身心容量并入本页（同页分页）。/wellbeing 深链接仍指向原页。
  const { t } = useI18n();
  const [pageTab, setPageTab] = useState<"calendar" | "wellbeing">("calendar");
  return (
    <>
      <div
        className="mb-5 inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
        data-page-tabs
      >
        {(["calendar", "wellbeing"] as const).map((tabKey) => (
          <button
            key={tabKey}
            type="button"
            data-page-tab={tabKey}
            aria-pressed={pageTab === tabKey}
            onClick={() => setPageTab(tabKey)}
            className="pressable t-meta rounded-sm px-3 py-1.5"
            style={{
              background: pageTab === tabKey ? "var(--accent-deep)" : "transparent",
              color: pageTab === tabKey ? "var(--accent-fg)" : "var(--fg-muted)",
              fontWeight: pageTab === tabKey ? 600 : 500,
            }}
          >
            {t(tabKey === "calendar" ? "page.calendar" : "page.wellbeing")}
          </button>
        ))}
      </div>
      {pageTab === "wellbeing" ? <WellbeingPage /> : <CalendarInner />}
    </>
  );
}

function CalendarInner() {
  const { t, locale } = useI18n();
  const { studentId } = usePersona();
  const [weekOffset, setWeekOffset] = useState(0);
  // R7-C：周 / 月两种模式，像 Google Calendar。月视图看分布，周视图做编辑。
  const [view, setView] = useState<"week" | "month">("week");
  const [monthIndex, setMonthIndex] = useState(0);

  const blocks = useResource(() => api.availability(studentId), [studentId]);
  // 用户裁定 B（2026-08-02）：课外活动规划的机会类条目要在日历上可见——
  // 以「规划中」虚线块呈现（有真实活动时间的才画；批准写入日历后由真实块取代）
  const plannedPathway = useResource(
    () => api.pathway(studentId).catch(() => null), [studentId]);
  const plannedCatalog = useResource(() => api.catalog(500, true), []);
  const snapshot = useResource(() => api.capacitySnapshot(studentId), [studentId]);
  // E1（2026-08-02）：睡眠单独统计。只认显式登记的睡眠块（id 带 sleep——
  // 作息卡与 seed 两条路都是这个形状），不从空白日历反推（B6）。
  const sleepPerDay = (() => {
    const rows = (blocks.data ?? []).filter((b) => b.block_id.includes("sleep"));
    if (!rows.length) return null;
    const total = rows.reduce((sum, b) =>
      sum + (new Date(b.span.end).getTime() - new Date(b.span.start).getTime())
        / 3_600_000, 0);
    const days = new Set(rows.map((b) => b.span.start.slice(0, 10))).size;
    return days ? total / days : null;
  })();
  // R4-M：编辑器里给课程/活动块配官方链接
  const catalog = useResource(() => api.catalog(500, true), []);

  /** 块 → 对应的官方链接（课程→教务页；活动→机会官方页）。推不出来就没有。 */
  function officialLinkOf(block: AvailabilityBlock): string | null {
    const oppMatch = block.block_id.match(/(OPP-[A-Za-z0-9-]+?)(-PI-|$)/);
    if (oppMatch) {
      const opp = (catalog.data ?? []).find(
        (o) => o.opportunity_id === oppMatch[1],
      );
      if (opp?.official_url) return opp.official_url;
    }
    const courseMatch = (block.title ?? "").match(/^([A-Z]{4}) \d{4}/);
    if (courseMatch) {
      return `https://prog-crs.hkust.edu.hk/ugcourse/2026-27/${courseMatch[1]}`;
    }
    return null;
  }
  // H：改/删之后由学生决定要不要重排近两周
  const [edited, setEdited] = useState(false);
  const [replanScope, setReplanScope] = useState<string | null>(null);

  /** A：点击网格直接编辑——像 Google Calendar 那样，没有单独的"调整卡"。 */
  type EditorState =
    | { mode: "edit"; block: AvailabilityBlock }
    | { mode: "create"; day: string; startHour: number };
  const [editor, setEditor] = useState<EditorState | null>(null);
  // 行程详情（2026-08-02 用户需求）：单击块 → 网格下方只读详情面板
  // （Google 日历式：标题/时间/类型/官方链接/简介，有才显示，不编造）
  const [detail, setDetail] = useState<AvailabilityBlock | null>(null);
  const [form, setForm] = useState({
    title: "", type: "busy" as AvailabilityBlock["type"],
    start: "", end: "", reminder: "" as string,
  });

  function openEdit(block: AvailabilityBlock) {
    setEditor({ mode: "edit", block });
    setForm({
      title: block.title ?? "",
      type: block.type,
      start: block.span.start.slice(11, 16),
      end: block.span.end.slice(11, 16),
      reminder: block.reminder_minutes_before?.toString() ?? "",
    });
  }

  function openCreate(day: string, startHour: number) {
    const hh = String(Math.min(startHour, 23)).padStart(2, "0");
    const eh = String(Math.min(startHour + 1, 24) % 24).padStart(2, "0");
    setEditor({ mode: "create", day, startHour });
    setForm({ title: "", type: "busy", start: `${hh}:00`, end: `${eh}:00`, reminder: "" });
  }

  function afterChange() {
    setEditor(null);
    setEdited(true);
    blocks.reload();
    snapshot.reload();
  }

  async function saveEditor() {
    if (!editor) return;
    const reminder = form.reminder === "" ? null : Number(form.reminder);
    if (editor.mode === "create") {
      const start = `${editor.day}T${form.start}:00Z`;
      let end = `${editor.day}T${form.end}:00Z`;
      if (end <= start) end = `${editor.day}T23:59:00Z`;
      await api.createBlock(studentId, {
        block_id: `AB-${studentId}-own-${Date.now()}`,
        student_id: studentId,
        span: { start, end },
        type: form.type,
        source: "student_defined",
        // 学生自己写的标题：student_defined 内容，层级随之为 event_titles
        detail_level: form.title ? "event_titles" : "free_busy_only",
        title: form.title || null,
        privacy_level: form.title ? "student_defined" : "opaque",
        reachable: true,
        reminder_minutes_before: reminder,
      });
    } else {
      const day = editor.block.span.start.slice(0, 10);
      // 审查修复：跨午夜块（23:00→次日 07:30）的 end 要落到次日——
      // 都拼在起始日会得到 end < start 的 422，连改个标题都存不回去
      let endDay = day;
      if (form.end <= form.start) {
        const next = new Date(`${day}T00:00:00Z`);
        next.setUTCDate(next.getUTCDate() + 1);
        endDay = next.toISOString().slice(0, 10);
      }
      await api.updateBlock(studentId, editor.block.block_id, {
        span: { start: `${day}T${form.start}:00Z`, end: `${endDay}T${form.end}:00Z` },
        type: form.type,
        title: form.title || null,
        reminder_minutes_before: reminder,
      });
    }
    afterChange();
  }

  async function removeBlock(blockId: string) {
    await api.removeBlock(studentId, blockId);
    afterChange();
  }

  async function confirmReplan(go: boolean) {
    setEdited(false);
    if (!go) return;
    const scope = await api.replanPreview(studentId, {
      student_id: studentId,
      trigger_type: "calendar_change",
      source: "student_calendar_edit",
      detected_at: new Date().toISOString(),
      request_id: `RQ-cal-${Date.now()}`,
    });
    setReplanScope(
      `${scope.affected_plan_item_ids.length} / ${scope.unaffected_plan_item_ids.length}`,
    );
  }

  /** 把区块按天分组，取第 `weekOffset` 周的 7 天。 */
  const { days, weekLabel, hasTitles, allDays, byDay, months, displayToOriginal, planDetails } =
    useMemo(() => {
    const real = blocks.data ?? [];
    // 规划中活动 → 虚线伪块（用户验收标准：规划里的活动必须在日历上看得见）。
    // 多日活动**按天切段**、同日多条**合并为一条**（标题 +N）——五个同时段
    // 活动叠成一摞糊标题是实测踩过的坑；已批准写入（AB-…-plan-…）的不再重复画。
    const written = new Set(
      real.filter((b) => b.block_id.includes("-plan-"))
          .map((b) => b.block_id));
    const oppById = new Map(
      (plannedCatalog.data ?? []).map((o) => [o.opportunity_id, o]));
    type Seg = { day: string; start: string; end: string; title: string;
                 url: string | null; brief: string | null };
    const segments: Seg[] = [];
    for (const item of plannedPathway.data?.plan_items ?? []) {
      if (item.kind !== "opportunity") continue;
      const opp = oppById.get(item.subject_id);
      if (!opp?.starts_at) continue;
      if ([...written].some((w) => w.includes(item.subject_id))) continue;
      const endIso = opp.ends_at
        ?? new Date(new Date(opp.starts_at).getTime() + 2 * 3600_000)
          .toISOString().replace(/\.\d{3}Z$/, "Z");
      const title = localized(opp.title_localized, locale) || opp.title;
      const firstDay = opp.starts_at.slice(0, 10);
      const lastDay = endIso.slice(0, 10);
      for (let d = new Date(`${firstDay}T00:00:00Z`);
           d.toISOString().slice(0, 10) <= lastDay;
           d = new Date(d.getTime() + 86_400_000)) {
        const day = d.toISOString().slice(0, 10);
        segments.push({
          day,
          start: day === firstDay ? opp.starts_at : `${day}T00:00:00Z`,
          end: day === lastDay ? endIso : `${day}T23:59:00Z`,
          title,
          url: opp.official_url ?? null,
          brief: opp.provenance?.evidence_snippet ?? null,
        });
      }
    }
    const byPlanDay = new Map<string, Seg[]>();
    for (const seg of segments) {
      byPlanDay.set(seg.day, [...(byPlanDay.get(seg.day) ?? []), seg]);
    }
    const planned: AvailabilityBlock[] = [...byPlanDay.entries()].map(
      ([day, segs]) => ({
        block_id: `PLAN-${day}`,
        student_id: studentId,
        span: {
          start: segs.reduce((a, s) => (s.start < a ? s.start : a), segs[0].start),
          end: segs.reduce((a, s) => (s.end > a ? s.end : a), segs[0].end),
        },
        type: "flexible",
        source: "derived",
        detail_level: "event_titles",
        title: segs.length > 1
          ? `${segs[0].title} +${segs.length - 1}`
          : segs[0].title,
        privacy_level: "student_defined",
      } as unknown as AvailabilityBlock));
    const rows = [...real, ...planned];
    const empty = {
      days: [] as Day[], weekLabel: "", hasTitles: false,
      allDays: [] as string[], byDay: new Map<string, AvailabilityBlock[]>(),
      months: [] as string[],
      displayToOriginal: new Map<string, AvailabilityBlock>(),
      planDetails: new Map<string, { day: string; start: string; end: string;
        title: string; url: string | null; brief: string | null }[]>(),
    };
    if (!rows.length) return empty;

    const byDay = new Map<string, AvailabilityBlock[]>();
    const displayToOriginal = new Map<string, AvailabilityBlock>();
    const push = (key: string, block: AvailabilityBlock) =>
      byDay.set(key, [...(byDay.get(key) ?? []), block]);
    for (const block of rows) {
      const startDay = block.span.start.slice(0, 10);
      const endDay = block.span.end.slice(0, 10);
      push(startDay, block);
      // R7-C：跨午夜的块（典型是 23:00→次日 07:30 的睡眠保护）拆一段
      // "次日凌晨"显示段——否则 24 小时网格的 0–7 点永远是空的，
      // 睡眠不足评估就没有可看的依据。显示段点开仍编辑**原块**。
      if (endDay > startDay && block.span.end.slice(11, 16) !== "00:00") {
        const morning: AvailabilityBlock = {
          ...block,
          block_id: `${block.block_id}~am`,
          span: { ...block.span, start: `${endDay}T00:00:00Z` },
        };
        displayToOriginal.set(morning.block_id, block);
        push(endDay, morning);
      }
    }
    // 连续日历周（2026-08-02 实测踩坑）：此前"周"=有数据的 7 天拼页，
    // 表头会出现「10-25 周日、11-19 周四、11-24 周二」混排。改为从最早
    // 数据日所在周的**周一**起逐日排满到最晚数据日，空日照常占位。
    const sparse = [...byDay.keys()].sort();
    // 锚点跳过"只有深夜睡眠起点"的前导日（作息生成的前一晚块）：
    // 它的意义在次日凌晨段，不该把整个空白前导周拉进分页
    const anchor = sparse.find((key) =>
      (byDay.get(key) ?? []).some((b) =>
        !(b.block_id.includes("sleep") && b.span.start.slice(11, 16) >= "20:00")),
    ) ?? sparse[0];
    const firstDate = new Date(`${anchor}T00:00:00Z`);
    const monday = new Date(firstDate.getTime()
      - ((firstDate.getUTCDay() + 6) % 7) * 86_400_000);
    const lastDay = sparse[sparse.length - 1];
    const allDays: string[] = [];
    for (let d = monday; d.toISOString().slice(0, 10) <= lastDay;
         d = new Date(d.getTime() + 86_400_000)) {
      allDays.push(d.toISOString().slice(0, 10));
    }
    const week = allDays.slice(weekOffset * 7, weekOffset * 7 + 7);
    return {
      days: week.map((key) => ({
        key,
        label: new Date(`${key}T00:00:00Z`).toLocaleDateString(locale, {
          weekday: "short",
          day: "numeric",
          timeZone: "UTC",
        }),
        blocks: (byDay.get(key) ?? []).sort((a, b) =>
          a.span.start.localeCompare(b.span.start),
        ),
      })),
      weekLabel: week.length ? `${week[0]} → ${week[week.length - 1]}` : "",
      hasTitles: rows.some((b) => Boolean(b.title)),
      allDays,
      byDay,
      // 月视图只翻**有数据的**月份——空月份翻过去只有一片空白
      months: [...new Set(allDays.map((d) => d.slice(0, 7)))].sort(),
      displayToOriginal,
      planDetails: byPlanDay,
    };
  }, [blocks.data, plannedPathway.data, plannedCatalog.data, studentId,
      weekOffset, locale]);

  /**
   * R7-C 月视图：真实月历（周一起步、含空白格），格子里放当天的块摘要。
   * 点一个有数据的日子 → 跳到含它的那一周做编辑；点空日子 → 直接建行程。
   */
  const monthCells = useMemo(() => {
    const month = months[Math.min(monthIndex, Math.max(0, months.length - 1))];
    if (!month) return { month: "", cells: [] as ({ key: string; blocks: AvailabilityBlock[] } | null)[] };
    const [y, m] = month.split("-").map(Number);
    const first = new Date(Date.UTC(y, m - 1, 1));
    const daysInMonth = new Date(Date.UTC(y, m, 0)).getUTCDate();
    const leading = (first.getUTCDay() + 6) % 7; // 周一=0
    const cells: ({ key: string; blocks: AvailabilityBlock[] } | null)[] =
      Array.from({ length: leading }, () => null);
    for (let d = 1; d <= daysInMonth; d++) {
      const key = `${month}-${String(d).padStart(2, "0")}`;
      cells.push({ key, blocks: byDay.get(key) ?? [] });
    }
    return { month, cells };
  }, [months, monthIndex, byDay]);

  function jumpToDay(dayKey: string) {
    const index = allDays.indexOf(dayKey);
    if (index >= 0) {
      setWeekOffset(Math.floor(index / 7));
      setView("week");
    } else {
      // 空日子：仍切到周视图（最近的一周）并直接开新建面板
      const before = allDays.filter((d) => d < dayKey).length;
      setWeekOffset(Math.max(0, Math.min(Math.floor((before - 1) / 7),
        Math.ceil(allDays.length / 7) - 1)));
      setView("week");
      openCreate(dayKey, 9);
    }
  }

  // 审查修复：翻页上限与 days 用同一份 allDays（含拆分出的凌晨段日），
  // 否则最后一天可能永远翻不到
  const totalWeeks = Math.ceil(allDays.length / 7);
  const overloaded = snapshot.data?.overload_signal ?? false;

  // 「睡眠-负荷平衡」周合计（2026-08-02 用户裁定）：按当前显示周的原始块
  // 求和（不含 PLAN- 投影与 ~am 显示段），生理开销固定 24.5h（3.5×7）。
  const weekStats = useMemo(() => {
    const keys = new Set(days.map((d) => d.key));
    const hoursOf = (b: AvailabilityBlock) => {
      const ms = new Date(b.span.end).getTime() - new Date(b.span.start).getTime();
      return (ms > 0 ? ms : ms + 86_400_000) / 3_600_000;
    };
    let sleep = 0, course = 0, busy = 0, buffer = 0, flexible = 0, prot = 0;
    for (const b of blocks.data ?? []) {
      if (b.block_id.startsWith("PLAN-")) continue;
      if (!keys.has(b.span.start.slice(0, 10))) continue;
      const dur = hoursOf(b);
      if (b.block_id.includes("sleep")) sleep += dur;
      else if ((b as { source?: string }).source === "course_timetable") course += dur;
      else if (b.type === "busy") busy += dur;
      else if (b.type === "buffer") buffer += dur;
      else if (b.type === "flexible") flexible += dur;
      else if (b.type === "protected") prot += dur;
    }
    const disposable =
      168 - sleep - course - busy - flexible - buffer - prot - 24.5;
    return { sleep, course, busy, buffer, disposable };
  }, [blocks.data, days]);

  /** 一个区块在网格里的位置，按分钟算，不按整点对齐——真实日程不落在整点上。 */
  function position(block: AvailabilityBlock) {
    const start = new Date(block.span.start);
    const end = new Date(block.span.end);
    const startHour = start.getUTCHours() + start.getUTCMinutes() / 60;
    const endHour = end.getUTCHours() + end.getUTCMinutes() / 60;
    const clampedStart = Math.max(startHour, DAY_START);
    const clampedEnd = Math.min(endHour <= startHour ? DAY_END : endHour, DAY_END);
    return {
      top: (clampedStart - DAY_START) * ROW_HEIGHT,
      height: Math.max(6, (clampedEnd - clampedStart) * ROW_HEIGHT),
      visible: clampedEnd > clampedStart,
    };
  }

  return (
    <>
      <PageHeader titleKey="calendar.title" leadKey="calendar.lead" />

      {snapshot.loading && <Loading />}
      {snapshot.error && <Failure error={snapshot.error} onRetry={snapshot.reload} />}

      {snapshot.data && (
        <Card className="mb-5" data-capacity-snapshot={snapshot.data.snapshot_id}>
          {/* 2026-08-02 用户裁定：换用「睡眠-负荷平衡」口径的周合计五项——
              剩余可支配 = 168 − 睡眠 − 课程 − 忙 − 弹性 − 缓冲 − 保护 −
              生理开销 24.5（3.5h×7，ATUS 口径）。原缓冲比/已安排条撤下。 */}
          <Grid min={168}>
            <Metric
              label={t("calendar.week.sleep")}
              value={weekStats.sleep.toFixed(1)}
              unit={t("calendar.hours")}
              tone={weekStats.sleep >= 49 ? "good" : "default"}
            />
            <Metric
              label={t("calendar.week.course")}
              value={weekStats.course.toFixed(1)}
              unit={t("calendar.hours")}
            />
            <Metric
              label={t("calendar.week.busy")}
              value={weekStats.busy.toFixed(1)}
              unit={t("calendar.hours")}
            />
            <Metric
              label={t("calendar.week.disposable")}
              value={weekStats.disposable.toFixed(1)}
              unit={t("calendar.hours")}
              tone={weekStats.disposable < 0 ? "warn" : "good"}
            />
            <Metric
              label={t("calendar.week.buffer")}
              value={weekStats.buffer.toFixed(1)}
              unit={t("calendar.hours")}
            />
          </Grid>
          <p className="t-micro mt-2 text-fg-faint" data-capacity-method>
            {t("calendar.week.method")}
          </p>
          {sleepPerDay == null && (
            <p className="ai-note t-micro mt-3 inline-block font-medium"
               data-sleep-reminder style={{ color: "var(--accent-deep)" }}>
              {t("calendar.sleepReminder")}
            </p>
          )}

          {overloaded && (
            <p
              className="t-meta mt-4 rounded-md p-3"
              data-overload
              style={{
                border: "1px solid var(--color-clay-500)",
                color: "var(--color-clay-600)",
                background: "var(--color-clay-100)",
              }}
            >
              <strong>{t("calendar.overload")}</strong> —{" "}
              {t("calendar.overload.explain")}
            </p>
          )}
        </Card>
      )}

      <Card>
        {/* 视图切换与日期翻页并入日历卡内（用户裁定 2026-08-01）：
            控件贴着它作用的对象（ui-ux-pro-max grouping & mapping） */}
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="t-section text-fg">
            {t(view === "week" ? "calendar.week" : "calendar.monthView")}
          </h2>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className="t-micro rounded-full px-2.5 py-1"
              data-calendar-fixture
              style={{
                border: "1px solid var(--hatch)",
                color: "var(--hatch-ink)",
                background: "color-mix(in srgb, var(--hatch) 9%, transparent)",
              }}
              title={t("calendar.fixture.explain")}
            >
              {t("calendar.fixture")}
            </span>
            <span
              className="t-micro rounded-full px-2.5 py-1"
              data-detail-tier={hasTitles ? "event_titles" : "free_busy_only"}
              style={{
                border: `1px solid ${hasTitles ? "var(--accent)" : "var(--line-strong)"}`,
                color: hasTitles ? "var(--accent-deep)" : "var(--fg-faint)",
              }}
            >
              {t(hasTitles ? "calendar.tier.titles" : "calendar.tier.freeBusy")}
            </span>
            {/* R7-C：周 / 月切换（Google Calendar 手感） */}
            <div
              className="ms-2 inline-flex gap-0.5 rounded-md border border-line bg-bg-sunk p-0.5"
              role="group"
              aria-label={t("calendar.viewSwitch")}
            >
              {(["week", "month"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  data-view-option={mode}
                  aria-pressed={view === mode}
                  onClick={() => setView(mode)}
                  className="pressable t-meta rounded-sm px-2.5 py-1"
                  style={{
                    background: view === mode ? "var(--accent-deep)" : "transparent",
                    color: view === mode ? "var(--accent-fg)" : "var(--fg-muted)",
                    fontWeight: view === mode ? 600 : 500,
                  }}
                >
                  {t(mode === "week" ? "calendar.view.week" : "calendar.view.month")}
                </button>
              ))}
            </div>
            {view === "week" ? (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  data-week-prev
                  disabled={weekOffset === 0}
                  onClick={() => setWeekOffset((w) => Math.max(0, w - 1))}
                  className="pressable t-meta rounded-sm border border-line px-2.5 py-1 text-fg-muted disabled:opacity-35"
                >
                  ←
                </button>
                <span className="t-mono px-1 text-fg-faint" data-week-label>
                  {weekLabel}
                </span>
                <button
                  type="button"
                  data-week-next
                  disabled={weekOffset >= totalWeeks - 1}
                  onClick={() => setWeekOffset((w) => w + 1)}
                  className="pressable t-meta rounded-sm border border-line px-2.5 py-1 text-fg-muted disabled:opacity-35"
                >
                  →
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-1">
                <button
                  type="button"
                  data-month-prev
                  disabled={monthIndex === 0}
                  onClick={() => setMonthIndex((i) => Math.max(0, i - 1))}
                  className="pressable t-meta rounded-sm border border-line px-2.5 py-1 text-fg-muted disabled:opacity-35"
                >
                  ←
                </button>
                <span className="t-mono px-1 text-fg-faint" data-month-label>
                  {monthCells.month}
                </span>
                <button
                  type="button"
                  data-month-next
                  disabled={monthIndex >= months.length - 1}
                  onClick={() => setMonthIndex((i) => i + 1)}
                  className="pressable t-meta rounded-sm border border-line px-2.5 py-1 text-fg-muted disabled:opacity-35"
                >
                  →
                </button>
              </div>
            )}
          </div>
        </div>

        {blocks.loading && <Loading />}
        {blocks.error && <Failure error={blocks.error} onRetry={blocks.reload} />}
        {days.length === 0 && !blocks.loading && <Empty />}

        {/* ── 月视图：分布一目了然，点进任何一天回到周视图编辑 ── */}
        {view === "month" && monthCells.cells.length > 0 && (
          <div data-month-grid>
            <div className="grid grid-cols-7 gap-1">
              {Array.from({ length: 7 }, (_, i) => (
                <div key={i} className="t-micro pb-1 text-center text-fg-faint">
                  {new Date(Date.UTC(2026, 5, 1 + i)).toLocaleDateString(locale, {
                    weekday: "short", timeZone: "UTC",
                  })}
                </div>
              ))}
              {monthCells.cells.map((cell, index) =>
                cell === null ? (
                  <div key={`blank-${index}`} />
                ) : (
                  <button
                    key={cell.key}
                    type="button"
                    data-month-day={cell.key}
                    data-month-day-count={cell.blocks.filter((b) => b.type !== "free").length}
                    onClick={() => jumpToDay(cell.key)}
                    className="pressable flex min-h-[72px] flex-col gap-0.5 rounded-sm border border-line bg-bg-sunk p-1.5 text-start"
                  >
                    <span className="t-micro text-fg-faint">
                      {Number(cell.key.slice(8, 10))}
                    </span>
                    {cell.blocks
                      .filter((b) => b.type !== "free")
                      .sort((a, b) => a.span.start.localeCompare(b.span.start))
                      .slice(0, 3)
                      .map((block) => (
                        <span
                          key={block.block_id}
                          data-month-chip={block.block_id}
                          className="t-micro block truncate rounded-xs px-1"
                          style={{
                            ...blockStyle(block),
                            letterSpacing: 0,
                            textTransform: "none",
                          }}
                        >
                          {block.title ??
                            `${block.span.start.slice(11, 16)} ${t(TYPE_KEY[block.type] ?? "calendar.block.busy")}`}
                        </span>
                      ))}
                    {cell.blocks.filter((b) => b.type !== "free").length > 3 && (
                      <span className="t-micro text-fg-faint">
                        +{cell.blocks.filter((b) => b.type !== "free").length - 3}
                      </span>
                    )}
                  </button>
                ),
              )}
            </div>
          </div>
        )}

        {view === "week" && days.length > 0 && (
          <div className="overflow-x-auto">
            <div className="flex min-w-[680px] gap-1" data-week-grid>
              {/* 时间刻度 */}
              <div className="w-11 shrink-0 pt-6">
                {HOURS.map((hour) => (
                  <div
                    key={hour}
                    className="t-micro text-end text-fg-faint"
                    style={{ height: ROW_HEIGHT, lineHeight: `${ROW_HEIGHT}px` }}
                  >
                    {String(hour).padStart(2, "0")}
                  </div>
                ))}
              </div>

              {days.map((day) => (
                <div key={day.key} className="min-w-0 flex-1" data-day={day.key}>
                  <div className="t-micro mb-1 h-5 truncate text-center text-fg-faint">
                    {day.label}
                  </div>
                  <div
                    className="relative cursor-cell rounded-sm border border-line bg-bg-sunk"
                    style={{ height: HOURS.length * ROW_HEIGHT }}
                    data-day-grid={day.key}
                    onClick={(e) => {
                      // A：点空白格 = 在该时段添加行程（Google Calendar 手感）
                      const rect = e.currentTarget.getBoundingClientRect();
                      const hour =
                        DAY_START + Math.floor((e.clientY - rect.top) / ROW_HEIGHT);
                      openCreate(day.key, hour);
                    }}
                  >
                    {/* 整点横线：只画每 3 小时一条，密了会盖过内容 */}
                    {HOURS.map((hour, index) =>
                      index % 3 === 0 ? (
                        <div
                          key={hour}
                          className="absolute inset-x-0 border-t border-line"
                          style={{ top: index * ROW_HEIGHT }}
                        />
                      ) : null,
                    )}

                    {day.blocks.map((block) => {
                      const { top, height, visible } = position(block);
                      if (!visible || block.type === "free") return null;
                      return (
                        <button
                          type="button"
                          key={block.block_id}
                          data-block={block.block_id}
                          data-block-type={block.type}
                          data-block-has-title={block.title ? "true" : "false"}
                          title={
                            block.title ??
                            t(TYPE_KEY[block.type] ?? "calendar.block.busy")
                          }
                          onClick={(e) => {
                            e.stopPropagation();  // 点块 = 看详情，编辑在详情面板里
                            // 凌晨显示段 → 详情/编辑都指向跨午夜的原块
                            setDetail(displayToOriginal.get(block.block_id) ?? block);
                            setEditor(null);
                          }}
                          className="pressable absolute inset-x-[2px] overflow-hidden rounded-xs px-1 text-start"
                          style={{ top, height, ...blockStyle(block) }}
                        >
                          {/* 标题只有在二级授权或学生自己命名时才存在。没有就不写，
                              **不填一个"忙"字充数**——那会让两种层级看起来一样。 */}
                          {block.title && height >= 20 && (
                            <span
                              className="t-micro block truncate"
                              style={{ letterSpacing: 0, textTransform: "none" }}
                            >
                              {block.title}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <ul className="mt-5 flex flex-wrap gap-3" data-calendar-legend>
          {Object.keys(TYPE_KEY).map((type) => (
            <li key={type} className="t-meta flex items-center gap-1.5 text-fg-muted">
              <span
                aria-hidden
                className="inline-block h-3 w-3 rounded-[3px]"
                style={{
                  background: TYPE_COLOR[type],
                  border: type === "free" ? "1px solid var(--line-strong)" : "none",
                }}
              />
              {t(TYPE_KEY[type])}
            </li>
          ))}
          {/* 睡眠不是 block.type，是 block_id 约定的渲染时特判（浅蓝
              mist-100），所以图例循环吃不到它——单列一项（用户需求 C）。
              浅底加细边框，防止色块在页面底色上不可读（同 free 的处理）。 */}
          <li className="t-meta flex items-center gap-1.5 text-fg-muted"
              data-legend-sleep>
            <span
              aria-hidden
              className="inline-block h-3 w-3 rounded-[3px]"
              style={{
                background: "var(--color-mist-100)",
                border: "1px solid var(--color-mist-700)",
              }}
            />
            {t("calendar.routine.sleep")}
          </li>
          {/* 用户裁定 B：课程（教务同步）与规划中活动各有独立图例 */}
          <li className="t-meta flex items-center gap-1.5 text-fg-muted"
              data-legend-course>
            <span aria-hidden className="inline-block h-3 w-3 rounded-[3px]"
                  style={{ background: COURSE_COLOR }} />
            {t("calendar.legend.course")}
          </li>
          <li className="t-meta flex items-center gap-1.5 text-fg-muted"
              data-legend-planned>
            <span aria-hidden className="inline-block h-3 w-3 rounded-[3px]"
                  style={{
                    background: "color-mix(in srgb, var(--accent) 12%, transparent)",
                    border: "2px dashed var(--accent-deep)",
                  }} />
            {t("calendar.legend.planned")}
          </li>
        </ul>

        {/* 行程详情面板（2026-08-02 用户需求）：只读，Google 日历式。
            字段有才显示——契约里没有的（如参与人）不编造。 */}
        {detail && (() => {
          const fmt = (iso: string) =>
            `${iso.slice(0, 10)} ${iso.slice(11, 16)}`;
          const isPlan = detail.block_id.startsWith("PLAN-");
          const planSegs = isPlan
            ? planDetails.get(detail.block_id.replace("PLAN-", "")) ?? []
            : [];
          const oppId = detail.block_id.match(/-plan-(OPP-[A-Za-z0-9-]+)/)?.[1];
          const opp = oppId
            ? (plannedCatalog.data ?? []).find((o) => o.opportunity_id === oppId)
            : null;
          const kindLabel = detail.block_id.includes("sleep")
            ? t("calendar.routine.sleep")
            : isPlan ? t("calendar.legend.planned")
            : (detail as { source?: string }).source === "course_timetable"
              ? t("calendar.legend.course")
              : t(TYPE_KEY[detail.type] ?? "calendar.block.busy");
          return (
            <div className="mt-4 rounded-md border border-line bg-bg-sunk p-4"
                 data-block-detail={detail.block_id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="t-section text-fg" data-detail-title>
                    {detail.title ?? kindLabel}
                  </div>
                  <div className="t-meta mt-1 text-fg-muted" data-detail-time>
                    {t("calendar.detail.time")}: {fmt(detail.span.start)} → {fmt(detail.span.end)}
                    <span className="ms-3">{t("calendar.detail.kind")}: {kindLabel}</span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {!isPlan && (
                    <button type="button" data-detail-edit
                            className="pressable btn btn-secondary t-meta"
                            onClick={() => {
                              openEdit(detail);
                              setDetail(null);
                            }}>
                      {t("calendar.detail.edit")}
                    </button>
                  )}
                  <button type="button" data-detail-close
                          className="pressable btn btn-ghost t-meta"
                          onClick={() => setDetail(null)}>
                    ✕
                  </button>
                </div>
              </div>
              {opp?.provenance?.evidence_snippet && (
                <p className="t-meta mt-2 max-w-[70ch] text-fg-muted" data-detail-brief>
                  {t("calendar.detail.brief")}: {opp.provenance.evidence_snippet}
                </p>
              )}
              {opp?.official_url && (
                <a href={opp.official_url} target="_blank" rel="noreferrer"
                   data-detail-official
                   className="t-meta mt-2 inline-block underline underline-offset-2"
                   style={{ color: "var(--accent-deep)" }}>
                  {t("calendar.detail.official")} ↗
                </a>
              )}
              {planSegs.length > 0 && (
                <ul className="mt-2 flex flex-col gap-2">
                  {planSegs.map((seg, index) => (
                    <li key={index} className="t-meta text-fg-muted" data-detail-plan-seg>
                      <span className="text-fg">{seg.title}</span>
                      <span className="ms-2">{fmt(seg.start)} → {fmt(seg.end)}</span>
                      {seg.brief && (
                        <span className="ms-2">{t("calendar.detail.brief")}: {seg.brief}</span>
                      )}
                      {seg.url && (
                        <a href={seg.url} target="_blank" rel="noreferrer"
                           className="ms-2 underline underline-offset-2"
                           style={{ color: "var(--accent-deep)" }}>
                          {t("calendar.detail.official")} ↗
                        </a>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })()}

        {/* A：就地编辑面板——点块或点空白格后出现在网格正下方 */}
        {editor && (
          <div
            className="mt-4 rounded-md border p-4"
            data-slot-editor
            style={{ borderColor: "var(--accent)", background: "var(--accent-soft)" }}
          >
            <div className="t-body mb-3 font-medium text-fg">
              {editor.mode === "create"
                ? `${t("calendar.editor.createTitle")} · ${editor.day}`
                : `${t("calendar.editor.editTitle")} · ${editor.block.span.start.slice(0, 10)}`}
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className="t-micro text-fg-muted">{t("calendar.editor.label")}</span>
                <input
                  type="text"
                  data-editor-title
                  value={form.title}
                  onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))}
                  placeholder={t("calendar.editor.labelHint")}
                  className="t-body w-56 rounded-md border border-line bg-card px-2.5 py-1.5 text-fg"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="t-micro text-fg-muted">{t("calendar.editor.start")}</span>
                <input
                  type="time" data-editor-start value={form.start}
                  onChange={(e) => setForm((f) => ({ ...f, start: e.target.value }))}
                  className="t-body rounded-md border border-line bg-card px-2 py-1.5 text-fg"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="t-micro text-fg-muted">{t("calendar.editor.end")}</span>
                <input
                  type="time" data-editor-end value={form.end}
                  onChange={(e) => setForm((f) => ({ ...f, end: e.target.value }))}
                  className="t-body rounded-md border border-line bg-card px-2 py-1.5 text-fg"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="t-micro text-fg-muted">{t("calendar.editor.type")}</span>
                <select
                  data-editor-type value={form.type}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, type: e.target.value as typeof f.type }))
                  }
                  className="t-body rounded-md border border-line bg-card px-2 py-1.5 text-fg"
                >
                  {(["busy", "flexible", "protected", "buffer"] as const).map((x) => (
                    <option key={x} value={x}>{t(TYPE_KEY[x])}</option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="t-micro text-fg-muted">{t("calendar.editor.reminder")}</span>
                <select
                  data-editor-reminder value={form.reminder}
                  onChange={(e) => setForm((f) => ({ ...f, reminder: e.target.value }))}
                  className="t-body rounded-md border border-line bg-card px-2 py-1.5 text-fg"
                >
                  <option value="">{t("calendar.editor.reminderNone")}</option>
                  {["10", "30", "60"].map((m) => (
                    <option key={m} value={m}>
                      {m} min
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {editor.mode === "edit" && officialLinkOf(editor.block) && (
              <a
                href={officialLinkOf(editor.block)!}
                target="_blank"
                rel="noreferrer"
                data-editor-official
                className="t-meta mt-2 inline-block underline underline-offset-2"
                style={{ color: "var(--accent-deep)" }}
              >
                {t("calendar.editor.official")} ↗
              </a>
            )}
            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button" data-editor-save onClick={saveEditor}
                className="pressable btn btn-primary t-meta font-medium"
              >
                {t("calendar.editor.save")}
              </button>
              {editor.mode === "edit" && (
                <button
                  type="button" data-editor-delete
                  onClick={() => removeBlock(editor.block.block_id)}
                  className="pressable btn btn-danger t-meta"
                >
                  {t("calendar.edit.remove")}
                </button>
              )}
              <button
                type="button" data-editor-cancel onClick={() => setEditor(null)}
                className="pressable btn btn-secondary t-meta"
              >
                {t("calendar.editor.cancel")}
              </button>
            </div>
          </div>
        )}

        {/* H：改完由学生决定要不要重排近两周 */}
        {edited && (
          <div className="mt-4 rounded-md p-3"
               data-replan-ask
               style={{ border: "1px solid var(--hatch)",
                        background: "color-mix(in srgb, var(--hatch) 8%, transparent)" }}>
            <p className="t-body text-fg">{t("calendar.edit.replanAsk")}</p>
            <div className="mt-2 flex gap-2">
              <button type="button" data-replan-yes
                      onClick={() => confirmReplan(true)}
                      className="pressable btn btn-primary t-meta font-medium">
                {t("calendar.edit.replanYes")}
              </button>
              <button type="button" data-replan-no
                      onClick={() => confirmReplan(false)}
                      className="pressable btn btn-secondary t-meta">
                {t("calendar.edit.replanNo")}
              </button>
            </div>
          </div>
        )}
        {replanScope && (
          <p className="t-meta mt-2" data-replan-scope style={{ color: "var(--color-moss-600)" }}>
            {t("calendar.edit.replanned").replace("{scope}", replanScope)}
          </p>
        )}

        <p className="t-meta mt-4 max-w-[62ch] text-fg-faint" data-tier-explain>
          {t(hasTitles ? "calendar.tier.titles.explain" : "calendar.tier.freeBusy.explain")}
        </p>
        <p className="t-meta mt-2 max-w-[62ch] text-fg-faint" data-capacity-explain>
          {t("calendar.capacity.explain")}
        </p>
      </Card>

      {/* M：日常作息——放在日历下方（用户裁定 2026-08-01）。
          学生显式提交，生成每天的保护时段（§16.8.2 不从日历反推） */}
      <RoutineCard
        studentId={studentId}
        onSubmitted={() => {
          blocks.reload();
          snapshot.reload();
        }}
      />
    </>
  );
}
