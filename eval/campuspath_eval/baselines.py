"""D6.4 的五项 BASELINE 对照数字。

**没有阈值。** 它们回答"比起不用 CampusPath 好多少"，不是及格线。
全部确定性可复现：排序零模型（模型只写理由文案，不影响顺序），
资格判定走 Rules Engine，输入与 T1 检查器完全一致。

口径限制如实写在每条 detail 里——对照数字最怕的是看起来像实验、
实际是自说自话。"vs 普通 RAG"那一列需要真实 RAG 基线对跑，
本轮不假装测过。
"""

from __future__ import annotations

import statistics
from datetime import date

from campuspath_contracts.common import ActorRole

from .fixtures import api_client, seed_bundle
from .harness import Result, Severity, Verdict, check
from .targets import _academic_record, _future_offerings

_HEADERS = {"X-CampusPath-Role": ActorRole.STUDENT.value}
_DEEP = ("STU-A", "STU-B", "STU-C")
_TOP_N = 20


def _result(metric_id: str, name: str, observed, detail: str) -> Result:
    return Result(metric_id=metric_id, name=name, severity=Severity.BASELINE,
                  verdict=Verdict.PASS, observed=observed, threshold="对照数字",
                  detail=detail)


def _eligible_now_ids(student_id: str) -> set[str]:
    """与 T1 检查器同一套输入的 Rules 判定：这个学生现在就能报的机会。"""
    from campuspath_contracts.opportunity import (
        EligibilityStateName, Opportunity, PublicationStatus,
    )
    from campuspath_rules.eligibility import StudentEligibilityFacts, assess

    bundle = seed_bundle()
    student = next(s for s in bundle["students"] if s["student_id"] == student_id)
    today = date.fromisoformat(bundle["manifest"]["as_of"])
    facts = StudentEligibilityFacts(
        student_id=student_id, year_level=student["year"],
        program_id=student["program_id"],
        academic=_academic_record(student_id),
        future_offerings=_future_offerings(),
    )
    out: set[str] = set()
    for row in bundle["opportunities"]:
        if row["publication_status"] != PublicationStatus.PUBLISHED.value:
            continue
        opportunity = Opportunity(**row)
        if opportunity.deadline is not None and opportunity.deadline.date() < today:
            continue
        state = assess(opportunity, facts, today).state
        if state is EligibilityStateName.ELIGIBLE_NOW:
            out.add(opportunity.opportunity_id)
    return out


def _catalog_order() -> list[str]:
    client = api_client()
    rows = client.get("/v1/catalog/opportunities?limit=500", headers=_HEADERS).json()
    return [r["opportunity_id"] for r in rows]


def _top_matches(student_id: str) -> list[str]:
    client = api_client()
    rows = client.get(f"/v1/students/{student_id}/matches?limit={_TOP_N}",
                      headers=_HEADERS).json()
    return [r["opportunity_id"] for r in rows]


@check("BL1")
def bl1_time_to_first() -> Result:
    """到第一条「现在就能报」的机会要看多少条。

    人工搜索代理 = 按目录默认顺序顺扫，数到第一条 eligible_now 的位置；
    CampusPath = /matches 排序里第一条 eligible_now 的位置。
    """
    manual: list[int] = []
    ranked: list[int] = []
    for student_id in _DEEP:
        eligible = _eligible_now_ids(student_id)
        if not eligible:
            continue
        catalog = _catalog_order()
        manual.append(next(
            (i + 1 for i, oid in enumerate(catalog) if oid in eligible),
            len(catalog),
        ))
        top = _top_matches(student_id)
        ranked.append(next(
            (i + 1 for i, oid in enumerate(top) if oid in eligible), _TOP_N + 1,
        ))
    return _result(
        "BL1", "Time to First Qualified & Useful Opportunity",
        f"CampusPath 第 {statistics.median(ranked):.0f} 条 vs 目录顺扫第 {statistics.median(manual):.0f} 条",
        f"{len(manual)} 个深度 Persona 的中位数。人工搜索代理=目录默认序顺扫到首条 "
        "eligible_now；⚠️ D6.4 还要求 vs 普通 RAG——需要真实 RAG 基线对跑，"
        "本轮未测，不假装测过",
    )


@check("BL2")
def bl2_discovery_rate() -> Result:
    """实际合格的机会里，有多少出现在前 20 条推荐里（合格机会的召回率）。"""
    rates: list[float] = []
    for student_id in _DEEP:
        eligible = _eligible_now_ids(student_id)
        if not eligible:
            continue
        top = set(_top_matches(student_id))
        rates.append(len(eligible & top) / len(eligible))
    value = statistics.fmean(rates) if rates else 0.0
    return _result(
        "BL2", "Eligible Opportunity Discovery Rate", f"{value * 100:.1f}%",
        f"{len(rates)} 个深度 Persona 宏平均；分母=Rules 判定 eligible_now 的全部"
        f"未过期机会，分子=其中进入 top-{_TOP_N} 推荐的",
    )


@check("BL3")
def bl3_discovered_to_action() -> Result:
    """被推荐看见的机会里，有多少被（合成群体）实际行动过。

    质量反馈是去标识的（B10），无法按学生归因——这里的行动代理是
    「该机会的 occurrence 收到过 ≥1 条质量反馈」，群体口径。
    """
    bundle = seed_bundle()
    acted_occurrences = {
        f["occurrence_id"] for f in bundle["event_quality_feedback"]
    }
    occurrence_of = {
        r["opportunity_id"]: r.get("occurrence_id")
        for r in bundle["opportunities"]
    }
    discovered: set[str] = set()
    for student_id in _DEEP:
        discovered |= set(_top_matches(student_id))
    if not discovered:
        return _result("BL3", "Discovered-to-Action Rate", "0.0%", "无推荐结果")
    acted = {
        oid for oid in discovered
        if occurrence_of.get(oid) and occurrence_of[oid] in acted_occurrences
    }
    return _result(
        "BL3", "Discovered-to-Action Rate",
        f"{len(acted) / len(discovered) * 100:.1f}%",
        f"分母=三个深度 Persona top-{_TOP_N} 推荐的并集（{len(discovered)} 条），"
        "分子=其 occurrence 收到过质量反馈的；⚠️ 反馈按 B10 去标识，"
        "此为群体代理而非个体转化率",
    )


@check("BL4")
def bl4_gap_coverage() -> Result:
    """缺口类别里，有多少能在目录里找到至少一条对应资源。"""
    from campuspath_contracts.opportunity import PublicationStatus

    bundle = seed_bundle()
    catalog_categories: set[str] = set()
    for row in bundle["opportunities"]:
        if row["publication_status"] == PublicationStatus.PUBLISHED.value:
            catalog_categories.update(row.get("requirement_categories", ()))

    client = api_client()
    rates: list[float] = []
    per_student: list[str] = []
    for student_id in _DEEP:
        gap_map = client.get(f"/v1/students/{student_id}/gap-map",
                             headers=_HEADERS).json()
        needed: set[str] = set()
        for shared in gap_map.get("shared_gaps", ()):
            needed.add(shared["category"])
        if not needed:
            continue
        covered = needed & catalog_categories
        rates.append(len(covered) / len(needed))
        per_student.append(f"{student_id} {len(covered)}/{len(needed)}")
    value = statistics.fmean(rates) if rates else 0.0
    return _result(
        "BL4", "Gap Coverage by Available Resources", f"{value * 100:.1f}%",
        "缺口类别（gap-map 的共享缺口类别集）中，目录里存在 ≥1 条已发布"
        f"同类资源的比例；{'; '.join(per_student)}",
    )


@check("BL5")
def bl5_non_recommended_discovery() -> Result:
    """AI 未推荐、但学生仍能在广场里主动发现的机会占比（D1 的可发现性承诺）。"""
    catalog = set(_catalog_order())
    recommended: set[str] = set()
    for student_id in _DEEP:
        recommended |= set(_top_matches(student_id))
    if not catalog:
        return _result("BL5", "Non-recommended Discovery Rate", "0.0%", "目录为空")
    outside = catalog - recommended
    return _result(
        "BL5", "Non-recommended Discovery Rate",
        f"{len(outside) / len(catalog) * 100:.1f}%",
        f"目录 {len(catalog)} 条中不在任何深度 Persona top-{_TOP_N} 推荐里的比例——"
        "这些全部仍可经广场浏览/筛选主动发现（D1：发现不依赖 AI 是否推荐），"
        "且每条都可点开「为什么没推荐」",
    )
