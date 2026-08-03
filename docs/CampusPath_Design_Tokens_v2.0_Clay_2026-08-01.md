# CampusPath 设计令牌表 v2.0 — 温柔陶土（Claymorphism）

> **版本** 2.0 · **日期** 2026-08-01 · **出处** `apps/web/src/app/globals.css`（分支 `ui/clay-restyle`）
> **技术栈** Tailwind CSS v4（`@theme`）· Next.js 16.2.12 · React 19.2.4 · motion 12.43 · next/font (Nunito)
> **取代** `CampusPath_Design_Tokens_2026-08-01.md`（v1.0，深海青系）——v1 保留作历史参照，其结构性契约（§9 清单）在本版逐项兑现
>
> 本版与 v1 的关系：**换皮不换骨**。14+ 语义变量、7 级字阶、两个签名元素、
> 三条无障碍降级全部保留原语义；色板、圆角、阴影、材质、字体按
> Claymorphism × Claude 暖色重铸。对比度不再是"文档里的自查表"，
> 而是 CI 化的门禁：`apps/web/scripts/check-contrast.mjs`（80 组合 × 双主题，
> 解析 globals.css 本身，值漂移即红）。

---

## 0. 设计系统的立意

> **"温柔陶土 × 可核验"**
> Claymorphism（温和档）× Claude 品牌暖色：奶油底、白卡、陶土橙。
> 给学生的是一张摸起来温柔的成长地图，不是一块仪表盘。
> 圆角与阴影出自粘土的物理：柔外影 + 内高光 = 轻微的"充气感"；按压收缩、松手回弹。
>
> 贯穿全站的主张不变：**本系统从不在没有凭据的情况下断言任何事。**
> UNKNOWN 有自己的**斜纹质感**——不是灰、更不是红（Spec §16.2）。
>
> v1 曾declared「避开米色+陶土」；本版按用户 2026-08-01 明确指定改用 Claude 暖色系。
> 设计依据为 `ui-ux-pro-max` skill（唯一依据，用户裁定），不再引用 frontend-design / apple-design。

**跨页布局稳定是硬约束**（用户裁定）：`scrollbar-gutter: stable` + 壳层统一容器；
`scripts/check-alignment.mjs` 逐页比对 header/sidebar/main/首内容块 boundingRect，偏差 >0.5px 即红。

---

## 1. 色板（`@theme` 层）

### 1.1 燕麦 `oat` — 奶油中性底（永不用纯白当页面底）

| Token | HEX | 用途 |
|---|---|---|
| `--color-oat-50` | `#faf9f5` | 浅色页面底 |
| `--color-oat-100` | `#f0eee6` | 浅色凹陷面 |
| `--color-oat-200` | `#e5e1d4` | 备用分隔面 |
| `--color-oat-300` | `#d4cebe` | 备用描边基 |

### 1.2 树皮 `bark` — 暖黑文字与暗色面（不是纯黑）

| Token | HEX | 用途 |
|---|---|---|
| `--color-bark-950` | `#1b1915` | |
| `--color-bark-900` | `#201e1a` | 暗色页面底 |
| `--color-bark-850` | `#2a2721` | 暗色卡片 |
| `--color-bark-800` | `#3a362d` | 高对比模式次级文字 |
| `--color-bark-600` | `#69624f` | 浅色弱文字 |
| `--color-bark-500` | `#7a7360` | |
| `--color-bark-400` | `#948d7a` | |
| `--color-bark-300` | `#b8b09e` | 暗色次级文字 |
| `--color-bark-100` | `#ede9de` | 暗色正文 |

### 1.3 陶土 `terra` — 品牌强调

| Token | HEX | 用途 |
|---|---|---|
| `--color-terra-100` | `#f6e3d8` | 浅色 accent-soft |
| `--color-terra-200` | `#efcdba` | |
| `--color-terra-300` | `#e5a588` | |
| `--color-terra-400` | `#e08a67` | 暗色 accent-deep |
| `--color-terra-500` | `#d97757` | **Claude 品牌锚点——只做装饰填充**（见下方硬结论） |
| `--color-terra-600` | `#c25e3f` | |
| `--color-terra-700` | `#a04a2a` | 浅色 accent-deep（文字档 + 主按钮填充） |
| `--color-terra-800` | `#7e3a20` | |

> **[硬结论·脚本自检钉死]** `#D97757` 双向文字都不达标（白字 3.12 / 暖黑字 3.46）。
> 它只出现在纯装饰；功能强调用 `--accent`（`#d3714e`，≥3:1 非文字档），
> 文字与按钮填充一律 `--accent-deep`。**「--accent 上放文字」是被禁止的组合。**

### 1.4 pastel 分区（Vibrant & Block-based）——sage 绿 / mist 蓝 / blossom 粉

200/500 为静态刻度；**100（底）与 700（字）随主题切换**（定义在 `:root` 各主题块）：

| 族 | 100 浅/暗 | 500（静态） | 700 浅/暗 | 语义分工 |
|---|---|---|---|---|
| `sage` | `#e5f0e3` / `#24352a` | `#4e8a63` | `#3a6b4e` / `#a5cdb0` | 软实力层、成功系分区 |
| `mist` | `#e1eef2` / `#22333a` | `#6e9aad` | `#31606f` / `#9cc6d4` | 硬性要求层、日历弹性块 |
| `blossom` | `#f7e6eb` / `#3a2a31` | `#c98aa0` | `#8d4a5e` / `#dca8ba` | 特殊约束层 |
| peach | = `--accent-soft` / `--accent-deep` | — | — | 方向徽章、编辑态标签 |

### 1.5 语义绿/红 `moss` / `clay` — 沿用 v1 变量名、换值、随主题（修复 v1 §8 缺陷 2）

| Token | 浅 | 暗 | 用途 |
|---|---|---|---|
| `--color-moss-600` | `#3a6b4e` | `#8fc59b` | 满足/成功文字 |
| `--color-moss-500` | `#4e8a63` | `#6fa87e` | 成功描边；日历缓冲块用 600 |
| `--color-moss-100` | `#e5f0e3` | `#253828` | 成功浅底 |
| `--color-clay-600` | `#a63838` | `#e9968f` | 不满足/危险文字（绯红，与陶土拉开色相） |
| `--color-clay-500` | `#c24e4e` | `#d97c74` | 危险描边 |
| `--color-clay-100` | `#f9e3e1` | `#3b2726` | 危险浅底（btn-danger） |

静态 `rust` 族（`100 #f9e3e1 / 200 / 500 / 600 / 700 #963030`）保留为刻度参照，组件一律走 clay 语义变量。

### 1.6 砂岩赭 `ochre` — **UNKNOWN 专属语汇，v1 硬约束原文不变**

| Token | HEX | 用途 |
|---|---|---|
| `--color-ochre-700` | `#7f5510` | **新增：浅色 `--hatch-ink`（UNKNOWN 文字档，修 v1 §8 缺陷 1）** |
| `--color-ochre-600` | `#9a6417` | |
| `--color-ochre-500` | `#c2831f` | 浅色 `--hatch`（斜纹/描边） |
| `--color-ochre-400` | `#dda43f` | 暗色 `--hatch` |
| `--color-ochre-300/100` | `#ecc37c` / `#f8ecd3` | |

> **[硬约束]** ochre 是"未知/待定"的专属语汇。挪作装饰或强调即破坏三值状态的唯一视觉标识。
> `.chip-*` 原语刻意**没有 ochre 档**；v1 时代目标方向徽章曾误用 ochre，本版已改 peach。

---

## 2. 语义变量（16 个 × 2 主题；暗色是整套暖深色，非反色）

> **实现同步（2026-08-03）**：深色主题已按用户裁定**整体撤除**（globals.css
> 两个暗色块、ThemeProvider、顶栏/设置页切换器全删，`color-scheme` 锁 light）；
> 门禁改为 **43 组合单主题**并新增「暗色块复活即红」断言。下表暗色列保留
> 作历史记录，不再是现行实现。

| 语义 Token | 浅色 | 暗色 | 说明 |
|---|---|---|---|
| `--bg` | `#faf9f5` | `#201e1a` | 页面底 |
| `--bg-sunk` | `#f0eee6` | `#1a1815` | 凹陷面（.field、卡内嵌块）|
| `--card` | `#ffffff` | `#2a2721` | 卡片面 |
| `--card-translucent` | `rgb(255 253 248/.8)` | `rgb(42 39 33/.78)` | 悬浮材质底 |
| `--line` / `--line-strong` | `rgb(41 38 27/.10/.20)` | `rgb(237 233 222/.12/.24)` | 描边 |
| `--fg` | `#29261b` | `#ede9de` | 正文 |
| `--fg-muted` | `#6b6455` | `#b8b09e` | 次级 |
| `--fg-faint` | `#69624f` | `#9a927e` | 弱化（v1 压线项已修：浅 5.76/暗 4.81）|
| `--accent` | `#d3714e` | `#d97757` | 功能陶土：焦点环、选中描边、装饰（**非文字**）|
| `--accent-deep` | `#a04a2a` | `#e08a67` | **新增**：陶土文字档 + 主按钮填充 |
| `--accent-soft` | `#f6e3d8` | `rgb(224 138 103/.12)` | 选中柔和底 |
| `--accent-fg` | `#ffffff` | `#2a1608` | accent-deep 填充上的文字 |
| `--hatch` | `#c2831f` | `#dda43f` | UNKNOWN 斜纹/描边 |
| `--hatch-ink` | `#7f5510` | `#e0a94a` | **新增**：UNKNOWN 文字档 |
| `--shadow-card/btn/inset` | 见 §5 | 见 §5 | clay 三层影 |

Tailwind 桥接（`@theme inline`）新增 `text-accent-deep` `text-hatch-ink` 等工具类。

---

## 3. 排版

### 3.1 字体栈（标题引入 Nunito，正文保持系统栈）

```css
--font-sans: ui-sans-serif, system-ui, -apple-system, "SF Pro Text",
             "Helvetica Neue", "PingFang SC", "Noto Sans CJK SC", sans-serif;
--font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;
/* --font-display 由 next/font (Nunito, latin 子集, variable) 注入 <html> */
```

- Nunito 经 `next/font/google` **构建期下载自托管**，运行时零外链请求；
- 只挂 `.t-display/.t-title/.t-section` 与 `Metric` 数字；中文回落系统中文字体；
- **tnum 实测通过**（1111 与 9999 渲染同宽），全局 `tabular-nums` 保留。

### 3.2 字阶（7 级不变；标题三级换 display 字体并提权重）

| 类名 | 变化 |
|---|---|
| `.t-display` | + `font-family: var(--font-display,…)`；weight 640→**800** |
| `.t-title` | 同上；weight 620→**700** |
| `.t-section` | 同上；weight 600→**700** |
| `.t-body/.t-meta/.t-micro/.t-mono` | 完全不变（含 `.t-micro` uppercase）|

### 3.3 全局排版

v1 §3.3 不变，另加一行：`html { scrollbar-gutter: stable; }`（跨页稳定硬约束）。
行长约束（`max-w-[62ch]` 等）沿用 v1 §3.4 分布。

---

## 4. 签名元素（两个，保留并 clay 化）

### 4.1 `.hatch-unknown`

−45°/2px-6px 条纹几何保留；新垫 `color-mix(in srgb, var(--hatch) 8%, var(--card))`
柔和赭色底、条纹浓度 38%→**30%**——从"警示胶带"变成"柔性凹槽"，
仍与 满足/不满足 截然异族。文字一律走 `--hatch-ink`。

### 4.2 `.credential-chip`

打孔从 `::before/::after` 用 `--bg` 填色，改为 **CSS mask 真镂空**
（双 radial-gradient，`mask-composite: intersect`）——放在白卡、pastel 块上
缺口都成立，根治 v1 记录的"换底色露馅"。票根 dashed 描边与 `validation_id`
`.t-mono` 展示不变，文字 `--hatch-ink`。

---

## 5. 材质与深度（clay 三层影体系）

| Token/类 | 浅色 | 暗色 |
|---|---|---|
| `--shadow-card` | `0 1px 2px rgb(94 74 56/.05), 0 12px 28px -10px rgb(94 74 56/.16), inset 0 1.5px 0 rgb(255 255 255/.85)` | 外层换黑 `.5/.6`，内高光 `.06` |
| `--shadow-btn` | 同构较小 + 内高光 `.7` | 同构 |
| `--shadow-inset` | `inset 0 2px 4px rgb(94 74 56/.07)`（.field 凹陷） | `inset … rgb(0 0 0/.4)` |
| `.material-chrome` | `--card-translucent` + `blur(16px) saturate(160%)`（暖色下 180% 会偏脏，降档） | 同 |
| `.material-modal` | 92% 近实底 + `blur(32px)`（v1 参数不变） | 同 |

铁律：**box-shadow 永不参与动画**（按压只动 transform）；长列表行内条目不用 `--shadow-card`。

---

## 6. 形状与间距

### 6.1 圆角——v1 的 11 个散值收敛为 **4 档 token**（@theme，产出 `rounded-xs/sm/md/lg`）

| Token | 值 | 用途 |
|---|---|---|
| `--radius-xs` | 4px | **仅日历微块**（26px 行高生态，v1 的 2-4px 特例冻结归并） |
| `--radius-sm` | 8px | chips、微标签、分段控件内段 |
| `--radius-md` | 14px | 按钮、输入框、下拉、卡内嵌块、列表项 |
| `--radius-lg` | 20px | Card、Drawer、登录卡 |

源码任意值 `rounded-[N]` 已清零（残留仅 2-3px 图形微件，B8 复核）。

### 6.2-6.4 布局常量 / Grid 列宽 / 日历常量

**全部沿用 v1 数值不动**（1240/880/210/74px；Grid 310-168；DAY_START 已为 0-24 制、
ROW_HEIGHT 26px、6px 最小块、20px 标题阈值——日历批次「只换色不换形」）。

### 6.5 原语类（v2 新增：样式的单一出处）

| 类 | 定义要点 |
|---|---|
| `.btn` + `.btn-primary/secondary/ghost/danger` | primary=accent-deep 底白字+btn 影；secondary=白卡+strong 描边+btn 影；ghost=透明 hover accent-soft；danger=clay-100 底 clay-600 字（不惩罚式）|
| `.field` | bg-sunk + line 描边 + md 圆角 + inset 影；focus 转 accent 描边 |
| `.chip` + `.chip-sage/mist/blossom/peach/neutral` | 100 底 700 字；**无 ochre 档** |

页面契约：「CSS 类为契约、组件为糖」——`primitives.tsx` 的 Button/Input/Select/Chip
仅是全透传糖衣。统一分段控件（用户裁定全站唯一 tab 形态）：外
`rounded-md border bg-bg-sunk p-0.5`、内 `rounded-sm`、激活 `accent-deep` 底。

---

## 7. 动效

### 7.1 `.pressable`（clay 版）

压入 110ms `cubic-bezier(0.32,0.72,0,1)` scale **0.97**；
松手回弹 260ms `cubic-bezier(0.22,1.15,0.36,1)`（轻过冲，粘土回弹）。

### 7.2 弹簧（motion/react）

v1 参数全部保留：导航 layoutId `bounce 0/0.35`、登录卡 `0/0.45`、抽屉 `0.2`、
reduced-motion 降级 `0.12`。依据改标 ui-ux-pro-max（spring-physics / interruptible /
exit-faster-than-enter），不再引用 apple-design（用户裁定）。

### 7.3 焦点 / 7.4 选区

`outline: 2px solid var(--accent)`（浅 3.36/暗 4.77，≥3:1 门禁钉住），radius 5px→**8px**；
`::selection` accent 28% 混色不变。

### 7.5 无障碍降级（三条，全部保留）

v1 §7.5 三条媒体查询原样保留；`prefers-contrast: more` 的值换成暖色系对应
（`--line` .45/.65、`--fg-muted #3a362d`）。

---

## 8. 对比度：从"两个已知缺陷"到"零缺陷 + CI 门禁"

v1 §8 的两个缺陷在本版**结构性修复**：

1. **`--hatch` 作文字 3.20:1（15 处）** → 新增 `--hatch-ink` 文字档（浅 `#7f5510`：
   比 v1 建议的 `#9a6417` 再深一档，因为后者只在白卡达标、奶油底不达标）。
2. **moss/clay 暗色 2.90/2.94（31 处）** → 变量原名换值、随主题切换，107 处引用零改动修复。

**自查表 CI 化**：`node scripts/check-contrast.mjs`——解析 globals.css 本身，
实算 WCAG 2.1；文字 <4.5、非文字 <3.0 即 exit 1；
内置 H5 自检（已知失败样例必须报红，否则脚本自身 exit 2）。
历史（2026-08-01）：80 组合 × 双主题 0 失败，最低裕量浅色
`accent-deep on accent-soft` 4.82、暗色同组合 4.65。
**现行（2026-08-03 深色撤除后）：43 组合单主题（light）0 失败**，
并断言暗色块不得复活；全表见脚本 `--verbose` 输出。

---

## 9. 交付清单（v1 §9 逐项兑现状态）

- [x] 色阶：oat 4 + bark 9 + terra 8 + pastel 3 族 + rust 5 + ochre 6 + moss/clay 语义 6
- [x] 语义变量 16 × 2 主题（较 v1 +2：`--accent-deep`、`--hatch-ink`）
- [x] 7 级字阶（标题三级换 Nunito + 提权重，其余不动）
- [x] 字体栈与加载策略（next/font 构建期自托管，零运行时外链）
- [x] 圆角 4 档 token 集中化（v1 弱点清零）
- [x] 卡片投影 × 2 主题（+ btn/inset 两档）
- [x] 两种材质参数（chrome 16px/160%、modal 32px/150%）
- [x] 三值 UNKNOWN 第三语汇（斜纹保留，clay 化）
- [x] 凭据票根形状（mask 真镂空）
- [x] 按压缩放 0.97 与双段缓动
- [x] 弹簧参数（导航/入场/抽屉）
- [x] 焦点环（accent 2px / radius 8px）
- [x] 三条降级媒体查询
- [x] 对比度自查表 → **升级为 CI 门禁脚本**（外加 check-alignment 跨页稳定门禁）

---

*数值抽取自 2026-08-01 `ui/clay-restyle` 分支；门禁：`check-contrast.mjs`（80×2）、
`check-alignment.mjs`（14 页 + probe 自检）、`run-pages-must.mjs`（data-* 结构回归）。*
