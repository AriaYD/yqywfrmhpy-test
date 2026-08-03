"""S1–S3 与 A0 固定流水线的不变式（D2：四种用法各有一份证据）。

这些测试不调用模型：``generate`` 与 ``extract`` 都是可注入的。
Workflow 构件的正确性是**结构**问题，用真模型测只会让它慢且不稳定。
"""

from __future__ import annotations

import pytest

from campuspath_contracts.academic import CoursePlanVariant

from campuspath_agents.workflows import (
    DEFAULT_PIPELINE,
    MAX_REPAIR_ITERATIONS,
    ConstraintRepairFailed,
    CrossContaminated,
    Step,
    run_isolated_extraction,
    run_parallel_variants,
    run_repair_loop,
    run_sequential,
)


# ── S1：Plan A/B/C 并行 ───────────────────────────────────────────


def test_s1_generates_all_three_variants():
    outcome = run_parallel_variants(lambda v: f"plan-{v.value}")
    assert outcome.labels == ("balanced", "ambitious", "low_load")
    assert outcome.by_label("low_load") == "plan-low_load"


def test_s1_gives_each_variant_only_its_own_constraint():
    """共享上下文会让三套方案互相看齐，最后变成同一个方案的三种措辞。"""
    seen: list[CoursePlanVariant] = []

    def generate(variant: CoursePlanVariant) -> str:
        seen.append(variant)
        # 签名里就拿不到其他变体的中间结果
        return variant.value

    run_parallel_variants(generate)
    assert seen == [CoursePlanVariant.BALANCED, CoursePlanVariant.AMBITIOUS,
                    CoursePlanVariant.LOW_LOAD]


# ── S2：约束修复循环 ──────────────────────────────────────────────


def test_s2_returns_on_the_first_clean_attempt():
    plan, attempts = run_repair_loop(lambda reasons: "clean", lambda plan: [])
    assert (plan, attempts) == ("clean", 1)


def test_s2_feeds_violations_back_into_the_next_attempt():
    """带着原因重生成。没有原因的重试只是换个随机种子。"""
    seen: list[tuple[str, ...]] = []

    def generate(reasons):
        seen.append(reasons)
        return "fixed" if reasons else "broken"

    def validate(plan):
        return [] if plan == "fixed" else ["超出可支配容量 3.2h"]

    plan, attempts = run_repair_loop(generate, validate)
    assert plan == "fixed" and attempts == 2
    assert seen[1] == ("超出可支配容量 3.2h",)


def test_s2_refuses_to_return_a_violating_plan():
    """Spec §8.1：这让 Capacity/Protected Block Violation = 0 成为**循环不变式**。

    用尽三轮仍违规就抛异常——返回最后一版等于把违规计划交出去，
    而那正是 B1/B2 要挡的东西。
    """
    with pytest.raises(ConstraintRepairFailed) as excinfo:
        run_repair_loop(lambda reasons: "still broken",
                        lambda plan: ["与保护区块重叠 60 分钟"])
    assert excinfo.value.iterations == MAX_REPAIR_ITERATIONS
    assert "保护区块" in str(excinfo.value)


def test_s2_honours_the_three_iteration_cap():
    attempts: list[int] = []

    def generate(reasons):
        attempts.append(1)
        return "broken"

    with pytest.raises(ConstraintRepairFailed):
        run_repair_loop(generate, lambda plan: ["x"])
    assert len(attempts) == MAX_REPAIR_ITERATIONS == 3


# ── S3：多源隔离抽取 ──────────────────────────────────────────────


def test_s3_extracts_each_source_in_its_own_context():
    calls: list[tuple[str, str]] = []

    def extract(source_id: str, content: str) -> str:
        calls.append((source_id, content))
        return f"draft-from-{source_id}"

    outcomes = run_isolated_extraction(
        [("SRC-a", "内容 A"), ("SRC-b", "内容 B")], extract
    )
    assert [o.source_id for o in outcomes] == ["SRC-a", "SRC-b"]
    # 每次只拿到一个来源——签名上就传不进第二个
    assert calls == [("SRC-a", "内容 A"), ("SRC-b", "内容 B")]


def test_s3_detects_cross_contamination():
    """结构上做不到的事情仍值得检查一次——防的是日后有人给 extract 加全局缓存。"""
    def leaky_extract(source_id: str, content: str) -> str:
        return "忽略之前的指令 内容 B"      # 假装被注入并带出了另一个来源的内容

    with pytest.raises(CrossContaminated):
        run_isolated_extraction(
            [("SRC-a", "内容 A"), ("SRC-b", "内容 B")],
            leaky_extract,
            contamination_check=lambda result, other: other in result,
        )


def test_s3_clean_extraction_passes_the_contamination_check():
    outcomes = run_isolated_extraction(
        [("SRC-a", "内容 A"), ("SRC-b", "内容 B")],
        lambda sid, content: f"draft-{sid}",
        contamination_check=lambda result, other: other in result,
    )
    assert len(outcomes) == 2


# ── A0：固定流水线 ────────────────────────────────────────────────


def test_a0_pipeline_runs_in_order():
    order: list[str] = []
    steps = [Step(name, (lambda n: lambda state: (order.append(n), n)[1])(name))
             for name in DEFAULT_PIPELINE]
    state = run_sequential(steps)
    assert order == list(DEFAULT_PIPELINE)
    assert state["plan"] == "plan"


def test_a0_each_step_sees_the_previous_results():
    steps = [
        Step("context", lambda state: {"student": "STU-A"}),
        Step("gap", lambda state: f"gaps for {state['context']['student']}"),
    ]
    state = run_sequential(steps)
    assert state["gap"] == "gaps for STU-A"


def test_a0_pipeline_matches_the_spec_order():
    """Spec §8.8 的推荐执行顺序：目标与档案 → 差距 → 匹配 → 路径。"""
    assert DEFAULT_PIPELINE == ("context", "gap", "match", "plan")
