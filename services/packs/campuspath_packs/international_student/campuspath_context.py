"""Deterministic Context Pack loader and evaluator.

The evaluator supports a small, explicit condition vocabulary. It does not
infer policy, call an LLM, or select a permissive result when records conflict.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
EFFECTS = {"eligible_now", "future_eligible", "needs_confirmation", "ineligible_current_cycle"}


def read_data(path: Path) -> dict[str, Any]:
    # Package files intentionally use the JSON-compatible subset of YAML.
    return json.loads(path.read_text(encoding="utf-8"))


def _iso_today(value: str | date | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(value[:10])


def _date_in_window(record: dict[str, Any], today: date) -> bool:
    effective_from = record.get("effective_from")
    effective_until = record.get("effective_until")
    return (not effective_from or _iso_today(effective_from) <= today) and (
        not effective_until or today <= _iso_today(effective_until)
    )


def _review_is_due(record: dict[str, Any], today: date, field: str = "review_at") -> bool:
    value = record.get(field)
    return bool(value and today >= _iso_today(value))


class PackLoader:
    """Load every layer and reject ambiguous identifiers immediately."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.manifests: list[dict[str, Any]] = []
        self.sources: dict[str, dict[str, Any]] = {}
        self.rules: list[dict[str, Any]] = []
        self.preparation: dict[str, dict[str, Any]] = {}
        self.support: dict[str, dict[str, Any]] = {}
        self.questions: list[dict[str, Any]] = []
        self.origins: dict[str, dict[str, str]] = {
            "manifest": {}, "source": {}, "rule": {}, "preparation": {}, "support": {}
        }
        self._load()

    def _register(
        self,
        collection: dict[str, dict[str, Any]],
        record: dict[str, Any],
        id_field: str,
        kind: str,
        path: Path,
    ) -> None:
        record_id = record[id_field]
        relative = str(path.relative_to(self.root))
        if record_id in self.origins[kind]:
            previous = self.origins[kind][record_id]
            raise ValueError(f"duplicate {kind} ID {record_id}: {previous} and {relative}")
        collection[record_id] = record
        self.origins[kind][record_id] = relative

    def _add_manifest(self, path: Path) -> None:
        manifest = read_data(path)
        pack_id = manifest["pack_id"]
        if pack_id in self.origins["manifest"]:
            raise ValueError(f"duplicate manifest ID {pack_id}")
        self.manifests.append(manifest)
        self.origins["manifest"][pack_id] = str(path.relative_to(self.root))

    def _load_records(self, path: Path, key: str, collection: dict[str, dict[str, Any]], id_field: str, kind: str) -> None:
        for record in read_data(path).get(key, []):
            self._register(collection, record, id_field, kind, path)

    def _load(self) -> None:
        base = self.root / "base"
        self._add_manifest(base / "manifest.yaml")
        self._load_records(base / "preparation-checklist.yaml", "preparation_items", self.preparation, "preparation_action_id", "preparation")
        self.questions = read_data(base / "questions.yaml").get("questions", [])

        for manifest_path in sorted(self.root.glob("jurisdictions/*/manifest.yaml")):
            self._add_manifest(manifest_path)
            directory = manifest_path.parent
            self._load_records(directory / "sources.yaml", "sources", self.sources, "source_id", "source")
            self._load_records(directory / "rules.yaml", "rules", {}, "rule_id", "rule")
            self.rules.extend(read_data(directory / "rules.yaml").get("rules", []))
            self._load_records(directory / "preparation.yaml", "preparation_items", self.preparation, "preparation_action_id", "preparation")
            self._load_records(directory / "support.yaml", "support_items", self.support, "support_item_id", "support")

        institution = self.root / "institutions/hkust"
        self._add_manifest(institution / "manifest.yaml")
        self._load_records(institution / "sources.yaml", "sources", self.sources, "source_id", "source")
        self._load_records(institution / "support.yaml", "support_items", self.support, "support_item_id", "support")

    def manifest(self, pack_id: str) -> dict[str, Any]:
        return next(item for item in self.manifests if item["pack_id"] == pack_id)


def _condition_matches(condition: dict[str, Any], profile: dict[str, Any], opportunity: dict[str, Any]) -> bool:
    field = condition["field"]
    value = profile.get(field, opportunity.get(field))
    operator = condition["operator"]
    expected = condition.get("value")
    if operator == "exists":
        return (value is not None) == bool(expected)
    if value is None:
        return False
    if operator == "equals":
        return value == expected
    if operator == "not_equals":
        return value != expected
    if operator == "in":
        return value in expected
    raise ValueError(f"Unsupported condition operator: {operator}")


def _matches(rule: dict[str, Any], profile: dict[str, Any], opportunity: dict[str, Any]) -> bool:
    return all(_condition_matches(condition, profile, opportunity) for condition in rule["conditions"])


def _headline(state: str) -> tuple[str, str]:
    return {
        "eligible_now": ("eligible_now", "Eligible now based on the current Pack context"),
        "future_eligible": ("future_eligible", "Potentially eligible after the required transition"),
        "ineligible_current_cycle": ("ineligible_current_cycle", "Not eligible in the current cycle"),
        "needs_confirmation": ("additional_confirmation_needed", "Additional confirmation is needed"),
    }[state]


def _validation_id(profile: dict[str, Any], opportunity: dict[str, Any], today: date, pack_ids: list[str], rule_ids: list[str]) -> str:
    payload = {
        "as_of": today.isoformat(),
        "opportunity": opportunity,
        "pack_ids": pack_ids,
        "profile": profile,
        "rule_ids": rule_ids,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return f"VAL-{digest[:20].upper()}"


class ContextPackEvaluator:
    def __init__(self, loader: PackLoader | None = None):
        self.loader = loader or PackLoader()

    @staticmethod
    def _manifest_applies(manifest: dict[str, Any], profile: dict[str, Any]) -> bool:
        applicability = manifest["applicability"]
        return all(
            (
                profile.get("student_cohort") == applicability["student_cohort"],
                profile.get("programme_level") in applicability["programme_levels"],
                profile.get("study_mode") in applicability["study_modes"],
                profile.get("goal_type") in applicability["goal_types"],
            )
        )

    @staticmethod
    def _manifest_current(manifest: dict[str, Any], today: date) -> bool:
        return manifest["status"] == "active" and _date_in_window(manifest, today) and not _review_is_due(manifest, today)

    def evaluate(self, profile: dict[str, Any], opportunity: dict[str, Any] | None = None, *, as_of: str | date | None = None) -> dict[str, Any]:
        opportunity = opportunity or {}
        today = _iso_today(as_of)
        consented = profile.get("consent_context_pack") is True
        jurisdiction = profile.get("intended_work_jurisdiction")
        if jurisdiction not in {"HK-SAR", "CN-MAINLAND"}:
            return self._empty(profile, opportunity, None, False, False, consented, "Unsupported or missing work jurisdiction", today)

        pack_id = "international-student-hk" if jurisdiction == "HK-SAR" else "international-student-cn-mainland"
        pack = self.loader.manifest(pack_id)
        base_pack = self.loader.manifest("international-student-base")
        installed = True
        applicable = self._manifest_applies(base_pack, profile) and self._manifest_applies(pack, profile)
        institutional = profile.get("institution") == "HKUST" and jurisdiction == "HK-SAR"
        overlay = self.loader.manifest("international-student-hkust") if institutional else None
        if overlay is not None:
            applicable = applicable and self._manifest_applies(overlay, profile)
        selected_packs = [base_pack, pack] + ([overlay] if overlay else [])
        pack_ids = [item["pack_id"] for item in selected_packs]
        packs_current = all(self._manifest_current(item, today) for item in selected_packs)
        if not applicable or not consented:
            return self._empty(profile, opportunity, pack, installed, applicable, consented, "Context Pack is not available for evaluation", today)

        matching_rules = [
            rule for rule in self.loader.rules
            if rule["jurisdiction"] == jurisdiction
            and rule.get("institution") in (None, profile.get("institution"))
            and _matches(rule, profile, opportunity)
        ]
        rule_ids = [rule["rule_id"] for rule in matching_rules]
        rules_current = all(
            rule["status"] == "verified" and _date_in_window(rule, today) and not _review_is_due(rule, today)
            for rule in matching_rules
        )
        missing = [field for item in selected_packs for field in item["required_student_fields"] if profile.get(field) in (None, "")]
        for rule in matching_rules:
            for evidence in rule["required_evidence"]:
                if profile.get(evidence) in (None, "") and opportunity.get(evidence) in (None, ""):
                    missing.append(evidence)
        if not matching_rules:
            missing.append("applicable_policy_rule")

        action_ids = {action_id for rule in matching_rules for action_id in rule["preparation_action_ids"]}
        permission_needs_confirmation = False
        try:
            permission_expiry_value = profile.get("permission_expiry_date")
            intended_start_value = profile.get("intended_start_date")
            if not permission_expiry_value or not intended_start_value:
                raise ValueError("permission and start dates are required")
            permission_expiry = _iso_today(permission_expiry_value)
            intended_start = _iso_today(intended_start_value)
            permission_needs_confirmation = permission_expiry < today or permission_expiry <= intended_start
        except (TypeError, ValueError):
            permission_needs_confirmation = True
        if permission_needs_confirmation:
            missing.append("valid_permission_for_intended_start_date")
            action_ids.add("PREP-BASE-DOC-001")

        effects = {rule["decision_effect"] for rule in matching_rules}
        conflict = len(effects) > 1
        support_ids: set[str] = set()
        for rule in matching_rules:
            support_ids.update(rule["support_item_ids"])
        if institutional:
            support_ids.update({"HKUST-SUPPORT-SCHOLARSHIP-001", "HKUST-SUPPORT-FA-001", "HKUST-SUPPORT-CAREER-001"})

        source_ids = {source_id for rule in matching_rules for source_id in rule["source_ids"]}
        for action_id in action_ids:
            source_ids.update(self.loader.preparation[action_id].get("source_ids", []))
        for support_id in support_ids:
            source_ids.update(self.loader.support[support_id].get("source_ids", []))
        sources_current = all(
            source["status"] == "active"
            and _date_in_window(source, today)
            and not _review_is_due(source, today, "next_review_at")
            for source_id in source_ids
            for source in [self.loader.sources[source_id]]
        )

        missing = sorted(set(missing))
        review_required = not packs_current or not rules_current or not sources_current or conflict
        state = (
            "needs_confirmation"
            if missing or review_required or not matching_rules
            else next(iter(effects))
        )
        source_links = [
            {
                "source_id": source_id,
                "title": self.loader.sources[source_id]["title"],
                "url": self.loader.sources[source_id]["url"],
                "last_checked_at": self.loader.sources[source_id]["last_checked_at"],
            }
            for source_id in sorted(source_ids)
        ]
        key, headline = _headline(state)
        impacts = [
            {
                "impact_id": f"IMPACT-{index:03d}",
                "rule_ids": [rule["rule_id"]],
                "pathway_segment_id": opportunity.get("pathway_segment_id", "current-goal"),
                "impact_type": "add_preparation_action" if rule["preparation_action_ids"] else "add_confirmation",
                "summary": rule["summary"],
            }
            for index, rule in enumerate(matching_rules, 1)
        ]
        validation_id = _validation_id(profile, opportunity, today, pack_ids, rule_ids)
        return {
            "pack_status": {"installed": installed, "applicable": applicable, "consented": consented, "current": packs_current},
            "eligibility_state": state,
            "headline_key": key,
            "headline": headline,
            "jurisdiction": jurisdiction,
            "pack_version": pack["version"],
            "last_verified_at": max([item["effective_from"] for item in selected_packs] + [rule["last_verified_at"] for rule in matching_rules]),
            "applicable_pack_ids": pack_ids,
            "applicable_rule_ids": rule_ids,
            "constraints": sorted({constraint for rule in matching_rules for constraint in rule["constraints"]}),
            "missing_information": missing,
            "required_evidence": sorted({evidence for rule in matching_rules for evidence in rule["required_evidence"]}),
            "preparation_actions": [self.loader.preparation[action_id] for action_id in sorted(action_ids)],
            "support_items": [self.loader.support[support_id] for support_id in sorted(support_ids)],
            "source_ids": sorted(source_ids),
            "source_links": source_links,
            "pathway_impacts": impacts,
            "validation_id": validation_id,
            "review_required": review_required,
            "evaluated_at": f"{today.isoformat()}T00:00:00Z",
        }

    def _empty(
        self,
        profile: dict[str, Any],
        opportunity: dict[str, Any],
        pack: dict[str, Any] | None,
        installed: bool,
        applicable: bool,
        consented: bool,
        reason: str,
        today: date,
    ) -> dict[str, Any]:
        jurisdiction = profile.get("intended_work_jurisdiction")
        key, headline = _headline("needs_confirmation")
        pack_ids: list[str] = []
        return {
            "pack_status": {"installed": installed, "applicable": applicable, "consented": consented, "current": False},
            "eligibility_state": "needs_confirmation",
            "headline_key": key,
            "headline": headline,
            "jurisdiction": jurisdiction,
            "pack_version": pack["version"] if pack else None,
            "last_verified_at": None,
            "applicable_pack_ids": pack_ids,
            "applicable_rule_ids": [],
            "constraints": [],
            "missing_information": [reason],
            "required_evidence": [],
            "preparation_actions": [],
            "support_items": [],
            "source_ids": [],
            "source_links": [],
            "pathway_impacts": [],
            "validation_id": _validation_id(profile, opportunity, today, pack_ids, []),
            "review_required": False,
            "evaluated_at": f"{today.isoformat()}T00:00:00Z",
        }
