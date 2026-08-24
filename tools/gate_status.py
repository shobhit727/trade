#!/usr/bin/env python3
"""Gate status at a glance — reusable daily check.

Usage:
    python3 tools/gate_status.py              # default ports 8081 8082
    python3 tools/gate_status.py 8081 8082 8083

Prints day counter, equity, breaker state, open positions and last fills
for every running gate bot. Exit code 0 if all healthy, 1 otherwise.
"""

from __future__ import annotations

import json
import sys
import urllib.request


def fetch(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=5) as r:
            return json.load(r)
    except Exception as exc:  # noqa: BLE001
        print(f"port {port}: DOWN ({exc})")
        return None


def show(port: int) -> bool:
    data = fetch(port)
    if data is None:
        return False
    gate = data.get("paper_gate", {})
    equity = data.get("equity", "?")
    pos = data.get("positions", {})
    print(
        f"port {port}: day {gate.get('days_elapsed', '?')}/{gate.get('required_days', '?')}"
        f" | equity {equity} | breaker {gate.get('breaker_tripped', False)}"
        f" | positions {len(pos)}"
    )
    for sym, p in pos.items():
        print(f"    {sym}: {p}")
    return True


def main() -> int:
    ports = [int(a) for a in sys.argv[1:]] or [8081, 8082]
    ok = all(show(p) for p in ports)
    print("ALL HEALTHY" if ok else "SOME BOTS DOWN")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
