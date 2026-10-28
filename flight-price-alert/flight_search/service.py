"""Fixture loading, quote replay, and flight search business rules."""

from __future__ import annotations

import json
import re
from contextlib import closing
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import db


IATA_RE = re.compile(r"^[A-Z]{3}$")
SCENARIO_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ALLOWED_CURRENCIES = {"EUR", "GBP", "USD"}
ALLOWED_SUPPLIERS = {"provider_a", "provider_b", "provider_c"}
QUOTE_FIELDS = {
    "event_id",
    "quote_id",
    "flight_id",
    "supplier",
    "total_price_minor",
    "currency",
    "available",
    "verified",
    "observed_at",
    "expires_at",
    "fare_family",
    "checked_bag_kg",
}


class ValidationError(ValueError):
    """Client or fixture input is malformed."""


class NotFoundError(LookupError):
    """A requested scenario does not exist."""


def parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{field} must be a non-empty timezone-aware timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"{field} must be an ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValidationError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


def timestamp_epoch(value: Any, field: str) -> float:
    return parse_timestamp(value, field).timestamp()


def validate_quote(event: Any) -> tuple[float, float]:
    if not isinstance(event, dict):
        raise ValidationError("quote event must be a JSON object")
    missing = sorted(QUOTE_FIELDS - set(event))
    extra = sorted(set(event) - QUOTE_FIELDS)
    if missing or extra:
        parts = []
        if missing:
            parts.append(f"missing fields: {', '.join(missing)}")
        if extra:
            parts.append(f"unknown fields: {', '.join(extra)}")
        raise ValidationError("quote event has " + "; ".join(parts))

    for field in ("event_id", "quote_id", "flight_id", "fare_family"):
        if not isinstance(event[field], str) or not event[field].strip():
            raise ValidationError(f"{field} must be a non-empty string")
    if event["supplier"] not in ALLOWED_SUPPLIERS:
        raise ValidationError("supplier is not supported")
    if event["currency"] not in ALLOWED_CURRENCIES:
        raise ValidationError("currency is not supported")
    if type(event["total_price_minor"]) is not int or event["total_price_minor"] <= 0:
        raise ValidationError("total_price_minor must be a positive integer")
    if type(event["checked_bag_kg"]) is not int or event["checked_bag_kg"] < 0:
        raise ValidationError("checked_bag_kg must be a non-negative integer")
    if type(event["available"]) is not bool or type(event["verified"]) is not bool:
        raise ValidationError("available and verified must be booleans")

    observed_epoch = timestamp_epoch(event["observed_at"], "observed_at")
    expires_epoch = timestamp_epoch(event["expires_at"], "expires_at")
    if expires_epoch <= observed_epoch:
        raise ValidationError("expires_at must be after observed_at")
    return observed_epoch, expires_epoch


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as fixture:
            return json.load(fixture)
    except FileNotFoundError as exc:
        raise ValidationError(f"required fixture is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON fixture {path}: {exc}") from exc


class FlightSearchService:
    """Application facade.

    Search results are intentionally flat: one item represents one flight and
    one quote product. Supplier, fare family, and baggage details are never
    silently combined.
    """

    def __init__(self, db_path: Path | str, data_dir: Path | str | None = None):
        self.db_path = Path(db_path)
        self.data_dir = (
            Path(data_dir)
            if data_dir is not None
            else Path(__file__).resolve().parent.parent / "data"
        )

    def initialize(self) -> None:
        db.initialize(self.db_path)
        seed = _load_json(self.data_dir / "seed_quotes.json")
        if not isinstance(seed, dict) or seed.get("schema_version") != 1:
            raise ValidationError("seed_quotes.json must have schema_version 1")
        events = seed.get("events")
        if not isinstance(events, list):
            raise ValidationError("seed_quotes.json events must be an array")
        with db.transaction(self.db_path) as connection:
            for event in events:
                observed_epoch, expires_epoch = validate_quote(event)
                db.insert_quote_event(
                    connection,
                    event,
                    observed_epoch=observed_epoch,
                    expires_epoch=expires_epoch,
                )

    def _catalog(self) -> dict[str, Any]:
        catalog = _load_json(self.data_dir / "catalog.json")
        if not isinstance(catalog, dict) or catalog.get("schema_version") != 1:
            raise ValidationError("catalog.json must have schema_version 1")
        if not isinstance(catalog.get("airports"), list) or not isinstance(
            catalog.get("flights"), list
        ):
            raise ValidationError("catalog airports and flights must be arrays")
        parse_timestamp(catalog.get("demo_as_of"), "demo_as_of")
        return catalog

    def catalog(self) -> dict[str, Any]:
        return self._catalog()

    @staticmethod
    def _validate_search_query(
        origin: Any,
        destination: Any,
        travel_date: Any,
        currency: Any,
        as_of: Any,
    ) -> tuple[str, str, str, str, datetime]:
        if not isinstance(origin, str) or not IATA_RE.fullmatch(origin):
            raise ValidationError("origin must be a three-letter uppercase IATA code")
        if not isinstance(destination, str) or not IATA_RE.fullmatch(destination):
            raise ValidationError("destination must be a three-letter uppercase IATA code")
        if origin == destination:
            raise ValidationError("origin and destination must differ")
        if currency not in ALLOWED_CURRENCIES:
            raise ValidationError("currency must be one of EUR, GBP, or USD")
        if not isinstance(travel_date, str):
            raise ValidationError("date must be an ISO calendar date")
        try:
            parsed_date = date.fromisoformat(travel_date)
        except ValueError as exc:
            raise ValidationError("date must be a valid ISO calendar date") from exc
        if parsed_date.isoformat() != travel_date:
            raise ValidationError("date must use YYYY-MM-DD format")
        parsed_as_of = parse_timestamp(as_of, "as_of")
        return origin, destination, travel_date, currency, parsed_as_of

    def search(
        self,
        *,
        origin: str,
        destination: str,
        travel_date: str,
        currency: str,
        as_of: str | None = None,
    ) -> dict[str, Any]:
        catalog = self._catalog()
        effective_as_of = as_of if as_of is not None else catalog["demo_as_of"]
        origin, destination, travel_date, currency, parsed_as_of = self._validate_search_query(
            origin, destination, travel_date, currency, effective_as_of
        )

        flights = {
            flight["flight_id"]: flight
            for flight in catalog["flights"]
            if flight.get("origin") == origin
            and flight.get("destination") == destination
            and isinstance(flight.get("departure_at"), str)
            and flight["departure_at"][:10] == travel_date
        }
        latest: dict[str, Any] = {}
        if flights:
            placeholders = ",".join("?" for _ in flights)
            sql = f"""
                SELECT * FROM quote_events
                WHERE flight_id IN ({placeholders}) AND observed_at_epoch <= ?
                ORDER BY quote_id ASC, observed_at_epoch DESC, event_id DESC
            """
            with closing(db.connect(self.db_path)) as connection:
                rows = connection.execute(
                    sql, (*flights.keys(), parsed_as_of.timestamp())
                ).fetchall()
            for row in rows:
                latest.setdefault(row["quote_id"], row)

        results = []
        for row in latest.values():
            # Eligibility is deliberately evaluated only after selecting the
            # latest observation. A sold-out update cannot reveal an old fare.
            if not row["available"] or not row["verified"]:
                continue
            if row["expires_at_epoch"] <= parsed_as_of.timestamp():
                continue
            if row["currency"] != currency:
                continue
            flight = flights[row["flight_id"]]
            results.append(
                {
                    **flight,
                    "event_id": row["event_id"],
                    "quote_id": row["quote_id"],
                    "supplier": row["supplier"],
                    "total_price_minor": row["total_price_minor"],
                    "currency": row["currency"],
                    "fare_family": row["fare_family"],
                    "checked_bag_kg": row["checked_bag_kg"],
                    "observed_at": row["observed_at"],
                    "expires_at": row["expires_at"],
                }
            )
        results.sort(
            key=lambda result: (
                result["total_price_minor"],
                result["departure_at"],
                result["flight_id"],
                result["quote_id"],
            )
        )
        return {
            "query": {
                "origin": origin,
                "destination": destination,
                "date": travel_date,
                "currency": currency,
                "as_of": effective_as_of,
            },
            "results": results,
        }

    def _scenarios(self) -> dict[str, dict[str, Any]]:
        scenarios: dict[str, dict[str, Any]] = {}
        scenarios_dir = self.data_dir / "scenarios"
        if not scenarios_dir.is_dir():
            raise ValidationError(f"required fixture directory is missing: {scenarios_dir}")
        for path in sorted(scenarios_dir.glob("*.json")):
            scenario = _load_json(path)
            if not isinstance(scenario, dict) or scenario.get("schema_version") != 1:
                raise ValidationError(f"{path.name} must have schema_version 1")
            scenario_id = scenario.get("scenario_id")
            if not isinstance(scenario_id, str) or not SCENARIO_ID_RE.fullmatch(scenario_id):
                raise ValidationError(f"{path.name} has an invalid scenario_id")
            if scenario_id in scenarios:
                raise ValidationError(f"duplicate scenario_id: {scenario_id}")
            steps = scenario.get("steps")
            if not isinstance(steps, list):
                raise ValidationError(f"{scenario_id} steps must be an array")
            scenarios[scenario_id] = scenario
        return scenarios

    def scenarios(self) -> dict[str, Any]:
        items = []
        for scenario in self._scenarios().values():
            items.append(
                {
                    "scenario_id": scenario["scenario_id"],
                    "description": scenario.get("description", ""),
                    "steps": [
                        {
                            "step": index,
                            "label": step.get("label", ""),
                            "as_of": step.get("as_of"),
                        }
                        for index, step in enumerate(scenario["steps"])
                    ],
                }
            )
        return {"scenarios": items}

    def replay(self, scenario_id: Any, step_index: Any) -> dict[str, Any]:
        if not isinstance(scenario_id, str) or not SCENARIO_ID_RE.fullmatch(scenario_id):
            raise ValidationError("scenario_id has an invalid format")
        if type(step_index) is not int or step_index < 0:
            raise ValidationError("step must be a non-negative integer")
        scenarios = self._scenarios()
        if scenario_id not in scenarios:
            raise NotFoundError(f"scenario {scenario_id!r} was not found")
        scenario = scenarios[scenario_id]
        if step_index >= len(scenario["steps"]):
            raise ValidationError("step is outside this scenario")
        step = scenario["steps"][step_index]
        if not isinstance(step, dict):
            raise ValidationError("scenario step must be an object")
        as_of = step.get("as_of")
        parse_timestamp(as_of, "as_of")
        event = step.get("event")
        observed_epoch, expires_epoch = validate_quote(event)
        with db.transaction(self.db_path) as connection:
            inserted = db.insert_quote_event(
                connection,
                event,
                observed_epoch=observed_epoch,
                expires_epoch=expires_epoch,
            )
        result = {
            "scenario_id": scenario_id,
            "step": step_index,
            "label": step.get("label", ""),
            "as_of": as_of,
            "event": event,
            "replayed": not inserted,
        }
        self.after_successful_replay(result)
        return result

    def after_successful_replay(self, replay_result: dict[str, Any]) -> None:
        """Extension point for the candidate's post-replay alert evaluation."""
