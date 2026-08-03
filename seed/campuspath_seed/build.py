"""Seed 构建器：把各模块的产出汇总成可复现的数据集。

输出是**确定性的**：键序固定、缩进固定、时间来自 :data:`SEED_TODAY`。
同一版本跑两次必须字节一致，由 ``consistency.py`` 的
``check_reproducible`` 直接比对两次构建结果验证——不是"应该一致"，是跑出来一致。

所有实体都是契约层的模型实例，序列化前已经过 Pydantic 校验：
数据集里不可能出现违反 B1/B2/B3/B6/B9 的记录，因为那些对象根本构造不出来。
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from .calendars import build_calendars
from .catalog import load_catalog
from .config import (
    CURRENT_TERM,
    PROFILES,
    SEED_TODAY,
    SEED_VERSION,
    SYNTHETIC_NOTICE,
    ScaleProfile,
)
from .events import build_events
from .failures import build_failure_cases
from .feedback import build_feedback
from .goldset import build_gold_set
from .opportunities import build_opportunities
from .personas import build_personas
from .publishing import build_publishing

OUT_DIR = pathlib.Path(__file__).resolve().parent.parent / "generated"


def _dump(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value


def _serialise(items: list[Any]) -> list[Any]:
    return [_dump(item) for item in items]


def build_seed(profile_name: str = "full") -> dict[str, Any]:
    scale: ScaleProfile = PROFILES[profile_name]

    # tiny 只建 Persona A 所在的培养方案，保证引用完整（见 load_catalog 的说明）
    catalog = load_catalog(("BSC-COMP",) if profile_name == "tiny" else None)
    personas = build_personas(catalog, scale.deep_personas, scale.slim_students)
    opportunities, opportunity_meta = build_opportunities(
        catalog,
        internships=scale.internships,
        events=scale.events,
        labs=scale.labs,
        competitions=scale.competitions,
    )
    # 真实的校园活动（HKUST Engage 公开页）与合成机会并存：
    # 真实源以讲座/研讨会为主，覆盖不到"投递实习"那条主线，两者互补。
    # tiny 剖面不加，保持它"最小可复现"的本意。
    if profile_name != "tiny":
        from .campus_events import load_campus_events

        real_events = load_campus_events(
            datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)
        )
        opportunities.extend(real_events)

    calendars = build_calendars(catalog, personas, scale.calendar_weeks)
    publishing = build_publishing(
        opportunities, publishers=scale.publishers, submissions=scale.submissions
    )
    feedback = build_feedback(opportunities, personas, scale.historical_feedback)
    failure_cases, failure_extra = build_failure_cases(
        opportunities, personas, low_quality_series=feedback.persistently_low_series
    )
    opportunities = opportunities + failure_extra
    events = build_events(personas, scale.profile_events)
    gold = build_gold_set(
        personas, opportunities, catalog,
        eligibility=60 if profile_name == "full" else 8,
        course_constraints=40 if profile_name == "full" else 5,
        memory_regression=20 if profile_name == "full" else 4,
    )

    bundle: dict[str, Any] = {
        "manifest": {
            "seed_version": SEED_VERSION,
            "scale_profile": scale.name,
            "as_of": SEED_TODAY.isoformat(),
            "current_term": CURRENT_TERM,
            "notice": SYNTHETIC_NOTICE,
            "real_data": (
                "课程目录与校园活动来自 HKUST 公开页面（prog-crs / calendar）；"
                "学生、成绩、日历、实习机会全部合成"
            ),
        },
        "programs": _serialise(catalog.programs),
        "degree_requirements": _serialise(catalog.requirements),
        "courses": _serialise(sorted(catalog.courses.values(), key=lambda c: c.course_id)),
        "course_offerings": _serialise(catalog.offerings),
        "students": _serialise([p.profile for p in personas]),
        "student_display": {
            p.profile.student_id: p.display for p in personas
        },
        "student_course_records": _serialise(
            [r for p in personas for r in p.course_records]
        ),
        "experiences": _serialise([e for p in personas for e in p.experiences]),
        "projects": _serialise([x for p in personas for x in p.projects]),
        "achievements": _serialise([a for p in personas for a in p.achievements]),
        "skills": _serialise([s for p in personas for s in p.skills]),
        "evidence": _serialise([e for p in personas for e in p.evidence]),
        "notes": _serialise([n for p in personas for n in p.notes]),
        "goals": _serialise([g for p in personas for g in p.goals]),
        "calendar_connections": _serialise(calendars.connections),
        "availability_blocks": _serialise(calendars.blocks),
        "capacity_snapshots": _serialise(calendars.snapshots),
        "opportunities": _serialise(opportunities),
        "opportunity_meta": _serialise(opportunity_meta),
        "publisher_grants": _serialise(publishing.grants),
        "publication_submissions": _serialise(publishing.submissions),
        "moderation_decisions": _serialise(publishing.decisions),
        "scope_violations": _serialise(publishing.violations),
        "event_quality_feedback": _serialise(feedback.feedback),
        "metric_tuples": _serialise(feedback.metric_tuples),
        "profile_update_proposals": _serialise(events.proposals),
        "profile_change_events": _serialise(events.change_events),
        "memory_entries": _serialise(events.memories),
        "gold_set": {
            "seed_version": gold.seed_version,
            "eligibility": _serialise(gold.eligibility),
            "course_constraints": _serialise(gold.course_constraints),
            "replan": _serialise(gold.replan),
            "memory_regression": _serialise(gold.memory_regression),
        },
        "failure_cases": _serialise(failure_cases),
    }
    return bundle


def _canonical_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_seed(profile_name: str = "full", out_dir: pathlib.Path | None = None) -> pathlib.Path:
    """写出数据集与校验和。返回输出目录。"""
    bundle = build_seed(profile_name)
    target = (out_dir or OUT_DIR) / profile_name
    target.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    for key, value in sorted(bundle.items()):
        if key == "manifest":
            continue
        payload = _canonical_json({key: value})
        path = target / f"{key}.json"
        path.write_text(payload, encoding="utf-8")
        checksums[key] = hashlib.sha256(payload.encode()).hexdigest()[:16]

    manifest = dict(bundle["manifest"])
    manifest["checksums"] = checksums
    manifest["record_counts"] = {
        key: (len(value) if isinstance(value, (list, dict)) else 1)
        for key, value in sorted(bundle.items()) if key != "manifest"
    }
    (target / "manifest.json").write_text(_canonical_json(manifest), encoding="utf-8")
    return target
