"""Cross-sectional equity factors for NIFTY-50, daily bars.

Every factor here is:
  * computed **point-in-time** from data up to and including day *t*
  * ranked **cross-sectionally** each day (not time-series z-scored)
  * free of look-ahead by construction (`GOAL.md` §5 Gate 1)

Sign convention: `higher score = more attractive` (we want to buy the top of the book).
For factors where the raw quantity is a *risk* (e.g. volatility), the sign is flipped
and documented at the factor level.

## Why there is no mean-reversion factor here

An earlier version of this module carried `reversal_5d` and `reversal_20d` at 25% of
composite weight. **That was wrong, and the research removed it.** Two methodologically
disjoint literatures converge on short-term *continuation* in India, not reversal:

* Sehgal & Jain (2011) and IIMC (2020) find significant short-term momentum in Indian
  cash equities; reversal appears only at multi-year horizons with a 1-year gap.
* The only multiple-testing-corrected (Romano-Wolf) study of Indian technical rules,
  2015–2025, found 7 of 8 surviving configurations were **trend-following**, while
  RSI_25_75, RSI_30_70, Bollinger 20/2.0 and Bollinger 20/2.5 **all failed**
  (adjusted p 0.071–0.473), as did multi-indicator confluence (p = 0.209).

Reversal functions are retained below only as **negative controls** in
`research/run_backtest.py` — they are expected to underperform, and that expectation is
itself evidence that the harness is not simply mining noise.

See `reports/FACTOR_EVIDENCE.md` for the full survey and citations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 244  # ~ Indian trading year


# --------------------------------------------------------------------------- #
# Raw feature construction (all trailing, no lookahead)
# --------------------------------------------------------------------------- #


def trailing_return(panel: pd.DataFrame, days: int) -> pd.DataFrame:
    """Cumulative return over the last ``days`` bars."""
    return panel / panel.shift(days) - 1.0


def momentum_12_1(panel: pd.DataFrame) -> pd.DataFrame:
    """Classic 12-1 month momentum: 252d return **skipping** the last 21d.

    Rationale: intermediate-horizon underreaction (Jegadeesh-Titman / Fama-French).
    Indian evidence (Agarwalla, Jacob & Varma, *J. Emerging Markets* 2018) finds
    winners-minus-losers is the best-performing Indian factor at 17.3% p.a. long-short.

    Note the long-only caveat in `reports/FACTOR_EVIDENCE.md` §1.1: a long-only
    momentum tilt is substantially a **beta tilt**, so the full spread is not
    harvestable. We expect a fraction of it.
    """
    long = panel / panel.shift(TRADING_DAYS) - 1.0
    skip = panel / panel.shift(21) - 1.0
    return long - skip


def momentum_6m(panel: pd.DataFrame) -> pd.DataFrame:
    """6-month trailing momentum (126d).

    Nigam & Pandey, *Algorithmic Finance* 10(1-2) 2023, found **lagged 6-month
    compounded return with quarterly rebalance was the best long-only risk-adjusted
    momentum variant in India** — better than the academic 12-1 convention.
    """
    return panel / panel.shift(126) - 1.0


def reversal_5d(panel: pd.DataFrame) -> pd.DataFrame:
    """5-day reversal — **NEGATIVE CONTROL ONLY**.

    Indian evidence points the other way (short-term *continuation*). Kept so the
    research harness can demonstrate that adding it destroys performance. Never
    include in the live composite.
    """
    return -(panel / panel.shift(5) - 1.0)


def reversal_20d(panel: pd.DataFrame) -> pd.DataFrame:
    """20-day reversal — **NEGATIVE CONTROL ONLY**. See `reversal_5d`."""
    return -(panel / panel.shift(20) - 1.0)


def trend_strength_200d(panel: pd.DataFrame) -> pd.DataFrame:
    """Price position within the trailing 200-day range (0 = 200d low, 1 = high).

    A bounded, robust trend proxy that is less sensitive to the exact lookback
    window than a raw return.
    """
    hi = panel.rolling(200, min_periods=100).max()
    lo = panel.rolling(200, min_periods=100).min()
    return (panel - lo) / (hi - lo).replace(0, np.nan)


def low_volatility(panel: pd.DataFrame) -> pd.DataFrame:
    """Negative trailing volatility — *lower* volatility scores higher.

    Rationale: the low-volatility anomaly is one of the most robust equity
    factors across markets, and it reduces drawdown (see `GOAL.md` §2.3 Band C
    max-DD requirement).
    """
    vol = panel.pct_change(fill_method=None).rolling(60, min_periods=40).std()
    return -vol


def liquidity_score(panel: pd.DataFrame) -> pd.DataFrame:
    """Log average traded value proxy — we only have share volume, not value.

    Score is **higher for less liquid** names, and we use it as an *avoid* screen
    rather than an alpha factor, because `GOAL.md` §7 ranks liquidity as a screen.
    Returned as negative log-volume so higher = more tradable.
    """
    vol = panel.pct_change(fill_method=None).abs()
    # Turnover proxy: |return| is a stand-in for activity when value is unavailable.
    return -vol.rolling(20, min_periods=10).mean()


# --------------------------------------------------------------------------- #
# Cross-sectional normalisation
# --------------------------------------------------------------------------- #


def zscore_cross_sectional(factor: pd.DataFrame) -> pd.DataFrame:
    """Per-day cross-sectional z-score. NaNs are preserved, never imputed.

    Using per-day normalisation (not a time-series z-score) is essential: it makes
    the factor a *relative* ranking within today's universe, which is what a
    long-only ₹21L book actually does.
    """
    mu = factor.mean(axis=1)
    sd = factor.std(axis=1, ddof=0)
    sd = sd.replace(0, np.nan)
    return factor.sub(mu, axis=0).div(sd, axis=0)


def rank_cross_sectional(factor: pd.DataFrame) -> pd.DataFrame:
    """Per-day percentile rank in [0, 1]. Higher = more attractive."""
    return factor.rank(axis=1, pct=True, na_option="keep")


# --------------------------------------------------------------------------- #
# Composite factor construction
# --------------------------------------------------------------------------- #


DEFAULT_WEIGHTS: dict[str, float] = {
    # Primary engine: trend/momentum. Two disjoint literatures agree (see module docstring).
    "momentum_12_1": 0.40,
    "momentum_6m": 0.20,
    "trend_strength_200d": 0.25,
    # Second pillar: low-volatility. Best-behaved long-only factor in India
    # (Joshipura & Joshipura 2016: low-vol decile 11.40% vs high-vol 1.30% p.a.).
    "low_volatility": 0.15,
    # NOTE: no value factor. Indian value premium "nearly ceased to exist" post-2008
    # (Subramaniam, Sharma & Sehgal 2018) and 0 of 9 NSE factor indices showed
    # significant OOS alpha (Lalwani). No accounting data available anyway.
    # NOTE: no reversal. See module docstring.
}

#: Negative controls — expected to UNDERPERFORM. Used to prove the harness is not
#: simply mining noise. Never a production configuration.
NEGATIVE_CONTROL_WEIGHTS: dict[str, float] = {
    "reversal_5d": 0.45,
    "reversal_20d": 0.30,
    "low_volatility": 0.25,
}


def compute_raw_factors(panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """All raw factors, each as a raw-value panel."""
    return {
        "momentum_12_1": momentum_12_1(panel),
        "momentum_6m": momentum_6m(panel),
        "trend_strength_200d": trend_strength_200d(panel),
        "reversal_5d": reversal_5d(panel),
        "reversal_20d": reversal_20d(panel),
        "low_volatility": low_volatility(panel),
        "liquidity": liquidity_score(panel),
    }


def build_composite_score(
    panel: pd.DataFrame,
    weights: dict[str, float] | None = None,
    ranked: bool = True,
) -> pd.DataFrame:
    """Weighted blend of z-scored factors into one composite score.

    Parameters
    ----------
    ranked
        If True, each factor is converted to a cross-sectional **percentile rank**
        before blending. This is more robust to outliers (a single −80% print in
        one name) than raw z-scores, and is what production uses.
    """
    weights = DEFAULT_WEIGHTS if weights is None else weights
    raw = compute_raw_factors(panel)

    total_w = sum(weights.values())
    if total_w <= 0:
        raise ValueError("factor weights must sum to > 0")

    composite = pd.DataFrame(0.0, index=panel.index, columns=panel.columns)
    for name, w in weights.items():
        if name not in raw:
            raise KeyError(f"unknown factor {name!r}; have {sorted(raw)}")
        f = zscore_cross_sectional(raw[name])
        if ranked:
            f = rank_cross_sectional(f)
        # Names with a missing factor value get the cross-sectional median (0.5),
        # not a forward-filled value — that would leak the future into the blend.
        f = f.fillna(0.5)
        composite = composite.add(f * (w / total_w), fill_value=0.0)

    return composite


# --------------------------------------------------------------------------- #
# Market / regime context
# --------------------------------------------------------------------------- #


def equal_weight_market(panel: pd.DataFrame) -> pd.Series:
    """Equal-weight universe return — our market proxy (no index data available)."""
    return panel.pct_change(fill_method=None).mean(axis=1)


def breadth(positive_frac: pd.Series, window: int = 20) -> pd.Series:
    """Rolling fraction of days the market proxy was positive."""
    return (positive_frac > 0).rolling(window, min_periods=5).mean()
