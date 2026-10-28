#!/usr/bin/env python3
"""Validate the public flight-search fixture tree using only the standard library."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
SCHEMA_VERSION = 1
CURRENCIES = {"EUR", "GBP", "USD"}
SUPPLIERS = {"provider_a", "provider_b", "provider_c"}
REQUIRED_SCENARIOS = {
    "baggage-product-isolation",
    "bounce-around-threshold",
    "conflicting-event-replay",
    "currency-isolation",
    "expiry-boundary",
    "future-observation",
    "identical-event-replay",
    "other-route-and-date",
    "out-of-order-observation",
    "sold-out-quotes",
    "steady-and-upward",
    "threshold-crossing",
    "threshold-equality",
    "unverified-quotes",
}
AIRPORT_FIELDS = {"iata", "name", "timezone"}
FLIGHT_FIELDS = {
    "flight_id", "origin", "destination", "departure_at", "arrival_at",
    "carrier", "flight_number", "cabin", "adults",
}
QUOTE_FIELDS = {
    "event_id", "quote_id", "flight_id", "supplier", "total_price_minor",
    "currency", "available", "verified", "observed_at", "expires_at",
    "fare_family", "checked_bag_kg",
}
IDENTITY_FIELDS = (
    "flight_id", "supplier", "currency", "fare_family", "checked_bag_kg",
)
TIMEZONE_LABEL_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*")


class DuplicateKeyError(ValueError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _load_json(path: Path, errors: list[str]) -> Any | None:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle, object_pairs_hook=_reject_duplicate_keys)
    except FileNotFoundError:
        errors.append(f"{path}: file is missing")
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as exc:
        errors.append(f"{path}: invalid JSON: {exc}")
    return None


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_timezone_display_label(value: Any) -> bool:
    """Check Region/Location syntax without consulting an optional system tzdb."""
    if not isinstance(value, str):
        return False
    parts = value.split("/")
    if len(parts) < 2 or re.fullmatch(r"[A-Za-z][A-Za-z0-9._+-]*", parts[0]) is None:
        return False
    return all(
        part not in {".", ".."} and TIMEZONE_LABEL_SEGMENT.fullmatch(part) is not None
        for part in parts[1:]
    )


def _parse_datetime(value: Any, location: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{location}: must be a timezone-aware ISO-8601 string")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{location}: invalid ISO-8601 datetime {value!r}")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        errors.append(f"{location}: datetime must include a timezone offset")
        return None
    return parsed


def _expect_object(value: Any, location: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{location}: must be an object")
        return False
    return True


def _check_fields(
    value: dict[str, Any], required: set[str], optional: set[str], location: str,
    errors: list[str],
) -> None:
    missing = sorted(required - value.keys())
    extra = sorted(value.keys() - required - optional)
    if missing:
        errors.append(f"{location}: missing fields: {', '.join(missing)}")
    if extra:
        errors.append(f"{location}: unexpected fields: {', '.join(extra)}")


def _validate_catalog(
    catalog: Any, location: str, errors: list[str]
) -> tuple[dict[str, dict[str, Any]], set[tuple[str, str]], set[str]]:
    flights: dict[str, dict[str, Any]] = {}
    routes: set[tuple[str, str]] = set()
    departure_dates: set[str] = set()
    if not _expect_object(catalog, location, errors):
        return flights, routes, departure_dates
    _check_fields(catalog, {"schema_version", "demo_as_of", "airports", "flights"}, set(), location, errors)
    if catalog.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{location}.schema_version: must be {SCHEMA_VERSION}")
    _parse_datetime(catalog.get("demo_as_of"), f"{location}.demo_as_of", errors)

    airports = catalog.get("airports")
    airport_codes: set[str] = set()
    if not isinstance(airports, list) or not airports:
        errors.append(f"{location}.airports: must be a non-empty array")
    else:
        for index, airport in enumerate(airports):
            item_location = f"{location}.airports[{index}]"
            if not _expect_object(airport, item_location, errors):
                continue
            _check_fields(airport, AIRPORT_FIELDS, set(), item_location, errors)
            iata = airport.get("iata")
            if not isinstance(iata, str) or re.fullmatch(r"[A-Z]{3}", iata) is None:
                errors.append(f"{item_location}.iata: must be three uppercase letters")
            elif iata in airport_codes:
                errors.append(f"{item_location}.iata: duplicate airport {iata!r}")
            else:
                airport_codes.add(iata)
            if not isinstance(airport.get("name"), str) or not airport.get("name", "").strip():
                errors.append(f"{item_location}.name: must be a non-empty string")
            timezone = airport.get("timezone")
            if not _is_timezone_display_label(timezone):
                errors.append(
                    f"{item_location}.timezone: must be a qualified "
                    "Region/Location-style display label"
                )

    flight_items = catalog.get("flights")
    if not isinstance(flight_items, list) or not flight_items:
        errors.append(f"{location}.flights: must be a non-empty array")
        return flights, routes, departure_dates
    for index, flight in enumerate(flight_items):
        item_location = f"{location}.flights[{index}]"
        if not _expect_object(flight, item_location, errors):
            continue
        _check_fields(flight, FLIGHT_FIELDS, set(), item_location, errors)
        flight_id = flight.get("flight_id")
        if not isinstance(flight_id, str) or re.fullmatch(r"flight_[0-9]{3}", flight_id) is None:
            errors.append(f"{item_location}.flight_id: must match flight_NNN")
        elif flight_id in flights:
            errors.append(f"{item_location}.flight_id: duplicate id {flight_id!r}")
        else:
            flights[flight_id] = flight
        origin = flight.get("origin")
        destination = flight.get("destination")
        if origin not in airport_codes:
            errors.append(f"{item_location}.origin: unknown airport {origin!r}")
        if destination not in airport_codes:
            errors.append(f"{item_location}.destination: unknown airport {destination!r}")
        if origin == destination:
            errors.append(f"{item_location}: origin and destination must differ")
        if isinstance(origin, str) and isinstance(destination, str):
            routes.add((origin, destination))
        departure = _parse_datetime(flight.get("departure_at"), f"{item_location}.departure_at", errors)
        arrival = _parse_datetime(flight.get("arrival_at"), f"{item_location}.arrival_at", errors)
        if departure is not None:
            departure_dates.add(departure.date().isoformat())
        if departure is not None and arrival is not None and arrival <= departure:
            errors.append(f"{item_location}: arrival_at must be after departure_at")
        carrier = flight.get("carrier")
        if not isinstance(carrier, str) or re.fullmatch(r"[A-Z0-9]{2}", carrier) is None:
            errors.append(f"{item_location}.carrier: must be a two-character synthetic code")
        flight_number = flight.get("flight_number")
        if not isinstance(flight_number, str) or not isinstance(carrier, str) or re.fullmatch(re.escape(carrier) + r"[0-9]{2,4}", flight_number) is None:
            errors.append(f"{item_location}.flight_number: must contain the carrier code and 2-4 digits")
        if flight.get("cabin") != "economy":
            errors.append(f"{item_location}.cabin: must be 'economy'")
        if flight.get("adults") != 1 or isinstance(flight.get("adults"), bool):
            errors.append(f"{item_location}.adults: must be integer 1")
    if len(flights) < 10:
        errors.append(f"{location}.flights: need at least 10 unique flights, found {len(flights)}")
    if len(routes) < 3:
        errors.append(f"{location}.flights: need at least 3 routes, found {len(routes)}")
    if len(departure_dates) < 2:
        errors.append(f"{location}.flights: need at least 2 departure dates, found {len(departure_dates)}")
    return flights, routes, departure_dates


def _validate_quote(
    quote: Any, location: str, flights: dict[str, dict[str, Any]], errors: list[str]
) -> tuple[datetime | None, datetime | None]:
    if not _expect_object(quote, location, errors):
        return None, None
    _check_fields(quote, QUOTE_FIELDS, set(), location, errors)
    for field in ("event_id", "quote_id", "fare_family"):
        value = quote.get(field)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{location}.{field}: must be a non-empty string")
    if quote.get("flight_id") not in flights:
        errors.append(f"{location}.flight_id: unknown flight {quote.get('flight_id')!r}")
    if quote.get("supplier") not in SUPPLIERS:
        errors.append(f"{location}.supplier: must be one of {sorted(SUPPLIERS)}")
    if quote.get("currency") not in CURRENCIES:
        errors.append(f"{location}.currency: must be one of {sorted(CURRENCIES)}")
    price = quote.get("total_price_minor")
    if not _is_int(price) or price <= 0:
        errors.append(f"{location}.total_price_minor: must be a positive integer (bool is invalid)")
    bag = quote.get("checked_bag_kg")
    if not _is_int(bag) or bag < 0:
        errors.append(f"{location}.checked_bag_kg: must be a nonnegative integer (bool is invalid)")
    for field in ("available", "verified"):
        if not isinstance(quote.get(field), bool):
            errors.append(f"{location}.{field}: must be boolean")
    observed = _parse_datetime(quote.get("observed_at"), f"{location}.observed_at", errors)
    expires = _parse_datetime(quote.get("expires_at"), f"{location}.expires_at", errors)
    if observed is not None and expires is not None and expires <= observed:
        errors.append(f"{location}: expires_at must be after observed_at")
    return observed, expires


def _identity(quote: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(quote.get(field) for field in IDENTITY_FIELDS)


def _validate_seed(
    seed: Any, location: str, flights: dict[str, dict[str, Any]], errors: list[str]
) -> tuple[dict[str, dict[str, Any]], dict[str, tuple[Any, ...]]]:
    events_by_id: dict[str, dict[str, Any]] = {}
    identities: dict[str, tuple[Any, ...]] = {}
    if not _expect_object(seed, location, errors):
        return events_by_id, identities
    _check_fields(seed, {"schema_version", "events"}, set(), location, errors)
    if seed.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"{location}.schema_version: must be {SCHEMA_VERSION}")
    events = seed.get("events")
    if not isinstance(events, list) or not events:
        errors.append(f"{location}.events: must be a non-empty array")
        return events_by_id, identities
    for index, event in enumerate(events):
        event_location = f"{location}.events[{index}]"
        _validate_quote(event, event_location, flights, errors)
        if not isinstance(event, dict):
            continue
        event_id = event.get("event_id")
        quote_id = event.get("quote_id")
        if isinstance(event_id, str):
            if event_id in events_by_id:
                errors.append(f"{event_location}.event_id: duplicate seed event {event_id!r}")
            else:
                events_by_id[event_id] = event
        if isinstance(quote_id, str):
            identity = _identity(event)
            if quote_id in identities and identities[quote_id] != identity:
                errors.append(f"{event_location}.quote_id: product identity changed for {quote_id!r}")
            else:
                identities[quote_id] = identity
    return events_by_id, identities


def _validate_scenarios(
    scenario_paths: list[Path], flights: dict[str, dict[str, Any]],
    seed_events: dict[str, dict[str, Any]], seed_identities: dict[str, tuple[Any, ...]],
    errors: list[str],
) -> tuple[set[str], int, dict[str, bool]]:
    scenario_ids: set[str] = set()
    step_count = 0
    coverage = {
        "identical replay": False,
        "annotated conflict": False,
        "future observation": False,
        "expired at evaluation": False,
        "unverified quote": False,
        "sold-out quote": False,
        "out-of-order observation": False,
        "same-price refresh": False,
        "price bounce": False,
        "positive baggage allowance": False,
    }
    scenario_currencies: set[str] = set()
    scenario_routes: set[tuple[str, str]] = set()
    scenario_dates: set[str] = set()
    # Product identity is a fixture-wide declaration even though event history,
    # prices, availability, and observation times reset for every scenario.
    global_identities = dict(seed_identities)

    for path in scenario_paths:
        scenario = _load_json(path, errors)
        location = str(path)
        if not _expect_object(scenario, location, errors):
            continue
        _check_fields(scenario, {"schema_version", "scenario_id", "description", "steps"}, set(), location, errors)
        if scenario.get("schema_version") != SCHEMA_VERSION:
            errors.append(f"{location}.schema_version: must be {SCHEMA_VERSION}")
        scenario_id = scenario.get("scenario_id")
        if not isinstance(scenario_id, str) or re.fullmatch(r"[a-z][a-z0-9-]*", scenario_id) is None:
            errors.append(f"{location}.scenario_id: must be a lowercase hyphenated id")
        else:
            if path.stem != scenario_id:
                errors.append(f"{location}.scenario_id: must match filename {path.stem!r}")
            if scenario_id in scenario_ids:
                errors.append(f"{location}.scenario_id: duplicate id {scenario_id!r}")
            scenario_ids.add(scenario_id)
        description = scenario.get("description")
        if not isinstance(description, str) or len(description.strip()) < 20:
            errors.append(f"{location}.description: must be a meaningful string of at least 20 characters")
        steps = scenario.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"{location}.steps: must be a non-empty array")
            continue

        # Each scenario is replayed against a fresh database initialized from seed.
        events_by_id = dict(seed_events)
        identities = dict(seed_identities)
        labels: set[str] = set()
        last_observed_by_quote: dict[str, datetime] = {}
        prices_by_quote: dict[str, list[int]] = defaultdict(list)
        step_count += len(steps)
        for index, step in enumerate(steps):
            step_location = f"{location}.steps[{index}]"
            if not _expect_object(step, step_location, errors):
                continue
            _check_fields(step, {"label", "as_of", "event"}, {"expected_replay_status"}, step_location, errors)
            label = step.get("label")
            if not isinstance(label, str) or re.fullmatch(r"[a-z][a-z0-9_]*", label) is None:
                errors.append(f"{step_location}.label: must be a lowercase snake_case label")
            elif label in labels:
                errors.append(f"{step_location}.label: duplicate label {label!r} in scenario")
            else:
                labels.add(label)
            as_of = _parse_datetime(step.get("as_of"), f"{step_location}.as_of", errors)
            status = step.get("expected_replay_status", 200)
            if not _is_int(status) or status not in {200, 409}:
                errors.append(f"{step_location}.expected_replay_status: must be integer 200 or 409")
                status = None
            event = step.get("event")
            observed, expires = _validate_quote(event, f"{step_location}.event", flights, errors)
            if not isinstance(event, dict):
                continue
            event_id = event.get("event_id")
            quote_id = event.get("quote_id")
            if isinstance(quote_id, str):
                identity = _identity(event)
                if quote_id in identities and identities[quote_id] != identity:
                    errors.append(f"{step_location}.event.quote_id: product identity changed for {quote_id!r}")
                else:
                    identities[quote_id] = identity
                if quote_id in global_identities and global_identities[quote_id] != identity:
                    errors.append(
                        f"{step_location}.event.quote_id: global product identity changed for {quote_id!r}"
                    )
                else:
                    global_identities[quote_id] = identity
            existing = events_by_id.get(event_id) if isinstance(event_id, str) else None
            if existing is None:
                if status == 409:
                    errors.append(f"{step_location}: status 409 requires a prior event with the same event_id")
                elif isinstance(event_id, str):
                    events_by_id[event_id] = event
            elif existing == event:
                coverage["identical replay"] = True
                if status != 200:
                    errors.append(f"{step_location}: identical event replay must expect status 200")
            else:
                coverage["annotated conflict"] = True
                if status != 409:
                    errors.append(f"{step_location}: changed payload for reused event_id must expect status 409")

            if observed is not None and as_of is not None and observed > as_of:
                coverage["future observation"] = True
            if expires is not None and as_of is not None and expires <= as_of:
                coverage["expired at evaluation"] = True
            if event.get("verified") is False:
                coverage["unverified quote"] = True
            if event.get("available") is False:
                coverage["sold-out quote"] = True
            if isinstance(event.get("checked_bag_kg"), int) and not isinstance(event.get("checked_bag_kg"), bool) and event["checked_bag_kg"] > 0:
                coverage["positive baggage allowance"] = True
            currency = event.get("currency")
            if isinstance(currency, str):
                scenario_currencies.add(currency)
            flight = flights.get(event.get("flight_id"))
            if flight is not None:
                scenario_routes.add((flight["origin"], flight["destination"]))
                departure = datetime.fromisoformat(flight["departure_at"].replace("Z", "+00:00"))
                scenario_dates.add(departure.date().isoformat())
            if isinstance(quote_id, str) and observed is not None:
                previous_observed = last_observed_by_quote.get(quote_id)
                if previous_observed is not None and observed < previous_observed:
                    coverage["out-of-order observation"] = True
                last_observed_by_quote[quote_id] = observed
            price = event.get("total_price_minor")
            if isinstance(quote_id, str) and _is_int(price):
                prices_by_quote[quote_id].append(price)

        for prices in prices_by_quote.values():
            if any(current == previous for previous, current in zip(prices, prices[1:])):
                coverage["same-price refresh"] = True
            directions = [
                (current > previous) - (current < previous)
                for previous, current in zip(prices, prices[1:])
                if current != previous
            ]
            if any(current != previous for previous, current in zip(directions, directions[1:])):
                coverage["price bounce"] = True

    if len(scenario_paths) < 12:
        errors.append(f"scenarios: need at least 12 files, found {len(scenario_paths)}")
    missing_scenarios = sorted(REQUIRED_SCENARIOS - scenario_ids)
    if missing_scenarios:
        errors.append(f"scenarios: missing required coverage scenarios: {', '.join(missing_scenarios)}")
    if step_count < 45:
        errors.append(f"scenarios: need at least 45 steps, found {step_count}")
    for coverage_name, present in coverage.items():
        if not present:
            errors.append(f"scenarios: missing coverage for {coverage_name}")
    if scenario_currencies != CURRENCIES:
        errors.append(f"scenarios: must exercise EUR, GBP, and USD; found {sorted(scenario_currencies)}")
    if len(scenario_routes) < 3:
        errors.append(f"scenarios: must exercise at least 3 routes; found {len(scenario_routes)}")
    if len(scenario_dates) < 2:
        errors.append(f"scenarios: must exercise at least 2 departure dates; found {len(scenario_dates)}")
    return scenario_ids, step_count, coverage


def validate_fixture_tree(data_dir: Path | str) -> list[str]:
    """Return all validation errors for a fixture data directory."""
    data_path = Path(data_dir)
    if not (data_path / "catalog.json").exists() and (data_path / "data").is_dir():
        data_path = data_path / "data"
    errors: list[str] = []
    catalog_path = data_path / "catalog.json"
    seed_path = data_path / "seed_quotes.json"
    catalog = _load_json(catalog_path, errors)
    seed = _load_json(seed_path, errors)
    flights, _, _ = _validate_catalog(catalog, str(catalog_path), errors)
    seed_events, seed_identities = _validate_seed(seed, str(seed_path), flights, errors)
    scenario_dir = data_path / "scenarios"
    if not scenario_dir.is_dir():
        errors.append(f"{scenario_dir}: directory is missing")
        scenario_paths: list[Path] = []
    else:
        scenario_paths = sorted(scenario_dir.glob("*.json"))
    _validate_scenarios(scenario_paths, flights, seed_events, seed_identities, errors)
    return errors


def _fixture_counts(data_dir: Path) -> tuple[int, int, int, int]:
    catalog = json.loads((data_dir / "catalog.json").read_text(encoding="utf-8"))
    seed = json.loads((data_dir / "seed_quotes.json").read_text(encoding="utf-8"))
    scenarios = [json.loads(path.read_text(encoding="utf-8")) for path in sorted((data_dir / "scenarios").glob("*.json"))]
    return len(catalog["flights"]), len(seed["events"]), len(scenarios), sum(len(item["steps"]) for item in scenarios)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR, help="fixture data directory")
    arguments = parser.parse_args(argv)
    errors = validate_fixture_tree(arguments.data_dir)
    if errors:
        print(f"Fixture validation failed with {len(errors)} error(s):", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    flights, seed_events, scenarios, steps = _fixture_counts(arguments.data_dir)
    print(
        "Fixture validation passed: "
        f"{flights} flights, {seed_events} seed events, {scenarios} scenarios, {steps} steps."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
