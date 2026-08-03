# 求职拆解 Pack 编译方法论（A 提案六步的固化，2026-08-02）

> 用户提案：目标拆解要「可行可量化」——JD 语料 + 成功者履历比对 + 权威榜单 → 带权重的拆解。
> 架构裁定：**离线编译、运行时零模型**。岗位市场模型与学生无关（同一岗位对每个学生是同一份
> 市场事实），研究跑分钟级、要人工复核来源，所以编制期做一次、入库复用、可随时重跑刷新；
> 学生个人差距比对（A3 + 差距图）仍是运行时毫秒级。未覆盖岗位的「现场 AI 拆解 + 进度条」
> 见任务 #27（后台任务，切页不断）。

## 流水线（重跑即刷新）

```bash
# 数据草稿更新后：
python3 seed/compile_employment_pack.py
# 产物：agents/campuspath_agents/pack_data/employment_roles.json（运行时消费）
#       agents/campuspath_agents/pack_data/evidence_catalog.json（权威证据参考表）
#       docs/verification/pack-compiler/weights_audit.md（权重审计表）
```

| 步骤 | 数据 | 位置 | 采集方式（2026-08-02 实跑） |
|---|---|---|---|
| 1 JD 语料 | 每岗位 10 家头部公司 ≥1 份官方 JD | `seed/raw/jd_market/<role>/jd_corpus.draft.json` | sonnet 子代理 WebSearch/WebFetch/浏览器；URL 逐条实测可达；只存结构化抽取 + 关键句摘录（≤2 句），不整页转存 |
| 2 逐行拆解 | 每行 JD → 要点 → hard/soft/constraint 归类 | 同上（points 数组） | 覆盖率表强制 lines_total == lines_mapped（「禁止遗漏」的机器判定，编译器 assert） |
| 3 履历聚合 | 成功入职者证据画像（**去标识**：只存聚合计数） | `success_profiles_aggregate.draft.json`（可选） | **本轮未取得样本**：LinkedIn 免费账号的 search_people 返回匿名化「领英会员」，无法定位公开档案（2026-08-02 实测 4 组查询确认）。诚实降级为 JD-only 口径；换完整可见性账号后补跑该文件、重跑编译器即可 |
| 4 权威榜单 | 比赛/证书/活动 tier 化参考表 | `evidence_catalog.draft.json`（36 条） | sonnet 子代理调研；每条官方 URL 实测 200 才收录（PMP/CCPC 因不可核实被排除） |
| 5 权重合成 | core / standard | 编译器确定性规则 | **core ⇔ JD 公司覆盖率 ≥60% 或 履历出现率 ≥50%**；覆盖率按"有该要求的公司数/公司总数"（一家 JD 写三遍沟通只算一票） |
| 6 产出呈现 | 目标工作室拆解区 | goals 页 | core 加粗+下划线；market_note（两组实测数字）随行；evidence_refs 展开为可点官方链接 |

## 红线与已知偏差（如实呈现）

- **去标识裁定（用户拍板 2026-08-02）**：真人履历原文/姓名/链接一律不入库；仓库只允许聚合统计。
- **步骤 3 未执行**：见上表。审计表与 market_note 均不含履历数字，不虚构。
- **样本偏差**：AI PM 语料 10 份全为社招 JD（campus/GPA/比赛类目 0 次是语料特征而非抽取遗漏，
  见 coverage_audit.draft.md）；对本科生用户解读时，经验年限类要求应读作「用实习+项目对标」。
  SWE 语料为校招/初级向，无此偏差。
- **部分 JD 来自镜像站**（nowcoder/niuqizp/builtin，官方站为 SPA 无法静态抓取时），
  语料 JSON 逐条记录了 fetch 方式；镜像内容与官方职位帖同文，风险为镜像滞后。
- 运行时匹配是确定性关键词子串命中（`_match_role_profile`），未命中回落方向级通用 Pack，
  决不硬套。
