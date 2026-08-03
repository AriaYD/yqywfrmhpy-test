# CampusPath 学生 Web App（WP7）

D1 的 14 个页面。Next.js 16 + Tailwind 4 + motion，bun 管理。
数据全部来自 `/v1`，前端**零硬编码业务数据**。

## 跑起来

```bash
make api                       # 仓库根目录：FastAPI 起在 :8000
cd apps/web && bun install && bun run dev --port 3100
```

浏览器开 `http://127.0.0.1:3100`。前端通过 `next.config.ts` 的 rewrite
把 `/api/*` 代理到 `:8000`，因此**同源、不需要 CORS**——API 侧不必为了
一个演示前端放开跨域，少一处需要有人记得收回去的放宽。

## 设计方向：「温柔陶土 × 可核验」（v2，2026-08-01 重构）

Claymorphism（温和档）× Claude 暖色：燕麦奶油底（`--color-oat-*`）、
白卡浮雕（柔外影 + 内高光）、陶土橙强调（`--color-terra-*`）。设计依据
`ui-ux-pro-max` skill；令牌全表见
`docs/CampusPath_Design_Tokens_v2.0_Clay_2026-08-01.md`。

三道门禁随批次强制（`apps/web/scripts/`）：`check-contrast.mjs`
（80 组合 × 双主题 WCAG 实算）、`check-alignment.mjs`（跨页骨架逐像素
比对——切页不许跳动）、`run-pages-must.mjs`（data-* 结构回归）。

砂岩赭（`--color-ochre-*`）仍是 UNKNOWN 的专属语汇，只花在两个**签名元素**上：

| 签名元素 | 在哪 | 为什么是它 |
|---|---|---|
| **三值指示器** `TriState` | `components/ui.tsx` | UNKNOWN 用**斜纹**，既不是绿也不是红。整个产品建立在"解析不出来 ≠ 你不合格"上，配色必须承认第三种状态 |
| **凭据票根** `CredentialChip` | 同上 | 任何来自 Rules 的结论都挂一张带真实 `validation_id` 的票根。看得见的审计链，比一句"我们很严谨"有用 |

交互物理按 `ui-ux-pro-max` 的 UX 规则：默认 spring `bounce 0`、
`duration 0.3–0.4`，按下即反馈（<100ms）不等 `click`，按压 scale 0.97
配 260ms 轻过冲回弹；`prefers-reduced-motion` / `reduced-transparency` /
`contrast: more` 三个信号各自有降级路径。

## 双语

`src/i18n/en.ts` 是词典的**类型源**；`zh-Hans.ts` 声明为
`Record<keyof Dict, string>`，所以**少一个键、拼错一个键都过不了 `tsc`**。
i18n 完整性因此是类型层事实，不是纪律。

选择持久化在 `localStorage`，并同步写 `<html lang>`；`layout.tsx` 里有一段
内联脚本在 hydration 前就把 lang / theme 打上，避免首帧闪烁。

⚠️ **已知缺口**：Rules / Wellbeing 服务产出的判定理由目前是单语中文
prose，塞进 `LocalizedText` 时两侧填了同一个字符串，所以英文态下
「为什么没推荐」抽屉里的理由仍显示中文。见任务 U7。

## 浏览器实测

`verify/pages.mjs` 是 D1「页面完整性」的机器化清单。断言一律基于
`data-*` 属性，**不基于文案**——用文案做断言，切到另一种语言就全线失败，
双语实测会变成摆设。

清单里最后一项是一个**故意查不到的选择器**：它必须红，否则说明这套断言
根本没在断言什么（Plan §10 H5）。

截图存 `docs/verification/wp7/`。

## 实测踩到的三个坑

1. **Next 16 的 root layout 不能手写 `<head>`**（`node_modules/next/dist/docs/…/layout.md:141`）。
   后果不是报错，是**整页静默不 hydrate**：SSR 的 HTML 照常显示，看起来
   完全正常，但 effect 不跑、`onClick` 无效，控制台一条红字都没有。
2. **dev server 默认只认 `localhost`**，用 `127.0.0.1` 访问时 `/_next/*`
   被当成跨源拦掉，症状与上一条一模一样。已在 `allowedDevOrigins` 里放开。
3. **组件不透传 `...rest` 会静默吃掉 `data-*`**，于是实测断言查不到东西，
   而"页面坏了"和"属性被组件吃了"分不开。`Card` 已改为透传。

三条都是"亲手点一下"发现的，读代码、跑 `tsc`、跑 `bun run build` 全都是绿的。
