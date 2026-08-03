"""确定性服务的**双语判定文案**。

为什么在契约层：Rules、Capacity、Wellbeing 三个零 LLM 服务都要出人看的理由，
而这些理由会直接显示在学生端界面上。CLAUDE.md 要求"UI 文案走 i18n 资源、
可切换"，判定理由自然也在其内——之前它们是单语中文 prose，塞进
``LocalizedText`` 时两侧填同一个字符串，于是英文界面里整段中文。

为什么是**模板 + 参数**而不是让模型翻：这三个服务零 LLM 是硬约束
（CI 断言它们不得 import 模型 SDK）。翻译因此必须是静态的、可复现的、
构建期就能全部看到的。这也顺带保证了同一条判定在两种语言下说的是同一件事——
模型翻译做不到这个保证。

**新增判定必须同时给两种语言**：``render`` 查不到 key 会抛异常，
不会悄悄回落到 key 本身。少写一种语言在这里是错误，不是降级。
"""

from __future__ import annotations

from .common import LocalizedText

#: message key → (zh_Hans 模板, en 模板)。
#: 两侧的占位符必须完全一致，由 ``tests/test_messages.py`` 逐条断言。
MESSAGES: dict[str, tuple[str, str]] = {
    # ── 先修 ────────────────────────────────────────────────────
    "prereq.met": ("已修读 {course}", "Completed {course}"),
    "prereq.not_met": ("未修读 {course}", "Not taken: {course}"),
    "prereq.grade_met": (
        "{course} 成绩 {actual} 达到要求的 {required}",
        "{course} grade {actual} meets the required {required}",
    ),
    "prereq.grade_not_met": (
        "{course} 成绩 {actual} 未达到要求的 {required}",
        "{course} grade {actual} is below the required {required}",
    ),
    "prereq.grade_unknown": (
        "{course} 已修但成绩未知，无法判断是否达到 {required}",
        "{course} was taken but the grade is unknown, so we cannot tell whether it meets {required}",
    ),
    "prereq.unparsed": (
        "无法解析这条先修表达式：{expression}",
        "Could not parse this prerequisite: {expression}",
    ),
    "prereq.none": ("本课程没有先修要求", "This course has no prerequisites"),
    "prereq.external": (
        "外部资历，系统不掌握：{text}",
        "An external qualification we do not hold: {text}",
    ),
    "prereq.programme_scoped": (
        "含项目适用性限定，需确认学生是否属于该项目：{text}",
        "Scoped to a specific programme — needs confirming whether you are in it: {text}",
    ),
    "prereq.unreadable": (
        "无法解析的先修表述，需人工确认：{text}",
        "This prerequisite could not be parsed and needs a human read: {text}",
    ),

    # ── 资格四态 ─────────────────────────────────────────────────
    # ── Wellbeing（零 LLM：措辞全部来自这里的固定模板）───────────────
    "wb.ref.sleep": (
        "成人每 24 小时通常建议至少 {hours} 小时",
        "Adults are generally advised at least {hours} hours per 24 hours",
    ),
    "wb.obs.sleep_compressed": (
        "未来 {window} 天中有 {nights} 晚被计划压缩至 {hours} 小时以下",
        "{nights} of the next {window} nights are squeezed below {hours} hours by the plan",
    ),
    "wb.obs.self_reported_sleep": (
        "自报近 {days} 天平均 {average} 小时，其中 {short} 天低于参考线",
        "Self-reported average of {average} hours over {days} days, with {short} below the reference",
    ),
    "wb.ref.activity": (
        "成人每周 {minutes}–300 分钟中等强度活动",
        "{minutes}–300 minutes of moderate activity per week for adults",
    ),
    "wb.obs.activity": (
        "{days}/{window} 天有记录，合计 {minutes} 分钟",
        "{days}/{window} days have records, {minutes} minutes in total",
    ),
    "wb.obs.recovery_no_capacity": (
        "未来 {window} 天无完整恢复区块，而且可支配容量已经是负数——现在安排的已经超出你剩下的时间",
        "No full recovery block in the next {window} days, and discretionary capacity is already negative — what is scheduled exceeds the time you have left",
    ),
    "wb.ref.recovery": (
        "学生自定的恢复偏好",
        "The recovery preference you set yourself",
    ),
    "wb.obs.recovery": (
        "未来 {window} 天无完整恢复区块，且计划占用可支配容量 {utilisation}",
        "No full recovery block in the next {window} days, with the plan using {utilisation} of discretionary capacity",
    ),
    "wb.ref.capacity": (
        "学生自定的每周可支配容量与缓冲下限",
        "The weekly discretionary capacity and buffer floor you set yourself",
    ),
    "wb.obs.capacity": (
        "计划负荷 {planned}h / 可支配 {available}h，缓冲比 {buffer}（下限 {floor}）",
        "Planned load {planned}h against {available}h available; buffer ratio {buffer} (floor {floor})",
    ),

    # ── 局部重排的理由（Spec §16.9）─────────────────────────────
    "replan.calendar_change": (
        "日历变化只重排冲突项并恢复缓冲，不推翻无关的长期目标",
        "A calendar change only reshuffles what clashes and restores your buffer — unrelated long-term goals are left alone",
    ),
    "replan.weekly_overload": (
        "本周负荷超标，自动降级非关键任务并提出新版本",
        "This week is over capacity, so non-critical tasks are eased off and a new version is proposed",
    ),
    "replan.student_declined": (
        "记录拒绝原因，避免换个名字重复推荐",
        "Recording why you declined, so the same thing does not come back under a different name",
    ),
    "replan.new_grade": (
        "更新相关技能与先修缺口",
        "Updating the related skills and prerequisite gaps",
    ),
    "replan.opportunity_change": (
        "重新排序受影响的机会与近期行动",
        "Re-ordering the affected opportunities and near-term actions",
    ),
    "replan.goal_confidence_shift": (
        "发起 Goal Review，比较候选方向",
        "Starting a goal review to compare the two directions",
    ),
    "replan.student_added_opportunity": (
        "你自己加的东西围着原主路线排——只动未来两周与本学期，长期路线不变",
        "What you added is fitted around your existing route — only the next two weeks and this term move; the long-term plan stays put",
    ),
    "replan.default": (
        "按 §16.9 计算受影响范围",
        "Affected scope computed per §16.9",
    ),

    # ── 排程冲突 ─────────────────────────────────────────────────
    "sched.protected_overlap": (
        "与你自己划下的保护时段重叠（{block}）——不会静默排进去",
        "Overlaps a protected block you set yourself ({block}) — it will not be scheduled silently",
    ),
    "sched.busy_overlap": (
        "与已有安排重叠（{block}）——可以排，但你得决定哪个让路",
        "Overlaps something already scheduled ({block}) — possible, but you decide which gives way",
    ),

    "match.reason_deterministic": (
        "覆盖 {categories} 类目标要求，预计投入 {workload}；此条理由由确定性规则生成（模型理由暂不可用）",
        "Covers {categories} of your goal's requirement categories at an estimated {workload}; this reason is rule-generated (model rationale unavailable)",
    ),
    "wellbeing.lowload_assumption": (
        "把 {hours} 小时可延期计划项延后，可覆盖 {excess} 小时超载；未经你批准不改任何日历",
        "Deferring {hours}h of movable plan items covers the {excess}h overload; nothing changes on your calendar without your approval",
    ),
    "elig.deadline_passed": (
        "截止日期 {deadline} 已过（今天 {today}），本轮无法申请",
        "The deadline of {deadline} has passed (today is {today}), so this cycle is closed",
    ),
    "elig.year_ok": (
        "当前 {actual} 年级满足「{expression}」",
        "Year {actual} satisfies “{expression}”",
    ),
    "elig.year_future": (
        "当前 {actual} 年级，升到 {required} 年级后可申请",
        "Currently year {actual}; eligible once you reach year {required}",
    ),
    "elig.program_ok": (
        "所在专业 {actual} 在允许范围内",
        "Your programme {actual} is within scope",
    ),
    "elig.program_no": (
        "该机会限 {expression}，与所在专业 {actual} 不符",
        "This is limited to {expression}, which does not include your programme {actual}",
    ),
    "elig.course_ok": (
        "课程要求已满足：{detail}",
        "Course requirements met: {detail}",
    ),
    "elig.course_unknown": (
        "课程要求无法判定：{detail}",
        "Course requirements could not be determined: {detail}",
    ),
    "elig.course_reachable": (
        "课程要求尚未满足，但可通过补修达成：{detail}",
        "Course requirements are not met yet but are reachable by taking them: {detail}",
    ),
    "elig.course_unreachable": (
        "课程要求未满足，且所缺课程在未来学期无开课记录，本轮无法补足：{detail}",
        "Course requirements are not met, and the missing courses have no future offerings on record, so this cannot be made up this cycle: {detail}",
    ),
    "elig.cgpa_missing": (
        "该机会要求 CGPA，但我们没有你的 CGPA，需人工确认",
        "This asks for a CGPA and we do not have yours — needs confirmation",
    ),
    "elig.cgpa_ok": (
        "CGPA {actual} 满足「{expression}」",
        "CGPA {actual} satisfies “{expression}”",
    ),
    "elig.cgpa_no": (
        "CGPA {actual} 未达到「{expression}」，本轮无法补足",
        "CGPA {actual} does not reach “{expression}” and cannot be raised in time",
    ),
    "elig.membership": (
        "在读学生身份即满足：{expression}",
        "Being an enrolled student is enough: {expression}",
    ),
    "elig.window_confirm": (
        "申请窗口需按来源原文确认：{expression}",
        "The application window must be confirmed against the source: {expression}",
    ),
    "elig.rule_uncovered": (
        "未覆盖的规则类型 {kind}，交由人工确认：{expression}",
        "Rule type {kind} is not covered yet — needs human confirmation: {expression}",
    ),
    "elig.no_hard_rules": (
        "来源未声明任何硬性资格条件",
        "The source states no hard eligibility conditions",
    ),
    "elig.preferred_only": (
        "（非硬性要求，未满足不影响资格）{detail}",
        "(Preferred, not required — not meeting it does not affect eligibility) {detail}",
    ),
    "elig.model_inferred": (
        "这条规则来自模型推断，只能提示确认，不能作为淘汰依据：{expression}",
        "This rule was inferred by a model — it can prompt a check but can never rule you out: {expression}",
    ),
    "elig.year_ambiguous": (
        "年级表述含糊，需向来源确认：{expression}",
        "The year requirement is ambiguous and must be confirmed with the source: {expression}",
    ),
    "elig.work_auth": (
        "工作授权状态系统不掌握，需你自己确认：{expression}",
        "We do not hold your work authorisation status — you will need to confirm it: {expression}",
    ),
    "elig.work_auth_visa": (
        "你登记了签证类约束；工作授权状态系统不掌握，需你自己确认：{expression}",
        "You have a visa constraint on record, and we do not hold your work authorisation status — you will need to confirm it: {expression}",
    ),
    "elig.gpa_unparsed": (
        "GPA 未授权或阈值无法解析，需确认：{expression}",
        "GPA is not shared with us, or the threshold could not be parsed — needs confirmation: {expression}",
    ),
    "elig.estimated_date": (
        "预计可申请日期 {date} 为系统推算的保守估计，没有来源给出确切窗口，请以来源公告为准",
        "The date {date} is our own conservative estimate — no source gave an exact window, so treat the official announcement as authoritative",
    ),
    "elig.visa_confirm": (
        "你登记了签证限制，这条需要与主办方确认：{expression}",
        "You have a visa constraint on record; confirm this one with the organiser: {expression}",
    ),
}


class UnknownMessage(KeyError):
    """用了未登记的 message key。**不回落**——回落会让缺失的翻译上线。"""


def _side(value: object, locale: str) -> object:
    """取参数在某种语言下的值。

    参数本身可以是 ``LocalizedText``（例如"课程要求已满足：{detail}"里的
    detail 是一串先修理由）。**必须按语言各取一侧再格式化**——
    先把中文那一侧拼好再塞进英文模板，得到的就是一句中英混排，
    而那正是这套目录要消灭的东西。
    """
    if isinstance(value, LocalizedText):
        return value.zh_Hans if locale == "zh_Hans" else value.en
    if isinstance(value, (list, tuple)) and value and all(
        isinstance(v, LocalizedText) for v in value
    ):
        return "; ".join(str(_side(v, locale)) for v in value)
    return value


def render(key: str, **params: object) -> LocalizedText:
    """按 key 渲染双语文案。

    缺 key 或缺参数都直接抛错：一条显示成 ``elig.cgpa_ok`` 的理由，
    比一条中英混排的理由更难被发现，因为它看起来像"某种编号"。

    参数可以是 ``LocalizedText`` 或它的序列，此时按语言各取一侧（见 :func:`_side`）。
    """
    try:
        zh_template, en_template = MESSAGES[key]
    except KeyError as exc:  # pragma: no cover - 由测试覆盖
        raise UnknownMessage(
            f"未登记的文案 key：{key!r}。新增判定必须同时给中英两种模板"
        ) from exc
    return LocalizedText(
        zh_Hans=zh_template.format(
            **{k: _side(v, "zh_Hans") for k, v in params.items()}
        ),
        en=en_template.format(**{k: _side(v, "en") for k, v in params.items()}),
    )
