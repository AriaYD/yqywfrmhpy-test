#!/usr/bin/env node
/**
 * verify-feedback-round.mjs — 2026-08-02 验收反馈五批修复的一次性浏览器实测。
 *
 * 逐项断言 + 截图存 docs/verification/feedback-round/。任何断言失败 exit 1。
 * 前置：Chrome :9222 + dev server :3100 + 本地 api :8000（新代码）。
 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const base = "http://127.0.0.1:3100";
const api = "http://127.0.0.1:8000";
const shotDir = new URL("../../../docs/verification/feedback-round/", import.meta.url)
  .pathname;
mkdirSync(shotDir, { recursive: true });

const H = { "X-CampusPath-Role": "student", "Content-Type": "application/json" };
async function apiCall(method, path, body) {
  const res = await fetch(`${api}${path}`, {
    method, headers: H, body: body ? JSON.stringify(body) : undefined,
  });
  return { status: res.status, body: await res.json().catch(() => null) };
}

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
async function goto(path) {
  await page.goto(`${base}${path}`, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 2500));
}
const shot = (name) =>
  page.screenshot({ path: `${shotDir}${name}.png` });

try {
  // ── 服务端预置：启用国际生 + 造一个软冲突提案 ────────────────────
  await apiCall("POST", "/v1/students/STU-A/consents",
    { scope: "context_pack", granted: true });
  await apiCall("POST", "/v1/students/STU-A/profile/self-edit", {
    intl_context: {
      study_jurisdiction: "HK-SAR", intended_work_jurisdiction: "HK-SAR",
      study_mode: "full_time", permission_category: "student_visa",
      permission_expiry_date: "2027-06-30", intended_start_date: "2026-09-01",
      school_approval: null, employer_sponsorship_expected: null,
      language_evidence: ["IELTS 6.5"], target_cities: ["Hong Kong"],
      updated_at: "2026-08-02T00:00:00Z",
    },
  });
  const avail = (await apiCall("GET", "/v1/students/STU-A/availability")).body;
  const busy = avail.find((b) => b.type === "busy");
  const catalogRows = (await apiCall("GET", "/v1/catalog/opportunities?limit=5")).body;
  const opp = catalogRows[0];
  await apiCall("POST", "/v1/students/STU-A/schedule-proposals", {
    proposal_id: `SP-VERIFY-${opp.opportunity_id}`, student_id: "STU-A",
    plan_item_ids: [`PI-VERIFY-${opp.opportunity_id}`],
    proposed_slots: [{
      plan_item_id: `PI-VERIFY-${opp.opportunity_id}`,
      span: busy.span, conflicts: [],
    }],
    assumptions: [], student_decision: "pending", calendar_action_ids: [],
  });
  // 档案提议（复现用户 500 的形状）
  await apiCall("POST", "/v1/students/STU-A/profile/proposals", {
    proposal_id: "PROP-RESUME-UI", student_id: "STU-A",
    proposed_changes: [
      { entity_type: "skill", operation: "add", field_path: "skills[]",
        old_value: null, new_value: "Kotlin" },
      { entity_type: "experience", operation: "add", field_path: "experiences[]",
        old_value: null,
        new_value: { organization: "Verify Org", role: "Tester" } },
    ],
    reason: "来自 Resume「verify.md」的候选变更（待确认）",
    impact: "medium", status: "pending", created_at: "2026-08-02T00:00:00Z",
  });

  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.setItem("campuspath.session",
      JSON.stringify({ portal: "student", studentId: "STU-A" }));
  });

  // ── 1. 目标工作室：信心条撤下 + 配比控件 ─────────────────────────
  await goto("/goals");
  const goalsProbe = await page.evaluate(() => ({
    confidenceBars: document.body.textContent.includes("信心") &&
      !!document.querySelector("[data-goal] [data-bar]"),
    confidenceWord: [...document.querySelectorAll("[data-goal]")]
      .some((el) => el.textContent.includes("信心")),
    splitCard: !!document.querySelector("[data-goal-split-card]"),
    splitValue: document.querySelector("[data-goal-split]")?.value ?? null,
  }));
  ok("goals: 目标卡无信心条", !goalsProbe.confidenceWord);
  ok("goals: 配比控件在场（主/副双目标）", goalsProbe.splitCard,
     JSON.stringify(goalsProbe));
  await shot("01-goals-split-no-confidence");

  // ── 2. 规划页：成长曲线口径 + 国际生官方指引 ─────────────────────
  await goto("/timeline");
  const planProbe = await page.evaluate(() => {
    const txt = document.querySelector("main")?.textContent ?? "";
    const guidance = [...document.querySelectorAll("[data-intl-guidance]")]
      .map((e) => e.textContent);
    return {
      gapsClosedShown: txt.includes("已关闭差距"),
      confidenceShown: txt.includes("目标信心"),
      method: !!document.querySelector("[data-trajectory-method]"),
      intlNotes: document.querySelectorAll("[data-intl-plan-note]").length,
      guidanceWithImmd: guidance.filter((t) => t.includes("immd.gov.hk")).length,
      ruleGeneratedOnIntl: [...document.querySelectorAll("[data-intl-plan-note]")]
        .some((e) => e.textContent.includes("规则生成")),
      links: document.querySelectorAll("[data-intl-guidance] a").length,
    };
  });
  ok("plans: 假指标已撤（无已关闭差距/目标信心）",
     !planProbe.gapsClosedShown && !planProbe.confidenceShown);
  ok("plans: 口径说明在场", planProbe.method);
  ok("plans: 国际生条目带官方指引链接",
     planProbe.intlNotes > 0 && planProbe.guidanceWithImmd > 0
       && planProbe.links > 0, JSON.stringify(planProbe));
  ok("plans: 国际生条目无「规则生成」复读", !planProbe.ruleGeneratedOnIntl);
  await shot("02-plans-trajectory-intl-guidance");

  // ── 3. 行动中心：软冲突警示 → 批准 → ⚠️ ─────────────────────────
  await goto("/actions");
  const softShown = await page.evaluate(
    () => !!document.querySelector("[data-soft-conflict]"));
  ok("actions: 非阻断冲突警示在场", softShown);
  await shot("03-actions-soft-conflict");
  if (softShown) {
    await page.evaluate(() => {
      const card = document.querySelector("[data-soft-conflict]")
        ?.closest("[data-schedule-proposal]");
      card?.querySelector("[data-approve]")?.click();
    });
    await new Promise((r) => setTimeout(r, 2500));
    const pathway = (await apiCall("GET", "/v1/students/STU-A/pathway")).body;
    const marked = pathway.plan_items.find((i) =>
      i.title.zh_Hans.startsWith("⚠️"));
    ok("actions: 批准后条目带 ⚠️", !!marked,
       JSON.stringify(pathway.plan_items.map((i) => i.title.zh_Hans).slice(-4)));
  }

  // ── 4. 日历：黄色保护 + 课程/规划图例 ────────────────────────────
  await goto("/calendar");
  const calProbe = await page.evaluate(() => {
    const legend = document.querySelector("[data-calendar-legend]");
    const items = [...(legend?.querySelectorAll("li") ?? [])]
      .map((li) => li.textContent.trim());
    const protectedSwatch = [...(legend?.querySelectorAll("li") ?? [])]
      .find((li) => li.textContent.includes("保护"))
      ?.querySelector("span")?.style.background ?? "";
    return {
      items,
      protectedIsHatch: protectedSwatch.includes("hatch"),
      courseLegend: items.some((t) => t.includes("课程")),
      plannedLegend: items.some((t) => t.includes("规划中")),
      courseBlocks: [...document.querySelectorAll("[data-block]")].length,
    };
  });
  ok("calendar: 保护图例为黄（--hatch）", calProbe.protectedIsHatch,
     JSON.stringify(calProbe.items));
  ok("calendar: 课程与规划中图例在场",
     calProbe.courseLegend && calProbe.plannedLegend);
  await shot("04-calendar-legend-colors");

  // ── 5. 广场：活动时间 + 发布时间 + 最新在前 ──────────────────────
  await goto("/square");
  const squareProbe = await page.evaluate(() => {
    const times = document.querySelectorAll("[data-square-event-time]").length;
    const pubs = [...document.querySelectorAll("[data-square-published]")]
      .map((e) => e.textContent.replace(/[^0-9-]/g, "").slice(0, 10));
    const sortedDesc = pubs.every(
      (v, i) => i === 0 || pubs[i - 1] >= v);
    return { times, pubCount: pubs.length, first: pubs[0], sortedDesc };
  });
  ok("square: 活动时间与发布时间在场",
     squareProbe.times > 0 && squareProbe.pubCount > 0,
     JSON.stringify(squareProbe));
  ok("square: 发布时间降序（最新在前）", squareProbe.sortedDesc);
  await shot("05-square-times-sorted");

  // ── 6. 档案：提议确认不再 500、技能落库 ──────────────────────────
  await goto("/profile");
  const confirmed = await page.evaluate(async () => {
    const res = await fetch(
      "/api/v1/students/STU-A/profile/proposals/PROP-RESUME-UI/decision"
      + "?decision=confirmed",
      { method: "POST", headers: { "X-CampusPath-Role": "student" } });
    const profile = await fetch("/api/v1/students/STU-A/profile",
      { headers: { "X-CampusPath-Role": "student" } }).then((r) => r.json());
    return { status: res.status, hasKotlin: profile.interests.includes("Kotlin") };
  });
  ok("profile: 确认提议 200（曾 500）", confirmed.status === 200,
     String(confirmed.status));
  ok("profile: 技能写入标签池", confirmed.hasKotlin);
  await shot("06-profile-confirm");

  // ── 7. console：状态灯 + 一键刷新按钮 ────────────────────────────
  await page.evaluate(() => {
    localStorage.setItem("campuspath.session",
      JSON.stringify({ portal: "institution", role: "career_center_admin" }));
  });
  await goto("/console");
  const consoleProbe = await page.evaluate(() => ({
    lights: document.querySelectorAll("[data-src-light]").length,
    sweepBtn: !!document.querySelector("[data-sources-sweep]"),
  }));
  ok("console: 每源状态灯", consoleProbe.lights >= 90,
     JSON.stringify(consoleProbe));
  ok("console: 一键刷新按钮", consoleProbe.sweepBtn);
  await shot("07-console-lights-sweep");
} finally {
  await page.close();
  browser.disconnect();
}
console.log(failures === 0
  ? "verify-feedback-round: all green"
  : `verify-feedback-round: ${failures} failures`);
process.exit(failures === 0 ? 0 : 1);
