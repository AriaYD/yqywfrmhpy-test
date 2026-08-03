# CampusPath 实现计划 V2

- 版本：v2.1
- 日期：2026-07-28
- 依据（唯一基线）：`CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md`
- 背景材料：`CampusPath_Architecture_Review_V4.1.md`（V4.1 各项修改的论证过程）
- V4 历史基线**已从仓库删除**（2026-07-29，用户决定）：留着它只会制造"引错基线"的机会。要追溯 V4 的原文，走 git 历史
- 范围：**只实现 Spec V4.1 §18.1 的 P0 清单**
- 交付形态：**Web App**（不做原生移动端，避免受限于学生使用何种设备）
- 执行模式：计划批准 + §5 阻塞项到位后，我在 Goal 模式下自主执行

---

## 1. 最终交付标准（Definition of Done）

7 个交付物全部满足验收条件即为完成。每条验收可由脚本或人工在 30 分钟内复核。

### D1｜学生 Web App（可访问 URL）

| 验收项 | 标准 | 判定方式 |
|---|---|---|
| 页面完整性 | Onboarding & Consent / My Growth Profile（含 Evidence Portfolio 页签）/ Goal Studio / Course & Degree Planner / Calendar & Capacity / Wellbeing Capacity / Dynamic Gap Map / For You / 资讯广场 / Pathway Timeline / Action Center / Reflection & Notes / Memory Center / Settings & Privacy。**2026-07-31 第二轮导航整合**：行动中心并入 Pathway Timeline 分页、Wellbeing Capacity 并入 Calendar 分页（功能零删减，/actions /wellbeing 深链接保留）；另有 /login（双门户）与校方 /advisor-desk | 逐页点检（分页也点） |
| Persona | 3 个本科求职 Demo Persona 可切换，数据全部来自 Seed，前端零硬编码 | 改 Seed 后前端跟随变化 |
| 时间视图 | ≥12–18 个月长期视图 + 学期视图 + 未来 2 周行动视图，三者数据同源 | 视图点检 |
| 资讯广场 | 展示全部审核通过资源；≥4 类标签筛选；可复现"AI 未推荐但学生主动发现"+「为什么没推荐？」解释 | 场景演示 |
| 多目标（G3） | Goal Studio 支持 1 主目标 + 1 候选目标；A3 对两者都出 Requirement Graph；显示共享缺口与分叉点 | 场景演示 |
| 成长曲线（G4） | Pathway Timeline 显示 GrowthTrajectory（关闭缺口数 / 新增 Evidence / 目标信心变化） | 视图点检 |
| 数据标记 | 全站默认 `Synthetic / Demo Data` 标记；已核实为真实公开来源的条目（HKUST 课程目录、官方活动日历）改用「官方」标记，并在数据免责声明里列出**全部**真实来源（2026-07-31 更新，`app.syntheticFull` 文案已补 Engage 活动） | 全页扫描 + 免责声明与真实来源清单逐一对照 |
| U 系列功能细节（2026-07-31 补录） | Reflection 页 subject 选择器覆盖经历/课程/机会三类且未选时输入框禁用（U3）；Goal Studio 五方向先于终点输入、探索方向可空终点保存（U4）；加入机会走 preview→conflicts→decide 三段式、保护时段冲突阻塞、收藏写入偏好记忆、`replan-preview` 不写数据（U8） | 浏览器实测（已完成，见 PROGRESS 07-30 各行） |
| 第三轮 A–R 功能（2026-07-31 补录） | 登录身份隔离（切换器移除）；日历写入同意自助授权（回执 B13）；课外活动规划（改名并入选课页，只含课外条目，四档跨度，活动卡官方链接+推荐理由）；行动中心独立导航 + Advisor 时段库存/取消/爽约规则（预约置顶）；共享要求/分叉点与成长动态跟踪三层归类+证据链；活动闭环（报名→行动中心→反思→证据）；周日历即编辑器+作息保护时段+容量口径钉定；档案 LinkedIn 式分区+按钮式上传；选课页只显本专业+课程详情三分区+规则生成相关性注；3 份合成 demo 学生档案（不采真人）。契约 1.2.0→1.6.0，api 测试 120 | 每项浏览器双语实测 + 回归测试（见 PROGRESS 07-31 第三轮各行；截图 docs/verification/round3/） |
| A/B/C 三提案批（2026-08-02 补录，`feat/pack-sources-intl` 分支，契约 1.22.0→1.26.0） | 源注册表 92 源（84 真实/8 mock 如实标注）+ 共享抓取器 + sha256 变更检测 + console 真刷新钮 + 官方域名白名单直发广场（审核队列只留第三方投稿）+ 主办方十大类 + 政策更新提醒卡；国际生 Pack vendored（零 LLM，待政策复核如实标注）+ Rules 签发 validation_id + 档案页唯一勾选入口 + 拆解「国际生准备」列 + `.intl-note` 注记 + 证件到期提醒；求职拆解市场证据化（两岗位 JD 语料 100% 行映射 + 36 条权威榜单 + core 权重 + 现场 AI 拆解后台任务与进度条）+「大几」学期选择器 + planner 已选课程折叠面板（与日历课表块同源） | 每项真浏览器点击流（政策卡真实抓入境处、现场拆解切页续接、勾选→拆解四列）+ api 195/agents 73/contracts 全绿 + 三门禁（86 组合/对齐/结构）+ 92 源实跑巡检（80Δ/3×/9 skip）；见 PROGRESS 08-02 行 |
| clay 分支功能（2026-08-01 补录，`ui/clay-restyle` 未并 main） | 全站 Claymorphism × Claude 暖色重构（令牌 v2 + 对比度/跨页对齐/结构三门禁，各带 H5 自检）；Advisor 一小时时段（工作日 9 档/天）+ 注册 CRUD 分页；校方端审核队列独立页、机会源全名+刷新、广场总览（搜索/编辑/下架=批准后生命周期管理）；学生报名与加入日历状态服务端持久化+广场标记/筛选/搜索；AI 评语高亮；档案空分区自添；契约 1.19.0→1.21.0 | 每批浏览器真点击 + 三门禁 + api/contracts 套件（见 PROGRESS 08-01 各行；截图 docs/verification/clay-restyle/） |
| 第二轮 A–O 功能（2026-07-31 补录） | Resume 上传→pending 提议（冲突带旧值）；反思评分三维+FitTag、历史搜索；Advisor 双端（预约/确认/建议，隔离 403）；目标拆解三层 Pack（求职/创业/读研）；专业课程地图（5 专业真实要求）；日历时段可改/删+学生决定重排；推荐每日缓存+限次刷新+报名按钮；收藏可取消；主办方八大类；行动卡活动详情+备考提前量 | 浏览器双语实测（已完成，见 PROGRESS 07-31 第二轮各行；截图 docs/verification/round2/） |

### D2｜6 Agent / 2 Runtime + 治理证据

| 验收项 | 标准 |
|---|---|
| Agent 主链 | A0–A5 均为 ADK Agent，跑通 Spec §19 的 17 步 Demo 故事 |
| Workflow Agents | A5 用 `ParallelAgent` 出 Plan A/B/C（S1）；A5 用 `LoopAgent(max_iter=3)` 做约束修复（S2）；A4 用 `ParallelAgent` 多源并行抽取（S3）；A0 固定流水线用 `SequentialAgent`。**四种用法各有一份 trace 证据** |
| Runtime 分离 | Student Path Runtime（A0/A1/A2/A3/A5）与 Opportunity Ops Runtime（A4）独立部署，各有 trace |
| 治理 | Agent Registry 登记记录 + Gateway/IAM 的"哪个 Agent 可调哪个 MCP"配置证据；不可得则走降级 R1 |
| 记忆 | 跨会话召回可演示；Memory Center 可查看/纠正/锁定/删除/导出 |
| **安全契约测试** | A4 无学生数据工具（权限断言测试通过）；A1 无聚合域写权限；A5 输出的每个 PlanItem 携带 Rules 的 `validation_id`，缺失即被 API 拒绝 |

### D3｜确定性服务平面（9 个模块）

| 服务 | 验收标准 |
|---|---|
| Student State & Memory | Canonical Profile + append-only Event Store + Evidence/Note 独立留存 + ProfileChangeEvent；学生拒绝的更新不写入且保留事件 |
| Rules & Constraint Engine | **零 LLM 调用**（代码级断言）；四态资格、先修、学分、日期、容量、保护区块、Wellbeing 五信号全部有单测 |
| Capacity & Calendar Service | free/busy → 五类 AvailabilityBlock → CapacitySnapshot，纯算术，单测覆盖 |
| Wellbeing Reminder Composer | 6 槽位模板；两次提醒状态机；outreach 邮件字段白名单；**零 LLM** |
| Action & Consent | 所有写入前有预览 + 同意记录；幂等；审计日志完整 |
| Event Monitor & Replan | 事件注入 → AffectedScope 计算 → 触发局部重规划（不推翻无关路径） |
| Publishing / Review / Audit | 状态机 `Draft→Submitted→Auto-checked→In Review→Changes Requested/Rejected/Approved→Published→Updated/Expired/Withdrawn/Archived` 完整；越权被拦截且记录 |
| Aggregation Service | 输入只接受结构化 `EventQualityFeedback`（类型级拒绝自由文本）；样本阈值、届次/系列分层、时间衰减 |
| Connector & Catalog | EducationDataAdapter / CalendarProvider / OpportunityProvider 统一接口；Source Health 八项指标可查 |

### D4｜Synthetic Campus Sandbox

| 验收项 | 标准 |
|---|---|
| Moodle | GCP 上运行、Web Services 开启、最小权限服务账户、Seed 注入；经自建 Moodle MCP 被 A2 真实读取（非 Mock 顶替） |
| Mock 服务 | SIS / Degree Audit / Course Catalog / Timetable / Opportunity Sources / Publisher 的 REST 服务，Schema 与未来真实适配器一致 |
| 数据规模 | Spec §11.2 各表下限；3 个 Persona 深度完整 |
| 失败样本 | Spec §11.3 的 16 类中覆盖 ≥12 类，每类带 Gold Label |
| 可复现 | `make seed-reset` 一条命令恢复；Data Dictionary + JSON Schema + Seed 版本号齐全 |

### D5｜Publisher Portal + Career Center Console

- 官方直发 1 条 → 进广场；
- Admin 授权 1 个社团 Publisher（限组织/分类/期限）→ 投稿 → 自动校验 → 人工审核批准 → 进广场；**退回修改**与**驳回**分支各演示 1 次；越权投稿被拦截 1 次；
- 校方端：Opportunity Source Health、Education Connector 总体健康、Publisher Authorization/Review 队列、Curated 标记、匿名质量趋势；
- **隔离验证**：以 Career Center 角色登录，确认看不到任何 wellbeing 事件、Reflection 原文、个体日历。

### D6｜Evaluation Harness 与验收标准

这一节是**整个计划的验收合同**。所有阈值由 `make eval` 一条命令自动产出，结论是机器判定的 PASS / FAIL。

#### D6.1 三类判定

| 类别 | 含义 | 不达标的后果 |
|---|---|---|
| 🔴 **BLOCKER** | 安全、隐私、金钱、正确性红线 | **必须为 0 / 100%**，任一不达标即不可交付 |
| 🟠 **TARGET** | 产品质量主张的量化证据 | 未达标须写明实测值、原因与缓解措施，不得隐藏 |
| 🔵 **BASELINE** | 对照组，证明"比现状好" | 只需产出数字，无固定阈值 |

#### D6.2 🔴 BLOCKER —— 全部必须为 0（或 100%）

| # | 指标 | 判定 | 测法 |
|---|---|---|---|
| B1 | Capacity Violation | **= 0** | 遍历所有 PathwayVersion 比对 CapacitySnapshot；未经显式警告的超载计划即失败 |
| B2 | Protected Block Violation | **= 0** | 排程结果与学生 Protected Block 求交集，非空即失败 |
| B3 | Unconfirmed Profile Write | **= 0** | 每条 Profile 变更须回溯到 `status=confirmed` 的 Proposal |
| B4 | Private Reflection Exposure | **= 0** | 向 Aggregation 注入自由文本须被类型层拒绝；校方端响应体无 Reflection 原文 |
| B5 | Calendar Detail Over-collection | **= 0（超出授权层级的采集）** | 两级授权（2026-07-30 用户拍板）：一级（free_busy_only）学生全库扫描无标题、参与人、备注；二级（event_titles）允许有标题但类型层校验 `detail_level` 匹配；"无授权带标题"在契约构造时即被拒绝（`AvailabilityBlock._title_requires_grant`），API 闸门用注入泄漏样例验证 |
| B6 | Wellbeing False Escalation | **= 0** | 注入"仅日历繁忙、无设定窗口、无自报数据"场景，不得产生 outreach |
| B7 | Unauthorized Publication | **= 0** | 越权投稿测试集全部被拦截 |
| B8 | Unbacked Plan Item | **= 0** | 每个 PlanItem 与资格结论携带有效 `validation_id` |
| B9 | Metric Re-identification | **= 0** | 低于样本阈值须显示 `Insufficient evidence`；后端无个体下钻 |
| B10 | MetricTuple Field Leakage | **= 0** | 出域元组不含 student_id／Profile／目标原文／日历／wellbeing 字段 |
| B11 | LLM-free Path Integrity | **= 0 违规** | CI 检查 Rules、Capacity & Calendar、Wellbeing Composer 依赖树无模型 SDK |
| B12 | AI Studio 路径 | **= 0 引用** | 代码扫描无 `google.generativeai` 或该端点调用（见 §5.1.1） |
| B13 | Outreach Consent Integrity | **= 100%** | 每封 outreach 可追溯到有效同意，字段在白名单内 |

#### D6.3 🟠 TARGET —— 质量阈值

| # | 指标 | 阈值 | 测法与样本量 |
|---|---|---|---|
| T1 | Eligibility State Accuracy | **≥ 90%** | Gold Set ≥ 60 条 × 3 Persona，四态人工标注，宏平均 |
| T2 | Hard Eligibility False Positive | **< 5%** | 实际不合格却判为 `Eligible now` 的比例。**比 T1 更要紧** |
| T3 | Course Plan Constraint Accuracy | **≥ 95%** | 满足毕业／先修／开课／冲突四项硬约束的比例，低于 95% 说明 Rules 有 bug |
| T4 | Plan Constraint Satisfaction | **≥ 98%** | 满足先修、截止、冲突、容量、保护区块 |
| T5 | Replan Correctness | **≥ 85%** | 注入 ≥ 10 类变化事件，判定"只改受影响路径 + 合理替代" |
| T6 | Low-Value Repeat Exposure | **< 10%** | 已反馈低价值后同类项仍进 Top-N 的比例 |
| T7 | Stale/Wrong Opportunity Rate | **< 5%** | Catalog 中过期、断链或与来源矛盾的比例 |
| T8 | Unsupported Key Claim Rate | **< 2%** | 抽样 ≥ 50 条解释，关键事实无法回溯到来源的比例 |
| T9 | Interaction Latency P50 | **< 3s** | 常见交互，≥ 30 次采样 |
| T10 | Replan Latency P95 | **< 12s** | 整体重规划，≥ 20 次采样 |
| T11 | Profile Proposal Precision | **≥ 80%** | 被 Persona 脚本确认或轻改后接受的比例 |
| T12 | Relevant Memory Recall@5 | **≥ 70%** | 是否召回与当前任务相关的历史决定／经历 |

#### D6.4 🔵 BASELINE —— 对照数字（必须产出）

Time to First Qualified & Useful Opportunity（vs 人工搜索 vs 普通 RAG）、Eligible Opportunity Discovery Rate、Discovered-to-Action Rate、Gap Coverage by Available Resources、Non-recommended Discovery Rate。

#### D6.5 Gold Set 与标注协议

| 数据集 | 下限 | 标注内容 |
|---|---:|---|
| 机会四态资格 | 60 条 | 四态 + 判定依据 |
| 课程约束 | 40 门 | 毕业要求归属、先修状态、开课学期、课表冲突 |
| 重规划情景 | 12 组 | 变化事件 → 预期受影响／不受影响范围 |
| 失败样本 | 12 类 | Spec §11.3 的 16 类中覆盖 ≥ 12 类 |
| 记忆回归 | 20 条 | 已拒绝／已完成事项，验证不重复推荐 |

规则：① 先规则生成初版标签再人工复核（工作量降至约三分之一，见 R8）；② 每条标签写明**判定依据**；③ 冲突时**以来源原文为准**，不以模型输出为准；④ 冻结后改动须走版本号 + 变更记录，防止"调标签凑指标"。

#### D6.6 交付物

`make eval` 产出 `eval/results/report.md`、`eval/results/metrics.json`、`eval/results/failures/`（每例含输入／期望／实际／复现命令）。**退出码**：任何 BLOCKER 失败 → 非零；仅 TARGET 未达标 → 退出 0 但报告标红。

#### D6.7 交付条件

13 项 BLOCKER 全通过（无条件）；TARGET 至少 10/12 达标且未达标项有说明；BASELINE 全部产出；固定 Seed 可复现两次数字一致。

### D7｜3 分钟端到端 Demo

- 按 Spec §19 的 17 步编排的剧本（操作 / 预期画面 / 口播词 / 计时）；
- Wellbeing 切片完整：睡眠窗口 → Rules 检测挤压 → 阻止发布 → A5 LoopAgent 出 Low-load → 两次提醒 → 学生主动请求 → 最小化邮件到测试 Counseling 邮箱 → Career Center 端确认不可见；
- **延迟达标**：常见交互 P50 < 3s，最重的重规划 P95 < 12s；
- 连续两次彩排一致通过 + 录屏备份。

---

## 2. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| Agent 框架 | Google ADK（Python） | 命题硬要求；Workflow Agents / Memory / Eval 原生 |
| Agent 部署 | Vertex AI Agent Engine（Agent Runtime）；不可用降级 R1 | 评分点 |
| 模型 | Gemini 稳定版（主力）+ 低成本档（A4 批量抽取），型号做成配置项 | Spec §12.4 明确不绑定型号 |
| 后端 | Python FastAPI → Cloud Run | 与 ADK 同语言，Pydantic Schema 在 Agent 与服务间共享 |
| 数据库 | Firestore | 黑客松规模下文档模型足够；Event Store 用 append-only collection；省去 Cloud SQL 运维 |
| 附件 | Cloud Storage，按 student_id 前缀隔离 | Private Vault |
| Moodle | GCE e2-medium + `moodlehq/moodle-docker`，内置 MariaDB | Spec §11.4 |
| Mock 服务 | FastAPI 单容器多路由 → Cloud Run | 省成本，Schema 与真实适配器一致 |
| MCP | 自建 Python Moodle MCP + Education MCP | Spec §11.4 |
| 前端 | Next.js + Tailwind（bun 管理）→ Cloud Run；单一应用、**两个各自登录的门户**（学生端 / 校方端，`/login` 双入口 + 会话模型 + 三规则门户守卫；2026-07-31 用户裁定推翻旧的"三端同 app 按角色路由"） | 界面互不混排；服务端 RBAC 仍是真正的权限边界 |
| **UI 设计流程** | **必须同时使用两者，缺一不可**：<br>① `frontend-design` skill（Claude 官方插件 `frontend-design@claude-plugins-official`）—— 视觉方向、排版层级、避免模板化默认<br>② `apple-design` skill（`.agents/skills/apple-design`）—— 交互物理：临界阻尼弹簧（damping 1.0 / response 0.3–0.4）、按下即反馈、可中断动画、速度接管、材质与深度、`prefers-reduced-motion` | 用户指定。前者定视觉，后者定手感 |
| 动效库 | Motion（`spring`，bounce 0 为默认；仅动量交互给 bounce 0.2） | 与 apple-design 的弹簧参数直接对应 |
| **UI 语言** | **简/繁/英三语**：全部用户可见文案走 i18n 资源文件（`zh-Hans` / `en`），界面可切换且选择持久化，**不硬编码任何语言的文案**。覆盖页面导航、按钮状态、表单校验与错误提示、四态资格标签、Wellbeing 提醒模板（各语言一份，均须含"不代表任何医学诊断"）**与 Rules Engine 的资格/先修判定理由（均以 message-id 模板目录实现，见 `contracts/campuspath_contracts/messages.py`，两侧占位符一致由测试断言）**、空状态与 `Insufficient evidence` | 用户指定。验收时两种语言各走一遍浏览器实测 |
| 邮件 | Gmail API 测试账号，只发预配置测试邮箱 | Spec §16.8.4 |
| 仓库 | monorepo：`apps/web` `services/api` `services/mock-campus` `agents/` `mcp/` `seed/` `eval/` `infra/` `contracts/` | — |

---

## 3. 工作包（WP0–WP11）

> 复杂度按我全职执行估算：S ≤1天，M 2–3天，L 4天+

### WP0｜仓库与基础设施（S）
- 产出：monorepo 骨架；`infra/` 的 gcloud 脚本（启用 API、Firestore、GCS、Cloud Run、GCE）；`.env` 模板；Makefile。
- 验收：dry-run 后一条命令完成资源创建。
- 依赖：§5 阻塞项 1。

### WP1｜契约先行：Schema 与 API 合同（S，**最高优先级**）
- 产出：`contracts/` 下全部 Pydantic/JSON Schema（对齐 Spec §14 + V4.1 新增的 `AnnotatedCourseCandidate`、`WellbeingCapacitySignal`、`ConstraintValidation`）；Agent↔服务的 OpenAPI 契约；`validation_id` 绑定规则。
- 验收：契约测试跑通（空实现即可）；前后端、Agent、Mock 服务全部从同一份 Schema 生成类型。
- 依赖：无。**这是所有后续工作包并行开展的前提，必须第一个做完。**

### WP2｜Synthetic Campus 数据设计（L，无云依赖，可立即开始）
- 产出：Data Dictionary；确定性 Seed 生成器；3 个深度 Persona + 其余精简数据；Gold Set（四态资格、课程约束、重规划预期）；≥12 类失败样本。
- 验收：跨表一致性校验脚本通过；`make seed-reset` 可复现。
- **隐藏成本预警**：Gold Label 标注是本项目最大的隐性工作量（50–100 条实习的四态资格标注 + 30–50 门课程的约束标注）。缓解方式见 R8：先用规则生成初版标签，再做人工复核，可把工作量降到约三分之一。
  **2026-07-31 状态**：规则生成的初版标签已就绪并驱动 `make eval`（课程目录实际抓了 1,534 门、先修解析器对 701 条真实表达式验收 94.6%/5.3%/0 假阴性，`53d1ca9`）；**R8 的人工复核仍未做**——T1/T2/T3 的满分因此仍属自评，见 D6.5。

### WP3｜Moodle Sandbox + Moodle MCP（M）
- 产出：GCE Moodle 实例；Web Services 配置；Demo 服务账户；Seed 注入脚本；Moodle MCP（只读工具：courses / enrolments / grades / completion）。
- 验收：MCP 工具返回 Seed 数据；凭据不入 git；夜间停机脚本。
- 依赖：WP0、WP1、WP2。

### WP4｜Mock Campus REST 服务（M）
- 产出：SIS / Degree Audit / Course Catalog / Timetable / Opportunity Sources / Calendar Fixtures 服务 → Cloud Run；Education MCP 封装；Source Health 端点。
- 验收：OpenAPI 文档；与 WP1 契约一致。
- 依赖：WP0、WP1、WP2。

### WP5｜确定性服务平面（L）
- 产出：D3 的 9 个模块 + RBAC 中间件（Student / Publisher / Reviewer / Curator / Connector Admin / Wellbeing Coordinator / Security Admin）+ 审计日志。
- **重点**：Rules Engine 与 Capacity Service 与 Wellbeing Composer 三者必须有"零 LLM"的代码级断言（import 层禁止引入模型 SDK）。
- 验收：D3 全部；Wellbeing 五信号阈值单测覆盖 §16.8.2 全部边界条件。
- 依赖：WP1；可与 WP3/WP4 并行。

### WP6｜A0–A5 Agents（L）
- 产出：6 个 ADK Agent；A1 的 Reflection/Memory Curation Skill；A2 的课程标注 Skill；S1–S3 三处 Workflow Agent；A0 确定性路由表；两 Runtime 部署；Memory Bank 接入；Registry/Gateway 配置证据。
- 安全契约：A4 工具白名单 + 外部内容 user-role 传入 + Schema 闸门；A1 输出类型边界；A5 validation_id 绑定。
- 验收：CLI 级跑通 17 步故事（无前端）；每个 Agent 输出契约有 Schema 校验测试；安全契约测试全绿。
- 依赖：WP1、WP3、WP4、WP5。

### WP7｜学生 Web App（L）
- 产出：D1 全部页面 + GrowthTrajectory 视图 + 多目标对比视图 + 简/繁/英三语 i18n 资源。
- **设计流程**：先用 `frontend-design` skill 定视觉方向，再用 `apple-design` skill 落交互物理。两个 skill 都要过。
- 验收：D1 全表通过 + **两种语言各走一遍浏览器实测**（§10.3）+ `/codex:review` 已跑且结论已处置。
- 依赖：WP1（可提前做骨架）、WP5、WP6。

### WP8｜Publisher Portal + Career Center Console（M）
- 产出：D5 全部功能；角色隔离中间件；隔离验证测试；双语 i18n。
- 验收：D5 场景可演示 + **浏览器实测角色隔离**（以 Career Center 身份登录，确认看不到 wellbeing 事件、Reflection 原文、个体日历）。
- 依赖：WP1、WP5。

### WP9｜Calendar & Wellbeing 垂直切片（M）
- 产出：CalendarProvider 双模式（A：真实 Google OAuth 测试账号；B：同接口 Fixture 并标记）；CapacitySnapshot；两次提醒状态机；consent-based outreach 邮件。
- 验收：D7 的 Wellbeing 全流程；无同意不发送、字段最小化测试通过。
- 依赖：WP5、WP6。

### WP10｜Evaluation Harness（M）
- 产出：D6 的评测脚本、KPI 报告生成、Guardrail 零违规测试、延迟基准测试。
- 依赖：WP2（Gold Set）、WP6。

### WP11｜延迟优化与 Demo 装配（M）
- 产出：并行化改造（A1/A2/A3 并行调用）、Requirement Graph 缓存、Demo 路径预热、前端流式渲染；Demo 剧本 + 彩排 + 录屏 + 故障预案。
- 验收：D7 延迟指标达标；连续两次彩排通过。
- 依赖：全部。

---

## 4. 里程碑

```mermaid
flowchart LR
    M0["M0 计划批准<br/>阻塞项到位"] --> M1["M1 契约冻结<br/>WP1"]
    M1 --> M2["M2 数据与沙盒<br/>WP0 WP2 WP3 WP4"]
    M2 --> M3["M3 服务平面 + Agent 主链<br/>WP5 WP6（CLI 端到端跑通）"]
    M3 --> M4["M4 三端 UI + 垂直切片<br/>WP7 WP8 WP9"]
    M4 --> M5["M5 评测与延迟<br/>WP10 WP11"]
    M5 --> M6["M6 Demo 冻结"]
```

- 关键路径：**WP1 → WP5 → WP6 → WP7 → WP11**
- WP1 + WP2 无云依赖，**计划批准后立即开始**
- 总量估算（我全职）：**20–26 个工作日等效**
- 截止日期不作为约束（已确认时间充足），因此按里程碑推进而非日历排期；§7-R4 的砍序方案保留为意外情况的应急路径，不主动触发

---

## 5. 需要你提供的内容

### 阻塞项（M0 前必须到位）

| # | 需要什么 | 具体形式 |
|---|---|---|
| **1** | GCP 项目与执行权限 | 项目 ID + 已开通 Billing。最简方式：在本会话输入 `! gcloud auth login`（用有 Owner/Editor 的账号），我用 gcloud CLI 操作 |
| **2** | Gemini Enterprise / Agent Platform 可用性 | Vertex AI Agent Engine / Agent Registry / Agent Gateway 在你的项目+区域是否可用？登录后我自查并报告；若不可用需你批准降级 R1 |
| **3** | 计费口径确认 | 见下方 §5.1；登录后我查 billing account 上挂的 credits 类型并报告 |

已确认、无需再提供的事项：

- **截止日期**：不作为约束（你已确认时间充足），因此本计划按里程碑而非日历排期推进；
- **提交形式**：Web App；
- **Calendar 测试账号**：已提供，走模式 A（真实 OAuth）。**账号凭据不写入任何文档、代码或提交物**，只在运行时通过环境变量注入；
- **UI 设计语言**：Apple 设计语言，依据 `.agents/skills/apple-design`。

### 5.1 关于 GCE 与 Gemini API 的计费口径（需确认）

这三者是**独立的计费概念**，容易混淆：

| 概念 | 是什么 | 与我们的关系 |
|---|---|---|
| Compute Engine（GCE） | 虚拟机租用，按机器规格与运行时长计费 | 我们用它跑 Moodle 沙箱 |
| Vertex AI Gemini API | 模型推理，按 token 计费 | Agent 的实际调用走这里 |
| Gemini Enterprise | **按席位（per-seat）授权的企业产品**，不是按量计费的 API | 命题名称来源，但不等于我们代码里调的东西 |

**关键结论：拥有 GCE 额度不等于可以免费调用模型**——两者是不同的 SKU。

#### 5.1.1 ✅ 已定案：模型调用只走 Vertex AI（2026-07-29）

经查证 Google 官方文档，赠金对两条路径待遇**不同**：

> "The $300 credit can't pay for Gemini API in AI Studio costs." —— Google Cloud Free Program 文档
> "starting March 2026, Gemini API usage costs are specifically excluded from the Google Cloud Free Trial program." —— Gemini API 计费文档

| 路径 | 认证 | 赠金覆盖 | 本项目 |
|---|---|---|---|
| Vertex AI（`aiplatform.googleapis.com`） | 服务账号 / ADC | ✅ 覆盖 | **唯一允许** |
| AI Studio（generativelanguage 端点） | API key | ❌ 不覆盖，直扣个人信用卡 | **禁用** |

**执行约束**：代码中不得出现 `google.generativeai` SDK、`GOOGLE_API_KEY` 环境变量或该端点调用。用 `google-cloud-aiplatform` 或 ADK 的 Vertex 后端。由 pre-commit hook 与评测项 **B12** 双重强制。

> 此前版本曾把"AI Studio API Key 作为本地开发 fallback"列为待提供项，**该条已删除**——它正是绕过赠金的路径。本地开发同样走 ADC（`gcloud auth application-default login`），不需要任何 API key。

#### 5.1.2 实际账户状态（2026-07-29 核实）

| 项 | 值 |
|---|---|
| 项目 | `keen-opus-498918-m8` |
| 计费账号 | `BILLING-ACCOUNT-REDACTED`（币种 **HKD**） |
| 赠金 | **HK$1,568.39** ≈ US$201，一次性 |
| **过期日** | **2026-09-27** —— 比比赛截止更硬的死线 |
| 预算告警 | 已建，5 档 25/50/75/90/100% |

**已修复的隐患**：项目原本挂在个人 USD 账号上，赠金在另一个挂 0 个项目的账号上——赠金完全未生效，开销会打到个人信用卡。已重新链接，`scripts/preflight.sh` 每次开工复检。

成本估算（HKD）：Moodle GCE ~HK$195/月（夜间停机可减半）、Cloud Run 近免费档、模型调用 HK$230–780。**总计约 HK$470–1,010，额度充足。**

### 非阻塞项（M3 前补齐）

| # | 需要什么 | 说明 |
|---|---|---|
| 4 | Counseling 测试邮箱 | 你控制的邮箱，接收 outreach demo 邮件。可以与 Calendar 测试账号是同一个 |
| 5 | Gold Label 复核 | 我先用规则生成初版标签；复核由谁完成、以什么形式回传给我，需要你确认（见 R8） |
| 8 | `phd-to-industry` Career Path Pack | 若该 Pack 会交付，请按 `CareerPathPack` 格式给我。**未交付则 MVP 不受影响**：前端不显示该 Pack，也不在任何材料中宣称支持该路径（Spec §2.3.1） |

### 已具备的外部资料

| 资料 | 用途与边界 |
|---|---|
| **HKUST 本科课程目录**<br>`https://prog-crs.hkust.edu.hk/ugcourse/<TERM>/<SUBJECT>` | **真实课程数据，直接抓取使用。** 这是学校公开的课程目录，只含课程信息（代码、名称、学分、先修、互斥、描述、CILO），**不含任何学生数据**。<br>抓取器：`seed/scrape_hkust_catalog.py`，磁盘缓存 + 1s 礼貌间隔 + 串行。<br>**已验证**（2026-07-29 smoke test，COMP + MATH 160 门）：核心字段 100% 覆盖，先修 82%（低阶课本无先修属正常），课程代码唯一，先修表达式如 `COMP 1021 OR COMP 1023` 与 `(prior to 2025-26)` 完整保留。<br>**价值**：真实先修表达式是 Rules Engine 先修解析的天然测试素材，远优于编造。学生、成绩、日历、机会、Publisher 仍全部合成 |

---

## 6. 我自行拍板的默认假设（不同意请推翻）

1. Firestore 而非 Cloud SQL；Moodle 用 GCE 内置 MariaDB；
2. UI 简/繁/英三语（i18n 资源文件 + 可切换且持久化）；单一 Next.js 应用拆**两个各自登录的门户**（2026-07-31 用户裁定，取代"三端同 app 按角色路由"）；
3. 3 个 Persona 深度完整，其余 Seed 精简到刚好支撑失败样本；
4. Calendar 走模式 A（真实 OAuth，测试账号已提供）；模式 B（Fixture）保留为 R3 降级路径；
5. F27 只实现 Pack 接口 + `undergrad-direct-employment` 一个实装 Pack；International Student Context Pack 与 `phd-to-industry` 只演示加载/卸载机制，不写任何政策或路径内容；
6. F18 Event Monitor 用 Demo 事件注入按钮触发，不部署真实定时任务（Spec §18.1 允许）；
7. G1–G4 四项定位补强全部纳入 P0（成本很低，但直接影响 Quantifiable Impact 与 Real-World Viability 评分）。

---

## 7. 风险与降级

| # | 风险 | 降级方案 |
|---|---|---|
| R1 | Agent Engine / Registry / Gateway 权限不可得 | ADK Agent 自托管到 Cloud Run（两服务对应两 Runtime），自建注册表 JSON + service account 隔离作为治理证据；口径改为"治理设计对齐 Agent Platform，演示用等价实现" |
| R2 | Memory Bank 不可用 | Firestore 实现 `MemoryProvider`（Spec §8.7 已预留接口），语义检索用 embedding + 向量最近邻 |
| R3 | Google OAuth 授权流程受限或配额不足 | 退回 Calendar 模式 B（Fixture），接口不变，页面明确标记 |
| R4 | 出现意外阻塞导致 P0 做不完 | 应急砍序（与你确认后才执行）：① 校方端 UI 精细度降级（保 API + 最小页面）→ ② Persona 从 3 降到 2 → ③ Publisher 审核分支只演示批准（去掉退回/驳回）→ ④ **最后手段**：Moodle 真实实例换 Mock LMS（损失 Ecosystem Execution 评分，非必要不做） |
| R5 | 模型输出不稳定拉低指标 | 资格与约束判定本就在 Rules 层，模型只做解释；所有 Agent 输出过 Schema 校验 + 重试；指标受结构保护 |
| R6 | Demo 现场延迟不可接受 | WP11 的预热 + 并行 + 缓存 + 流式；最坏情况用录屏 |
| R7 | 成本失控 | A4 用低成本模型；Moodle 夜间停机；每日成本检查脚本 |
| R8 | Gold Label 标注拖期 | 我先用规则生成初版标签，人工只做复核，工作量降到约三分之一 |

---

## 8. 计划批准后的第一步

1. 你提供 §5 阻塞项 1–3（核心是 `gcloud auth login`）；
2. 我立即启动 **WP1（契约冻结）** 和 **WP2（数据设计）**——两者无云依赖；同时用 gcloud 完成 WP0，并第一时间查清 §5.1 的计费口径回报给你；
3. 每到一个里程碑（M1–M6）提交进度报告 + 可验证产物清单 + 已消耗成本。

## 9. 凭据与敏感信息处理规则

适用于本项目全部产出物（代码、文档、可视化网页、提交材料、Demo 录屏）：

- Google 账号、密码、OAuth client secret、API Key、Moodle 服务账户 Token 一律**不写入任何文件**，只通过环境变量或 Secret Manager 注入；
- `.env` 只提交 `.env.example`（占位符），真实值不入库；
- 测试邮箱地址不出现在文档、网页与截图中；Demo 录屏中如出现，需打码；
- 所有合成数据不得使用真实姓名、邮箱、学号、成绩；
- 全站与全部演示页面保留 `Synthetic / Demo Data` 标记。

---

## 10. 工程方法：Harness Engineering（全程强制）

> **不信任任何未经自动化验证的断言——包括我自己刚写下的那一句。**

### 10.1 五条准则

| # | 准则 | 做法 |
|---|---|---|
| H1 | **先建验证，再建功能** | 每个 WP 先写检验脚本或断言再写实现。WP1 契约冻结排第一，因为它是所有后续验证的地基 |
| H2 | **约束写进机器，不写进备忘录** | "不用 AI Studio"必须落成 pre-commit hook + 评测项 B12，不靠人记 |
| H3 | **报告实测值，不报告预期值** | 说"测试通过"附命令与输出；说"部署成功"附实际访问验证 |
| H4 | **失败要能复现** | 每个失败样例给出输入、期望、实际、复现命令，存 `eval/results/failures/` |
| H5 | **检查脚本本身也要被检查** | 写完必须用**已知会失败的样例**验证它真的会失败 |

### 10.2 已踩过的坑

| 坑 | 教训 |
|---|---|
| 凭"产物列表没变化"推断发布成功而未验证内容 | 部署必须实际访问并断言页面内容 |
| `grep \| head` 管道退出码恒为 0，密钥扫描永远误报 | 管道中的退出码判断必须显式处理 |
| pre-commit 的 grep 把 `-----BEGIN` 当成选项而静默失效 | 模式可能以 `-` 开头，grep 前加 `--` |
| 检查器分不清"文档提到端点以禁止它"与"代码调用该端点"，误拦正当提交 | 内容检查按文件类型分域；发现误报**修检查器，不用 `--no-verify` 长期绕过** |
| 幂等检查用 `new` 的首行判断"是否已应用"，而那行常与锚点相同 | 恒为真而静默跳过编辑；应改用**独特标记**判断 |
| 本目录文档曾被外部进程多次回退，编辑丢失 | 改完**立即 commit 落库**，别攒着 |
| 禁用路径检查器把"**代码**里把它列进禁用词表"当成"代码调用它"，拦下了拦截器自身与其测试 | 同一个误报换了个位置又出现一次：先是文档、后是代码。改为**按行判定 + 同行标注 `ai-studio-denylist` 豁免**，`scripts/pre-commit` 与 `scripts/preflight.sh` 两处口径一致。标注进 diff、可 grep 审计，比"整份文件跳过"精确 |

| 单元测试全绿，真实 HTTP 打过去 500 —— 端点根本没被任何测试调用过 | 覆盖率不是"测试数量"，是"**每个对外入口至少被真实调用过一次**"。§10.3 的浏览器实测协议对后端同样适用：起服务、curl、看状态码 |
| 浏览器实测新路由（/wellbeing-desk）登录后停在 /login，误判为守卫 bug——实际是 Next dev 首次编译新页面慢于固定 sleep | drive.mjs 断言跳转用 `waitForFunction(location.pathname===…)` 等条件，不用固定延时；新路由首访要预留编译时间 |
| 外联同意只 seed 给 STU-B，其他学生按「联系辅导员」全部 403——测试都用 STU-B 所以全绿 | 凡"每个学生都该能做"的动作，测试要**遍历全部 demo 学生**；fixture 别只造一份 |
| 确定性 `validation_id` 与每次变化的 `evaluated_at` 冲突，同一端点**第二次**调用必炸 | 幂等性要单独测：只调一次的测试永远发现不了重放问题。凡是"同一输入应得同一结果"的地方，测试就要**连调两次** |
| Next dev 改动后首访重编译慢于断言超时，回归 runner 偶发 FAIL——同一断言复跑就绿 | 浏览器断言脚本对失败**先 reload 重试一次**再判死；「偶发红」不许靠人肉复跑洗白，把重试写进 runner（`run-pages-must.mjs`） |
| 词典 en.ts 的多行值（键与值不同一行）被逐行插键脚本劈开键值对，构建期才炸 | 机械插入 TS 词典要么用 AST，要么锚定到**值结束**的行；插完立刻 `tsc --noEmit`，别攒 |
| 新装的 editable 包对**已在跑**的服务不可见（.pth 只在解释器启动时生效），uvicorn --reload 重载代码但不重建 sys.path——decomposition 端点 500 到重启才好 | 装了新工作区包就重启常驻进程；「--reload 会处理」只对已在 path 里的代码成立 |
| 用 Edit 在 Pydantic 类字段区**中间**追加新类，把后面的 @model_validator 劈进了新类——契约测试全绿（validator 静默失效在另一个类上） | 向类追加内容锚定到**类的最后一个成员之后**；插完看一眼 `sed` 上下文再跑测试 |
| Cloud Run Job 执行表看串了列：FAILED=1 被读成 SUCCEEDED=1，据此报告"巡检成功"——根因是 `.gcloudignore` 把 `jobs/` 排除在构建上下文外，容器里根本没有那个脚本 | 断言 Job 成功要用 `executions describe` 的字段值 + **业务侧留痕**（API 上真的有巡检时间戳），不读表格排版；`.gcloudignore` 与 Dockerfile 的 COPY 清单要一起 review |
| 本地 dev server 代理默认打 127.0.0.1:8000，上一轮会话残留的旧 API 进程还在监听——对着"以为是云端"的旧后端做了半轮审计 | 起代理后**先断言后端身份**（拿一个只有目标后端才有的数据点，如条目总数/版本号），再开始测；杀残留进程列入开工检查 |
| 新前端读新契约字段（`intl_notes`），代理却指着旧版本后端——字段 undefined，`.length` 直接炸掉整页，pages-must 报 FAIL | 门禁与浏览器实测必须**前后端同版本**（本地新 api + 本地新 web）；跨版本兼容不是前端 `??` 兜底的理由，契约默认值只在同版本内成立 |
| 审查 #18 把 connector/packs 的 llm-free 测试改了名，Makefile `llm-free` 目标却硬编码 `tests/test_llm_free.py`——改名后 `make check` 一直是红的，但改名那批收尾没有重跑 make check，"全绿"结论带着一个从没再跑过的检查 | 改**被检查对象的名字/位置**时，当场重跑引用它的每个检查目标；收尾"全绿"清单要列明**每项各自的最后实跑时间**，不许拿上一轮的绿抵账（目标已改为 `test_llm_free*.py` 通配） |
| 用 Edit 在 `@implements(...)` 装饰器与被装饰函数**之间**插入 helper——装饰器吃掉了 helper，原端点从路由表消失，helper 的参数 `d` 变成了 query 参数 | 与「劈进 Pydantic 类」同族：插入点必须锚定**完整的 装饰器+函数 单元之外**；插完立刻跑该端点的一条测试，不攒 |
| matches 的副目标配额注入 top50 尾部，展示层切前 10 时配额全被挤掉——测试只查"总表里有没有"就会假绿 | 结果会被**缓存后按任意 limit 切片**的列表，任何比例保证必须对**每个前缀**成立（前缀成比例交织），测试断言配额时要按展示口径（limit=10）数 |
| 用 pkill -f uvicorn 杀不掉 --reload 的 worker 子进程（cmdline 是 multiprocessing spawn，不含 uvicorn 字样）——老进程霸着 8000，新 make api 静默 Error 3，随后的"实测"全打在旧代码旧状态上（浏览器实测阶段真实发生） | 重启常驻服务用**端口反查 PID** 强杀并断言端口已空再起；起完先打只有新代码才有的探针（新字段/新措辞）确认身份，再开始测 |
| 接地抽取提示词写"category 词表同上"——它是独立调用，没有"上"；模型自由发挥 education/tool/time，解析器如实丢弃，产量 1/7 | 提示词禁止跨调用指代，词表**显式嵌入每个** prompt（join(CATEGORY_MAP) 生成，改词表自动同步）；再配确定性别名归一收常见近义 |
| uvicorn --reload 连测试文件目录也在监听——往 tests/ 追加测试就触发整个应用 reload，内存态（目标/研究任务）静默清空，紧接着的浏览器验证"莫名"读到空状态 | 演示/验证期用不带 --reload 的进程，或验证前重建所需状态并**先探针确认状态在**；"状态怎么没了"先查 reload 日志再查代码 |
| 直接 `uvicorn …` 起本地 API 没有带 `.env`——`deps.model=None`，A5/推荐理由全走降级路径，"A5 没生效"查了半天代码，其实是环境 | 起服务永远走 `make api` 的 env 装载口径（`set -a; . ./.env; set +a`）；「模型面怎么不工作」先探 `deps.model` 是否为 None，再看代码 |
| Next 预渲染 HTML 自带 `s-maxage=31536000`——Google 门时代所有请求先 307，这个头**从未生效过**；门一撤，缓存节点把旧部署的 HTML 发给用户（引用的 chunk 已不存在）→ 白屏，而修复者自己的浏览器命中新副本一切正常 | 撤掉挡在前面的层（门/代理/重定向）时，要审视它**顺带遮蔽了什么行为**（缓存头/CORS/压缩）；页面 HTML 一律 `no-store`（middleware 统一加），只让内容哈希的静态资源长缓存 |
| 给测试「加料」（拍前 9 个机会到近两周）但料没进分数前列——断言碰巧全绿，什么也没证明；实现根本没写上限逻辑测试也过 | 构造失败场景要**让被测约束成为唯一约束**（全量拍近两周、断言精确等于上限值），再看它红；「断言过了」与「断言有约束力」是两回事 |
| 浏览器脚本等「有条目」（length>0）就读数——A5 重新生成期间旧渲染还挂着，三档读出同一组数，差点当产品 bug 上报（一天内第二次） | 等待条件必须是**目标状态的独有特征**（如档位注记的门数变成该档目标值），不是"页面有东西"；凡验证"切换生效"，等的是变化本身 |
| 凡「失败静默回落」的路径（A5 失败→夹具），验证只看"页面没炸"就会把回落态当成功态——本轮就差点把 env 缺失导致的夹具当成"A5 已生效" | 这类路径必须**正向断言成功态的独有特征**（如 trigger=a5:、模型理由文案在场），回落态与成功态要有可断言的显式区别 |
| 浏览器自动化用 JS `el.click()` 点反思对象选择，React onPointerDown 监听收不到——textarea 一直 disabled，差点当成产品 bug 上报 | 验证脚本对交互元素用 puppeteer **真实指针点击**（elementHandle.click()），JS click 只用于确认过监听方式的元素；"点了没反应"先换 trusted 事件再定性 |
| 契约里两个同名字段承载两种概念：`StudentProfile.current_term` 是 "y1s2" 年级码，教务 TermCode 是 "2026-27_FALL"——A5 拿前者当后者用，用户在目标工作室选了年级后整个规划页 500 | 同名不同义的字段是定时炸弹：取值前**看目标 schema 的 pattern/Literal**，别按字段名望文生义；跨模型传值优先走已验证的权威源（seed manifest），不从"恰好也叫这个名"的地方拿 |
| A5 生成抛异常（上一条的 500）不进失败负缓存——负缓存只覆盖"返回 None"路径，异常路径每次 GET 都重烧一轮模型再炸一遍（本地实测每刷一次 8–17 秒 Vertex 调用打水漂） | 「失败不重试」的负缓存必须覆盖**所有**失败出口（返回值失败 + 异常失败）；读端点包 try/except 时，except 分支要与失败分支做**同样的记账** |
| 行动中心「近两周」筛 `status==="in_progress"`——那是演示夹具拿 status 编码档期的私约，A5 真数据全是 proposed → 该区恒空，与规划页（按日期分桶）互相矛盾数周 | 前端不许依赖某个数据源实现的**私有编码习惯**做语义判断；同一语义（"近两周"）在多页出现时抽**单一出处**（plan-window.ts），并且读同一资源的页面要带**相同的请求参数**（强度档）——参数不同=读的不是同一份数据 |
| pages-must 把「外联同意默认关闭」写成 `[data-consent-granted='false']` 状态断言——用户测身心链路**合法授权一次**，门禁从此永远红（还差点被当产品 bug 追查） | 浏览器门禁的 must 项只断言**控件在场**，不断言可被用户合法操作改变的状态；「默认关闭」这类不变量钉在**状态确定的层**（fresh seed 全学生遍历的单测），且加料样例先证明断言真的会响 |

前几条是靠 H5 发现的，后两条是靠**真实 HTTP 实测**发现的——没有一条是靠"仔细看代码"发现的。

### 10.3 浏览器实测协议（前端唯一验收方式）

**未经在真实浏览器中亲自点击验证的前端功能，不得声称"已完成"。** 不接受读代码推断、单测通过、构建无报错。

| 步骤 | 做法 |
|---|---|
| 1 | chrome-devtools 打开实际运行页面 |
| 2 | **逐个功能点击**，不只看首屏渲染 |
| 3 | `evaluate_script` 断言 DOM 真实状态（元素数、文本、data 属性） |
| 4 | **中英两种语言各走一遍**，确认无硬编码文案、无溢出错位 |
| 5 | 截图存 `docs/verification/<WP>-<功能>-<lang>.png` |
| 6 | 检查 console 无报错、无 404 |
| 7 | 关键交互测反向用例（未授权时是否真被拦） |

最终交付前形成 `docs/verification/final-acceptance.md`，是 D7 彩排的前置条件。

### 10.4 Codex 审查的用法与边界

| 场景 | 命令 |
|---|---|
| 工作包完成后 | `/codex:review --scope working-tree` |
| 架构决策、安全契约 | `/codex:adversarial-review`（挑战设计选择本身） |
| 卡住或要第二种思路 | `codex-rescue` 子 agent |
| **Codex 超时 / 无结论 / 额度上限** | **改用独立 subagent 审查并回报结果** |

**审查者不是决策者。** 每条意见三选一：采纳并改（说明改了什么）／不采纳（说明为何不成立）／记录待办（说明为何延后）。

**审查不可因工具不可用而跳过。** 2026-07-29 实际发生过一次：Codex 任务发起后逾一小时无输出（疑似额度上限），
若就此放过，WP1 就成了"跑过审查"的假象。正确做法是换一个独立的审查者重跑——
换谁审都行，唯独不能变成没人审。

### 10.5 测试策略：反馈环要快

**原则：验证强度与改动阶段匹配。** 每轮都跑全量验证会让反馈环慢到没人愿意跑，反而降低质量。

| 阶段 | 用什么 | 时长目标 |
|---|---|---|
| 写代码时 | **TDD** —— 先写失败的测试，再写实现让它通过 | 秒级 |
| 每次改动后 | **Smoke test** —— 最小路径能跑通（1 个 Persona、3 条机会、1 门课） | < 10s |
| 改某模块后 | **局部测试** —— 只跑该模块及其直接下游 | < 60s |
| WP 收尾 | 该 WP 完整验收 + 相关评测项 | 几分钟 |
| 交付前 / 每日一次 | **全量** `make eval` + 全部 BLOCKER + 浏览器实测 | 可以慢 |

配套要求：

- `make smoke` 必须存在且 < 10 秒，这是最常用的命令
- Gold Set 提供 `--sample N` 参数，开发时用 10 条，收尾才跑 60 条
- Seed 提供 `--tiny` 档（1 Persona / 5 课程 / 5 机会），供 smoke 与单测使用
- 评测脚本支持 `--only B1,B4,T3` 只跑指定项
- **不要**为了"保险"在每次提交前跑全量——那会让人开始跳过验证，比慢更糟

### 10.6 委派给便宜模型

机械、规则明确、产出可校验的活，交给 **sonnet subagent** 跑并回报结果，我只审结论：

| 适合委派 | 不适合委派 |
|---|---|
| 批量抓取与格式转换（如逐学科抓课程目录） | 架构决策、取舍判断 |
| 跑固定脚本并汇总输出（seed 生成、批量校验） | 评测结果的解读与是否达标的判定 |
| 日志/报告的整理与去噪 | Codex 审查意见的采纳与否 |
| 大量重复的样板文件生成（i18n 键位骨架） | Schema 契约设计、安全契约实现 |
| 跨文件的机械改名与引用同步 | 任何涉及金钱、隐私、安全的改动 |

委派时必须给出：明确的输入、明确的产出格式、明确的成功判据。回报后我**独立复核关键结论**，不直接采信。

### 10.7 每个工作包的收尾清单

1. `bash scripts/preflight.sh`
2. 该 WP 的验收条款（§3）
3. `make eval`（若影响评测项）—— BLOCKER 全绿
4. `/codex:review` —— 结论逐条处置
5. 涉及前端 → §10.3，双语各一遍
6. **更新 `PROGRESS.md`** —— 已完成表加一行（附验证方式）、WP 状态、新增的决策或坑
7. `git commit`（§11），报告 commit hash

---

## 11. 提交纪律

每个修改文件的实现任务，**必须在给出最终回复前完成一次 git commit**：

- 编辑前先看 `git status`，把已存在的或并发产生的改动当作**用户所有**，不擅自纳入
- 提交前审查完整 diff，并跑与改动量相称的验证
- **只暂存属于当前任务的文件或 hunk**；不把无关改动打包进同一次提交
- 在 `main` 上用简洁描述性的提交信息，**报告 commit hash**
- **不 push、不 amend、不改写历史**，除非用户要求
- 只读任务或无文件改动的任务，**不制造空提交**
