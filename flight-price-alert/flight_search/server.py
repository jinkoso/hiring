"""Minimal local HTTP API for the flight search demo."""

from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .db import QuoteConflictError
from .service import FlightSearchService, NotFoundError, ValidationError


MAX_REQUEST_BODY = 64 * 1024
SEARCH_FIELDS = {"origin", "destination", "date", "currency", "as_of"}


class FlightSearchHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class RequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "FlightSearchDemo/1.0"

    def __init__(
        self,
        *args: Any,
        service: FlightSearchService,
        static_dir: Path,
        **kwargs: Any,
    ) -> None:
        self.service = service
        self.static_dir = static_dir
        super().__init__(*args, **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        # Keep the local demo quiet; callers and tests receive structured errors.
        return

    def _write_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, body: bytes) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        # Some errors are known before a POST body is consumed. Closing the
        # HTTP/1.1 connection prevents those unread bytes from becoming a
        # prefix of the next request on a persistent connection.
        self.close_connection = True
        self._write_json(status, {"error": {"code": code, "message": message}})

    def _query(self, query: str, allowed: set[str]) -> dict[str, str]:
        parsed = parse_qs(query, keep_blank_values=True, strict_parsing=False)
        unknown = sorted(set(parsed) - allowed)
        if unknown:
            raise ValidationError(f"unknown query parameter: {unknown[0]}")
        duplicated = sorted(key for key, values in parsed.items() if len(values) != 1)
        if duplicated:
            raise ValidationError(f"query parameter may appear once: {duplicated[0]}")
        return {key: values[0] for key, values in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        target = urlsplit(self.path)
        try:
            if target.path == "/":
                if target.query:
                    raise ValidationError("the UI route does not accept query parameters")
                self._write_html((self.static_dir / "index.html").read_bytes())
                return
            if target.path == "/health":
                if target.query:
                    raise ValidationError("health does not accept query parameters")
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return
            if target.path == "/api/flights":
                if target.query:
                    raise ValidationError("flights does not accept query parameters")
                self._write_json(HTTPStatus.OK, self.service.catalog())
                return
            if target.path == "/api/scenarios":
                if target.query:
                    raise ValidationError("scenarios does not accept query parameters")
                self._write_json(HTTPStatus.OK, self.service.scenarios())
                return
            if target.path == "/api/search":
                query = self._query(target.query, SEARCH_FIELDS)
                required = ("origin", "destination", "date", "currency")
                missing = [field for field in required if field not in query]
                if missing:
                    raise ValidationError(f"missing query parameter: {missing[0]}")
                self._write_json(
                    HTTPStatus.OK,
                    self.service.search(
                        origin=query["origin"],
                        destination=query["destination"],
                        travel_date=query["date"],
                        currency=query["currency"],
                        as_of=query.get("as_of"),
                    ),
                )
                return
            self._error(HTTPStatus.NOT_FOUND, "not_found", "route was not found")
        except ValidationError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
        except FileNotFoundError:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "server_error", "UI asset is missing")

    def _read_json_body(self) -> Any:
        content_type = self.headers.get_content_type()
        if content_type != "application/json":
            raise ValidationError("Content-Type must be application/json")
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValidationError("Content-Length is required")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValidationError("Content-Length must be an integer") from exc
        if length < 0:
            raise ValidationError("Content-Length must not be negative")
        if length > MAX_REQUEST_BODY:
            self.close_connection = True
            raise BodyTooLargeError("request body exceeds 65536 bytes")
        body = self.rfile.read(length)
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("request body must be valid JSON") from exc

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        target = urlsplit(self.path)
        try:
            if target.path != "/api/replay":
                self._error(HTTPStatus.NOT_FOUND, "not_found", "route was not found")
                return
            if target.query:
                raise ValidationError("replay does not accept query parameters")
            payload = self._read_json_body()
            if not isinstance(payload, dict):
                raise ValidationError("request body must be a JSON object")
            unknown = sorted(set(payload) - {"scenario_id", "step"})
            if unknown:
                raise ValidationError(f"unknown request field: {unknown[0]}")
            missing = [field for field in ("scenario_id", "step") if field not in payload]
            if missing:
                raise ValidationError(f"missing request field: {missing[0]}")
            result = self.service.replay(payload["scenario_id"], payload["step"])
            self._write_json(HTTPStatus.OK, result)
        except BodyTooLargeError as exc:
            self._error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", str(exc))
        except ValidationError as exc:
            self._error(HTTPStatus.BAD_REQUEST, "invalid_request", str(exc))
        except NotFoundError as exc:
            self._error(HTTPStatus.NOT_FOUND, "not_found", str(exc))
        except QuoteConflictError as exc:
            self._error(HTTPStatus.CONFLICT, "replay_conflict", str(exc))

    def _method_not_allowed(self) -> None:
        self._error(
            HTTPStatus.METHOD_NOT_ALLOWED,
            "method_not_allowed",
            "HTTP method is not supported for this route",
        )

    do_DELETE = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler API
    do_PATCH = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler API
    do_PUT = _method_not_allowed  # noqa: N815 - BaseHTTPRequestHandler API


class BodyTooLargeError(ValueError):
    pass


def build_server(
    service: FlightSearchService,
    host: str = "127.0.0.1",
    port: int = 8000,
    static_dir: Path | str | None = None,
) -> FlightSearchHTTPServer:
    assets = (
        Path(static_dir)
        if static_dir is not None
        else Path(__file__).resolve().parent.parent / "static"
    )
    handler = partial(RequestHandler, service=service, static_dir=assets)
    return FlightSearchHTTPServer((host, port), handler)
