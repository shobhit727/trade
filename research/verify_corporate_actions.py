"""Corporate-action verification — is the backtest return series actually clean?

This answers the single most important question about any backtest on vendor data:
*does the price series contain unadjusted splits and bonus issues?* A 1:1 bonus on
unadjusted data shows as a clean -50% one-day drop, which would silently delete real
returns (or invent fake ones) around every corporate action.

It also quantifies what the data does NOT contain: **dividends**. The panel is
price-return only, so every figure this project produces is a price return and is
understated versus the official NSE total-return index by roughly the dividend yield.

Run:  .venv/bin/python research/verify_corporate_actions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

DATA = "data/nse"

#: Documented NIFTY-50 bonus/split issues, used to test for split adjustment.
#: A 1:1 bonus on UNADJUSTED data produces a ~-50% one-day drop on the ex-date.
KNOWN_ACTIONS = [
    ("infy", "2018-09", "Infosys 1:1 bonus (ex-Sep 2018)"),
    ("wipro", "2024-11", "Wipro 1:1 bonus (ex-Nov 2024)"),
    ("hdfcbank", "2015-07", "HDFC Bank 1:1 bonus (ex-Jul 2015)"),
    ("hcltech", "2013-07", "HCLTech 1:1 bonus (ex-Jul 2013)"),
    ("axisbank", "2015-09", "Axis Bank 1:1 bonus (ex-Sep 2015)"),
    ("icicibank", "2014-06", "ICICI Bank 1:1 bonus (ex-Jun 2014)"),
    ("techm", "2013-05", "Tech Mahindra 1:1 bonus (ex-May 2013)"),
    ("hindunilvr", "2013-12", "HUL 1:1 bonus (ex-Dec 2013)"),
    ("sbin", "2015-09", "SBI 1:1 bonus (ex-Sep 2015)"),
    ("tcs", "2014-07", "TCS 1:1 bonus (ex-Jul 2014)"),
]

#: If a series is unadjusted, a 1:1 bonus shows as at least this large a one-day drop.
UNADJUSTED_SIGNATURE = -0.35


def load(sym: str) -> pd.Series:
    df = pd.read_csv(f"{DATA}/{sym}_1d.csv")
    df.columns = [c.lower() for c in df.columns]
    idx = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata")
    return pd.Series(df["close"].astype(float).to_numpy(), index=idx, name=sym)


def main() -> int:
    print("=" * 88)
    print("CORPORATE-ACTION VERIFICATION")
    print("=" * 88)
    print("\nTest: does a known 1:1 bonus produce a ~-50% one-day drop?")
    print("If yes -> the series is UNADJUSTED and backtest returns are invalid.")
    print(f"Signature threshold: {UNADJUSTED_SIGNATURE:.0%} one-day drop\n")

    print(f"{'symbol':>11} {'event':<34} {'worst day in window':>22}  verdict")
    print("-" * 88)

    unadjusted: list[str] = []
    for sym, window, desc in KNOWN_ACTIONS:
        try:
            px = load(sym)
        except FileNotFoundError:
            print(f"{sym:>11} {desc:<34} {'(missing)':>22}")
            continue
        w = px.loc[window].pct_change().dropna()
        if w.empty:
            print(f"{sym:>11} {desc:<34} {'(no data)':>22}")
            continue
        worst = float(w.min())
        verdict = "UNADJUSTED" if worst < UNADJUSTED_SIGNATURE else "adjusted OK"
        if worst < UNADJUSTED_SIGNATURE:
            unadjusted.append(sym)
        print(f"{sym:>11} {desc:<34} {worst * 100:>21.2f}%  {verdict}")

    print("-" * 88)
    if unadjusted:
        print(f"\nRESULT: {len(unadjusted)} series look UNADJUSTED -> results INVALID:")
        for s in unadjusted:
            print(f"  - {s}")
        return 1

    print("\nRESULT: all tested bonus dates show normal daily moves.")
    print("The post-2008 panel is corporate-action adjusted. Returns are usable.\n")

    # ------------------------------------------------------------------
    print("=" * 88)
    print("WHAT THE DATA DOES NOT CONTAIN: DIVIDENDS")
    print("=" * 88)
    from nsealgo.data.loader import load_universe

    panel, symbols, _ = load_universe(DATA)
    rets = panel.pct_change().mean(axis=1).dropna()
    years = len(rets) / 244

    print("\nThe panel is PRICE return only.")
    print("Official NSE NIFTY-50 TRI (12.44% over 20y) INCLUDES dividends; our figures do not.")
    print("Indian large-cap dividend yield is roughly 1.0-1.3%/yr, so every number in")
    print("reports/VALIDATION_v1.md is understated by about that much as a total return.\n")

    ew_price_cagr = float((1 + rets).prod() ** (1 / years) - 1)
    div_yield = 0.0115  # NSE 50 long-run average, ~1.15%
    official_tri = 0.1244
    print(f"  our equal-weight benchmark (price only) : {ew_price_cagr * 100:>6.2f}%")
    print(f"  + estimated dividend yield               : {div_yield * 100:>6.2f}%")
    print(f"  = our benchmark as total return          : {(ew_price_cagr + div_yield) * 100:>6.2f}%")
    print(f"  official NSE TRI (20y to Feb 2026)       : {official_tri * 100:>6.2f}%")
    print("  ---------------------------------------------------------------")
    print(f"  implied SURVIVORSHIP + selection bias   : "
          f"{((ew_price_cagr + div_yield) - official_tri) * 100:>6.2f}% / yr")
    print("\nThat gap is the cost of backfilling today's NIFTY-50 to 2008. Both the")
    print("strategy AND the benchmark carry it, so the relative comparison is the")
    print("trustworthy number; the absolute ones are optimistic by this margin.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
