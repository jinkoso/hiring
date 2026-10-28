from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
VALIDATOR_PATH = PROJECT_ROOT / "tools" / "validate_fixtures.py"
SPEC = importlib.util.spec_from_file_location("validate_fixtures", VALIDATOR_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class FixtureValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.data_dir = Path(self.temporary_directory.name) / "data"
        shutil.copytree(DATA_DIR, self.data_dir)

    def read_json(self, relative_path: str) -> dict:
        return json.loads((self.data_dir / relative_path).read_text(encoding="utf-8"))

    def write_json(self, relative_path: str, value: dict) -> None:
        (self.data_dir / relative_path).write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def assert_has_error(self, errors: list[str], text: str) -> None:
        self.assertTrue(
            any(text in error for error in errors),
            f"expected an error containing {text!r}; got:\n" + "\n".join(errors),
        )

    def test_complete_fixture_tree_is_valid_and_meets_public_minimums(self) -> None:
        self.assertEqual([], VALIDATOR.validate_fixture_tree(DATA_DIR))
        catalog = json.loads((DATA_DIR / "catalog.json").read_text(encoding="utf-8"))
        scenario_paths = sorted((DATA_DIR / "scenarios").glob("*.json"))
        scenarios = [json.loads(path.read_text(encoding="utf-8")) for path in scenario_paths]
        routes = {(flight["origin"], flight["destination"]) for flight in catalog["flights"]}
        dates = {flight["departure_at"][:10] for flight in catalog["flights"]}
        self.assertGreaterEqual(len(catalog["flights"]), 10)
        self.assertGreaterEqual(len(routes), 3)
        self.assertGreaterEqual(len(dates), 2)
        self.assertGreaterEqual(len(scenarios), 12)
        self.assertGreaterEqual(sum(len(scenario["steps"]) for scenario in scenarios), 45)

    def test_rejects_boolean_money_and_naive_timestamp(self) -> None:
        seed = self.read_json("seed_quotes.json")
        seed["events"][0]["total_price_minor"] = True
        seed["events"][0]["observed_at"] = "2027-01-15T09:40:00"
        self.write_json("seed_quotes.json", seed)
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "positive integer (bool is invalid)")
        self.assert_has_error(errors, "datetime must include a timezone offset")

    def test_rejects_unknown_flight_reference(self) -> None:
        seed = self.read_json("seed_quotes.json")
        seed["events"][0]["flight_id"] = "flight_999"
        self.write_json("seed_quotes.json", seed)
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "unknown flight 'flight_999'")

    def test_rejects_unqualified_timezone_display_label(self) -> None:
        catalog = self.read_json("catalog.json")
        catalog["airports"][0]["timezone"] = "Europe"
        self.write_json("catalog.json", catalog)
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "qualified Region/Location-style display label")

    def test_validator_import_does_not_require_zoneinfo(self) -> None:
        original_import = __import__

        def import_without_zoneinfo(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "zoneinfo" or name.startswith("zoneinfo."):
                raise ImportError("zoneinfo intentionally unavailable")
            return original_import(name, globals, locals, fromlist, level)

        spec = importlib.util.spec_from_file_location(
            "validate_fixtures_without_zoneinfo", VALIDATOR_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch("builtins.__import__", side_effect=import_without_zoneinfo):
            spec.loader.exec_module(module)
        self.assertEqual([], module.validate_fixture_tree(DATA_DIR))

    def test_validation_does_not_require_timezone_database(self) -> None:
        fake_zoneinfo = types.ModuleType("zoneinfo")

        class MissingTimezoneDatabase(Exception):
            pass

        def fail_timezone_lookup(_name):
            raise MissingTimezoneDatabase("tzdb intentionally unavailable")

        fake_zoneinfo.ZoneInfo = fail_timezone_lookup
        fake_zoneinfo.ZoneInfoNotFoundError = MissingTimezoneDatabase
        spec = importlib.util.spec_from_file_location(
            "validate_fixtures_without_tzdb", VALIDATOR_PATH
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        with mock.patch.dict(sys.modules, {"zoneinfo": fake_zoneinfo}):
            spec.loader.exec_module(module)
        self.assertEqual([], module.validate_fixture_tree(DATA_DIR))

    def test_rejects_quote_identity_change_against_seed(self) -> None:
        scenario_path = "scenarios/threshold-crossing.json"
        scenario = self.read_json(scenario_path)
        scenario["steps"][0]["event"]["supplier"] = "provider_b"
        self.write_json(scenario_path, scenario)
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "product identity changed for 'offer_001_a_eur_standard_0'")

    def test_rejects_unannotated_changed_event_replay(self) -> None:
        scenario_path = "scenarios/conflicting-event-replay.json"
        scenario = self.read_json(scenario_path)
        del scenario["steps"][1]["expected_replay_status"]
        self.write_json(scenario_path, scenario)
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "changed payload for reused event_id must expect status 409")

    def test_rejects_409_without_prior_event(self) -> None:
        scenario_path = "scenarios/threshold-crossing.json"
        scenario = self.read_json(scenario_path)
        scenario["steps"][0]["expected_replay_status"] = 409
        self.write_json(scenario_path, scenario)
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "status 409 requires a prior event with the same event_id")

    def test_rejects_duplicate_json_keys(self) -> None:
        catalog_path = self.data_dir / "catalog.json"
        text = catalog_path.read_text(encoding="utf-8")
        catalog_path.write_text(text.replace('"schema_version": 1,', '"schema_version": 1,\n  "schema_version": 1,', 1), encoding="utf-8")
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "duplicate JSON key 'schema_version'")

    def test_scenarios_have_independent_event_namespaces(self) -> None:
        scenario_path = "scenarios/threshold-crossing.json"
        scenario = self.read_json(scenario_path)
        # This event id exists in another scenario with a different payload. Each
        # scenario starts from seed, so it must not be treated as a conflict here.
        scenario["steps"][0]["event"]["event_id"] = "up_evt_001"
        self.write_json(scenario_path, scenario)
        self.assertEqual([], VALIDATOR.validate_fixture_tree(self.data_dir))

    def test_rejects_product_identity_change_between_independent_scenarios(self) -> None:
        baggage_path = "scenarios/baggage-product-isolation.json"
        baggage = self.read_json(baggage_path)
        baggage["steps"][0]["event"]["quote_id"] = "scenario_shared_product"
        self.write_json(baggage_path, baggage)

        currency_path = "scenarios/currency-isolation.json"
        currency = self.read_json(currency_path)
        currency["steps"][1]["event"]["quote_id"] = "scenario_shared_product"
        self.write_json(currency_path, currency)

        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(
            errors,
            "global product identity changed for 'scenario_shared_product'",
        )

    def test_missing_scenario_reports_coverage_loss(self) -> None:
        (self.data_dir / "scenarios" / "sold-out-quotes.json").unlink()
        errors = VALIDATOR.validate_fixture_tree(self.data_dir)
        self.assert_has_error(errors, "missing required coverage scenarios: sold-out-quotes")
        self.assert_has_error(errors, "missing coverage for sold-out quote")


if __name__ == "__main__":
    unittest.main()
