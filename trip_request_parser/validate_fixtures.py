#!/usr/bin/env python3
"""Validate the public assignment fixtures using only the Python standard library."""

from __future__ import annotations

import argparse
import json
import math
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
TIERS = {"core", "extended"}
STATUSES = {"ready", "needs_clarification"}
CLARIFICATION_FIELDS = {
    "origin",
    "destination",
    "departure_date",
    "passengers",
    "budget_per_person.amount",
    "budget_per_person.currency",
    "budget_basis",
}
EXPECTED_KEYS = {
    "status",
    "origin",
    "destination",
    "departure_date",
    "passengers",
    "budget_per_person",
    "clarification_questions",
}


class FixtureError(ValueError):
    """Raised when public fixture data violates its declared contract."""


def _reject_constant(value: str) -> None:
    raise FixtureError(f"non-finite JSON number {value!r} is not allowed")


def load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, parse_constant=_reject_constant)
    except (OSError, json.JSONDecodeError) as exc:
        raise FixtureError(f"could not read {path}: {exc}") from exc


def require_exact_keys(value: dict[str, Any], required: set[str], context: str) -> None:
    missing = required - value.keys()
    extra = value.keys() - required
    if missing or extra:
        raise FixtureError(
            f"{context} keys differ: missing={sorted(missing)}, extra={sorted(extra)}"
        )


def parse_iso_date(value: Any, context: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise FixtureError(f"{context} must be an ISO YYYY-MM-DD string")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise FixtureError(f"{context} is not a valid calendar date: {value!r}") from exc


def is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def validate_questions(value: Any, status: str, context: str) -> None:
    if not isinstance(value, list):
        raise FixtureError(f"{context} must be an array")
    if status == "ready" and value:
        raise FixtureError(f"{context} must be empty for ready results")
    if status == "needs_clarification" and not value:
        raise FixtureError(f"{context} must be non-empty for clarification results")
    for index, question in enumerate(value):
        q_context = f"{context}[{index}]"
        if (
            not isinstance(question, str)
            or not question
            or question != question.strip()
        ):
            raise FixtureError(f"{q_context} must be a non-empty trimmed string")


def validate_expected(expected: Any, reference: date, context: str) -> None:
    if not isinstance(expected, dict):
        raise FixtureError(f"{context} must be an object")
    require_exact_keys(expected, EXPECTED_KEYS, context)

    status = expected["status"]
    if not isinstance(status, str) or status not in STATUSES:
        raise FixtureError(f"{context}.status must be one of {sorted(STATUSES)}")

    for field in ("origin", "destination"):
        value = expected[field]
        if value is not None and (
            not isinstance(value, str) or not value or value != value.strip()
        ):
            raise FixtureError(f"{context}.{field} must be null or a non-empty trimmed string")

    departure = expected["departure_date"]
    if departure is not None:
        departure_value = parse_iso_date(departure, f"{context}.departure_date")
        if departure_value < reference:
            raise FixtureError(f"{context}.departure_date must not precede reference_date")

    passengers = expected["passengers"]
    if passengers is not None and (
        not isinstance(passengers, int) or isinstance(passengers, bool) or passengers <= 0
    ):
        raise FixtureError(f"{context}.passengers must be null or a positive integer")

    budget = expected["budget_per_person"]
    if not isinstance(budget, dict):
        raise FixtureError(f"{context}.budget_per_person must be an object")
    require_exact_keys(budget, {"amount", "currency"}, f"{context}.budget_per_person")
    amount = budget["amount"]
    if amount is not None and (not is_number(amount) or amount <= 0):
        raise FixtureError(f"{context}.budget_per_person.amount must be null or positive")
    currency = budget["currency"]
    if currency is not None and (
        not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)
    ):
        raise FixtureError(
            f"{context}.budget_per_person.currency must be null or an uppercase ISO code"
        )

    validate_questions(expected["clarification_questions"], status, f"{context}.clarification_questions")


def validate_case(case: Any, index: int) -> None:
    context = f"cases[{index}]"
    if not isinstance(case, dict):
        raise FixtureError(f"{context} must be an object")
    required = {"id", "tier", "category", "input", "expected", "clarification_fields", "reason"}
    allowed = required | {"date_offset_days"}
    missing = required - case.keys()
    extra = case.keys() - allowed
    if missing or extra:
        raise FixtureError(
            f"{context} keys differ: missing={sorted(missing)}, extra={sorted(extra)}"
        )

    for field in ("id", "category", "reason"):
        if not isinstance(case[field], str) or not case[field].strip():
            raise FixtureError(f"{context}.{field} must be a non-empty string")
    if not isinstance(case["tier"], str) or case["tier"] not in TIERS:
        raise FixtureError(f"{context}.tier must be core or extended")

    input_value = case["input"]
    if not isinstance(input_value, dict):
        raise FixtureError(f"{context}.input must be an object")
    require_exact_keys(input_value, {"text", "reference_date"}, f"{context}.input")
    if not isinstance(input_value["text"], str) or not input_value["text"].strip():
        raise FixtureError(f"{context}.input.text must be a non-blank string")
    reference = parse_iso_date(input_value["reference_date"], f"{context}.input.reference_date")

    validate_expected(case["expected"], reference, f"{context}.expected")

    clarification_fields = case["clarification_fields"]
    if not isinstance(clarification_fields, list) or any(
        not isinstance(field, str) or field not in CLARIFICATION_FIELDS
        for field in clarification_fields
    ):
        raise FixtureError(f"{context}.clarification_fields contains an unsupported field")
    if len(clarification_fields) != len(set(clarification_fields)):
        raise FixtureError(f"{context}.clarification_fields contains duplicates")

    expected = case["expected"]
    status = expected["status"]
    if status == "ready":
        if clarification_fields:
            raise FixtureError(f"{context}: ready cases cannot declare clarification fields")
        for field in ("origin", "destination", "departure_date", "passengers"):
            if expected[field] is None:
                raise FixtureError(f"{context}: ready case is missing {field}")
        budget = expected["budget_per_person"]
        if (budget["amount"] is None) != (budget["currency"] is None):
            raise FixtureError(f"{context}: ready case has a partial budget")
    else:
        if not clarification_fields:
            raise FixtureError(f"{context}: clarification status requires clarification_fields")
        null_field_map = {
            "origin": "origin",
            "destination": "destination",
            "departure_date": "departure_date",
            "passengers": "passengers",
        }
        for marker, field in null_field_map.items():
            if marker in clarification_fields and expected[field] is not None:
                raise FixtureError(f"{context}: {marker} clarification must have a null value")
            if expected[field] is None and marker not in clarification_fields:
                raise FixtureError(f"{context}: null {field} must be declared for clarification")
        budget = expected["budget_per_person"]
        if "budget_per_person.amount" in clarification_fields and budget["amount"] is not None:
            raise FixtureError(f"{context}: invalid budget amount must be null")
        if "budget_per_person.currency" in clarification_fields and budget["currency"] is not None:
            raise FixtureError(f"{context}: unknown budget currency must be null")
        if "budget_basis" in clarification_fields and budget["amount"] is not None:
            raise FixtureError(f"{context}: ambiguous budget basis must have null amount")

    if "date_offset_days" in case:
        offset = case["date_offset_days"]
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise FixtureError(f"{context}.date_offset_days must be a non-negative integer")
        calculated = (reference + timedelta(days=offset)).isoformat()
        if expected["departure_date"] != calculated:
            raise FixtureError(
                f"{context}: expected relative date {calculated}, got {expected['departure_date']!r}"
            )


def validate_cases_file(path: Path = DATA_DIR / "cases.json") -> dict[str, Any]:
    document = load_json(path)
    if not isinstance(document, dict):
        raise FixtureError("cases document must be an object")
    require_exact_keys(document, {"format_version", "description", "counts", "cases"}, "cases document")
    if document["format_version"] != 1:
        raise FixtureError("cases format_version must be 1")
    if not isinstance(document["description"], str) or not document["description"].strip():
        raise FixtureError("cases description must be non-empty")
    if not isinstance(document["cases"], list):
        raise FixtureError("cases must be an array")

    ids: set[str] = set()
    tier_counts = {tier: 0 for tier in TIERS}
    for index, case in enumerate(document["cases"]):
        validate_case(case, index)
        if case["id"] in ids:
            raise FixtureError(f"duplicate case id {case['id']!r}")
        ids.add(case["id"])
        tier_counts[case["tier"]] += 1

    counts = document["counts"]
    if not isinstance(counts, dict):
        raise FixtureError("counts must be an object")
    require_exact_keys(counts, {"core", "extended", "total"}, "counts")
    actual = {**tier_counts, "total": len(document["cases"])}
    if counts != actual:
        raise FixtureError(f"declared counts {counts!r} do not match actual counts {actual!r}")
    if actual != {"core": 28, "extended": 12, "total": 40}:
        raise FixtureError(f"assignment requires 28 core and 12 extended cases, got {actual!r}")
    return document


def validate_supporting_files() -> tuple[int, int]:
    failure_document = load_json(DATA_DIR / "failure_cases.json")
    require_exact_keys(
        failure_document, {"format_version", "description", "cases"}, "failure document"
    )
    failures = failure_document["cases"]
    if failure_document["format_version"] != 1 or not isinstance(failures, list):
        raise FixtureError("failure_cases.json has an unsupported format")
    if not 8 <= len(failures) <= 12:
        raise FixtureError("failure_cases.json must contain 8 to 12 cases")

    failure_required = {"id", "type", "input", "expected_behavior", "reason"}
    failure_allowed = failure_required | {
        "mock_provider_error",
        "mock_provider_response",
        "mock_sqlite_error",
    }
    failure_types = {"invalid_input", "provider_error", "invalid_model_output", "persistence_error"}
    for index, entry in enumerate(failures):
        context = f"failure cases[{index}]"
        if not isinstance(entry, dict):
            raise FixtureError(f"{context} must be an object")
        missing = failure_required - entry.keys()
        extra = entry.keys() - failure_allowed
        if missing or extra:
            raise FixtureError(
                f"{context} keys differ: missing={sorted(missing)}, extra={sorted(extra)}"
            )
        if not isinstance(entry["type"], str) or entry["type"] not in failure_types:
            raise FixtureError(f"{context}.type is unsupported")
        if not isinstance(entry["input"], dict):
            raise FixtureError(f"{context}.input must be an object")
        require_exact_keys(entry["input"], {"text", "reference_date"}, f"{context}.input")
        if not isinstance(entry["expected_behavior"], dict) or not entry["expected_behavior"]:
            raise FixtureError(f"{context}.expected_behavior must be a non-empty object")
        if entry["expected_behavior"].get("outcome") != "technical_error":
            raise FixtureError(f"{context} must describe a technical_error outcome")
        if not isinstance(entry["reason"], str) or not entry["reason"].strip():
            raise FixtureError(f"{context}.reason must be non-empty")

    persistence_document = load_json(DATA_DIR / "persistence_scenarios.json")
    require_exact_keys(
        persistence_document,
        {"format_version", "description", "scenarios"},
        "persistence document",
    )
    scenarios = persistence_document["scenarios"]
    if persistence_document["format_version"] != 1 or not isinstance(scenarios, list):
        raise FixtureError("persistence_scenarios.json has an unsupported format")
    if not 4 <= len(scenarios) <= 6:
        raise FixtureError("persistence_scenarios.json must contain 4 to 6 scenarios")

    for index, entry in enumerate(scenarios):
        context = f"persistence scenarios[{index}]"
        if not isinstance(entry, dict):
            raise FixtureError(f"{context} must be an object")
        require_exact_keys(entry, {"id", "name", "steps", "checks"}, context)
        if not isinstance(entry["name"], str) or not entry["name"].strip():
            raise FixtureError(f"{context}.name must be non-empty")
        for field in ("steps", "checks"):
            values = entry[field]
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise FixtureError(f"{context}.{field} must be a non-empty string array")

    for label, entries in (("failure", failures), ("persistence", scenarios)):
        seen: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict) or not isinstance(entry.get("id"), str):
                raise FixtureError(f"{label} entry {index} must have a string id")
            if entry["id"] in seen:
                raise FixtureError(f"duplicate {label} id {entry['id']!r}")
            seen.add(entry["id"])
    return len(failures), len(scenarios)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        cases = validate_cases_file()
        failures, persistence = validate_supporting_files()
    except FixtureError as exc:
        print(f"Fixture validation failed: {exc}")
        return 1
    counts = cases["counts"]
    print(
        "Fixture validation passed: "
        f"{counts['core']} core, {counts['extended']} extended, "
        f"{failures} failure cases, {persistence} persistence scenarios."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
