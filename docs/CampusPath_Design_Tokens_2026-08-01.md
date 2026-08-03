# CampusPath 设计令牌现状表

> **版本** 1.0 · **日期** 2026-08-01 · **出处** `apps/web/src/app/globals.css` + 组件内联值
> **技术栈** Tailwind CSS v4（`@theme` 指令）· Next.js 16.2.12 · React 19.2.4 · motion 12.43
>
> **这份表干什么用**：新设计必须**映射回这套令牌**，而不是另起一套。
> 映射得上，接入就是改一个变量文件；映射不上，接入就是重写每一个组件。
>
> 所有色值、字号、圆角、时长均为**从源码抽取的实测值**，含使用次数统计。
> 对比度为 WCAG 2.1 相对亮度算法计算值，非估算。

---

## 0. 设计系统的立意（来自源码注释，改设计前请先读）

> **"可核验的地形图"**
> 取材：科大在清水湾的山脊上。深海青（sea）来自海面，砂岩赭（ochre）来自山体与日照。
> **刻意避开三种 AI 默认相**：米色+衬线+陶土、近黑+荧光色、报纸细线排版。
>
> 贯穿全站的主张：**本系统从不在没有凭据的情况下断言任何事。**
> 所以 UNKNOWN 有自己的**斜纹质感**——不是灰、更不是红。
> "解析不出来"永远不等于"你不合格"（Spec §16.2）。

新设计可以换风格，但**不能换掉这个主张的视觉承载**（见 §4 签名元素）。

---

## 1. 色板（`@theme` 层，与主题无关的原始刻度）

### 1.1 墨色阶 `ink` — 偏青的深灰，不是纯黑

| Token | HEX | 用途 |
|---|---|---|
| `--color-ink-950` | `#08110f` | 深色主题背景 |
| `--color-ink-900` | `#0b1614` | 浅色主题正文色 / 深色卡片 |
| `--color-ink-800` | `#16292a` | 高对比模式下的次级文字 |
| `--color-ink-700` | `#23403f` | |
| `--color-ink-600` | `#3a5c5a` | 浅色主题次级文字 |
| `--color-ink-500` | `#5b7d7b` | 浅色主题弱化文字 |
| `--color-ink-400` | `#86a3a1` | 深色主题弱化文字 |
| `--color-ink-300` | `#b3c6c4` | 深色主题次级文字 |
| `--color-ink-200` | `#d5e0de` | |
| `--color-ink-100` | `#e9efee` | 深色主题正文色 |
| `--color-ink-50` | `#f4f7f6` | 浅色主题背景 |

### 1.2 深海青 `sea` — 主色

| Token | HEX | 用途 |
|---|---|---|
| `--color-sea-700` | `#084f48` | |
| `--color-sea-600` | `#0a6058` | **浅色主题主色** |
| `--color-sea-500` | `#0d7c70` | |
| `--color-sea-400` | `#199e8d` | |
| `--color-sea-300` | `#4dbfae` | **深色主题主色**；日历「弹性」区块 |
| `--color-sea-200` | `#9adcd0` | |
| `--color-sea-100` | `#d5f0ea` | 浅色主题主色柔和底 |

### 1.3 砂岩赭 `ochre` — **全站唯一"张扬"的颜色，只用在签名元素上**

| Token | HEX | 用途 |
|---|---|---|
| `--color-ochre-600` | `#9a6417` | |
| `--color-ochre-500` | `#c2831f` | **浅色主题 `--hatch`**（三值 UNKNOWN） |
| `--color-ochre-400` | `#dda43f` | **深色主题 `--hatch`** |
| `--color-ochre-300` | `#ecc37c` | |
| `--color-ochre-100` | `#f8ecd3` | |

> **[硬约束]** ochre 是"未知/待定"的专属语汇。新设计若把它挪去做装饰色或强调色，
> 三值状态就失去了唯一的视觉标识。

### 1.4 语义色 — **刻意不用警报红 / 信号绿。这个产品不惩罚人**

| Token | HEX | 用途 | ⚠️ |
|---|---|---|---|
| `--color-moss-600` | `#2f6b41` | 成功/已完成文字 | **深色模式对比度不足，见 §8** |
| `--color-moss-500` | `#3f8a52` | 成功描边；日历「缓冲」区块 | |
| `--color-moss-100` | `#dfeee2` | 成功底色 | |
| `--color-clay-600` | `#9d4630` | 错误/危险文字 | **深色模式对比度不足，见 §8** |
| `--color-clay-500` | `#bd5940` | 危险描边；日历「保护」区块 | |
| `--color-clay-100` | `#f7e2dc` | 危险底色 | |

---

## 2. 语义变量（`:root` 层，随主题切换）

**主题机制**：浅色为默认；深色跟随系统 `prefers-color-scheme`；
`data-theme="light|dark"` 挂在 `<html>` 上可**双向压住**系统偏好（用户在顶栏切换后写入 localStorage）。

| 语义 Token | 浅色 | 深色 | 说明 |
|---|---|---|---|
| `--bg` | `#f4f7f6` | `#08110f` | 页面底 |
| `--bg-sunk` | `#eaf0ee` | `#060d0c` | 凹陷面（输入框、卡内嵌块）|
| `--card` | `#ffffff` | `#0b1614` | 卡片面 |
| `--card-translucent` | `rgb(255 255 255 / .72)` | `rgb(11 22 20 / .72)` | 悬浮层材质底 |
| `--line` | `rgb(16 31 29 / .10)` | `rgb(214 233 229 / .12)` | 普通描边 |
| `--line-strong` | `rgb(16 31 29 / .20)` | `rgb(214 233 229 / .24)` | 强调描边 |
| `--fg` | `#0b1614` | `#e9efee` | 正文 |
| `--fg-muted` | `#3a5c5a` | `#b3c6c4` | 次级 |
| `--fg-faint` | `#5b7d7b` | `#86a3a1` | 弱化/标注 |
| `--accent` | `#0a6058` | `#4dbfae` | 主色 |
| `--accent-soft` | `#d5f0ea` | `rgb(77 191 174 / .16)` | 主色柔和底（选中态）|
| `--accent-fg` | `#ffffff` | `#08110f` | 主色上的文字 |
| `--hatch` | `#c2831f` | `#dda43f` | **三值 UNKNOWN 专用** |
| `--shadow-card` | `0 1px 2px rgb(8 17 15/.05), 0 8px 24px -12px rgb(8 17 15/.18)` | `0 1px 2px rgb(0 0 0/.4), 0 8px 24px -12px rgb(0 0 0/.7)` | 卡片投影 |

**Tailwind 桥接**（`@theme inline`）：`bg-bg` `bg-bg-sunk` `bg-card` `border-line`
`border-line-strong` `text-fg` `text-fg-muted` `text-fg-faint` `text-accent` 等工具类
直接映射到上表，组件里因此可以写 `className="bg-card text-fg-muted border-line"`。

---

## 3. 排版

### 3.1 字体栈

```css
--font-sans: ui-sans-serif, system-ui, -apple-system, "SF Pro Text",
             "Helvetica Neue", "PingFang SC", "Noto Sans CJK SC", sans-serif;
--font-mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;
```

**全部系统字体，零 Web Font 请求。** 中文走 PingFang SC / Noto Sans CJK SC。
新设计若要引入自定义字体，需评估首屏与离线表现——目前是零字体加载成本。

### 3.2 字阶（7 级，`tracking` 随字号变，不是一个值走天下）

| 类名 | font-size | line-height | letter-spacing | weight | 其他 | 用途 |
|---|---|---|---|---|---|---|
| `.t-display` | `clamp(1.75rem, 3.2vw, 2.5rem)` | 1.08 | −0.022em | 640 | | 页面 h1 |
| `.t-title` | 1.3125rem (21px) | 1.24 | −0.014em | 620 | | 卡片主标题、抽屉标题 |
| `.t-section` | 1rem (16px) | 1.35 | −0.006em | 600 | | 区块小标题、卡片条目名 |
| `.t-body` | 0.9375rem (15px) | 1.62 | 0 | — | | 正文 |
| `.t-meta` | 0.8125rem (13px) | 1.45 | +0.006em | — | | 次要信息、按钮文字 |
| `.t-micro` | 0.6875rem (11px) | 1.3 | **+0.055em** | 600 | **`text-transform: uppercase`** | 标签、指标名 |
| `.t-mono` | 0.75rem (12px) | — | −0.01em | — | 等宽字体 | id、时间戳、技术值 |

> **`.t-micro` 的 uppercase 是全局的**：中文不受影响，但英文标签全部大写。
> 新设计如取消 uppercase，需检查所有 `t-micro` 位置的英文视觉重量是否失衡。

### 3.3 全局排版设置

```css
html { font: 100% / 1.55 var(--font-sans); }   /* 间距用 rem：用户放大字号时布局跟着长 */
body { -webkit-font-smoothing: antialiased; font-variant-numeric: tabular-nums; }
```

**`tabular-nums` 是全局的** —— 所有数字等宽对齐。指标、百分比、学分、时间在滚动/刷新时
不会左右跳动。新设计不要取消它。

### 3.4 行长约束（实测分布）

| 值 | 出现次数 | 典型用途 |
|---|---|---|
| `max-w-[62ch]` | 9 | 说明段落（最常用）|
| `max-w-[70ch]` | 6 | 卡片内长说明 |
| `max-w-[76ch]` | 4 | 列表项描述 |
| `max-w-[52ch]` | 3 | 抽屉内说明 |
| `max-w-[60ch]` / `[46ch]` | 各 2 | 页头引导语 / 量表题干 |
| `max-w-[72ch]` / `[64ch]` / `[58ch]` | 各 1 | |

---

## 4. 签名元素（**两个，不可替换**）

### 4.1 三值 UNKNOWN 的斜纹 `.hatch-unknown`

```css
.hatch-unknown {
  background-image: repeating-linear-gradient(
    -45deg,
    color-mix(in srgb, var(--hatch) 38%, transparent) 0 2px,
    transparent 2px 6px
  );
}
```

−45° 斜纹，2px 实 / 4px 空，颜色为 `--hatch` 的 38% 混色。

> **[硬约束]** 三值逻辑在视觉上也必须是三值。UNKNOWN **既不是绿也不是红**，
> 也不能是"灰掉的绿"。产品的整个论证建立在"解析不出来 ≠ 你不合格"上。
> 新设计可以换纹理形式（点阵、虚线、其他角度），但**必须保留一个与"满足/不满足"
> 都不同族的第三种视觉语汇**。

### 4.2 凭据票根 `.credential-chip`

```css
.credential-chip { position: relative; isolation: isolate; }
.credential-chip::before, .credential-chip::after {
  content: ""; position: absolute; top: 50%;
  width: 6px; height: 6px; border-radius: 999px;
  background: var(--bg); transform: translateY(-50%);
}
.credential-chip::before { left: -3px; }
.credential-chip::after  { right: -3px; }
```

左右各一个 6px 圆形缺口，**缺口来自真实票据的打孔**。缺口用 `--bg` 填色，
因此它只在直接放在页面底色上时形状正确（放进卡片时需要相应调整填色）。

> **[硬约束]** 凡是来自 Rules 的结论都挂它，带真实 `validation_id`。
> 看得见的审计链比一句"我们很严谨"有用。形状可以改，**不能删**。

---

## 5. 材质与深度

| 类名 | 定义 | 用途 |
|---|---|---|
| `.material-chrome` | `background: var(--card-translucent)` + `blur(20px) saturate(180%)` | 顶栏、底部导航条 —— 内容从下面滚过去，不是一条不透明横条 |
| `.material-modal` | `background: color-mix(in srgb, var(--card) 92%, transparent)` + `blur(32px) saturate(150%)` | 抽屉/模态 —— **刻意比 chrome 更"厚"** |
| `--shadow-card` | 见 §2 | 双层投影：1px 贴边 + 24px 扩散 |

> **为什么模态要更厚**：实测过一版用 `material-chrome` 的抽屉——下面那片卡片网格
> 透上来，正文几乎读不了。"大面积表面读起来要更厚"和"模态要压暗背景"两条都得做，
> 只做其中一条不够。

**降级**：`prefers-reduced-transparency: reduce` 时两者都退化为不透明 `var(--card)`，
`backdrop-filter: none`。

---

## 6. 形状与间距

### 6.1 圆角（实测分布，共 11 个值 / 180 处）

| 值 | 次数 | 用途 |
|---|---|---|
| `9px` | **82** | **默认圆角**：按钮、输入框、下拉、内嵌块 |
| `7px` | 34 | 小控件：标签、次级按钮、分段控件内的段 |
| `10px` | 32 | 卡内嵌块、列表项 |
| `full` | 13 | 徽章、指示点 |
| `6px` | 7 | 网格内小元素 |
| `5px` | 5 | 微标签 |
| `14px` | 3 | 登录卡片（最大） |
| `12px` | 1 | 日历就地编辑面板 |
| `4px` / `3px` / `2px` | 各 1 | 日历区块 / 图例色块 / 进度条 |

> 圆角**没有集中定义**，散在组件里的 Tailwind 任意值中。这是当前实现的一个弱点：
> 新设计交付时建议一并给出 `--radius-sm/md/lg` 三档并集中化。

### 6.2 布局常量

| 值 | 位置 |
|---|---|
| `max-w-[1240px]` | 主内容区最大宽度（顶栏与正文各一处）|
| `max-w-[880px]` | 登录页最大宽度 |
| `w-[210px]` | 侧栏宽度 |
| `top-[74px]` | 侧栏 sticky 偏移（顶栏高度）|
| `lg:` 断点（1024px） | 侧栏显示/隐藏的分界；窄屏导航折到底部 |
| `min-w-[680px]` | 日历周网格最小宽度（低于此值横向滚动）|
| `max-h-[220px]` | 反思对象列表滚动区 |
| `max-h-[132px]` | Advisor 时段滚动区 |
| `px-5 py-8` | 正文区内边距 |
| `gap-8` | 侧栏与正文间距 |

### 6.3 网格最小列宽（`<Grid min={n}>`）

| 值 | 用在 |
|---|---|
| `310` | 推荐卡（for-you）|
| `300` | 目标卡（goals）|
| `290` | 机会卡（square）|
| `280` | 证据卡（profile）|
| `180` | 档案指标格 |
| `168` | 容量指标格 |

### 6.4 日历网格专用常量（`calendar/page.tsx`）

| 常量 | 值 | 说明 |
|---|---|---|
| `DAY_START` | 7 | 只画 07:00 起（凌晨画出来会把有内容的部分压扁）|
| `DAY_END` | 24 | |
| `ROW_HEIGHT` | 26px | 每小时行高 |
| 横线密度 | 每 3 小时一条 | 密了会盖过内容 |
| 区块最小高度 | 6px | |
| 标题显示阈值 | 高度 ≥ 20px | 低于此值不显示标题文字 |

---

## 7. 动效

### 7.1 按下反馈 `.pressable`

```css
.pressable {
  transition: transform 110ms cubic-bezier(0.32, 0.72, 0, 1),
              background-color 140ms ease-out, border-color 140ms ease-out;
  touch-action: manipulation;
}
.pressable:active { transform: scale(0.975); }
```

**按下即反馈，不等 click**（apple-design §1）。缓动 `cubic-bezier(0.32, 0.72, 0, 1)`
是 Apple 的标准出场曲线。

### 7.2 弹簧过渡（motion/react）

| 场景 | 参数 |
|---|---|
| 导航选中态位移（`layoutId="nav-active"`） | `spring, bounce: 0, duration: 0.35` |
| 登录卡入场 | `spring, bounce: 0, duration: 0.45, delay: 0.05 / 0.12` |
| 冲突列表逐条入场 | `spring, bounce: 0, duration: 0.34, delay: index * 0.04` |
| 抽屉 | `spring, bounce: 0.2` |
| 减弱动效时的替代 | `duration: 0.12` 纯淡入 |

**`bounce: 0` 是主基调** —— 全站几乎不用回弹，只有抽屉有轻微的 `0.2`。

### 7.3 焦点

```css
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 5px; }
```

### 7.4 选区

```css
::selection { background: color-mix(in srgb, var(--accent) 28%, transparent); }
```

### 7.5 无障碍降级（三条媒体查询，**全部必须保留**）

| 查询 | 行为 |
|---|---|
| `prefers-reduced-motion: reduce` | 动画 0.01ms、过渡 120ms、`.pressable:active` 取消缩放、滚动改 auto。**减少动效 ≠ 没有反馈** |
| `prefers-reduced-transparency: reduce` | `.material-chrome` / `.material-modal` 退化为不透明 |
| `prefers-contrast: more` | `--line` 提到 .42、`--line-strong` 提到 .62、`--fg-muted` 换成 `#16292a`、材质退化 |

---

## 8. ⚠️ 现存的两个对比度缺陷（实测计算，重设计时请一并修）

我用 WCAG 2.1 相对亮度算法算了全部前景/背景组合。绝大多数达标，**两处不达标**：

### 缺陷 1：`--hatch` 在浅色主题下作正文色不达 AA

| 组合 | 对比度 | AA 要求 | 判定 |
|---|---|---|---|
| `--hatch` `#c2831f` on `--card` | **3.20** | 4.5（普通文字）| ❌ |
| `--hatch` on `--bg` | **2.97** | 4.5 | ❌ |
| `--hatch` on `--bg-sunk` | **2.77** | 4.5 | ❌ |

`--hatch` 在 **15 处**被直接用作文字颜色（`color: "var(--hatch)"`），
字号多为 `.t-meta`（13px）与 `.t-micro`（11px），都不属于 WCAG"大文字"豁免范围。

**这是签名色，不能换成别的色相**。建议解法：浅色主题下把文字用色换成
`--color-ochre-600` `#9a6417`（对比度 **4.52**，刚过 AA），
斜纹与描边继续用 `#c2831f`。

### 缺陷 2：`moss-600` / `clay-600` 在深色主题下完全不达标

这两个色**只定义在 `@theme` 里，从未随主题切换**（`globals.css` 的深色块没有覆盖它们），
但它们在 **31 处**被用作文字颜色。

| 组合 | 浅色 | 深色 | 判定 |
|---|---|---|---|
| `moss-600` on `--card` | 6.36 ✅ | **2.90** ❌ | 深色下不可读 |
| `clay-600` on `--card` | 6.26 ✅ | **2.94** ❌ | 深色下不可读 |

影响：深色主题下所有**成功提示**（"已保存"、"已写入日历"）与**错误提示**
（"保存失败"、"该时段已被约走"）都难以辨认。

**建议解法**：把它们纳入 `:root` 的主题切换，深色下改用 `moss-500` `#3f8a52`
（深色对比度 4.4，接近 AA）或更亮的一档；同时新增 `--color-moss-400` / `--color-clay-400`。

### 达标的部分（供参考，不用改）

| 组合 | 浅色 | 深色 |
|---|---|---|
| `--fg` on `--card` | 18.44 | 15.84 |
| `--fg-muted` on `--card` | 7.35 | 10.35 |
| `--fg-faint` on `--card` | 4.50 | 6.82 |
| `--accent` on `--card` | 7.43 | 8.23 |
| `--accent-fg` on `--accent` | 7.43 | 8.55 |

`--fg-faint` 浅色下 4.50 刚好压线过 AA —— 新设计调背景色时要重算，很容易掉下去。

---

## 9. 新设计的交付要求（映射清单）

设计侧交付时，请按这个清单逐项给出对应值，接入才能是"换皮"：

- [ ] 11 阶中性色 + 7 阶主色 + 5 阶签名色 + 6 个语义色
- [ ] 14 个语义变量 × 2 主题（浅/深）
- [ ] 7 级字阶（含 letter-spacing 与 weight）
- [ ] 字体栈（若引入 Web Font，需说明加载策略）
- [ ] 3 档圆角（替代现在散落的 11 个值）
- [ ] 卡片投影 × 2 主题
- [ ] 两种材质（chrome / modal）的模糊与饱和度参数
- [ ] **三值 UNKNOWN 的第三种视觉语汇**（不可省）
- [ ] **凭据票根的形状**（不可省）
- [ ] 按下反馈的缩放比与缓动曲线
- [ ] 弹簧过渡参数（至少：导航位移、卡片入场、抽屉）
- [ ] 焦点环样式
- [ ] 三条无障碍降级媒体查询下的表现
- [ ] **全部前景/背景组合的对比度自查表**（AA 4.5:1 起）

---

*所有数值抽取自 2026-08-01 的 `main` 分支（commit `b8371bd`）。*
