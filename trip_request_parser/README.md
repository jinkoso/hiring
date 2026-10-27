# Trip Request Parser evaluation data

This directory accompanies [`trip_request_parser.md`](../trip_request_parser.md).
It contains public, synthetic examples and standard-library utilities. It does
not contain an applicant solution, hidden scoring data, personal information, or
a claim about live-model quality.

The assignment is to support arbitrary in-scope requests under the documented
contract. These fixtures are examples; do not branch on `case_id` or memorize
their outputs.

## Files

- `data/cases.json` contains 40 natural-language examples: 28 `core` and 12
  `extended`.
- `data/failure_cases.json` contains 10 optional, reproducible technical-failure
  scenarios for mocked input, provider, model-output, and SQLite behavior.
- `data/persistence_scenarios.json` contains 5 language-independent SQLite
  scenarios.
- `validate_fixtures.py` checks the public data's structure and invariants.
- `evaluate.py` optionally compares exported candidate results with the public
  natural-language cases.
- `tests/test_dataset_tools.py` verifies that the data is valid and that the
  evaluator rejects representative false positives.

All utilities use only the Python standard library and make no network calls.

## Recommended scope

Implement the interface, genuine LLM extraction, deterministic application
validation, and SQLite save/retrieve behavior first. Use the `core` examples as
the baseline. `extended` is optional if time remains; incomplete extended
coverage is not a hard failure and candidates are not expected to reach 100%.

At minimum, candidate tests should cover a normal request, a clarification
request, deterministic validation, and retrieval from the same SQLite file
after a fresh application instance is created. Mock the LLM for repeatability
and document one real-model example. The supporting failure and persistence
files are additional design/testing references, not a requirement to implement
every listed scenario or adopt a particular test adapter.

## `cases.json` format

The root records `format_version`, a description, declared tier counts, and a
`cases` array. Every case contains:

- `id`: stable public fixture ID;
- `tier`: `core` or `extended`;
- `category`: descriptive coverage label;
- `input`: the assignment's `text` and `reference_date` input;
- `expected`: all output fields except dynamic `request_id`;
- `clarification_fields`: metadata naming unresolved business fields;
- `reason`: short explanation of the expectation;
- optional `date_offset_days`: independently checked relative-date metadata.

`clarification_fields` is fixture metadata, not part of the candidate output.
Expected question wording is illustrative and is never compared literally.

The location policy is intentionally narrow: preserve supplied labels after
trimming. Comparison ignores surrounding whitespace and letter case only. It
does not resolve airports, expand abbreviations, or compare aliases; for
example, `nyc` and `NYC` compare equal, while `nyc` and `New York City` do not.

## Validate the supplied data

From the repository root:

```sh
python3 trip_request_parser/validate_fixtures.py
python3 -m unittest discover -s trip_request_parser/tests -v
```

Validation checks unique IDs, exact declared counts, required keys, JSON types,
finite positive numeric values, date validity, status/clarification consistency,
and all declared relative-date calculations.

## Optional evaluator

`evaluate.py` is a convenience, not a required application interface. A
candidate may write a small one-off adapter that invokes their CLI, HTTP route,
or application function and exports one JSON object per line:

```json
{"case_id":"c001","result":{"request_id":"any-generated-id","status":"ready","origin":"New York","destination":"Paris","departure_date":"2027-05-10","passengers":2,"budget_per_person":{"amount":1200,"currency":"USD"},"clarification_questions":[]}}
```

Run it with:

```sh
python3 trip_request_parser/evaluate.py predictions.jsonl --tier core
python3 trip_request_parser/evaluate.py predictions.jsonl --tier extended
python3 trip_request_parser/evaluate.py predictions.jsonl --tier all
```

The selected tier must have exactly one prediction for every selected case.
Predictions for known, unselected cases are ignored. Unknown or duplicate IDs,
missing selected IDs, malformed JSON, missing output keys, wrong types,
non-finite numbers, and unexpected fields are errors.

Within `result`, every output-contract field is required. `request_id` is the
only optional extra field and its value is ignored after checking that it is a
non-empty string or positive integer. This supports UUID-style and SQLite-style
IDs while still detecting accidentally omitted nullable fields.

The evaluator compares:

- `origin` and `destination` after `strip()` plus Unicode `casefold()`;
- `status`, date, passengers, and currency exactly;
- budget amounts by numeric equality, so `1200` and `1200.0` are equal;
- clarification arrays by status and non-empty trimmed-string shape, without
  comparing example wording.

Clarification specificity and usefulness still require manual review. A passing
public-fixture score is supporting evidence, not a substitute for code review,
candidate-authored tests, a real-model example, or evaluation on arbitrary
equivalent inputs.

## Supporting scenario formats

`failure_cases.json` separates invalid interface input, provider failures,
structurally invalid model output, and persistence failures. Each scenario gives
concrete input, mock response/error data where relevant, and observable expected
behavior. These are integration ideas and do not prescribe exception classes,
mock libraries, retry rules, or an adapter API.

`persistence_scenarios.json` describes setup steps and checks in plain language.
SQLite schema design, serialization choices, timestamps, and CLI/HTTP response
details remain part of the candidate's implementation.
