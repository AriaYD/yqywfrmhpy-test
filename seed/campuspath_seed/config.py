"""Seed 的全局常量：版本、时钟、规模档位。

**这里没有一个值是随机的。** Spec §11.5 要求"Seed 可重复运行，保证评委每次看到
一致情景"，D6.7 进一步要求"固定 Seed 可复现两次数字一致"。因此：

* 时间基准是常量 :data:`SEED_TODAY`，不是 ``date.today()``；
* 随机性一律经 :mod:`campuspath_seed.rng`，禁止模块级 ``random``；
* 遍历一律排序，不依赖 dict 插入序或 set 迭代序。

改这些常量等于改 Seed 版本，必须同步 :data:`SEED_VERSION` —— 否则 Gold Label
会悄悄对不上它标注的那份数据（D6.5 规则④）。
"""

from __future__ import annotations

import dataclasses
from datetime import date

#: 改数据分布、规模或时钟都要 bump。Gold Set 冻结后与该版本绑定。
#:
#: 变更记录（D6.5 规则④——标签口径变更必须走版本号，禁止静默改标签）：
#:
#: * ``seed/1.8.0`` (2026-07-31)：机会 category_tags 源头去重（类型词与随机
#:   标签撞车产生 ('internship','internship')，前端 React key 冲突报错）
#: * ``seed/1.7.0`` (2026-07-31)：证据条目 source 改为可读名称，公开课链接
#:   指向真实课程公开页（R4-C；证书本体仍合成并标注）
#: * ``seed/1.6.0`` (2026-07-31)：课表块带课程全名（教务公开数据 + 学生自设
#:   区块的标题不受二级日历授权限制——B5 管的是私人日历采集，R4-M）
#: * ``seed/1.5.0`` (2026-07-31)：机会补 ``organizer_category`` 八大类标注
#:   （用户裁定收敛主办方筛选）；官方活动归 campus_official。
#: * ``seed/1.4.0`` (2026-07-31)：二级日历授权 Persona（STU-B）补
#:   ``calendar_write`` 同意——此前无人授权写入，F06 的"确认后创建计划事件"
#:   在数据上是死路；其余学生保持未授权以演示 403 分支。
#: * ``seed/1.3.0`` (2026-07-31)：合成机会 title/organizer 补双语 localized
#:   字段，词表改 (zh,en) 对；数据身份不变（title 原文与 series_id 不动）。
#: * ``seed/1.2.0`` (2026-07-31)：T12 可测化。memory_regression 新增
#:   ``expected_memory_ids`` 列；每人记忆池 5 → 9 条（加 4 条干扰项，
#:   否则 top-5 召回在 5 条里是恒真式）；memory_id 改为按人按模板序号
#:   （``MEM-{sid}-{模板序号+1}``），Gold 由此可确定性推导引用。
#: * ``seed/1.1.0`` (2026-07-31)：T1/T3 裁定落地，见 ``docs/T1-T3-adjudication.md``。
#:   ① Gold 的 STATE_PRECEDENCE 第 2、3 位对齐 Rules Engine
#:   （needs_confirmation 优先于 future_eligible）；
#:   ② 课程约束 Gold 的先修判定改为三值成绩感知评估，
#:   含成绩条件的表达式不再一律 unknown。
#: * ``seed/1.0.0``：初版。
SEED_VERSION = "seed/1.9.0"

#: 全局随机种子。不要按环境变量覆盖——那等于放弃可复现。
MASTER_SEED = 20260729

#: 演示的"今天"。落在 2026-27 秋季学期期中：往前有已修记录，往后有截止日期。
SEED_TODAY = date(2026, 9, 15)

#: 学期定义。key 必须匹配契约的 ``TERM_PATTERN``。
TERMS: dict[str, tuple[date, date]] = {
    "2024-25_FALL": (date(2024, 9, 2), date(2024, 12, 20)),
    "2024-25_SPRING": (date(2025, 2, 3), date(2025, 5, 23)),
    "2025-26_FALL": (date(2025, 9, 1), date(2025, 12, 19)),
    "2025-26_SPRING": (date(2026, 2, 2), date(2026, 5, 22)),
    "2026-27_FALL": (date(2026, 9, 1), date(2026, 12, 18)),
    "2026-27_SPRING": (date(2027, 2, 1), date(2027, 5, 21)),
    "2027-28_FALL": (date(2027, 9, 6), date(2027, 12, 17)),
    "2027-28_SPRING": (date(2028, 2, 7), date(2028, 5, 26)),
}

CURRENT_TERM = "2026-27_FALL"
NEXT_TERM = "2026-27_SPRING"

#: 已经结束的学期，可用于生成"已修课程"。
PAST_TERMS = ("2024-25_FALL", "2024-25_SPRING", "2025-26_FALL", "2025-26_SPRING")

#: 可规划的未来学期，供 12–18 个月长期视图使用。
FUTURE_TERMS = ("2026-27_SPRING", "2027-28_FALL", "2027-28_SPRING")

INSTITUTION = "HKUST"

#: 全站标记（Spec §16.8.4、D1）。
SYNTHETIC_NOTICE = "Synthetic / Demo Data"


@dataclasses.dataclass(frozen=True)
class ScaleProfile:
    """规模档位。

    ``tiny`` 供 smoke 与单测使用（Plan §10.5 要求 1 Persona / 5 课程 / 5 机会），
    ``full`` 对齐 Spec §11.2 的各表下限。
    """

    name: str
    deep_personas: int
    slim_students: int
    catalog_courses: int
    internships: int
    events: int
    labs: int
    competitions: int
    historical_feedback: int
    publishers: int
    submissions: int
    profile_events: int
    calendar_weeks: int

    def total_students(self) -> int:
        return self.deep_personas + self.slim_students


TINY = ScaleProfile(
    name="tiny",
    deep_personas=1,
    slim_students=0,
    catalog_courses=0,       # 未使用：tiny 靠"只建一个培养方案"缩小，不靠裁课程
    internships=12,          # 需要足够多才能让四态各自出现
    events=6,
    labs=2,
    competitions=2,
    historical_feedback=3,
    publishers=2,
    submissions=3,
    profile_events=3,
    calendar_weeks=2,
)

FULL = ScaleProfile(
    name="full",
    deep_personas=3,
    slim_students=9,        # 合计 12，落在 Spec §11.2 的 10–15
    catalog_courses=60,     # 下限 30–50
    internships=60,         # 下限 50–100
    events=48,              # 下限 40–60
    labs=14,                # 下限 10–20
    competitions=18,        # 下限 15–25
    historical_feedback=40,  # 下限 30–50
    publishers=10,          # 下限 8–12
    submissions=24,         # 下限 20–30
    profile_events=24,      # 下限 20–30
    calendar_weeks=6,       # 下限 4–8
)

PROFILES: dict[str, ScaleProfile] = {"tiny": TINY, "full": FULL}


#: Spec §11.2 的各表下限，由 ``consistency.py`` 逐项断言。
#: 写成数据而不是散在注释里，是为了让"数据量不够"这件事能被脚本发现。
FULL_SCALE_FLOORS: dict[str, int] = {
    "students": 10,
    "programs": 3,
    "catalog_courses": 30,
    "internships": 50,
    "events": 40,
    "labs": 10,
    "competitions": 15,
    "historical_feedback": 30,
    "publishers": 8,
    "submissions": 20,
    "profile_events": 20,
    "moodle_courses": 8,
}

#: D6.5 的 Gold Set 下限。
GOLD_SET_FLOORS: dict[str, int] = {
    "eligibility": 60,
    "course_constraints": 40,
    "replan": 12,
    "failure_kinds": 12,
    "memory_regression": 20,
}
