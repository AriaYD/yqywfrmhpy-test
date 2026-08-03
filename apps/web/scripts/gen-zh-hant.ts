/**
 * 生成 / 校验繁体词典 `src/i18n/zh-Hant.ts`。
 *
 *   bun run i18n:hant          重新生成（改了 zh-Hans.ts 之后跑）
 *   bun run i18n:hant:check    只校验不写盘——入库文件与生成结果不一致时退出 1
 *
 * 与 `make contracts-check` 同一守法：**生成物入库、检查器守一致性**。
 * 转换用 OpenCC（cn→hk，确定性），个别术语用 OVERRIDES 显式钉住。
 */
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as OpenCC from "opencc-js";
import { en } from "../src/i18n/en";
import { zhHans } from "../src/i18n/zh-Hans";

const convert = OpenCC.Converter({ from: "cn", to: "hk" });

/** 整句覆盖：OpenCC 逐字转换在个别词上不合用时，在这里显式钉住。 */
const OVERRIDES: Record<string, string> = {
  // 目前无——发现坏例先补这里再重新生成，别手改 zh-Hant.ts
};

const entries = (Object.keys(en) as Array<keyof typeof en>).map((key) => {
  const source = zhHans[key];
  const value = OVERRIDES[source] ?? convert(source);
  return `  ${JSON.stringify(key)}: ${JSON.stringify(value)},`;
});

const output = `import type { Dict } from "./en";

/**
 * 繁体中文（香港用字）。**生成物，禁止手改**——改 zh-Hans.ts 后执行
 * \`bun run i18n:hant\` 重新生成；\`bun run i18n:hant:check\` 守一致性。
 * 类型仍是 \`Record<keyof Dict, string>\`：漏键 / 多键都过不了 tsc。
 */
export const zhHant: Record<keyof Dict, string> = {
${entries.join("\n")}
};
`;

const target = fileURLToPath(new URL("../src/i18n/zh-Hant.ts", import.meta.url));

if (process.argv.includes("--check")) {
  let current = "";
  try {
    current = readFileSync(target, "utf-8");
  } catch {
    console.error("zh-Hant.ts 不存在——先跑 bun run i18n:hant");
    process.exit(1);
  }
  if (current !== output) {
    console.error(
      "zh-Hant.ts 与 zh-Hans.ts 不同步——跑 bun run i18n:hant 重新生成",
    );
    process.exit(1);
  }
  console.log(`zh-Hant.ts 一致（${entries.length} 键）`);
} else {
  writeFileSync(target, output);
  console.log(`已生成 zh-Hant.ts（${entries.length} 键）`);
}
