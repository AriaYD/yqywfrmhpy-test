#!/usr/bin/env node
/**
 * check-contrast.mjs — WCAG 2.1 对比度门禁（零依赖）
 *
 * 数据源是 globals.css 本身（单一出处，不复制色值）：
 * 解析 :root / @theme 两个块里的 CSS 变量（深色已于 2026-08-03 用户裁定
 * 禁用——单主题浅色，并断言暗色块不静默复活），
 * 按 COMBOS 白名单逐对实算对比度。文字对 < 4.5、非文字对 < 3.0 即 exit 1。
 *
 * Harness（Plan §10 H5）：脚本每次运行都先跑内置自检——
 * 一对已知不达标的组合（#FFFFFF on #D97757 = 3.15:1）必须被判失败、
 * 一对已知达标的（#000 on #FFF = 21:1）必须被判通过，否则脚本自身 exit 2。
 *
 * 用法：node scripts/check-contrast.mjs [--verbose]
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const CSS_PATH = join(dirname(fileURLToPath(import.meta.url)), "..", "src", "app", "globals.css");

/* ---------------- 颜色数学 ---------------- */

function parseColor(raw) {
  const s = raw.trim();
  let m = s.match(/^#([0-9a-f]{6})$/i);
  if (m) {
    const n = parseInt(m[1], 16);
    return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255, a: 1 };
  }
  m = s.match(/^rgb\(\s*(\d+)\s+(\d+)\s+(\d+)\s*(?:\/\s*([\d.]+)\s*)?\)$/);
  if (m) return { r: +m[1], g: +m[2], b: +m[3], a: m[4] === undefined ? 1 : +m[4] };
  return null; // 渐变、color-mix 等不参与本脚本
}

/** 半透明前景合成到背景上（用于 --line 等 alpha 色） */
function composite(fg, bg) {
  const a = fg.a;
  return {
    r: fg.r * a + bg.r * (1 - a),
    g: fg.g * a + bg.g * (1 - a),
    b: fg.b * a + bg.b * (1 - a),
    a: 1,
  };
}

function luminance({ r, g, b }) {
  const f = (c) => {
    c /= 255;
    return c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}

function ratio(fg, bg, under) {
  // 背景自身带 alpha（如暗色 --accent-soft）时先合成到它下面的表面（默认 --card）
  const resolvedBg = bg.a < 1 && under ? composite(bg, under) : bg;
  const resolvedFg = fg.a < 1 ? composite(fg, resolvedBg) : fg;
  const l1 = luminance(resolvedFg);
  const l2 = luminance(resolvedBg);
  const [hi, lo] = l1 > l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

/* ---------------- H5 自检：检查器必须能失败 ---------------- */

{
  const white = parseColor("#ffffff");
  const terra500 = parseColor("#d97757");
  const black = parseColor("#000000");
  const badPair = ratio(white, terra500); // 已知 ≈3.15，必须 < 4.5
  const goodPair = ratio(black, white); // 已知 = 21
  if (!(badPair < 4.5)) {
    console.error(`SELFTEST FAIL: white on #D97757 computed ${badPair.toFixed(2)} — checker cannot fail, aborting`);
    process.exit(2);
  }
  if (!(goodPair > 20.9 && goodPair < 21.1)) {
    console.error(`SELFTEST FAIL: black on white computed ${goodPair.toFixed(2)} ≠ 21 — luminance math broken`);
    process.exit(2);
  }
}

/* ---------------- 解析 globals.css ---------------- */

const css = readFileSync(CSS_PATH, "utf8");

/** 抓取一个块（从给定标记的 `{` 到配平的 `}`）内的全部 `--var: value;` */
function extractVars(source, blockMarker) {
  const start = source.indexOf(blockMarker);
  if (start === -1) return {};
  let i = source.indexOf("{", start);
  let depth = 0;
  let end = i;
  for (; end < source.length; end++) {
    if (source[end] === "{") depth++;
    else if (source[end] === "}") { depth--; if (depth === 0) break; }
  }
  const body = source.slice(i + 1, end);
  const vars = {};
  for (const m of body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) vars[m[1]] = m[2].trim();
  return vars;
}

const themeScale = extractVars(css, "@theme");
const light = { ...themeScale, ...extractVars(css, ":root {") };

// 深色已禁用（2026-08-03 用户裁定，唯一浅色）：dark 主题构造与
// 「暗色双块漂移」自检随暗色块一并移除；若有人重新引入暗色块而
// 不改本门禁，这里顺手断言它不存在——静默复活不许发生。
if (css.includes('data-theme="dark"') || css.includes("prefers-color-scheme: dark")) {
  console.error("FAIL 深色已禁用，globals.css 不应再出现暗色块/暗色媒体查询");
  process.exit(1);
}

function resolve(vars, name) {
  let v = vars[name];
  for (let hop = 0; hop < 4 && v && v.startsWith("var("); hop++) {
    v = vars[v.slice(4, -1).trim()];
  }
  if (!v) return null;
  return parseColor(v);
}

/* ---------------- 组合白名单 ----------------
 * [前景, 背景, 最低比值, 说明]
 * 文字 4.5 / 大字与非文字 UI 3.0
 * 「--accent 上放文字」是被禁止的组合，任何人把它加进来
 * 都应当在 review 里被拦下——#D97757 双向都不达标（见自检）。
 */
const COMBOS = [
  // 正文层
  ["--fg", "--bg", 4.5, "正文 on 页面底"],
  ["--fg", "--bg-sunk", 4.5, "正文 on 凹陷面"],
  ["--fg", "--card", 4.5, "正文 on 卡片"],
  ["--fg-muted", "--bg", 4.5, "次级文字 on 页面底"],
  ["--fg-muted", "--bg-sunk", 4.5, "次级文字 on 凹陷面"],
  ["--fg-muted", "--card", 4.5, "次级文字 on 卡片"],
  ["--fg-faint", "--bg", 4.5, "弱文字 on 页面底"],
  ["--fg-faint", "--card", 4.5, "弱文字 on 卡片"],
  // 强调层
  ["--accent-deep", "--bg", 4.5, "陶土文字档 on 页面底"],
  ["--accent-deep", "--bg-sunk", 4.5, "陶土文字档 on 凹陷面"],
  ["--accent-deep", "--card", 4.5, "陶土文字档 on 卡片"],
  ["--accent-fg", "--accent-deep", 4.5, "主按钮文字 on 填充"],
  ["--accent-deep", "--accent-soft", 4.5, "陶土文字 on 陶土浅底"],
  ["--accent", "--card", 3.0, "焦点环/装饰 on 卡片"],
  ["--fg-muted", "--accent-soft", 4.5, "就地编辑器标签 on 陶土浅底（M5）"],
  ["--fg", "--accent-soft", 4.5, "AI 评语正文 on 陶土浅底"],
  ["--hatch-ink", "--accent-soft", 4.5, "备考估算评语 on 陶土浅底"],
  ["--accent", "--bg", 3.0, "焦点环/装饰 on 页面底"],
  // UNKNOWN 语汇
  ["--hatch-ink", "--bg", 4.5, "UNKNOWN 文字 on 页面底"],
  ["--hatch-ink", "--bg-sunk", 4.5, "UNKNOWN 文字 on 凹陷面"],
  ["--hatch-ink", "--card", 4.5, "UNKNOWN 文字 on 卡片"],
  ["--hatch", "--card", 3.0, "斜纹/描边 on 卡片"],
  // 语义绿/红（moss/clay 原名换值，随主题）
  ["--color-moss-600", "--card", 4.5, "满足态文字 on 卡片"],
  ["--color-moss-600", "--bg", 4.5, "满足态文字 on 页面底"],
  ["--color-moss-600", "--color-moss-100", 4.5, "满足态文字 on 满足浅底"],
  ["--color-clay-600", "--card", 4.5, "不满足态文字 on 卡片"],
  ["--color-clay-600", "--bg", 4.5, "不满足态文字 on 页面底"],
  ["--color-clay-600", "--color-clay-100", 4.5, "不满足态文字 on 不满足浅底"],
  ["--color-clay-100", "--color-clay-600", 4.5, "删除确认钮：浅字 on 深底（反相）"],
  // 日历区块填充上有 accent-fg 文字（TYPE_COLOR 深档）
  ["--accent-fg", "--color-clay-600", 4.5, "日历保护块文字"],
  ["--accent-fg", "--color-moss-600", 4.5, "日历缓冲块文字"],
  ["--accent-fg", "--color-mist-700", 4.5, "日历弹性块文字"],
  // pastel 分区色块承载正文（goals 拆解区起）：主文字与次级文字都要达标
  ["--fg", "--color-sage-100", 4.5, "正文 on sage 分区"],
  ["--fg", "--color-mist-100", 4.5, "正文 on mist 分区"],
  ["--fg", "--color-blossom-100", 4.5, "正文 on blossom 分区"],
  ["--fg-muted", "--color-sage-100", 4.5, "次级文字 on sage 分区"],
  ["--fg-muted", "--color-mist-100", 4.5, "次级文字 on mist 分区"],
  ["--fg-muted", "--color-blossom-100", 4.5, "次级文字 on blossom 分区"],
  // pastel 分区 chips（bg 固定浅档，文字取同族深档）
  ["--color-sage-700", "--color-sage-100", 4.5, "sage chip"],
  ["--color-mist-700", "--color-mist-100", 4.5, "mist chip"],
  ["--color-blossom-700", "--color-blossom-100", 4.5, "blossom chip"],
  ["--color-terra-700", "--color-terra-100", 4.5, "peach chip（terra 族）"],
  // danger 按钮实际取 clay 变量（随主题），已由上面 clay 行覆盖；
  // rust 是静态色阶，只钉浅色内部配对的完整性
  ["--color-rust-700", "--color-rust-100", 4.5, "rust 静态配对"],
  // 描边可见性（合成 alpha 后对底 ≥ 1.2 仅记录不判死，line 本就是弱分隔）
];

/* ---------------- 执行 ---------------- */

const verbose = process.argv.includes("--verbose");
let failures = 0;
const rows = [];

for (const [themeName, vars] of [["light", light]]) {
  for (const [fgName, bgName, min, note] of COMBOS) {
    const fg = resolve(vars, fgName);
    const bg = resolve(vars, bgName);
    if (!fg || !bg) {
      failures++;
      rows.push({ themeName, fgName, bgName, note, r: NaN, min, ok: false, missing: true });
      continue;
    }
    const r = ratio(fg, bg, resolve(vars, "--card"));
    const ok = r >= min;
    if (!ok) failures++;
    rows.push({ themeName, fgName, bgName, note, r, min, ok });
  }
}

for (const row of rows) {
  if (!row.ok || verbose) {
    const val = row.missing ? "MISSING VAR" : row.r.toFixed(2);
    console.log(
      `${row.ok ? "  ok " : "FAIL "}[${row.themeName}] ${row.fgName} on ${row.bgName}  ${val} (min ${row.min})  ${row.note}`,
    );
  }
}

console.log(`\ncheck-contrast: ${rows.length} combos, ${failures} failures (selftest passed)`);
process.exit(failures > 0 ? 1 : 0);
