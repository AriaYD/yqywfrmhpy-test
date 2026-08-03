#!/usr/bin/env node
/**
 * 计划→日历贯通实测（2026-08-02 用户验收标准）：
 * 1) 首日凌晨睡眠块不缺角；2) 规划标签与日历同口径（活动真实日期）；
 * 3) 「课外活动规划」的活动以规划块显示在日历对应日期；
 * 4) 行动中心真实点击「批准」→ 活动自动写入日历成真实块。
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const base = "http://127.0.0.1:3100";
const shotDir = new URL("../../../docs/verification/plan-to-calendar/", import.meta.url).pathname;
mkdirSync(shotDir, { recursive: true });

const browser = await puppeteer.connect({
  browserURL: "http://127.0.0.1:9222",
  defaultViewport: { width: 1280, height: 900 },
});
const page = await browser.newPage();
let failures = 0;
const ok = (name, cond, detail = "") => {
  if (cond) console.log(`  ok  ${name}`);
  else { failures += 1; console.log(`FAIL ${name}  ${detail}`); }
};
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const sfetch = (path, opts) => page.evaluate(async (p, o) => {
  const res = await fetch(`/api${p}`, {
    headers: { "X-CampusPath-Role": "student", "Content-Type": "application/json" },
    ...(o ?? {}),
  });
  return { status: res.status, body: await res.json().catch(() => null) };
}, path, opts);

async function pageWeeksUntil(pred, max = 20) {
  for (let i = 0; i < max; i++) {
    const found = await page.evaluate(pred);
    if (found) return true;
    const moved = await page.evaluate(() => {
      const next = [...document.querySelectorAll("button")]
        .find((b) => b.textContent.trim() === "→" && !b.disabled);
      if (next) { next.click(); return true; }
      return false;
    });
    if (!moved) return false;
    await sleep(500);
  }
  return false;
}

try {
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.clear();
    localStorage.setItem("campuspath.session",
      JSON.stringify({ portal: "student", studentId: "STU-A" }));
  });

  // ── 0. 预置：作息（跨午夜睡眠）+ 日历写入授权 ────────────────────
  await sfetch("/v1/students/STU-A/routine", {
    method: "POST",
    body: JSON.stringify({ sleep: { start: "23:00", end: "07:30" },
                           meals: [{ start: "12:00", end: "13:00" }] }),
  });
  await sfetch("/v1/students/STU-A/consents", {
    method: "POST",
    body: JSON.stringify({ scope: "calendar_write", granted: true }),
  });

  // ── 1. 首日凌晨睡眠块 ────────────────────────────────────────────
  await page.goto(`${base}/calendar`, { waitUntil: "domcontentloaded" });
  await sleep(3000);
  const first = await page.evaluate(() => {
    const grid = document.querySelector("[data-day-grid]");
    return {
      day: grid?.getAttribute("data-day-grid"),
      sleep: [...(grid?.querySelectorAll("[data-block]") ?? [])]
        .some((b) => b.getAttribute("data-block").includes("sleep")),
    };
  });
  ok("首日凌晨有睡眠块（不再缺角）", first.sleep, JSON.stringify(first));
  await page.screenshot({ path: `${shotDir}01-first-morning-sleep.png` });

  // ── 2. 规划标签口径：真实活动日期 ────────────────────────────────
  const pathway = (await sfetch("/v1/students/STU-A/pathway")).body;
  const challenge = pathway.plan_items.find((i) => i.subject_id === "OPP-CMP-001");
  ok("规划条目用活动真实日期（11-24）",
     challenge?.date_range.start === "2026-11-24", JSON.stringify(challenge?.date_range));

  // ── 3. 规划中的活动出现在日历对应日期 ────────────────────────────
  const reached = await pageWeeksUntil(() =>
    [...document.querySelectorAll("[data-block]")]
      .some((b) => b.getAttribute("data-block").startsWith("PLAN-")));
  const planShot = await page.evaluate(() => ({
    label: document.querySelector("main")?.textContent
      .match(/2026-\d\d-\d\d → 2026-\d\d-\d\d/)?.[0],
    titles: [...document.querySelectorAll('[data-block^="PLAN-"]')]
      .map((b) => b.getAttribute("title")).slice(0, 3),
  }));
  ok("「课外活动规划」的活动以规划块显示在日历", reached, JSON.stringify(planShot));
  await page.screenshot({ path: `${shotDir}02-planned-blocks-on-calendar.png` });

  // ── 4. 行动中心点「批准」→ 自动写入日历 ──────────────────────────
  // 造一个待批准提案：取一个有真实时间的活动（OPP-EVT-001，11-19）
  const opp = (await sfetch("/v1/catalog/opportunities?limit=500")).body
    .find((o) => o.opportunity_id === "OPP-EVT-001");
  const proposal = {
    proposal_id: "SP-APPLY-OPP-EVT-001", student_id: "STU-A",
    plan_item_ids: ["PI-APPLY-OPP-EVT-001"],
    proposed_slots: [{
      plan_item_id: "PI-APPLY-OPP-EVT-001",
      span: { start: opp.starts_at, end: opp.ends_at },
      conflicts: [],
    }],
    assumptions: [], student_decision: "pending", calendar_action_ids: [],
  };
  const posted = await sfetch("/v1/students/STU-A/schedule-proposals",
    { method: "POST", body: JSON.stringify(proposal) });
  ok("待批准提案就位", posted.status === 200, String(posted.status));

  await page.goto(`${base}/actions`, { waitUntil: "domcontentloaded" });
  await sleep(3000);
  const approved = await page.evaluate(async () => {
    const btn = document.querySelector('[data-approve="SP-APPLY-OPP-EVT-001"]');
    if (!btn) return { clicked: false };
    btn.click();
    await new Promise((r) => setTimeout(r, 3500));
    return { clicked: true,
             outcome: document.body.textContent.includes("已写入") ||
                      !document.querySelector('[data-approve="SP-APPLY-OPP-EVT-001"]') };
  });
  ok("行动中心真实点击批准", approved.clicked, JSON.stringify(approved));
  await page.screenshot({ path: `${shotDir}03-approve-clicked.png` });

  // 日历上应出现真实写入块（AB-STU-A-plan-OPP-EVT-001，11-19，带活动名）
  await page.goto(`${base}/calendar`, { waitUntil: "domcontentloaded" });
  await sleep(3000);
  const found = await pageWeeksUntil(() =>
    [...document.querySelectorAll("[data-block]")]
      .some((b) => b.getAttribute("data-block").includes("plan-OPP-EVT-001")));
  const written = await page.evaluate(() => {
    const el = [...document.querySelectorAll("[data-block]")]
      .find((b) => b.getAttribute("data-block").includes("plan-OPP-EVT-001"));
    return { title: el?.getAttribute("title"),
             label: document.querySelector("main")?.textContent
               .match(/2026-\d\d-\d\d → 2026-\d\d-\d\d/)?.[0] };
  });
  ok("批准的活动自动落进日历（真实块，带活动名）",
     found && !!written.title, JSON.stringify(written));
  await page.screenshot({ path: `${shotDir}04-approved-activity-on-calendar.png` });
  // ── 5. 行程详情面板（2026-08-02 追加需求）─────────────────────────
  // 回到首周，点一个课程块 → 只读详情（标题/时间/类型/编辑入口）
  await page.goto(`${base}/calendar`, { waitUntil: "domcontentloaded" });
  await sleep(3000);
  const courseDetail = await page.evaluate(async () => {
    const el = [...document.querySelectorAll("[data-block]")]
      .find((b) => (b.getAttribute("title") ?? "").includes("HUMA"));
    if (!el) return { found: false };
    el.click();
    await new Promise((r) => setTimeout(r, 600));
    const panel = document.querySelector("[data-block-detail]");
    return {
      found: true,
      panel: !!panel,
      title: panel?.querySelector("[data-detail-title]")?.textContent ?? "",
      time: !!panel?.querySelector("[data-detail-time]"),
      edit: !!panel?.querySelector("[data-detail-edit]"),
      notEditor: !document.querySelector("[data-slot-editor]"),
    };
  });
  ok("详情面板：点课程块出只读详情（非编辑态）",
     courseDetail.panel && courseDetail.time && courseDetail.edit
       && courseDetail.notEditor && courseDetail.title.includes("HUMA"),
     JSON.stringify(courseDetail));
  await page.screenshot({ path: `${shotDir}06-detail-course.png` });
  // 规划块详情：含活动名/时间/官方链接
  await pageWeeksUntil(() =>
    [...document.querySelectorAll("[data-block]")]
      .some((b) => b.getAttribute("data-block").startsWith("PLAN-")));
  const planDetail = await page.evaluate(async () => {
    const el = [...document.querySelectorAll("[data-block]")]
      .find((b) => b.getAttribute("data-block").startsWith("PLAN-"));
    el?.click();
    await new Promise((r) => setTimeout(r, 600));
    const panel = document.querySelector("[data-block-detail]");
    return {
      panel: !!panel,
      segs: panel?.querySelectorAll("[data-detail-plan-seg]").length ?? 0,
      links: panel?.querySelectorAll("a[href^='http']").length ?? 0,
      text: panel?.textContent.slice(0, 120) ?? "",
    };
  });
  ok("详情面板：规划块列出活动明细与官方链接",
     planDetail.panel && planDetail.segs > 0 && planDetail.links > 0,
     JSON.stringify(planDetail));
  await page.evaluate(() => {
    const el = document.querySelector("[data-block-detail]");
    el?.scrollIntoView({ block: "center" });
  });
  await sleep(400);
  await page.screenshot({ path: `${shotDir}07-detail-planned.png` });
} finally {
  await page.close();
  browser.disconnect();
}
console.log(failures === 0 ? "verify-plan-to-calendar: all green"
  : `verify-plan-to-calendar: ${failures} failures`);
process.exit(failures === 0 ? 0 : 1);
