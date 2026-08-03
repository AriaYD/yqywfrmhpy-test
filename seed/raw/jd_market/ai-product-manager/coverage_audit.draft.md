# AI Product Manager JD 语料库 — 覆盖率与频次审计

生成方式：对 `jd_corpus.draft.json` 做程序化统计（`python3 -c "import json..."`），非估算。
校验脚本同时断言了每条 `category` 落在 Spec 规定的枚举内（hard 7 类 / soft 9 类 / constraint 5 类），零违例。

## 每家公司行覆盖率

| # | 公司 | JD 标题 | requirement_lines 行数 (lines_total) | 已映射行数 (lines_mapped) | 覆盖率 | 拆解出的要点数 (points) |
|---|------|---------|---:|---:|---:|---:|
| C01 | 字节跳动 ByteDance | AI产品经理（评测方向）-TikTok | 7 | 7 | 100% | 11 |
| C02 | Google | Product Manager, Retrieval-Augmented Generation and Embeddings | 10 | 10 | 100% | 11 |
| C03 | Microsoft | Senior AI Product Manager | 9 | 9 | 100% | 14 |
| C04 | OpenAI | Product Manager, API Agents | 5 | 5 | 100% | 7 |
| C05 | Anthropic | Product Manager, Enterprise | 19 | 19 | 100% | 21 |
| C06 | 美团 Meituan | AI产品经理-小美Agent方向 | 6 | 6 | 100% | 13 |
| C07 | 腾讯 Tencent | 腾讯会议-AI产品经理-企业应用方向 | 4 | 4 | 100% | 9 |
| C08 | 阿里巴巴 Alibaba | ATH-AI创新事业部-产品经理-AI Agent | 7 | 7 | 100% | 16 |
| C09 | 小红书 Xiaohongshu | AI 产品经理-商业化 / 电商 | 8 | 8 | 100% | 16 |
| C10 | 科大讯飞 iFlytek | AI产品经理 | 5 | 5 | 100% | 12 |
| **合计** | — | — | **80** | **80** | **100%** | **130** |

说明：
- `lines_total` = 该公司 JD「岗位要求/任职资格」段原文的行数（逐条编号或逐条项目符号）。
- `lines_mapped` = 有 ≥1 个 point 映射到该行的行数；全表 80/80 = 100% 覆盖，无遗漏行。
- Anthropic 行数最多（19 行），因其 JD 结构为 Minimum qualifications（5）+ Preferred qualifications（10）+ Logistics 中与任职资格强相关的学历/地点/签证条款（4），后者用于补齐 constraint 层样本，已在 `original_excerpt` 中如实注明来源小节。
- 腾讯行数最少（4 行），JD 原文任职要求本身只有 4 条编号项。

## 全语料 category 出现次数统计（130 个 point 的分布）

### 按 layer 汇总

| layer | 出现次数 | 占比 |
|---|---:|---:|
| hard | 71 | 54.6% |
| soft | 56 | 43.1% |
| constraint | 3 | 2.3% |
| **合计** | **130** | 100% |

### 按 category 汇总（降序）

| category | layer | 出现次数 |
|---|---|---:|
| technical_skill | hard | 26 |
| credential | hard | 19 |
| project_portfolio | hard | 15 |
| execution | soft | 12 |
| education_degree | hard | 11 |
| communication | soft | 10 |
| data_sense | soft | 9 |
| user_empathy | soft | 7 |
| teamwork | soft | 6 |
| ownership | soft | 4 |
| learning_agility | soft | 4 |
| influence | soft | 3 |
| leadership | soft | 1 |
| location | constraint | 1 |
| visa_identity | constraint | 1 |
| language | constraint | 1 |
| coursework/gpa | hard | 0 |
| internship | hard | 0 |
| competition | hard | 0 |
| availability_duration | constraint | 0 |
| start_date | constraint | 0 |

零出现的类别（`coursework/gpa`、`internship`、`competition`、`availability_duration`、`start_date`）在这 10 份社招/资深岗 JD 中确实未出现对应表述——样本全部是有工作经验门槛的社招岗（1–10 年经验不等），JD 原文没有 GPA/在校课程、实习专项、竞赛背景或到岗时间/在职时长类条款；这是 AI PM 社招语料的真实特征，不是抽取遗漏（每行都已逐行核对映射，coverage 100%）。

## 复核方法

1. `python3 -c "import json..."` 对 `jd_corpus.draft.json` 做程序化解析，逐公司断言 `len(requirement_lines) == coverage.lines_total == coverage.lines_mapped`，10/10 通过。
2. 对每个 point 的 `(layer, category)` 组合做枚举校验（hard 7 类、soft 9 类、constraint 5 类），零违例。
3. 所有 `original_url` 均通过 chrome-devtools MCP 实际打开浏览器访问并抓取页面 `innerText` 确认内容存在（非 WebFetch 静态抓取，因多数中国大厂招聘站为 JS 渲染 SPA，静态抓取会拿到空壳）。
