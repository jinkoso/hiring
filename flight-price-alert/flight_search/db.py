"""SQLite storage for immutable quote events."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


class QuoteConflictError(ValueError):
    """A replay tried to reuse an identifier for different data."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS quote_events (
    event_id TEXT PRIMARY KEY,
    quote_id TEXT NOT NULL,
    flight_id TEXT NOT NULL,
    supplier TEXT NOT NULL,
    total_price_minor INTEGER NOT NULL CHECK (total_price_minor > 0),
    currency TEXT NOT NULL,
    available INTEGER NOT NULL CHECK (available IN (0, 1)),
    verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
    observed_at TEXT NOT NULL,
    observed_at_epoch REAL NOT NULL,
    expires_at TEXT NOT NULL,
    expires_at_epoch REAL NOT NULL,
    fare_family TEXT NOT NULL,
    checked_bag_kg INTEGER NOT NULL CHECK (checked_bag_kg >= 0),
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS quote_events_flight_observed
    ON quote_events(flight_id, observed_at_epoch);
CREATE INDEX IF NOT EXISTS quote_events_quote_observed
    ON quote_events(quote_id, observed_at_epoch, event_id);
"""


def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open one operation-scoped connection with defensive defaults."""

    connection = sqlite3.connect(str(db_path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


@contextmanager
def transaction(db_path: Path | str) -> Iterator[sqlite3.Connection]:
    connection = connect(db_path)
    try:
        # Replay checks an identifier and its immutable product identity before
        # inserting. Reserving the single SQLite writer up front makes that
        # check-and-insert sequence atomic across concurrent HTTP requests.
        connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize(db_path: Path | str) -> None:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(path)
    try:
        connection.executescript(SCHEMA)
    finally:
        connection.close()


def canonical_payload(event: dict[str, Any]) -> str:
    return json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def insert_quote_event(
    connection: sqlite3.Connection,
    event: dict[str, Any],
    *,
    observed_epoch: float,
    expires_epoch: float,
) -> bool:
    """Insert an event, returning False for an identical replay.

    Both event identifiers and quote product identity are immutable. This keeps
    out-of-order delivery safe while retaining every accepted observation.
    """

    payload_json = canonical_payload(event)
    existing = connection.execute(
        "SELECT payload_json FROM quote_events WHERE event_id = ?", (event["event_id"],)
    ).fetchone()
    if existing is not None:
        if existing["payload_json"] == payload_json:
            return False
        raise QuoteConflictError(
            f'event_id {event["event_id"]!r} already exists with different content'
        )

    product = connection.execute(
        """
        SELECT flight_id, supplier, currency, fare_family, checked_bag_kg
        FROM quote_events
        WHERE quote_id = ?
        LIMIT 1
        """,
        (event["quote_id"],),
    ).fetchone()
    if product is not None:
        expected = (
            product["flight_id"],
            product["supplier"],
            product["currency"],
            product["fare_family"],
            product["checked_bag_kg"],
        )
        received = (
            event["flight_id"],
            event["supplier"],
            event["currency"],
            event["fare_family"],
            event["checked_bag_kg"],
        )
        if received != expected:
            raise QuoteConflictError(
                f'quote_id {event["quote_id"]!r} cannot change its product identity'
            )

    connection.execute(
        """
        INSERT INTO quote_events (
            event_id, quote_id, flight_id, supplier, total_price_minor,
            currency, available, verified, observed_at, observed_at_epoch,
            expires_at, expires_at_epoch, fare_family, checked_bag_kg,
            payload_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event["event_id"],
            event["quote_id"],
            event["flight_id"],
            event["supplier"],
            event["total_price_minor"],
            event["currency"],
            int(event["available"]),
            int(event["verified"]),
            event["observed_at"],
            observed_epoch,
            event["expires_at"],
            expires_epoch,
            event["fare_family"],
            event["checked_bag_kg"],
            payload_json,
        ),
    )
    return True
