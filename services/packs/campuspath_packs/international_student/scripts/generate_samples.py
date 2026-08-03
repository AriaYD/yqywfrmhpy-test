#!/usr/bin/env python3
"""Generate committed frontend samples from the deterministic evaluator."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from campuspath_context import ContextPackEvaluator, read_data  # noqa: E402

SAMPLES = {
    "hk-recent-graduate.json": "hk-recent-graduate.json",
    "mainland-graduate-employment.json": "mainland-graduate-employment.json",
}


def main() -> None:
    evaluator = ContextPackEvaluator()
    for sample_name, fixture_name in SAMPLES.items():
        result = evaluator.evaluate(read_data(ROOT / "fixtures" / fixture_name), as_of="2026-08-01")
        (ROOT / "samples" / sample_name).write_text(
            json.dumps(result, ensure_ascii=True, indent=2) + "\n",
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
