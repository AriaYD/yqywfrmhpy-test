# CampusPath 学生端 · UI 重设计回归验证清单

> **版本** 1.0 · **日期** 2026-08-01 · **对应代码** commit `b8371bd`
>
> **什么时候用**：新 UI 接入之后、合并之前。逐条跑，全绿才算换皮成功。
> **怎么用**：每条给了 **选择器 + 断言**，可以直接写成 `evaluate_script` 脚本。
> 手动过一遍也行，但**不接受"看起来没问题"**——必须有断言结果。
>
> **优先级**
> - **P0** 破坏即回滚。多数是 Spec §8.9 的架构红线，删掉等于产品主张失效。
> - **P1** 功能缺失。用户做不成某件事。
> - **P2** 体验退化。能用但变差。
>
> **验证前置**：`bash scripts/preflight.sh` 全绿；web 3100 与 api 8000 均在线；
> 以 `STU-A` 登录；**三语各跑一遍**（简/繁/英）；**双主题各跑一遍**（浅/深）。

---

## A. 全局框架（每次都要跑）

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| A1 | **P0** | Synthetic 徽章全站常驻 | 每个页面 `[data-synthetic-badge]` 存在 |
| A2 | **P0** | 学生端看不到校方页面 | 学生会话访问 `/publisher` `/console` `/advisor-desk` → 被重定向到 `/profile` |
| A3 | **P0** | 未登录必跳登录 | 清 localStorage 后访问任意页 → `/login` |
| A4 | **P0** | 身份徽章只读不可切换 | `[data-persona-badge]` 存在且**不是** `<select>`；页面上无学生切换器 |
| A5 | P1 | 导航 11 项 5 组 | `[data-nav-link]` 数量 = 11；分组标题 = 开始/我/方向/发现/系统 |
| A6 | P1 | 隐藏路由仍可达 | `/wellbeing` `/timeline` `/planner` 均返回内容，不是 404，且落在正确分页 |
| A7 | **P0** | 三语可切换且持久化 | 点 `[data-locale-option="en"]` → 文案变英文；刷新后仍是英文 |
| A8 | — | ~~主题可切换且持久化~~ **已撤除**（2026-08-03 用户裁定禁用深色，全站唯一浅色） | 反向断言：无 `[data-theme-select]`；系统深色偏好下 body 背景仍 `#faf9f5` |
| A9 | P1 | 跳到主内容链接可用 | Tab 第一下聚焦"跳到主内容"，回车后焦点进 `#main` |
| A10 | P1 | 窄屏导航不丢项 | 视口 <1024px 时侧栏隐藏、底部导航条出现且含全部 11 项 |
| A11 | P2 | 退出登录可用 | `[data-logout]` 点击 → 回 `/login` 且会话清空 |
| A12 | **P0** | 减弱动效时仍有反馈 | 模拟 `prefers-reduced-motion` → 过渡变 120ms，`.pressable:active` 不缩放，但状态变化仍可见 |
| A13 | P1 | 高对比模式不塌 | 模拟 `prefers-contrast: more` → 描边加深，材质退化为不透明 |
| A14 | P1 | 降低透明度时可读 | 模拟 `prefers-reduced-transparency` → 顶栏与抽屉变不透明 |
| A15 | **P0** | 对比度达 AA | 全部前景/背景组合 ≥ 4.5:1（大文字 ≥ 3:1）。**注意现版有两处不达标，见令牌表 §8，新设计必须修好** |
| A16 | P1 | 键盘可达 | 每页所有可交互元素可 Tab 到达，`:focus-visible` 焦点环可见 |
| A17 | P2 | 数字等宽 | `font-variant-numeric: tabular-nums` 仍生效，指标刷新时不左右跳 |

---

## B. `/login` 登录

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| B1 | P1 | 双门户两张卡 | `[data-login-card="student"]` 与 `[data-login-card="institution"]` 各 1 |
| B2 | P1 | 学生身份 3 个 | `[data-login-student-id] option` = `STU-A/B/C` |
| B3 | P1 | 校方 4 类入口 | `[data-login-role-option]` = `publisher` / `career_center_admin` / `wellbeing_coordinator` / `advisor`，**每个都带一行岗位说明小字** |
| B4 | P1 | 口令错误有反馈 | 填错口令提交 → `[data-password-hint]` 转错误色，**已填内容不清空** |
| B5 | P1 | 登录后落地正确 | 学生 → `/profile`；校方 → `/publisher` |
| B6 | P2 | 登录页不带导航壳 | 页面上无 `[data-sidebar]` |

---

## C. `/onboarding` 开通与授权

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| C1 | **P0** | 6 项授权全在 | `[data-consent]` = `academic` `calendar` `calendar_titles` `calendar_write` `wellbeing` `outreach` |
| C2 | **P0** | 默认态正确 | `calendar_titles` / `calendar_write` / `outreach` 三项 `[data-consent-granted="false"]`，其余 `true` |
| C3 | **P0** | 逐项独立，关一项不锁全站 | 关掉 `academic` 后，`/square` `/calendar` 仍可正常打开 |
| C4 | **P0** | 保存失败必须回滚且如实标注 | 断网后切换开关 → `[data-consent-state="failed"]` 出现，开关回到原位。**绝不允许本地假装成功** |
| C5 | P1 | 开关落库 | 切换后刷新页面 → 状态保持（不回默认值）|
| C6 | P1 | 联系人三行可填可存 | `[data-contact-row]` = tutor/class_teacher/monitor；填写后 `[data-save-contacts]` → `[data-contacts-saved]` 出现 |
| C7 | P2 | 完成按钮有回执 | `[data-onboarding-finish]` → `[data-onboarding-done]` 出现 |

---

## D. `/profile` 我的成长档案

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| D1 | P1 | 三分页齐全 | 分页 = 总览 / 证据档案 / 更新提议；切换后 `[data-tab-panel]` 相应变化 |
| D2 | P1 | **总览 12 个分区顺序正确** | h2 顺序 = 技能与兴趣标签 → 上传 Resume → 实习与工作 → 教育经历 → 出版物 → 荣誉与奖项 → 组织机构 → 语言 → 兴趣爱好 → 项目 → 志愿与助理工作 → 课程 → 课外课程与证书 |
| D3 | P1 | 6 个补充分区在 | `[data-extras-section]` = `education` `publications` `honors` `organizations` `languages` `hobbies` |
| D4 | P1 | 一个 Edit 管全部 | 点 `[data-profile-edit]` → 标签编辑器出现 **且** `[data-extras-input]` 数量 > 0（实测 29）**且** `[data-extras-add]` 出现 5 个 |
| D5 | **P0** | **课程分区只读** | 编辑态下 `[data-courses-section] input` 数量 = **0**。出处在 SIS，学生不能自由改 |
| D6 | P1 | 取消编辑不留残留 | `[data-profile-edit-cancel]` → `[data-extras-input]` 数量回 0 |
| D7 | **P0** | 核验状态不被抹平 | 「自述」条目的三值指示器为 **unknown（斜纹）**，**不是** not_met；`institution_verified` 才是 met |
| D8 | P1 | Resume 上传三态 | 上传后依次出现 解析中 → `[data-resume-done]`；失败时出现失败文案 |
| D9 | **P0** | Resume 原文不落库的说明在 | 上传卡的说明文字含"原文解析后即丢弃，不落库" |
| D10 | P1 | 提议可逐条裁定 | `pending` 提议有 `[data-proposal-confirm]` 与 `[data-proposal-reject]` 两个按钮；**没有"全部接受"** |
| D11 | P1 | 证据可上传 | `[data-evidence-type]` 5 个选项 + `[data-evidence-upload]` → `[data-evidence-uploaded]` |
| D12 | P2 | 专业显示全名 | 显示"计算机科学理学士 (BSc in Computer Science)"，不是 `BSC-COMP` |

---

## E. `/reflections` 反思与笔记

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| E1 | P1 | 两分页 | `[data-page-tab]` = 写一条反思 / 反思记录 |
| E2 | P1 | 对象筛选 5 类 | `[data-subject-filter]` = all / experience / course / opportunity / advisor |
| E3 | P1 | 只列修过或在修的课 | 对象列表里的课程都来自 `academic-state` 且 status ∈ {completed, enrolled} |
| E4 | P1 | 三维评分各 5 档 | `[data-rating="depth-1..5"]` `learned-1..5` `organization-1..5` 齐全 |
| E5 | P1 | 匹配标签 5 个 | `[data-fit]` = good_fit / too_basic_for_me / too_advanced_for_me / wrong_format_for_me / schedule_mismatch |
| E6 | **P0** | **边界声明常驻** | `[data-reflection-boundary]` 存在，文案含"只有评分与结构化标签会向下游传递" |
| E7 | P1 | 未选对象时不能写 | 未选对象 → `[data-reflection-input]` 为 disabled |
| E8 | P1 | 记录页六类筛选 | `[data-category-filter]` = all/advisor/lecture_course/internship_job/lab_research/other |
| E9 | P1 | 三维评分下限筛选 | `[data-score-filter]` × 3，各含 全部 / ≥3 / ≥4 / ≥5 |
| E10 | P1 | 搜索可用 | `[data-reflection-search]` 输入后列表条数减少 |
| E11 | **P0** | **一次会面只出一条** | 有 Advisor 预约且已写反思时：`[data-advisor-merged]` = 1 条，该 booking 的反思**不再单独成条**；卡内含 `[data-my-meeting-reflection]` |
| E12 | **P0** | **建议先写后看** | 未写反思的会面 → `[data-advice-locked]` 出现且看不到 `key_advice`；写完后 → `[data-advisor-advice]` 出现 |

> ⚠️ E11 / E12 在 2026-08-01 的 `STU-A` 数据下**无法观测**（该学生当前 0 条 Advisor 预约）。
> 验证时需先在 `/actions` 预约一个时段并让校方端确认，或换用有预约数据的学生。

---

## F. `/memory` 记忆中心

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| F1 | **P0** | **五种操作齐全** | 每条记忆有 `[data-memory-correct]` `[data-memory-lock]` `[data-memory-forget]`，页头有 `[data-memory-export]` |
| F2 | P1 | 纠正可提交 | 点纠正 → `[data-memory-correction-input]` 出现 → 提交后内容更新 |
| F3 | P1 | 锁定后按钮禁用 | 锁定后 `[data-memory-locked="true"]` 且锁定按钮 disabled |
| F4 | P1 | 删除即消失 | 删除后该 `[data-memory]` 不在列表中 |
| F5 | P1 | 导出可下载 | 点导出 → 触发 JSON 下载 |
| F6 | P2 | 溯源信息完整 | 每条显示 类型 · 来源 · 置信度 · 生效日期 · 权威等级 · 可见性 |

---

## G. `/goals` 目标工作室

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| G1 | **P0** | **五个方向都在，"探索中"不弱化** | `[data-mode]` = employment / academia / entrepreneurship / **exploration** / personal_interest，五个按钮视觉权重一致 |
| G2 | **P0** | **选"探索中"不要求填终点** | 点 `[data-mode="exploration"]` → `[data-goal-target]` 输入框**不出现**，`[data-goal-save]` 仍可点 |
| G3 | P1 | 两步顺序不可逆 | 未选方向时 `[data-goal-form]` 不存在 |
| G4 | P1 | 主/候选可选 | `[data-goal-role-option="primary"|"candidate"]` 各 1 |
| G5 | P1 | 目标卡显示信心度 | `[data-goal]` 内有进度条 + 百分比 |
| G6 | P1 | 拆解三层 | `[data-facet]` 的 kind ∈ {hard, soft, constraint}；软性条目带"取证来源" |
| G7 | **P0** | **无 Pack 时如实说明** | 探索中/个人兴趣方向 → `[data-decomp-none]` 出现，**不套用别人的模板** |
| G8 | P1 | 共同要求按三层分组 | `[data-shared-layer]` 存在，同类别合并计数显示 `N ↔ M` |
| G9 | P1 | 分叉点分两侧 | `[data-divergence-point]` 内有"仅主目标"与"仅候选目标"两栏 |

---

## H. `/gaps` 成长动态跟踪

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| H1 | P1 | 三层分组 | `[data-growth-layer]` = hard / soft / constraint |
| H2 | **P0** | **证据链挂在能力条目下** | 有证据的条目内 `[data-evidence-chain]` 存在，列出活动名 + 日期 + 核验状态 |
| H3 | **P0** | **无证据时如实说** | `[data-no-evidence]` 出现，**不留空白也不编内容** |
| H4 | P1 | 只挂选修课 | `[data-completed-electives]` 里不含本专业必修组的课程码 |
| H5 | P1 | 无主目标时引导 | 未设主目标 → 空态提示去目标工作室 |

---

## I. `/calendar` 日历与容量

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| I1 | P1 | 两分页 | `[data-page-tab]` = 日历与容量 / 身心容量 |
| I2 | **P0** | **授权层级徽章如实** | `[data-detail-tier]` = `free_busy_only` 或 `event_titles`，与实际返回数据一致 |
| I3 | **P0** | **一级授权下不编标题** | `data-block-has-title="false"` 的区块内**没有任何文字**，不得填"忙"字充数 |
| I4 | **P0** | **作息不从日历反推** | 作息卡 `[data-routine-card]` 存在，学生显式提交；说明文案在 |
| I5 | P1 | 容量五指标 | 固定负担 / 保护时段 / 可用空档 / 可支配容量 / 缓冲占比 |
| I6 | P1 | 可支配为负时警示 | 负值时该 Metric 转警示色 |
| I7 | P1 | 过载有提示 | 过载时 `[data-overload]` 出现 |
| I8 | P1 | 周网格 7 天 | `[data-day]` = 7；`[data-week-prev]` / `[data-week-next]` 可切周 |
| I9 | P1 | 图例 5 类 | `[data-calendar-legend] li` = 忙/空/保护/缓冲/弹性 |
| I10 | P1 | 点空白格可新建 | 点 `[data-day-grid]` 空白处 → `[data-slot-editor]` 出现且为 create 模式 |
| I11 | P1 | 点区块可编辑 | 点 `[data-block]` → 编辑器出现，字段预填该区块的值 |
| I12 | P1 | 编辑器字段齐 | `[data-editor-title]` `[data-editor-start]` `[data-editor-end]` `[data-editor-type]` `[data-editor-reminder]` |
| I13 | P1 | 删除仅编辑态有 | create 模式下无 `[data-editor-delete]` |
| I14 | **P0** | **改完问要不要重排，默认不重排** | 改动后 `[data-replan-ask]` 出现，两个按钮 `[data-replan-yes]` / `[data-replan-no]`；**不得自动重排** |
| I15 | P1 | 重排显示影响范围 | 选是 → `[data-replan-scope]` 显示 `受影响 / 未受影响` 计数 |
| I16 | P2 | 官方链接可推导 | 课程/活动块的编辑器里 `[data-editor-official]` 存在 |

---

## J. `/wellbeing` 身心容量

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| J1 | **P0** | **零 LLM 徽章常驻** | `[data-zero-llm]` 存在 |
| J2 | **P0** | **免责声明常驻** | `[data-wellbeing-disclaimer]` 存在，且**不依赖任何异步结果**才显示 |
| J3 | **P0** | **不得引入 AI 生成文案** | 页面上无任何调用模型的模块；所有文案来自 i18n 或后端固定模板 |
| J4 | P1 | 严重度三档 | `[data-signal]` 的严重度 ∈ {info, attention, blocking}，`info` 不呈现为告警 |
| J5 | **P0** | **数据覆盖率单独可见** | 每条信号有覆盖率进度条 + `有数据天数/窗口天数`。覆盖 2/7 的结论不能看起来和 7/7 一样有分量 |
| J6 | **P0** | **提醒上限 2 次并明说** | 已发 2 次时 `[data-reminder-capped]` 出现 |
| J7 | P1 | 自评两个量表 | ISI 7 题 + PSS-10 10 题，每题 5 档（0–4）|
| J8 | P1 | 自评有分流结论 | 提交后 `[data-assessment-result]` + `[data-routing-copy]` 出现 |
| J9 | **P0** | **外联失败不伪装成功** | 无同意时点 `[data-outreach-request]` → `[data-outreach-error]` 出现，**不显示"已发送"** |

---

## K. `/actions` `/timeline` `/planner` 三分页

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| K1 | P1 | 三分页 + 三深链接 | `[data-page-tab]` = actions/activities/electives；三个 URL 各自落在对应分页 |
| K2 | **P0** | **没有"一键全部批准"** | 页面上不存在批量批准控件；`[data-approve]` 只能逐条点 |
| K3 | **P0** | **阻断冲突时禁用批准** | 有 `[data-blocking-conflict]` 时对应 `[data-approve]` 为 disabled |
| K4 | **P0** | **写日历失败如实标注** | 缺 `calendar_write` 时 → `[data-calendar-denied]` 出现，**不显示"已写入"** |
| K5 | **P0** | **就地授权入口** | 上述情况下 `[data-grant-calendar-write]` 出现；授权后自动重试并转 `[data-calendar-written]` |
| K6 | P1 | 活动详情完整 | `[data-activity-detail]` 含 截止 / 时间跨度 / 投入 / 前置要求 / `[data-prep-hint]` 备考提前量 |
| K7 | P1 | Advisor 面板置顶 | `[data-advisor-booking-panel]` 是本分页第一张卡 |
| K8 | **P0** | **违约规则明示** | `[data-advisor-policy]` 存在，含"爽约 3 次暂停资格" |
| K9 | P1 | 已占时段不可选 | `[data-slot-booked="true"]` 的按钮 disabled 且有删除线 |
| K10 | P1 | 预约四种结果 | 分别可触发 `[data-booking-sent]` `[data-booking-taken]` `[data-booking-blacklisted]` 与通用失败 |
| K11 | P1 | 预约可取消 | `[data-cancel-booking]` 存在；不足 1 天时 `[data-cancel-denied]` 出现并说明后果 |
| K12 | **P0** | **课程不进活动规划页** | activities 分页里无 `kind=course` 的条目；有课程被隐藏时 `[data-courses-elsewhere]` 提示 |
| K13 | **P0** | **推荐理由必须标注来源** | `[data-activity-reason]` 存在；规则生成的带"（规则生成）"标注，不冒充模型判断 |
| K14 | P1 | 成长曲线不平滑 | `[data-trajectory-chart]` 柱高与 `verified_growth_actions` 成正比，无插值 |
| K15 | P1 | 四档跨度 | 近两周 / 一个月 / 本学期 / 一年 |
| K16 | P1 | 专业地图只显示本人专业 | `[data-program-own]` 存在，页面上**无专业选择器** |
| K17 | P1 | 专业未入库时如实说 | `[data-program-missing]` 出现，不显示别的专业冒充 |
| K18 | P1 | 学期切换 8 档 | `[data-term-select]` 含 大一上…大四下 + 总览 |
| K19 | **P0** | **"需确认"标记保留** | AI 拿不准的课带 `[data-needs-confirm]`；页头 `[data-confirm-count]` 计数 |
| K20 | P1 | 每门课有理由 | 每条 `[data-course-reason]` 非空 |
| K21 | P1 | 必修不出现在推荐 | 推荐列表里无本专业必修组课程码 |
| K22 | P1 | 计划项带凭据 | `[data-plan-item]` / `[data-action-item]` 均有凭据票根 |

---

## L. `/for-you` 为你推荐

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| L1 | **P0** | **503 说"依赖不可用"而不是"没有推荐"** | 停掉 Vertex 凭据 → 页面显示依赖不可用，**且 `/square` 仍完整可用** |
| L2 | **P0** | **四态资格映射正确** | `eligible_now`→met；`future_eligible`→unknown；**`needs_confirmation`→unknown**；`ineligible_current_cycle`→not_met。**待确认绝不能映到 not_met** |
| L3 | **P0** | **每张卡带凭据** | 每个 `[data-match]` 内有凭据票根，`validation_id` 非空 |
| L4 | P1 | 每张卡有理由 | "为什么是这个"列表非空 |
| L5 | P1 | 契合度可见 | 进度条 + 百分比 |
| L6 | P1 | 报名按钮仅在可报时出现 | `[data-apply]` 只出现在 `eligible_now` 的卡上 |
| L7 | **P0** | **报名不越权写日历** | 点报名 → 生成 pending 排程提议，**不直接写日历**；批准仍在行动中心走三步 |
| L8 | P1 | 刷新限次如实告知 | 超 3 次 → `[data-refresh-matches]` 后显示限次提示，**且仍展示缓存结果** |
| L9 | P2 | 卡上是标题不是 id | 标题从目录取，`opportunity_id` 只作次要信息 |

---

## M. `/square` 资讯广场

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| M1 | **P0** | **不排序、可看全部** | 无排序控件；`[data-square-count]` 与目录总数一致（实测 177）|
| M2 | P1 | 7 个筛选器 | `[data-filter]` = type / tag / official / organizer / deadline / expired / saved |
| M3 | P1 | 主办方 8 大类 | organizer 下拉含 校友/校园官方/Career Center/企业/合作企业/学院与学系/学生社团 等 |
| M4 | P1 | 类型 8 类 | club_activity / competition / event / internship / job / mentorship / research_position / workshop |
| M5 | **P0** | **已截止一眼可辨** | `[data-expired]` 标签存在且视觉上明显区别于在开放的条目 |
| M6 | P1 | 官方来源可辨 | `[data-official-source]` 标签存在 |
| M7 | P1 | 收藏可取消 | `[data-save]` 点击后 `[data-saved]` 在 true/false 间切换；**乐观更新，点击立刻有反应** |
| M8 | P1 | 清空筛选可用 | `[data-clear-filters]` 后全部筛选归零，计数回到全量 |
| M9 | **P0** | **"为什么没推荐"来自 Rules** | `[data-why-not]` → 抽屉内 `[data-explanation]` 含三值状态 + 缺什么 + **凭据票根** |
| M10 | **P0** | **加入日程三步分开** | `[data-add-to-plan]` → 预览时段 → `[data-schedule-conflicts]` → `[data-add-without-replan]` / `[data-add-with-replan]` |
| M11 | **P0** | **保护时段冲突阻断添加** | 有 `[data-conflict-blocking="true"]` 时两个添加按钮均 disabled，且 `[data-blocked-by-protected]` 出现 |
| M12 | P1 | 长期项目有说明 | >8 小时的机会 → `[data-long-running]` 提示 |
| M13 | P1 | 假定时段有标注 | 来源无开始时间时标"（系统假定的时段）"，不假装来源说了 |

---

## N. `/settings` 设置与隐私

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| N1 | P1 | 授权回执列全 | `[data-consent-scope]` 覆盖 profile 返回的全部 scope，各带 `receipt_id` |
| N2 | P1 | 语言/主题可切 | 两个 Segmented 均可用且立即生效 |
| N3 | P1 | 导出可下载 | `[data-export-data]` → JSON 下载 |
| N4 | **P0** | **确认框只给删除** | `[data-delete-data]` → `[data-delete-confirm]` 出现（`role="alertdialog"`）。**全站其他任何操作都不得有确认框** |
| N5 | P1 | 删除后登出 | `[data-delete-go]` → 服务端清除 → 回 `/login` |
| N6 | P1 | 数据声明在 | 关于卡含 Synthetic 完整徽章 |

---

## O. 跨页数据一致性（换皮后最容易掉的）

| # | 优先级 | 检查项 | 断言 |
|---|---|---|---|
| O1 | **P0** | 三值语汇全站一致 | `/profile` `/for-you` `/square` `/planner` 的 unknown 用**同一种**视觉语汇 |
| O2 | **P0** | 凭据票根全站一致 | 所有 Rules 结论处的票根样式相同，`validation_id` 均可见 |
| O3 | P1 | 空/错/无权/限流四态全覆盖 | 按功能文档 §5 状态矩阵逐格验证 |
| O4 | P1 | 中英繁三语不溢出 | 每页三语各截图，按钮/标签/指标格无截断、无换行破版 |
| O5 | P1 | 深浅双主题均可读 | 每页双主题各截图，**特别检查成功/错误提示文字**（现版深色下不达标）|
| O6 | P2 | 深链接不断 | 全部 15 个 URL 直接访问均可达 |

---

## P. 执行记录表（跑的时候填这张）

| 批次 | 日期 | 语言 | 主题 | P0 通过/总数 | P1 通过/总数 | P2 通过/总数 | 未通过项 | 执行人 |
|---|---|---|---|---|---|---|---|---|
| | | 简 | 浅 | /53 | /93 | /9 | | |
| | | 简 | 深 | /53 | /93 | /9 | | |
| | | 繁 | 浅 | /53 | /93 | /9 | | |
| | | 英 | 浅 | /53 | /93 | /9 | | |
| | | 英 | 深 | /53 | /93 | /9 | | |

> **合并门槛**：P0 必须 100% 通过；P1 未通过项须逐条给出"已改 / 不改（含理由）/ 记待办"三选一；
> P2 可记待办。

---

## Q. 附录：断言脚本骨架

```js
// chrome-devtools evaluate_script 里跑
async () => {
  const q  = (s) => document.querySelector(s);
  const qa = (s) => [...document.querySelectorAll(s)];
  const results = [];
  const check = (id, pass, detail) => results.push({ id, pass, detail });

  // A1
  check('A1', !!q('[data-synthetic-badge]'), 'Synthetic 徽章');
  // A5
  check('A5', qa('[data-nav-link]').length === 11, `nav=${qa('[data-nav-link]').length}`);
  // D5（在 /profile 编辑态下跑）
  check('D5', qa('[data-courses-section] input').length === 0, '课程分区必须只读');
  // I3
  check('I3', qa('[data-block-has-title="false"]').every(b => !b.textContent.trim()),
        '无标题区块不得有文字');
  // L2
  const triOf = (el) => el.querySelector('[data-tri]')?.getAttribute('data-tri');
  check('L2', true, '需按各卡 eligibility.state 逐一比对');

  return { pass: results.filter(r=>r.pass).length, total: results.length, results };
}
```

---

*清单基于 2026-08-01 的 `main` 分支（commit `b8371bd`）实测行为编写。
共 **155 项**：P0 53 · P1 93 · P2 9。*
