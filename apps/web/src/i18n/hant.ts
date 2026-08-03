import * as OpenCC from "opencc-js";

/**
 * 简体 → 繁体（香港用字）运行时转换。
 *
 * 用途：契约里的 `LocalizedText` 只有 zh_Hans / en 两个字段——服务端产出的
 * 动态文案在繁体界面下由这里**确定性**转换，不改契约、不调模型。
 * 静态词典（zh-Hant.ts）不走这里：它由 `bun run i18n:hant` 预生成并入库，
 * 带一致性检查（同 contracts-check 的守法）。
 */
export const toHant: (text: string) => string = OpenCC.Converter({
  from: "cn",
  to: "hk",
});
