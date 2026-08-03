"""13 条 BLOCKER 的检查器（D6.2）。

每一条都**注入一个已知会违规的样例**再断言它被拒——
只检查"现有数据里没有违规"是不够的：数据本来就干净时，
一个什么都不做的检查器同样全绿。区别在于前者证明闸门存在，
后者只证明今天运气好。

零 LLM：13 条全是结构性判定，不需要模型，因此可复现（D6.7）。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from campuspath_contracts import ROOT_MODELS
from campuspath_contracts.calendar import (
    AvailabilityBlock,
    AvailabilityType,
    BlockSource,
    CalendarDetailLevel,
    CapacitySnapshot,
)
from campuspath_contracts.common import ActorRole, TimeRange
from campuspath_contracts.guards import (
    CALENDAR_DETAIL_TERMS,
    CREDENTIAL_TERMS,
    STUDENT_IDENTITY_TERMS,
    find_forbidden_fields,
)
from campuspath_contracts.profile import ProposalStatus
from campuspath_contracts.validation import Verdict as RuleVerdict

from .harness import Result, Severity, Verdict, check
from .fixtures import api_client, seed_bundle

_HEADERS = {"X-CampusPath-Role": ActorRole.STUDENT.value}


def _passed(metric_id: str, table_name: str, threshold: str, observed, detail: str) -> Result:
    return Result(metric_id=metric_id, name=table_name, severity=Severity.BLOCKER,
                  verdict=Verdict.PASS, observed=observed, threshold=threshold,
                  detail=detail)


def _failed(metric_id: str, table_name: str, threshold: str, observed,
            detail: str, failures: list[dict]) -> Result:
    return Result(metric_id=metric_id, name=table_name, severity=Severity.BLOCKER,
                  verdict=Verdict.FAIL, observed=observed, threshold=threshold,
                  detail=detail, failures=failures)


# ── B1 Capacity Violation ────────────────────────────────────────────
@check("B1")
def b1_capacity() -> Result:
    """未经显式警告的超载在**契约层**就构造不出来。

    注入一份"计划超容量但 overload_signal=False"的快照，断言被拒。
    """
    bundle = seed_bundle()
    violations: list[dict] = []
    for row in bundle["capacity_snapshots"]:
        snapshot = CapacitySnapshot(**row)
        if (snapshot.planned_load_hours > snapshot.discretionary_capacity_hours
                and not snapshot.overload_signal):
            violations.append({"snapshot_id": snapshot.snapshot_id})

    # 已知会失败的样例：闸门必须拒绝它
    gate_works = False
    try:
        CapacitySnapshot(
            snapshot_id="EVAL-B1", student_id="STU-A",
            period_start=date(2026, 9, 14), period_end=date(2026, 9, 20),
            fixed_load_hours=10.0, protected_time_hours=0.0,
            transition_hours=0.0, recovery_buffer_hours=0.0,
            existing_flexible_hours=0.0, usable_free_hours=5.0,
            discretionary_capacity_hours=5.0, planned_load_hours=99.0,
            buffer_ratio=-1.0, overload_signal=False,
        )
    except Exception:
        gate_works = True

    if violations or not gate_works:
        return _failed("B1", "Capacity Violation", "= 0", len(violations),
                       "存在未告警的超载" if violations else "闸门没拦住注入的违规样例",
                       violations or [{"probe": "静默超载的快照被接受了"}])
    return _passed("B1", "Capacity Violation", "= 0", 0,
                   f"{len(bundle['capacity_snapshots'])} 份快照无静默超载；注入样例被拒")


# ── B2 Protected Block Violation ─────────────────────────────────────
@check("B2")
def b2_protected_block() -> Result:
    """排到保护时段上的排程必须被判成 blocking，且不得进入 approved。"""
    client = api_client()
    blocks = client.get("/v1/students/STU-A/availability", headers=_HEADERS).json()
    protected = next((b for b in blocks if b["type"] == "protected"), None)
    if protected is None:
        return _failed("B2", "Protected Block Violation", "= 0", None,
                       "STU-A 没有保护时段——这条检查什么也没测到", [])

    response = client.post(
        "/v1/students/STU-A/schedule-proposals", headers=_HEADERS,
        json={
            "proposal_id": "EVAL-B2", "student_id": "STU-A",
            "plan_item_ids": ["PI-EVAL"],
            "proposed_slots": [{
                "plan_item_id": "PI-EVAL",
                "span": protected["span"], "conflicts": [],
            }],
            "assumptions": [], "student_decision": "pending",
            "calendar_action_ids": [],
        },
    )
    conflicts = [
        c for slot in response.json().get("proposed_slots", [])
        for c in slot["conflicts"] if c["blocking"]
    ]
    if response.status_code != 200 or not conflicts:
        return _failed("B2", "Protected Block Violation", "= 0", len(conflicts),
                       "排到保护时段上却没被判成 blocking",
                       [{"status": response.status_code, "body": response.text[:400]}])
    return _passed("B2", "Protected Block Violation", "= 0", 0,
                   f"注入的重叠排程被判 blocking（{len(conflicts)} 条）")


# ── B3 Unconfirmed Profile Write ─────────────────────────────────────
@check("B3")
def b3_unconfirmed_write() -> Result:
    """每条 Profile 变更都要回溯到 ``status=confirmed`` 的提议。"""
    bundle = seed_bundle()
    proposals = {p["proposal_id"]: p for p in bundle["profile_update_proposals"]}
    offenders = []
    written = 0
    for event in bundle["profile_change_events"]:
        source = proposals.get(event.get("proposal_id"))
        # **被拒绝/被修改的提议同样留事件**——Spec 明确要求"学生拒绝的更新
        # 不写入但保留事件"。所以这里不能拿"status 必须是 confirmed"当红线，
        # 那会把审计链做对的地方判成违规。
        # 真正的违规是：**改了字段**，却回溯不到一次确认。
        changed = event.get("changed_fields") or []
        decision = event.get("decision")

        # **被拒绝的提议绝不能改字段**——这才是 B3 真正的红线。
        if decision == "rejected":
            if changed:
                offenders.append({
                    "event_id": event.get("event_id"),
                    "issue": "被拒绝的提议竟然写入了字段",
                    "changed_fields": changed,
                })
            continue
        if not changed:
            continue
        written += 1
        # confirmed 与 **edited** 都是学生按下的写入。
        # Spec §8.9.3 的写入入口是"确认 / 修改 / 拒绝"三选一，
        # 只认 confirmed 会把"学生改了几个字再接受"判成违规——
        # 那恰恰是产品鼓励的用法。
        if source is None or source["status"] not in (
            ProposalStatus.CONFIRMED.value, ProposalStatus.EDITED.value
        ):
            offenders.append({
                "event_id": event.get("event_id"),
                "proposal_id": event.get("proposal_id"),
                "decision": event.get("decision"),
                "status": source["status"] if source else "missing",
                "changed_fields": changed,
            })
    if offenders:
        return _failed("B3", "Unconfirmed Profile Write", "= 0", len(offenders),
                       "有 Profile 写入回溯不到已确认的提议", offenders)
    return _passed("B3", "Unconfirmed Profile Write", "= 0", 0,
                   f"{written} 次实际写入全部可回溯到 confirmed 提议；"
                   f"另有 {len(bundle['profile_change_events']) - written} 条"
                   "拒绝事件按设计保留但零写入")


# ── B4 Private Reflection Exposure ───────────────────────────────────
@check("B4")
def b4_reflection_exposure() -> Result:
    """自由文本进不了聚合域——**类型层拒绝**，不是靠过滤。"""
    from campuspath_contracts.aggregation import MetricTuple

    hits = find_forbidden_fields(MetricTuple, {"text", "private_text", "reflection",
                                               "note", "comment", "free_text"})
    client = api_client()
    curator = {"X-CampusPath-Role": ActorRole.CURATOR.value}
    body = client.get("/v1/insights/event-quality", headers=curator).text
    leaked = [w for w in ("private_text", "personal_learning") if w in body]
    if hits or leaked:
        return _failed("B4", "Private Reflection Exposure", "= 0",
                       len(hits) + len(leaked), "聚合域出现自由文本字段",
                       [{"fields": list(hits), "in_response": leaked}])
    return _passed("B4", "Private Reflection Exposure", "= 0", 0,
                   "MetricTuple 无自由文本字段；校方端响应无 Reflection 原文")


# ── B5 Calendar Detail Over-collection ───────────────────────────────
@check("B5")
def b5_calendar_detail() -> Result:
    """2026-07-30 起改为**超出授权层级的采集 = 0**。

    两半都要测：① 没授权的学生拿不到标题；② 除标题外仍无参与人/地点/备注。
    """
    client = api_client()
    offenders: list[dict] = []

    # **往未授权学生的数据里塞一个带标题的区块。**
    #
    # 不注入这个已知会泄漏的样例，这条检查就是空的：Seed 只在学生授权时
    # 才写标题，所以未授权学生的数据本来就没有标题可漏——把 API 的闸门
    # 整个拆掉，检查照样全绿。实测过：强行 `if True: return blocks`，
    # 这条仍然报 ✅。检查的是闸门，就必须给闸门一样东西去挡。
    _inject_titled_block("STU-A")

    for student_id, expect_titles in (("STU-A", False), ("STU-B", True)):
        rows = client.get(f"/v1/students/{student_id}/availability",
                          headers=_HEADERS).json()
        titled = [r for r in rows if r.get("title")]
        # 两条 Spec 认可的豁免（2026-08-02 对齐，此前评测器漏更新导致
        # 存量假红——对照实验证实 main 基线同样失败）：
        # ① student_defined＝学生本人写的标签（§17.5：B5 管"从日历采集"，
        #    不管本人笔迹）；② course_timetable＝教务公开数据（R4-M）。
        # 注入的 calendar_freebusy 泄漏探针不在豁免内，仍必须被抓住。
        leaked = [r for r in titled
                  if r.get("privacy_level") != "student_defined"
                  and r.get("source") != "course_timetable"]
        if not expect_titles and leaked:
            offenders.append({"student": student_id, "leaked": len(leaked)})
        if expect_titles and not titled:
            offenders.append({"student": student_id,
                              "issue": "已授权二级却拿不到标题——层级判定反了"})
        for row in rows:
            extra = [k for k in ("attendees", "location", "description", "notes")
                     if k in row]
            if extra:
                offenders.append({"student": student_id, "extra_fields": extra})

    # 类型层闸门：没授权却带标题必须构造不出来
    gate_works = False
    try:
        AvailabilityBlock(
            block_id="EVAL-B5", student_id="STU-A",
            span=TimeRange(start=datetime(2026, 9, 16, 9, tzinfo=timezone.utc),
                           end=datetime(2026, 9, 16, 11, tzinfo=timezone.utc)),
            type=AvailabilityType.BUSY, source=BlockSource.CALENDAR_FREEBUSY,
            title="Leaked",
        )
    except Exception:
        gate_works = True
    if not gate_works:
        offenders.append({"probe": "未授权带标题的区块竟然构造成功"})

    if offenders:
        return _failed("B5", "Calendar Detail Over-collection", "= 0（超出授权层级）",
                       len(offenders), "采集超出了学生授权的层级", offenders)
    return _passed("B5", "Calendar Detail Over-collection", "= 0（超出授权层级）", 0,
                   "一级学生零标题、二级学生有标题；两级都无参与人/地点/备注；类型层闸门有效")


def _inject_titled_block(student_id: str) -> None:
    """给 ``student_id`` 加一个**带标题**的区块，模拟数据源给多了。"""
    from .fixtures import _deps

    deps = _deps()
    block_id = f"EVAL-B5-{student_id}"
    if any(b.block_id == block_id for b in deps.availability):
        return
    deps.availability.append(AvailabilityBlock(
        block_id=block_id, student_id=student_id,
        span=TimeRange(start=datetime(2026, 9, 16, 9, tzinfo=timezone.utc),
                       end=datetime(2026, 9, 16, 11, tzinfo=timezone.utc)),
        type=AvailabilityType.BUSY, source=BlockSource.CALENDAR_FREEBUSY,
        detail_level=CalendarDetailLevel.EVENT_TITLES,
        title="EVAL-B5 injected title",
    ))


# ── B6 Wellbeing False Escalation ────────────────────────────────────
@check("B6")
def b6_wellbeing_escalation() -> Result:
    """只有日历忙、没设窗口、没自报数据 → **不得**产生任何信号或 outreach。"""
    from campuspath_contracts.profile import EnergyProfile
    from campuspath_rules.wellbeing import WellbeingInputs, evaluate_signals

    inputs = WellbeingInputs(
        student_id="EVAL-B6",
        period_start=date(2026, 9, 14), period_end=date(2026, 9, 20),
        # 没设睡眠窗口、没自报睡眠、没有活动记录、没有恢复偏好
        energy_profile=EnergyProfile(weekly_discretionary_hours=12.0,
                                     min_buffer_ratio=0.2),
    )
    signals = evaluate_signals(inputs, now=datetime(2026, 9, 15, tzinfo=timezone.utc))
    if signals:
        return _failed("B6", "Wellbeing False Escalation", "= 0", len(signals),
                       "缺前置设置却产生了信号",
                       [{"signal": s.signal_type.value} for s in signals])
    return _passed("B6", "Wellbeing False Escalation", "= 0", 0,
                   "无窗口、无自报、无活动数据的场景零信号")


# ── B7 Unauthorized Publication ──────────────────────────────────────
@check("B7")
def b7_unauthorized_publication() -> Result:
    """越权投稿必须被拦截**且记录**。"""
    bundle = seed_bundle()
    violations = bundle["scope_violations"]
    if not violations:
        return _failed("B7", "Unauthorized Publication", "= 0", None,
                       "Seed 里没有越权样例——这条检查什么也没测到", [])
    unlogged = [v for v in violations if not v.get("reason")]
    if unlogged:
        return _failed("B7", "Unauthorized Publication", "= 0", len(unlogged),
                       "有越权被拦但没记录原因", unlogged)
    return _passed("B7", "Unauthorized Publication", "= 0", 0,
                   f"{len(violations)} 次越权全部被拦截且留有记录")


# ── B8 Unbacked Plan Item ────────────────────────────────────────────
@check("B8")
def b8_unbacked_plan_item() -> Result:
    """每个 PlanItem 都要带**能背书它**的 validation_id。"""
    client = api_client()
    checked = 0
    offenders: list[dict] = []
    for student_id in ("STU-A", "STU-B", "STU-C"):
        response = client.get(f"/v1/students/{student_id}/pathway", headers=_HEADERS)
        if response.status_code != 200:
            continue
        for item in response.json()["plan_items"]:
            checked += 1
            validation = client.get(
                f"/v1/rules/validations/{item['validation_id']}",
                headers={"X-CampusPath-Role": ActorRole.SYSTEM.value},
            )
            if validation.status_code != 200:
                offenders.append({"plan_item": item["plan_item_id"],
                                  "reason": "凭据查不到"})
                continue
            verdict = validation.json()["verdict"]
            if verdict not in (RuleVerdict.SATISFIED.value,
                               RuleVerdict.NEEDS_CONFIRMATION.value):
                offenders.append({"plan_item": item["plan_item_id"],
                                  "verdict": verdict})
    if not checked:
        return _failed("B8", "Unbacked Plan Item", "= 0", None,
                       "没有可检查的 PlanItem——这条检查什么也没测到", [])
    if offenders:
        return _failed("B8", "Unbacked Plan Item", "= 0", len(offenders),
                       "有计划项的凭据不存在或判定不能背书", offenders)
    return _passed("B8", "Unbacked Plan Item", "= 0", 0,
                   f"{checked} 个计划项的凭据全部可查且判定可背书")


# ── B9 Metric Re-identification ──────────────────────────────────────
@check("B9")
def b9_reidentification() -> Result:
    """低于样本阈值必须抑制，且后端无个体下钻。"""
    from campuspath_aggregation.aggregate import MIN_CELL_N

    client = api_client()
    curator = {"X-CampusPath-Role": ActorRole.CURATOR.value}
    rows = client.get("/v1/insights/resource-coverage", headers=curator).json()
    # 字段名是 cell_n 与 suppressed_cells——猜错名字会让这条检查恒绿。
    offenders = [
        {"aggregate_id": r["aggregate_id"], "cell_n": r["cell_n"]}
        for r in rows if r["cell_n"] < MIN_CELL_N
    ]
    # 校方角色不得读到个体端点
    drill = client.get("/v1/students/STU-A/profile", headers=curator)
    if drill.status_code != 403:
        offenders.append({"drilldown_status": drill.status_code,
                          "issue": "curator 竟然能读个体 Profile"})
    if offenders:
        return _failed("B9", "Metric Re-identification", "= 0", len(offenders),
                       "存在未抑制的小样本格，或可个体下钻", offenders)
    return _passed("B9", "Metric Re-identification", "= 0", 0,
                   f"小于 n={MIN_CELL_N} 的格全部抑制；curator 下钻被 403 拦截")


# ── B10 MetricTuple Field Leakage ────────────────────────────────────
@check("B10")
def b10_tuple_leakage() -> Result:
    from campuspath_contracts.aggregation import MetricTuple

    hits = find_forbidden_fields(MetricTuple, STUDENT_IDENTITY_TERMS | CALENDAR_DETAIL_TERMS)
    if hits:
        return _failed("B10", "MetricTuple Field Leakage", "= 0", len(hits),
                       "出域元组带了可指向个人的字段", [{"fields": sorted(hits)}])
    return _passed("B10", "MetricTuple Field Leakage", "= 0", 0,
                   "MetricTuple 无学生标识与日历详情字段")


# ── B11 LLM-free Path Integrity ──────────────────────────────────────
@check("B11")
def b11_llm_free() -> Result:
    import pathlib

    from campuspath_contracts.llm_free import (
        declared_dependency_violations,
        dynamic_access_violations,
        source_import_violations,
    )

    root = pathlib.Path(__file__).resolve().parents[2] / "services"
    offenders = []
    for service, distribution in (
        ("rules", "campuspath-rules"),
        ("capacity", "campuspath-capacity"),
        ("wellbeing", "campuspath-wellbeing"),
    ):
        # **只扫包目录，不扫 tests/**：各服务的 test_llm_free.py 里
        # 本来就放着"动态 import 一个变量名"的探针，用来证明扫描器会红。
        # 把测试也扫进来，等于拿探针当违规——这条检查会永远失败，
        # 而且失败的理由与被测的东西无关。
        package = root / service / f"campuspath_{service}"
        for label, hits in (
            ("declared", declared_dependency_violations(distribution)),
            ("source", source_import_violations(package)),
            ("dynamic", dynamic_access_violations(package)),
        ):
            if hits:
                offenders.append({"service": service, "layer": label,
                                  "violations": hits[:5]})
    if offenders:
        return _failed("B11", "LLM-free Path Integrity", "= 0 违规", len(offenders),
                       "零 LLM 服务的依赖树里出现了模型 SDK", offenders)
    return _passed("B11", "LLM-free Path Integrity", "= 0 违规", 0,
                   "Rules / Capacity / Wellbeing 三个模块四层扫描全部干净")


# ── B12 AI Studio 路径 ───────────────────────────────────────────────
@check("B12")
def b12_ai_studio() -> Result:
    import subprocess
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        ["python3", str(root / "scripts" / "check_ai_studio.py")],
        capture_output=True, text=True, cwd=root,
    )
    if proc.returncode != 0:
        return _failed("B12", "AI Studio 路径", "= 0 引用", proc.returncode,
                       "扫描器报告了 AI Studio 路径引用",
                       [{"stdout": proc.stdout[-2000:]}])
    # 静态扫描防"代码里写了"，防不住"环境配歪了"——运行时再断言一次：
    # 这台机器此刻若构造 VertexModel，会不会走上 AI Studio 计费路径。
    try:
        from campuspath_agents.vertex import assert_vertex_only

        assert_vertex_only()
    except Exception as exc:  # noqa: BLE001
        return _failed("B12", "AI Studio 路径", "= 0 引用", None,
                       f"运行时环境自检失败：{exc}", [])
    return _passed("B12", "AI Studio 路径", "= 0 引用", 0,
                   "静态：check_ai_studio.py 全库零引用（含 9 个自检探针）；"
                   "运行时：assert_vertex_only 确认本环境只可能走 Vertex")


# ── B13 Outreach Consent Integrity ───────────────────────────────────
@check("B13")
def b13_outreach_consent() -> Result:
    """没有有效同意就不可能构造 outreach——**类型/异常层保证**。"""
    from campuspath_contracts.wellbeing import OutreachConsent, WellbeingSignalType
    from campuspath_wellbeing.composer import OutreachWithoutConsent, build_outreach
    from campuspath_rules.wellbeing import WellbeingInputs

    client = api_client()
    now = datetime(2026, 9, 15, 9, tzinfo=timezone.utc)
    signals = client.get("/v1/students/STU-B/wellbeing/signals", headers=_HEADERS).json()
    if not signals:
        return _failed("B13", "Outreach Consent Integrity", "= 100%", None,
                       "STU-B 没有信号——这条检查什么也没测到", [])

    from campuspath_contracts.wellbeing import WellbeingCapacitySignal

    signal = WellbeingCapacitySignal(**signals[0])
    revoked = OutreachConsent(
        consent_id="EVAL-B13", student_id=signal.student_id,
        scope="single_request", recipient_role="counseling_wellbeing_queue",
        granted_at=now - timedelta(days=2), revoked_at=now - timedelta(days=1),
    )
    gate_works = False
    try:
        build_outreach(signal, revoked, internal_student_ref="ref",
                       acknowledgement_url="https://example.invalid/a", now=now)
    except OutreachWithoutConsent:
        gate_works = True
    if not gate_works:
        return _failed("B13", "Outreach Consent Integrity", "= 100%", 0,
                       "已撤销的同意竟然能构造出 outreach",
                       [{"consent": "EVAL-B13", "revoked_at": str(revoked.revoked_at)}])

    valid = OutreachConsent(
        consent_id="EVAL-B13-OK", student_id=signal.student_id,
        scope="single_request", recipient_role="counseling_wellbeing_queue",
        granted_at=now - timedelta(hours=1),
    )
    request = build_outreach(signal, valid, internal_student_ref="ref",
                             acknowledgement_url="https://example.invalid/a", now=now)
    fields = set(request.email_fields.model_dump())
    forbidden = fields & (STUDENT_IDENTITY_TERMS | CALENDAR_DETAIL_TERMS)
    if forbidden:
        return _failed("B13", "Outreach Consent Integrity", "= 100%", len(forbidden),
                       "outreach 邮件字段超出白名单", [{"fields": sorted(forbidden)}])
    return _passed("B13", "Outreach Consent Integrity", "= 100%", "100%",
                   "已撤销同意被拒；有效同意产出的邮件字段全部在白名单内")
