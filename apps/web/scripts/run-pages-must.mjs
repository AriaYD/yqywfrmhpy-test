#!/usr/bin/env node
/**
 * run-pages-must.mjs — 吃 verify/pages.mjs 的 PAGES/GLOBAL_MUST 清单，
 * 以学生会话逐页断言 data-* 选择器存在。任何缺失 exit 1。
 *
 * 断言全部基于 data-*，对纯视觉重构免疫——重构批次跑它守"结构没被改坏"。
 * 前置：Chrome :9222 + dev server :3100。
 */
import puppeteer from "puppeteer-core";
import { PAGES, GLOBAL_MUST } from "../verify/pages.mjs";

const base = process.argv.includes("--base")
  ? process.argv[process.argv.indexOf("--base") + 1]
  : "http://127.0.0.1:3100";

/**
 * 状态依赖基线（2026-08-01 实测，main ae36b05 与 ui/clay-restyle 完全同集）：
 * 这些选择器在**新鲜种子态**下本就不出现（要有 pending 提案 / 已写笔记 /
 * unknown 缺口 / 交互后的课程搜索 / 日历授权层级），不是重构破坏的。
 * 命中基线记 warn 不判死；基线**之外**的缺失才是回归。
 * 属性被整体删除的风险由每批 `git diff | grep -c data-` 比对兜底。
 */
const KNOWN_STATE_DEPENDENT = new Set([
  "[data-onboarding-finish]",
  "[data-proposal]",
  "[data-note]",
  "[data-unknowns]",
  "[data-prereq-counts]",
  "[data-availability-grid]",
]);

const browser = await puppeteer.connect({
  browserURL: "http://127.0.0.1:9222",
  defaultViewport: { width: 1280, height: 900 },
});
const page = await browser.newPage();
let failures = 0;

try {
  await page.goto(`${base}/login`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => {
    localStorage.setItem("campuspath.session", JSON.stringify({ portal: "student", studentId: "STU-A" }));
  });

  // H5 探针（审查 M7）：--probe 给首页多塞一个不可能存在的选择器，
  // 必须报 FAIL（exit 1），否则断言循环本身坏了
  const probe = process.argv.includes("--probe");
  if (probe && PAGES.length) {
    // 只跑首页 + 注入不可能选择器；短超时、不重试——探针要快
    PAGES.length = 1;
    PAGES[0] = { ...PAGES[0], must: ["[data-definitely-not-here]"] };
  }
  for (const spec of PAGES) {
    await page.goto(`${base}${spec.path}`, { waitUntil: "domcontentloaded" });
    try {
      try {
        await page.waitForFunction(
          (sels) => sels.every((s) => document.querySelector(s)),
          { timeout: probe ? 5000 : 30000 },
          [...spec.must, ...GLOBAL_MUST],
        );
      } catch (firstErr) {
        if (probe) throw firstErr;
        // dev 首访编译抖动：重载一次再断言，仍失败才算真缺失
        await page.reload({ waitUntil: "domcontentloaded" });
        await page.waitForFunction(
          (sels) => sels.every((s) => document.querySelector(s)),
          { timeout: 30000 },
          [...spec.must, ...GLOBAL_MUST],
        );
      }
      console.log(`  ok  ${spec.path}`);
    } catch {
      const missing = await page.evaluate(
        (sels) => sels.filter((s) => !document.querySelector(s)),
        [...spec.must, ...GLOBAL_MUST],
      );
      const real = missing.filter((s) => !KNOWN_STATE_DEPENDENT.has(s));
      const warned = missing.filter((s) => KNOWN_STATE_DEPENDENT.has(s));
      if (warned.length) console.log(`warn ${spec.path}  状态依赖缺席: ${warned.join(" , ")}`);
      if (real.length) {
        failures++;
        console.log(`FAIL ${spec.path}  缺失: ${real.join(" , ")}`);
      } else if (!warned.length) {
        console.log(`  ok  ${spec.path}`);
      }
    }
  }
} finally {
  await page.close();
  browser.disconnect();
}

console.log(`\nrun-pages-must: ${PAGES.length} pages, ${failures} failures`);
process.exit(failures > 0 ? 1 : 0);
