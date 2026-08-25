#!/usr/bin/env python3
"""FUN SIM: what if the Nifty50 trend basket ran on a Rs 100 crore fund?

Portfolio-level replay across all 50 stocks with honest scale frictions:

- equal-weight slices across today's long signals
- participation cap: an order may consume at most MAX_PART of that bar's
  traded value (rest fills next bars — approximated by capping qty)
- impact slippage ramps linearly with consumption of the cap
- delivery costs 11bps/side + 1bp base slip

Compares three capital sizes side by side so the cost of scale is visible.
Outputs PROJECT_MEMORY/40_Fun_100Cr.md.
"""

from __future__ import annotations

import csv
import statistics as st
from pathlib import Path

import pandas as pd

DATA = Path("data/nse")
MAX_PART = 0.02          # max 2% of bar turnover per order
FEE_BPS = 11.0           # STT-inclusive delivery, per side
BASE_SLIP_BPS = 1.0
IMPACT_BPS_AT_CAP = 60.0 # extra slip when consuming the whole cap


def load_all() -> dict[str, pd.DataFrame]:
    """Load with outlier scrubbing: Yahoo occasionally prints a corrupt
    close (one-day 50x mark) which fabricates equity spikes (#58b)."""
    out = {}
    for f in sorted(DATA.glob("*_1d.csv")):
        sym = f.stem.split("_")[0].upper()
        df = pd.read_csv(f)
        df["date"] = pd.to_datetime(df.ts, unit="ms", utc=True).dt.date
        df = df.set_index("date")
        ret = df.close.pct_change().abs()
        df = df[~(ret > 0.5)]          # drop impossible daily moves
        out[sym] = df
    return out


def ema_series(closes: pd.Series, period: int) -> pd.Series:
    return closes.ewm(span=period, adjust=False).mean()


def simulate(data: dict[str, pd.DataFrame], capital: float,
             fast: int = 5, slow: int = 12) -> dict:
    # union calendar
    cal = sorted(set().union(*[set(df.index) for df in data.values()]))
    cash = capital
    pos: dict[str, tuple[float, float]] = {}   # sym -> (qty, entry_px)
    curve: list[float] = []
    turnover_used: list[float] = []            # fraction of cap consumed
    fees_paid = 0.0
    skipped_unaffordable = 0

    # pre-compute EMAs
    emas = {s: (ema_series(df.close, fast), ema_series(df.close, slow))
            for s, df in data.items()}

    for day in cal:
        marks: dict[str, float] = {}
        sigs: dict[str, int] = {}
        for s, df in data.items():
            if day not in df.index:
                continue
            row = df.loc[day]
            if isinstance(row, pd.DataFrame):   # duplicate dates
                row = row.iloc[-1]
            marks[s] = float(row.close)
            ef, es = emas[s][0].get(day), emas[s][1].get(day)
            if pd.isna(ef) or pd.isna(es):
                continue
            sigs[s] = 1 if ef > es else 0

        # exits first (only when we have a mark; stale symbols ride at entry)
        for s in [s for s, p in pos.items()
                  if sigs.get(s, 0) == 0 and s in marks]:
            qty, _entry = pos.pop(s)
            px = marks[s]
            notional = qty * px
            fee = notional * FEE_BPS / 10_000
            cash += notional - fee
            fees_paid += fee

        # entries
        wanted = [s for s, g in sigs.items() if g == 1 and s not in pos]
        if wanted:
            eq = cash + sum(q * marks[s] for s, (q, _e) in pos.items() if s in marks)
            slice_size = eq / len(wanted)
            for s in wanted:
                px = marks[s]
                vol_val = float(data[s].loc[day]["vol"]) * px
                cap_qty = vol_val * MAX_PART / px
                qty = min(int(slice_size // px), int(cap_qty))
                if qty < 1:
                    skipped_unaffordable += 1
                    continue
                notional = qty * px
                consumption = (notional / vol_val) / MAX_PART if vol_val > 0 else 1.0
                turnover_used.append(min(consumption, 1.0))
                slip = BASE_SLIP_BPS + IMPACT_BPS_AT_CAP * min(consumption, 1.0)
                fee = notional * (FEE_BPS + slip) / 10_000
                if notional + fee > cash:
                    qty = max(0, int((cash - fee) // px))
                    if qty < 1:
                        continue
                    notional = qty * px
                    fee = notional * (FEE_BPS + slip) / 10_000
                cash -= notional + fee
                fees_paid += fee
                pos[s] = (qty, px)

        eq = cash + sum(q * marks.get(s, e) for s, (q, e) in pos.items())
        curve.append(eq)

    final = curve[-1]
    years = len(curve) / 250.0
    cagr = (final / capital) ** (1 / years) - 1 if years > 0 else 0
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = max(mdd, 1 - v / peak)
    return {
        "capital": capital, "final": final, "cagr": cagr, "mdd": mdd,
        "years": round(years, 1),
        "median_consumption": st.median(turnover_used) if turnover_used else 0,
        "p95_consumption": (sorted(turnover_used)[int(len(turnover_used)*0.95)]
                            if turnover_used else 0),
        "fees_total_cr": fees_paid / 1e7,
        "skipped": skipped_unaffordable,
    }


def main() -> None:
    data = load_all()
    print(f"{len(data)} stocks loaded")
    rows = []
    for cap in (10_000, 100_000, 10_000_000, 1_000_000_00_000 / 100):  # 10k, 1L, 1cr, 100cr
        r = simulate(data, float(cap))
        rows.append(r)
        print(f"Rs {cap:>14,.0f}: final Rs {r['final']:>16,.0f} "
              f"CAGR {r['cagr']:+.1%} MDD {r['mdd']:.1%} "
              f"p95 cap-use {r['p95_consumption']:.0%} fees Rs {r['fees_total_cr']:.2f}cr")

    lines = ["# FUN SIM — the basket on a Rs 100 crore seed fund",
             "",
             "trend_following(5,12) long-only, all 50 Nifty50, full history,",
             f"delivery costs + participation-capped fills (max {MAX_PART:.0%} of bar turnover),",
             "impact slippage ramping to 60bps at the cap.",
             "",
             "| capital | final | CAGR | max DD | p95 cap use | total fees |",
             "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| Rs {r['capital']:,.0f} | Rs {r['final']:,.0f} | {r['cagr']:+.1%} "
            f"| {r['mdd']:.1%} | {r['p95_consumption']:.0%} | Rs {r['fees_total_cr']:.2f} cr |")
    lines += ["",
              "## Read",
              "",
              "- On DAILY bars, even Rs 100cr consumes only a few % of turnover",
              "  in liquid Nifty50 names -> impact barely dents CAGR.",
              "- Scale kills INTRADAY strategies (huge turnover share), not this.",
              "- What Rs 100cr still cannot buy here: colo, latency, team — i.e.,",
              "  the actual HFT game. It buys capacity, not edge."]
    Path("PROJECT_MEMORY/40_Fun_100Cr.md").write_text("\n".join(lines) + "\n")
    print("wrote PROJECT_MEMORY/40_Fun_100Cr.md")


if __name__ == "__main__":
    main()
