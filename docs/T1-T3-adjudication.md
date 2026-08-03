# T1 / T3 标签分歧：裁定所需的证据

`make eval` 报 T1 81.7%（阈值 ≥90%）、T3 90.0%（≥95%）。这不是"模型不准"——
**两套确定性实现对同一批样例判定不同**：Gold Set 的标签生成器
（`seed/campuspath_seed/goldset.py`）与 Rules Engine
（`services/rules/campuspath_rules/eligibility.py`）。

D6.5 规则④禁止改标签凑指标，所以这里**只摆证据、不动任何一方**。
下面两条原因互不相干，需要分别裁定。

---

## 原因一：STATE_PRECEDENCE 的第 2、3 位互换了（约 6/11 例）

多条规则给出不同状态时，取哪一个：

| | 第 1 | 第 2 | 第 3 | 第 4 |
|---|---|---|---|---|
| **Rules Engine** | ineligible_current_cycle | **needs_confirmation** | **future_eligible** | eligible_now |
| **Gold 生成器** | ineligible_current_cycle | **future_eligible** | **needs_confirmation** | eligible_now |

典型样例 `GOLD-ELIG-STU-A-OPP-INT-026`：
- 年级：Year 2，要求 Year 3 or above → **future_eligible**（升上去就行）
- 工作授权：系统不掌握 → **needs_confirmation**
- Gold 判 `future_eligible`；引擎判 `needs_confirmation`

**这是一个政策选择，两边都说得通：**

- 引擎的顺序（needs_confirmation 优先）＝「只要有一项没弄清，整条结论就标成待确认」。
  更谨慎，但会把一条**本来能说清时间线**的机会（"升上大三就能报"）
  降级成一句没信息量的"需要确认"。
- Gold 的顺序（future_eligible 优先）＝「能说出何时可达就先说」，
  未确认项作为附注。信息量更大，但学生可能忽略掉那条待确认。

⚠️ 两种顺序**都不影响 T2**（硬假阳性 = 实际不合格却判 eligible_now）——
`eligible_now` 在两边都排最后，这是刻意的。T2 实测 0.0%。

**需要裁定：以哪一份为准。** 定了之后改另一方，并按 D6.5 规则④走版本号 + 变更记录。

---

## 原因二：引擎判「课程未修」时**不查该课将来还开不开**（约 5/11 例）

`eligibility.py` 里 `PREREQUISITE_COURSE` 分支：课程未修一律给
`FUTURE_ELIGIBLE`，理由是"可通过补修达成"。**它没有查开课记录。**

Gold 生成器查了。样例 `GOLD-ELIG-STU-A-OPP-LAB-008`：
> 尚未修读 MATH 4141，**且未来学期无开课记录**

Gold 因此判 `ineligible_current_cycle`；引擎判 `future_eligible`。

**这一条我认为不是政策分歧，是引擎的缺口**：告诉学生"补修就能达成"，
而那门课再也不开了——学生会为一条走不通的路安排时间。
它不算 T2 的假阳性（没判成 eligible_now），但性质上同源：
**给了一个我们没有依据的承诺。**

修法：`_assess_rule` 的 PREREQUISITE_COURSE 分支需要拿到开课信息
（`CourseOffering`），未修且无未来开课 → `INELIGIBLE_CURRENT_CYCLE`，
未修但有开课 → `FUTURE_ELIGIBLE`（现状）。
这会让 `StudentEligibilityFacts` 多一项输入，属契约层改动。

---

## T3 的 4 例是另一回事

`GOLD-CRS-STU-B-COMP2012H`、`COMP3111H` 等：Gold 标 `unknown`，
解析器给出确定判定。但这两门课的先修表达式本身完全可解析：

```
COMP 2012H: (Grade A or above in COMP 1023) OR (Grade A or above in COMP 1021 AND Pass grade in COMP 1028)
COMP 3111H: Grade A- or above in COMP 2012 / COMP 2012H
```

里面**没有任何项目限定**。Gold 标 unknown 应该是因为它对 H 结尾的荣誉课
一律保守处理——但"能不能读荣誉班"是**入读资格**，不是**先修条件**，
两者不在同一个字段里。

倾向：解析器是对的，Gold 标签过度保守。仍需人工确认。

---

## 给裁定人的三个问题

1. STATE_PRECEDENCE 用哪一份顺序？（原因一）
2. 引擎要不要查开课记录？（原因二 —— 我建议要，这是缺口不是分歧）
3. 荣誉课的先修判定，Gold 的 `unknown` 是否过度保守？（T3）

---

## 裁定（2026-07-31）

用户已授权接手窗口在通读 Spec 与 Plan 后代为裁定。三项裁定与依据：

**① STATE_PRECEDENCE 采用 Rules Engine 的顺序**（needs_confirmation 排在
future_eligible 之前），改 Gold 生成器。依据：future_eligible 的系统动作是
「放入长期路径，生成桥接行动与**预计可申请窗口**」（Spec §16.1）——那是一个承诺；
还有硬条件未确认时给出确切日期，是系统自己站不住的承诺。这与原因二被认定为
缺口的理由（"给了一个我们没有依据的承诺"）是同一条原则，两项裁定因此互相一致。
信息量并不损失：「升入 Year 3 后可达」仍逐条留在 reasons / per_rule 里，
且 §16.4 会为 needs_confirmation 安排近期核实动作，确认完成后状态自然重算。

**② 引擎必须查开课记录**（这是缺口不是分歧，采纳原文档建议）。
`StudentEligibilityFacts` 新增 `future_offerings: Mapping[str, date] | None`：
`None` = 没有目录，沿用旧假设；有目录时把「未来还开的课」假设修完再评一次，
仍 NOT_MET → `ineligible_current_cycle`（新文案 `elig.course_unreachable`），
可达 → `future_eligible` 并给出最早可完成日期。评测与 API 两处调用方
均已接入同一份开课事实。

**③ T3 的 Gold `unknown` 判为过度保守，改 Gold。** 真实根因不是"荣誉课"，
是 Gold 的简易判定器对**一切含 grade 字样的表达式**直接弃权（旧
`goldset.py` 的 `grade|level|prior to` 拦截）。学生成绩在档且写法可识别
（`Grade X or above in …` / `Pass grade in …`）时应给出确定判定；
识别不了的写法仍归 unknown——解析器的无能只能变成"待确认"，不能变成判定。
「能不能读荣誉班」是入读资格，不在先修字段里，维持原文档的判断。

三项落地均走 `SEED_VERSION` bump：`seed/1.0.0 → seed/1.1.0`（变更记录见
`seed/campuspath_seed/config.py`）。实施后 `make eval` 的 T1/T3 实测值
见 PROGRESS.md 对应行。
