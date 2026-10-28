"""Command-line entry point for the offline flight search demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .server import build_server
from .service import FlightSearchService


DEFAULT_DB = Path("data/local.sqlite3")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the offline flight search demo")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init-db", help="create the database and load seed quotes")
    init.add_argument("--db", type=Path, default=DEFAULT_DB)
    init.add_argument("--data-dir", type=Path, default=None)

    serve = subcommands.add_parser("serve", help="start the local HTTP server")
    serve.add_argument("--db", type=Path, default=DEFAULT_DB)
    serve.add_argument("--data-dir", type=Path, default=None)
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    replay = subcommands.add_parser("replay", help="apply one fixture scenario step")
    replay.add_argument("--db", type=Path, default=DEFAULT_DB)
    replay.add_argument("--data-dir", type=Path, default=None)
    replay.add_argument("--scenario", required=True)
    replay.add_argument("--step", required=True, type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    service = FlightSearchService(args.db, args.data_dir)
    service.initialize()
    if args.command == "init-db":
        print(f"Initialized {args.db}")
        return 0
    if args.command == "replay":
        print(json.dumps(service.replay(args.scenario, args.step), indent=2, sort_keys=True))
        return 0

    server = build_server(service, host=args.host, port=args.port)
    host, port = server.server_address
    print(f"Flight search listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
