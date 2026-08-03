"""构造合法样例的工厂。

原则：**工厂只造"应该通过"的对象**。每个测试自己去破坏它想破坏的那一处，
这样断言失败时能立刻定位到是哪条契约被破坏，而不是"某个 fixture 变了"。
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from campuspath_contracts.common import (
    Locale,
    LocalizedText,
    Provenance,
    SourceRef,
)
from campuspath_contracts.validation import (
    ConstraintValidation,
    InMemoryValidationRegistry,
    RuleCategory,
    ValidationReason,
    Verdict,
    deterministic_validation_id,
)

NOW = datetime(2026, 7, 29, 9, 0, tzinfo=timezone.utc)
TODAY = date(2026, 7, 29)


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest.fixture
def text() -> LocalizedText:
    return LocalizedText(zh_Hans="示例文案", en="Sample text")


@pytest.fixture
def provenance() -> Provenance:
    return Provenance(
        source="hkust_ugcourse",
        source_url="https://prog-crs.hkust.edu.hk/ugcourse/2025-26/COMP",
        retrieved_at=NOW,
        parser_version="hkust-catalog/0.1",
        confidence=1.0,
    )


def make_validation(
    entity_type: str,
    entity_id: str,
    *,
    verdict: Verdict = Verdict.SATISFIED,
    expires_at: datetime | None = None,
) -> ConstraintValidation:
    ref = SourceRef(entity_type=entity_type, entity_id=entity_id)
    return ConstraintValidation(
        validation_id=deterministic_validation_id("rules/2026.07", ref),
        rule_set_version="rules/2026.07",
        subject_ref=ref,
        verdict=verdict,
        reasons=(
            ValidationReason(
                rule_id="PREREQ.COMP2011",
                category=RuleCategory.PREREQUISITE,
                verdict=verdict,
                message=LocalizedText(zh_Hans="先修已满足", en="Prerequisite met"),
                observed="COMP 1021 completed",
                expected="COMP 1021",
            ),
        ),
        evaluated_at=NOW,
        expires_at=expires_at,
    )


@pytest.fixture
def registry() -> InMemoryValidationRegistry:
    """预先签发几条常用凭据的 Registry。"""
    reg = InMemoryValidationRegistry()
    for entity_type, entity_id in (
        ("course", "COMP 2011"),
        ("course", "MATH 2011"),
        ("opportunity", "OPP-001"),
        ("action", "ACT-001"),
    ):
        reg.issue(make_validation(entity_type, entity_id))
    return reg


@pytest.fixture
def expiring_registry() -> InMemoryValidationRegistry:
    reg = InMemoryValidationRegistry()
    reg.issue(make_validation("course", "COMP 2011", expires_at=NOW - timedelta(days=1)))
    return reg


@pytest.fixture
def locales() -> tuple[Locale, Locale]:
    return (Locale.ZH_HANS, Locale.EN)
