# contracts —— CampusPath 契约层（WP1）

**Schema 的唯一真相来源。** 前端 TypeScript 类型、Agent 输出校验、Mock 服务、
评测断言全部从这里生成或导入。契约先于实现存在，不是从实现反推的文档。

```
contracts/
├── campuspath_contracts/     Pydantic 模型（唯一手写来源）
├── schema/                   导出的 JSON Schema（每模型一份 + _index.json）
├── openapi/campuspath.json   Agent ↔ 服务的 OpenAPI 3.1 合同
├── generated/                从 OpenAPI 生成的前端类型
├── scripts/export_schemas.py 导出器（支持 --check）
└── tests/                    契约测试
```

## 常用命令

```bash
make smoke            # < 1 秒，最常用
make test             # 契约测试全量
make contracts        # 重新导出 schema/ 与 openapi/
make contracts-check  # 断言磁盘产物与代码一致
make types            # 从 OpenAPI 生成前端 TypeScript 类型
```

改了 `campuspath_contracts/` 里的任何模型，**必须**跑一次 `make contracts`，
否则 `test_disk_artifacts_match_the_code` 会红。

## 这一层强制了哪些红线

契约层不是"数据结构的集合"，它是 D6 里若干 BLOCKER 的实现位置。
每条都有对应测试，且测试本身用**已知会失败的样例**验证过（Plan §10 H5）。

| 红线 | 在契约层怎么落地 | 测试 |
|---|---|---|
| B1 Capacity Violation | `CapacitySnapshot` 校验 §16.6 公式；超载未标警告即拒绝构造 | `test_capacity_and_schedule.py` |
| B2 Protected Block Violation | 含 blocking 冲突的 `ScheduleProposal` 进不了 approved | 同上 |
| B3 Unconfirmed Profile Write | 拒绝的提案不得 bump 版本；确认必须恰好 +1 | `test_profile_write_path.py` |
| B4 Private Reflection Exposure | `EventQualityFeedback` 无任何自由文本字段，是 A1 通往聚合的唯一类型 | `test_boundary_guards.py` |
| B5 Calendar Detail Over-collection | 遍历 `calendar` 模块**全部**模型，扫日历详情词与凭据词（不是手写清单） | 同上 |
| B6 Wellbeing False Escalation | 无学生显式设置就构造不出 sleep/recovery 信号 | `test_wellbeing_contracts.py` |
| B7 Unauthorized Publication | 契约层只提供**迁移表与判定 helper**，强制在 `services/publishing`（每次迁移都过角色检查） | `test_publication_state_machine.py` + `services/publishing/tests` |
| B8 Unbacked Plan Item | `validation_id` 必填 + 正则 + 查签发 + **查 verdict 能否背书** | `test_validation_binding.py` |
| B9 Metric Re-identification | 样本量 < `MIN_CELL_N` 必须抑制数值；分组维度层数受限 | `test_aggregation_privacy.py` |
| B10 MetricTuple Field Leakage | 字段白名单 + `extra="forbid"` + 字段名递归扫描 | `test_boundary_guards.py` |
| B11 LLM-free Path Integrity | 四层：运行时 / 依赖树（真实发行名）/ 源码 import / 动态导入与裸 HTTP | `test_llm_free_path.py`、`llm_free.py` |
| B12 AI Studio 路径 | 按**用法**判定（API key / 专属端点 / `genai.Client(` 无 `vertexai=True`），三处强制点共用 `scripts/check_ai_studio.py` | 同上 |
| B13 Outreach Consent Integrity | 邮件字段白名单；同意回执与 trigger 必须自洽 | `test_wellbeing_contracts.py` |

## 两条容易被误解的设计

**这一层保证到什么程度？**
`extra="forbid"` 与 validator 挡住构造与反序列化；`model_copy(update=...)` 也已经
覆写成重新校验，冻结记录则直接拒绝带 update 的复制。`model_construct` 仍然不校验——
那是 pydantic 明示的出口，评测需要它来构造违规样本。区别在于它得被显式写出来。
真正的类型层保证（任何构造路径都违反不了）目前是 B8 的形状半边与 B13 的白名单半边；
其余各条是 validator 不变式 + 字段扫描 + 服务层强制的组合。

**为什么字段名扫描而不是只靠 `extra="forbid"`？**
`extra="forbid"` 挡住的是运行时多传的字段，挡不住有人日后在
`AvailabilityBlock` 上加一个 `title: str`。那样 B5 会在没有任何测试变红的情况下被破坏。
`guards.py` 递归遍历模型字段图，把"这些字段不许出现在这条链路上"变成断言。
唯一的豁免是 `CalendarWriteDraft.event_title`——那是我们生成、学生预览后写回的事件名称，
不是从学生日历读来的标题。豁免集合用**精确相等**钉死，加一条就会红——
只靠「写在测试里所以 diff 可见」防守是不够的：泄露和它的豁免可以在同一个 commit 里一起加。

**为什么 `validation_id` 要查三层？**
只查形状，模型编一个 `val_` + 32 位十六进制就能过；只查签发，
缺字段的输出在到达闸门前已经被当成合法对象传播开了；
**只有这两层时，一条 Rules 真实签发的「先修不满足」照样能背书计划项**——
证明了出处，没证明合规。第三层查 verdict 是否在 `BACKING_VERDICTS` 内。

## 约束

- 本包**不得依赖任何模型 SDK**。确定性服务平面会 import 它，
  一旦混进 SDK，Rules / Capacity / Wellbeing 的零 LLM 断言一起失效。
- 契约模型不做排序。分数只允许出现在 A5 的输出模型上（`MatchResult`、`CoursePlan`）。
- 新增或修改字段要同步 `CONTRACTS_VERSION` 与 `make contracts`。
