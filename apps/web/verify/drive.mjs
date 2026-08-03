/**
 * 浏览器实测驱动器（chrome-devtools MCP 不可用时的替代通道）。
 *
 *   bun verify/drive.mjs '<async 函数体，收 page 参数>'
 *
 * 连接本机已运行的 Chrome（--remote-debugging-port=9222），新开标签执行，
 * 结束时打印 JSON 结果并关闭标签。断言仍在浏览器里跑（page.evaluate）。
 */
import puppeteer from "puppeteer-core";

const body = process.argv[2];
if (!body) {
  console.error("用法: bun verify/drive.mjs '<async (page) 函数体>'");
  process.exit(1);
}

const browser = await puppeteer.connect({
  browserURL: "http://127.0.0.1:9222",
  defaultViewport: { width: 1280, height: 900 },
});
const page = await browser.newPage();
try {
  const fn = new Function("page", `return (async () => { ${body} })()`);
  const result = await fn(page);
  console.log(JSON.stringify(result ?? null));
} catch (error) {
  console.error("DRIVE_ERROR:", error?.message ?? error);
  process.exitCode = 1;
} finally {
  await page.close();
  browser.disconnect();
}
