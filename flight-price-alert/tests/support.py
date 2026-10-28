"""Small deterministic fixtures shared by the application tests."""

from __future__ import annotations

import json
import threading
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from flight_search.server import build_server
from flight_search.service import FlightSearchService


def quote(
    event_id: str,
    *,
    quote_id: str = "offer_001",
    flight_id: str = "flight_001",
    supplier: str = "provider_a",
    price: int = 22000,
    currency: str = "EUR",
    available: bool = True,
    verified: bool = True,
    observed_at: str = "2027-01-15T09:55:00Z",
    expires_at: str = "2027-01-15T10:30:00Z",
    fare_family: str = "standard",
    checked_bag_kg: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": event_id,
        "quote_id": quote_id,
        "flight_id": flight_id,
        "supplier": supplier,
        "total_price_minor": price,
        "currency": currency,
        "available": available,
        "verified": verified,
        "observed_at": observed_at,
        "expires_at": expires_at,
        "fare_family": fare_family,
        "checked_bag_kg": checked_bag_kg,
    }


def write_test_data(root: Path) -> Path:
    data = root / "data"
    scenarios = data / "scenarios"
    scenarios.mkdir(parents=True)
    catalog = {
        "schema_version": 1,
        "demo_as_of": "2027-01-15T10:00:00Z",
        "airports": [
            {"iata": "LHR", "name": "London North", "timezone": "Europe/London"},
            {"iata": "LIS", "name": "Lisbon Central", "timezone": "Europe/Lisbon"},
            {"iata": "MAD", "name": "Madrid Central", "timezone": "Europe/Madrid"},
        ],
        "flights": [
            {
                "flight_id": "flight_001",
                "origin": "LHR",
                "destination": "LIS",
                "departure_at": "2027-02-12T09:00:00+00:00",
                "arrival_at": "2027-02-12T11:45:00+00:00",
                "carrier": "ZZ",
                "flight_number": "ZZ101",
                "cabin": "economy",
                "adults": 1,
            },
            {
                "flight_id": "flight_002",
                "origin": "LHR",
                "destination": "MAD",
                "departure_at": "2027-02-12T12:00:00+00:00",
                "arrival_at": "2027-02-12T14:20:00+00:00",
                "carrier": "ZZ",
                "flight_number": "ZZ202",
                "cabin": "economy",
                "adults": 1,
            },
        ],
    }
    seed = {
        "schema_version": 1,
        "events": [
            quote("evt_seed"),
            quote(
                "evt_usd",
                quote_id="offer_usd",
                supplier="provider_b",
                price=24000,
                currency="USD",
            ),
        ],
    }
    availability_steps = [
        {
            "label": "supplier sells out",
            "as_of": "2027-01-15T10:06:00Z",
            "event": quote(
                "evt_sold_out",
                available=False,
                observed_at="2027-01-15T10:05:00Z",
                expires_at="2027-01-15T11:00:00Z",
            ),
        },
        {
            "label": "older event arrives late",
            "as_of": "2027-01-15T10:07:00Z",
            "event": quote(
                "evt_old_late",
                price=18000,
                observed_at="2027-01-15T10:01:00Z",
                expires_at="2027-01-15T11:00:00Z",
            ),
        },
        {
            "label": "supplier returns",
            "as_of": "2027-01-15T10:11:00Z",
            "event": quote(
                "evt_available",
                price=19000,
                observed_at="2027-01-15T10:10:00Z",
                expires_at="2027-01-15T11:00:00Z",
            ),
        },
    ]
    duplicate_event = quote(
        "evt_duplicate",
        price=20000,
        observed_at="2027-01-15T10:12:00Z",
        expires_at="2027-01-15T11:00:00Z",
    )
    conflict_event = dict(duplicate_event, total_price_minor=19900)
    duplicate_steps = [
        {"label": "first delivery", "as_of": "2027-01-15T10:13:00Z", "event": duplicate_event},
        {"label": "identical delivery", "as_of": "2027-01-15T10:13:00Z", "event": duplicate_event},
        {
            "label": "conflicting delivery",
            "as_of": "2027-01-15T10:13:00Z",
            "event": conflict_event,
            "expected_replay_status": 409,
        },
    ]
    for filename, scenario_id, description, steps in (
        ("availability.json", "availability", "Latest event eligibility", availability_steps),
        ("duplicate.json", "duplicate-event", "Idempotency and conflicts", duplicate_steps),
    ):
        payload = {
            "schema_version": 1,
            "scenario_id": scenario_id,
            "description": description,
            "steps": steps,
        }
        (scenarios / filename).write_text(json.dumps(payload), encoding="utf-8")
    (data / "catalog.json").write_text(json.dumps(catalog), encoding="utf-8")
    (data / "seed_quotes.json").write_text(json.dumps(seed), encoding="utf-8")
    return data


class LiveServer(AbstractContextManager["LiveServer"]):
    def __init__(self, db_path: Path, data_dir: Path):
        self.service = FlightSearchService(db_path, data_dir)
        self.service.initialize()
        self.server = build_server(self.service, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.port = self.server.server_address[1]

    def __enter__(self) -> "LiveServer":
        self.thread.start()
        return self

    def __exit__(self, *args: Any) -> None:
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
