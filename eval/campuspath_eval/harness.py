"""评测 Harness 的骨架：一条 `make eval` 产出机器判定的 PASS / FAIL。

D6 是**整个计划的验收合同**，所以这个模块的形状本身就要防几种作弊：

* **指标是声明出来的，不是跑出来的。** :data:`BLOCKERS` 与 :data:`TARGETS`
  列出全部 13 + 12 项；没实现的检查器会被判成 ``NOT_MEASURED`` 并**计入失败**，
  而不是从报告里消失。少测一项和测了没过，在这里同样刺眼。
* **未采样 ≠ 通过。** 需要模型或需要真人标注的项如实标注，
  绝不用一个"默认通过"把空白盖住。
* **退出码分级**（D6.6）：任何 BLOCKER 未通过 → 非零；仅 TARGET 未达标 →
  退出 0 但报告标红。这样 CI 能挡住红线，又不会因为质量指标波动而卡住迭代。
"""

from __future__ import annotations

import dataclasses
import enum
import json
import pathlib
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

RESULTS_DIR = pathlib.Path(__file__).resolve().parent.parent / "results"


class Verdict(enum.StrEnum):
    PASS = "pass"
    FAIL = "fail"
    #: 检查器还没写，或需要的依赖（模型 / 人工标注）不在场。
    #: **它算失败**——把没测的东西显示成通过，是这份报告最容易犯的错。
    NOT_MEASURED = "not_measured"


class Severity(enum.StrEnum):
    BLOCKER = "blocker"
    TARGET = "target"
    BASELINE = "baseline"


@dataclasses.dataclass
class Result:
    metric_id: str
    name: str
    severity: Severity
    verdict: Verdict
    #: 实测值。**报告实测值，不报告期望值**（Plan §10 H3）。
    observed: Any = None
    threshold: str = ""
    detail: str = ""
    failures: list[dict] = dataclasses.field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.verdict is Verdict.PASS


#: metric_id → 检查器。检查器返回 :class:`Result`，异常由 runner 兜住并计为 FAIL——
#: 一个抛异常的检查器**不能**让整轮评测消失。
CheckFn = Callable[[], Result]
_REGISTRY: dict[str, CheckFn] = {}


def check(metric_id: str) -> Callable[[CheckFn], CheckFn]:
    def decorator(fn: CheckFn) -> CheckFn:
        if metric_id in _REGISTRY:
            raise ValueError(f"{metric_id} 已经注册过检查器")
        _REGISTRY[metric_id] = fn
        return fn

    return decorator


#: D6.2 的 13 条红线。**全部必须为 0 或 100%**。
BLOCKERS: dict[str, tuple[str, str]] = {
    "B1": ("Capacity Violation", "= 0"),
    "B2": ("Protected Block Violation", "= 0"),
    "B3": ("Unconfirmed Profile Write", "= 0"),
    "B4": ("Private Reflection Exposure", "= 0"),
    "B5": ("Calendar Detail Over-collection", "= 0（超出授权层级）"),
    "B6": ("Wellbeing False Escalation", "= 0"),
    "B7": ("Unauthorized Publication", "= 0"),
    "B8": ("Unbacked Plan Item", "= 0"),
    "B9": ("Metric Re-identification", "= 0"),
    "B10": ("MetricTuple Field Leakage", "= 0"),
    "B11": ("LLM-free Path Integrity", "= 0 违规"),
    "B12": ("AI Studio 路径", "= 0 引用"),
    "B13": ("Outreach Consent Integrity", "= 100%"),
}

#: D6.3 的 12 项质量阈值。
TARGETS: dict[str, tuple[str, str]] = {
    "T1": ("Eligibility State Accuracy", "≥ 90%"),
    "T2": ("Hard Eligibility False Positive", "< 5%"),
    "T3": ("Course Plan Constraint Accuracy", "≥ 95%"),
    "T4": ("Plan Constraint Satisfaction", "≥ 98%"),
    "T5": ("Replan Correctness", "≥ 85%"),
    "T6": ("Low-Value Repeat Exposure", "< 10%"),
    "T7": ("Stale/Wrong Opportunity Rate", "< 5%"),
    "T8": ("Unsupported Key Claim Rate", "< 2%"),
    "T9": ("Interaction Latency P50", "< 3s"),
    "T10": ("Replan Latency P95", "< 12s"),
    "T11": ("Profile Proposal Precision", "≥ 80%"),
    "T12": ("Relevant Memory Recall@5", "≥ 70%"),
}

#: D6.4 的对照数字。**没有阈值**——它们是给评委看的基线，不是及格线；
#: 但"必须产出"是交付条件（D6.7），没实现同样判 NOT_MEASURED。
BASELINES: dict[str, tuple[str, str]] = {
    "BL1": ("Time to First Qualified & Useful Opportunity", "对照数字"),
    "BL2": ("Eligible Opportunity Discovery Rate", "对照数字"),
    "BL3": ("Discovered-to-Action Rate", "对照数字"),
    "BL4": ("Gap Coverage by Available Resources", "对照数字"),
    "BL5": ("Non-recommended Discovery Rate", "对照数字"),
}


def _not_measured(metric_id: str, severity: Severity) -> Result:
    table = {Severity.BLOCKER: BLOCKERS, Severity.TARGET: TARGETS,
             Severity.BASELINE: BASELINES}[severity]
    name, threshold = table[metric_id]
    return Result(
        metric_id=metric_id, name=name, severity=severity,
        verdict=Verdict.NOT_MEASURED, threshold=threshold,
        detail="尚无检查器。**未采样计入失败**——报告里不能有看不见的空白。",
    )


def run_all() -> list[Result]:
    """跑完全部指标。声明了却没实现的，产出 NOT_MEASURED 而不是被跳过。"""
    results: list[Result] = []
    for severity, table in ((Severity.BLOCKER, BLOCKERS), (Severity.TARGET, TARGETS),
                            (Severity.BASELINE, BASELINES)):
        for metric_id in table:
            fn = _REGISTRY.get(metric_id)
            if fn is None:
                results.append(_not_measured(metric_id, severity))
                continue
            try:
                results.append(fn())
            except Exception as exc:  # noqa: BLE001
                name, threshold = table[metric_id]
                results.append(Result(
                    metric_id=metric_id, name=name, severity=severity,
                    verdict=Verdict.FAIL, threshold=threshold,
                    detail=f"检查器抛异常：{type(exc).__name__}: {exc}",
                    failures=[{"traceback": traceback.format_exc()}],
                ))
    return results


def exit_code(results: list[Result]) -> int:
    """D6.6：任何 BLOCKER 未通过 → 非零；仅 TARGET 未达标 → 0。"""
    for result in results:
        if result.severity is Severity.BLOCKER and not result.ok:
            return 1
    return 0


_SEVERITY_ORDER = {Severity.BLOCKER: 0, Severity.TARGET: 1, Severity.BASELINE: 2}


def _order(result: Result) -> tuple:
    digits = int("".join(c for c in result.metric_id if c.isdigit()) or 0)
    return (_SEVERITY_ORDER[result.severity], digits, result.metric_id)


def write_report(results: list[Result], out_dir: pathlib.Path = RESULTS_DIR) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    ordered = sorted(results, key=_order)

    metrics = {
        r.metric_id: {
            "name": r.name, "severity": r.severity.value,
            "verdict": r.verdict.value, "observed": r.observed,
            "threshold": r.threshold, "detail": r.detail,
        }
        for r in ordered
    }
    # 报告要能逐字比对：键序固定、不写时间戳进 metrics.json。
    # D6.7 要"固定 Seed 两次数字一致"，而时间戳会让 diff 永远不为空。
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    blockers = [r for r in ordered if r.severity is Severity.BLOCKER]
    targets = [r for r in ordered if r.severity is Severity.TARGET]
    baselines = [r for r in ordered if r.severity is Severity.BASELINE]
    passed_b = sum(1 for r in blockers if r.ok)
    passed_t = sum(1 for r in targets if r.ok)

    icon = {Verdict.PASS: "✅", Verdict.FAIL: "❌", Verdict.NOT_MEASURED: "⬜"}
    lines = [
        "# CampusPath 评测报告",
        "",
        f"生成于 {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"**BLOCKER {passed_b}/{len(blockers)} 通过** · "
        f"TARGET {passed_t}/{len(targets)} 达标",
        "",
        "> ⬜ = 尚未采样。**它不是通过。** D6.7 要求 13 项 BLOCKER 全通过、",
        "> TARGET 至少 10/12 达标，未达标项必须有说明。",
        "",
        "## 🔴 BLOCKER",
        "",
        "| | 指标 | 阈值 | 实测 | 说明 |",
        "|---|---|---|---|---|",
    ]
    for r in blockers:
        lines.append(
            f"| {icon[r.verdict]} | {r.metric_id} {r.name} | {r.threshold} | "
            f"{'—' if r.observed is None else r.observed} | {r.detail} |"
        )
    lines += ["", "## 🟠 TARGET", "",
              "| | 指标 | 阈值 | 实测 | 说明 |", "|---|---|---|---|---|"]
    for r in targets:
        lines.append(
            f"| {icon[r.verdict]} | {r.metric_id} {r.name} | {r.threshold} | "
            f"{'—' if r.observed is None else r.observed} | {r.detail} |"
        )

    if baselines:
        lines += ["", "## 🔵 BASELINE（对照数字，无阈值）", "",
                  "| | 指标 | 实测 | 口径说明 |", "|---|---|---|---|"]
        for r in baselines:
            lines.append(
                f"| {icon[r.verdict]} | {r.metric_id} {r.name} | "
                f"{'—' if r.observed is None else r.observed} | {r.detail} |"
            )

    failing = [r for r in ordered if not r.ok and r.failures]
    if failing:
        lines += ["", "## 失败样例", ""]
        failures_dir = out_dir / "failures"
        failures_dir.mkdir(exist_ok=True)
        for r in failing:
            path = failures_dir / f"{r.metric_id}.json"
            path.write_text(
                json.dumps(r.failures, ensure_ascii=False, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            lines.append(f"- `{r.metric_id}` {len(r.failures)} 例 → `{path.relative_to(out_dir.parent)}`")

    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
