"""Verify the Supertrend port before any backtest is run.

Three things are checked, because a vectorised band recursion is exactly the kind of
thing that quietly develops a look-ahead:

1. **Prefix invariance** (the no-look-ahead test). If the signal on bars 1..k is a pure
   function of bars 1..k, then computing on a truncated series must reproduce the same
   values. A one-bar peek anywhere in the recursion breaks this. Tested at several
   truncation points on several symbols.
2. **An independent stateful re-implementation.** The panel version is a flat loop over
   rows; the checker is a small recursive function written the other way up (explicit
   carried state, Wilder-style naming) so a shared typo would have to be made twice in
   two different styles to escape.
3. **ATR definition parity** with `cryptobot.strategies.indicators.atr`, which is the
   reference implementation the crypto engine actually uses.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from common import (  # noqa: E402
    as_shipped_signal,
    load_ohlc,
    supertrend_signal,
    true_range,
)

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2] / "src"))
from cryptobot.strategies.indicators import atr as crypto_atr  # noqa: E402

# --------------------------------------------------------------------------- #


def _st_one_symbol(c, h, low_, tr, period, mult):
    """Independent, explicitly stateful re-implementation of the same recursion."""
    n = len(c)
    out = np.full(n, np.nan)
    final_upper = None
    final_lower = None
    uptrend = False
    for i in range(n):
        if i + 1 < period + 1:  # crypto `atr` needs period+1 closes to be defined
            continue
        # --- SMA of TR over the last `period` bars (repo convention, not Wilder)
        a = float(np.mean(tr[i - period + 1: i + 1]))
        if not np.isfinite(a):
            continue
        midline = 0.5 * (h[i] + low_[i])
        raw_up = midline + mult * a
        raw_dn = midline - mult * a
        if final_upper is None:
            final_upper, final_lower = raw_up, raw_dn
            uptrend = bool(c[i] >= final_upper)
        else:
            if raw_up < final_upper or c[i - 1] > final_upper:
                final_upper = raw_up
            if raw_dn > final_lower or c[i - 1] < final_lower:
                final_lower = raw_dn
            if uptrend:
                if c[i] <= final_lower:
                    uptrend = False
            elif c[i] >= final_upper:
                uptrend = True
        out[i] = 1.0 if uptrend else -1.0
    return out


def _count_disagreements(a: pd.DataFrame, b: pd.DataFrame) -> int:
    """Compare two panels only where BOTH have a value.

    NaN != NaN is True, so the obvious `(a != b).sum()` counts every *absent* cell as a
    disagreement — which is how the first version of this check reported ~9,000 false
    mismatches. Compare on the raw values with an explicit mask instead.
    """
    both = a.notna().to_numpy() & b.notna().to_numpy()
    if not both.any():
        return 0
    diff = a.to_numpy()[both] != b.to_numpy()[both]
    return int(diff.sum())


def check_prefix_invariance(close, high, low, period, mult, syms, cut_fracs):
    """Truncating the input must not change any earlier signal value."""
    failures = []
    n = len(close)
    for frac in cut_fracs:
        k = int(n * frac)
        sub_c = close.iloc[:k]
        full = supertrend_signal(close, high, low, period, mult).iloc[:k]
        part = supertrend_signal(sub_c, high.iloc[:k], low.iloc[:k], period, mult)
        mismatch = _count_disagreements(full, part)
        if mismatch:
            failures.append(
                f"period={period} mult={mult} cut={frac} ({k} bars): {mismatch} mismatches"
            )
        # Also assert the truncated run has NO value the full run lacks.
        invented = int((part.notna() & full.isna()).sum().sum())
        if invented:
            failures.append(
                f"period={period} mult={mult} cut={frac}: {invented} values invented "
                "on truncated data that the full run did not have"
            )
    return failures


def check_atr_parity(close, high, low, period, sym):
    """Panel ATR must equal the repo's own `cryptobot...atr()` on raw arrays."""
    c = close[sym].to_numpy()
    h = high[sym].to_numpy()
    low_ = low[sym].to_numpy()
    tr = true_range(close, high, low)[sym].to_numpy()
    i = len(c) - 1
    mine = float(np.mean(tr[i - period + 1: i + 1]))
    theirs = crypto_atr(h, low_, c, period)
    return mine, float(theirs)


def main():
    print("loading panels ...", flush=True)
    close, high, low = load_ohlc()
    print(f"close {close.shape} {close.index[0].date()} -> {close.index[-1].date()}")

    report = {"checks": [], "failures": []}

    # ---- 3. ATR parity
    for sym in ("reliance", "tcs", "hdfcbank", "infy"):
        if sym not in close.columns:
            continue
        mine, theirs = check_atr_parity(close, high, low, 14, sym)
        ok = abs(mine - theirs) < 1e-9
        print(f"ATR parity {sym:<10} panel={mine:.6f} crypto={theirs:.6f}  {'OK' if ok else 'FAIL'}")
        report["checks"].append({"check": f"atr_parity_{sym}", "ok": ok})
        if not ok:
            report["failures"].append(f"ATR parity mismatch on {sym}: {mine} vs {theirs}")

    # ---- 2. independent re-implementation
    variants = [(10, 3.0), (14, 3.0), (10, 2.0), (20, 3.0)]
    syms = [s for s in ("reliance", "tcs", "hdfcbank", "infy", "sbin", "lt") if s in close.columns]
    tr_panel = true_range(close, high, low)
    worst = 0.0
    for period, mult in variants:
        mine_panel = supertrend_signal(close, high, low, period, mult)
        for sym in syms:
            ref = _st_one_symbol(
                close[sym].to_numpy(), high[sym].to_numpy(), low[sym].to_numpy(),
                tr_panel[sym].to_numpy(), period, mult,
            )
            mine = mine_panel[sym].to_numpy()
            both = ~np.isnan(ref) & ~np.isnan(mine)
            d = float(np.max(np.abs(ref[both] - mine[both]))) if both.any() else 0.0
            ndiff = int((ref[both] != mine[both]).sum())
            worst = max(worst, d)
            if ndiff:
                report["failures"].append(
                    f"cross-check diff p={period} m={mult} {sym}: {ndiff} bars"
                )
        print(f"cross-check period={period} mult={mult}: {len(syms)} symbols, "
              f"max abs diff {worst:.3f}")
    report["checks"].append({"check": "independent_recursion", "ok": worst == 0.0,
                             "max_abs_diff": worst})

    # ---- 1. prefix invariance (the no-look-ahead test)
    print("prefix-invariance (look-ahead) test ...", flush=True)
    cuts = [0.35, 0.5, 0.62, 0.8, 0.93]
    fails = check_prefix_invariance(close, high, low, 10, 3.0, syms, cuts)
    # V0 too: a 1-day return signal must be trivially causal, but prove it.
    sub = as_shipped_signal(close.iloc[: int(len(close) * 0.7)])
    full0 = as_shipped_signal(close).iloc[: len(sub)]
    if _count_disagreements(full0, sub):
        fails.append("V0 as_shipped_signal failed prefix invariance")
    print(f"prefix invariance failures: {len(fails)}")
    for f in fails:
        print("   ", f)
    report["failures"].extend(fails)
    report["checks"].append({"check": "prefix_invariance", "ok": not fails})

    # ---- liveness of both signals over the full panel
    live = {}
    st = supertrend_signal(close, high, low, 10, 3.0)
    sh = as_shipped_signal(close)
    live["as_shipped"] = float((sh > 0).to_numpy().mean())
    for period, mult in variants:
        s = supertrend_signal(close, high, low, period, mult)
        live[f"st_p{period}_m{mult}"] = float((s > 0).to_numpy().mean())
    print("\nfraction of bars flagged +1 (full panel, NaN excluded):")
    for k, v in live.items():
        print(f"   {k:<16} {v * 100:6.2f}%")
    report["liveness_full_panel"] = live

    # ---- sign flips per year (chop indicator)
    flips = {}
    for name, s in (("as_shipped", sh), ("st_p10_m3.0", st)):
        d = s.diff().abs().to_numpy()
        flips[name] = float(np.nansum(d > 0) / (len(s) / 244))
    print("\nsign flips per year (lower = more persistent):")
    for k, v in flips.items():
        print(f"   {k:<16} {v:6.1f} flips/yr")
    report["flips_per_year"] = flips

    report["ok"] = not report["failures"]
    with open(Path(__file__).parent / "verify_signal.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nVERIFY {'PASS' if report['ok'] else 'FAIL'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
