from __future__ import annotations

import http.client
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from support import LiveServer, write_test_data


class FlightSearchHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.data_dir = write_test_data(self.root)
        self.db_path = self.root / "http.sqlite3"

    @staticmethod
    def request(
        server: LiveServer,
        method: str,
        path: str,
        payload: Any = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | str]:
        connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
        body = None if payload is None else json.dumps(payload)
        request_headers = dict(headers or {})
        if payload is not None:
            request_headers.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        content_type = response.getheader("Content-Type", "")
        connection.close()
        decoded: dict[str, Any] | str
        if content_type.startswith("application/json"):
            decoded = json.loads(raw)
        else:
            decoded = raw.decode("utf-8")
        return response.status, decoded

    def search_path(self, as_of: str) -> str:
        return "/api/search?" + urlencode(
            {
                "origin": "LHR",
                "destination": "LIS",
                "date": "2027-02-12",
                "currency": "EUR",
                "as_of": as_of,
            }
        )

    def test_http_ui_catalog_scenarios_and_search(self) -> None:
        with LiveServer(self.db_path, self.data_dir) as server:
            status, health = self.request(server, "GET", "/health")
            self.assertEqual((200, {"status": "ok"}), (status, health))
            status, page = self.request(server, "GET", "/")
            self.assertEqual(200, status)
            self.assertIn("Independent scenarios require a fresh database", page)
            status, catalog = self.request(server, "GET", "/api/flights")
            self.assertEqual(200, status)
            self.assertEqual(2, len(catalog["flights"]))
            status, scenarios = self.request(server, "GET", "/api/scenarios")
            self.assertEqual(200, status)
            self.assertEqual({"availability", "duplicate-event"}, {s["scenario_id"] for s in scenarios["scenarios"]})
            status, search = self.request(server, "GET", self.search_path("2027-01-15T10:00:00Z"))
            self.assertEqual(200, status)
            self.assertEqual([22000], [result["total_price_minor"] for result in search["results"]])

    def test_replay_is_idempotent_conflicts_without_mutation_and_survives_restart(self) -> None:
        with LiveServer(self.db_path, self.data_dir) as server:
            request = {"scenario_id": "duplicate-event", "step": 0}
            status, inserted = self.request(server, "POST", "/api/replay", request)
            self.assertEqual(200, status)
            self.assertFalse(inserted["replayed"])
            status, duplicate = self.request(server, "POST", "/api/replay", request)
            self.assertEqual(200, status)
            self.assertTrue(duplicate["replayed"])
            status, conflict = self.request(
                server, "POST", "/api/replay", {"scenario_id": "duplicate-event", "step": 2}
            )
            self.assertEqual(409, status)
            self.assertEqual("replay_conflict", conflict["error"]["code"])

        with LiveServer(self.db_path, self.data_dir) as restarted:
            status, search = self.request(restarted, "GET", self.search_path("2027-01-15T10:13:00Z"))
            self.assertEqual(200, status)
            self.assertEqual(20000, search["results"][0]["total_price_minor"])
            self.assertEqual("evt_duplicate", search["results"][0]["event_id"])

    def test_replay_response_as_of_drives_latest_event_eligibility(self) -> None:
        with LiveServer(self.db_path, self.data_dir) as server:
            status, replay = self.request(
                server, "POST", "/api/replay", {"scenario_id": "availability", "step": 0}
            )
            self.assertEqual(200, status)
            status, sold_out = self.request(server, "GET", self.search_path(replay["as_of"]))
            self.assertEqual(200, status)
            self.assertEqual([], sold_out["results"])

    def test_invalid_routes_queries_and_bodies_return_json_errors(self) -> None:
        with LiveServer(self.db_path, self.data_dir) as server:
            cases = [
                ("GET", "/missing", None, 404),
                ("PUT", "/api/replay", None, 405),
                ("GET", "/api/search?origin=lhr", None, 400),
                ("GET", self.search_path("not-a-time"), None, 400),
                ("POST", "/api/replay", {"scenario_id": "../data", "step": 0}, 400),
                ("POST", "/api/replay", {"scenario_id": "not-present", "step": 0}, 404),
                ("POST", "/api/replay", {"scenario_id": "availability", "step": True}, 400),
            ]
            for method, path, payload, expected in cases:
                with self.subTest(method=method, path=path):
                    status, response = self.request(server, method, path, payload)
                    self.assertEqual(expected, status)
                    self.assertIn("error", response)

            connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=5)
            oversized = b"x" * (64 * 1024 + 1)
            connection.request(
                "POST",
                "/api/replay",
                body=oversized,
                headers={"Content-Type": "application/json", "Content-Length": str(len(oversized))},
            )
            response = connection.getresponse()
            response.read()
            connection.close()
            self.assertEqual(413, response.status)

    def test_early_post_rejections_do_not_pollute_the_next_request(self) -> None:
        with LiveServer(self.db_path, self.data_dir) as server:
            cases = [
                ("/api/replay", "text/plain", 400),
                ("/unknown", "application/json", 404),
                ("/api/replay?unexpected=1", "application/json", 400),
            ]
            for path, content_type, expected_status in cases:
                with self.subTest(path=path):
                    connection = http.client.HTTPConnection(
                        "127.0.0.1", server.port, timeout=5
                    )
                    connection.request(
                        "POST",
                        path,
                        body=b"{}",
                        headers={"Content-Type": content_type},
                    )
                    rejected = connection.getresponse()
                    rejected_payload = json.loads(rejected.read())
                    self.assertEqual(expected_status, rejected.status)
                    self.assertEqual("close", rejected.getheader("Connection"))
                    self.assertIn("error", rejected_payload)

                    # HTTPConnection transparently reconnects when the server
                    # correctly closes an early-rejected request with unread body.
                    connection.request("GET", "/health")
                    health = connection.getresponse()
                    health_payload = json.loads(health.read())
                    connection.close()
                    self.assertEqual(200, health.status)
                    self.assertEqual({"status": "ok"}, health_payload)


if __name__ == "__main__":
    unittest.main()
