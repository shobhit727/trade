"""Shared data prep for the volume_weighted_momentum agent.

Builds a cleaned close panel AND a cleaned volume panel that share an identical
index, so any signal built from them is aligned by construction.

`load_universe` returns only closes. Volume is needed, so it is re-read from the
same CSVs via the same `load_symbol` cleaning path (C1-C9), which guarantees the
volume rows correspond one-to-one with the surviving close rows.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import EXCLUDE_SYMBOLS, load_symbol  # noqa: E402

DATA_DIR = os.environ.get("NSE_DATA", "data/nse")

TRAIN_START = pd.Timestamp("2016-01-01", tz="Asia/Kolkata")
TRAIN_END = pd.Timestamp("2023-12-31", tz="Asia/Kolkata")
TEST_START = pd.Timestamp("2024-01-01", tz="Asia/Kolkata")
TEST_END = pd.Timestamp("2026-10-01", tz="Asia/Kolkata")

COST_MODEL = CostModel(segment="delivery", slippage_bps=5)
ZERO_COST_MODEL = CostModel(segment="delivery", slippage_bps=0.0)


def load_panels(data_dir: str = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Return (close_panel, volume_panel, symbols) on a shared index.

    Mirrors `load_universe`'s retention rules (skip excluded symbols, skip
    DataIntegrityError, skip < 1000 bars) so the two panels agree on the universe.
    """
    closes: dict[str, pd.Series] = {}
    vols: dict[str, pd.Series] = {}

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith("_1d.csv"):
            continue
        symbol = fname[: -len("_1d.csv")]
        if symbol in EXCLUDE_SYMBOLS:
            continue
        try:
            df = load_symbol(os.path.join(data_dir, fname), symbol, None)
        except Exception:  # noqa: BLE001 - same fallback load_universe uses
            continue
        if len(df) < 1000:
            continue
        closes[symbol] = df["close"].rename(symbol)
        vols[symbol] = df["vol"].rename(symbol)

    px = pd.DataFrame(closes).sort_index()
    vol = pd.DataFrame(vols).sort_index()

    # Same panel-level filters load_universe applies (C8 weekend, sparse-coverage).
    weekend = px.index.dayofweek >= 5
    if weekend.any():
        px = px.loc[~weekend]
        vol = vol.loc[~weekend]
    coverage = px.notna().mean(axis=1)
    sparse = coverage < 0.05
    if sparse.any():
        px = px.loc[~sparse]
        vol = vol.loc[~sparse]

    # Force a shared index: the volume panel must never have a date the close panel
    # lacks, or a signal would silently reference a price that isn't there.
    vol = vol.reindex(px.index)
    assert list(vol.index) == list(px.index)
    return px, vol, list(px.columns)


def slice_split(panel: pd.DataFrame, start, end) -> pd.DataFrame:
    return panel.loc[(panel.index >= start) & (panel.index <= end)]


def roc_panel(close: pd.DataFrame, period: int) -> pd.DataFrame:
    """Vectorised equivalent of `indicators.roc(closes, period)`.

    catalog `roc` returns (C_t - C_{t-p}) / C_{t-p} using closes[-1] vs
    closes[-period-1], i.e. exactly `close/close.shift(period) - 1`.
    NaN during warmup (catalog returns NaN and the strategy returns 0).
    """
    return close / close.shift(period) - 1.0


def avg_volume_panel(vol: pd.DataFrame, period: int) -> pd.DataFrame:
    """`mean(volumes[-period:])` — trailing simple mean volume, incl. today."""
    return vol.rolling(period, min_periods=period).mean()


def vwm_signal(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    period: int,
    threshold: float,
    long_only: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """Faithful port of `VwMomentumStrategy.signal`.

    The catalog computes, per bar, from a **streaming per-symbol deque** of real
    bars (see `cryptobot/strategies/signal_base.py`):

        m   = roc(closes, period)
        avg = mean(volumes[-period:])
        vw  = avg * (1.0 if volumes[-1] >= avg else 0.5)
        +1  if m >  threshold and vw > 0
        -1  if m < -threshold and vw > 0
         0  otherwise

    ---- WHY THIS IS COMPUTED PER SYMBOL, NOT ON THE WIDE PANEL ----

    An earlier version computed `vol.rolling(period, min_periods=period).mean()` on
    the NaN-padded wide panel. That is NOT the same function. `min_periods=period`
    means the mean is NaN if ANY of the window's cells is NaN, so ONE missing vendor
    bar produces a NaN for the next `period` days, `vw` becomes NaN, `vw > 0` is
    False, and the strategy returns 0 -- a `period`-day trading blackout for that
    name. The streaming original never sees this: a missing vendor day means no
    `feed()` call at all, and the `period`-bar window simply spans the `period`
    most recent *actual* bars.

    Measured cost of the wide-panel shortcut on this data: `indigo` is missing
    2026-05-01 from the vendor feed, which silenced it on 20 bars at period=20,
    35 at 63, 53 at 126 and 0 at 252 -- 96 spurious signal cells in total.

    So: drop NaN rows per symbol first (that is exactly what the deque holds), run
    the rolling mean on the symbol's own bars, then reindex back to the panel.

    `long_only=True` maps -1 -> 0 (Indian delivery accounts cannot short).
    """
    sig = pd.DataFrame(0.0, index=close.index, columns=close.columns)

    n_up = n_down = n_blocked = 0
    n_cells = 0
    blocked_cells = 0

    for sym in close.columns:
        c = close[sym].dropna()
        v = vol[sym].reindex(c.index)
        if c.empty:
            continue

        # The deque holds exactly the bars that exist. Any remaining NaN in `v`
        # would be a close with no volume print; the engine coerces those to 0.0
        # (`v.append(float(volume if volume is not None else 0.0))`).
        vv = v.fillna(0.0).to_numpy(dtype=float)
        cc = c.to_numpy(dtype=float)

        m = np.full(cc.size, np.nan)
        if cc.size > period:
            # catalog `roc`: prev = closes[-period-1], last = closes[-1]
            # i.e. at array position t, prev is position t-period.
            idx = np.arange(period, cc.size)
            prev = cc[idx - period]
            last = cc[idx]
            with np.errstate(divide="ignore", invalid="ignore"):
                m[idx] = np.where(prev != 0, (last - prev) / prev, 0.0)

        avg = np.full(cc.size, np.nan)
        if period > 0 and cc.size >= period:
            cs = np.concatenate(([0.0], np.cumsum(vv)))
            avg[period - 1:] = (cs[period:] - cs[:-period]) / period

        vw = avg * np.where(vv >= avg, 1.0, 0.5)
        gate = vw > 0  # NaN -> False, exactly as the catalog's `vw > 0` behaves

        up = (m > threshold) & gate
        down = (m < -threshold) & gate

        out = np.zeros(cc.size)
        out[up] = 1.0
        if not long_only:
            out[down] = -1.0

        sig.loc[c.index, sym] = out

        n_up += int(up.sum())
        n_down += int(down.sum())
        n_cells += int(gate.size)
        n_blocked += int((~gate).sum())
        blocked_cells += int((~gate).sum())

    diag = {
        "frac_cells_long": n_up / max(n_cells, 1),
        "frac_cells_short": n_down / max(n_cells, 1),
        "frac_days_any_long": float((sig > 0).any(axis=1).mean()),
        "mean_names_long": float((sig > 0).sum(axis=1).mean()),
        "min_names_long": float((sig > 0).sum(axis=1).min()),
        "frac_days_lt22_long": float(((sig > 0).sum(axis=1) < 22).mean()),
        "vw_gate_blocked_frac": n_blocked / max(n_cells, 1),
        "vw_gate_blocked_cells": blocked_cells,
    }
    return sig, diag


def momentum_rank_score(close: pd.DataFrame, signal: pd.DataFrame, mom_days: int = 126):
    """Cross-sectional score: trailing momentum rank, masked to flagged names.

    Per AGENT_BRIEF §5. Names not flagged get NaN, which `build_rebalance_weights`
    treats as ineligible (valid requires isfinite). Fixed, not tuned.
    """
    mom = close / close.shift(mom_days) - 1.0
    return mom.where(signal > 0).rank(axis=1, pct=True)


def signal_rank_score(signal: pd.DataFrame):
    """Alternative score: rank by the signal itself (1.0 everywhere flagged).

    Degenerate — every flagged name ties — so only used as a control to show the
    ranking term, not the flag, is what carries the result.
    """
    return signal.where(signal > 0).rank(axis=1, pct=True)


def fmt_metrics(m) -> str:
    return m.fmt()
