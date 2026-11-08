"""Local research API server entrypoint."""

from __future__ import annotations

import argparse
import os
from ipaddress import ip_address
from pathlib import Path
from wsgiref.simple_server import make_server

from .api import create_app


def main(argv: list[str] | None = None) -> None:
    """Run the dashboard/API on loopback unless remote exposure is explicitly enabled."""
    # Store experiment metadata separately from existing account and bot databases.
    parser = argparse.ArgumentParser(description="Run the local quantitative research dashboard.")
    parser.add_argument("--host", default=os.getenv("RESEARCH_API_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("RESEARCH_API_PORT", "8765")))
    parser.add_argument(
        "--database",
        default=os.getenv("RESEARCH_DB", "data/research/experiments.sqlite3"),
    )
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args(argv)

    # Unauthenticated experiment metadata endpoints must not bind publicly by accident.
    host_is_loopback = args.host == "localhost"
    try:
        host_is_loopback = host_is_loopback or ip_address(args.host).is_loopback
    except ValueError:
        host_is_loopback = False
    if not host_is_loopback and not args.allow_remote:
        parser.error("non-loopback host requires --allow-remote; configure authentication first")
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    database = Path(args.database)
    database.parent.mkdir(parents=True, exist_ok=True)
    application = create_app(str(database))
    # The standard-library WSGI server keeps the runtime dependency surface minimal.
    with make_server(args.host, args.port, application) as server:
        print(f"Research dashboard/API listening at http://{args.host}:{args.port}")
        server.serve_forever()


if __name__ == "__main__":
    # Support python -m research.platform.app.
    main()
