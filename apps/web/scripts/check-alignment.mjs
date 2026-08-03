#!/usr/bin/env node
/**
 * check-alignment.mjs — 跨页面布局稳定性门禁（用户硬约束）
 *
 * 旧 UI 的问题：不同页面的导航/主内容容器各偏各的，切页时整个界面"跳"。
 * 本脚本以学生会话逐页访问，测量三个骨架元素的 boundingClientRect：
 *   header 内容容器（header > div）/ 侧栏 [data-sidebar] / <main>
 * 任意页面与第一页的 x / width 偏差 > 0.5px 即 FAIL，exit 1。
 *
 * 前置：Chrome --remote-debugging-port=9222 + dev server :3100。
 * 用法：node scripts/check-alignment.mjs [--base http://127.0.0.1:3100]
 */
import puppeteer from "puppeteer-core";

const base = process.argv.includes("--base")
  ? process.argv[process.argv.indexOf("--base") + 1]
  : "http://127.0.0.1:3100";

const STUDENT_PAGES = [
  "/profile", "/goals", "/gaps", "/for-you", "/square", "/timeline",
  "/actions", "/calendar", "/wellbeing", "/planner", "/reflections",
  "/memory", "/settings", "/onboarding",
];

const browser = await puppeteer.connect({
  browserURL: "http://127.0.0.1:9222",
  defaultViewport: { width: 1280, height: 900 },
});
const page = await browser.newPage();
let failures = 0;

try {
  // 合成学生会话（Synthetic / Demo）——绕过门户守卫
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.setItem("campuspath.session", JSON.stringify({ portal: "student", studentId: "STU-A" }));
  });

  const measure = () =>
    page.evaluate(() => {
      const pick = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: +r.x.toFixed(2), w: +r.width.toFixed(2) };
      };
      return {
        header: pick(document.querySelector("header > div")),
        sidebar: pick(document.querySelector("[data-sidebar]")),
        main: pick(document.querySelector("main")),
        // 页面首个内容块：用户点名的"主内容区块偏移"就发生在这层。
        // 宽度允许按页设计不同，x 必须全站一致。
        content: pick(document.querySelector("main > *:first-child")),
      };
    });

  let reference = null;
  for (const path of STUDENT_PAGES) {
    await page.goto(`${base}${path}`, { waitUntil: "domcontentloaded" });
    // 新路由首访 dev 编译慢：等骨架真的渲染出来，不用固定 sleep（Plan §10.2）
    await page.waitForFunction(
      () => document.querySelector("main") && document.querySelector("header > div"),
      { timeout: 30000 },
    );
    const rects = await measure();
    if (!reference) {
      reference = { path, rects };
      // H5 探针：--probe 人为把基准右移 10px，后续页面必须全线报 FAIL，
      // 否则说明比较逻辑坏了（exit 应为 1，由调用方断言）
      if (process.argv.includes("--probe")) {
        for (const k of ["header", "sidebar", "main", "content"]) {
          if (reference.rects[k]) reference.rects[k] = { ...reference.rects[k], x: reference.rects[k].x + 10 };
        }
      }
      console.log(`  ref  ${path}  header=${JSON.stringify(rects.header)} sidebar=${JSON.stringify(rects.sidebar)} main=${JSON.stringify(rects.main)}`);
      continue;
    }
    for (const key of ["header", "sidebar", "main", "content"]) {
      const a = reference.rects[key];
      const b = rects[key];
      if (!a && !b) continue; // 两页都没有（如 onboarding 无侧栏）——合法
      if (!a || !b) {
        // 审查 M8：单边缺席说明某页骨架没渲染出来——这不是"没得比"，是回归
        failures++;
        console.log(`FAIL ${path}  ${key} 单边缺席（ref=${JSON.stringify(a)} page=${JSON.stringify(b)}）`);
        continue;
      }
      const dx = Math.abs(a.x - b.x);
      const dw = key === "content" ? 0 : Math.abs(a.w - b.w);
      if (dx > 0.5 || dw > 0.5) {
        failures++;
        console.log(`FAIL ${path}  ${key} 相对 ${reference.path} 偏移 dx=${dx.toFixed(2)} dw=${dw.toFixed(2)}  (${JSON.stringify(b)} vs ${JSON.stringify(a)})`);
      }
    }
  }
} finally {
  await page.close();
  browser.disconnect();
}

console.log(`\ncheck-alignment: ${STUDENT_PAGES.length} pages, ${failures} misalignments`);
process.exit(failures > 0 ? 1 : 0);
