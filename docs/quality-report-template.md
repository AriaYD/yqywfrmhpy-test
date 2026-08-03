# 活动反馈周期报告——数据与样式模板（D3，2026-08-02）

> 生成端点：`POST /v1/ops/quality-reports/{weekly|monthly|term|year}`（仅 career_center_admin）。
> 统计全部确定性；唯一模型产物是叙事段（输入只有本报告聚合 JSON）。页面：/quality-reports。

## 数据模板（QualityReport 契约）

| 段 | 字段 | 口径 |
|---|---|---|
| 总览 | activities_total / feedback_total / verified_total / attend_total | 窗口内有反馈的活动数；评分条数；验证参加数；扫码签到人次 |
| 主办方对比 | by_organizer[] | 按十大类分组：活动数/评分数/验证数/签到、均分（1-5）、真实好评率 |
| 形式对比 | by_type[] | workshop/competition/internship… 同上口径 |
| 专业对比 | by_school[] | cohort_dims.school 粗粒度（ENGG/SCI/BM），不细分到专业方向以下（B10） |
| 活动排行 | top_activities[] | 按均分→样本量排序，前 10 |
| 供给缺口 | coverage_gaps[] | 确定性检出：窗口内零反馈的主办方类别 |
| AI 结论 | narrative | 4-6 句：受欢迎类型、缺口查缺补漏、值得倾斜的高质量活动；无后端时为 None 并注明 |
| 口径注 | data_notes[] | 阈值抑制 / 好评率分母=验证参加 / 两月冻结 |

**硬口径**：真实好评率 = 验证参加者中（均分 ≥4 的份数 / 验证份数）；任何分组 verified_n < MIN_CELL_N(5) → 分数抑制为 Insufficient evidence；窗口 = 7/30/180/365 天滚动。

## 样式模板（quality-reports 页）

分段控件切周期 → 总览 Metric 行 → `.ai-note` 叙事块 → 四张分组表（每行：名称 + 计数串 + 均分横条 Bar(比例=均分/5) + 好评率强调色）→ 缺口列表 → 口径注脚。生成按钮 + 三段式进度条（服务端任务，切页/关页不中断）。
