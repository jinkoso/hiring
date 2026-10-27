from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import evaluate  # noqa: E402
import validate_fixtures  # noqa: E402


class FixtureValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = validate_fixtures.validate_cases_file()

    def test_declared_tiers_and_supporting_scenario_counts(self) -> None:
        self.assertEqual(
            self.document["counts"], {"core": 28, "extended": 12, "total": 40}
        )
        self.assertEqual(validate_fixtures.validate_supporting_files(), (10, 5))

    def test_relative_date_metadata_covers_calendar_boundaries(self) -> None:
        relative = {
            case["id"]: case
            for case in self.document["cases"]
            if "date_offset_days" in case
        }
        self.assertGreaterEqual(len(relative), 6)
        self.assertEqual(relative["c026"]["expected"]["departure_date"], "2026-05-02")
        self.assertEqual(relative["c027"]["expected"]["departure_date"], "2027-01-01")
        self.assertEqual(relative["c028"]["expected"]["departure_date"], "2028-02-29")

    def test_null_required_field_cannot_be_omitted_from_clarification_metadata(self) -> None:
        case = copy.deepcopy(next(case for case in self.document["cases"] if case["id"] == "c012"))
        case["clarification_fields"].remove("origin")
        with self.assertRaisesRegex(validate_fixtures.FixtureError, "null origin"):
            validate_fixtures.validate_case(case, 0)


class EvaluatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = validate_fixtures.validate_cases_file()["cases"]
        cls.by_id = {case["id"]: case for case in cls.cases}

    def valid_records(self) -> list[dict[str, object]]:
        records = []
        for case in self.cases:
            result = copy.deepcopy(case["expected"])
            result["request_id"] = f"generated-{case['id']}"
            records.append({"case_id": case["id"], "result": result})
        return records

    def test_public_expected_results_are_accepted_for_all_tiers(self) -> None:
        report = evaluate.evaluate_records(self.cases, self.valid_records(), "all")
        self.assertEqual(report["global_errors"], [])
        self.assertEqual(len(report["results"]), 40)
        self.assertTrue(all(item["passed"] for item in report["results"]))

    def test_location_comparison_only_trims_and_casefolds(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c032"
        )
        record["result"]["origin"] = "  NYC "
        record["result"]["destination"] = "la"
        report = evaluate.evaluate_records([self.by_id["c032"]], [record], "all")
        self.assertTrue(report["results"][0]["passed"])

        record["result"]["origin"] = "New York City"
        report = evaluate.evaluate_records([self.by_id["c032"]], [record], "all")
        self.assertFalse(report["results"][0]["passed"])

    def test_missing_result_key_cannot_silently_equal_null(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c008"
        )
        del record["result"]["origin"]
        report = evaluate.evaluate_records([self.by_id["c008"]], [record], "all")
        self.assertIn("missing result keys", report["results"][0]["errors"][0])

    def test_boolean_is_not_accepted_as_passenger_integer(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c003"
        )
        record["result"]["passengers"] = True
        report = evaluate.evaluate_records([self.by_id["c003"]], [record], "all")
        self.assertFalse(report["results"][0]["passed"])
        self.assertTrue(
            any("positive integer" in error for error in report["results"][0]["errors"])
        )

    def test_short_question_is_accepted_and_blank_question_is_rejected(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c008"
        )
        record["result"]["clarification_questions"] = ["From where?"]
        report = evaluate.evaluate_records([self.by_id["c008"]], [record], "all")
        self.assertTrue(report["results"][0]["passed"])

        record["result"]["clarification_questions"] = [" "]
        report = evaluate.evaluate_records([self.by_id["c008"]], [record], "all")
        self.assertFalse(report["results"][0]["passed"])
        self.assertTrue(
            any("non-empty" in error for error in report["results"][0]["errors"])
        )

    def test_non_string_status_is_reported_without_crashing(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c001"
        )
        record["result"]["status"] = []
        report = evaluate.evaluate_records([self.by_id["c001"]], [record], "all")
        self.assertFalse(report["results"][0]["passed"])
        self.assertTrue(any("status" in error for error in report["results"][0]["errors"]))

    def test_positive_integer_request_id_is_accepted_but_boolean_is_not(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c001"
        )
        record["result"]["request_id"] = 17
        report = evaluate.evaluate_records([self.by_id["c001"]], [record], "all")
        self.assertTrue(report["results"][0]["passed"])

        record["result"]["request_id"] = True
        report = evaluate.evaluate_records([self.by_id["c001"]], [record], "all")
        self.assertFalse(report["results"][0]["passed"])

    def test_huge_integer_does_not_overflow_numeric_validation(self) -> None:
        huge = 10**1000
        self.assertTrue(validate_fixtures.is_number(huge))
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c001"
        )
        record["result"]["budget_per_person"]["amount"] = huge
        report = evaluate.evaluate_records([self.by_id["c001"]], [record], "all")
        self.assertFalse(report["results"][0]["passed"])

    def test_each_wrong_business_value_is_rejected(self) -> None:
        mutations = {
            "status": lambda result: result.update(
                status="needs_clarification",
                clarification_questions=["Should anything else be clarified?"],
            ),
            "departure_date": lambda result: result.update(departure_date="2027-05-11"),
            "passengers": lambda result: result.update(passengers=3),
            "budget_per_person.amount": lambda result: result["budget_per_person"].update(
                amount=1201
            ),
            "budget_per_person.currency": lambda result: result["budget_per_person"].update(
                currency="EUR"
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(field=label):
                record = next(
                    item
                    for item in self.valid_records()
                    if item["case_id"] == "c001"
                )
                mutate(record["result"])
                report = evaluate.evaluate_records(
                    [self.by_id["c001"]], [record], "all"
                )
                self.assertFalse(report["results"][0]["passed"])
                self.assertTrue(
                    any(label in error for error in report["results"][0]["errors"]),
                    report["results"][0]["errors"],
                )

    def test_unexpected_output_field_is_rejected(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c001"
        )
        record["result"]["confidence"] = 0.99
        report = evaluate.evaluate_records([self.by_id["c001"]], [record], "all")
        self.assertTrue(
            any(
                "unknown result keys" in error
                for error in report["results"][0]["errors"]
            )
        )

    def test_missing_duplicate_and_unknown_case_ids_are_input_errors(self) -> None:
        records = self.valid_records()
        core_records = [item for item in records if self.by_id[item["case_id"]]["tier"] == "core"]
        core_records.pop()
        core_records.append(copy.deepcopy(core_records[0]))
        core_records.append(
            {"case_id": "not-a-case", "result": copy.deepcopy(core_records[0]["result"])}
        )
        report = evaluate.evaluate_records(self.cases, core_records, "core")
        joined = "\n".join(report["global_errors"])
        self.assertIn("missing prediction", joined)
        self.assertIn("duplicate case_id", joined)
        self.assertIn("unknown case_id", joined)

    def test_non_finite_json_number_is_rejected_while_reading_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.jsonl"
            path.write_text(
                '{"case_id":"c001","result":{"budget_per_person":{"amount":NaN}}}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(evaluate.PredictionError, "non-finite"):
                evaluate.read_prediction_lines(path)

    def test_numeric_budget_equality_accepts_integral_float(self) -> None:
        record = next(
            item for item in self.valid_records() if item["case_id"] == "c001"
        )
        record["result"]["budget_per_person"]["amount"] = 1200.0
        report = evaluate.evaluate_records([self.by_id["c001"]], [record], "all")
        self.assertTrue(report["results"][0]["passed"])


if __name__ == "__main__":
    unittest.main()
