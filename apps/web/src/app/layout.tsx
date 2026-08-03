import type { Metadata } from "next";
import { Nunito } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Shell } from "@/components/shell";

/**
 * 标题字体：Nunito（圆润，配 clay 质感）。next/font 构建期下载并自托管，
 * 运行时零外链请求；latin 子集 → 中文由 --font-sans 栈回落系统字体。
 * 只挂在 .t-display/.t-title/.t-section 与 Metric 数字上（globals.css）。
 */
const nunito = Nunito({
  subsets: ["latin"],
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CampusPath",
  description: "Growth pathways, with receipts — synthetic demo build",
};

/**
 * 首帧防闪：在 hydration **之前**把 lang 打到 <html> 上，否则中文用户会
 * 先看到一帧英文——这类闪烁是 craft 最容易失分的地方（apple-design §16.7）。
 * （主题分支已撤：2026-08-03 用户裁定全站唯一浅色，data-theme 无人再读。）
 *
 * 这段脚本必须与 `i18n/index.tsx` 用**同样的 storage key**。
 *
 * 踩过的坑：一开始把它包在自己写的 `<head>` 里。Next 16 的 root layout
 * **不允许手写 `<head>`**（`docs/…/layout.md:141`），后果不是报错，
 * 是**整页静默不 hydrate**——SSR 的 HTML 照常渲染，看起来完全正常，
 * 但所有 effect 不跑、所有 onClick 无效，控制台一条错误都没有。
 * 是"点了没反应"这个实测动作抓到的，读代码抓不到。
 */
const NO_FLASH = `
(function () {
  try {
    var l = localStorage.getItem("campuspath.locale");
    document.documentElement.lang = (l === "en" || l === "zh-Hans" || l === "zh-Hant") ? l : "zh-Hans";
  } catch (e) {}
})();
`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-Hans" suppressHydrationWarning className={nunito.variable}>
      <body>
        <script dangerouslySetInnerHTML={{ __html: NO_FLASH }} />
        <Providers>
          <Shell>{children}</Shell>
        </Providers>
      </body>
    </html>
  );
}
