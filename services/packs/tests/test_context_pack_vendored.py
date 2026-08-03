import copy
import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

# vendored（2026-08-02）：pack 根在 campuspath_packs/international_student/，
# 与上游仓库的 tests 相对位置不同，仅此一行调整。
ROOT = Path(__file__).resolve().parents[1] / "campuspath_packs" / "international_student"
sys.path.insert(0, str(ROOT))
from campuspath_context import ContextPackEvaluator, PackLoader  # noqa: E402


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text())


def promote_for_test(loader):
    for manifest in loader.manifests:
        manifest["status"] = "active"
        manifest["review_at"] = "2099-01-01"
    for rule in loader.rules:
        rule["status"] = "verified"
        rule["review_at"] = "2099-01-01"
    for source in loader.sources.values():
        source["status"] = "active"
        source["next_review_at"] = "2099-01-01"


class ContextPackAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = PackLoader()
        cls.evaluator = ContextPackEvaluator(cls.loader)

    def test_base_layer_is_loaded(self):
        self.assertIn("international-student-base", [item["pack_id"] for item in self.loader.manifests])
        self.assertIn("PREP-BASE-JOB-001", self.loader.preparation)
        self.assertEqual(len(self.loader.questions), 13)

    def test_manifest_schema_rejects_wrong_type_and_missing_field(self):
        schema = json.loads((ROOT / "schemas" / "context-pack.schema.json").read_text())
        invalid = copy.deepcopy(self.loader.manifest("international-student-base"))
        invalid["consent_required"] = "true"
        del invalid["reviewer"]
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(invalid))
        self.assertGreaterEqual(len(errors), 2)

    def test_duplicate_identifiers_are_rejected(self):
        duplicate = copy.deepcopy(self.loader.support["HKUST-SUPPORT-CAREER-001"])
        with self.assertRaisesRegex(ValueError, "duplicate support ID"):
            self.loader._register(
                self.loader.support,
                duplicate,
                "support_item_id",
                "support",
                ROOT / "institutions" / "hkust" / "support.yaml",
            )

    def test_no_consent_does_not_load(self):
        profile = fixture("hk-undergraduate-internship.json")
        profile["consent_context_pack"] = False
        result = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertFalse(result["pack_status"]["consented"])
        self.assertEqual(result["applicable_rule_ids"], [])

    def test_unsupported_jurisdiction_preserves_consent(self):
        profile = fixture("hk-undergraduate-internship.json")
        profile["intended_work_jurisdiction"] = "US"
        result = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertFalse(result["pack_status"]["applicable"])
        self.assertTrue(result["pack_status"]["consented"])
        self.assertEqual(result["applicable_pack_ids"], [])

    def test_programme_level_and_goal_type_are_enforced(self):
        profile = fixture("hk-undergraduate-internship.json")
        profile.update(programme_level="secondary_school", goal_type="entrepreneurship")
        result = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertFalse(result["pack_status"]["applicable"])
        self.assertEqual(result["applicable_rule_ids"], [])

    def test_missing_required_information(self):
        result = self.evaluator.evaluate(fixture("hk-undergraduate-internship.json"), as_of="2026-08-01")
        self.assertEqual(result["eligibility_state"], "needs_confirmation")
        self.assertTrue(result["missing_information"])

    def test_expired_permission_needs_confirmation_and_preparation(self):
        result = self.evaluator.evaluate(fixture("missing-and-expired-context.json"), as_of="2026-08-01")
        self.assertEqual(result["eligibility_state"], "needs_confirmation")
        self.assertIn("valid_permission_for_intended_start_date", result["missing_information"])
        self.assertIn("PREP-BASE-DOC-001", [item["preparation_action_id"] for item in result["preparation_actions"]])

    def test_permission_expiring_before_activity_needs_confirmation(self):
        profile = fixture("mainland-graduate-employment.json")
        profile["permission_expiry_date"] = "2026-08-15"
        result = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertIn("valid_permission_for_intended_start_date", result["missing_information"])

    def test_expired_rule_needs_confirmation(self):
        loader = PackLoader()
        promote_for_test(loader)
        target = next(rule for rule in loader.rules if rule["rule_id"] == "CN-GRAD-EMPLOYMENT-001")
        target["effective_until"] = "2026-07-31"
        result = ContextPackEvaluator(loader).evaluate(fixture("mainland-graduate-employment.json"), as_of="2026-08-01")
        self.assertEqual(result["eligibility_state"], "needs_confirmation")
        self.assertTrue(result["review_required"])

    def test_review_date_is_due_on_the_date(self):
        loader = PackLoader()
        promote_for_test(loader)
        loader.manifest("international-student-cn-mainland")["review_at"] = "2026-08-01"
        result = ContextPackEvaluator(loader).evaluate(fixture("mainland-graduate-employment.json"), as_of="2026-08-01")
        self.assertFalse(result["pack_status"]["current"])
        self.assertTrue(result["review_required"])

    def test_conflicting_rules_never_choose_permissive(self):
        loader = PackLoader()
        promote_for_test(loader)
        first = next(rule for rule in loader.rules if rule["rule_id"] == "CN-GRAD-EMPLOYMENT-001")
        second = copy.deepcopy(first)
        second["rule_id"] = "TEST-CONFLICT"
        second["decision_effect"] = "eligible_now"
        loader.rules.append(second)
        result = ContextPackEvaluator(loader).evaluate(fixture("mainland-graduate-employment.json"), as_of="2026-08-01")
        self.assertEqual(result["eligibility_state"], "needs_confirmation")
        self.assertTrue(result["review_required"])

    def test_unreviewed_policy_never_returns_future_eligible(self):
        result = self.evaluator.evaluate(fixture("mainland-graduate-employment.json"), as_of="2026-08-01")
        self.assertEqual(result["eligibility_state"], "needs_confirmation")
        self.assertIn("CN-GRAD-EMPLOYMENT-001", result["applicable_rule_ids"])
        self.assertFalse(result["pack_status"]["current"])

    def test_hkust_overlay_only_for_hkust(self):
        result = self.evaluator.evaluate(fixture("hk-recent-graduate.json"), as_of="2026-08-01")
        self.assertIn("international-student-hkust", result["applicable_pack_ids"])
        self.assertTrue(result["support_items"])
        other = fixture("hk-recent-graduate.json")
        other["institution"] = "Other University"
        other_result = self.evaluator.evaluate(other, as_of="2026-08-01")
        self.assertNotIn("international-student-hkust", other_result["applicable_pack_ids"])
        self.assertEqual(other_result["support_items"], [])
        self.assertFalse(any(source_id.startswith("HKUST-") for source_id in other_result["source_ids"]))

    def test_generic_rules_do_not_reference_hkust_support(self):
        self.assertTrue(all(not rule["support_item_ids"] for rule in self.loader.rules if rule.get("institution") is None))
        self.assertEqual(self.loader.origins["support"]["HKUST-SUPPORT-CAREER-001"], "institutions/hkust/support.yaml")

    def test_language_is_not_universally_mandatory(self):
        language_items = [item for item in self.loader.preparation.values() if item["category"] == "language"]
        self.assertTrue(language_items)
        self.assertTrue(all(not item["mandatory"] for item in language_items))

    def test_opportunity_fields_are_not_global_policy(self):
        result = self.evaluator.evaluate(
            fixture("mainland-graduate-employment.json"), {"employer_sponsorship": False}, as_of="2026-08-01"
        )
        self.assertIn("CN-GRAD-EMPLOYMENT-001", result["applicable_rule_ids"])

    def test_provenance_completeness(self):
        for rule in self.loader.rules:
            self.assertTrue(rule["version"] and rule["review_at"] and rule["source_ids"])

    def test_fixtures_have_no_raw_sensitive_data(self):
        for path in (ROOT / "fixtures").glob("*.json"):
            text = path.read_text().lower()
            self.assertNotIn("passport", text)
            self.assertNotIn("visa_number", text)
            self.assertNotIn("student_id", text)

    def test_frontend_envelope_completeness(self):
        result = self.evaluator.evaluate(fixture("mainland-graduate-employment.json"), as_of="2026-08-01")
        for key in ("pack_status", "jurisdiction", "pack_version", "last_verified_at", "eligibility_state", "headline_key", "review_required"):
            self.assertIn(key, result)

    def test_pathway_impact_traceability(self):
        result = self.evaluator.evaluate(fixture("hk-recent-graduate.json"), as_of="2026-08-01")
        for impact in result["pathway_impacts"]:
            self.assertTrue(impact["rule_ids"] and impact["pathway_segment_id"])

    def test_source_links_exactly_cover_source_ids(self):
        result = self.evaluator.evaluate(fixture("hk-recent-graduate.json"), as_of="2026-08-01")
        self.assertEqual(result["source_ids"], [link["source_id"] for link in result["source_links"]])

    def test_validation_id_is_nonempty_and_stable(self):
        profile = fixture("hk-recent-graduate.json")
        first = self.evaluator.evaluate(profile, as_of="2026-08-01")
        second = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertRegex(first["validation_id"], r"^VAL-[A-F0-9]{20}$")
        self.assertEqual(first["validation_id"], second["validation_id"])

    def test_confirmation_safe_headline(self):
        result = self.evaluator.evaluate(fixture("hk-undergraduate-internship.json"), as_of="2026-08-01")
        self.assertEqual(result["eligibility_state"], "needs_confirmation")
        self.assertNotIn("legal", result["headline"].lower())
        self.assertNotIn("authorized", result["headline"].lower())

    def test_city_claims_are_not_nationally_eligible(self):
        profile = fixture("mainland-graduate-employment.json")
        profile["local_overlay_confirmed"] = False
        result = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertIn("CN-CITY-SCOPE-001", result["applicable_rule_ids"])
        self.assertEqual(result["eligibility_state"], "needs_confirmation")

    def test_installed_applicable_consented_are_distinct(self):
        profile = fixture("hk-undergraduate-internship.json")
        profile["consent_context_pack"] = False
        result = self.evaluator.evaluate(profile, as_of="2026-08-01")
        self.assertTrue(result["pack_status"]["installed"])
        self.assertTrue(result["pack_status"]["applicable"])
        self.assertFalse(result["pack_status"]["consented"])


if __name__ == "__main__":
    unittest.main()
