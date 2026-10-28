# Flight search fixtures

This directory contains deterministic fixture data for the existing flight-search application. The carrier code `ZZ`, supplier labels, product identifiers, event identifiers, schedules, and prices are synthetic. The application does not contact an airline, supplier, currency service, or other external API.

All JSON files use `schema_version: 1`. Money is represented as a positive integer in the currency's minor unit. For example, `22000` with `currency: "EUR"` represents EUR 220.00. Fixtures never perform currency conversion.

## Files

- `catalog.json` defines airports and synthetic flights. `demo_as_of` is the default evaluation time used by the demo application.
- `seed_quotes.json` contains the quote-event history loaded into a new database before a search or scenario replay.
- `scenarios/*.json` contains named, ordered replay sequences. Scenario file names match their `scenario_id` values.

The catalog fields are:

- Airport `timezone` is a qualified `Region/Location`-style display label. It is metadata for display and grouping only. Validation checks the label's structure without consulting the IANA registry or a system timezone database. Flight-time comparisons use the explicit UTC offsets in `departure_at` and `arrival_at`, so they do not depend on this label.
- `flight_id`: stable fixture identifier for one scheduled flight.
- `origin` and `destination`: three-letter airport codes.
- `departure_at` and `arrival_at`: timezone-aware ISO-8601 datetimes.
- `carrier` and `flight_number`: synthetic display values.
- `cabin` and `adults`: the fixed scope of the starter search (`economy`, one adult).

Every quote event has these fields:

- `event_id`: delivery identity. Replaying an identical event is idempotent. Reusing it with different content is a technical conflict.
- `quote_id`: stable product identity across observations. A `quote_id` always refers to the same `flight_id`, `supplier`, `currency`, `fare_family`, and `checked_bag_kg` values.
- `flight_id`: reference to a flight in `catalog.json`.
- `supplier`: one of the synthetic labels `provider_a`, `provider_b`, or `provider_c`.
- `total_price_minor` and `currency`: gross one-adult total in integer minor units, with currency `EUR`, `GBP`, or `USD`.
- `available` and `verified`: boolean state reported by that observation.
- `observed_at`: timezone-aware time at which the supplier observation was made.
- `expires_at`: timezone-aware validity boundary, later than `observed_at`.
- `fare_family` and `checked_bag_kg`: product attributes. Different baggage or fare values are separate products and must not be combined silently.

## Scenario mechanics

A scenario is an ordered list of steps. Each step has a unique `label`, an `as_of` evaluation time, and exactly one quote `event` to replay. Evaluate search and alert behavior using the step's `as_of`; do not substitute wall-clock time. It is valid for `as_of` to be earlier than `event.observed_at`, which represents a future observation that has arrived but is not yet eligible at that evaluation time.

`expected_replay_status` is optional and defaults to `200`. It describes only event-ingestion behavior. An identical event replay expects `200`; a deliberately changed payload reusing an earlier `event_id` is annotated `409`. It does not specify any alert decision or notification count.

Scenarios are independent examples. To run one deterministically, create a fresh SQLite database, load `seed_quotes.json`, and then replay that scenario's steps in order. Scenario events from a previous run are not an input to the next scenario. The demo UI's scenario selector does not itself reset a database, so use a fresh database when switching between independent examples.

The sequences cover price decreases, equality, steady and upward movement, bouncing prices, duplicate and conflicting deliveries, out-of-order observations, expiry boundaries, future observations, verification and availability state, route and date scope, currency separation, and baggage-product separation. They intentionally do not publish expected alert counts or prescribe alert-product decisions.

Run the structural and coverage validator from the assignment root:

```sh
python3 tools/validate_fixtures.py
```
