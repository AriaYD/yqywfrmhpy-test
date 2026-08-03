# CampusPath 学生端 · 界面功能说明书

> **版本** 1.1 · **日期** 2026-08-01 · **对应代码** `apps/web/src/app/**` @ commit `b8371bd`（契约 1.15.0）
>
> **这份文档写给谁**：拿去做 UI/UX 重设计的设计工具或设计师。
> **它是什么**：学生端**每一个页面、每一个控件、每一块内容、每一条接口**的清单。
> **它不是什么**：交互稿、动效说明、信息架构提案。交互与视觉由设计侧产出，本文只负责
> 把"这一页到底要装什么"说清楚，不预设怎么装。
>
> **文档来源**：逐文件读取前端源码 + 浏览器逐页实测（localhost:3100，学生 STU-A，
> 2026-08-01）。文中所有计数、选项枚举、数据量级均为**实测值**，不是预期值。
>
> **配套文档**（三份一起交给设计侧）
> · `CampusPath_Design_Tokens_2026-08-01.md` —— 设计令牌现状表（色板 / 字阶 / 圆角 / 动效 / 对比度自查）
> · `CampusPath_Student_UI_Regression_Checklist_2026-08-01.md` —— 接入后的回归验证清单（155 项）

---

## 变更记录

| 版本 | 日期 | 变更 |
|---|---|---|
| 1.1 | 2026-08-01 | 按 commit `b8371bd` 复核。四处实质变化：① 档案总览由 5 块扩为 **12 个分区**（新增 教育 / 出版物 / 荣誉 / 组织 / 语言 / 爱好 / 课程 / 志愿 **八区**，原「项目与经历」收窄为「项目」，见 §3.2）；② 登录页校方入口由下拉改为 **4 个带说明的岗位卡**（§3.0）；③ 反思记录页 **一次会面只出一条**，预约条目吸收该会面的反思（§3.3）；④ i18n 文案 587 → **626** 条。新增端点 `GET/POST /profile/extras`。 |
| 1.0 | 2026-08-01 | 首版，对应 commit `e588552`（契约 1.6.0）。 |

---

## 0. 阅读约定

| 记号 | 含义 |
|---|---|
| `路由` | Next.js App Router 的 URL 路径，深链接可直达 |
| `分页` | 同一路由内的 tab 面板（不换 URL） |
| **[必存]** | 重设计后必须仍然存在的信息/控件，删掉即功能缺失 |
| **[硬约束]** | 涉及产品架构红线，改动需回到 Spec §8.9 确认，设计侧不可自行取舍 |
| 端点 | 前端实际调用的 API，全部经同源代理 `/api` 转发到 `/v1` |

**术语对照**（界面三语，文案走 i18n 资源，共 **626** 条 key × 3 语言）：

| 中文（简/繁） | English | 说明 |
|---|---|---|
| 机会 / 機會 | Opportunity | 比赛、实习、工作坊、讲座、社团活动等课外资源的统称 |
| 计划项 / 計劃項 | Plan Item | 已进入学生路径的一条待办（课程或活动） |
| 排程提议 / 排程提議 | Schedule Proposal | 系统算好但**尚未生效**的时段安排，待学生批准 |
| 规则凭据 / 規則憑據 | Validation ID | 每条结论背后可追溯的规则运算编号 |
| 三值状态 | Tri-state | 满足 / 不满足 / **未知**——未知是独立的第三态 |

---

## 1. 全局框架（Shell）

所有登录后的页面共用同一个外壳，定义在 `components/shell.tsx`。

### 1.1 顶栏（sticky，全站常驻）

从左到右：

1. **产品标识** `CampusPath` + 副标"有据可查的成长路径"（点击回落地页 `/profile`）
2. **Synthetic / Demo Data 徽章** **[必存]** —— 全站数据为合成数据的声明，法务性质，
   任何页面都不得移除
3. **身份徽章** —— 显示当前学生号（如 `STU-A`）。**只读，不可切换**：换人必须退出重登
4. **主题选择** —— 跟随系统 / 浅色 / 深色（持久化到 localStorage）
5. **语言切换** —— 简 / 繁 / EN 三档（持久化）**[必存]**
6. **退出登录**

### 1.2 侧栏导航（≥1024px 显示；窄屏折到底部横向滚动条）

学生端 **11 个导航项，分 5 组**。校方端的项目对学生会话**完全不可见**（不是灰掉，是不存在）。

```
开始    · 开通与授权
我      · 我的成长档案 ← 登录落地页
        · 反思与笔记
        · 记忆中心
方向    · 目标工作室
        · 成长动态跟踪
        · 日历与容量
        · 行动中心
发现    · 为你推荐
        · 资讯广场
系统    · 设置与隐私
```

选中态是一条滑动的高亮块（`layoutId` 共享过渡），切页时位置连续。

### 1.3 页面骨架

每页统一由 `PageHeader` 起头：`h1 标题` +（可选）一句引导语 +（可选）页头右侧操作区。
正文为最大宽度 1240px 的单列，卡片（`Card`）为基本容器。

### 1.4 全局状态语汇 **[必存]**

四种状态在每个数据区块都可能出现，**设计必须为四种都给出样式**：

| 状态 | 触发 | 现在的表现 |
|---|---|---|
| 加载中 | 请求未回 | `Loading` 骨架 |
| 空 | 200 + 空数组 | `Empty` 文案，可带自定义说明 |
| 缺失（404） | 这个学生真的没有这个东西 | 按"空"处理，**不报错** |
| 依赖不可用（503） | 后端做完了但依赖挂了（如 Vertex 无凭据） | 明说"依赖不可用"，**不能说成"没有推荐"** |
| 无权（403） | 缺少对应授权 | 明说缺哪一项，并就地给授权入口 |
| 限流（429） | 超出每日次数 | 明说次数用完，仍展示缓存结果 |

---

## 2. 页面总表

**学生端共 12 个路由（含登录），15 个 URL 入口，18 个内容面板。**

| # | 路由 | 页面名（简 / EN） | 导航组 | 分页数 | 主要职责 |
|---|---|---|---|---|---|
| 0 | `/login` | 登录 / Login | 不在导航 | 1 | 双门户登录入口 |
| 1 | `/onboarding` | 开通与授权 / Onboarding & Consent | 开始 | 1 | 6 项独立授权开关 + 重要联系人 |
| 2 | `/profile` | 我的成长档案 / My Growth Profile | 我 | 3 | 档案总览（**12 分区**）、证据档案、更新提议 |
| 3 | `/reflections` | 反思与笔记 / Reflection & Notes | 我 | 2 | 写反思、查记录 |
| 4 | `/memory` | 记忆中心 / Memory Center | 我 | 1 | 系统对我的记忆：查/改/锁/删/导出 |
| 5 | `/goals` | 目标工作室 / Goal Studio | 方向 | 1 | 定主/候选目标，看共同要求与分叉 |
| 6 | `/gaps` | 成长动态跟踪 / Growth Tracking | 方向 | 1 | 能力三层 + 每条能力的证据链 |
| 7 | `/calendar` | 日历与容量 / Calendar & Capacity | 方向 | 2 | 周视图编辑器 + 身心容量 |
| 7b | `/wellbeing` | 身心容量 / Wellbeing Capacity | 隐藏路由 | — | 同上第 2 分页的深链接 |
| 8 | `/actions` | 行动中心 / Action Center | 方向 | 3 | 预约、批准排程、活动规划、选课推荐 |
| 8b | `/timeline` | 课外活动规划 / Extracurricular Plan | 隐藏路由 | — | 同上第 2 分页的深链接 |
| 8c | `/planner` | 选修课推荐 / Elective Recommendations | 隐藏路由 | — | 同上第 3 分页的深链接 |
| 9 | `/for-you` | 为你推荐 / For You | 发现 | 1 | A5 排序过的机会推荐 |
| 10 | `/square` | 资讯广场 / Opportunity Square | 发现 | 1 | 全量机会目录，不排序 |
| 11 | `/settings` | 设置与隐私 / Settings & Privacy | 系统 | 1 | 授权回执、外观、导出、删除 |

> **隐藏路由的意思**：`/wellbeing`、`/timeline`、`/planner` 不出现在导航里，但 URL 仍有效，
> 打开后落在对应宿主页的那个分页上。重设计**不能让这三个 URL 404**。

---

## 3. 逐页规格

---

### 3.0 `/login` 登录

**布局**：无侧栏、无顶栏导航（登录页不套 Shell）。页头只有产品名 + Synthetic 徽章 + 语言切换。

**内容**：标题、副标、**两张并排的门户卡**。

| 卡片 | 字段 | 控件 |
|---|---|---|
| **学生端** | 身份（下拉：`STU-A` / `STU-B` / `STU-C`） | `select` |
| | 口令 | `password` 输入 + 提示语（口令明写在界面上，演示性质） |
| | | 主按钮「进入学生端」 |
| **校方管理端** | 身份（**4 张岗位卡，单选**） | 按钮组，非下拉 |
| | 口令 | 同上 |
| | | 次级按钮「进入校方端」 |

**校方 4 个岗位入口**（每个一行主标题 + 一行小字说明，实测文案）：

| 岗位 | 标题 | 说明小字 |
|---|---|---|
| `publisher` | 机会投稿方 | 院系 / 实验室 / 社团 / 雇主联络人——发布实习、比赛与活动机会 |
| `career_center_admin` | Career Center 管理员 | 一人身兼三职：投稿审核、内容策展与质量运营、数据源接入管理 |
| `wellbeing_coordinator` | 心理咨询室 | 学校心理咨询中心部门——处理学生主动发起的外联请求 |
| `advisor` | 学业 / 职业顾问 | Career Center Advisor——确认预约、会后写关键建议 |

> 旧的细分角色（`reviewer` / `curator` / `connector_admin`）仍在会话类型里保留（真实部署可拆），
> 但**不再作为登录入口**——现实中 Career Center 是一个人兼三职。

**行为**：口令错 → 输入框转错误色 + 提示文案（不清空已填内容）。
成功 → 学生落到 `/profile`，校方落到 `/publisher`。
**以哪个岗位登录就是哪个岗位**——登录后没有岗位切换器，换岗必须退出重登
（与学生端同一裁定：切换器 = 免验证看别人的工作台）。

**端点**：无（合成登录，判定在客户端；真实授权由服务端 RBAC 独立成立）。

**设计要点**：两个门户是**平级**关系，但学生端是主路径，视觉权重应更高。

---

### 3.1 `/onboarding` 开通与授权

**页头**：标题 + 引导语 + Synthetic 完整徽章。

#### 内容块 A：授权开关（6 项，**逐项独立**）**[硬约束]**

每项一行：`开关` + `标题` + `一段说明` + `状态微文案`。

| # | 开关标题 | 契约 scope | 默认 | 说明要点 |
|---|---|---|---|---|
| 1 | 教务与学习记录 | `sis_records` + `lms_records` | **开** | 一个开关管两项 |
| 2 | 日历忙闲 | `calendar_freebusy` | **开** | 一级授权：只知道忙/闲，不知道内容 |
| 3 | 日历事件标题 | `calendar_event_titles` | **关** | 二级授权，关着不影响其余功能 |
| 4 | 写入我的日历 | `calendar_write` | **关** | 对学生日历做写入 |
| 5 | 自报身心状态 | `self_reported_wellbeing` | **开** | |
| 6 | 允许主动联系 | `wellbeing_outreach` | **关** | 信息会送出校内系统 |

**状态微文案三态**：已开启 / 已关闭 / 保存中 / **保存失败**（失败时开关回滚，绝不假装成功）。

> **[硬约束]** 关掉任何一项，其余功能照常可用。界面上不得出现"必须全开才能使用"的暗示，
> 也不得把某项做成默认勾选的捆绑。第 3、4、6 项默认关闭这件事不可改。

#### 内容块 B：重要联系人

三行（辅导员 / 班主任 / 班长），每行 3 个输入框：姓名、邮箱、电话。
一个「保存」按钮 + 已保存 / 失败提示。

#### 内容块 C：完成

「完成开通」按钮 + 完成后的确认文案。

**端点**
- `GET /v1/students/{id}/profile` — 读回已记录的授权状态
- `GET /v1/students/{id}/contacts`
- `POST /v1/students/{id}/contacts`
- `POST /v1/students/{id}/consents` — 每次切换即调用，拿服务端回执

---

### 3.2 `/profile` 我的成长档案 ← **登录落地页**

**页头**：标题 + **三分页切换器**（Segmented）：总览 / 证据档案 / 更新提议。

#### 分页 1：总览（**LinkedIn 式完整履历，12 个分区**）

**卡片 0 · 关键指标**（4 格 Metric）
专业（显示官方全名，如「计算机科学理学士 (BSc in Computer Science)」）· 年级 · 已修学分 · 发展模式

**卡片 0 续 · 技能与兴趣标签**
- 只读态：标签云（实测 STU-A 有 3 个：web development / game design / generative ai）
- 右上角 **「编辑」按钮 —— 这一个按钮同时切换本页全部可编辑分区** **[必存]**
- 编辑态：每个标签带 `×` 删除、下方一个输入框 + `+` 新增；顶部出现 保存 / 取消
- 一句说明：这是**你自己的**标签，不是专业必备技能清单 **[必存]**

**12 个分区，按页面实际顺序**：

| # | 分区 | 数据来源 | 可编辑 | 每条包含 |
|---|---|---|---|---|
| 1 | **上传 Resume** | — | — | 见下方说明 |
| 2 | **实习与工作** | `experiences`（internship / part_time / entrepreneurship）| 否（来自档案）| 角色 · 组织 · 起止 · **核验状态** · 职责（≤3）· 成果 · 技能标签 |
| 3 | **教育经历 (Education)** | `profile/extras` | **是** | 学校 · 专业/项目 · 起始年 → 结束年 · 备注 |
| 4 | **出版物 (Publications)** | `profile/extras` | **是** | 名称（可带链接 ↗）· 颁发/所属机构 · 日期 · 备注 |
| 5 | **荣誉与奖项 (Honors & Awards)** | `profile/extras` | **是** | 同上 |
| 6 | **组织机构 (Organizations)** | `profile/extras` | **是** | 同上 |
| 7 | **语言 (Languages)** | `profile/extras` | **是** | 语言 · 流利程度 · 考级（可选）|
| 8 | **兴趣爱好 (Interests)** | `profile/extras` | **是** | 标签形式；编辑态回车添加 |
| 9 | **项目 (Projects)** | `experiences`（project / research / competition）| 否 | 同分区 2 |
| 10 | **志愿与助理工作 (Volunteering)** | `experiences`（volunteer / club）| 否 | 同分区 2 |
| 11 | **课程 (Courses)** | `academic-state`（SIS 派生）| **否 —— 只读** | 课程码标签组（实测 12 个），hover 显示学期 |
| 12 | **课外课程与证书** | `evidence`（certificate / link）| 否 | 名称 · 颁发方 · 获得日期 · 核验状态 · 外链 |

**分区 1 · 上传 Resume 的细则**
- 主按钮「选择文件（md / txt / pdf）」（原生 file input 隐藏但保持可聚焦）
- 状态：解析中 / 完成 / 失败
- 说明文案要点：解析出的内容变成**待确认提议**（去第 3 分页），与现有档案冲突的会标出旧值；
  **原文解析后即丢弃，不落库** **[必存]**

**编辑态行为**（实测）
- 点一次「编辑」→ 标签编辑器 + **6 个自述分区**同时进入编辑态（实测 29 个输入框、5 个「添加一条」按钮、10 个删除按钮）
- 每个自述分区底部有「+ 添加一条」；每行末尾有 `×` 删除
- 「保存」一次性提交标签与全部补充分区；「取消」全部丢弃

> **[硬约束] 出处决定可编辑性。**
> - **自述分区**（教育 / 出版物 / 荣誉 / 组织 / 语言 / 爱好）—— 学生自填自改，整体标记为自述。
> - **课程分区** —— 出处在教务系统（SIS），**学生不能自由编辑**。说明文字明写这一点。
>   网络课程与自学证书走「课外课程与证书」分区，两者不能混。
> - **经历分区**（实习/项目/志愿）与**证书** —— 各自带核验状态，不在这里自由改。
>
> **"自述"不能被渲染成"已认证"。** 三值指示器里，自述 = **未知**（斜纹），
> 不是"不满足"——"你说了但没人证实"和"证实为假"是两回事。

#### 分页 2：证据档案

- 顶部说明卡 + **上传证据**：类型下拉（certificate / artifact / transcript / screenshot / other）
  + 上传按钮 + 成功/失败提示
- 网格卡片：每张证据一卡 —— 类型 · 颁发方/来源 · 获得日期（→ 过期日期）· 三值核验指示器 · 可见性

#### 分页 3：更新提议

系统从 Resume / 反思里提炼出的档案变更，等学生逐条裁定。
每条：变更理由 · 状态 · 逐行列出 `操作 · 字段路径 → 新值`；`pending` 状态下有
「接受」/「拒绝」两个按钮。

**端点**
`GET profile` · `GET degree-progress` · `GET evidence` · `GET experiences` ·
`GET academic-state` · **`GET profile/extras`** · `GET profile/proposals`
`POST profile/self-edit` · **`POST profile/extras`** · `POST resume` · `POST evidence` ·
`POST profile/proposals/{id}/decision?decision=confirmed|rejected`

---

### 3.3 `/reflections` 反思与笔记

**页头**：标题 + 引导语 + **两分页**：写一条反思 / 反思记录。

#### 分页 1：写一条反思

**步骤 1 · 选对象**
- 五个筛选按钮：全部 / 经历 / 课程 / 机会 / Advisor
- 对象列表（最高 220px 滚动区），每项：标题 · 副信息（日期/学期/主办方）· 右侧类型标签
- 对象来源：我的经历、**修过或在修**的课、进了计划或已报名的机会、已完成的 Advisor 会面

**步骤 2 · 写正文**
多行文本框（未选对象时禁用并提示先选对象）

**步骤 3 · 三维评分**（每维 1–5，按钮组）
内容深度 / 实际收获 / 组织质量

**步骤 4 · 匹配标签**（五选一）
刚好合适 / 对我太基础 / 对我太难 / 形式不适合我 / 时间不合适

**边界声明卡** **[硬约束]**
一段虚线框文案：原文留在私有域，**只有评分与结构化标签会向下游传递**。
这不是承诺而是类型层事实，界面必须明说。

**保存按钮** + 已保存 / 失败提示。

#### 分页 2：反思记录

**筛选条**
- 搜索框（搜正文与对象 id）
- 六个类别按钮（实测文案）：全部 / **Advisor 会面** / **讲座课程** / **实习与工作** / **实验室与研究** / **其他活动**
- 三个评分下限下拉：内容深度 / 实际收获 / 组织质量，各可选 全部 / ≥3 / ≥4 / ≥5

**记录列表**（反思 + 笔记 + Advisor 会面**合并成一个列表**，按日期倒序）

普通条目：类别 · 日期 · 对象 id · 正文（保留换行）· 三维评分 + 匹配标签

**Advisor 条目：一次会面只出一条** **[必存]**

> 预约条目**吸收**学生为它写的反思——同一件事不在列表里出现两次。
> 被吸收的反思不再单独成条；同一会面写了多条时取最新一条并入卡片。

一张会面卡上依次是：
1. 类别「Advisor 会面」+ 日期
2. **主题**：`主题：<topic>`
3. 时间 + 预约状态（已申请 / 已确认 / 已完成 / …）
4. **我的反思** —— 学生自己写的那段（有才显示）
5. 三维评分 + 匹配标签（从并入的反思取）
6. **Advisor 的关键建议** —— 见下方门禁规则

**"先写后看"门禁** **[必存]**
- 已写过这次会面的反思 → 展开「关键建议」列表
- 未写 → 显示锁定框 + 「去写这次会面的反思」按钮（跳到分页 1 并预选该对象）
- 设计意图：先记下自己的收获，再看别人给你的总结

> ⚠️ 实测提示：`STU-A` 当前有 **0 条** Advisor 预约（`/advisor/bookings` 返回 `[]`），
> 因此合并卡与门禁在这个数据状态下**观测不到**。验证时需先在 `/actions` 预约一个时段。

**端点**
`GET advisor/bookings` · `GET experiences` · `GET academic-state` · `GET pathway` ·
`GET catalog/opportunities` · `GET actions` · `GET notes` · `GET reflections`
`POST reflections` · `POST event-feedback`（仅当对象是机会时）

---

### 3.4 `/memory` 记忆中心

**页头**：标题 + 引导语 + 右侧「导出全部」按钮（下载 JSON，客户端生成）。

**记忆条目列表**，每条一张卡：
- 元信息行：类型 · 来源 · 置信度百分比
- 记忆正文
- 溯源行：生效日期 · 权威等级 · 可见性
- **四个操作** **[必存]**：
  - 「纠正」→ 展开文本框 + 提交 / 取消
  - 「锁定」（已锁定则禁用并变主色）
  - 「删除」（危险色描边）
  - 页头的「导出」

> **[必存]** D2 要求记忆可**查看 / 纠正 / 锁定 / 删除 / 导出**五件事齐全，缺一不可。

**端点**
`GET memory` · `POST memory/{id}/correction` · `POST memory/{id}/lock` · `POST memory/{id}/forget`

---

### 3.5 `/goals` 目标工作室

#### 内容块 A：设定目标（**两步，顺序不能反**）**[必存]**

**第一步 · 选方向**（5 个按钮，单选可取消）
就业 / 深造 / 创业 / **探索中** / 个人兴趣

> **[硬约束]** 「探索中」是**一等选项**，不是"还没想好"的占位。选它之后**不要求填终点**。
> 界面不得把它做得比其他四项弱、也不得在选它之后追问"那你到底想做什么"。

**第二步 · 写下终点**（选了方向后才出现）
- 方向对应的提示语（就业→职位、深造→项目、创业→行业、个人兴趣→技能）
- 文本输入（最多 200 字；「探索中」时此框不出现）
- 角色切换：主目标 / 候选目标
- 「保存目标」按钮

#### 内容块 B：目标卡（两张并排：主目标 / 候选目标）

每张：方向标签 · 目标名称 · 目标类型 + 时间跨度 · **信心度进度条 + 百分比** · 备选项标签

**目标拆解面板**（挂在每张目标卡下方）分三层：
- **硬性条件** —— 卡着门槛的
- **软性条件** —— 每条带**取证来源**
- **特殊约束**

每条格式：`[类别] 描述` +（软性条目）`取证来源：…`
拆解 Pack 不存在的方向（探索中 / 个人兴趣）→ 如实显示"该方向暂无拆解 Pack"，**不套用别人的模板**。

#### 内容块 C：共同要求 vs 分叉点（并排两卡）

**共同要求**：按硬性 / 软性 / 约束三层分组，每行 `类别名称` + `主目标数 ↔ 候选目标数`
（同类别的多条在展示层合并计数）

**分叉点**：按学期分块，每块内分「仅主目标需要」/「仅候选目标需要」，
再按三层列出类别标签。斜纹边框（这是"未知/待定"的视觉语汇）。

**端点**
`GET goals` · `GET gap-map` · `GET goals/{goalId}/decomposition` · `POST goals`

---

### 3.6 `/gaps` 成长动态跟踪

**页头**：标题 + 引导语。

**内容**：按 **硬性条件 / 软性条件 / 特殊约束** 三张卡分组。每张卡内列出该层的能力条目，
每条条目下面挂**这个学生自己的证据链**：

- ✓ **已写完反思的活动** —— 活动名称 · 获得日期 · 核验状态
- **已完成的选修课** —— 课程码标签组（只挂在课程/技能类的硬性条目下）
- 两者都没有 → 明说"暂无证据"，不留空白

> **设计意图**：必修课人人都要修，区分不了学生；真正拉开差距的是**选修课与课外活动**。
> 这一页刻意不罗列必修课、也不做完成度百分比。

**空态**：还没设主目标 → 提示先去目标工作室；主目标方向无拆解 Pack → 如实说明。

**端点**
`GET goals` · `GET evidence` · `GET academic-state` · `GET catalog/opportunities` ·
`GET catalog/programs` · `GET profile` · `GET goals/{goalId}/decomposition`

---

### 3.7 `/calendar` 日历与容量

**两分页**：日历与容量 / 身心容量（后者内容见 3.7b）。

#### 分页 1：日历与容量

**页头右侧**
- `Fixture 数据` 徽章（斜纹色）
- **授权层级徽章** **[硬约束]**：`仅忙闲` 或 `含事件标题` —— 由服务端返回的数据决定，
  不由前端决定。一级授权下 API 返回的 title 就是 null
- 周切换：`←` · 当前周区间 · `→`

**卡片 1 · 日常作息**
睡眠时间段 + 早/午/晚餐三个可勾选的时间段（`time` 输入），「应用到本周期」按钮。
说明要点：作息由学生**显式提交**，系统**不从日历反推** **[硬约束]**；
作息不扣可支配容量，自己额外划的保护时段才扣。

**卡片 2 · 容量快照**（5 格 Metric + 1 条进度条）
固定负担 · 保护时段 · 可用空档 · **可支配容量**（为负时转警示色）· 缓冲占比
进度条：已安排 / 可支配（实测 STU-A：4.9 / 5.3 小时）
过载时追加一个警示条：`过载` + 一句解释

> ⚠️ **本节有一处进行中的改动（截至 2026-08-01 尚未提交，代号 R7-C）**：
> 日历正在从「07:00–24:00 周视图」改为「**00:00–24:00 整天** + **周 / 月两种模式**」。
> 月视图看分布、周视图做编辑（Google Calendar 的分工）。改动理由：**睡眠窗口
> 23:00–07:30 正好被旧的起始时间裁掉**，而身心容量的睡眠不足判定看的就是这段——
> 日历必须让人亲眼看到它。
> 新增钩子：`data-view-option` `data-month-grid` `data-month-day` `data-month-day-count`
> `data-month-chip` `data-month-label` `data-month-prev` `data-month-next`。
> **设计侧请按 24 小时 + 双模式来做**；本节下方描述的是已提交版本，落库后我会再校一次。

**卡片 3 · 周视图网格**（本页的主体）
- 7 天 × 07:00–24:00，行高 26px，每 3 小时一条横线
- 区块按**分钟**定位，不对齐整点
- 五种区块类型 + 图例：忙（主色）/ 空（透明描边）/ 保护（陶土色）/ 缓冲（苔绿）/ 弹性（海蓝）
- **标题只在二级授权或学生自己命名时才有**；没有就留空，**不填"忙"字充数** **[硬约束]**
- 实测：22 个区块 / 周，其中 15 个有标题

**交互入口**（交互细节由设计侧定，此处只列必须存在的入口）
- 点空白格 → 新建行程
- 点区块 → 编辑该区块

**就地编辑面板**（出现在网格正下方）
字段：标签（文本）· 开始（time）· 结束（time）· 类型（忙/弹性/保护/缓冲）· 提醒（无 / 10 / 30 / 60 分钟）
编辑既有区块时额外显示**官方页面外链**（课程→教务页，活动→机会官方页）
按钮：保存 / 删除（仅编辑态）/ 取消

**改动后的重排询问** **[必存]**
改完弹出一个询问框：要不要重排近两周？「重排」/「不用」两个按钮。
选重排后显示影响范围：`受影响条目数 / 未受影响条目数`。
**默认不重排** —— 动学生的计划必须他点头。

**页脚两段说明**：当前授权层级的含义 · 容量口径的解释

**端点**
`GET availability` · `GET capacity-snapshot` · `GET catalog/opportunities`
`POST availability` · `POST availability/{blockId}/update` · `POST availability/{blockId}/remove` ·
`POST routine` · `POST replan-preview`

---

### 3.7b `/wellbeing` 身心容量（`/calendar` 第 2 分页 + 独立深链接）

> **[硬约束] 全链零 LLM。** 这一页上每一句话要么来自 i18n 资源，要么来自后端固定模板；
> 数字来自阈值运算。**没有任何一段文案是模型生成的**。免责声明因此 100% 出现——
> 它不依赖模型记得说。重设计不得引入任何"AI 生成建议"类的模块。

**页头**：标题 + 引导语 + **绿色「零 LLM」徽章** **[必存]**

**信号列表**（5 类，每条一卡）
睡眠机会被压缩 / 自报睡眠不足 / 活动机会偏低 / 缺少恢复时段 / 容量过载

每卡：
- 信号名 + **三档严重度**标签：记录 / 需留意 / 阻断（`info` 是"记一笔"，不是"出事了"）
- `观察值` / `参考线` 两行 —— **是模板填出来的文字，不是数字**（五个信号量纲不同，
  硬凑成百分比会得到看起来精确其实无意义的数）
- **数据覆盖率**单独一条进度条 + `有数据天数 / 窗口天数` —— 覆盖 2/7 天的结论
  不该看起来和覆盖 7/7 的一样有分量 **[必存]**
- 溯源行：规则 id · 统计区间

**提醒状态机卡** **[必存]**
- 已发出的提醒列表：第 1 次 / 第 2 次 · 低负担模式标签 · 送达时间 · 重新评估时间
- **达到 2 次后显示"已达上限，不会再发"** —— 学生有权知道这套东西会不会一直找他

**免责声明**（i18n 常量，不来自任何生成过程）

**自评卡**（ISI 7 题 + PSS-10 10 题）
- 升级判定层级 +（无睡眠窗口时）提示
- 「开始自评」→ 展开量表：每题一行，右侧 0–4 五个按钮
- 「提交」→ 结果区：`ISI x/28（分级）· PSS-10 y/40（分级）` + **分流建议文案** + 免责声明
- 计分与分流全在服务端

**主动联系卡**
说明 + 「请求主动联系」按钮 + 已记录 / 错误提示。
服务端会验同意，没有有效同意直接 403，界面照实说，**不伪装成成功** **[必存]**。

**端点**
`GET wellbeing/signals` · `GET wellbeing/reminders` · `GET wellbeing/escalation` ·
`POST wellbeing/assessment` · `POST wellbeing/outreach`

---

### 3.8 `/actions` `/timeline` `/planner` 行动中心（三分页共用一页）

顶部三个分页按钮：**行动中心** / **课外活动规划** / **选修课推荐**。
三个 URL 各自落在对应分页。

---

#### 分页 1：行动中心（`/actions`）

**卡片 1 · Career Center Advisor 预约**（置顶）
- 说明 + **违约规则声明框**：预约必到；一学期爽约 3 次暂停预约资格 **[必存]**
- 顾问名录（实测 3 位）：姓名 · 专长方向 · 时段按钮组（实测 90 个时段）
  - 已被约走的时段：**禁用 + 删除线 + 降透明度**（库存实时）
- 主题输入框 + 「预约」按钮（按钮文案带上已选时段）
- 四种结果提示：已提交 / **该时段刚被约走** / **已被暂停预约资格** / 暂不可用
- 我的预约列表：主题 · 时间 · 状态 · 「取消」按钮（提前 <1 天会被服务端拒绝并说明后果）
- 已完成且有总结的预约展开「关键建议」

**卡片 2 · 同意回执**说明

**卡片 3 · 等你批准**（排程提议列表）**[硬约束]**

> **预览 → 批准 → 执行，三步分开。这一页不做"一键全部批准"。**
> 回执是对**你看过的那份内容**做的指纹；批量批准会让"看过"失去含义。

每条提议：
- 提议编号
- 逐时段列表：计划项 id · 起止时间
- **活动详情块**（若关联到机会）：
  - 活动全名
  - 截止日期 / 活动时间跨度 / 总投入小时数
  - **前置要求**（最多 4 条规则表达式）
  - **备考提前量提示**：`建议从 {日期} 开始准备（约 {天数} 天）` —— 确定性估算，界面注明
- **阻断冲突警示条**（与保护时段撞车时出现，此时批准按钮禁用）
- 按钮：「批准」/「拒绝」
- 批准后的三种结果：
  - 已写入日历（绿）
  - **已批准但未能写入日历**（斜纹色）
  - 若失败原因是缺 `calendar_write` 授权 → 就地出现「授予日历写入权限」按钮，
    授权后自动重试 **[必存]**

**卡片 4 · 未来两周**
进行中的计划项列表：标题 · 起止日期 · **规则凭据票根**

---

#### 分页 2：课外活动规划（`/timeline`）

> 只呈现**课外**条目 —— 比赛、实习、工作坊、证书、语言考试。
> **课程一律不进本页**（在第 3 分页）。

**页头**：标题 + 引导语 + **四档跨度切换**：近两周 / 一个月 / 本学期 / 一年

**卡片 1 · 成长曲线**
- 三格 Metric：累计关闭差距数 / 累计新增已确认证据 / 当前目标信心度
- 逐学期柱状图：数值就是"已验证的成长行动数"，**不做平滑、不做插值** **[必存]**

**活动卡列表**（时间线）
每张卡：
- 时间行（优先取机会的真实起止，否则取计划项日期）
- 活动标题
- 元信息：类型 · 投入小时数 · 主办方 · 分类标签
- **简介**（来自来源的证据片段）
- **推荐理由** **[必存]** —— 优先取 A5 的匹配理由；没有就按规则生成，
  并**明确标注"（规则生成）"**，不冒充模型判断
- 官方页面外链
- 右侧：状态标签（待定 / 进行中 / 已完成）+ **规则凭据票根**
- 底部进度条

**辅助提示**：`demo_fixture` 数据时显示假设声明条；有课程被隐藏时显示"课程在选课分页"提示。

---

#### 分页 3：选修课推荐（`/planner`）

**卡片 1 · 专业课程地图**
- 只显示**登录学生自己的专业**（无专业选择器 —— 别的专业不堆在这个平台上）
- 学院 · 总学分要求 · 替代说明
- **学期切换下拉**：按要求组总览 / 大一上 … 大四下（8 档）
  - 选具体学期 → 该学期的必修课程码 + 说明 + **来源注明**
  - 「按要求组总览」→ 要求组卡片网格：组名 · 类型标签（必修用警示色）·
    学分/门数要求 · 择一逻辑标记 · **只有必修组铺课程码**（最多 16 个 + 溢出计数）
- 大学毕业要求清单
- 专业未抓到沙箱时：如实说明，**不显示别的专业冒充** **[必存]**

**卡片 2 · 学位进度**
`已修学分 / 总要求学分` + `还差 N` + 进度条

**卡片 3 · 搜索条**
搜索框（搜课程码 / 课名 / 技能标签）+ 右侧「需确认」计数

**推荐课程列表**（规则初筛 + AI 复筛，必修课不出现）
每条：
- `课程码 + 课名 + 学分`
- 课程描述（截断 2 行）
- **推荐理由** **[必存]**：`为什么推荐：…`，规则生成的标注"（规则生成）"
- 先修说明（斜纹色）
- 技能标签（最多 5 个）+ 官方页面外链
- 右侧：AI 复筛后仍拿不准的课挂**「需确认」**标记（斜纹色）**[必存]**

**端点（三分页合计）**
`GET schedule-proposals` · `GET pathway` · `GET catalog/opportunities` · `GET matches` ·
`GET growth-trajectory` · `GET course-recommendations` · `GET degree-progress` ·
`GET profile` · `GET catalog/programs` · `GET advising/advisors` · `GET advisor/bookings`
`POST schedule-proposals` · `POST calendar-actions` · `POST consents` ·
`POST advisor/bookings` · `POST advisor/bookings/{id}/cancel`

---

### 3.9 `/for-you` 为你推荐

> 唯一被允许做取舍的那个 Agent（A5）的输出。**它需要 Vertex 后端**；
> 没有凭据时 `/matches` 返回 503，界面必须说"依赖不可用"，
> **不能说"没有推荐"** —— 后者是谎话，而且资讯广场此时仍然完整。**[硬约束]**

**页头**：标题 + 引导语 + 右侧「重新计算推荐」按钮
**缓存说明**：推荐每天自动重算一次；手动刷新**每天限 3 次**
刷新结果两态：已刷新 / **今日次数已用完**（429，结果仍是缓存的，如实告知）

**推荐卡网格**（实测 STU-A 有多张卡）
每张：
- 机会标题 + 机会 id（id 用等宽小字，标题从目录取 —— 卡上放一串 id 等于让学生自己查表）
- 右上 **四态资格指示器** **[硬约束]**：
  - 现在可报 → **满足**
  - 未来可报 → **未知**
  - 待确认 → **未知**（绝不能映射成"不满足"）
  - 本轮不符合 → **不满足**
- **为什么是这个** —— 理由列表（实测每张 1 条，如"提升商业分析能力，掌握职场沟通技巧。"）
- **契合度**：进度条 + 百分比（实测 59%）
- 投入评估（如 `comfortable`）· 关闭差距数（如 2）
- **规则凭据票根**（带真实 `validation_id`，实测如 `val_a7ff4257…`）
- 「去报名」按钮 —— **仅当状态是"现在可报"时出现**
  - 点击后：记录行动 → 同步生成一条待批准的排程提议（**不越权直接写日历**）→ 新窗口打开官方页
  - 按钮转为「已报名」并禁用

**端点**
`GET matches` · `GET catalog/opportunities` · `POST matches/refresh` ·
`POST actions` · `POST schedule-proposals`

---

### 3.10 `/square` 资讯广场

> **全部已审核通过的机会，不排序。** 它存在的理由是"AI 未推荐但学生主动发现"这条路径
> 必须走得通 —— 一个只给推荐结果的产品会把没被推荐的东西变成不存在。**[硬约束]**

**页头筛选条**（实测 7 个筛选器 + 1 个计数）

| 控件 | 类型 | 实测选项 |
|---|---|---|
| 类型 | 下拉 | club_activity / competition / event / internship / job / mentorship / research_position / workshop（8 类） |
| 标签 | 下拉 | 由目录动态生成 |
| 官方来源 | 复选 | 只看 HKUST 官方来源 |
| 主办方 | 下拉 | 校友 / 校园官方（主校区）/ Career Center / 企业 / 合作企业 / 学院与学系 / 学生社团（**8 大类**）|
| 有截止日期 | 复选 | |
| 含已截止 | 复选 | 默认**不含** |
| 只看收藏 | 复选 | |
| 清空筛选 | 按钮 | |
| 计数 | 文字 | 实测「**177 个机会**」 |

**机会卡网格**（实测 177 张）
每张：
- 顶行：类型微标签 + **已截止标签**（警示色描边）+ **官方来源标签**（主色描边）
  - 已截止的必须**一眼看得出**，不能和还开着的长得一样 **[必存]**
- 标题（本地化）
- 主办方（本地化）
- 截止日期
- 分类标签（最多 4 个）
- **三个操作按钮** **[必存]**：
  - 「收藏 / 已收藏」—— 可取消，乐观更新（点击立刻有反应）
  - 「加入我的日程」—— 打开抽屉，见下
  - 「为什么没推荐？」—— 打开抽屉，见下

#### 抽屉 A：加入我的日程（三步）**[硬约束]**

1. **排程预览** —— 显示拟占用的时段；来源没给开始时间时标注"（系统假定的时段）"；
   长期项目（>8 小时）额外说明"这是长期承诺，只排第一天两小时作为起点"
2. **冲突高亮** —— 逐条列出冲突：
   - **阻断**（与保护时段撞车：睡眠/用餐/照护）→ 警示色，**两个添加按钮都禁用**
   - **软冲突**（与普通忙碌撞车）→ 斜纹色，仅提示
   - 无冲突 → 明说"无冲突"
3. **由学生决定要不要重排** —— 「只加入，不重排」/「加入并重排」两个按钮，
   **默认不重排**。重排后显示影响范围：会动 N 条 / 不动 M 条 + 理由
4. 完成态：确认文案 + 「去行动中心」链接

#### 抽屉 B：为什么没推荐

- 三值状态指示器
- 一句总结
- **缺什么** —— 逐条列出
- **什么时候能达到**（若可推算）
- **规则凭据票根** —— 答案来自 Rules，不是模型的事后解释 **[硬约束]**

**端点**
`GET catalog/opportunities?limit=500[&include_expired=true]` · `GET actions` ·
`GET catalog/opportunities/{id}/why-not-recommended?student_id=…` ·
`POST actions`（save / unsave / add_to_pathway）· `POST schedule-proposals` · `POST replan-preview`

---

### 3.11 `/settings` 设置与隐私

**卡片 1 · 授权回执**
列出服务端记录的每一条同意：开关（只读镜像）+ 人类可读名称 + `scope 原文 · 回执 id`

**卡片 2 · 外观**
- 语言（Segmented：简 / 繁 / EN）
- 主题（Segmented：跟随系统 / 浅色 / 深色）
- 偏好强度（只读：温和 / 平衡 / 冲刺）

**卡片 3 · 数据**
- 「导出我的数据」→ 下载完整 JSON
- 「删除我的数据」（危险色描边）→ **唯一使用确认框的动作** **[硬约束]**
  - 确认框（`role="alertdialog"`）：警示文案 + 「取消」/「确认删除」
  - 确认后：服务端清除 → 本地登出 → 回登录页

> **[硬约束]** apple-design §16.2：确认框只留给真正不可逆的事。到处都用，
> 人就会训练出"闭眼点确定"的手感，那时它对真正危险的操作也不再有效。
> **重设计不得给其他操作加确认框。**

**卡片 4 · 关于**
数据声明文案 + Synthetic 完整徽章

**端点**
`GET profile` · `GET export` · `POST deletion-request`

---

## 4. 共享组件清单（`components/ui.tsx`）

重设计需要为这 15 个原语各出一套样式，它们全站复用，别处不再自造：

| 组件 | 用途 | 备注 |
|---|---|---|
| `PageHeader` | 页头：h1 + 引导语 + 操作区 | 每页必用 |
| `Card` | 基础容器 | |
| `SectionTitle` | 卡内小标题 | |
| `Grid` | 自适应网格（可设最小列宽） | |
| **`TriState`** | **三值指示器** | **签名元素**：UNKNOWN 用**斜纹**，既不是绿也不是红 **[硬约束]** |
| **`CredentialChip`** | **规则凭据票根** | **签名元素**：任何来自 Rules 的结论都挂着它，带真实 validation_id **[硬约束]** |
| `Loading` | 加载骨架 | |
| `Empty` | 空态 | 可带自定义文案 |
| `Failure` | 失败态 | 区分 404 / 503 / 通用错误，带重试 |
| `Metric` | 指标格：标签 + 数值 + 单位 | 支持 good / warn 语气 |
| `Bar` | 进度条 | 支持 accent / warn 语气 |
| `Toggle` | 开关 | |
| `Segmented` | 分段控件 | 用于分页与二选一 |
| `Drawer` | 侧滑抽屉 | 用于"为什么没推荐"与"加入日程" |
| `SyntheticBadge` | 合成数据徽章 | 简版 / 完整版两态 **[必存]** |

**两个签名元素不可替换**：
- `TriState` 的**斜纹**承载了整个产品的核心论证——"解析不出来 ≠ 你不合格"。
  配色必须承认第三种状态，不能退化成绿/红二值。
- `CredentialChip` 是看得见的审计链。凡是规则结论就必须挂它，
  设计上可以变形，但不能删。

**另有 6 个跨页复合模块**（不在 `ui.tsx`，但被多页复用）：

| 文件 | 组件 | 用在 |
|---|---|---|
| `components/shell.tsx` | `Shell` / `Sidebar` / `LocaleSwitch` | 全站外壳 |
| `components/nav.ts` | `NAV_ITEMS` | **导航的唯一出处** —— 导航栏、面包屑、门户守卫、实测脚本都从这里取 |
| `components/plan-hub.tsx` | `PlanHub` | `/actions` `/timeline` `/planner` 三分页容器 |
| `components/add-to-plan.tsx` | `AddToPlan` | 资讯广场的「加入我的日程」抽屉（三步流程） |
| `components/advisor-booking.tsx` | `AdvisorBookingPanel` | 行动中心置顶的预约面板 |
| `components/profile-extras.tsx` | `ProfileExtrasSections` | 档案总览的 6 个自述分区（显示与编辑同一组件） |

> `nav.ts` 是**唯一出处**这件事很重要：新设计若要改导航结构，改这一个文件，
> 不要在各处硬编码——否则"少做了一页"就不可能只在某一处被发现。

---

## 5. 状态矩阵（每页都要出的态）

| 页面 | 加载 | 空 | 404 | 503 | 403 | 429 | 冲突/阻断 |
|---|---|---|---|---|---|---|---|
| /onboarding | ✓ | | | | | | 保存失败回滚 |
| /profile | ✓ | ✓ | ✓ | | | | |
| /reflections | ✓ | ✓ | | | | | 无对象可选 |
| /memory | ✓ | ✓ | | | | | |
| /goals | ✓ | ✓ | | | | | 无拆解 Pack |
| /gaps | ✓ | ✓ | | | | | 无主目标 / 无证据 |
| /calendar | ✓ | ✓ | | | | | 授权层级差异 |
| /wellbeing | ✓ | ✓ | | | **✓** 外联需同意 | | 覆盖率不足 |
| /actions | ✓ | ✓ | | | **✓** 缺日历写入 | | **✓** 阻断冲突 |
| /planner | ✓ | ✓ | | | | | 专业未入库 |
| /for-you | ✓ | ✓ | | **✓** A5 依赖 | | **✓** 刷新限次 | |
| /square | ✓ | ✓ | | | | | **✓** 加入日程冲突 |
| /settings | ✓ | | | | | | 删除确认 |

---

## 6. 重设计不可破坏的硬约束（汇总）

按重要性排序。设计侧如需触碰任意一条，必须先回到 `CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md` §8.9 确认。

1. **三值不能压成二值** —— 「待确认 / 未知」必须有独立于"满足"和"不满足"的视觉表达。
   把 UNKNOWN 折叠成 NOT_MET 是这个产品最不能犯的错：解析器读不懂一句话，学生就被告知"你不够格"。
2. **规则凭据必须可见** —— 每条来自 Rules 的结论挂 `validation_id`。
3. **身心容量页零 LLM** —— 不得引入任何"AI 生成的关怀建议"模块；免责声明必须常驻。
4. **日历授权分两级** —— 一级只有忙闲，二级才有标题。没有标题时留空，不填占位词。
   参与人、地点、备注在**任何层级**都不存在。
5. **预览 → 批准 → 执行三步分开** —— 不做"一键全部批准"；不做"自动写入日历"。
6. **重排默认不发生** —— 动学生的计划必须他点头。
7. **授权逐项独立** —— 关掉任何一项，其余功能照常。
8. **确认框只给删除** —— 其他操作一律不加。
9. **"探索中"是一等选项** —— 不是占位，不追问，不弱化。
10. **资讯广场不排序、可看全部** —— 包括"为什么没推荐"这条反向解释路径。
11. **Synthetic / Demo Data 徽章全站常驻**。
12. **三语（简/繁/英）可切换且持久化** —— 文案全部走 i18n，不硬编码任何语言。
13. **两个门户互不可见** —— 学生会话里校方页面等于不存在。
    登录后**没有身份/岗位切换器**，换人换岗一律退出重登。
14. **出处决定可编辑性** —— 自述分区学生随便改；SIS 派生的课程记录只读；
    带核验状态的经历与证书不在档案页自由改。三者不能混成一个"都能编辑"的表单。
15. **功能基线 F01–F27 零删减** —— 改实现位置可以，删功能不行。

---

## 7. 真实数据量级（设计时按这个规模考虑，不要按 3 条示例排版）

以实测学生 `STU-A`（计算机科学理学士，2 年级，已修 24 学分）为准：

| 数据 | 实测量 | 对设计的含义 |
|---|---|---|
| 机会目录 | **177 条** | 广场需要筛选 + 计数 + 虚拟滚动考量 |
| 机会类型 | 8 类 | 类型筛选是下拉不是标签组 |
| 主办方分类 | 8 大类（含长名"由 XXX Institute for Advanced Study 主办"） | 下拉需限宽，否则换行时独占整排 |
| 推荐卡 | 每次 5–10 张 | 网格 |
| Advisor | 3 位 / **90 个时段** | 时段区需滚动（现为 132px 高滚动区） |
| 日历区块 | 22 个 / 周，15 个有标题 | 网格密度不低，短区块（<20px）放不下文字 |
| 导航项 | 11 项 / 5 组 | |
| i18n 文案 | **626** 条 key × 3 语言 | 中英文长度差异大，按钮需弹性宽度 |
| 目标 | 主 1 + 候选 1 | |
| 技能标签 | 3–8 个 | |
| **档案总览分区** | **12 个** | 单页很长，需要考虑分区导航或折叠 |
| **档案编辑态输入框** | **29 个 / 5 个添加按钮 / 10 个删除按钮** | 一次 Edit 全页进编辑态，需要清晰的"正在编辑"状态 |
| **课程标签** | 12 个（只读）| |
| 反思记录 | 数条到数十条 | 需搜索 + 三维评分筛选 |
| Advisor 预约 | STU-A 当前 **0** 条 | 空态要能看；有预约时会面卡是合并卡 |

**中英文长度差异**是这套界面最常见的排版陷阱：
中文"重新计算推荐"6 字 vs 英文 "Recalculate recommendations" 27 字符；
繁体比简体平均长 5–8%。所有按钮、标签、指标格必须按最长语言留余量。

---

## 8. 附录 A：学生端端点全表

前端类型全部来自 `contracts/generated/campuspath-api.d.ts`（同一份 OpenAPI 生成）。
角色由请求头 `X-CampusPath-Role` 声明，默认 `student`。

**读取（GET）**

```
/v1/students/{id}/profile
/v1/students/{id}/profile/extras
/v1/students/{id}/profile/proposals
/v1/students/{id}/evidence
/v1/students/{id}/notes
/v1/students/{id}/experiences
/v1/students/{id}/goals
/v1/students/{id}/goals/{goalId}/decomposition
/v1/students/{id}/availability
/v1/students/{id}/memory
/v1/students/{id}/academic-state
/v1/students/{id}/degree-progress
/v1/students/{id}/course-candidates?limit=
/v1/students/{id}/course-recommendations
/v1/students/{id}/gap-map
/v1/students/{id}/growth-trajectory
/v1/students/{id}/capacity-snapshot
/v1/students/{id}/wellbeing/signals
/v1/students/{id}/wellbeing/reminders
/v1/students/{id}/wellbeing/escalation
/v1/students/{id}/contacts
/v1/students/{id}/reflections
/v1/students/{id}/matches
/v1/students/{id}/pathway
/v1/students/{id}/schedule-proposals
/v1/students/{id}/actions
/v1/students/{id}/advisor/bookings
/v1/students/{id}/export
/v1/advising/advisors
/v1/catalog/opportunities?limit=&include_expired=
/v1/catalog/opportunities/{oppId}/why-not-recommended?student_id=
/v1/catalog/courses?limit=&subject=
/v1/catalog/programs
```

**写入（POST）**

```
/v1/students/{id}/consents
/v1/students/{id}/contacts
/v1/students/{id}/profile/self-edit
/v1/students/{id}/profile/extras
/v1/students/{id}/profile/proposals/{proposalId}/decision?decision=confirmed|edited|rejected
/v1/students/{id}/evidence
/v1/students/{id}/resume
/v1/students/{id}/goals
/v1/students/{id}/availability
/v1/students/{id}/availability/{blockId}/update
/v1/students/{id}/availability/{blockId}/remove
/v1/students/{id}/routine
/v1/students/{id}/memory/{memoryId}/correction
/v1/students/{id}/memory/{memoryId}/lock
/v1/students/{id}/memory/{memoryId}/forget
/v1/students/{id}/deletion-request
/v1/students/{id}/reflections
/v1/students/{id}/event-feedback
/v1/students/{id}/wellbeing/assessment
/v1/students/{id}/wellbeing/outreach
/v1/students/{id}/matches/refresh
/v1/students/{id}/schedule-proposals
/v1/students/{id}/calendar-actions
/v1/students/{id}/replan-preview
/v1/students/{id}/actions
/v1/students/{id}/advisor/bookings
/v1/students/{id}/advisor/bookings/{bookingId}/cancel
```

---

## 9. 附录 B：QA 钩子（`data-*` 属性）

现有实现在每个关键控件上挂了 `data-*` 属性，浏览器实测脚本靠它断言。
**重设计后请保留同名属性**，否则回归验证脚本会全部失效。

主要钩子（不完全列举）：

```
data-sidebar / data-nav-link / data-persona-badge / data-portal-tag / data-synthetic-badge
data-locale-option / data-theme-select / data-logout
data-login-student-id / data-login-student / data-login-roles / data-login-role-option
data-login-institution / data-login-card / data-password-hint / data-role-badge
data-consent / data-consent-granted / data-consent-state / data-contact / data-save-contacts
data-tab-panel / data-profile-edit / data-profile-edit-save / data-profile-edit-cancel
data-tag-editor / data-new-tag / data-add-tag / data-remove-tag
data-resume-upload / data-resume-upload-button / data-resume-done
data-evidence-upload / data-evidence-type / data-evidence-uploaded
data-extras-section / data-extras-row / data-extras-input / data-extras-add / data-extras-remove
data-courses-section / data-experience-section / data-experience / data-certificates / data-cert
data-proposal / data-proposal-confirm / data-proposal-reject
data-mode-picker / data-mode / data-goal / data-goal-role / data-goal-save
data-decomposition / data-facet / data-shared-gap / data-shared-layer / data-divergence-point
data-growth-layer / data-growth-facet / data-evidence-chain / data-no-evidence
data-page-tabs / data-page-tab
data-routine-card / data-routine / data-routine-submit
data-capacity-snapshot / data-overload / data-week-grid / data-day-grid / data-block
data-block-type / data-block-has-title / data-detail-tier / data-calendar-legend
data-slot-editor / data-editor-title / data-editor-save / data-editor-delete
data-replan-ask / data-replan-yes / data-replan-scope
data-signal / data-signal-triggered / data-reminders / data-reminder-capped
data-zero-llm / data-wellbeing-disclaimer / data-assessment-card / data-assessment-result
data-outreach-request / data-outreach-sent
data-advisor-booking-panel / data-advisor / data-slot / data-slot-booked / data-book-advisor
data-schedule-proposal / data-approve / data-reject / data-blocking-conflict
data-calendar-written / data-calendar-denied / data-grant-calendar-write
data-activity-detail / data-detail-deadline / data-prep-hint
data-trajectory / data-trajectory-chart / data-plan-item / data-activity-reason
data-program-group / data-term-select / data-term-view / data-course / data-course-verdict
data-course-reason / data-needs-confirm
data-match / data-apply / data-refresh-matches
data-square-filters / data-filter / data-square-count / data-opportunity / data-expired
data-official-source / data-save / data-saved / data-add-to-plan / data-why-not
data-schedule-conflicts / data-conflict-blocking / data-add-without-replan / data-add-with-replan
data-explanation / data-memory / data-memory-locked / data-memory-correct / data-memory-forget
data-consent-scope / data-export-data / data-delete-data / data-delete-confirm / data-delete-go
data-record / data-record-category / data-record-ratings / data-category-filter / data-score-filter
data-reflection-search / data-reflection-boundary / data-reflection-save / data-reflection-saved
data-subject-filter / data-subject-option / data-subject-list / data-rating / data-fit
data-advisor-merged / data-my-meeting-reflection / data-advisor-advice / data-advice-locked
data-write-for-booking / data-my-bookings / data-my-booking / data-cancel-booking
data-advisor-policy / data-booking-sent / data-booking-taken / data-booking-blacklisted
```

---

## 10. 交付清单：还需要什么

本文只解决"每一页有什么功能"。要让重设计真正能接回系统，需要四件配套材料：

| # | 材料 | 状态 | 位置 |
|---|---|---|---|
| 1 | **设计令牌现状表** —— 色板 / 语义变量 × 2 主题 / 7 级字阶 / 圆角分布 / 材质 / 动效 / **对比度自查表** | ✅ **已产出** | `docs/CampusPath_Design_Tokens_2026-08-01.md` |
| 2 | **回归验证清单** —— 基于第 9 节 `data-*` 钩子的 155 项断言（P0 53 / P1 93 / P2 9） | ✅ **已产出** | `docs/CampusPath_Student_UI_Regression_Checklist_2026-08-01.md` |
| 3 | **当前界面截图集** —— 12 路由 × 18 面板 × 3 语言 × 2 主题 | ⬜ 待产出 | 建议 `docs/verification/current-ui-<日期>/` |
| 4 | **组件契约表** —— 第 4 节 15 个原语各自的 props、状态、尺寸约束 | ⬜ 待产出 | |

**给设计侧的最小包**：本文 + 材料 1（令牌表）。
**接入时我方需要的**：材料 2（回归清单）逐条跑绿。

> 令牌表 §8 记录了现版**两处对比度不达 WCAG AA** 的缺陷（浅色下的 `--hatch` 文字、
> 深色下的成功/错误提示色）。这两处属于现存问题，请在新设计里一并修掉，
> 不要照抄。

---

*文档结束。所有数据为 2026-08-01 在 localhost:3100（学生 STU-A，commit `b8371bd`）的实测值。*
