#!/usr/bin/env node
/** 「睡眠-负荷平衡」批浏览器实测：容量五项/身心容量卡/预警弹窗两级。 */
import puppeteer from "puppeteer-core";
import { mkdirSync } from "node:fs";

const base = "http://127.0.0.1:3100";
const shotDir = new URL("../../../docs/verification/balance-round/", import.meta.url).pathname;
mkdirSync(shotDir, { recursive: true });

const browser = await puppeteer.connect({
  browserURL: "http://127.0.0.1:9222",
  defaultViewport: { width: 1280, height: 900 },
});
let failures = 0;
const ok = (name, cond, detail = "") => {
  if (cond) console.log(`  ok  ${name}`);
  else { failures += 1; console.log(`FAIL ${name}  ${detail}`); }
};

async function newStudentPage(escalationMock) {
  const page = await browser.newPage();
  if (escalationMock) {
    await page.setRequestInterception(true);
    page.on("request", (req) => {
      if (req.url().includes("/wellbeing/escalation")) {
        req.respond({
          status: 200, contentType: "application/json",
          body: JSON.stringify(escalationMock),
        });
      } else req.continue();
    });
  }
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.clear();
    localStorage.setItem("campuspath.session",
      JSON.stringify({ portal: "student", studentId: "STU-A" }));
  });
  return page;
}
const esc = (tier, extra = {}) => ({
  student_id: "STU-A", declared_sleep_hours: 6.5,
  sleep_deficit_consecutive_days: 0, data_coverage_days: 28,
  qualifying_days_14: 11, qualifying_days_28: 21,
  last_assessment_at: null, overload_now: false,
  refused_or_deferred_30d: 0, tier, reasons: [], ...extra,
});

try {
  // 1) 日历五项周合计 + 已安排条撤下
  let page = await newStudentPage(null);
  await page.goto(`${base}/calendar`, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 3000));
  const cal = await page.evaluate(() => ({
    method: !!document.querySelector("[data-capacity-method]"),
    text: document.querySelector("[data-capacity-snapshot]")?.textContent ?? "",
  }));
  ok("calendar: 周合计口径说明在场", cal.method);
  ok("calendar: 五项在场（睡眠/课程/忙/可支配/缓冲）",
     ["本周睡眠", "本周课程", "本周忙碌", "剩余可支配", "本周缓冲"]
       .every((k) => cal.text.includes(k)), cal.text.slice(0, 200));
  ok("calendar: 已安排进度条已撤", !cal.text.includes("已安排"));
  await page.screenshot({ path: `${shotDir}01-calendar-weekly-five.png` });
  await page.close();

  // 2) 身心容量卡（真实数据）
  page = await newStudentPage(null);
  await page.goto(`${base}/wellbeing`, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 3000));
  const wb = await page.evaluate(() => ({
    balance: !!document.querySelector("[data-balance-card]"),
    bar: document.querySelector("[data-balance-card]")?.textContent.includes("66"),
    overloadCard: !!document.querySelector('[data-signal="capacity_overload"]'),
  }));
  ok("wellbeing: 睡眠-负荷平衡卡在场（含 66h 上限条）", wb.balance && wb.bar);
  ok("wellbeing: 原容量超载信号卡已撤", !wb.overloadCard);
  await page.screenshot({ path: `${shotDir}02-wellbeing-balance-card.png` });
  await page.close();

  // 3) warning 弹窗：温和提醒 + 可关闭且不复弹
  page = await newStudentPage(esc("warning"));
  await page.goto(`${base}/for-you`, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 2500));
  const w1 = await page.evaluate(() => ({
    shown: !!document.querySelector('[data-wellbeing-nudge="warning"]'),
    gentle: document.querySelector("[data-wellbeing-nudge]")
      ?.textContent.includes("不是你不够努力"),
  }));
  ok("nudge: warning 弹窗出现且措辞温和", w1.shown && w1.gentle);
  await page.screenshot({ path: `${shotDir}03-nudge-warning.png` });
  await page.evaluate(() => document.querySelector("[data-nudge-dismiss]")?.click());
  await new Promise((r) => setTimeout(r, 800));
  const w2 = await page.evaluate(
    () => !!document.querySelector("[data-wellbeing-nudge]"));
  ok("nudge: 关闭后消失", !w2);
  await page.close();

  // 4) assessment 弹窗：只有去填量表一条路；填过（last_assessment_at）即不弹
  page = await newStudentPage(esc("assessment"));
  await page.goto(`${base}/for-you`, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 2500));
  const a1 = await page.evaluate(() => ({
    shown: !!document.querySelector('[data-wellbeing-nudge="assessment"]'),
    go: !!document.querySelector("[data-nudge-go]"),
    noDismiss: !document.querySelector("[data-nudge-dismiss]"),
  }));
  ok("nudge: assessment 弹窗只留「去填量表」", a1.shown && a1.go && a1.noDismiss);
  await page.screenshot({ path: `${shotDir}04-nudge-assessment.png` });
  await page.close();

  page = await newStudentPage(esc("assessment",
    { last_assessment_at: "2026-08-02T10:00:00Z" }));
  await page.goto(`${base}/for-you`, { waitUntil: "domcontentloaded" });
  await new Promise((r) => setTimeout(r, 2500));
  const a2 = await page.evaluate(
    () => !!document.querySelector("[data-wellbeing-nudge]"));
  ok("nudge: 完成量表后自动解除", !a2);
  await page.close();
} finally {
  browser.disconnect();
}
console.log(failures === 0 ? "verify-balance-round: all green"
  : `verify-balance-round: ${failures} failures`);
process.exit(failures === 0 ? 0 : 1);
