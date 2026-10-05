#!/usr/bin/env python3
"""Daily Kite login: exchange request_token for an access_token.

Flow (every morning before market open — tokens expire ~06:00 IST):
  1. python3 tools/kite_login.py --login-url     -> prints the login URL
  2. open it in a browser, log in, copy the ?request_token=... from the
     redirect URL
  3. python3 tools/kite_login.py --request-token <TOKEN>

Reads KITE_API_KEY / KITE_API_SECRET from env (or .env). Writes
state-nse/kite_session.json which KiteVenue picks up automatically.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def load_env() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login-url", action="store_true")
    ap.add_argument("--request-token", default=None)
    args = ap.parse_args()

    load_env()
    api_key = os.environ.get("KITE_API_KEY", "")
    if not api_key:
        print("KITE_API_KEY missing (.env or env)")
        return 1

    sys.path.insert(0, "src")
    from cryptobot.execution.venue.kite_venue import KiteSession

    session = KiteSession(api_key=api_key,
                          api_secret=os.environ.get("KITE_API_SECRET", ""))
    if args.login_url or not args.request_token:
        print("1. open:", session.login_url())
        print("2. log in; copy request_token from the redirect URL")
        print("3. run: tools/kite_login.py --request-token <TOKEN>")
        return 0

    token = session.exchange_token(args.request_token)
    print(f"access_token stored ({token[:6]}...) -> {session.session_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
