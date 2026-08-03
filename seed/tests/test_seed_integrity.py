"""Seed 的验收测试（WP2）。

三件事：数据集本身自洽、检查器抓得住已知矛盾、两次构建字节一致。
第二件最容易被省略，也最重要——一个永远绿的检查器比没有检查器更危险。
"""

from __future__ import annotations

import pytest

from campuspath_seed.build import _canonical_json, build_seed
from campuspath_seed.config import FULL_SCALE_FLOORS, GOLD_SET_FLOORS
from campuspath_seed.consistency import MUTATIONS, run_checks, run_selftest
from campuspath_seed.failures import FAILURE_KINDS


@pytest.fixture(scope="module")
def full() -> dict:
    return build_seed("full")


@pytest.fixture(scope="module")
def tiny() -> dict:
    return build_seed("tiny")


def test_full_dataset_is_consistent(full):
    failures = [f"{r.name}: {r.detail}" for r in run_checks(full) if not r.ok]
    assert failures == []


def test_tiny_dataset_is_consistent(tiny):
    failures = [f"{r.name}: {r.detail}" for r in run_checks(tiny) if not r.ok]
    assert failures == []


@pytest.mark.parametrize("label", [m[0] for m in MUTATIONS])
def test_every_known_contradiction_is_caught(full, label):
    """H5：逐个变异断言**对应的那一项**检查会失败。

    只断言"有某项检查失败"是不够的——那样一个过于宽泛的检查会掩盖其余全部失效。
    """
    outcome = next(r for r in run_selftest(full) if r[0].startswith(label))
    assert outcome[1], f"{label} 未被检查器抓住：{outcome[2]}"


def test_build_is_byte_reproducible():
    assert _canonical_json(build_seed("full")) == _canonical_json(build_seed("full"))


def test_tiny_build_is_byte_reproducible():
    assert _canonical_json(build_seed("tiny")) == _canonical_json(build_seed("tiny"))


def test_scale_floors_are_met(full):
    counts = {
        "students": len(full["students"]),
        "programs": len(full["programs"]),
        "catalog_courses": len(full["courses"]),
        "publishers": len(full["publisher_grants"]),
        "submissions": len(full["publication_submissions"]),
        "profile_events": len(full["profile_update_proposals"]),
        "historical_feedback": len(full["event_quality_feedback"]),
    }
    for key, value in counts.items():
        assert value >= FULL_SCALE_FLOORS[key], f"{key}={value} 低于下限"


def test_gold_set_floors_are_met(full):
    gold = full["gold_set"]
    assert len(gold["eligibility"]) >= GOLD_SET_FLOORS["eligibility"]
    assert len(gold["course_constraints"]) >= GOLD_SET_FLOORS["course_constraints"]
    assert len(gold["replan"]) >= GOLD_SET_FLOORS["replan"]
    assert len(gold["memory_regression"]) >= GOLD_SET_FLOORS["memory_regression"]


def test_all_sixteen_failure_kinds_are_covered(full):
    """Spec §11.3 列了 16 类，D4 只要求 ≥12——这里做满。"""
    covered = {case["kind"] for case in full["failure_cases"]}
    assert covered == set(FAILURE_KINDS)


def test_gold_labels_are_marked_as_rule_generated(full):
    """R8：这是规则生成的初版标签，人工复核前不得当作已验证的准确率基线。"""
    for row in full["gold_set"]["eligibility"]:
        assert row["review_status"] == "rule_generated"


def test_replan_cases_declare_unaffected_scope(full):
    """T5 判的是"只改受影响路径"，没有 unaffected 就无法证伪。"""
    for case in full["gold_set"]["replan"]:
        assert case["expected_unaffected"], case["case_id"]


def test_persona_without_sleep_window_cannot_trigger_sleep_signal(full):
    """B6 的反例样本必须真的存在：Persona A 没有设置睡眠窗口。"""
    a = next(s for s in full["students"] if s["student_id"] == "STU-A")
    assert a["energy_profile"]["sleep_window_start"] is None
    assert a["energy_profile"]["recovery_preference_defined"] is False

    sleep_blocks = [
        b for b in full["availability_blocks"]
        if b["student_id"] == "STU-A" and "sleep" in b["block_id"]
    ]
    assert sleep_blocks == []


def test_persona_with_sleep_window_has_protected_blocks(full):
    """反过来，设置了窗口的 Persona B 必须有对应的保护区块，否则演示不了正例。"""
    b = next(s for s in full["students"] if s["student_id"] == "STU-B")
    assert b["energy_profile"]["sleep_window_start"] is not None
    sleep_blocks = [
        x for x in full["availability_blocks"]
        if x["student_id"] == "STU-B" and "sleep" in x["block_id"]
    ]
    assert len(sleep_blocks) >= 7
    assert all(x["type"] == "protected" for x in sleep_blocks)


def test_at_least_one_overloaded_and_one_healthy_week(full):
    """容量数据要有对照：全是超载或全不超载都测不出 B1。"""
    signals = {s["overload_signal"] for s in full["capacity_snapshots"]}
    assert signals == {True, False}


def test_publication_state_machine_branches_are_present(full):
    """D5 要求退回与驳回各演示一次。"""
    statuses = {s["status"] for s in full["publication_submissions"]}
    assert "changes_requested" in statuses
    assert "rejected" in statuses
    assert "published" in statuses


def test_scope_violations_reference_existing_grants(full):
    grants = {g["grant_id"] for g in full["publisher_grants"]}
    for violation in full["scope_violations"]:
        assert violation["grant_id"] in grants


def test_rejected_proposal_branch_exists(full):
    """没有被拒绝的提案，B3 就没有可测的样本。"""
    decisions = {e["decision"] for e in full["profile_change_events"]}
    assert "rejected" in decisions


def test_course_catalog_keeps_real_prerequisite_expressions(full):
    """真实先修表达式是 Rules Engine 的测试素材，不能在 Seed 里被解析掉。"""
    expressions = [
        c["prerequisite_expression"] for c in full["courses"]
        if c["prerequisite_expression"]
    ]
    assert any(" OR " in e for e in expressions)
    assert any(" AND " in e for e in expressions)
    assert any("(" in e for e in expressions)
