# CampusPath

HKUST Google 黑客松参赛项目（命题：Gemini Enterprise for Higher Education）。

一个由 Gemini Enterprise 驱动的动态校园成长路径 Agent 系统：持续整合校内外可信资源与学生真实反馈，把学生想成为的人动态倒推成当下可执行、并随变化实时校准的校园成长路径。

- MVP Study Case：Undergraduate → Direct Employment
- 架构：6 语义 Agent（A0–A5）/ 9 个确定性服务，双平面 + 契约先行（详见 [ARCHITECTURE.md](ARCHITECTURE.md)）
- 功能基线：F01–F27（零删减）
- 交付形态：Web App（学生 / 校方双门户，简/繁/英三语）

## 文档

| 文档 | 说明 |
|---|---|
| **[CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md](CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md)** | **产品说明书 — 唯一现行基线**（现 v4.1.26，实现同步批注随版本块滚动） |
| [CampusPath_Implementation_Plan_V2.md](CampusPath_Implementation_Plan_V2.md) | 实现计划：交付标准 D1–D7、工作包 WP0–WP11、踩坑台账 §10.2、风险降级 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 架构文档：双平面组成、系统架构图与关键数据流（mermaid）、六条红线的技术落点 |
| [CampusPath_Architecture_Review_V4.1.md](CampusPath_Architecture_Review_V4.1.md) | V4.1 各项修改的论证过程记录（含被否决与被撤销的条目及理由），非执行基线 |
| [PROGRESS.md](PROGRESS.md) | 进度审计：断点、决策时间线、待确认项（只记已验证事实） |
| [docs/demo-runbook.md](docs/demo-runbook.md) | Demo 运行手册：Spec §19 十七步对照与彩排清单 |
| [docs/campuspath-visual.html](docs/campuspath-visual.html) | 交互式项目说明网页源码（五分页：项目背景 / 功能清单 / Agent 架构 / Workflow / 技术实现） |
| [contracts/README.md](contracts/README.md) | 契约层：Schema 唯一真相来源，以及它强制了哪些红线 |
| [seed/DATA_DICTIONARY.md](seed/DATA_DICTIONARY.md) | 合成数据字典 |
| [infra/README.md](infra/README.md) | GCP 基础设施脚本（bootstrap / verify / moodle / cost） |

V4 历史基线已从仓库删除——**只保留一份基线，就不会引错基线**。要看 V4 原文走 git 历史。

## 项目文件结构

```text
HKUST_CampusPath/
├── CampusPath_Complete_Product_Spec_V4.1_2026-07-28.md   # 产品基线（v4.1.26）
├── CampusPath_Implementation_Plan_V2.md                  # 执行计划
├── ARCHITECTURE.md                                       # 架构文档（图在此）
├── PROGRESS.md                                           # 进度审计
├── CLAUDE.md                                             # 工作硬约束（会话自动加载）
├── Makefile                                              # check/eval/api/web/contracts/seed…
│
├── contracts/                    # 契约层：唯一真相来源（1.35.0）
│   ├── campuspath_contracts/     #   173 个 Pydantic 模型 + 声明式 openapi.py + 边界守卫
│   ├── openapi/campuspath.json   #   生成的 OpenAPI 3.1（88 路径 / 108 操作）
│   ├── schema/                   #   逐模型 JSON Schema 冻结产物
│   └── tests/                    #   B1–B13 红线逐条测试 + 变异自检
│
├── services/                     # 确定性平面（零 LLM，三层扫描强制）
│   ├── rules/                    #   先修三值逻辑、四态资格、validation_id 签发（+国际生 Pack 桥）
│   ├── capacity/                 #   五类时段、容量公式；Calendar Token 止步于此
│   ├── wellbeing/                #   五信号阈值 + 固定双语模板 + 两次提醒状态机
│   ├── state/                    #   四层记忆、Profile 三段式写入、锁定/忘记
│   ├── action/                   #   预览→回执→幂等执行→审计
│   ├── aggregation/              #   k-匿名抑制、时间衰减（无 student_id）
│   ├── monitor/                  #   事件去抖 + 受影响范围（长期项不波及）
│   ├── publishing/               #   投稿状态机、越权拦截留痕
│   ├── connector/                #   统一适配器接口 + Source Health + 源注册表（92 源）+ 共享抓取器/变更检测
│   ├── packs/                    #   国际生 Context Pack（vendored，确定性求值，待政策复核）
│   ├── api/                      #   FastAPI 装配 + RBAC + B8 闸门（app.py + a5_pathway.py A5 线上生成 + resume_template.py 模板解析）
│   └── mock-campus/              #   SIS / Degree Audit 等 7 个 mock 端点
│
├── agents/campuspath_agents/     # 语义平面：A0–A5 + 工具白名单 + Vertex-only 守卫
│   ├── pack_data/                #   岗位画像 + 权威证据参考表（compile_employment_pack.py 编译产物）
│   ├── live_market_research.py   #   现场拆解真流水线（接地搜索→真抓原文→确定性加权）
│   ├── roster.py                 #   六个 Agent 类 + GOAL_DECOMPOSITION_PACKS
│   ├── tools.py                  #   ToolBelt 白名单（A4 仅 2 个工具）
│   ├── vertex.py                 #   唯一模型出口（ADC + assert_vertex_only）
│   └── workflows.py              #   Plan A/B/C 并行、约束修复循环、多源隔离抽取
├── agents/cloud/                 # ADK 部署镜像（A0/A4 → Vertex AI Agent Engine，两运行时；镜像一致性 CI 断言）
│
├── apps/web/                     # Next.js 16 前端（bun），学生/校方双门户
│   ├── src/app/                  #   login + 学生 14 页 + 校方 6 页（publisher/console/review/plaza-admin/advisor-desk/wellbeing-desk）
│   ├── src/components/           #   shell / nav（门户过滤+守卫）/ ui / primitives / add-to-plan / review-queue
│   ├── scripts/                  #   三道 UI 门禁：check-contrast / check-alignment / run-pages-must（各带 H5 自检）
│   ├── src/i18n/                 #   en.ts（类型源）+ zh-Hans + zh-Hant（生成物），三语切换持久化
│   ├── src/lib/api.ts            #   契约类型化 API 客户端
│   ├── src/lib/gate.ts           #   口令门 HMAC（middleware 与校验路由共用）
│   ├── src/lib/plan-window.ts    #   规划时间窗口口径（行动中心/课外规划共用）
│   └── public/resume-template.md #   官方 Resume 模板（上传只认它，零 AI 解析）；同目录 demo-resume-*.md 一键注入用
│
├── seed/                         # 数据层
│   ├── campuspath_seed/          #   确定性生成器（SEED 1.9.0）+ Gold Set + 失败样本 + 一致性检查
│   ├── scrape_hkust_catalog.py   #   真实课程目录抓取（1534 门，磁盘缓存 + 礼貌间隔）
│   ├── scrape_hkust_events.py    #   Engage 活动抓取（66 条官方源）
│   ├── scrape_hkust_programs.py  #   5 专业培养要求抓取
│   └── raw/                      #   冻结的真实数据快照（courses.json / programs.json）
│
├── jobs/                         # 每日源巡检脚本（Cloud Run Job 形态见 infra/sources_job.sh）
├── mcp/moodle_mcp/               # Moodle 只读 MCP：白名单客户端 + stdio 服务器 + 契约适配器
├── eval/campuspath_eval/         # make eval：13 BLOCKER / 12 TARGET / 5 BASELINE
├── infra/                        # GCP 脚本（默认 dry-run）：bootstrap/verify/moodle/cost/agent_engine（运行时 status/query/delete）
├── scripts/                      # preflight（14 项自检）、pre-commit 密钥拦截、install-hooks
├── docs/                         # demo-runbook、verification/ 浏览器实测截图、visual 网页
└── .claude/                      # hooks（上下文交接引擎）、skills、handoff
```

## 开工

```bash
bash scripts/install-hooks.sh   # 首次或换机
make setup                      # 创建 .venv 并安装工作区
make check                      # preflight + 契约/Seed 一致性 + 全量测试 + llm-free
```

日常最常用：`make smoke`（< 1 秒）· `make eval`（机器判定）· `make api`(8000) + `make web`(3100)。
详细进度与断点见 [PROGRESS.md](PROGRESS.md)。

## V4.1 相对 V4 的变更

**F01–F27 零功能删减。** 变更只涉及「由谁实现」和「用什么方式实现」，完整差异见说明书 §25。

六处架构收紧：

1. **C1** A2 剥离容量计算 → `Capacity & Calendar Service`（确定性），Calendar Token 不再进入任何 LLM 上下文
2. **C2** Wellbeing 五信号判定与提醒文案全链脱离 LLM（Rules 阈值 + 固定模板）
3. **C3** A2 只出事实与候选，A5 成为系统中唯一做 trade-off 的 Agent
4. **C4** A4 不可信内容三条隔离契约（内容非指令 / 工具白名单 / Schema 闸门）
5. **C5** A1 与 Aggregation Service 之间建立数据类型边界，私人原文物理上无路径到达校方
6. **C6** A0 两段式路由：确定性路由表 + LLM 编排兜底

三处引入 ADK Workflow Agent（Agent 内部构件，部署单元与治理对象数量不变）：A5 的 Plan A/B/C 并行生成、A5 的约束修复循环、A4 的多源隔离抽取。

四项定位补强：双边价值陈述、三项资源利用率指标、Goal Studio 主目标+候选目标、GrowthTrajectory 成长曲线。

## 线上环境（2026-08-03 · Cloud Run · asia-east2 · 赠金项目）

- **Web**：https://campuspath-web-786160486093.asia-east2.run.app （rev 00019-269）
  （**访问口令门**，2026-08-02 取代 Google 邮箱白名单：口令只存 Cloud Run 环境变量
  `CAMPUSPATH_DEMO_PASSCODE`（本地 .env 同名），服务端校验 + HMAC httpOnly cookie，
  页面与 `/api/*` 反代都在门内；口令值不进代码/文档/界面，向团队口头分发；
  本地开发不设该变量门自动不存在）
- **API**：https://campuspath-api-786160486093.asia-east2.run.app （rev 00013-hqr；公网实例不含测试邮箱，联系人回落哑地址；
  `CHECKIN_SECRET` 挂 Secret Manager `campuspath-checkin-secret`；**max-instances=1**——巡检/签到/后台任务全是实例内存态，多实例会互相看不见）
- **每日源巡检**：Cloud Run Job `campuspath-sources-refresh` + Cloud Scheduler `campuspath-sources-daily`（09:00 HKT；赠金 2026-09-27 到期前 `bash infra/sources_job.sh delete --apply` 清理）
- **Agent 运行时 ×2**：Vertex AI Agent Engine（us-central1），`bash infra/agent_engine.sh status|query|delete`；
  顶栏**状态灯**实时显示（绿=运行中计费——云端探测走 Vertex REST 回退，2026-08-03 起线上可见）；控制按钮仍是本地功能（云端点按如实 503）
- 缩容到零，闲置近乎零成本；Agent Engine 按小时计费（约 HK$50–100/天量级，实测以账单为准），用完 delete。
- 重新发布：仓库根 `gcloud run deploy campuspath-api --source .`（Dockerfile 现含 `jobs/`，Job 镜像同源需一并 `gcloud run jobs deploy`）；`apps/web` 下先 `rm -rf .contracts-generated && cp -r ../../contracts/generated .contracts-generated`（**必须先 rm**——目录已存在时 cp -r 会拷成嵌套子目录，云构建吃到旧类型）再 `gcloud run deploy campuspath-web --source .`。
  **契约变更的发布次序按变更方向定**（1.32.0 审查裁定）：
  ① 新增**响应**字段/枚举值（api 说新话）→ 先发 web 后发 api（旧前端读新值会渲染误导性 UI；新前端对旧 api 有 `?? []` 守卫）；
  ② 新增**请求体**字段/枚举值（前端说新话，如 ProposedChange.entity_type 扩容）→ **先发 api 后发 web**（旧 api 收到新枚举直接 422）。
  两类都有时分两步发，中间各自验证。

## 状态（2026-07-31）

- **WP0–WP10 全部完成**：契约冻结（1.10.0）、合成数据（Seed 1.5.0）、9 个确定性服务、A0–A5 接线、
  学生/校方双门户前端（浏览器双语实测）、Moodle 沙箱（GCE + MCP 只读链）、评测 Harness。
- **eval：13/13 BLOCKER · 11/12 TARGET（T11 75% 如实红）· BL1–BL5 全产出**，判定类指标双跑逐字节一致。
- 四轮用户功能优化（U1–U8、二轮 A–O、三轮 A–Q、四轮 A–M）全部落地并同步进 Spec（v4.1.4）与 Plan。
- **clay 重构（2026-08-01 已并入 main 并上线）**：全站 UI 重构（Claymorphism × Claude 暖色，
  设计令牌 v2 + 三道 UI 门禁）+ 十余项用户裁定的功能升级（契约 1.19.0→1.22.0：Advisor 一小时时段与注册 CRUD、
  校方审核页/广场总览与批准后生命周期管理、学生报名/加入日历状态持久化等）。
- 余下：WP11 演示彩排与录屏；backlog 与待用户确认项见 [PROGRESS.md](PROGRESS.md) 收口段。
- 逐日时间线不在本文件维护——见 [PROGRESS.md](PROGRESS.md) 的「已完成」表。

## pack-sources-intl 批（2026-08-02 已验收并入 main 并上线，契约 1.22.0→1.28.0）

用户 A/B/C 三提案 + 增补 A–H + D/E/F 批全部落地：官方源注册表与真实抓取回路
（92 源、变更检测、官方白名单直发广场、政策更新提醒卡、每日云端巡检）；International Student
Context Pack 安装（vendored 确定性求值、Rules 签发凭据、档案页唯一勾选入口、拆解「国际生准备」列、
`.intl-note` 注记、证件到期提醒——**待政策复核状态如实标注**）；求职拆解市场证据化（两岗位 JD 语料
→ core 权重加粗、权威榜单 36 条可点链接、未命中岗位的「现场 AI 拆解」后台任务+进度条）；
四维匿名评分与逐场统计（60 天冻结归档）+ 签到二维码全链（HMAC token）+ 质量报告页（admin-only，
实时生成带进度）；日历睡眠块与睡眠统计；顶栏 Agent 运行时开关；
「我现在大几」学期选择器；planner「本学期已选课程」折叠面板（与日历课表块同源）。
独立审查 20 条意见全部处置（采纳 17）。合并 commit `c6f2963`。
