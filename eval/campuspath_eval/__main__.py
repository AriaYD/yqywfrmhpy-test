"""`make eval` 的入口。

退出码分级（D6.6）：任何 BLOCKER 未通过 → 非零；仅 TARGET 未达标 → 0。
"""

from __future__ import annotations

import sys

from . import baselines, blockers, targets  # noqa: F401  —— import 即注册检查器
from .harness import Severity, Verdict, exit_code, run_all, write_report


def main() -> int:
    results = run_all()
    write_report(results)

    icon = {Verdict.PASS: "✅", Verdict.FAIL: "❌", Verdict.NOT_MEASURED: "⬜"}
    from .harness import _order

    for result in sorted(results, key=_order):
        observed = "—" if result.observed is None else result.observed
        print(f"{icon[result.verdict]} {result.metric_id:4s} {result.name:38s} "
              f"{result.threshold:22s} 实测 {observed}")

    blockers_ = [r for r in results if r.severity is Severity.BLOCKER]
    targets_ = [r for r in results if r.severity is Severity.TARGET]
    print()
    print(f"BLOCKER {sum(r.ok for r in blockers_)}/{len(blockers_)} · "
          f"TARGET {sum(r.ok for r in targets_)}/{len(targets_)}")
    print("报告 → eval/results/report.md")
    return exit_code(results)


if __name__ == "__main__":
    sys.exit(main())
