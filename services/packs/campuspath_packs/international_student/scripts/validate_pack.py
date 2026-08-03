#!/usr/bin/env python3
"""Validate schemas, provenance, layer boundaries, and generated samples."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError:
    print("Pack validation requires jsonschema; install requirements.txt", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from campuspath_context import ContextPackEvaluator, PackLoader, read_data  # noqa: E402

SCHEMA_FILES = {
    "manifest": "context-pack.schema.json",
    "rule": "rule.schema.json",
    "source": "source.schema.json",
    "preparation": "preparation-item.schema.json",
    "support": "support-item.schema.json",
    "question": "question.schema.json",
    "procedure": "procedure.schema.json",
    "sample": "evaluation-result.schema.json",
}
SAMPLE_FIXTURES = {
    "hk-recent-graduate.json": "hk-recent-graduate.json",
    "mainland-graduate-employment.json": "mainland-graduate-employment.json",
}


def _validator(kind: str) -> Draft202012Validator:
    schema = read_data(ROOT / "schemas" / SCHEMA_FILES[kind])
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate_record(errors: list[str], validator: Draft202012Validator, record: Any, label: str) -> None:
    for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path)):
        location = ".".join(str(part) for part in error.absolute_path) or "<root>"
        errors.append(f"{label}:{location}: {error.message}")


def _records(errors: list[str], path: Path, key: str) -> list[dict[str, Any]]:
    data = read_data(path)
    if set(data) != {key} or not isinstance(data.get(key), list):
        errors.append(f"{path.relative_to(ROOT)} must contain only an array property named {key}")
        return []
    return data[key]


def main() -> int:
    errors: list[str] = []
    validators = {kind: _validator(kind) for kind in SCHEMA_FILES}

    for path in sorted(ROOT.rglob("*.yaml")) + sorted((ROOT / "samples").glob("*.json")):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"{path.relative_to(ROOT)} is not JSON-compatible YAML/JSON: {exc}")
    if errors:
        return _finish(errors)

    for path in sorted(ROOT.glob("base/manifest.yaml")) + sorted(ROOT.glob("jurisdictions/*/manifest.yaml")) + sorted(ROOT.glob("institutions/*/manifest.yaml")):
        _validate_record(errors, validators["manifest"], read_data(path), str(path.relative_to(ROOT)))
    record_groups = [
        ("rule", "jurisdictions/*/rules.yaml", "rules"),
        ("source", "jurisdictions/*/sources.yaml", "sources"),
        ("source", "institutions/*/sources.yaml", "sources"),
        ("preparation", "base/preparation-checklist.yaml", "preparation_items"),
        ("preparation", "jurisdictions/*/preparation.yaml", "preparation_items"),
        ("support", "jurisdictions/*/support.yaml", "support_items"),
        ("support", "institutions/*/support.yaml", "support_items"),
        ("question", "base/questions.yaml", "questions"),
        ("procedure", "institutions/*/procedures.yaml", "procedures"),
    ]
    for kind, pattern, key in record_groups:
        for path in sorted(ROOT.glob(pattern)):
            for index, record in enumerate(_records(errors, path, key)):
                _validate_record(errors, validators[kind], record, f"{path.relative_to(ROOT)}[{index}]")
    for path in sorted((ROOT / "samples").glob("*.json")):
        sample = read_data(path)
        _validate_record(errors, validators["sample"], sample, str(path.relative_to(ROOT)))
        for index, record in enumerate(sample.get("preparation_actions", [])):
            _validate_record(errors, validators["preparation"], record, f"{path.relative_to(ROOT)}:preparation_actions[{index}]")
        for index, record in enumerate(sample.get("support_items", [])):
            _validate_record(errors, validators["support"], record, f"{path.relative_to(ROOT)}:support_items[{index}]")

    try:
        loader = PackLoader(ROOT)
    except (KeyError, ValueError) as exc:
        errors.append(str(exc))
        loader = None
    if loader is None:
        return _finish(errors)

    if len(loader.sources) < 12:
        errors.append(f"expected >=12 sources, found {len(loader.sources)}")
    tiers = {"HK-SAR": 0, "CN-MAINLAND": 0}
    for source in loader.sources.values():
        if source["status"] == "active" and source["authority_tier"] <= 2:
            tiers[source["jurisdiction"]] = tiers.get(source["jurisdiction"], 0) + 1
    if tiers.get("HK-SAR", 0) < 5:
        errors.append("expected >=5 active HK sources")
    if tiers.get("CN-MAINLAND", 0) < 4:
        errors.append("expected >=4 active Mainland sources")

    for manifest in loader.manifests:
        if manifest["status"] == "active" and "required" in manifest["reviewer"].lower():
            errors.append(f"active pack {manifest['pack_id']} has no named reviewer")
    for rule in loader.rules:
        rule_id = rule["rule_id"]
        if rule["status"] == "verified" and "required" in rule["reviewer"].lower():
            errors.append(f"verified rule {rule_id} has no named reviewer")
        if rule["uncertainty_policy"] != "needs_confirmation":
            errors.append(f"rule {rule_id} has unsafe uncertainty policy")
        for source_id in rule["source_ids"]:
            if source_id not in loader.sources:
                errors.append(f"rule {rule_id} references unknown source {source_id}")
        for action_id in rule["preparation_action_ids"]:
            if action_id not in loader.preparation:
                errors.append(f"rule {rule_id} references unknown preparation {action_id}")
        for support_id in rule["support_item_ids"]:
            if support_id not in loader.support:
                errors.append(f"rule {rule_id} references unknown support {support_id}")
            elif rule.get("institution") is None and loader.origins["support"][support_id].startswith("institutions/"):
                errors.append(f"generic rule {rule_id} references institution support {support_id}")
    for item in loader.preparation.values():
        item_id = item["preparation_action_id"]
        if item["mandatory"] and not item["mandatory_source_id"]:
            errors.append(f"mandatory preparation {item_id} lacks source")
        referenced = item["source_ids"] + ([item["mandatory_source_id"]] if item["mandatory_source_id"] else [])
        for source_id in referenced:
            if source_id not in loader.sources:
                errors.append(f"preparation {item_id} references unknown source {source_id}")
    for item in loader.support.values():
        for source_id in item["source_ids"]:
            if source_id not in loader.sources:
                errors.append(f"support {item['support_item_id']} references unknown source {source_id}")
    for path in sorted(ROOT.glob("institutions/*/procedures.yaml")):
        for procedure in _records(errors, path, "procedures"):
            for source_id in procedure["source_ids"]:
                if source_id not in loader.sources:
                    errors.append(f"procedure {procedure['procedure_id']} references unknown source {source_id}")

    evaluator = ContextPackEvaluator(loader)
    for sample_name, fixture_name in SAMPLE_FIXTURES.items():
        sample = read_data(ROOT / "samples" / sample_name)
        expected = evaluator.evaluate(read_data(ROOT / "fixtures" / fixture_name), as_of="2026-08-01")
        if sample != expected:
            errors.append(f"sample {sample_name} does not match evaluator output; run generate_samples.py")
        linked_ids = [link["source_id"] for link in sample.get("source_links", [])]
        if linked_ids != sample.get("source_ids", []):
            errors.append(f"sample {sample_name} source_links do not exactly match source_ids")

    if errors:
        return _finish(errors)
    print(
        f"Pack validation passed: {len(loader.sources)} sources, {len(loader.rules)} rules, "
        f"{len(loader.preparation)} preparation items, {len(loader.support)} support items, "
        f"{len(loader.questions)} questions"
    )
    return 0


def _finish(errors: list[str]) -> int:
    print("Pack validation failed:")
    print("\n".join(f"- {error}" for error in errors))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
