"""真实先修表达式的来源：WP2 冻结的 HKUST 课程目录快照。"""

from __future__ import annotations

import json
import pathlib

import pytest

CATALOG = (
    pathlib.Path(__file__).resolve().parents[3]
    / "seed" / "raw" / "hkust_catalog" / "courses.json"
)


@pytest.fixture(scope="session")
def real_expressions() -> list[str]:
    courses = json.loads(CATALOG.read_text(encoding="utf-8"))
    return sorted({c["prerequisite"] for c in courses if c.get("prerequisite")})
