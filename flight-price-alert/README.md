# Take-home assignment: flight price alerts

## Product brief

Travellers often repeat the same flight search while waiting for a price they can afford. Add a feature that lets a traveller save a search and receive a notification when a matching, available fare reaches their target price.

You are joining an existing project. The starter already searches flights, stores supplier quotes in SQLite, and replays simulated price updates. Extend it with price alerts while keeping the existing search working.

We are interested in how you understand an unfamiliar codebase, clarify a product request, use AI, and verify the changes you make.

## Timebox and working approach

- Aim for **3 hours**, with a **hard stop at 4 hours**. Submit partial work and explain remaining priorities when you reach the limit.
- Use AI coding assistants as much as you find useful. No paid service, model API, real flight API, or deployment is required.
- Before coding, raise the product or engineering questions that affect your approach. During a live introduction, ask your interviewer. If you are working asynchronously, record your assumptions and proceed; we assess the consistency of reasonable, stated assumptions.
- Keep the change focused on the feature. Work with the existing application structure and justify any changes to it.

## What to add

1. **Create, list, and cancel a saved price alert.** An alert includes a search, a target total price, and a local recipient identifier. Store its state durably in SQLite. There is one demo user, so you can use a fixed user identity.
2. **Evaluate alerts after replayed quote updates.** Record a notification when an eligible matching fare is at or below the target. Use the replay response's `as_of` as the evaluation time. Explain any additional notification policy you choose.
3. **Provide a durable local notification outbox.** A database record represents a notification. Make it possible to inspect these records through an API or a documented command. Include enough information to identify the alert, triggering quote/update, price, currency, and time. Keep it local; no email, SMS, or push integration is required.
4. **Handle retries and cancellation.** Replaying the same update must not create duplicate notifications. A cancelled alert must stop producing new notifications. Alert and outbox records must survive a process restart.
5. **Add meaningful tests.** Cover the main user flow and the failure or boundary conditions that matter to your implementation. The supplied tests protect the existing starter; they are not a complete acceptance suite for your new feature.

HTTP APIs and a reproducible end-to-end demonstration are sufficient. Extending the browser UI is optional. You may design the alert endpoints and database schema; document how to use them.

## Scope

The core feature covers **one adult, one-way economy searches, with EUR target prices and no currency conversion**. Quote amounts are gross totals in integer minor units, including taxes; EUR 220.00 is `22000`. Search also supports displaying other fixture currencies separately. Preserve fare and baggage information when deciding what matches a saved alert.

The app uses a fixed simulated clock. Flight dates are in 2027; fixtures work independently of the day you run them. A replay step can represent an old, current, or future observation. `observed_at`, `expires_at`, and evaluation `as_of` have different meanings; see [the data guide](data/README.md). Timestamp calculations use their explicit numeric offsets. Airport time-zone labels are descriptive metadata, so the starter does not require an installed time-zone database.

All notifications are local records. Authentication, real suppliers, payments, scheduling infrastructure, and production deployment are outside this exercise. Describe any important production concerns in your notes.

## Run the existing application

Requirements: **Python 3.11 or newer**, including its standard `sqlite3` module. There are no third-party Python dependencies to install.

From the repository root:

```sh
cd flight-price-alert
python3 -m flight_search init-db --db data/local.sqlite3
python3 -m flight_search serve --db data/local.sqlite3 --port 8000
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) to search the supplied flights and replay a scenario step. The server binds to localhost by default.

In another terminal:

```sh
curl -sS http://127.0.0.1:8000/health
curl -sS 'http://127.0.0.1:8000/api/search?origin=LHR&destination=LIS&date=2027-02-12&currency=EUR&as_of=2027-01-15T10:00:00Z'
curl -sS http://127.0.0.1:8000/api/scenarios
```

Apply one scenario step, using a scenario ID from the list:

```sh
curl -sS -X POST http://127.0.0.1:8000/api/replay \
  -H 'Content-Type: application/json' \
  -d '{"scenario_id":"threshold-crossing","step":0}'
```

Run the baseline checks from `flight-price-alert/`:

```sh
python3 tools/validate_fixtures.py
python3 -m unittest discover -s tests -v
```

## Existing interfaces

| Interface | Purpose |
| --- | --- |
| `GET /health` | Check the local service |
| `GET /api/flights` | Inspect the supplied flight catalog |
| `GET /api/search` | Search current eligible quotes for a route, date, currency, and simulated time |
| `GET /api/scenarios` | List deterministic scenario steps |
| `POST /api/replay` | Persist exactly one quote update, identified by scenario and zero-based step index |

Search chooses the latest observation at or before `as_of` for each supplier offer, then excludes unavailable, unverified, expired, and wrong-currency quotes. The ordering matters: an older available observation must not revive an offer whose latest observation is sold out. Separate fare/baggage products retain separate identities. There is no currency conversion.

An identical replay returns success with a replay indicator. Reusing an event ID with different content returns a conflict without changing the stored event. Candidate alert evaluation belongs after a successful replay, including a repeated replay; make notification handling safe to repeat and recover after interruptions. The starter leaves that integration point for you to implement.

Initializing an existing database preserves replay history. For an **independent scenario**, stop the server, choose a fresh SQLite file, initialize it, and create the alerts needed for that scenario. Switching scenarios in the UI does not reset quotes, alerts, or outbox state. For a restart test, reuse the same file.

## Data and project layout

```text
flight_search/       existing search, SQLite storage, HTTP API, CLI
static/              existing flight search and replay UI
data/catalog.json    fictional flight catalog and fixed demo clock
data/seed_quotes.json initial supplier observations
data/scenarios/      deterministic update sequences
tools/               fixture validation
tests/               existing starter tests
```

The data includes price drops and increases, repeated and delayed updates, expired and future quotes, availability changes, and different search/fare products. Scenarios are input data rather than a prescribed notification policy. Add fixtures where your design needs them.

This starter and its quote data were independently authored for this assessment. Suppliers, flight numbers, availability, and prices are synthetic. Airport identifiers and time zones describe the example routes. No live inventory or original supplier credentials are used.

## Submission

Submit a branch, repository, or archive as agreed with your interviewer, including:

- Your implementation and tests.
- Exact install/run/test commands and an example that creates an alert, replays an update, and inspects its notification.
- `DECISIONS.md`: questions or assumptions, chosen product behavior, key engineering decisions, time spent, and remaining work.
- `AI_USAGE.md`: tools used, important tasks/prompts, what you accepted or changed, and how you checked the resulting code and tests. Include any misleading AI suggestion you encountered; do not invent one if none occurred.

We assess working behavior, data integrity, useful tests, product reasoning, and your ability to explain the implementation. A smaller, verified change with clear priorities is a valid submission at the time limit.
