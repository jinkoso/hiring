from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from flight_search import db
from flight_search.db import QuoteConflictError
from flight_search.service import FlightSearchService, ValidationError, validate_quote

from support import quote, write_test_data


class TrackingConnection:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.closed = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def close(self):
        self.closed = True
        return self.connection.close()


class CoordinatedConnection:
    """Force deferred transactions to make their pre-insert reads together."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        event_barrier: threading.Barrier,
        product_barrier: threading.Barrier,
    ):
        self.connection = connection
        self.event_barrier = event_barrier
        self.product_barrier = product_barrier
        self.serialized_writer = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def execute(self, sql, parameters=()):
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            self.serialized_writer = True
        cursor = self.connection.execute(sql, parameters)
        if not self.serialized_writer:
            if "WHERE event_id = ?" in sql:
                self.event_barrier.wait(timeout=5)
            elif "SELECT flight_id" in sql and "WHERE quote_id = ?" in sql:
                self.product_barrier.wait(timeout=5)
        return cursor


class FlightSearchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_dir = write_test_data(self.root)
        self.db_path = self.root / "search.sqlite3"
        self.service = FlightSearchService(self.db_path, self.data_dir)
        self.service.initialize()

    def search(self, as_of: str = "2027-01-15T10:00:00Z", currency: str = "EUR"):
        return self.service.search(
            origin="LHR",
            destination="LIS",
            travel_date="2027-02-12",
            currency=currency,
            as_of=as_of,
        )

    def test_seed_search_returns_each_eligible_quote_product(self) -> None:
        eur = self.search()
        self.assertEqual(["offer_001"], [item["quote_id"] for item in eur["results"]])
        self.assertEqual(22000, eur["results"][0]["total_price_minor"])
        self.assertEqual("standard", eur["results"][0]["fare_family"])
        self.assertEqual(0, eur["results"][0]["checked_bag_kg"])
        self.assertEqual(["offer_usd"], [item["quote_id"] for item in self.search(currency="USD")["results"]])

    def test_latest_event_is_selected_before_eligibility_filters(self) -> None:
        self.service.replay("availability", 0)
        self.assertEqual([], self.search("2027-01-15T10:06:00Z")["results"])

        self.service.replay("availability", 1)
        self.assertEqual(
            [],
            self.search("2027-01-15T10:07:00Z")["results"],
            "an older available event must not replace a newer sold-out event",
        )

        replay = self.service.replay("availability", 2)
        self.assertEqual("2027-01-15T10:11:00Z", replay["as_of"])
        results = self.search(replay["as_of"])["results"]
        self.assertEqual([19000], [item["total_price_minor"] for item in results])

    def test_future_unverified_and_expired_latest_events_do_not_fall_back(self) -> None:
        events = [
            quote(
                "evt_unverified",
                verified=False,
                observed_at="2027-01-15T10:05:00Z",
                expires_at="2027-01-15T11:00:00Z",
            ),
            quote(
                "evt_future",
                price=17000,
                observed_at="2027-01-15T10:20:00Z",
                expires_at="2027-01-15T11:00:00Z",
            ),
        ]
        with db.transaction(self.db_path) as connection:
            for event in events:
                observed, expires = validate_quote(event)
                db.insert_quote_event(connection, event, observed_epoch=observed, expires_epoch=expires)
        self.assertEqual([], self.search("2027-01-15T10:10:00Z")["results"])
        self.assertEqual([17000], [r["total_price_minor"] for r in self.search("2027-01-15T10:21:00Z")["results"]])
        self.assertEqual([], self.search("2027-01-15T11:00:00Z")["results"])

    def test_tied_observations_use_event_id_as_a_deterministic_tie_break(self) -> None:
        first = quote("evt_tie_a", price=21000)
        second = quote("evt_tie_z", price=20500)
        with db.transaction(self.db_path) as connection:
            for event in (first, second):
                observed, expires = validate_quote(event)
                db.insert_quote_event(connection, event, observed_epoch=observed, expires_epoch=expires)
        self.assertEqual(20500, self.search()["results"][0]["total_price_minor"])
        self.assertEqual("evt_tie_z", self.search()["results"][0]["event_id"])

    def test_initialize_is_idempotent_and_replayed_quotes_survive_restart(self) -> None:
        self.service.replay("availability", 0)
        restarted = FlightSearchService(self.db_path, self.data_dir)
        restarted.initialize()
        result = restarted.search(
            origin="LHR",
            destination="LIS",
            travel_date="2027-02-12",
            currency="EUR",
            as_of="2027-01-15T10:06:00Z",
        )
        self.assertEqual([], result["results"])
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute("SELECT COUNT(*) FROM quote_events").fetchone()[0]
        self.assertEqual(3, count)

    def test_search_closes_its_operation_scoped_connection(self) -> None:
        tracking = TrackingConnection(db.connect(self.db_path))
        with mock.patch.object(db, "connect", return_value=tracking):
            self.search()
        self.assertTrue(tracking.closed)

    def _concurrent_inserts(self, events):
        original_connect = db.connect
        event_barrier = threading.Barrier(2)
        product_barrier = threading.Barrier(2)
        outcomes = []
        outcome_lock = threading.Lock()

        def coordinated_connect(path):
            return CoordinatedConnection(
                original_connect(path), event_barrier, product_barrier
            )

        def worker(event):
            try:
                observed, expires = validate_quote(event)
                with db.transaction(self.db_path) as connection:
                    inserted = db.insert_quote_event(
                        connection,
                        event,
                        observed_epoch=observed,
                        expires_epoch=expires,
                    )
                outcome = ("ok", inserted)
            except QuoteConflictError:
                outcome = ("conflict", None)
            except Exception as exc:  # The assertion reports unexpected lock failures.
                outcome = (type(exc).__name__, str(exc))
            with outcome_lock:
                outcomes.append(outcome)

        with mock.patch.object(db, "connect", side_effect=coordinated_connect):
            threads = [threading.Thread(target=worker, args=(event,)) for event in events]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10)
            self.assertTrue(all(not thread.is_alive() for thread in threads))
        return outcomes

    def test_concurrent_identical_first_replay_is_idempotent(self) -> None:
        event = quote("evt_concurrent", quote_id="offer_concurrent")
        outcomes = self._concurrent_inserts([event, event])
        self.assertCountEqual([("ok", True), ("ok", False)], outcomes)
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM quote_events WHERE event_id = ?", (event["event_id"],)
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_concurrent_quote_product_identity_conflict_is_deterministic(self) -> None:
        first = quote("evt_product_a", quote_id="offer_product")
        second = quote(
            "evt_product_b",
            quote_id="offer_product",
            supplier="provider_b",
        )
        outcomes = self._concurrent_inserts([first, second])
        self.assertEqual(1, sum(outcome[0] == "ok" for outcome in outcomes))
        self.assertEqual(1, sum(outcome[0] == "conflict" for outcome in outcomes))
        with closing(sqlite3.connect(self.db_path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM quote_events WHERE quote_id = ?", ("offer_product",)
            ).fetchone()[0]
        self.assertEqual(1, count)

    def test_search_rejects_malformed_inputs_and_empty_matches_are_valid(self) -> None:
        with self.assertRaisesRegex(ValidationError, "origin"):
            self.service.search(
                origin="lhr",
                destination="LIS",
                travel_date="2027-02-12",
                currency="EUR",
            )
        with self.assertRaisesRegex(ValidationError, "timezone"):
            self.search(as_of="2027-01-15T10:00:00")
        empty = self.service.search(
            origin="LIS",
            destination="LHR",
            travel_date="2027-02-12",
            currency="EUR",
        )
        self.assertEqual([], empty["results"])

    def test_public_scenarios_replay_independently_with_annotated_statuses(self) -> None:
        public_data = Path(__file__).resolve().parents[1] / "data"
        catalog = json.loads((public_data / "catalog.json").read_text(encoding="utf-8"))
        flights = {flight["flight_id"]: flight for flight in catalog["flights"]}
        for scenario_path in sorted((public_data / "scenarios").glob("*.json")):
            scenario = json.loads(scenario_path.read_text(encoding="utf-8"))
            scenario_db = self.root / f'{scenario["scenario_id"]}.sqlite3'
            service = FlightSearchService(scenario_db, public_data)
            service.initialize()
            for index, step in enumerate(scenario["steps"]):
                expected = step.get("expected_replay_status", 200)
                with self.subTest(scenario=scenario["scenario_id"], step=index):
                    if expected == 409:
                        with self.assertRaises(QuoteConflictError):
                            service.replay(scenario["scenario_id"], index)
                        continue
                    replayed = service.replay(scenario["scenario_id"], index)
                    self.assertEqual(step["as_of"], replayed["as_of"])
                    flight = flights[step["event"]["flight_id"]]
                    response = service.search(
                        origin=flight["origin"],
                        destination=flight["destination"],
                        travel_date=flight["departure_at"][:10],
                        currency=step["event"]["currency"],
                        as_of=replayed["as_of"],
                    )
                    self.assertIn("results", response)


if __name__ == "__main__":
    unittest.main()
