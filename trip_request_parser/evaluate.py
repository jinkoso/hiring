#!/usr/bin/env python3
"""Compare candidate-produced JSONL predictions with the public fixtures."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from validate_fixtures import (
    DATA_DIR,
    EXPECTED_KEYS,
    FixtureError,
    is_number,
    parse_iso_date,
    validate_cases_file,
    validate_questions,
)


RESULT_ALLOWED_KEYS = EXPECTED_KEYS | {"request_id"}


class PredictionError(ValueError):
    """Raised for malformed prediction input."""


def _reject_constant(value: str) -> None:
    raise PredictionError(f"non-finite JSON number {value!r} is not allowed")


def read_prediction_lines(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        handle = path.open(encoding="utf-8")
    except OSError as exc:
        raise PredictionError(f"could not open predictions: {exc}") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line, parse_constant=_reject_constant)
            except json.JSONDecodeError as exc:
                raise PredictionError(f"line {line_number} is malformed JSON: {exc}") from exc
            if not isinstance(value, dict):
                raise PredictionError(f"line {line_number} must contain a JSON object")
            missing = {"case_id", "result"} - value.keys()
            extra = value.keys() - {"case_id", "result"}
            if missing or extra:
                raise PredictionError(
                    f"line {line_number} keys differ: missing={sorted(missing)}, extra={sorted(extra)}"
                )
            if not isinstance(value["case_id"], str) or not value["case_id"]:
                raise PredictionError(f"line {line_number}.case_id must be a non-empty string")
            records.append(value)
    return records


def validate_result(result: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(result, dict):
        return ["result must be an object"]
    missing = EXPECTED_KEYS - result.keys()
    extra = result.keys() - RESULT_ALLOWED_KEYS
    if missing:
        errors.append(f"missing result keys: {sorted(missing)}")
    if extra:
        errors.append(f"unknown result keys: {sorted(extra)}")
    if missing:
        return errors

    request_id = result.get("request_id")
    if "request_id" in result:
        valid_string_id = isinstance(request_id, str) and bool(request_id.strip())
        valid_integer_id = (
            isinstance(request_id, int) and not isinstance(request_id, bool) and request_id > 0
        )
        if not valid_string_id and not valid_integer_id:
            errors.append("request_id must be a non-empty string or positive integer when present")

    status = result["status"]
    if not isinstance(status, str) or status not in {"ready", "needs_clarification"}:
        errors.append("status must be ready or needs_clarification")

    for field in ("origin", "destination"):
        value = result[field]
        if value is not None and (
            not isinstance(value, str) or not value.strip()
        ):
            errors.append(f"{field} must be null or a non-empty string")

    departure = result["departure_date"]
    if departure is not None:
        try:
            parse_iso_date(departure, "departure_date")
        except FixtureError as exc:
            errors.append(str(exc))

    passengers = result["passengers"]
    if passengers is not None and (
        not isinstance(passengers, int) or isinstance(passengers, bool) or passengers <= 0
    ):
        errors.append("passengers must be null or a positive integer")

    budget = result["budget_per_person"]
    if not isinstance(budget, dict):
        errors.append("budget_per_person must be an object")
    else:
        missing_budget = {"amount", "currency"} - budget.keys()
        extra_budget = budget.keys() - {"amount", "currency"}
        if missing_budget or extra_budget:
            errors.append(
                "budget_per_person keys differ: "
                f"missing={sorted(missing_budget)}, extra={sorted(extra_budget)}"
            )
        if not missing_budget:
            amount = budget["amount"]
            if amount is not None and (not is_number(amount) or amount <= 0):
                errors.append("budget_per_person.amount must be null or a positive finite number")
            currency = budget["currency"]
            if currency is not None and (
                not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
            ):
                errors.append("budget_per_person.currency must be null or an uppercase ISO code")

    if isinstance(status, str) and status in {"ready", "needs_clarification"}:
        try:
            validate_questions(result["clarification_questions"], status, "clarification_questions")
        except FixtureError as exc:
            errors.append(str(exc))
    elif not isinstance(result["clarification_questions"], list):
        errors.append("clarification_questions must be an array")
    return errors


def _location_equal(actual: Any, expected: Any) -> bool:
    if actual is None or expected is None:
        return actual is expected
    if not isinstance(actual, str) or not isinstance(expected, str):
        return False
    return actual.strip().casefold() == expected.strip().casefold()


def compare_result(result: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    mismatches: list[str] = []
    for field in ("origin", "destination"):
        if not _location_equal(result[field], expected[field]):
            mismatches.append(
                f"{field}: expected {expected[field]!r}, got {result[field]!r}"
            )
    for field in ("status", "departure_date", "passengers"):
        if result[field] != expected[field]:
            mismatches.append(
                f"{field}: expected {expected[field]!r}, got {result[field]!r}"
            )

    actual_budget = result["budget_per_person"]
    expected_budget = expected["budget_per_person"]
    if actual_budget["amount"] != expected_budget["amount"]:
        mismatches.append(
            "budget_per_person.amount: "
            f"expected {expected_budget['amount']!r}, got {actual_budget['amount']!r}"
        )
    if actual_budget["currency"] != expected_budget["currency"]:
        mismatches.append(
            "budget_per_person.currency: "
            f"expected {expected_budget['currency']!r}, got {actual_budget['currency']!r}"
        )
    return mismatches


def evaluate_records(
    cases: Iterable[dict[str, Any]], records: list[dict[str, Any]], tier: str
) -> dict[str, Any]:
    all_cases = {case["id"]: case for case in cases}
    selected = {
        case_id: case
        for case_id, case in all_cases.items()
        if tier == "all" or case["tier"] == tier
    }
    counts = Counter(record["case_id"] for record in records)
    global_errors: list[str] = []
    for case_id, count in sorted(counts.items()):
        if case_id not in all_cases:
            global_errors.append(f"unknown case_id {case_id!r}")
        if count > 1:
            global_errors.append(f"duplicate case_id {case_id!r}")
    for case_id in sorted(selected.keys() - counts.keys()):
        global_errors.append(f"missing prediction for {case_id!r}")

    by_id = {
        record["case_id"]: record["result"]
        for record in records
        if counts[record["case_id"]] == 1 and record["case_id"] in selected
    }
    results: list[dict[str, Any]] = []
    for case_id, case in selected.items():
        if case_id not in by_id:
            continue
        result = by_id[case_id]
        errors = validate_result(result)
        if not errors:
            errors = compare_result(result, case["expected"])
        results.append(
            {
                "case_id": case_id,
                "tier": case["tier"],
                "passed": not errors,
                "errors": errors,
            }
        )
    return {"selected": selected, "results": results, "global_errors": global_errors}


def print_report(report: dict[str, Any]) -> None:
    for error in report["global_errors"]:
        print(f"ERROR: {error}")
    for result in report["results"]:
        if result["passed"]:
            print(f"PASS {result['case_id']}")
        else:
            print(f"FAIL {result['case_id']}")
            for error in result["errors"]:
                print(f"  - {error}")

    selected = report["selected"]
    for tier in ("core", "extended"):
        total = sum(case["tier"] == tier for case in selected.values())
        if not total:
            continue
        passed = sum(
            result["passed"] for result in report["results"] if result["tier"] == tier
        )
        print(f"Summary {tier}: {passed}/{total} passed")
    if report["global_errors"]:
        print(f"Input errors: {len(report['global_errors'])}")
    print("Clarification wording and usefulness still require manual review.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("predictions", type=Path, help="JSONL file of {case_id, result} records")
    parser.add_argument(
        "--tier", choices=("core", "extended", "all"), default="core"
    )
    args = parser.parse_args(argv)
    try:
        fixtures = validate_cases_file(DATA_DIR / "cases.json")
        records = read_prediction_lines(args.predictions)
    except (FixtureError, PredictionError) as exc:
        print(f"Evaluation input error: {exc}", file=sys.stderr)
        return 2
    report = evaluate_records(fixtures["cases"], records, args.tier)
    print_report(report)
    failed = any(not result["passed"] for result in report["results"])
    return 1 if report["global_errors"] or failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
