# CampusPath 进度审计

> 由 Claude 自主维护，**按需读取，不占每轮上下文**。
>
> 三份文件的分工，别互相抄：
> · `memory/`（任何目录都加载）→ 只放"不在项目目录时也必须知道"的，即赠金与 Vertex-only
> · `CLAUDE.md`（项目目录内加载）→ 约束本身，以它为准
> · **本文件**（按需读取）→ 会变的东西：进度、断点、决策时间线、待确认项
>
> 规则：**只记已验证的事实**——写"完成"必须附验证方式；未验证的写"待验证"。

最后更新：2026-07-31

---

## 当前状态

**阶段**：M3 进行中。**架构不可动摇的六条里，"零 LLM"那两条已经有实物**：
Rules & Constraint Engine、Capacity & Calendar Service、Wellbeing Reminder Composer 三个模块全部完成且各自受三层零 LLM 扫描强制。
**Vertex 已接通并实测**：ADC 就位，preflight 确认项目挂在赠金账号 `BILLING-ACCOUNT-REDACTED` 上，实跑一次 `VERTEX_OK`（32 token，`traffic_type=ON_DEMAND`）。`/matches` 是第一条真实端到端链路。
**用户追加的 8 条功能优化（U1–U8）全部完成**，含一次硬约束修改：日历采集改为两级授权（B5 从"详情=0"改为"超出授权层级的采集=0"，架构第 3 条不动）。
**2026-07-31 第二轮收口**：用户 A–O 15 项全部完成（Resume 上传解析、反思多维评分、
5 专业真实课程要求入沙箱并上选课页、三个人群拆解 Pack、报名按钮、推荐缓存+限次刷新、
收藏可取消+加入行程指引、日历直接编辑+重排确认、Advisor 双端纵切、主办方八大类、
导航整合（方向+计划、日历+身心、时间线+行动中心）、反思搜索、行动详情+备考提前量）。
eval：**13/13 BLOCKER · 11/12 TARGET · BL1–BL5**。第一轮收口内容见下表 07-31 各行。
**2026-07-31 第三轮收口**：用户 A–R 十八项全部完成（身份隔离、同意自助授权、课外活动
规划、三层归类与证据链、活动闭环、日历即编辑器+作息、档案分区、选课三分区、Advisor
时段库存与违约规则、3 份合成学生档案、全流程模拟评估报告）。契约 1.2.0→**1.6.0**，
api 测试 120，`make check` 全绿。评估报告 `docs/full-journey-review-2026-07-31.md`
（**结论未经用户同意不改代码**）。
**余下 backlog（08-03 双报障批审查记待办 4 项，opus 审查 4M8L 处置：采纳 8 / 记待办 4 / 不采纳 0）**：M-3 前端「近两周」锚点（最早活动日）与服务端 `_bucket`（deps.today）不同源——统一需 API 下发 as_of 且演示时钟语义是用户裁定过的，动它单独批；L-3 A5 失败负缓存对瞬时故障（配额抖动）也锁一天——可分级 TTL；L-6 强度选择 context 化（现依赖 PlanHub 卸载重挂语义）；L-7 会话水合前首帧以 STU-A 预取一轮。
**余下 backlog**：R 报告 P1×2（反思对象缺新报名活动；ISOM/IEDA 培养要求无公开 PDF）与 P2×3（课程语义点评、For You 冷启动提示、日历拖拽）——**待用户过目报告后决定**；本轮改动的独立审查（codex/subagent review）待跑；T12 subject 级标签；MoodleEducationAdapter 挂进 A2 工具带；
T11 75%（自评口径，如实红）；R8 人工复核（需用户）；D6.7 加权（需用户）；
personal_interest / exploration 两个拆解 Pack（demo 范围外）；导航 i18n 的
"方向"组标签可考虑改为"方向与计划"（文案级）。

已就绪的地基：preflight 自检（14 项）、pre-commit 密钥拦截、验收标准已量化（D6 的 13+12+5 项）、**契约层冻结（110 模型 / 29 端点 / 前端类型同源，168 项测试）**、**Synthetic Campus 数据集（12 学生 / 143 机会 / Gold Set 四态各 15 条 / 16 类失败样本，16 项一致性检查 + 16 个变异自检）**。
**阻塞**：无。`make check` 一条命令跑通 preflight + 契约产物一致性 + Seed 一致性 + 全量测试。

---

## 已完成

| 日期 | 事项 | 验证方式 | commit |
|---|---|---|---|
| 08-04 | **校方广场反馈呈现重做（用户裁定，Spec v4.1.26，契约 1.34.0→1.35.0）**：不再拼一行计数——① 契约新增 FitShare/汇总行 fit_distribution（契合五标签在已验证反馈中的占比；§17.4 个人判断不折进质量分：独立字段+前端独立分区标注"非质量分"；k-匿名阈值 validator 双保险）② 逐维分中文标签上屏（内容深度/实用收获/组织流程/预期兑现/人脉价值，CI 收 title）③ Insufficient 带阈值解释文案 | TDD 先红（KeyError fit_distribution）后绿（份额和≈1、阈值下必须为空）；api 293 + contracts 307 全绿；浏览器实测校方端：逐维中文分"内容深度 4.1…"、契合分布"对我太难 38%…"、199 个 Insufficient 全带解释、零裸枚举；EN 同过（截图 light-only/09–10） | 见本行 commit |
| 08-04 | **校方广场四维统计位常驻（用户报障，Spec v4.1.25）**：quality-summary 曾跳过零反馈零签到活动 → 新实例上校方广场统计区整块蒸发像功能不存在；删跳过逻辑，每条活动常驻统计行（0 如实 + Insufficient）；k-匿名 MIN_CELL_N=5 出分口径不变 | TDD 先红（173 条无统计行）后绿；api 292 全绿；浏览器实测校方端：205 行统计区常驻、199 行如实 Insufficient、6 个种子反馈活动照常出分（截图 light-only/08） | 见本行 commit |
| 08-04 | **验收通过 → 十 commit 批统一上线 + GitHub 快照**：web `00019-269` → api `00013-hqr`（双向契约变更按口径两步发，中间各自验证）→ Job 镜像同源重发并实跑重灌；快照单 commit `1251ce1` 覆盖推送（排除口径同前 + 新增口令词扫描；金丝雀先响、正扫零命中；作者 noreply 邮箱）；`evaluation-criteria-answers` 按"给评委看"用途首次纳入快照（扫描零命中） | 线上实测：门 307/口令 200/发出 HTML 零深色残留；自述学期 422 结构性拒收；VGA 冷启动 0→线上反思后 total 1/month 1；pathway `trigger=a5:` + 学期码 2026-27_FALL；demo 简历两文件 200；catalog 重灌 233（15 政策卡+44 实采） | 见本行 |
| 08-04 | **拆解取证来源溢出修复（用户报障，Spec v4.1.24）**：现场拆解的接地跳转 URL（数百字符）整段直出溢出卡片 → 改紧凑药丸（`evidenceSourceParts` 解析生产端固定格式「公司 · 岗位」+URL，URL 只进 href；无 URL 取证作纯文本药丸；跳转域注脚保留）。**顺带修 pages-must 门禁设计缺陷**：「外联同意默认关闭」曾是浏览器状态断言，用户合法授权一次即永久误报（实发追根：授权 POST 来自用户本人会话）——改控件在场断言 + 不变量移到 fresh seed 全学生遍历单测；坑入 §10.2 | 已知溢出样例（415 字符 URL×12，puppeteer 拦截注入）断言：12 药丸链接 href 保真、可见文本零裸 URL、零卡片溢出、EN 态同过（截图 light-only/06–07）；不变量测试加料样例证明会响；api 291 全绿；三门禁全绿（14/0+14/0+43/0）；现场拆解真跑一轮如实失败（接地无可用 JD，限次耗尽）故走注入路——如实记录 | 见本行 commit |
| 08-04 | **北极星指标 VGA 落地学生端（用户指令，plan 模式批准，Spec v4.1.23，契约 1.33.0→1.34.0）**：生产者=反思闭环（反思 OPP→铸 EV-REFL 证据+同步铸 `ActionEvent(verified_growth=True)`，幂等、契约校验器强制挂证据；点击/收藏/报名恒 false=「不奖励忙碌」）；新增 VgaSummary/VgaMonthPoint 契约与 `GET /vga-summary`（RBAC 路由表注册，纯派生逐月分桶，0 如实 200）；成长动态跟踪页北极星卡——金黄质感星星（用户看图裁定径向渐变 #ffedb3→#f0b545）+本月数+累计+逐月柱+行动清单带证据回溯 | TDD 5 例先红后绿（铸事件挂证据/同反思重交只计一次/课程反思不计/跨月分桶/0=200 空桶）；make check exit 0；api 290 + contracts 307 全绿（实测）；浏览器 E2E：卡片 0 基线→报名→写反思→**本月 0→1**、清单+1 行、EN 态、金黄渐变三停断言；三门禁全绿；截图 light-only/04–05 | 见本行 commit |
| 08-04 | **demo 学生简历一键注入（用户需求，Spec v4.1.22）**：public/ 分发两份模板合规合成简历（小红帽=市场营销、大灰狼=机械工程，全部标注 Synthetic/Demo）；上传区上方两行 mist 蓝文字链（用户两轮裁定：文案按原话「demo student … 的简历一键注入文档上传」、样式不做按钮做文字链），点击 fetch 内置文件走同一 uploadResume 链路 | TDD：解析质量测试先红（文件不存在）后绿（多小节覆盖/org+role 成对/零 ** 残渣/零占位符），resume 套件 11 绿；浏览器 E2E：点小红帽→提议出现→批准→**不刷新**切总览内容立即可见；大灰狼上传 done；链样式断言（#31606f/下划线/逐行/非 btn）；EN 标签；截图 actions-near-cache/09–11 | 见本行 commit |
| 08-04 | **档案批准后总览不更新（用户报障）**：批准提议只 `proposals.reload()`，而物化写进 experiences/extras/profile 三处、总览/提议是同页切分页不重挂载 → 总览停在批准前快照（服务端数据实为已落：用户批准的 22 经历+extras 全在）；批准回调补三处 reload | 浏览器全程重放用户路径：上传合规探针简历→提议分页批准→**不刷新**切总览→探针实习+证书立即可见（before=false→after=true，截图 actions-near-cache/08）；tsc 0 | 见本行 commit |
| 08-03 | **深色模式禁用（用户裁定，plan 模式批准后执行，Spec v4.1.21）**：globals.css 两个暗色块、ThemeProvider/useTheme、顶栏+设置页切换器、首帧脚本主题分支、chrome.theme.* 4 键全删；color-scheme 锁 light；对比度门禁改 43 组合单主题 + 新增「暗色块复活即红」断言（H5 自检保留）；残留 localStorage 键无人读取即无效（不写迁移） | Harness 三证：坏样例 fg=bg 门禁 exit 1、暗色块复活断言 exit 1、还原后 43 组合 0 失败 exit 0（首验时又踩了一次「管道 `$?` 恒为 0」的老坑，当场发现并改为无管道取码复验——§10.2 第二行的坑，警钟长鸣）；tsc 0；浏览器实测：OS 深色仿真+预置 dark 键下 body 仍 `rgb(250,249,245)`、data-theme=null、无 [data-theme-select]、设置页零主题文案（简/EN 各一遍，截图 light-only/×3）；三门禁全绿；smoke 21 绿 | 见本行 commit |
| 08-03 | **自述学期通道全撤（用户裁定，Spec v4.1.20，契约 1.32.0→1.33.0）**：三处学期设置统一到教务学期码——契约删 ProfileSelfEdit/StudentProfile 的 current_term 与 CurrentTerm Literal（extra=forbid 结构性拒收，年级码撞名 500 永不复发）；目标工作室「我现在的学期」选择器删（国际生引导保留）；选修课页学期下拉删、改教务侧派生徽标（year2×2026-27_FALL→大二上）+「全部要求」常驻；12 个孤儿 i18n 键清理 | TDD：拒收测试先红（200→422）后绿；api 283 + contracts 307 全绿；make check exit 0；i18n:hant 再生 965 键；浏览器实测：goals 无 [data-current-term]、planner 无 [data-term-select]、派生徽标「大二上 2026-27_FALL」/EN「Y2 Fall」、要求组 3 组常驻；三门禁全绿；截图 actions-near-cache/05–07 | 见本行 commit |
| 08-03 | **用户双报障修复批（Spec v4.1.19）**：① `GET /pathway` 500——`StudentProfile.current_term`（y1s2 年级码）被 A5 当教务 TermCode 用，目标工作室选过年级即整页炸，且异常不进负缓存每刷一次白烧 8–17s Vertex；改取 `deps.current_term` + `build_a5_pathway` 异常护栏（回落夹具+当日负缓存）② 行动中心「近两周」筛 `in_progress`（夹具私约）致 A5 数据下恒空、与规划页矛盾；改共用 `plan-window.ts` 单一口径 + 补读 storedIntensity 强度同源 ③ For You 切页重等骨架；`useResource` 增 cacheKey 会话缓存（SWR：命中即渲染、后台核新、错误不吞） | TDD 2 例先红后绿（y1s2 复现精确到线上同款 traceback；异常负缓存断言只调一次）；api 283 全绿；本地 E2E：y1s2→pathway 200 trigger=a5:、二读 12ms；浏览器实测：行动中心近两周 7 条=规划页 7 条（修中途抓到强度不同源 5≠7）、For You 切回 65ms 满屏零骨架、EN 态 7 条；三门禁全绿（14 页 must/14 页对齐/86 对比组合）；截图 actions-near-cache/ 4 张 | 见本行 commit |
| 08-03 | **状态灯/强度/垃圾桶整批上线**：api `00012-chq` + web `00017-cbl`；巡检 Job 重灌 catalog 236；引擎按用户指令持续运行 | 线上实测：三档 `低 7活动/近3/课2 → 均衡 10/4/3 → 进取 12/5/4`（近两周受真实供给限制未顶满上限，如实）；状态灯云端 REST 探测 state=running 两运行时；门 307 完好 | 见本行 |
| 08-03 | **强度全量分档（用户实测抓包 8/8/8 + 二轮裁定 3/5/7）**：三档从「只动课程门数」改全量口径——课程 2/3/4 门、活动池 8/10/12、**近两周活动数上限 3/5/7（天花板，受真实供给限制）**、近两周时长预算 20/30/45h（11h/日模型折算）；假绿教训一枚（加料测试没进分数前列、断言碰巧过——改全量拍近两周+精确等值断言才见真红） | TDD 先假绿→真红→绿；api 281 全绿；**浏览器实证 近两周 3→5→7、总活动 7→10→12**（live-eval/21，note 门数变化作为档位到位信号）；三门禁全绿 | 见本行 commit |
| 08-03 | **「不参加」垃圾桶 + 强度选择器复裁定样式（用户需求，契约新增 DELETE /pathway/items/{id}）**：活动条目右下角垃圾桶（仅机会类）二段确认删除——服务端一次四件事（版本剔除+里程碑引用清理、DECLINE 审计事件、日历真实块收走、拒绝名单防复活【A5 与夹具双路过滤】），RBAC 经契约路由表注册；强度选择器由 Segmented 改 mist 标签药丸（用户裁定：不得与导航分段控件混淆） | TDD 3 例先红后绿（删除四联动/重生成不复活/未知 404，中途真红抓到 RBAC 未注册与块 source 枚举两处）；api 280 全绿；浏览器实测：选中药丸 mist 底色、8 垃圾桶、二段确认→DELETE 200→条目 8→7（live-eval/20）；三门禁全绿 | 见本行 commit |
| 08-03 | **状态灯 + 三档强度选择器（用户需求，Spec v4.1.18）**：顶栏 Agent Runtime 实时灯（绿呼吸=运行中计费、灰=停止；云端探测新增 Vertex REST 回退——容器 ADC 直查 ReasoningEngine 列表，unknown 仅双路皆盲时出现；状态缓存改 stale-while-revalidate 单飞后台刷新，慢探测不再拖垮顶栏）；课外规划页三档强度 Segmented（轻2/均衡3/进取4 门，`?intensity=` 驱动 S1 变体选档上屏，trigger 指纹带档位同档缓存换档重生成，本地持久化）；引擎按用户指令**保持常驻运行**（关停等指令） | TDD：REST 回退 H5 三向（有名单→running/空→stopped/抛错→unknown）+ 强度三档门数与缓存测试先红后绿；api 276 全绿；浏览器实测灯绿「Agent Runtime 运行中」+ Segmented 控件（live-eval/19）；三门禁+make check 见本行收尾 | 见本行 commit |
| 08-03 | **评测修复批上线**：api `00011-g6r` + web `00016-wwz` 重发（无契约变更）；巡检 Job 实跑重灌 catalog 236（15 政策卡 + 47 OPP-LIVE）；口令门与 no-store 头保持完好 | 线上探针：设目标A→matches 200 建缓存→换目标B 200→matches 重建 200、无任务研究状态 404、门 307→/login、login 头 private,no-store | 见本行 |
| 08-03 | **评测 Bug-1/2 + 三条 UI 打磨修复（用户批准）**：统一「目标变更失效」口径——研究任务记录发起时目标名、改名即 stale（状态 404、拆解不再混入旧岗位实采，同名重存保留复用）；`set_goal` 目标名变更时清空选修推荐与 matches 当日缓存；拆解区加载骨架取代空窗；课外规划 lead 加演示时钟注脚（快照日 2026-09-15，三语）；行动中心国际生横幅加标题 | TDD：3 例先红后绿（含同名重存反例）；api 273 全绿；make check exit 0；三门禁全绿；浏览器实测演示时钟注脚上屏（live-eval/18） | 见本行 commit |
| 08-03 | **双人设线上全链路评测（用户指令，引擎跑完即删）**：全新国际生人设（机器人向）+ 全新常规生人设（PM+数据记者）在线上各走完整旅程；口令门 UI 真实过门（错口令不泄露）；模板简历七类上屏；「机器人工程师」零劫持 + 现场实采 7/8 家（取证含小米具身智能真实在招岗）；「数据记者」实采 6 家；For You 3/10 签证敏感卡差异化注记；恢复链线上全环（403→刷新仍在→授权重试→200）；周统计两页一致 + 标签；反思闭环提议生成；A0 确定性路由 model_used=false、A4 伪 SYSTEM 注入恒 draft；EN 零残留。**新发现 2 个同族中危 bug（报告结论未经用户同意不改代码）**：改目标后 ①旧现场研究结果顶替新目标编制画像（research job 无目标指纹）②选修推荐日缓存不失效（理由仍提旧目标）——建议统一「目标指纹失效」修法；另 3 条轻度 UI 观察。报告 `docs/live-dual-persona-eval-2026-08-03.md`（不进 GitHub 快照）；引擎全部跑完后删除（status 零运行时） | 17 张截图 docs/verification/live-eval/；关键断言全为浏览器网络实录与 API 交叉验证（正文逐处注状态码/家数/条数） | 见本行 commit |
| 08-02 | **白屏事故修复（口令门上线后 40 分钟内）**：用户实报 /login 空白——根因 Next 预渲染 HTML 的 `s-maxage=31536000` 被 Google 门的 307 遮蔽多时，门一撤缓存节点即发旧部署 HTML（chunk 已不存在）；middleware 给全部页面响应统一 `Cache-Control: private, no-store`（_next/ 静态资源不经 middleware，内容哈希长缓存不变）；web 重发 `00015-f99`；坑入 Plan §10.2（撤层要审视其遮蔽的行为） | curl 实测：/login 头变 `private, no-store`；门行为回归（无 cookie 307→/login、对口令 cookie 后 200） | 见本行 commit |
| 08-02 | **访问口令门取代 Google 邮箱白名单（用户裁定）**：站内演示口令与外层 Google 门合并为一道**口令门**——口令只存 `CAMPUSPATH_DEMO_PASSCODE` 环境变量（Cloud Run env / 本地 .env，代码·快照·界面零出现，界面文案只写「请输入团队提供的访问口令」）；服务端 `/api/auth/passcode` 恒时比对 + HMAC httpOnly cookie（30 天），middleware 全站过门（页面 307→/login、反代 API 401）；学生端与校方四岗位入口共用；本地不设变量门自动不存在（验证脚本/三门禁不受影响）；删除 OAuth 回调路由与 OAUTH_CLIENT_ID/OAUTH_CLIENT_SECRET/TEAM_EMAILS 三个环境变量；web 重发 `00014-7ck` | 线上 curl 全链实测：无 cookie 页面 307→/login（不再去 Google）、登录页 200、无 cookie 反代 401、错口令 401、对口令 200+cookie 签发、带 cookie 页面 200 + 反代真数据返回 | 见本行 commit |
| 08-02 | **审计修复批验收通过 → 合并上线 + GitHub 快照**：`fix/audit-round` ff 并入 main（`2cdf633`）；云端按**新部署次序**（本批含请求体枚举扩容 → 先 api 后 web）重发：api `00010-4r8` → web `00013-k84` → Job 镜像同源重发 → 巡检 Job 实跑重灌；GitHub 过滤快照力推 `307cbdd`（排除口径同前：reference/、docs/verification/、docs/plans/、五份评审审计报告、根 CLAUDE.md；计费账号 ID 脱敏；金丝雀先证明扫描会响、正扫唯一命中为 pre-commit 检查器自身的检测正则=已知误报类，判定 CLEAN）；**Agent Engine 保持零运行时**（用户指令确认关闭，status 实测「没有已部署的运行时」） | 合并后 make smoke 21 绿；线上探针：自由文本简历 → 422 `resume_not_in_template`（新代码身份）、matches 带 `goal_role`（candidate/primary）、**pathway `trigger=a5:…` + balanced 课程计划 = A5 类本体云端真跑**、catalog 重灌 236（15 政策卡 + 47 OPP-LIVE）、web 门 307→Google | 见本行 |
| 08-02 | **审计修复批·独立审查处置 + 两项追加需求（同分支）**：opus 独立审查 18 条全处置——**采纳并改 15**：H1 fit 词表改用 FitTag 枚举本体（原词表与真实取值零交集=死代码，测试与实现共用错误假设——枚举全扫钉死）；H2 质量分阈值改共用 MIN_CELL_N=5（不再开 n=3 匿名旁路）+ 第六维 0.1 档粗化防联立还原；H3 pathway 失败负缓存（同指纹当日不重试）+ matches 日缓存回写（不再每次 GET 烧模型）；H4 模板占位符/括注过滤（原样模板零产出）；M5 每类 50 条上限；M6 自述证书改落 extras.certificates（不再伪造 Vault 引用、编号入 note）；M7 changed_fields 按实际 entity_type 派生；M8 周一对齐改本地日期（UTC+ 时区不再前移一天）；M9 修复循环单轮砍足预算；M10 B8 闸门 try/except+日志回落；M12 个人负修正移至加权和层（零重叠也真压分）；L14 EXP_CATEGORY 补全枚举；L15 文件类型文案对齐 .md；L16 完整 ISO 日期+空格连字符分隔；L17 小节正则收紧行首 `## `；**部分采纳 1**：M11 中性词表补行业/载体修饰（互联网/嵌入式等召回恢复，游戏类领域修饰仍阻断，附回归测试）；**记待办 2**：M13 改期路径块缺失+恢复卡 dismiss、L18 睡眠块判定改语义字段。README 部署次序改为按变更方向双向口径（请求体枚举扩容→**先 api 后 web**）。**追加需求**：① 选修课推荐页无学期计划的专业按 (专业,学期) 确定性抽 7 门必修作 Demo 参考+数据边界备注；② 查证 STU-B（ISOM 必修仅 4 门）/STU-C（IEDA 无学期计划）呈现单薄属实 → 登录入口只留 STU-A（种子与会话校验保留全集） | api 270 + agents 76 全绿（H1 枚举全扫/M12 零重叠/H4 原样模板/M11 召回 新增红转绿）；make check exit 0；三门禁复跑全绿；浏览器：登录仅 STU-A、IEDA Y2_FALL 抽样 7 门+备注、同学期两次进入结果逐门一致（确定性）（audit-fixes/07、08） | 见本行 commit |
| 08-02 | **审计修复批（分支 `fix/audit-round`，用户 A–G 指令，契约 1.31.0→1.32.0，Seed 1.9.0，Spec v4.1.17）**：**A** 预警规则逐行核对（两级窗口/量表出口/高压分流与用户口径一致；初级分流 PSS≥14 差异呈报）；**D** Resume 模板化（`resume_template.py` 零模型解析器全面取代模型提炼，教育/证书/语言/荣誉物化通道 + extras 去重并入，模板文件随站点分发，非模板 422）；**E** A5 类本体接线（`a5_pathway.py`：build_pathway 修复循环 + generate_course_plans 三变体 + 记忆 advisory 输入；trigger 带目标指纹换目标重生成；已批准项跨版本携带；失败回落夹具如实标注）；**F** 周统计口径统一（身心页锚睡眠周+范围标签、日历页注脚明示显示周）；**G** 审计红 4 黄 8 蓝 1 全处置（前缀守卫防子串劫持+画像命中也开现场拆解入口+live 取代编制、写入 403 持久恢复区、已加入日历标记读写入真值、质量聚合分+个人 fit 修正入六维、goal_role 徽章、档案经历入证据链、保存缺项提示、跳转域注脚、种子+3 游戏活动、其他经历兜底分区）；报告追加处置附录 | TDD 全程（新增 api 17 测/agents 6 测先红后绿）：api 266 + agents 74 + rules/packs/connector 全绿；make check exit 0；三门禁全绿；浏览器实测（audit-fixes/ 5 张）：模板简历七区全链、403→刷新→恢复区→授权重试→200 全网络实录、goal_role 徽章 10/10 主副皆有、身心页统计周标签；**本地真 Vertex 实证 trigger=a5: + balanced 课程计划 + 逐条模型取舍理由**；新坑 2 条入 §10.2（env 装载、回落态正向断言） | 见本行 commit |
| 08-02 | **P4 普通学生全流程线上审计（新人设/新简历/新目标）+ P5 引擎删除**：审计对象=线上 Cloud Run（web 00010-46w / api 00009-qr2）；全新虚构人设「陈思远」（28 条目新简历 + 新目标「游戏开发工程师」）真实浏览器走完 15 步全环（登录→上传→裁决→目标→报名→批准→授权→日历真实块→作息→反思→证据→成长跟踪→闭环提议→接受→EN）；产出报告 `docs/full-journey-audit-2026-08-02.md`（**结论未经用户同意不改代码**）。核心发现：红 4（物化经历 type=other 总览永不可见；「游戏开发工程师」子串误命中 SWE 画像且现场拆解入口被挡；批准→日历写入 403 静默无引导；「已加入日历」标记在写入失败时照亮）+ 黄 8（A1 十行上限两类词表、两页周统计矛盾、纯睡眠<5h 不触发预警【模型要求学习>11h 同时成立，待拍板】、59% 平顶依旧等）。老测评六项对照：A2 原因/A3 归档已修，A1 半修（1/24→10 条但截断+展示断点），A4 中文伪 JSON 注入免疫，A5 类本体+平顶未修，A0 兜底证据补齐（意图分类本身是模型判断）。审计完成后两 Agent Engine 立即删除（status 确认零运行时） | 32 张截图 + 4 份探针原始 JSON 存 docs/verification/full-journey/；关键断言全部来自浏览器 response 实录与 API 交叉验证（正文逐处注状态码）；引擎删除后 status 实测「没有已部署的运行时」 | 见本行 commit |
| 08-02 | **验收通过 → 合并上线 + GitHub 快照更新**：`fix/intl-chain`（10 commits，契约 1.28.0→1.31.0，Spec v4.1.12→v4.1.16）ff 并入 main（`d27240f`）；过滤快照力推 github.com/AriaYD/yqywfrmhpy-test（单 commit `7eb979d`，排除 reference/、docs/verification/、docs/plans/、全部评审与审计报告、根 CLAUDE.md；**赠金计费账号 ID 本次新增脱敏为占位符**；敏感扫描 H5 canary 先证明会响，正扫 CLEAN、用户名零出现）；Cloud Run 重发 web `00010-46w` + api `00009-qr2` + Job 镜像同步（发布次序按契约口径 web→api）。**发现并修部署坑**：`cp -r` 目标目录已存在时拷成嵌套子目录 → 云构建吃旧 d.ts 类型报错构建失败（README 口径已改为先 rm） | 合并后 `make smoke` 21 绿；线上实测：巡检 Job 实跑后 catalog 235（15 政策卡含新 IANG 繁中源、46 真实活动）、matches 带 intl_notes、escalation 带 qualifying 字段、web 门 307→Google；**云端真流水线实跑：UI/UX 实采 6 家在招 JD（2 跳过），core 4/6 覆盖带实时采集注** | 见本行 commit |
| 08-02 | **现场拆解结果复用 + 显式重跑覆盖（同分支，用户补充裁定）**：已有实采结果自动持续并入拆解视图（含前端本地缓存）；「AI 现场拆解」按钮**不再隐藏**——已有结果时变为「重新现场拆解（覆盖当前结果）」并注明复用中，点按即忠实重新采集分析并整体替换旧结果（每日限次不变） | TDD：重跑覆盖测试（旧 OldCo 结果→重跑 NewCo→旧条目消失不叠加）；研究套件 6/6；浏览器实证：真跑一轮（实采 5 家）后按钮态/复用提示/12 条实采注记齐现（截图 live-pipeline/05） | 见本行 commit |
| 08-02 | **现场拆解重建为真流水线（同分支，Spec v4.1.16）**：用户裁定后重写——接地搜索真实在招 JD（VertexModel 新增 google_search 接地调用）→ 服务端逐条真抓原文+模型逐行拆解（词表从编译器同源导入；JS 壳页走接地抽取回退并回报实际引用 URL；词表外别名确定性归一）→ 零模型加权合成（覆盖率≥60% core、market_note 实采计数、来源带 URL）；进度=真实阶段；完成语如实报实采/跳过数；前端「现场实采」标签区分编制期、ai_live 徽章加成因说明；命中编制库不叠加现场残留。中途实测两轮失败驱动两次修复（0/8 全败→接地回退；1/7 低产→提示词"词表同上"空引用 bug+别名归一）。**撤销**预编译 UI/UX 绕行（8 家人工语料降级为对照基线留存）。附带抓到 uvicorn --reload worker pkill 杀不净老进程占 8000 的坑 | TDD：流水线桩测 5 例（含壳页接地回退+SOURCE URL 替换、实采计数、core 判据、诚实跳过）先红后绿；agents+api 全量回归；**浏览器真流水线全程**：真实点击按钮→进度条走真实阶段（检索 8%→逐家抓取 45%→完成）→9 条目全带「2 家在招 JD 中 N 家要求（实时采集）」+字节跳动/阿里真实在招 JD 链接（截图 docs/verification/live-pipeline/ 4 张） | 见本行 commit |
| 08-02 | **日历-规划贯通二批 + 行程详情（同分支，Spec v4.1.15）**：首日凌晨睡眠块补齐（作息从周期前一晚起铺）；机会类计划项改用活动真实起止（修「未来两周标签 vs 日历」两视图矛盾）；周分页改真实连续日历周（周一对齐、空日占位，锚点跳过纯前夜睡眠日）；规划投影多日切段+同日合并（标题 +N）；行程详情只读面板（标题/时间/类型/官方链接/简介，编辑入口后移）；POST agent-runtime 测试环境硬拒。**事故记录：两个 Vertex 引擎 14:26 UTC 被未知路径重建（本地 API 零 POST、测试 body 均 422、审计日志无果）——已再次删除止血 + pytest 护栏，成因列待查** | TDD：作息前夜块/夹具真实日期两测先行；api 全量回归；**verify-plan-to-calendar.mjs 浏览器实测 8/8**：含行动中心真实点击批准→活动真实块落日历（截图 7 张 docs/verification/plan-to-calendar/，05 号为滚动到块的实景、07 号为合并规划块详情展开 5 活动带官方链接）；三门禁复跑 | 见本行 commit |
| 08-02 | **「睡眠-负荷平衡」预警与容量口径（同分支，契约 1.30.0→1.31.0，Spec v4.1.14）**：用户裁定的计数模型取代连续 streak——合格日=有效睡眠<7h 且学习工作(忙+课程)>11h；14 天 ≥10 → 温和弹窗（可关、按计数记忆）；28 天 ≥20 → 量表弹窗（唯一出口去填 ISI+PSS-10，完成 last_assessment_at 落档自动解除，分流走既有 §16.8 链）；理论口径（ATUS 3.5h 生理成本/WHO-ILO 55h/Scarcity 缓冲）注入 Spec 与界面注脚，标注非医疗建议。容量展示换周合计五项（睡眠/课程/忙/剩余可支配=168−六类−24.5h/缓冲），日历「已安排」条撤下；身心容量页容量超载卡替换为五项+已安排率条((忙+课程)/66)。全链零 LLM 红线不动 | TDD 5 例（9/14 不触发反例、10/14 warning、20/28 assessment、量表落档、睡够不计入反例）先行全绿；api 244 全绿；**verify-balance-round.mjs 浏览器实测 9/9**（弹窗两级真实渲染/关闭/解除，截图 docs/verification/balance-round/ 4 张）；三门禁复跑 | 见本行 commit |
| 08-02 | **验收反馈五批修复（同分支 fix/intl-chain，契约 1.29.0→1.30.0，Spec v4.1.13）**：**①** 成长曲线口径化（证据=EvidenceRecord.obtained_at 落期实数；已关闭差距/目标信心两个无依据指标从 UI 撤下，目标卡信心条同撤；口径说明上屏）；**②** 日历-规划贯通（课程块独立色+图例、规划中活动虚线投影、保护色改黄 --hatch、行动中心非阻断冲突显式警示+可仍批准+⚠️ 持久标记进 pathway 与日历块）；**③** console 每源状态灯 + 一键刷新（SourcesSweepJob 后台任务、单例 409、与逐源刷新共用核心）；**④** 档案提议确认三修（无 period 经历 500、技能无写回、多经历共 id）；**⑤** 主/副目标推荐配比（candidate_goal_share 默认 0.2，goals 页 10–50% 可调；For You 前缀成比例交织、选修加权+保底）；**⑥** 国际生官方指引问答表（packs/official_answers.json 7 组 + IANG 繁中源注册为第 93 源；计划项 assumptions 带官方链接、广场政策卡二级回退、界面「国际生提前准备事项」替代「规则生成」复读）；广场卡活动时间+发布时间+最新在前 | TDD：提案修复先红后绿（500→200）；api 239 + rules 98 + packs 36 + connector 48 全绿；三门禁全绿；**浏览器实测脚本 verify-feedback-round.mjs 16/16 断言全绿**（截图 docs/verification/feedback-round/ 7 张：含点击批准后 ⚠️ 实测、确认提议 200+Kotlin 落标签池）；本地一键巡检真实跑（85 源） | 见本行 commit |
| 08-02 | **codex 审查（fix/intl-chain，14 条）处置**：**采纳并改 11**——高2全修（#2 注入凭据 subject_id 前缀学生 id，防跨生复用，附反例断言；#6 确定性 id 的 context 纳入 pack digest，档案变更/Pack 修订不再撞旧凭据 500，附 digest 变更回归）+ 中（#3 intl 勾选/取消/consent 开关即时作废当日推荐缓存；#4「未标注」警示独立于担保/语言注记且恒排第一；#5 逾期锚点显式标注不改写；#7 console 在架数只数现行在架；#10/#11/#12/#14 测试补强：日期语义断言、runtime 三态含失败脚本 H5 双向、跨学生/跨修订签发、未标受众收敛默认）+ 低（#9 空态不叠加失败态）；**部分采纳 2**——#1 契约新增枚举时先发 web 后发 api（README 部署口径）+ 前端 `?? []` 部署窗口守卫、#13 断言行使计数；**记待办 1**——#8 横幅与规划同源校验（TODO 注释）。另发现并修**存量假红**：审查 #18 改名 llm-free 测试后 Makefile 目标仍指旧名，`make check` 自那批起一直红而未被发现（管道吞退出码 + 收尾未重跑）——目标改通配 `test_llm_free*.py`，坑记 Plan §10.2 | 修复后 api 229 + rules 98 全绿；make check exit 0（对照实验证实基线红）；pages-must 复跑 14 页 0 失败；tsc 零错 | 见本行 commit |
| 08-02 | **国际生链路审计 + 修复批（分支 `fix/intl-chain`，契约 1.28.0→1.29.0，待用户验收后合并）**：P1 线上审计（Agent Engine start 路径首验成功×2 运行时；云端以国际生人设全链实测）产出 `docs/intl-chain-audit-2026-08-02.md`——五 bug 全部定位到代码级根因（推荐引擎零调用 Pack、规划零注入、政策卡挥发+chip 数据驱动、policy 枚举死值、console 无链接）；P2 修复：**①** `MatchResult.intl_notes` 服务端逐机会派生（三态字段+提前量对齐该机会开始日，讲座类无字段不硬贴）取代前端复读 `preparation_actions[0]`；**②** Pack 准备/核实/约束动作 → `PlanItem(kind=action)` 读时注入规划四档（`issue_prep_item_validation` Rules 真签发、B8 对齐、不落缓存），行动中心横幅带目标日+官方链接；**③** registry `policy_audience` → 政策卡 policy/intl_policy 双分类，广场两 chip 恒显+空态文案；**④** console 每源 URL 链接/上次抽出/在架条目数；**⑤** 日历图例补睡眠；另修运行时探测失败冒充 stopped（改 `unknown`+按钮隐藏）、for-you 错注释、拆解列分组 | TDD：新测试先红后绿（3 红→7/7）；api 223 + rules 97 全绿；三门禁 86 组合/14 页对齐/14 页 pages-must 全绿（发现并记坑：门禁必须前后端同版本）；浏览器实测：For You 10 卡仅 3 张签证敏感型带注记且天数逐卡不同（9/40 天）、SFAO→policy 与 IANG→intl_policy 真实抓取双分类落广场、规划四档现 4 条 Pack 条目、console 92 链接+抽出 36/在架 36 一致、图例六项、EN 一遍；截图 docs/verification/intl-chain-fix/（7 张） | 见本行 commit |
| 08-02 | **pack-sources-intl 批验收并入 main + 云端上线**：ff-merge → `c6f2963`；Secret Manager 建 `campuspath-checkin-secret` 并授权 Cloud Run 服务账号；api 重发含三处部署修复（Dockerfile 补 `COPY jobs`——`.gcloudignore` 曾把它排除在构建上下文外导致首轮 Job 实为失败、PYTHONPATH 补 `services/packs`、**max-instances=1**——巡检/签到/后台任务是实例内存态，双实例会互相看不见）→ rev **00008-hsd**；web 重发 → rev **00008-8kk**；每日巡检 Cloud Run Job `campuspath-sources-refresh` + Scheduler `campuspath-sources-daily`（09:00 HKT）建成并实跑 | 云端 Job 执行 `wff8h` 日志实测 `changed=81 unchanged=0 error=2 skipped=9`；线上 API 复核 83/92 源有巡检痕迹、81 ok、2 不可达如实红（alumni×2）；线上广场 174→224 条：**36 条 OPP-LIVE 真实活动 + 14 张政策卡**；programs 200、/v1/ops/sources 92、质量汇总 6 场全有分、STU-A 拆解 role_profile 命中；web /login 307→Google 团队门 | 见本行 commit |
| 08-02 | **F 批（同分支，契约 1.28.0）**：顶栏 demo 按钮一键启停 Vertex Agent Engine（GET/POST /v1/ops/agent-runtime，后台线程跑 infra/agent_engine.sh 新增 start/stop 模式；30s 状态缓存；无 adk/脚本环境 503 如实且按钮隐藏）；onboarding 免责声明重排版（四条真实源编号分行、去字面 **、宽度随栏 958px 对齐下方模块，SyntheticBadge full 态改 block）；publisher 投稿台「组织」下拉删除（与主办方分类重合，用户裁定；B7 越权拦截演示改由 services/publishing 回归测试与 API 佐证，403 闸门未动） | 浏览器实测：按钮 stopped 态「点击启动 Cloud Run」→ POST stop 走全链 stopping→stopped 无错（start 未实跑——会产生按小时计费的真实部署，演示前手动首验并记入 runbook）；免责声明 4 行/无星号/958px；publisher org 下拉缺席+orgcat 在位断言；三门禁+api 523 全绿 | 见本行 commit |
| 08-02 | **独立审查（opus 子代理，20 条发现）全部处置**：**采纳并改 17**——高5全修（#1 签到 token 改 HMAC(env secret) 防离线伪造；#2 OPP-LIVE id 改内容哈希防跨轮碰撞；#3 还原 Source Health 八项面板（F22 零删减）；#4 archive 视图 withdrawn 受 include_expired 约束不再漏给学生；#5 publisher 取签到码限投稿产物 403）+ 中10（#6 intl 落库前置同意闸门+clear 服务端撤销、#7 jobs_lock 原子化、#8 全链抓取改用 source.url+engage 降级去重、#9 解析器加载入 try、#10 三处静默吞错补可见错误态、#11 by_school 不再编造 0、#12 均分/好评率统一 verified 分母、#13 last_extracted_count 可观测、#15 去重扫全三列表、#16 Pack 凭据 context 绑定 student_id）+ 低2（#17 裸域名、#18 测试重名改名）；**部分采纳 2**——#9 解析器迁 connector、#20 政策卡服务端过滤（公开政府链接无隐私面，界面折叠口径已注明）；**记待办 1**——#19 前端真实源名单改后端派生字段（代码内 TODO 注明维护点）。#20 配额失败返还+按日清理已改 | 修复后 api 214 + rules 12 + connector 48 + packs 32 全绿；eval 13/13 · 11/12 复跑不回归；测试顺序改为「先同意后落库」并新增 403/撤销两条回归 | 见本行 commit |
| 08-02 | **发现并修复存量假红：B5 评测器漏更新豁免口径**——收尾全量 `make eval` 报 B5 失败（STU-A 90 条带标题块）；`git worktree` 对照实验证实 **main 基线同样红**：07-31 R4-M 落地两条 Spec 认可豁免（课表=教务公开数据、student_defined=本人笔迹）时评测器没同步，且此后没人重跑过 eval。修评测器对齐 §17.5/R4-M 口径（闸门本身没坏） | H5 双向：修后 B5 绿（canary 被闸门剥除）；模拟闸门失效（授予二级+注入 canary）修订口径捕获泄漏 1 条→仍会红；全量 eval **13/13 BLOCKER · 11/12 TARGET** 恢复 | `8fff601` |
| 08-02 | **D/E 批（同分支，契约 1.26.0→1.27.0）**：四维评分（+预期兑现）+ 反思页 promotion 两句；签到二维码全链（确定性 token、开始日起计数 409 有测试、publisher 批准行内取码、扫码后评分自动 verified）；plaza-admin 实时四维统计 + Archive 分页（结束+2 月冻结/归档视图，评分拒收 409）；周/月/学期/学年反馈报告页（admin-only 四角色 403 测试；确定性统计+阈值抑制+真实好评率口径；AI 叙事仅吃聚合 JSON；后台任务进度条切页不断）；日历睡眠浅蓝块+睡眠/天统计+未登记提醒；免责声明扩充真实源四类枚举 | api 213 全绿（含 6 条闭环新测试）；浏览器实测：评分 4 行/promo、plaza 6 行实时统计（均分 4.0/好评率 62%）、QR data-image、Archive 3 条、报告真 Vertex 叙事 + 4 表、睡眠 STU-B 有统计无提醒/STU-A 反之；三门禁全绿；截图 pack-sources-intl/ | `98fcf39` `4f051c3` |
| 08-02 | **A/B/C 三提案批（分支 `feat/pack-sources-intl`，未并 main，契约 1.22.0→1.26.0）**：**C** 源注册表 92 源（84 真实/8 mock `is_real_fetch` 如实标注；HKUST 资源地图全量转录 + 国际生政策源 14 个）+ 共享抓取器（三 scrape 脚本收编）+ sha256 变更检测 + console 真刷新钮（修掉 B10 假按钮）+ 官方域名白名单**直发广场**（第三方投稿仍走审核）+ 主办方十大类（Publisher 下拉同步）+ 政策更新提醒卡（无报名动作、仅国际生可见）+ 每日巡检脚本；**B** 国际生 Pack vendored 进 services/packs（零 LLM 扫描第 11 成员；draft/review_required 恒 needs_confirmation 如实标「待政策复核」）+ Rules 桥签发真 validation_id（Pack 自铸 VAL-* 过不了 B8 有反例测试）+ 契约扩展（InternationalStudentContext 13 字段/ConsentScope.context_pack/Opportunity 三态 accepts_international）+ 档案页唯一勾选入口（取消=撤销+卸载）+ 拆解「国际生准备」列 + `.intl-note` 特殊色注记（For You/广场/行动中心证件 90 天提醒）+ intl_policy chip 仅勾选后可见；**A** 编译流水线（两岗位×10 家公司 JD、100% 行映射机器断言、榜单 36 条 URL 全实测；履历聚合因 LinkedIn 免费账号匿名化未取样——如实 JD-only，方法论文档记录）→ 岗位画像（AI PM 16 facets/9 core；SWE 13/7）+ A3 确定性关键词命中 + goals 页 core 加粗下划线/市场证据注/可点取证链接 +「现场 AI 拆解」服务端后台任务（三段确定性进度条、切页关页不中断实测、产出 origin=ai_live 标「待核验」、每日 2 次）；**增补** 学期选择器（y1s1–y4s2 存档案）+ planner 已选课程折叠面板（advisor 同款交互；与日历课表块同源——HUMA×4 两页一致实证） | 真实抓取端到端：入境处 IANG 页 → 政策卡上广场；活动日历 → 36 条真实活动直发（OPP-LIVE）；图书馆官网刷新按钮浏览器点击实测；92 源全量巡检实跑（80Δ/3 不可达如实红/9 skip）；api 195 + agents 73 + contracts + packs 32 + rules 桥 5 全绿；三门禁全绿；浏览器三语/双题验证截图 docs/verification/pack-sources-intl/（9 张） | `1dad64d`→`baaa3e8` 十批 |
| 08-02 | **API 直连加锁拍板（用户裁定：方案 C，不加锁）+ 云端成本面收口**：API 站点维持公网可达（仅合成数据，web `/api` 反代已在 Google 团队门内）；为封死滥用烧钱面，两个 Cloud Run 服务 max-instances 20→2（纯成本上限，非访问锁；api 修订 00005 / web 00007）。队友 ust.hk 邮箱过门定为**自行用该地址注册 Google 账号**，`TEAM_EMAILS` 白名单不改 | 实测：两服务 describe 断言 maxScale='2'、min 未设（缩容到零）；API 无角色头 403（`role_denied`，带 `x-campuspath-data` 头证明达容器）、带 `X-CampusPath-Role: student` 头 programs 200；web /login 307→Google；Agent Engine 运行时 REST 列表为空（0 个按小时计费项）；Moodle GCE TERMINATED；预算告警 5 档在案（07-29 建） | 见本行 |
| 08-01 | **UI 全站重构：Claymorphism × Claude 暖色（分支 `ui/clay-restyle`，未并入 main）**。B0 基建（globals.css v2：oat/bark/terra 色阶 + 16 语义变量×双主题 + 4 档圆角 token + clay 三层影 + Nunito next/font 自托管 + 签名元素 clay 化——票根 mask 真镂空、斜纹垫底；`scrollbar-gutter: stable` 跨页稳定）→ B1 外壳/登录/onboarding → B2 原语库（ui.tsx 14 导出 + primitives.tsx；`.btn/.field/.chip` 类为契约）→ B3–B7 全部 19 页迁移（4+3 页机械批委派 opus 子代理，逐条独立复核）。用户中途裁定逐项落地：全站分页标签统一分段控件、goals 拆解区三层 pastel 色块重排版、profile 表头重排+编辑钮右上+技能沉底、日历控件并入日历卡+作息卡沉底、Advisor 预约面板默认折叠、publisher 上传按钮+我的投稿快照展开。**三道新门禁**：`check-contrast.mjs`（80 组合×双主题 WCAG 实算，修复 v1 令牌文档 §8 两缺陷——hatch 文字 15 处、moss/clay 暗色 31 处）、`check-alignment.mjs`（跨页骨架逐像素+probe 自检）、`run-pages-must.mjs`（data-* 回归+重试）。文档：Design Tokens v2.0、apps/web README、Spec v4.1.10、ARCHITECTURE 版头 | 每批：三门禁 + 真浏览器点击流（登录/删除确认/抽屉/折叠/编辑往返/日历拖选）+ 双语双主题截图（docs/verification/clay-restyle/），`git diff` data-* 行数逐批为 0；对比度值全部脚本实算非估算 | `3d6e712`→`876c22e` 九批 |
| 08-01 | **合并上线 + GitHub 快照**：`ui/clay-restyle`（25 commits）fast-forward 并入 main（`c39ab28`）；过滤快照推送 github.com/AriaYD/yqywfrmhpy-test（单 commit，排除 reference/、docs/verification/ 与全部评审报告、用户个人文档；敏感串扫描含 H5 自检全净——测试邮箱在入库代码中零出现，仅环境变量名）；Cloud Run 双服务重部署（api 修订 00004 / web 修订 00006，env 原样保留） | 合并后 `make smoke` 21 绿；快照 `grep -rqi` 敏感扫描（先证明 grep 会响再判净）；线上实测：API programs 200 + 目录 JSON 正常（/healthz 404 系 GFE 保留路径拦截、请求未达容器，非回归）、web 页面与 /api 反代均 307 → Google 登录且 redirect_uri 为公网域名 | main `c39ab28` · 快照 `39713fa` |
| 08-01 | **全链路筛查 + B13 修复批（同分支，契约 1.22.0）**：三子代理并行筛查（学生 11 步 / 校方 A–F / agents 7 项）——**0 阻断 0 死链**，agents 链 7/7 通过且实证分支未触碰 agent 代码；总报告 `docs/verification/clay-restyle/full-audit-2026-08-01.md`。发现的 5 个功能问题**全部修复并复验**：投稿退回可见+同 id 重投（新端点 GET /v1/publisher/submissions + 回归测试）、settings 授权开关接真 /consents、CONSENT_KEY 对齐枚举全集、memory 取代链标注、memory 删除两段确认；顺手修既有缺陷 matches 理由双语化（en≠zh 实测 5/5）。追加四条界面裁定：回执注脚归位、成长跟踪归「我」分组、日历导航更名「日历/身心容量」（页内分页不动）、紧急求助沉底 | 全部真浏览器复验（重投全环、开关持久化往返、取代徽章、删除确认取消保留、DOM 序断言）+ 三门禁全绿 + api 178 / contracts-check 一致 | `35b6643` + 本批 |
| 08-01 | **B12（同分支）**：AI 推荐评语统一 `.ai-note` 高亮语汇（陶土浅底，for-you 理由 / 课外活动「为什么推荐」/ 备考提前量估算三处；fg/fg-muted/hatch-ink 对 accent-soft 三组合进对比度门禁，86×2 全绿）；资讯广场删冗余「官方」复选（主办方八大类已含校园官方）、截止/含已截止挪至第二行与 已收藏/已加入日历 并排 | 浏览器实测：三处 computed accent-soft 背景断言、official 控件缺席断言、第二行四筛选成员断言；三门禁+对齐+结构复跑全绿 | `f0b41cd` |
| 08-01 | **B10+B11（同分支，契约 1.21.0）**：审核队列独立成页+校方广场总览（搜索/编辑/下架——PUT/DELETE catalog 端点，下架幂等留档；catalog GET 放行管理角色修 403）；机会源写全名+API 订阅源刷新钮；goals 两列对齐；已报名态服务端回读持久化（for-you/square 标记）+行动中心提案卡显示活动原名（OPP- 抽取修根因）；**独立审查（opus subagent 替代被禁自调的 codex）23 条全处置**：高1修（advisor id 序号解耦防复用串号+回归测试）、中11修9记2（删除两段确认/错误码 i18n/编辑器标签对比度+门禁组合/暗色双块漂移断言/pages-must probe/alignment 单边缺席判死/label.btn 焦点环/aria-pressed 统一/primitives 实装）、低11修6记4不采纳1（next/font 构建期网络依赖属权衡）；B11 五项用户裁定：工作日 8–12/13–18 每小时档（9 档/天）、导航「顾问预约/规划与行动」、折叠行 accent-soft 凸显、同意回执卡收成注脚、广场搜索+「已加入日历」标记与筛选、档案空分区自添记录（self-edit 整表替换、恒 self_reported） | api 179 绿（新增 id 复用/编辑下架/时段集合回归）；contracts 307+contracts-check；每项真浏览器点击流（广场搜索 177→2、加入计划→刷新→标记→筛选闭环、自添经历存后重载仍在）；三门禁 82 组合/对齐/结构均绿且各带 H5 自检 | `3c2d6f5` `56da23f` |
| 08-01 | **B9 Advisor 体系改造（同分支，契约 1.19.0→1.20.0）**：预约改一小时时间段制（库存 10 工作日×10–11/14–15/16–17；学生端/工作台双端显示起止区间）；Advisor 注册信息查看/编辑/删除（advisor-desk 拆两分页；DELETE 有未完结预约 409 保护）；AdvisorUpdate 模型 + PUT/DELETE 端点 | TDD 3 条新回归（时段=3600s、编辑删除往返、活跃预约删除拒绝）；api 172 / contracts 307 全绿 + contracts-check 一致；真浏览器全链（注册→编辑生效→删除消失；学生端「09/16 10:00–11:00」） | `2f94317` |
| 08-01 | **第六轮 A/B/C + B+D 大件**（契约 1.14.0→1.15.0）：校方端岗位切换器移除（只读徽章，换岗=重登）+ 登录 4 类入口带中文岗位说明（复合角色 career_center_admin 进契约与 RBAC 表，隔离测试钉住：insights/source-health 200 而学生数据与 outreach 队列 403）；Advisor 会面记录合并为一条（topic+时间+我的反思+建议同卡，反思不再单独成条）；档案总览 12 分区完整 resume（ProfileExtras 契约 + 三学生合成初值 + 全页编辑往返实测：新增爱好/荣誉保存回读） | 每项 drive.mjs 浏览器实测（4 入口卡/复合角色进控制台+advisor 台拒绝/合并卡四要素/12 分区渲染+编辑往返）；api+contracts 全套件绿；截图 round6/ | `9c0601f` `a4d1653` `9dafc3e` |
| 08-01 | **第七轮 A–D**（契约 1.15.0→1.17.0，Spec v4.1.8）：校方一岗一台（导航按岗过滤+守卫弹回；新建 wellbeing-desk）；Publisher 表单扩展（申请人/联系/详介/报名方式/附件元数据）+ 审核队列移入 console 落真实存储（auto_check→in_review→裁决，409/404 如实）；日历 24 小时制+周/月双视图（跨午夜睡眠块拆段显示、编辑作用原块）；A0/A2/A4 上线（agent-trace 端点、A2 类构建候选、/ops/sources/ingest 摄入链）+ ADK 部署两个 Agent Engine 运行时（us-central1，`infra/agent_engine.sh` 管理，镜像一致性 CI 断言） | 四岗位浏览器实测+三语；审核全链实测（投稿→队列→批准）；月视图/凌晨睡眠段实测；云端 status+真机问答（A0 确定性路由、A4 无视注入恒 draft）；api 144→157 绿 | `0231798` `1dc364a` `b16354a` `fe0e87e` |
| 08-01 | **第八轮 1–3**（契约 1.17.0→1.19.0，Spec v4.1.9）：「联系辅导员」403 根因修复（外联同意按学生 seed；联系人 fixture 邮箱走 GOOGLE_TEST_ACCOUNT_EMAIL 环境变量不进码）；心理干预三层机制落地并写入 Spec §16.8.3 批注（第一层自动联系自填 tutor【用户拍板，量表提交即知情动作】、第二层咨询室预约【时段唯一来源=wellbeing-desk 工作时段，预约带五项学生信息、专业年级服务端回填】、第三层紧急红按钮【2 次/学期，第 3 次拉黑但拒绝响应仍附热线】、疲惫自报直接开评估）；Advisor 自助注册+逐时段「不在」管理（不在时段学生端服务端过滤，预约 409） | 全链浏览器实测（STU-A 二层预约+紧急 3 连按、STU-B 一层自动联系、校方时段设置与预约队列、Advisor 注册→拉黑→学生端消失→恢复）；api 161 绿、contracts 307、wellbeing 55 | `8e344b7` `15e17ba` `86a8bdc` |
| 08-01 | **R7/R8 独立审查 + 修复**（opus subagent 替代排队超时的 codex；范围 0231798^..86a8bdc，12 条发现全部逃过原测试网）：高3全修（重投覆写已裁决投稿→未裁决幂等重放/异主403/已裁决409；ingest 契约请求响应写反；跨午夜块编辑 422+快照 -15.5h 500——作息块不入 personal_protected + 跨午夜窗口拆段）；中6修4（99:99 时段 500→契约层422、改时段孤儿预约→409、预约 id 判重、紧急计数不含被拒+前端防双击、删号补清 R8 四容器【tutor 台账含 ISI/PSS 原始分】、审核卡按岗渲染）+待办2（advisor 归属绑定与并发id、TOCTOU 锁）；低3改2 | 6 条回归钉+全套 api 167/contracts 307 绿；跨午夜保存浏览器复测通过 | `915a893` |
| 08-01 | **第九轮：全流程报告修复（用户批准）+ 公网部署**：P2-4 冷启动文案/P3-6 死链不弹/P3-8 导航文案/P2-3 AI 复筛回填无词命中候选（成本不变）；P1-2 ISOM/IEDA 官方 2025-26 PDF 人工转录（sonnet 子代理，provenance=manual_transcription，ISOM 4组9门/IEDA 6组49门，区间型组如实缺席）并入两处消费点；P2-5 拖拽记待办。**Cloud Run 双服务上线**（asia-east2 赠金项目）：campuspath-api（2 修订）+ campuspath-web（3 次构建，坑×2：契约类型在构建上下文外、Next rewrites 构建期烧录）——公网不注入测试邮箱 | 云端 curl（programs 7 专业、profile 200）；公网真浏览器 e2e（登录→档案→代理 200，截图 live-cloudrun.png）；本地 api 167 绿 | `723a746` `e93f49d` `dda9dc5` `62c6ed2` `f50aadb` |
| 08-01 | **第十轮**：提议页只剩证据型提案（seed 行为推断不再注入+列表只读 store，TDD 钉住）；导航「规划与行动」；「开始规划」迁入目标工作室；公网 13 步全链路测评+Agents 质量评估两份报告（`docs/full-journey-review-live-2026-08-01.md`、`docs/agent-quality-review-2026-08-01.md`，写手复核纠正了两条误报、新发现量表文案超阶【已修：文案改述真实阈值】）；Agent Engine 两 runtime 采数后**已删除**；campuspath-web 上 **IAP 白名单**（3 队员邮箱） | 公网 e2e JSON+13 截图（journey-live/）；api 167 绿；IAP 绑定 3 条成功 | `7fbf4b0` 等 |
| 08-01 | **第五轮 A/C/E/E2/G2 + F 检查**（契约 1.11.0→1.13.0）：档案三分页（总览成干净 resume）+ 证据源文件上传（核验恒自述）；重要联系人学生自填随时改；Wellbeing 两层预警（确定性阈值→ISI+PSS-10 零 LLM 计分，PSS 反向计分逐界钉死 9 项测试；ISI≥15 且 PSS>20→心理咨询中心，余→辅导员；**外联仍需学生确认，B13 不放宽已向用户说明**）；闭环记录确定性生成"加为经历"提议、确认后物化（B3）；F：AI 链路三条真机实测全通（matches 模型理由/A1 反思提炼/K 批量复筛均 model 产出）。chrome-devtools MCP 断连→新建 `verify/drive.mjs`（puppeteer-core 连 9222）恢复浏览器实测能力 | 量表 9 测试+边界；API 分流/隔离/物化测试；浏览器实测（三分页、上传出卡、联系人持久化、17 题作答→分流卡）；llm-free 扫描绿；截图 round5/ | `4dd6728` `3d2d171` `90f22c6` `7baaa97` |
| 07-31 | **UI 第三语言：繁体中文（zh-Hant）**。词典由 OpenCC（cn→hk）自 zh-Hans 确定性生成并入库（536 键，`bun run i18n:hant`），一致性检查 `i18n:hant:check` 与 contracts-check 同守法（H5 实证：篡改一键即红，再生成复绿）；契约 LocalizedText 不动——繁体态下服务端动态文案运行时转换（`toHant`）；新增 `pickLang` 通道并迁移全部 6 处 `locale==="zh-Hans"` 硬编码（否则繁体会掉英文）；类型层保证词典完整（Record<keyof Dict,string>） | 浏览器实测：三键切换（简/繁/EN）、导航全繁体 0 简体特征字、动态内容转换（產品運營實習生）0 简体泄漏、html lang=zh-Hant、localStorage 持久化、简/英回归正常、console 零错误；`bun run build` 通过 | 见本行 commit |
| 07-31 | **修复用户报障：广场 React 重复 key**（Seed→1.8.0，契约 1.10.1）。根因：种子生成 `("internship", 随机标签)` 时随机池也含类型词，撞车产生重复标签，前端拿标签当 key 报错。三层修复：①源头 `_dedupe_tags` 去重保序；②Seed 一致性新增「机会标签无重复」检查 + 已知失败变异（自检 16→17 项全抓住）；③契约层 `Opportunity.category_tags` 规范化 validator——任何来源的数据都干净 | 实测：重复标签机会 14→0；seed-check/selftest 全绿；全套件绿；浏览器巡检 square(177 卡)/actions 三分页/reflections 两分页 console 零错误零警告 | 见本行 commit |
| 07-31 | **第四轮 A–M 十三项**（契约 1.6.0→1.10.0，Seed→1.7.0）：M 批准活动落入 pathway+周日历（课表块带课程全名、编辑器配官方链接、TDD 钉住吸收幂等与标题）；K 选修推荐两层筛选（真 Vertex 批量复筛每门带理由、AI 不改判先修、无模型降级自报 rules）；J 五专业分学期课纲（sonnet 搜集官方 PDF+先修链推断、0 非法课程码、地图学期切换）；L 三分页合并；DEF 反思两分页+合并记录列表（五类标签+评分下限筛选）+Advisor 建议解锁机制（浏览器全链：锁定→写反思→解锁）；G 档案就地编辑（删/增标签落库版本+1）；BC 专业全名+证书可读命名+真实公开课链接；HI 共享要求同类合并+分叉点文案 | 每项浏览器实测；api/contracts 全绿；截图 docs/verification/round4/ | `4076859`…`c0a8f74` |
| 07-31 | **第三轮 R：全流程真人模拟实测 + 评估报告**（`docs/full-journey-review-2026-07-31.md`）：以"同学A"人设 15 步走完 登录→授权→Resume→目标→选课→作息→报名→广场→行动中心批准写日历→Advisor 预约→反思→成长跟踪证据链。闭环走通；报告列 10 项发现（P1×2：新报名活动不在反思对象列表、ISOM/IEDA 专业无公开 PDF 数据；P2×3；P3×4 + 评测口径重申），**结论未经用户同意不改代码** | 全程 chrome-devtools 真实点击；API 重启回种子态后从零走起；截图 R-journey-growth-tracking.png | 见下 |
| 07-31 | **第三轮 Q：Advisor 预约升级**（契约 1.6.0）：3 合成顾问名录 + 实时时段库存（占用 409、提前 ≥1 天取消即释放、迟取消 422 并说明后果、一学期爽约 3 次拉黑）；预约面板挪到行动中心置顶，反思页只留会后建议；advisor 工作台加占用统计与爽约标记 | 新回归测试覆盖 409/释放/422/拉黑全链；浏览器实测选时段→预约→时段变灰→取消→释放；英文态 0 CJK；api 120 全绿 | `e3ab4ae` |
| 07-31 | **第三轮 A+M：周日历即编辑器**（契约 1.5.0）：点空白格添加行程、点块编辑/删除（标题/起止/类型/提醒），独立"日程调整"卡移除、重排询问随之下移；作息卡显式提交睡眠/三餐→每天保护块；容量口径钉死（作息不重复扣可支配、仅个人划出的保护时段扣）；层级闸门学生自笔标题例外（B5 管采集不管本人笔迹） | 回归测试钉容量口径（0→+2h→回落）；浏览器实测创建带标题保护块（0→1.0h、重排询问出现）、改时长、作息生成 28 块且可支配不变；测试先抓到我自己的口径漏洞（种子保护块误计）后改为显式登记 | `4ccd5d8` |
| 07-31 | **第三轮 G+H：选课页只显本专业 + 课程可读**（契约 1.4.0，新端点 /catalog/courses）：专业地图锁定登录学生本专业（IEDA/ISOM 无公开 PDF → 如实"未接入"），选修组不再铺课程码；候选课分三区（可直接选/需提前规划/无法判定），每行带全名/简介/先修原文/教务链接/学分 + 词级匹配的"为什么相关"（规则生成标注，只有有据才显示） | 浏览器实测 STU-C（未接入提示 + 92/7/1 三区 + IEDA 1180 详情 + 官方链接）与 STU-A（本专业地图、7 条相关性注）；尝试补抓 IEDA/ISOM 实证其 ugprog 页无 PDF 后按不编造原则回退 | `3754c62` |
| 07-31 | **第三轮 B+D：档案页简历化**：上传按钮改为真按钮（隐藏原生 input）；新增 LinkedIn 式分区（项目与经历/实习与工作/课外课程与证书，核验状态不抹平） | 浏览器实测：真实上传 STU-C 合成简历 → Vertex 提炼 → pending 提议；三分区渲染；英文 0 CJK | `7b72806` |
| 07-31 | **第三轮 C+P：三份合成 Demo 学生档案**（不抓真人 LinkedIn——针对私人个体收集资料不做，且项目基线要求学生数据全合成）：STU-A/B/C 各一份人设文档 + 英文简历（sonnet 起草，本人逐项 review：无真名、与 personas.py 无矛盾、证书号全 SYNTH-、无可验证伪造链接） | 逐文件 review + grep 自查 | `2f0d2e7` |
| 07-31 | **第三轮 O：活动闭环**：报名→行动中心（pending 排程提议）→批准→参加→写反思→自动落 EvidenceRecord→成长动态跟踪对应能力下 | 浏览器实测报名后 SP-APPLY-* 出现在行动中心；反思后证据挂到 project_portfolio/teamwork 两个条目下 | `695530f` |
| 07-31 | **第三轮 L：动态差距图 → 成长动态跟踪**：不再罗列必修课与状态筛选；主目标拆解三层列能力细则，每条挂证据链（写完反思的活动 + 已完成选修课） | 浏览器实测三层渲染、证据链、选修课列表；旧筛选/必修罗列消失；英文 0 CJK | `3e9034b` |
| 07-31 | **第三轮 K：共享要求/分叉点三层归类**：按 硬性要求/软实力/特殊约束 分组（展示层统一映射 requirementLayers.ts），类别用可读双语标签，删除"两条路都需要"冗余；分叉点按主/候选独有 + 层级出标签 | 浏览器实测 STU-C 双目标（hard 3 条 / soft 3 条；分叉主目标独有 3 项 vs 候选 1 项）；英文 0 CJK | `5a31fd7` |
| 07-31 | **第三轮 I+J：课外活动规划**：路径时间线改名并入选课页分页（只含非课程条目），行动中心恢复独立导航；四档跨度（两周/一月/学期/学年）；活动卡带官方超链接/简介（provenance 原文）/两句推荐理由（A5 理由优先，规则生成如实标注）；demo 夹具补 opportunity 条目（凭据真实签发，B8 不豁免） | 夹具回归测试（三学生均含课外条目）；浏览器实测 3 张活动卡全要素；先写失败测试抓出夹具全课程的问题 | `043a1e9` |
| 07-31 | **第三轮 N：修通日历写入授权**（契约 1.3.0）：新端点学生自助授权/撤销单项同意（服务端签发回执 B13）；行动中心 403 后就地"授权并重试"；onboarding 开关落库（原为纯本地 state）并新增 calendar_write 项 | TDD：403→授权→200→撤销→403 全链回归测试；浏览器实测 STU-C 一键授权后"已写入"；onboarding 实时反映授权态 | `7eea714` |
| 07-31 | **第三轮 E：登录身份隔离**：右上角学生切换器移除（改只读徽章）；换学生唯一路径 = 退出登录重新验证 | 浏览器实测：切换器消失、徽章只读、logout→login 选 STU-B 生效 | `ffca2bc` |
| 07-31 | **架构文档 + README 补全 + 文档维护清单**：新建 `ARCHITECTURE.md`（双平面组成、mermaid 系统架构总图 + 2 条关键数据流时序图、六条红线技术落点、分层清单、文档地图）；README 补项目文件结构树、修好被段落截断的文档表、状态段更新到 07-31；CLAUDE.md 增「文档自主维护」表（何时改哪份）与 compact 后必读顺序 | 文档内数字全部实测取自冻结产物：契约 1.2.0 / 123 模型 / 53 路径 59 操作 / 179 schema（`contracts/openapi/campuspath.json` + `_index.json` 脚本清点）、Seed 1.5.0（config.py）、Agent 类名对照 roster.py；结构树逐目录对照 `find` 输出 | `ef9d672` |
| 07-31 | **第二轮 A–O 同步进 Spec（v4.1.1→v4.1.2）与 Plan**：§6.1 八行页面说明（Resume 上传口/专业课程地图/日历直接调整+重排确认/推荐缓存+报名/收藏可取消/时间线并入行动中心/反思多维+Advisor 分区/行动详情+备考提前量）、§6.6 新增 Career Center Advisor 角色行（含不可见边界）、§6.10 主办方八大类、§9.4 C 轨多维评分落地注、§5.9 三人群 Pack 实装注、§10.1 新增 ugprog 专业要求数据源行、§12.5 推荐每日缓存行；Plan D1 页面完整性行（导航整合）+ 新增"第二轮 A–O 功能"验收行 | 每处引用原文核对后修改；功能零删减；批注统一标「2026-07-31 实现同步（第二轮）」；文档版本 v4.1.2 变更记录在文件头；`make check` 全绿 | 见下 |
| 07-31 | **第二轮 H：日历直接编辑 + 学生决定重排**。契约 2 端点（update/remove 时段，改的是 CampusPath 视图、权威日历不动）；日历页「日程调整」卡：busy/flexible 时段可 ±30min 或删除（误占用场景）；改完弹「要不要重排近两周」——是→calendar_change 触发 replan-preview 显示将动/不动范围（长期项不受影响），否→保持原状 | 浏览器实测：+30min 16:20→16:50、询问条出现、重排范围 0/8、删除后行消失；容量快照随改动刷新；`make check` 全绿（api 109） | 见下 |
| 07-31 | **第二轮 K/M/O：导航整合 + 专业课程地图 + 行动详情**。K/M：方向与计划并为一组，行动中心并入路径时间线、身心容量并入日历（同页分页，/actions /wellbeing 深链接保留且守卫仍认学生端归属）；导航 12 项。K②：契约 `ProgramCurriculum` + `GET /catalog/programs` 服务 C 抓的 5 专业真实要求，选课页新增「专业课程地图」（必修/选修组、学分/门数、择一逻辑标注、全校毕业要求、BCB 替代关系显式展示）。O：行动中心行程卡加载活动详情——报名截止/活动时间线/预计投入/前置要求（来源原文）/备考提前量（仅比赛/工作坊/含证书要求的按投入折算 14–60 天，实习类固定 14 天材料准备，均注明估算） | 浏览器实测：导航无独立 /actions /wellbeing；timeline 与 calendar 分页切换正常且身心容量内容加载；专业地图 5 个专业下拉、COMP 3 组 ↔ MATH 18 组切换、毕业要求呈现；行程卡详情块含截止与备考提示（修掉一处把整段实习工时当备考量的 504 天错误估算）；`make check` 全绿（api 107） | 见下 |
| 07-31 | **第二轮 A/D：Resume 上传 + 三个人群拆解 Pack**。A：新端点接 md/txt/pdf（pypdf），A1 经模型提炼技能/经历 → 恒 pending 提案，与现有档案冲突项标 update 带旧值由学生逐项裁决；原文解析后即丢。D：**"5 类人 5 个 skill"与框架的关系已界定——就是 F27 Career Path Pack + A3 内容表的完整形态，实现为 Pack 数据（`GOAL_DECOMPOSITION_PACKS`），不新增 Agent 不动框架（§5.9）**。三个 Pack（求职/创业/读研）各含硬性/软性（强制带取证来源，类型层校验）/特殊约束三层；目标工作室每张目标卡呈现拆解，双目标并排即对比；要求图改由 Pack 派生；未覆盖方向 422 如实说明 | 浏览器实测：STU-C 双目标面板（5硬/3软/1约束 vs 4硬/2软/1约束）双语取证来源；ScriptedModel 单测冲突标注；真 Vertex 提炼 5 条；`make check` 全绿（api 106） | `553b320` `3f24198` |
| 07-31 | **第二轮 B/I/L：反思多维评分 + Advisor 纵切**。B：评分拆三维（内容深度/实用收获/组织）走新端点转去标识 EventQualityFeedback，个人匹配只以 FitTag 出域（Personal-vs-Global）；反思历史加搜索框。I：契约新模块 advising（AdvisorBooking/AdvisorSummary，completed 必带总结在类型层强制）+ 新角色 advisor + 5 端点；学生在反思页预约（Year 1 被拒带解释 403）、看关键建议、把会面作为反思对象（L 的 advisor 分类）；校方门户新增 Advisor 工作台（确认→写建议→发送），与学生端不混 | 浏览器实测全链：预约→advisor 确认→两条建议→学生端展示且会面进反思对象筛选；隔离测试：student 访问队列 403、advisor 访问 profile/notes 403；未确认写总结 409；`make check` 全绿（api 103+流程测试）；截图 `docs/verification/round2/` | 见下 |
| 07-31 | **第二轮 G/E/F/J 四项**：①收藏可取消（契约加 `ActionType.UNSAVE`，事件流按最新方向定态，unsave 连带清除未锁定的偏好记忆）；加入日程后补"去行动中心批准"指引（链路本身经上一批修复已通）。②为你推荐加「去报名」按钮（eligible_now 卡，记录 apply 事件+开官方页）。③`/matches` 当日缓存（跨天首访自动重算=每日一次 AI）+ `POST /matches/refresh` 手动刷新每日限 3 次（429）。④主办方收敛八大类（契约 `OrganizerCategory`，seed 全量标注，广场筛选切类别，双语标签）。Seed 1.4.0→1.5.0 | 浏览器实测：toggle true→false→true、unsave 事件落库、偏好记忆移除；缓存 GET 4–12ms、刷新 3×200+第 4 次 429；10 个报名按钮点击变"已记录报名"；八大类下拉双语、career_center 筛出 15 条；`make check` 全绿；截图 `docs/verification/round2/` | 见下 |
| 07-31 | **WP3 第二阶段：Moodle BYO-MCP 落地**（`mcp/moodle_mcp/`）：REST 客户端（wsfunction 白名单只读、token 只从环境/Secret Manager 取、异常不回显 token）+ stdio JSON-RPC MCP 服务器（3 个只读工具，零第三方依赖）+ `MoodleEducationAdapter`（选课记录映射为契约 `StudentCourseRecord`；培养方案/目录/开课如实返回空，不编造）。`make test` 挂上 test-mcp | 6 项结构测试（含"白名单外调用不发请求"探针）；**真链路实测**（SSH 隧道）：site info 9 函数、STU-A 7 门 / STU-B 9 门选课映射为契约记录，与 seed 花名册一致。F04 的 Moodle REST→MCP→契约链打通；ADK 侧作为 A2 工具接入待 WP6 后续 | 见下 |
| 07-31 | **独立审查（Codex，9m22s）11 条发现的处置与修复**。采纳并改 8 条：② `/rules/validate` 曾按「无先修」评估任何课并签发真 satisfied 凭据（B8 被架空）→ 改读目录权威表达式 + 可选学生记录；③ 日历回执可伪造 → 服务端批准时签发、写入时验证归属与时段；④ 同 id 直写可顶掉锁定记忆并把锁归零 → provider 拒绝；⑤ 记忆操作无锁并发 500 → RLock + 序号计数器；⑥ 删除残留同意与 outreach → 清除；⑦ 导出缺 7 类数据 → StudentDataExport 扩到 17 节；⑧ 补修后 UNKNOWN 仍给带日期 future_eligible → 改 needs_confirmation（与裁定同一原则）；⑨ Gold 不识别 "any N of" 计数选择却给确定标签 → 归 unknown。不采纳 1 条：① student 角色未绑定个体身份——demo 既定设计（真实部署走 IAM 断言），代码注释与待确认清单已注明。记待办 2 条：⑩ T12 标签非 subject 级（WP10 backlog）；⑪ 反思评分未接质量反馈流（F14 C 轨 backlog） | 4 条新回归测试钉住修复；`make check` 全绿（api 96）；eval 仍 13/13 + 11/12 + BL 五项 | 见下 |
| 07-31 | **WP3 第一阶段完成：Moodle 沙箱实建并注入**（sonnet subagent 执行，三跑幂等验证）。GCE `campuspath-moodle`（asia-east2-a，夜间停机策略已挂）上 moodle-docker + MOODLE_405_STABLE；Web Services + REST 启用；9 门课（与 seed 选课记录对齐）+ 12 个 stu-* 学生 + 80 条注册；`campuspath_svc` 永久 token 与 admin 密码只进 Secret Manager（`campuspath-moodle-ws-token` / `campuspath-moodle-admin-password`），全程未打印明文 | VM 内 REST 实测：`core_webservice_get_site_info` 响应、`core_course_get_courses` 9 门、用户 12 个 stu-*；`infra/moodle_provision.sh`（514 行，DRY_RUN 门控）三跑证幂等，途中抓出并修掉 2 个脚本真 bug。**WP3 余项**：Education MCP 封装 + ADK 读取链（F04） | 见下 |
| 07-31 | **WP10：BASELINE 五项从零到产出 + B12 补运行时自检**。新增 `eval/campuspath_eval/baselines.py`（BL1–BL5，全确定性：排序零模型、资格判定与 T1 同一套输入）；harness/报告/runner 支持 BASELINE 类别（无阈值、未实现仍判 NOT_MEASURED）；B12 在静态扫描外加 `assert_vertex_only()` 运行时断言 | `make eval` 实测：BL1 CampusPath 第 1 条 vs 目录顺扫第 1 条（vs RAG 未测，如实注明）；BL2 15.0%；BL3 8.7%（B10 去标识 → 群体代理口径注明）；BL4 100%；BL5 87.0%；B12 双保险通过；判定类指标双跑逐字节一致（T9/T10 墙钟值天然抖动，非判定项）。T11 保持 75% 红色如实呈现，11/12 仍达 D6.7 | 见下 |
| 07-31 | **WP7 接线（第二批）+ 契约 1.1.0→1.2.0**：新增 5 端点（记忆纠正/锁定/忘记、导出、删除请求）+ 4 模型；锁定强制在 provider 层（取代已锁条目抛 MemoryLocked→409）；纠正=新条目取代旧条目留痕（§8.6）；忘记与删除幂等；Memory Center 三按钮 + Settings 导出/删除接通（F17/F01 落地） | 浏览器实测：锁定持久化、锁定后纠正 409、纠正 9→10 条留痕、忘记 10→9、导出 10 个数据节；全端点扫描对删除用 STU-L 防误伤；`make check` 全绿（api 92）；契约产物与 TS 类型再生成一致 | `be59f89` |
| 07-31 | **WP7 接线（第一批）：反思保存 / 提议裁决 / 排程批准+日历写入**。api.ts 补 submitReflection、decideProposal、writeCalendarAction；反思保存（原文只进 private_text）带已保存/失败态；档案提议 pending 时出接受/拒绝按钮；排程批准走"记录决定→逐时段写日历"，403 时如实显示"未获授权、不静默写入"。Seed 1.3.0→1.4.0：STU-B 补 `calendar_write` 同意（此前无人授权，F06 写路径数据上是死路；其余学生保留 403 分支） | **浏览器实测又抓到一个真 bug**：提案列表读 `deps.proposals`、决策读 `StudentStateStore`，两份数据从未同步，所有种子提案 404「未知提案」——修复（pending 种子提案灌入 store、GET 合并 live+历史、A1 新提案改走 store）并钉回归测试。实测：拒绝后状态变 rejected；STU-B 批准→「已写入 CampusPath Plan 日历」；STU-C 批准→「日历写入未获授权」；英文态两串复核；截图 `docs/verification/wp7-wiring/`；`make check` 全绿（api 87） | 见下 |
| 07-31 | **WP6 接线：API 开始真正调用 Agent 库**。① A3 `requirement_graph_for_mode` + `derive_divergence`（方向→非课程类别内容表 `MODE_REQUIREMENT_CATEGORIES`）接进 `/gap-map`，divergence_points 不再恒空；② `/reflections` 从硬编码 503 变真实现：存反思零模型，有后端时 A1 从非私有字段提炼 pending 提案（private_text 不进模型）；③ `/ops/opportunity-drafts` 从硬编码 503 变落草稿+确定性判重；④ `/matches` 摘掉入口 `_require_model`——排序零模型，无后端时给自报"规则生成"的兜底理由；⑤ 提醒状态机接 A5 low-load 确定性试算（仅纯 capacity_overload 且可延期项足以覆盖超载时判 True 并同步生成可见 ScheduleProposal）。`_require_model` 已无调用者 | `make check` 全绿（api 82→86，新增 4 条回归测试）；**真实 HTTP 实测**：STU-C gap-map 两次各 1 个分叉点（employment vs academia）；`/reflections` 经真 Vertex 提炼出 `PROP-REFL-…` pending 提案；`/matches` 两次 id 与分数完全一致、理由为模型产出；eval 仍 13/13 + 11/12。已知缺口：low-load True 分支缺 capacity-only 样本未被自动化覆盖（记 WP10） | 见下 |
| 07-31 | **U1–U8 行为同步进 Spec（v4.1→v4.1.1）与 Plan**：§11.1/§11.2/§10.1 真实数据源边界、§6.9 官方源直接 Published、§6.10 来源真实性标签、§14.4 Reflection.subject_id、§9.2 反思绑对象、§14.3 Goal.development_mode、§6.1 两步建目标+Action Center 三段式、§6.3/§17.5 两级日历授权、§8.9.4 双语模板目录、§16.9 学生主动加入触发器、§15.3+Plan§2/默认假设 门户拆分（推翻"三端同 app 按角色路由"）、Plan B5 行、D1 数据标记与 U 系列验收行、WP2 成本预警状态。修复 `app.syntheticFull` 文案漏列 Engage 活动（双语） | 每处引用原文核对后修改；F01–F27 零删减（审计确认无一条删除/弱化）；标注统一为「2026-07-31 实现同步」；文档版本 v4.1.1 变更记录在文件头 | 见下 |
| 07-31 | **T12 可测化并转绿**：Gold 补 `expected_memory_ids`、记忆池每人 5→9 条（4 条干扰项防恒真式）、检索 `_tokenise` 支持中文字符二元组（此前无空格中文整句一个 token，真实查询永远召回不到）。Seed bump `1.1.0→1.2.0` 附变更记录 | `make eval`：T12 **100%**（20 组，威胁模型注明 rule_generated 自评）；H5 探针：干扰项不进 top5、无关查询不召回预期项；新增中文检索回归测试；`make check` 全绿；双跑 metrics.json 一致；**TARGET 11/12** | 见下 |
| 07-31 | WP9 提醒面板复核：门户拆分后以学生会话双语实测 | /wellbeing 渲染「第一次提醒 / First reminder」+ 触发时间 + 重评估时间 + 非诊断声明；英文态 0 CJK；截图 `docs/verification/wp9/`。WP9 仅剩 `auto_rescheduling_possible`（待 A5 low-load 试算，归 WP6）与日历 OAuth（用户拍板用夹具） | 见下 |
| 07-31 | **学生端 / 校方端拆成两个门户，各自登录**（用户裁定推翻 Plan §165 的"同一导航按角色路由"）：新增 `/login` 合成登录页（两张卡各自入口、演示口令、错误态）；会话模型 `campuspath.session` 取代散装 role/persona 键并自动迁移清除；导航按门户过滤，门户守卫三规则（未登录→login、跨门户→弹回本门户、已登录访问 login→弹回）；校方壳只含 publisher/console 与校方岗位切换（无 student 选项），学生壳只含 14 学生页 | chrome-devtools 实测双语各一遍：错误口令被拒；学生会话导航 14 项 0 校方项、直开 /console 弹回 /profile；curator 会话导航仅 2 项、直开 /calendar 弹回 /publisher；D5 隔离面板在校方会话正常加载；英文态登录页 0 CJK；6 张截图 `docs/verification/portal-split/`；`tsc` + `bun run build` 通过 | 见下 |
| 07-31 | **T1/T3 裁定落地**（用户授权接手窗口代裁）：① Gold 的 STATE_PRECEDENCE 对齐引擎（needs_confirmation 优先——有未确认硬条件时不给站不住的日期）；② 引擎补开课记录检查（`future_offerings`，未修且无未来开课 → ineligible）；③ Gold 先修判定改三值成绩感知，含 grade 表达式不再一律 unknown。Seed bump `1.0.0→1.1.0` 附变更记录（D6.5 规则④） | `make eval`：T1 81.7%→**100%**、T3 90.0%→**100%**、T2 仍 0.0%，TARGET **10/12** 达 D6.7；两次跑 metrics.json 逐字节一致；`make check` 全绿；新增 3 条引擎回归测试 + 修 Gold 切分器把「Grade A- **or** above」劈成两半的真 bug（评测器自测样例抓住） | 见下 |
| 07-30 | WP9 提醒面板：前端渲染并双语实测 | 学生身份下渲染 1 条「第一次提醒 / First reminder」含重评估时间，英文态零 CJK。**前一版说它渲染为空是我用错角色测的**——role 切换器持久化在 localStorage，还停在 WP8 的 reviewer，端点返回 403 而面板正确地把错误显示了出来，是我没读 | `f010175` |
| 07-30 | T1/T3 分歧查清根因，写成裁定文档 | 不是一个问题是两个：① STATE_PRECEDENCE 第 2、3 位在两套实现里互换（≈6/11，政策选择）；② 引擎判「课程未修」不查未来开课，一律给 future_eligible（≈5/11，**缺口不是分歧**）。两边**均未改动**（D6.5 规则④） | `c89ce20` |
| 07-30 | WP9：两次提醒状态机接出 `GET /wellbeing/reminders` | 模拟时间实测：t+0 发第 1 次 → t+25h 发第 2 次 → t+50h/+75h **拒绝**（已达上限 2，Alert Overload 被挡住）。`auto_rescheduling_possible` 硬编码 False 并注明理由 | `a2a1172` |
| 07-30 | WP9 起步：outreach 按钮接上真实端点 | 实测 B13 两条路：STU-B 有效同意 **200**；STU-A 无同意 **403** 且界面照实说，不伪装成成功。此前它只置本地 state，什么都没发过 | `6ed52b9` |
| 07-30 | 修复：交接引擎失效**无声** | 根因实测：会话早于 `settings.json` 约 17 小时启动，本会话曾无 `.guard-<id>.json` → guard 从未被调用。新增 `handoff.py status`（判据是「跑过没有」而非「配得对不对」）+ SessionStart 无待交接时也报活。自检 33 → **37 项全绿** | `cfd4042` |
| 07-30 | 更正：该会话**后来自行武装** | 90.1% 时 guard 真的拦下了 Stop，`.guard-9e3e2a7a-….json` 已生成，`status` 报 `armed: true`。此前"这个窗口救不回来"的判断**是错的** | — |
| 07-30 | WP8 Publisher Portal + 校方 Console | 浏览器实测：授权投稿 ok / 越权 refused / 三条裁决全 200；curator 身份下 5 个禁区端点全 403，聚合面板正常加载 | `73967e3` |
| 07-30 | 实测发现 Seed 缺审核员授权 | 10 条 publisher 授权、**0 条 reviewer**，导致"人工审核批准"这条 D5 分支根本跑不起来（三次裁决全 403）。已补 | `73967e3` |
| 07-30 | WP10 评测 Harness：`make eval` 出机器判定 | **BLOCKER 13/13**；两次跑 metrics.json **逐字节一致**（D6.7）；拆掉 B5 闸门 → 变红且退出码 1，还原 → 全绿 | `ae82eba` `c13eea7` `8130afc` |
| 07-30 | 评测抓出真缺陷：validation_id 不认人 | 同一门课对不同学生判定不同却共用一个 id，第二次签发抛异常。加 context 参数，主体与绑定语义不变 | `ae82eba` |
| 07-30 | 评测抓出真缺陷：目录在卖已截止的机会 | 31 条过期仍 published；推进到 expired，广场默认不显示、可用 include_expired 取回并打「已截止」标 | `8696c61` |
| 07-30 | U1 课程目录抓全（58 学科 1534 门，desc 100% / ILO 99.6%） | 先修解析器对 **701 条**真实表达式：94.6% MET / 5.3% UNKNOWN / **0 假阴性** | `53d1ca9` |
| 07-30 | U2 资讯广场接 HKUST Engage 真实活动（66 条） | 广场 208 条中 66 条带「官方」标记，筛选后正好 66 | `5e276db` |
| 07-30 | U3 反思必须挂在具体对象上 | 浏览器实测 13 个可选对象；未选中时文本框 disabled | `54f22a5` |
| 07-30 | U4 目标工作室五方向 + 自填终点 | 浏览器实测存盘回显；「探索中」不填终点也能存 | `2fe30f9` |
| 07-30 | U7 Rules/Wellbeing 判定文案双语（模板目录 + 占位符自检） | 英文态下 Wellbeing 与「为什么没推荐」**零 CJK 字符** | `0f11e79` |
| 07-30 | **U5 日历授权分两级**（用户拍板改 B5） | 契约 validator 拒绝「无授权带标题」；API 闸门用**注入的泄漏样例**验证：强行放行 → 2 条测试变红，还原 → 全绿 | `3f6c950` `dc3c8fb` |
| 07-30 | U5 小时级周视图 + 两级授权可视 | STU-A（一级）0 个标题 / STU-B（二级）23 个标题，同一网格 | `dc3c8fb` |
| 07-30 | U8 收藏 + 偏好记忆 + 加入日程 + 学生决定重排 | 浏览器实测收藏→筛选→加入→重排范围；保护时段冲突 blocking 且双语 | `38386e3` |
| 07-30 | 契约 1.1.0：新增 8 个学生侧读端点 + gap-map 确定性实现 | `make check` 全绿；`test_every_endpoint_responds` 遍历 37 端点各调两次 | `cee2e83` |
| 07-30 | WP7 学生 Web App：14 页 + 双语 + 设计系统 | chrome-devtools 逐页实测**两种语言各一遍**，14/14 通过；断言清单里的故意坏选择器仍为红（H5）；截图 `docs/verification/wp7/` | `99b4c45` |
| 07-30 | 实测抓到 3 个"全绿但页面是死的"缺陷 | 手写 `<head>` 导致整页不 hydrate / dev server 拦 127.0.0.1 的 `/_next/*` / `Card` 不透传 `data-*`——`tsc`、`bun run build`、单测三者全绿 | `99b4c45` |
| 07-30 | Vertex 接通，`/matches` 走通端到端 | 实跑 `VERTEX_OK`（ON_DEMAND 计费）；`/matches` 冷 17.3s / **热 1.6s**（T9 要求 P50 < 3s）；两次调用分数完全一致（D6.7） | `828f483` |
| 07-30 | thinking_budget 默认置 0 | 实测一次 trivial 调用 17s、21 个 thought token；置 0 后热路径 1.6s | `828f483` |
| 07-28 | Spec V4.1 定稿（V4 → V4.1 六处架构收紧、G1–G4 定位补强、E32/E33 资源覆盖通路） | 全文一致性扫描：无残留旧 Agent 名、F01–F27 逐条核对 27/27 | `afd5f45` |
| 07-28 | 实现计划 V2 | — | `afd5f45` |
| 07-28 | 交互式项目说明网页（中英双版） | 线上实测：6 图渲染、89 个可点 F 码、27 功能 / 33 箭头 / 6 Agent、英文版 0 残留中文 | — |
| 07-28 | 英文版部署 Cloudflare Workers | 浏览器实测放大浮层 + F 码抽屉 + 截图 | — |
| 07-29 | GCP 计费修正 | `gcloud billing projects describe` 确认挂 `BILLING-ACCOUNT-REDACTED` | — |
| 07-29 | 11 个 API 启用 | 逐项 `services list --enabled` 核对 | — |
| 07-29 | 5 档预算告警（25/50/75/90/100% of HK$1,568.39） | `budgets describe` 确认 thresholdRules | — |
| 07-29 | 密钥防护：`.gitignore` + `.env`(600) + pre-commit hook | **7 个探针用例实测**：4 拦截 / 2 放行 / 1 私钥头，无内部报错 | `97b473c` |
| 07-29 | `scripts/preflight.sh` 开工自检 | 实跑 14 项全绿 | `97b473c` |
| 07-29 | Plan D6 验收标准（13 BLOCKER + 12 TARGET + 5 BASELINE + Gold Set 协议） | git 版本逐关键词核对 | `7a11f70` |
| 07-29 | Plan §5.1.1 Vertex-only 决策、§10 Harness、§11 提交纪律、双语要求 | git 版本核对 + 过时内容零残留 | `30a341c` `47af148` |
| 07-29 | HKUST 真实课程目录抓取器 `seed/scrape_hkust_catalog.py` | Smoke test 2 学科 160 门：核心字段 100% 覆盖、先修 82%、代码唯一、先修表达式（`OR` / `prior to 2025-26`）完整保留 | `9f27d8b` |
| 07-29 | CLAUDE.md 精简 200 → 78 行；新增 PROGRESS.md；Plan §10.5 测试策略 + §10.6 委派 | 行数核对；git 版本关键词核对 | `9f27d8b` |
| 07-29 | 三份记忆文件收敛为 1 个指针，每轮 memory 开销 5,576 → 1,459 字（省 73%） | 逐文件字数统计；关键内容重复处数核对 | `c81f953` |
| 07-29 | **WP1 契约冻结**：`contracts/` 110 个 Pydantic 模型覆盖 Spec §14 全部实体 + V4.1 新增三项 | `make test` 实跑 **168 项全绿**；`make contracts-check` 产物一致 | 见下 |
| 07-29 | 13 项 BLOCKER 在契约层的落点（B1–B13 逐条有测试） | 每条红线各有"已知会失败的样例"；三次**变异测试**实证：给 `AvailabilityBlock` 加 `event_title`／给 `PlanItem.validation_id` 加默认值／给 `MetricTuple` 加 `student_id`，对应测试各自变红，还原后全绿 | 见下 |
| 07-29 | OpenAPI 3.1 合同（29 端点 / 164 schema）+ 前端 TypeScript 类型 | `openapi-typescript@7` 生成 4,990 行 `.d.ts`，`tsc --noEmit --strict` 通过；`test_export_is_deterministic` 断言两次导出字节一致 | 见下 |
| 07-29 | `make smoke` 反馈环 | 实测 **0.55 秒**（目标 < 10 秒） | 见下 |
| 07-29 | 发现并修复第 7 个坑：禁用路径检查器误拦"把它列进禁用词表"的代码 | 修 `pre-commit` + `preflight.sh` 为按行判定 + `ai-studio-denylist` 同行豁免；**两个探针实测**：真实 `import google.generativeai` 仍被两处各自拦下，带标注的词表行放行 | `2383197` |
| 07-29 | **WP2 Synthetic Campus 数据集**：3 培养方案 / 12 学生（3 深度 Persona）/ 96 真实课程 / 558 开课 / 143 机会 / 24 投稿 / 40 质量反馈 | `make seed-check` 实跑 **16 项跨表校验全绿**；各表记录数逐项对照 Spec §11.2 下限 | 见下 |
| 07-29 | Gold Set：四态资格 60（**每态各 15**）、课程约束 40、重规划 12、记忆回归 20 | 逐条带 `reasons` 判定依据；状态分布实测四态均衡；全部标记 `rule_generated` 待人工复核 | 见下 |
| 07-29 | 失败样本 **16 类全覆盖**（Spec §11.3 全部，D4 只要求 ≥12） | `failures.py` 内置断言：漏一类即构建失败；每条带 `must_not` 才算可证伪 | 见下 |
| 07-29 | Seed 一致性检查器自检 | **16 个已知矛盾逐个注入**，断言**对应的那一项**检查失败（不是"有检查失败"）：16/16 全部抓住 | 见下 |
| 07-29 | Seed 可复现 | `make seed-reset` 实跑：两次构建**字节一致**（full 1,161,627 字符 / tiny 493,813 字符） | 见下 |
| 07-29 | `make check` 一键验收；`make smoke` 0.6 秒 | 实跑：preflight 14 项 + 契约产物一致 + Seed 一致 + 200 项测试全绿 | `088254f` |
| 07-29 | **WP5-1 Rules & Constraint Engine**：先修表达式解析器（三值逻辑）、四态资格、容量/保护区块、Wellbeing 五信号阈值、validation_id 签发 | `make test-rules` 实跑 **76 项全绿**；解析器对 **195 条真实 HKUST 表达式实测 95.9% 完全解析**，其余 8 条为自然语言写法，按契约归 UNKNOWN | 见下 |
| 07-29 | Rules Engine 零 LLM（B11/B12） | **三层扫描**：运行时 `sys.modules`、声明依赖树（含传递）、源码 import 语句；各自带已知会失败的样例 | 见下 |
| 07-29 | Rules Engine 变异测试 | 两次实证：把 `eligible_now` 提到优先级最前 → `test_expired_deadline_outranks_a_satisfied_year_rule` 变红；去掉睡眠信号的"学生须先设窗口"前提 → B6 反例测试变红；还原后 66/66 全绿 | `a6ae160` |
| 07-29 | **WP5-2 Wellbeing Reminder Composer**：六槽位模板（中英各一份）、两次提醒状态机、最小化 outreach | `make test-wellbeing` 实跑 **47 项全绿**；模板逐条断言含"不代表任何医学诊断"/"not a medical diagnosis"，并扫描全部槽位无诊断性词汇 | 见下 |
| 07-29 | **WP5-3 Capacity & Calendar Service**：五类时段分类、§16.6 公式、六类规划信号 | `make test-capacity` 实跑 **33 项全绿**；六类信号各自可达且断言一次性全部检出；`PlanningSignal` 类型上拒绝任何医学动作 | 见下 |
| 07-29 | Capacity 变异测试 | 把睡眠/用餐也从成长预算里扣 → `test_sleep_and_meals_do_not_eat_the_growth_budget` 与公式测试同时变红；还原后 33/33 全绿 | `87b79d3` |
| 07-29 | **WP5-4 Student State & Memory Platform**：四层记忆、Profile 三段式写入、Evidence 独立留存、MemoryProvider 接口 | `make test-services` 实跑 **26 项全绿**；含结构性断言"除 `apply_decision` 外不存在任何 Profile 写入方法" | 见下 |
| 07-29 | **WP5-5 Action & Consent Service**：预览 → 回执 → 幂等执行 → 审计 | **15 项全绿**；含"确认后被改动的 payload 必须被拒"与"重复执行不再调 executor"两条实测 | 见下 |
| 07-29 | **WP5-6 Aggregation Service**：小样本抑制、维度层数拒绝、时间衰减、置信区间 | **19 项全绿**；含结构性断言"模块内所有公开函数的签名都不含 `student_id`"（§17.1.2 边界 2） | 见下 |
| 07-29 | 全仓测试规模 | `make check` 实跑：**416 项全绿**（契约 168 / Seed 32 / 六个确定性服务 216）；`make llm-free` 六个服务各自三层扫描通过 | `b598d5b` |
| 07-29 | **WP5-7 Event Monitor & Replan**：去抖 + AffectedScope（同时给出受影响与**不受影响**范围） | **21 项全绿**；含"日历变化不波及 long_term 项"与"成绩变化可以波及"两条对照实测 | 见下 |
| 07-29 | **WP5-8 Publishing / Review / Audit**：越权拦截并留痕、状态机迁移、复审触发字段 | **22 项全绿**；三种越权原因逐条实测被拦且写入 `ScopeViolation`；改截止日期自动回到 `in_review` | 见下 |
| 07-29 | **WP5-9 Connector & Catalog**：三个统一适配器接口 + Source Health 八项 | **26 项全绿**；含结构性断言"EducationDataAdapter 没有任何写方法"与"BusyInterval 只有 start/end" | 见下 |
| 07-29 | **WP5 九个模块全部完成** | `make check` 实跑 485 项全绿（**该数字当时不可信，见下一行**） | `e628315` |
| 07-30 | **WP0 `infra/`**：bootstrap（默认 dry-run）/ verify（只读实测）/ moodle（单独）/ cost | 已 `--apply` 实建；`verify.sh` 实跑 **14 通过 0 失败**，含否定式检查"A4 无任何学生数据权限" | `f8788bc` |
| 07-30 | **独立 subagent 审查**（Codex 逾时无结论，按 CLAUDE.md 改用 subagent）：契约层 14 条 + 确定性服务 13 条 | 两份报告的每条结论都附可复现命令与实测输出 | — |
| 07-30 | 🔴 **修复：`make check` 在测试失败时返回 0** | 注入必失败测试实测：修前 exit 0，修后 exit 1；`scripts/check_make_fails.sh` 正反双向自检并入 `make check` | `f8788bc` |
| 07-30 | 🔴 **修复：AI Studio 防线盯的是已被取代的包** | 改为按**用法**判定；9 个探针；上线当场拦下自己的禁用词表、`verify.sh` 与新代码 | `f8788bc` |
| 07-30 | 🔴 **修复：先修解析器读错 4 条真实表达式**（2 条假阳性 / 1 条假阴性 / 1 条潜伏） | 四条各成回归测试；解析率 95.9% 之外新增"可行动率" 91.8% | `f8788bc` |
| 07-30 | 🔴 **修复：聚合的分组维度收下就丢，k-匿名抑制被架空** | 2 人格子曾拿全校 102 人分母报 98%（真实 0%）；改为逐格聚合逐格抑制 | `6fd021b` |
| 07-30 | 🔴 **修复：只有 `submit()` 检查授权** | 未注册者曾可 `publish()` 到学生端广场且不留记录；每次迁移都过角色检查，分类逐个校验 | `6fd021b` |
| 07-30 | 🔴 **修复：B8 闸门只查签发、不查判定** | 一条真实签发的"先修不满足"曾能背书计划项；新增 verdict 层 + 覆盖资格结论 + 四种失败分别报错 | `8e15b5e` |
| 07-30 | 🔴 **修复：`model_copy(update=)` 绕过全部 validator** | 通杀 B1/B2/B3/B6/B9；改为重新校验，冻结记录直接拒绝——**当场暴露一个没人报告的 bug**：`update_published` 置 in_review 却不指派审核人 | `8e15b5e` |
| 07-30 | 🔴 **修复：Wellbeing 三处误升级**（B6） | 真有 35% 余量的学生收到 blocking；空计划学生被报 100% 占用；碎片剔除在真实管道从未执行 | `dcc7791` |
| 07-30 | 🔴 **修复：零 LLM 扫描第二层对真实发行名无效** | 九份 sed 复制一起失效；改为共用四层扫描，新增动态导入与裸 HTTP 层，两种绕过实测拦下 | `5053c4e` |
| 07-30 | 修复：资格判定四条（needs_confirmation 被掩盖 / 日期是编的 / `mandatory` 从没被读过 / GPA 阈值取第一个数字） | 各附回归测试；`mandatory` 与 GPA 两条实测能造成假阳性 | `5053c4e` |
| 07-30 | 修复：去抖会饥饿、长期项保护静默失效 | 每 80 秒改一次日程的学生曾一小时不被重规划；`horizon_of` 改为必填 | `5053c4e` |
| 07-30 | 修复：边界扫描的 7 条加固（手写清单 / 凭据词 / 豁免自授 / `Any` 逃逸口 / CohortDims 自由文本 / 不透明凭据 / 未 rebuild 模型） | 新增模型的变异实测：加一个 `RawCalendarEvent` 当场变红 | `7863d26` |
| 07-30 | **WP4-1 Mock Campus REST**：SIS / Degree Audit / Catalog / Timetable / Opportunities / Calendar / Source Health | **27 项**；含"响应类型必须就是契约类"的断言；**真实 uvicorn + curl 实测**每个端点 | `656714c` |
| 07-30 | **WP6-1 Agent 安全契约**：工具白名单双重强制、四种 Workflow 用法、Vertex-only 运行时守卫 | **44 项，全部不调模型**；守卫对真实环境实测报出"这台机器会走 AI Studio" | `d8dd677` |
| 07-30 | **WP6-2 A0–A5 六个 Agent + Spec §19 十七步 Demo 故事** | **66 项**；步骤 2 断言容量链路模型调用数为 0；步骤 7 断言注入串不出现在 system prompt；步骤 9 断言违规计划永不被返回 | 见下 |
| 07-30 | **WP4-3 API 29 个契约端点全部实现** | **33 项**；`test_every_contract_endpoint_is_implemented` 断言 pending 集合为空；501/503 语义分开（没做 vs 依赖不可用）| 见下 |
| 07-30 | 发现并修复第 10、11 个坑（**真实 HTTP 实测发现，TestClient 没覆盖**） | ① `why-not-recommended` 缺 import 直接 500；② 确定性 `validation_id` 与每次变化的 `evaluated_at` 冲突，**同一端点第二次调用必炸**——"不可改判"指的是判定，不是计算时刻 | 见下 |
| 07-30 | **WP4-2 CampusPath API**：RBAC 中间件（角色表来自契约）+ B8 部署边界闸门 + 契约覆盖双向断言 | **24 项**；真实 HTTP 实测：无角色头 403、Curator 访问 wellbeing 队列被拒、伪造 `validation_id` 被 422 拒并说明"从未被 Rules 签发" | 见下 |
| 07-30 | **上下文交接引擎**（70% 提醒写断点 / 80% 自动 compact / 压缩后与新窗口自动注入 / 右上角系统通知 / 双层锁定只在本项目生效），见 `.claude/hooks/README.md` | 自检 **33 项全绿** + **六次变异**各自只让对应项变红；真机实测：`claude -p` 确认注入的标记进了新会话上下文、PreCompact 落盘 `facts.md`、Stop 拦截在本会话真实触发两次；全局 Polymarket handover 已收窄到它自己的仓库（四个 cwd 反例实测）；上下文窗口分母改为按模型判定（曾把 1M 当 200k，18% 误报成 95.5%），用本会话真实 transcript 实测 `{tokens:198904, pct:20.3, limit:980000}` 与状态栏一致 | `3e5a908` `957e94b` `1bea7f5` |

---

## 工作包状态

| WP | 内容 | 状态 | 备注 |
|---|---|---|---|
| WP0 | 仓库与基础设施 | ✅ 完成 | git + 密钥防护 + preflight + Makefile + Python 工作区 + `infra/` 四脚本（已实建并实测）|
| WP1 | 契约冻结（Schema / OpenAPI） | ✅ 完成 | 110 模型 / 29 端点 / 168 测试；产物一致性由 `make contracts-check` 守住 |
| WP2 | 合成数据设计 | ✅ 完成 | Data Dictionary、确定性生成器、3 深度 Persona、Gold Set、16 类失败样本、16 项一致性检查 |
| WP3 | Moodle Sandbox + MCP | ✅ 完成 | GCE `campuspath-moodle` 实建（9 课 12 学生 80 注册，夜间停机）+ `mcp/moodle_mcp` 白名单只读链（SSH 隧道真链路实测）。**余项**：adapter 挂进 A2 工具带（backlog） |
| WP4 | Mock Campus REST + CampusPath API | ✅ 完成 | Mock Campus 七端点全通；CampusPath API 契约 1.2.0 全部端点实现（53 路径 59 操作），`/reflections`、`/ops/opportunity-drafts` 已转真实现 |
| WP5 | 确定性服务平面（9 模块） | ✅ 9/9 | 全部完成，各自独立成包、各自通过三层零 LLM 扫描 |
| WP6 | A0–A5 Agents | ✅ 接线完成 | 六个 Agent + 安全契约；API 真正调用 Agent 库（divergence/reflections/drafts/matches/low-load 试算），`_require_model` 已无调用者 |
| WP7 | 学生 Web App | ✅ 完成 | 14 页 + 双语 + 双门户拆分；两轮功能优化（U1–U8、A–O）全部浏览器实测落地；divergence_points 已接 A3 |
| WP8 | Publisher / Career Center | ✅ 完成 | 投稿台四条分支 + 校方控制台 + Advisor 工作台；隔离验证可见面板（5 个禁区端点 403） |
| WP9 | Calendar & Wellbeing 切片 | ✅ 完成 | outreach 同意分支（200/403）、两次提醒状态机、提醒面板双语实测；日历 OAuth 用户拍板用夹具 |
| WP10 | Evaluation Harness | ✅ 完成 | `make eval`：**13/13 BLOCKER · 11/12 TARGET（T11 75% 如实红）· BL1–BL5 全产出**，判定类双跑逐字节一致，达 D6.7 |
| WP11 | 延迟优化与 Demo 装配 | 🟡 就绪待彩排 | `docs/demo-runbook.md` 十七步对照已编制；`/matches` 冷 22s/热 2.3s（演示前热身）；余：全流程彩排 + 录屏 |

---

## 关键决策记录

| 日期 | 决策 | 理由 |
|---|---|---|
| 07-28 | A2 拆分为 Academic Agent + Capacity & Calendar Service | 学业记录 / 日历 Token / 健康数据本属三个独立数据域，不应合并进同一 LLM 上下文 |
| 07-28 | Wellbeing 全链零 LLM | 五信号判定皆为纯阈值，无语义收益；这是全产品风险最高的数据类别 |
| 07-28 | A5 为唯一 trade-off Agent | 让"为什么推荐这个"只有一个解释来源，KPI 有唯一责任方 |
| 07-28 | 资源利用率指标补 E32/E33 通往校方的通路 | 原设计声明了"匿名聚合给校方"但架构图上无任何箭头承载，属漏洞 |
| 07-29 | **模型调用只走 Vertex AI** | 官方文档明确 AI Studio 的 Gemini API 不吃赠金，会直扣个人信用卡 |
| 07-29 | 删除"AI Studio API Key 作为本地开发 fallback" | 它正是绕过赠金的路径；本地开发同样走 ADC |
| 07-29 | HKUST 真实课程目录直接抓取使用 | 公开目录、无学生数据；先修表达式是 Rules Engine 的真实素材，优于编造 |
| 07-29 | OpenAPI **声明式定义**（`campuspath_contracts/openapi.py`），不从 FastAPI 反推 | 从实现导出的契约永远落后实现一步，而 WP1 的全部意义是契约先于实现 |
| 07-29 | 边界约束用**字段名递归扫描**，不只靠 `extra="forbid"` | 后者挡不住"日后在 `AvailabilityBlock` 上加一个 `title`"——那会让 B5 在无测试变红的情况下被破坏 |
| 07-29 | `validation_id` 查**两层**：正则形状 + Registry 签发 | 只查形状挡不住模型编一个格式正确的 id；只查签发则缺字段的输出在到达闸门前已扩散 |
| 07-29 | `uncovered_requirement_categories` 用枚举而非自由文本 | 出域字段里最有价值也最危险的一项；自由文本能反推到具体学生（B10） |
| 07-29 | 先修表达式在契约层保留**来源原文**，不存解析结果 | 解析是 Rules 的职责；保留原文才能满足 D6.5「冲突时以来源原文为准」 |
| 07-29 | HKUST 课程快照 `courses.json` **入库冻结**（HTML 缓存不入库） | Gold Label 与它绑定，学校随时可能改页面；不冻结就谈不上"评委每次看到一致情景" |
| 07-29 | Gold Label 的判定逻辑**故意与 WP5 的 Rules Engine 分开写** | 用同一份代码生成标签又用它评测，等于自己给自己打分 |
| 07-29 | Gold Set 四态**各取 15 条**，不按顺序采样 | 顺序采样会得到几乎全是 `eligible_now` 的集合，T2（比 T1 更要紧）根本测不出来 |
| 07-29 | tiny 档靠"只建一个培养方案"缩小，**不**靠"只保留 N 门课" | 后者会让培养方案引用到被裁掉的课程，造出 Spec §11.5 明令禁止的跨表矛盾 |
| 07-29 | Persona A 刻意**不设置**睡眠窗口与恢复偏好 | B6 需要一个反例样本：日历再忙也不得升级。没有反例，"零误升级"只是没触发过 |
| 07-29 | 先修判定用**三值逻辑**（MET / NOT_MET / **UNKNOWN**） | 解析器的无能只能变成"待确认"，绝不能变成"你不满足"——后者正是 Spec §16.2 第 5 条禁止的以推断淘汰 |
| 07-29 | `(For DDP only) X; (For all others) Y` 判为 UNKNOWN，**不**当成 `X OR Y` | 当成 OR 会让不属于该项目的学生凭 X 通过，直接推高 T2 假阳性 |
| 07-29 | 课程类资格未满足判 `future_eligible` 而非 `ineligible` | 课程可以补修；判成本轮不合格等于替学生把路堵死 |
| 07-29 | 资格凭据 `expires_at` 绑定机会截止日期 | 资格随截止与名额变化，永久有效的凭据会让过期结论继续背书计划 |
| 07-30 | 未实现的 API 端点返回 **501 而非空数组** | 空数组会被前端当成"这个学生没有结果"，而事实是这条路还没接。空数组是一种会被信以为真的谎 |
| 07-30 | 未实现端点由契约**自动补齐**，不靠人维护 pending 名单 | 覆盖率因此是构造性的：契约里有的，一定有路由 |
| 07-30 | RBAC 中间件的角色表**只从契约生成**，不重列一份 | D5 的隔离验证若靠两份表保证，迟早出现"契约写了、中间件漏了" |
| 07-30 | 路由匹配用自建索引，不读 `app.routes` | 新版 FastAPI 把子路由包成 `_IncludedRouter`，依赖框架内部结构的代码升级时会静默失效——而这里失效意味着**中间件全程放行** |
| 07-30 | Agent 层用 `ModelClient` 协议 + 确定性桩，**Agent 正确性不依赖能否调通模型** | §19 里可验证的性质是结构性的（提案 pending、候选无分数、每项带凭据、A4 只出草稿）。用真模型测只会更慢更贵更不稳定，而且没 ADC 的机器根本跑不了。语义质量归 WP10 评测 |
| 07-30 | `ModelRequest` 把 system 与 data **分成两个字段** | §8.9.1 第 1 条要求外部内容永不拼进 system prompt。分开之后，"拼进去"需要刻意去做，而不是顺手 |
| 07-30 | `ScriptedModel` 遇到未预设的 purpose **抛异常**，不返回空串 | 空串会让 Agent 走进"模型没说话"的分支，而测试作者以为自己测的是正常路径 |
| 07-29 | 睡眠与用餐**不**从"每周可支配成长时间"里再扣一次 | 它们本就不在成长时段内。重复扣会让每个学生都算出大幅负容量，于是 B1 的超载告警彻底失去意义。它们仍进 AvailabilityBlock，因为 B2 要靠它们挡排程 |
| 07-29 | 规划信号（§16.6）与 Wellbeing 信号（§16.8.2）**分成两个模块** | 前者只调计划、无前置条件；后者进最高风险数据类别、必须有学生显式设置。混在一起就会出现"日历满 → 判定健康风险"这种 B6 禁止的推断 |
| 07-29 | `PlanningSignal.suggested_action` 只允许四种取值 | §16.6 明确这些信号"不能自动下医学结论"。做成类型层拒绝，比写在注释里可靠 |
| 07-29 | 提醒模板是**带占位符的格式串**，实测值由确定性代码填充 | 既保证"不代表任何医学诊断"100% 出现，又能说出"7 天中 2 晚"这种具体数字——模型生成两头都不保证 |
| 07-29 | Action & Consent 拆成 preview → approve → execute **三次调用** | `execute` 的参数类型就是回执，"没有同意就执行"因此在类型上做不到，而不是靠调用方记得判断 |
| 07-29 | 同意回执绑定预览内容的**指纹** | 防"确认了 3 个时段、执行时变成 30 个"。改一个字节回执就失效 |
| 07-29 | 分组维度超限时**拒绝**而非抑制 | 抑制会让使用者以为"再筛细一点就有数了"，反而诱导他们去找可识别的组合 |
| 07-29 | 质量聚合按时间衰减（半衰期 365 天） | 活动会改进；三年前的差评不该和上个月的一样重，否则整改没有回报 |
| 07-29 | 去抖保留**最后一条**而非第一条 | 学生连改三次日程，该重算的是最终状态 |
| 07-29 | `LOCAL_ONLY_TRIGGERS`：日历变化与超载不波及 `long_term` 项 | Spec §16.9「只重排冲突项并恢复缓冲，不推翻无关长期目标」。成绩变化则可以波及——它影响先修链，不是一刀切 |
| 07-29 | 越权异常里**带着 `ScopeViolation` 对象** | 逼调用方把它写进审计。B7 的判定包含可追溯，只拦不记不算通过 |
| 07-29 | Source Health 的比率在"没检查过"时返回 1.0 | 没检查过 ≠ 全都坏了。用 freshness 去暴露"根本没跑过"，避免面板上一片红 |

---

## 已知缺口清单（2026-07-31 全盘扫描，两个只读 subagent 交叉产出）

**架构性发现（归 WP6，不动大框架，属"把 API 临时实现替换为调用已建好的 Agent 库"）**：
`agents/campuspath_agents/roster.py` 的 A0–A5 六个 Agent 类**从未被 `app.py` 导入**——
ToolBelt 白名单、`assert_vertex_only` 只在单测里生效，真实 API 路径裸调 `model.generate`。
连带：F03/F08 的 divergence_points 恒空（`GoalGapAgent.compare_goals` 已写好未接）；
F09 `/ops/opportunity-drafts` 与 F14 `/reflections` 是**硬编码 503**（配好模型也 503，
语义上其实是"还没做"应为 501）；F11 `/matches` 入口无条件 `_require_model()`，
但模型只用于理由文案且已有兜底——没配 ADC 时整个 For You 页 503。

**前端死按钮（归 WP7，UI 在、后端没接）**：Reflection 保存无 onClick；Profile Proposal
确认/拒绝未调 decision 端点；Memory 纠正/忘记无 onClick、锁定只改本地 state（契约无
lock 端点，归 WP1）；Settings 导出/删除无 onClick（契约无 export/delete 端点，归 WP1）；
Action Center 日历批准只改本地 state、拒绝无 onClick；Resume 导入无入口。

**数据层（归 WP2）**：合成机会四类标题词表 + ORGANIZERS 为纯中文，`title_localized`
恒 None → 英文态广场/For You 大部分标题仍中文；`series_id` 把中文拼进 ID。

**评测（归 WP10）**：BASELINE 五项零实现（harness 只有枚举）；T11 75% 且判据是
Persona 脚本自评；T1/T2/T3 满分 = rule_generated 自评，**R8 人工复核未做**（需用户）；
T9/T10 口径不含模型调用与前端渲染（报告已如实注明，Demo 时须口头澄清）；
B12 只有静态扫描，建议补运行时后端类型自检；D6.7 的 10/12 门槛不加权关键项。

---

## 待验证 / 待确认

| 项 | 说明 |
|---|---|
| Agent Engine / Registry / Gateway 可用性 | 未实测。不可用则走 Plan R1 降级（自托管 Cloud Run） |
| Memory Bank 可用性 | 未实测。不可用则走 R2（Firestore + embedding） |
| Counseling 测试邮箱 | 待用户提供（Plan §5 非阻塞项 4） |
| Gold Label 复核安排 | 待用户确认（Plan §5 非阻塞项 5） |
| `phd-to-industry` Career Path Pack | 待交付；未交付则前端不显示、不宣称 |
| Counseling 测试邮箱 / Calendar OAuth / Moodle token | `infra/verify.sh` 实测三个 Secret **存在但没有值**；用到它们的功能会在运行时失败。值由用户注入 |
| Moodle VM | 未创建。唯一有实质月成本的资源（约 HK$195/月），`bash infra/moodle.sh create --apply` 按需开 |

---

## 踩过的坑

**清单在 `CampusPath_Implementation_Plan_V2.md` §10.2**，本文件不复制，避免两处不同步。

新踩到坑时：先写进 Plan §10.2（那里是唯一出处），再在本文件"已完成"表里记一行"发现并修复 X"。

截至 07-30 共 11 条。第 10、11 条是**真实 HTTP 实测**发现的，TestClient 那 31 项测试全绿——因为它们没调过那个端点，也没有任何一条测试连着调两次同一个端点。

前 9 条全部是靠"用已知会失败的样例测检查器"发现的——没有一条是靠通读代码发现的。这是 §10 H5 准则存在的理由。

第 7 条尤其说明问题：同一个误报（"提到它以禁止它" vs "调用它"）换了个位置又犯了一次，先是文档、后是代码。后来它还在第三处（契约测试按文件名豁免）和第四处（`infra/verify.sh`）出现过。修检查器时要问的是"这个区分在别处还成立吗"。

第 9 条是最贵的一条：**`make check` 在测试失败时返回 0**，因此此前每一句"全绿"都是用一条不可能失败的命令断言的。它不是被 H5 抓到的，是被独立审查者抓到的——H5 管的是"我写的检查器会不会失败"，这条是"跑检查器的那层会不会把失败传出来"。两者都要有人盯。
