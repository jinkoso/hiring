# Take-Home Assignment: LLM Trip Request Parser

## Goal

Build a small service that turns a natural-language one-way trip request into a validated structured record. Show how you combine an LLM with deterministic application logic, persistence, and tests.

## Timebox

- Spend 2–3 hours.
- Stop after 3 hours and submit what you have. An incomplete but well-explained solution is acceptable.
- Please note any unfinished work or trade-offs in your README.

## Technology

- Use Python or TypeScript.
- Expose either a command-line interface or an HTTP interface.
- Use a genuine LLM call for extraction. Do not implement the production path entirely with regular expressions or hard-coded phrase matching.
- Any LLM provider and generally available model are acceptable.
- Read API keys and other secrets from environment variables only.
- Use SQLite for persistence.

You do not need `cities.json`. Do not resolve, canonicalize, or validate city or airport names. Preserve supplied location labels with surrounding whitespace removed.

## Input contract

Your interface accepts:

```json
{
  "text": "Two of us need to fly from Seattle to Lisbon on 2027-05-10",
  "reference_date": "2026-11-02"
}
```

- `text` is a non-empty string.
- `reference_date` is a valid ISO `YYYY-MM-DD` local calendar date.
- `reference_date` is the sole basis for relative dates. Do not use the server clock, user locale, or an inferred time zone.

Invalid interface input is a technical error and must not create a successful request record.

## Output contract

Return this shape after successful extraction and validation:

```json
{
  "request_id": "generated-unique-id",
  "status": "ready",
  "origin": "Seattle",
  "destination": "Lisbon",
  "departure_date": "2027-05-10",
  "passengers": 2,
  "budget_per_person": {
    "amount": null,
    "currency": null
  },
  "clarification_questions": []
}
```

Field rules:

- `request_id`: a generated unique identifier.
- `status`: exactly `ready` or `needs_clarification`.
- `origin`: a trimmed string or `null`.
- `destination`: a trimmed string or `null`.
- `departure_date`: ISO `YYYY-MM-DD` or `null`.
- `passengers`: a positive integer or `null`.
- `budget_per_person.amount`: a positive number or `null`.
- `budget_per_person.currency`: an uppercase ISO currency code or `null`.
- `clarification_questions`: an array of specific questions for the user.

Origin, destination, departure date, and passengers are required. Missing, ambiguous, or invalid required information becomes `null`; preserve every other known field, set `status` to `needs_clarification`, and ask a specific question.

Budget is optional. If absent, both budget fields are `null` and do not prevent `ready` status. For incomplete, ambiguous, or invalid budget information, preserve valid parts, require clarification, and ask for the missing detail.

When `status` is `ready`, questions must be empty. When it is `needs_clarification`, they must be meaningful; wording is your choice.

## Deterministic interpretation policy

Implement and test these rules so behavior does not depend on hidden locale or travel-domain assumptions.

### Dates

- Support ISO dates and unambiguous written dates that include a year.
- Support `today`, `tomorrow`, and `in N days`, where `N` is a non-negative integer.
- Same-day travel is allowed.
- A past or invalid calendar date becomes `null` and requires clarification.
- Numeric dates are ambiguous when both day and month could be 12 or less, for example `03/04/2027`.
- Treat phrases such as `next Friday` and `next week` as ambiguous.
- A written month and day without a year requires clarification.

### Passengers

- Accept numbers and words, including phrases such as `two of us`.
- `solo` means one passenger.
- Return total headcount only. `4 adults and 2 children` means six passengers.
- Do not infer one passenger when passenger count is missing.
- Zero, negative, fractional, or invalid counts become `null` and require clarification.

### Budget

- Recognize explicit `EUR`/`€`, `GBP`/`£`, and `USD`/`US$` currencies.
- A bare `$` is ambiguous; never infer currency from the route.
- `per person` and `each` identify an explicit per-person amount.
- An unqualified budget has ambiguous basis. Preserve known currency, set amount to `null`, and ask if it is per person.
- If a positive per-person amount is explicit but currency is unknown, preserve the amount and ask for currency.
- Zero or negative amounts become `null`; retain explicit valid currency and ask for a valid amount.
- Explicit total budgets are outside this exercise's test data.

Return trips and multi-leg trips are also outside this exercise's test data.

## LLM and validation responsibilities

Use the LLM to extract meaning from the request. Application code must still:

- validate that model output is structurally valid;
- reject malformed JSON, arrays, missing keys required by your extraction schema, and wrong types;
- enforce semantic date, passenger, and budget constraints;
- derive final status and clarification behavior consistently.

The application, not the model, generates `request_id` and final status. Model-output failures are technical errors, not user clarifications. A bounded retry is optional; final failure must be clear.

Report provider and SQLite errors clearly, preserve useful context, and never turn a technical failure into an empty extraction or success record.

## Persistence

For every successfully processed request, save at least:

- the generated request ID;
- original input text;
- reference date;
- complete result;
- status;
- creation timestamp.

Retrieve records by ID after restart using the same SQLite file. Return clear not-found and write-failure outcomes.

## Provided evaluation data

`trip_request_parser/` contains public synthetic fixtures and standard-library utilities. Start with 28 core cases; 12 extended cases are optional if time remains. Extended coverage and a 100% score are not required.

The fixtures are examples of arbitrary in-scope input. Do not hard-code case IDs. `evaluate.py` is optional; a small adapter may export JSONL from any CLI, HTTP, or application interface. Expected question wording is illustrative and reviewed manually.

## Testing expectations

- Unit-test deterministic validation and persistence behavior.
- Mock the LLM in automated tests so they need no network or API cost.
- Include at least one documented example run against a real LLM.
- At minimum test normal and clarification results, validation, and retrieval from the same SQLite file with a fresh application instance.

Failure and persistence scenario files are supplemental references, not a requirement to implement every scenario or a prescribed adapter.

## Deliverables

Submit your implementation with a short README containing:

- setup and run instructions;
- your CLI or HTTP contract with example commands;
- how to configure the model and database;
- how to run tests and the supplied evaluator;
- one real-model example and its observed output;
- known limitations and unfinished work;
- brief AI-usage notes: tools used, what they helped with, and output you verified or changed.

Do not include API keys, populated personal databases, or real personal data.

## Review criteria

We evaluate this as an intern-level exercise, with emphasis on:

- correct and understandable behavior for the stated contract;
- sensible separation between LLM extraction and deterministic validation;
- safe error handling and SQLite persistence;
- focused, repeatable tests;
- readable code and practical documentation;
- clear trade-offs within the three-hour timebox.

Small, well-reasoned solutions are preferred. We do not expect production infrastructure, sophisticated prompt optimization, or perfect model accuracy.
