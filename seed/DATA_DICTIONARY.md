# Synthetic Campus Sandbox —— Data Dictionary

Seed 版本：`seed/1.0.0` · 数据基准日：**2026-09-15**（2026-27 秋季学期期中）

全部页面与数据集标记 `Synthetic / Demo Data`。

## 真实 vs 合成，界线在哪

| 数据 | 来源 | 说明 |
|---|---|---|
| **课程目录**（代码、名称、学分、先修/互斥表达式、CILO） | **真实**：HKUST 公开本科课程目录 | 公开页面，**不含任何学生数据**。先修表达式原文保留（如 `(COMP 2011 OR COMP 2012 OR COMP 2012H) AND (COMP 2711 OR ...)`），是 Rules Engine 先修解析的天然测试素材 |
| 开课时段、班次、名额、考试时间 | 合成 | 学校不公开；我们需要可控的冲突与满额情形做失败样本 |
| 培养方案与毕业要求组 | 合成 | 参考真实开课结构，学分与分组是我们定的；不是校方 handbook 的复刻 |
| 学生、成绩、日历、经历、证据、机会、Publisher、反馈 | **全部合成** | 无真实姓名、邮箱、学号、成绩。`StudentProfile` 契约本身就没有姓名字段 |

课程快照 `seed/raw/hkust_catalog/courses.json` **入库冻结**：Gold Label 与它绑定，
学校随时可能改页面，不冻结就谈不上"评委每次看到一致情景"。HTML 缓存不入库。

## 生成与校验

```bash
make seed          # 生成 full + tiny
make seed-reset    # 删除旧产物重新生成，并做两次构建的字节比对
make seed-check    # 16 项跨表一致性校验
make seed-selftest # 用 16 个已知矛盾验证检查器真的会报错
```

产物在 `seed/generated/<profile>/`（不入库，由生成器复现），每份带
`manifest.json`：Seed 版本、基准日、各表记录数与 SHA-256 校验和前 16 位。

## 两个规模档位

| 档位 | 用途 | 内容 |
|---|---|---|
| `full` | Demo、评测、验收 | 3 培养方案 / 12 学生 / 96 课程 / 143 机会，满足 Spec §11.2 全部下限 |
| `tiny` | smoke 与单测（Plan §10.5） | 1 培养方案 / 1 Persona，构建 < 0.1 秒 |

`tiny` 靠**只建一个培养方案**缩小，而不是"只保留 N 门课"——
后者会让培养方案引用到被裁掉的课程，造出 Spec §11.5 明令禁止的跨表矛盾。

## 三个深度 Persona 各自承担什么

不是三个差不多的学生，每个都是某类必须被演示到的情形。

| Persona | 方案 / 年级 | 承担的演示 | 关键设定 |
|---|---|---|---|
| **A · Explorer** | BSc COMP / 大二 | G3 多目标（主 + 候选）、发现成本、**B6 反例** | **未设置睡眠窗口与恢复偏好** → 日历再忙也不得产生 wellbeing 升级 |
| **B · Sprinter** | BBA ISOM / 大三 | Wellbeing 垂直切片、容量超载重规划 | 已设睡眠窗口 00:30–07:30、周六照护硬约束、6 项既有承诺 → 每周可支配容量为负 |
| **C · Pivoter** | BEng IEDA / 大三 | Goal Review、主/候选目标分叉、课程取舍 | 主目标信心 0.35 且下滑，候选目标 0.55；有签证类约束 |

另有 9 名精简学生（STU-D…STU-L），覆盖四个年级与五种发展模式，
用于让分组聚合达到 `MIN_CELL_N`。

## 数据表

| 文件 | 契约类型 | 记录数（full） | 说明 |
|---|---|---:|---|
| `programs.json` | `AcademicProgram` | 3 | BSc COMP / BBA ISOM / BEng IEDA |
| `degree_requirements.json` | `DegreeRequirement` | 18 | 每方案 5–7 个要求组 |
| `courses.json` | `CourseCatalogItem` | 96 | 真实课程数据 |
| `course_offerings.json` | `CourseOffering` | 558 | 含 `full` / `waitlist` 状态，供"满额"样本 |
| `students.json` | `StudentProfile` | 12 | 无姓名字段 |
| `student_display.json` | — | 12 | 展示化名，一望即知是化名 |
| `student_course_records.json` | `StudentCourseRecord` | 184 | 按先修层级顺序排入历史学期 |
| `experiences / projects / achievements / skills / evidence / notes` | 对应契约 | 4 / 3 / 2 / 8 / 7 / 3 | 深度 Persona 才有 |
| `goals.json` | `Goal` | 14 | 主目标 + 候选目标 |
| `calendar_connections.json` | `CalendarConnection` | 3 | **无 token 字段** |
| `availability_blocks.json` | `AvailabilityBlock` | 588 | 6 周 × 3 人；**无标题/参与人/地点** |
| `capacity_snapshots.json` | `CapacitySnapshot` | 18 | 满足 §16.6 公式；超载与不超载都有 |
| `opportunities.json` | `Opportunity` | 143 | 含为失败样本额外注入的 3 条 |
| `opportunity_meta.json` | — | 140 | 每条机会的**生成规则**（Spec §11.5） |
| `publisher_grants / publication_submissions / moderation_decisions / scope_violations` | 对应契约 | 10 / 24 / 17 / 4 | 状态机每个终态至少一个样本 |
| `event_quality_feedback.json` | `EventQualityFeedback` | 40 | **无 student_id、无自由文本** |
| `metric_tuples.json` | `MetricTuple` | 12 | 出域元组，B10 的实物 |
| `profile_update_proposals / profile_change_events` | 对应契约 | 24 / 20 | 含确认 / 修改 / **拒绝** / 待定四种分支 |
| `memory_entries.json` | `MemoryEntry` | 15 | 含 `rejection` 类型，T6 的判据来源 |
| `gold_set.json` | — | 见下 | Gold Label |
| `failure_cases.json` | — | 16 | Spec §11.3 十六类**全覆盖** |

所有记录在序列化前都是契约层的模型实例，已过 Pydantic 校验：
数据集里不可能出现违反 B1/B2/B3/B6/B9 的记录，因为那些对象根本构造不出来。

## Gold Set

| 数据集 | 数量 | 下限（D6.5） | 内容 |
|---|---:|---:|---|
| 四态资格 | 60 | 60 | 四态**各 15 条**——只按顺序取样会得到几乎全是 `eligible_now` 的集合，那样 T2 根本测不出来 |
| 课程约束 | 40 | 40 | 要求组归属、先修状态、开课学期、课表冲突 |
| 重规划情景 | 12 | 12 | 覆盖 `ReplanTriggerType` 全部 11 类，每条都写明**不受影响**的范围 |
| 失败样本 | 16 类 | 12 类 | 见下 |
| 记忆回归 | 20 | 20 | 已拒绝 / 已完成事项，验证不重复推荐 |

**标注状态**：全部为 `rule_generated`（Plan R8：先规则生成初版，人工只做复核）。
**人工复核完成前，用它算出来的 T1/T2/T3 只是自评，不能当作已验证的准确率。**
复核安排见 Plan §5 非阻塞项 5。

每条标签都带 `reasons`，写明判定依据并引用规则原文（D6.5 规则②）；
冲突时以来源原文为准，不以模型输出为准（规则③）；
Gold Set 带 `seed_version`，冻结后改动须 bump（规则④）。

Gold Label 的判定逻辑**故意与 WP5 的 Rules Engine 分开写**——
用同一份代码生成标签又用它来评测，等于自己给自己打分。

### 四态合并优先级

一条机会有多条规则时按此优先级合并，写在 `goldset.STATE_PRECEDENCE`：

```
ineligible_current_cycle > future_eligible > needs_confirmation > eligible_now
```

`eligible_now` 排最后是刻意的：它直接对应 T2（把不合格判成可申请），
这是比 T1 更要紧的指标。

## 失败样本（Spec §11.3 十六类全覆盖）

| # | 类别 | 期望行为 | **不许做什么** |
|---:|---|---|---|
| 01 | 已过期但页面仍在线 | 判 `ineligible_current_cycle` | 不得因页面可访问就当作可申请 |
| 02 | 大一不合格、大三可达 | 判 `future_eligible` + 桥接行动 | 不得永久删除 |
| 03 | 年级要求含糊 | 判 `needs_confirmation` | 不得按统一年级假设淘汰 |
| 04 | 两来源截止日期冲突 | 标记冲突并显示两个日期 | 不得静默取其一 |
| 05 | 标题不同、内容重复 | 去重合并并保留两条来源 | 不得同时进 Top-N |
| 06 | 宣传好、反馈持续差 | 下调质量置信度并替换 | 不得输出个体反馈原文 |
| 07 | 活动优质但对该生过于基础 | 个人适配降权 | 不得据此下调**全局**质量分 |
| 08 | 与课程或休息边界冲突 | 显示 blocking 冲突 | 不得静默排进保护区块 |
| 09 | 工作量字段缺失 | 标记 uncertainty | 不得默认按 0 小时排 |
| 10 | 已做过同类活动 | 不再推荐或说明差异 | 不得换名重复推荐 |
| 11 | 职业目标满足但毕业学分不足 | Rules 拒绝并指出缺口组 | 毕业硬约束不得被职业分抵消 |
| 12 | 先修未满足 / 不开设 / 满额 / 冲突 | 四种情形分别判定 | 不得统一显示「不可选」 |
| 13 | 日历空档实为保护时间 | 不计入 Usable Free Time | 不得当成可压缩空档 |
| 14 | Resume 提取错误 / 证书过期 / 拒绝写入 | 保留事件不写 Profile | 不得静默写入 Canonical Profile |
| 15 | 越权投稿（四种原因） | 全部拦截并留痕 | 不得只拦不记 |
| 16 | 更新未复审 / 取消仍显示 | 回到 `in_review`；下架 | 不得跳过复审直接 published |

每条都写明**不许做什么**——只写期望行为的样本无法证伪。

## 一致性校验

`make seed-check` 跑 16 项跨表检查：课程/学生/证据引用、先修顺序、机会 id 唯一、
Gold Set 引用与判定依据、四态覆盖、发布方引用、MetricTuple 去标识、
真实 PII 形状扫描、Synthetic 标记、规模下限、Gold 下限、失败样本可证伪、
被拒绝的提案未写入。

`make seed-selftest` 往数据集里注入 16 个**已知矛盾**，逐个断言**对应的那一项**
检查确实失败。只断言"有检查失败"是不够的——那样一个过于宽泛的检查会掩盖其余全部失效。

## 确定性

- 时间基准是常量，不是 `date.today()`；
- 随机性一律经 `rng.stream(namespace)` 按命名空间派生，改一张表不会让其他表整体错位；
- 种子由 SHA-256 派生，不用内置 `hash()`（它带 `PYTHONHASHSEED` 随机化）；
- 遍历一律排序，不依赖 dict/set 迭代序；
- `make seed-reset` 会做两次构建的**字节比对**，不一致即报错。
