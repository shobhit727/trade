#!/usr/bin/env python3
"""Unified live dashboard — everything, one page, auto-refreshing.

Aggregates:
- every gate bot's /health (equity, day counter, positions, last fills)
- latest research artifacts (sweep/WF/mid-freq results in PROJECT_MEMORY)

Serves on :8090 (read-only; no credentials). Stdlib only.
"""

from __future__ import annotations

import json
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import os
# Targets as "host:port" pairs. Inside compose we use service DNS names and
# container ports; standalone host runs can pass localhost published ports.
TARGETS = [
    tuple(t.split(":")) for t in os.environ.get(
        "ROOM_TARGETS",
        "localhost:8081,localhost:8082,localhost:8083,localhost:8084",
    ).split(",")
]
RESEARCH_FILES = [
    "PROJECT_MEMORY/38_NSE_MidFreq_Results.md",
    "PROJECT_MEMORY/37_NSE_All_Timeframes.md",
    "PROJECT_MEMORY/36_NSE_Pivot.md",
    "PROJECT_MEMORY/35_2026_Validation.md",
]
CACHE: dict = {"bots": [], "ts": 0.0}


def fetch_bot(target: tuple[str, str]) -> dict | None:
    host, port = target
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=4) as r:
            d = json.load(r)
        d["_port"] = int(port)
        return d
    except Exception as exc:  # noqa: BLE001
        return {"_port": int(port), "status": "DOWN", "error": str(exc)[:60]}


def bots_snapshot() -> list[dict]:
    if time.time() - CACHE["ts"] > 3.0:
        CACHE["bots"] = [fetch_bot(tg) for tg in TARGETS]
        CACHE["ts"] = time.time()
    return CACHE["bots"]


def render() -> str:
    cards = []
    for b in bots_snapshot():
        port = b.get("_port")
        if b.get("status") == "DOWN":
            cards.append(f"<div class='card down'><h2>:{port} DOWN</h2><p>{b.get('error','')}</p></div>")
            continue
        gate = b.get("paper_gate", {})
        pos = b.get("positions", {})
        trades = b.get("recent_trades", [])[-6:]
        equity = float(b.get("equity", 0) or 0)
        pnl = equity - 10000
        pnl_cls = "pos" if pnl >= 0 else "neg"
        trade_rows = "".join(
            f"<tr><td>{t.get('time','')[-8:]}</td><td>{t.get('side','')}</td>"
            f"<td>{t.get('qty','')} @ {t.get('price','')}</td></tr>"
            for t in reversed(trades)) or "<tr><td colspan=3>no fills yet</td></tr>"
        pos_rows = "".join(
            f"<tr><td>{s}</td><td>{p}</td></tr>" for s, p in pos.items()
        ) or "<tr><td colspan=2>flat</td></tr>"
        cards.append(f"""
<div class='card'>
  <h2>:{port} {b.get('symbol','?')} · {b.get('strategy','?')} · {b.get('timeframe','?')}</h2>
  <div class='big'>₹{equity:,.0f} <span class='{pnl_cls}'>({pnl:+,.0f})</span></div>
  <p>gate day {gate.get('days_elapsed','?')} · breaker {gate.get('breaker_tripped', False)}
     · bars {b.get('bars_fed',0)} · orders {b.get('orders_submitted',0)} · fills {b.get('fills',0)}</p>
  <table><tr><th>position</th></tr>{pos_rows}</table>
  <table><tr><th>time</th><th>side</th><th>fill</th></tr>{trade_rows}</table>
</div>""")

    research = ""
    for f in RESEARCH_FILES:
        p = Path(f)
        if not p.exists():
            continue
        body = p.read_text(encoding="utf-8")
        # crude md → html: tables + headers + paragraphs
        lines = body.splitlines()
        out, in_tbl = [], False
        for ln in lines:
            if ln.startswith("|"):
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if set("".join(cells)) <= set("-: "):
                    continue
                if not in_tbl:
                    out.append("<table>"); in_tbl = True
                tag = "th" if not any(t in ("ret", "sharpe", "wins") for t in cells[:2]) or out[-1].endswith("<table>") else "td"
                out.append("<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>")
            else:
                if in_tbl:
                    out.append("</table>"); in_tbl = False
                if ln.startswith("#"):
                    out.append(f"<h3>{ln.lstrip('# ')}</h3>")
                elif ln.strip():
                    out.append(f"<p>{ln}</p>")
        if in_tbl:
            out.append("</table>")
        research += f"<section><h2>{p.name}</h2>{''.join(out)}</section>"

    return f"""<!doctype html><html><head><meta charset=utf-8>
<title>cryptobot — live control room</title>
<meta http-equiv=refresh content="5">
<style>
body{{background:#0d1117;color:#e6edf3;font-family:ui-monospace,monospace;margin:20px}}
h1{{color:#58a6ff}} h2{{font-size:15px;color:#8b949e}} h3{{font-size:13px;color:#79c0ff}}
.card{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin:10px 0}}
.down{{border-color:#f85149}}
.big{{font-size:26px;font-weight:700}}
.pos{{color:#3fb950}} .neg{{color:#f85149}}
table{{border-collapse:collapse;width:100%;margin:8px 0;font-size:12px}}
td,th{{border-bottom:1px solid #21262d;padding:3px 6px;text-align:left}}
th{{color:#8b949e}}
section{{background:#161b22;border:1px solid #30363d;border-radius:10px;padding:14px;margin:16px 0;max-height:420px;overflow:auto}}
</style></head><body>
<h1>◉ cryptobot control room <small style=color:#8b949e>auto-refresh 5s</small></h1>
{''.join(cards)}
{research}
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/bots":
            body = json.dumps(bots_snapshot()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        body = render().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


if __name__ == "__main__":
    print("control room on http://localhost:8090/dashboard")
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
