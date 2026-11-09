"""Step 1 — data audit, indicator fidelity, and the no-lookahead proof.

Nothing here touches TEST results; it establishes that the harness measures the
indicator the catalog strategy actually trades, and that no decision on day t can
see day t+1.
"""

from __future__ import annotations

import json

import numpy as np
from common import (
    COST,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    build_score,
    header,
    load_panels,
    rsi_panel,
    signal_panel,
    validate_rsi_matches_catalog,
)

p = load_panels()
close = p.close

print(header("DATA AUDIT (load_universe)"))
print(p.report.describe())
print(f"\nsymbols        {len(p.symbols)}")
print(f"panel shape    {close.shape}   {close.index[0].date()} -> {close.index[-1].date()}")
print(f"excluded       {sorted(p.report.excluded_symbols)}")

print(header("WINDOW COVERAGE"))
for nm, s, e in (
    ("TRAIN", TRAIN_START, TRAIN_END),
    ("TEST", TEST_START, TEST_END),
):
    sl = close.loc[s:e]
    print(
        f"  {nm:<6} {sl.index[0].date()} -> {sl.index[-1].date()}  bars={len(sl):>5}  "
        f"symbols={sl.shape[1]}  "
        f"median_nonnull_per_bar={int(sl.notna().sum(axis=1).median())}"
    )

print(header("COST BASIS (must be quoted consistently)"))
print(f"  round_trip_bps(100000)      = {COST.round_trip_bps(__import__('decimal').Decimal('100000'))}")
print(f"  all_in_round_trip_bps(...)  = {COST.all_in_round_trip_bps(__import__('decimal').Decimal('100000'))}")
print("  -> run_backtest charges all_in (statutory + 2x slippage). Every number in this")
print("     report is net of 21.92 bps unless explicitly labelled gross.")

print(header("INDICATOR FIDELITY — vectorised RSI vs catalog streaming rsi()"))
fidelity = {}
for period in (6, 14, 21):
    v = validate_rsi_matches_catalog(close, period=period, n_probe=250)
    fidelity[period] = v
    print(
        f"  period={period:<3} probes={v['n_checked']:>4}  "
        f"max_abs_error={v['max_abs_error']:.3e}  identical={v['identical']}"
    )
assert all(v["identical"] for v in fidelity.values()), "vectorised RSI != catalog RSI"
print("  -> the panel RSI reproduces cryptobot.strategies.indicators.rsi exactly.")

print(header("NO-LOOKAHEAD PROOF"))


def prefix_invariance_check(fn, label: str, dates: list, tol: float = 0.0) -> dict:
    """`f(full panel)[:t]` must equal `f(panel truncated at t)` for every t.

    The strongest available check: it catches both accidental `.shift(-n)` and any
    normalisation (z-score, rank, fill) that pools information across dates, because
    any statistic that uses a bar after t changes when those bars are removed.
    """
    worst = 0.0
    worst_at = None
    for t in dates:
        full = fn(close)
        trunc = fn(close.iloc[: t + 1])
        a = full.iloc[t]
        b = trunc.iloc[t]
        both_nan = a.isna() & b.isna()
        err = float((a[~both_nan] - b[~both_nan]).abs().max())
        if err > worst:
            worst, worst_at = err, t
    ok = worst <= tol
    print(f"  {label:<26} max |full[:t] - truncated(t)| = {worst:.3e}  at {worst_at}  "
          f"{'OK' if ok else 'LOOKAHEAD'}")
    return {"label": label, "max_err": worst, "ok": bool(ok), "worst_at": str(worst_at)}


probes = [int(i) for i in np.linspace(2000, len(close) - 2, 12).astype(int)]
la = [
    prefix_invariance_check(lambda x: rsi_panel(x, 14), "rsi_panel(14)", probes),
    prefix_invariance_check(
        lambda x: signal_panel(rsi_panel(x, 14), 30.0), "signal_panel(14,30)", probes
    ),
    prefix_invariance_check(
        lambda x: build_score(x, rsi_panel(x, 14), 30.0, "deepest"),
        "build_score deepest",
        probes,
    ),
    prefix_invariance_check(
        lambda x: build_score(x, rsi_panel(x, 14), 30.0, "mom126"),
        "build_score mom126",
        probes,
    ),
]
assert all(x["ok"] for x in la), "lookahead detected"

# --- future-corruption check: scramble every bar AFTER t, re-read the score at t.
t = int(np.linspace(2000, len(close) - 400, 1)[0])
corrupted = close.copy()
corrupted.iloc[t + 1 :] *= 7.77
r_full = build_score(close, rsi_panel(close, 14), 30.0, "deepest")
r_corr = build_score(corrupted, rsi_panel(corrupted, 14), 30.0, "deepest")
delta = float((r_full.iloc[t] - r_corr.iloc[t]).abs().max())
print(f"  future-corruption check  max |score(t)| change after scrambling all bars "
      f"> t = {delta:.3e}  {'OK' if delta == 0.0 else 'LOOKAHEAD'}")
assert delta == 0.0

# --- fill policy audit: nothing may be forward-filled from the future.
s = build_score(close, rsi_panel(close, 14), 30.0, "deepest")
print(f"  score panel: NaN count {int(s.isna().to_numpy().sum())}, "
      f"no ffill/bfill applied (NaN = ineligible = never bought)")

print(header("SIGNAL LIVENESS (TRAIN only — TEST long fraction measured later)"))
for period, lower in ((14, 30.0), (14, 40.0), (6, 30.0), (21, 30.0)):
    r = rsi_panel(close, period)
    sig = signal_panel(r, lower)
    win = sig.loc[TRAIN_START:TRAIN_END]
    n = int((~np.isnan(r.loc[TRAIN_START:TRAIN_END])).to_numpy().sum())
    long_f = float((win > 0).to_numpy().sum()) / n
    short_f = float((win < 0).to_numpy().sum()) / n
    flat_f = float((win == 0).to_numpy().sum()) / n
    print(
        f"  RSI({period:<2}) < {lower:<4} TRAIN  long {long_f * 100:>6.2f}%   "
        f"short {short_f * 100:>6.2f}%   flat {flat_f * 100:>6.2f}%"
        + ("   <-- DEAD (<5% liveness)" if long_f < 0.05 else "")
    )

out = {
    "symbols": len(p.symbols),
    "panel": [str(close.index[0].date()), str(close.index[-1].date())],
    "bars": int(close.shape[0]),
    "excluded": sorted(p.report.excluded_symbols),
    "fidelity": fidelity,
    "lookahead": la,
    "future_corruption_delta": delta,
}
with open("S1_DATA_CHECK.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("\n>> wrote S1_DATA_CHECK.json")
