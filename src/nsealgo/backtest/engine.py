"""Vectorised, event-driven, cost-aware NIFTY-50 backtest engine.

Design decisions and their evidence (see `reports/FACTOR_EVIDENCE.md`):

* **Trend/momentum is the primary alpha engine. There is no mean-reversion core.**
  Two methodologically disjoint literatures converge on this: the Indian factor
  literature finds short-term *continuation* (Sehgal & Jain 2011; IIMC 2020), and the
  only multiple-testing-corrected Indian technical study (Romano-Wolf) found 7 of 8
  surviving rules were trend-following while RSI/Bollinger mean-reversion all failed.

* **Monthly rebalance, not weekly.** No Indian study supports weekly. Monthly signal
  evaluation with a turnover budget is what the evidence supports, and it is also
  cheaper. Weight targets are computed only on rebalance dates and held in between —
  which is both the realistic behaviour and what makes this fast enough to sweep.

* **No look-ahead.** Targets on date *t* use factors from closes up to and including
  *t*; the portfolio earns returns from *t+1* onward via `held_weights . returns`.

* **Costs on every rebalance**, measured from the same `CostModel` used by the live
  system, so the backtest can never be more optimistic than reality (GOAL.md §6.4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..costs import CostModel
from .metrics import Metrics, compute_metrics

TRADING_DAYS = 244

#: Reference per-position notional for cost measurement. Flat DP charges make the
#: round-trip bps size-dependent, so this must be realistic: Rs 21,00,000 x 0.9
#: deployed / 22 positions ~ Rs 86,000. We round to 1,00,000 for stability.
REF_POSITION_NOTIONAL = 100_000


# --------------------------------------------------------------------------- #
# Sector map. Static approximation — a diversification guard, not an alpha input.
# --------------------------------------------------------------------------- #

SECTORS: dict[str, str] = {
    "hdfcbank": "bank", "icicibank": "bank", "kotakbank": "bank", "axisbank": "bank",
    "sbin": "bank",
    "bajajfinsv": "fin", "bajajfinance": "fin", "sbilife": "fin", "hdfclife": "fin",
    "shriramfin": "fin",
    "tcs": "it", "infy": "it", "hcltech": "it", "techm": "it", "lt": "it",
    "wipro": "it",
    "reliance": "oilgas", "ongc": "oilgas", "coalindia": "oilgas",
    "powergrid": "util", "ntpc": "util",
    "titan": "cons", "asianpaint": "cons", "nestleind": "cons", "tataconsum": "cons",
    "trent": "cons", "indigo": "cons",
    "maruti": "auto", "bajaj-auto": "auto", "m&m": "auto", "eichermot": "auto",
    "jswsteel": "metal", "tatasteel": "metal", "hindalco": "metal",
    "ultracemco": "cement", "grasim": "cement",
    "bel": "psu",
    "sunpharma": "pharma", "drreddy": "pharma", "cipla": "pharma",
    "apollohosp": "pharma", "maxhealth": "pharma",
    "bhartiartl": "telecom",
    "adaniports": "infra", "adaniient": "infra",
    "eternal": "cons", "jiofin": "fin", "tmpv": "cons",
}


def sector_of(symbol: str) -> str:
    return SECTORS.get(symbol, "other")


# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PortfolioConfig:
    """Constraints. Defaults come from `GOAL.md` §3.2."""

    n_positions: int = 22
    max_weight: float = 0.12          # 12% max single stock
    max_sector_weight: float = 0.25   # 25% max sector
    cash_buffer: float = 0.10         # hold ~10% cash
    vol_lookback: int = 60            # trailing days for inverse-vol scaling
    turnover_budget: float = 0.35     # max fraction of book that may change per rebalance
    max_names: int = 30


@dataclass
class BacktestResult:
    returns: pd.Series
    equity: pd.Series
    weights: pd.DataFrame
    metrics: Metrics
    costs_paid: float = 0.0
    diag: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        return self.metrics.fmt()


# --------------------------------------------------------------------------- #
# Vectorised weight construction
# --------------------------------------------------------------------------- #


def _cap_columns(
    w: np.ndarray, cap: float, member: np.ndarray | None = None, iters: int = 30
) -> np.ndarray:
    """Clip weights to ``cap`` and redistribute the excess to uncapped columns.

    ``member`` optionally restricts which columns are in the capped group (used for
    sector caps); the excess goes to all columns not in that group.
    """
    w = w.copy()
    for _ in range(iters):
        if member is None:
            over = w > cap
        else:
            over = (w > cap) & member
        if not over.any():
            break
        excess = float((w - cap)[over].sum())
        w[over] = cap
        if member is None:
            free = ~over
        else:
            free = ~member
        total_room = float((cap - w[free]).sum())
        if total_room <= 1e-12:
            break
        w[free] += excess * (cap - w[free]) / total_room
    return w


def build_rebalance_weights(
    score: pd.DataFrame,
    dates: list,
    vol: pd.DataFrame,
    config: PortfolioConfig,
) -> pd.DataFrame:
    """Target weights on each rebalance date only. Fully vectorised per row."""
    cols = list(score.columns)
    n = len(cols)

    # Precompute sector membership as a boolean matrix (n_sectors, n_names).
    sectors = sorted({sector_of(c) for c in cols})
    sector_mask = np.zeros((len(sectors), n), dtype=bool)
    for si, sec in enumerate(sectors):
        for j, c in enumerate(cols):
            if sector_of(c) == sec:
                sector_mask[si, j] = True

    S = score.to_numpy(dtype=float)
    V = vol.to_numpy(dtype=float)
    out = np.zeros((len(dates), n), dtype=float)
    k = min(config.n_positions, n)

    for i in range(len(dates)):
        s = S[i].copy()
        v = V[i].copy()
        valid = np.isfinite(s) & np.isfinite(v) & (v > 0)
        if not valid.any():
            continue

        # Rank on score; deterministic tie-break via stable sort on (score, index).
        s_masked = np.where(valid, s, -np.inf)
        order = np.argsort(-s_masked, kind="stable")[:k]
        if len(order) == 0:
            continue

        pick_valid = valid[order]
        order = order[pick_valid]
        if len(order) == 0:
            continue

        # ---- inverse-volatility scaling (bounds the weight of high-vol names)
        ivol = 1.0 / np.clip(v[order], 1e-6, None)
        w_full = np.zeros(n)
        w_full[order] = ivol / ivol.sum()

        # ---- single-name cap
        w_full = _cap_columns(w_full, config.max_weight)

        # ---- sector cap: cap each sector's total, push excess to other sectors
        for si in range(len(sectors)):
            member = sector_mask[si]
            tot = float(w_full[member].sum())
            if tot > config.max_sector_weight + 1e-12:
                excess = tot - config.max_sector_weight
                w_full[member] *= config.max_sector_weight / tot
                free = ~member
                fw = w_full[free]
                fs = float(fw.sum())
                if fs > 0:
                    w_full[free] = fw + excess * fw / fs

        # ---- cash buffer
        w_full *= (1.0 - config.cash_buffer)
        out[i] = w_full

    return pd.DataFrame(out, index=pd.DatetimeIndex(dates), columns=cols)


def apply_turnover_budget(
    weights: pd.Series, prev: pd.Series | None, budget: float
) -> pd.Series:
    """Cap how much of the book may change at one rebalance.

    The evidence is unambiguous that turnover is the main drag (SEBI's own monotone
    loss gradient: 25 -> 742 trades/yr maps to a 65% -> 80% loss rate). Holding most
    of the book between rebalances is the cheapest way to respect that.
    """
    if prev is None:
        return weights
    universe = weights.index.union(prev.index)
    tgt = weights.reindex(universe).fillna(0.0)
    cur = prev.reindex(universe).fillna(0.0)
    changed = (tgt - cur).abs().sum() / 2.0  # one-way turnover fraction
    if changed <= budget or changed <= 0:
        return tgt
    # Move only a fraction of the way toward the target so turnover hits the budget.
    lam = budget / changed
    blended = cur + lam * (tgt - cur)
    return blended


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #


def _rebalance_dates(index: pd.DatetimeIndex, freq: str) -> list:
    """First available trading day of each period. No external calendar."""
    if freq.upper() == "M":
        keys = index.tz_localize(None).to_period("M")
    elif freq.upper() == "W":
        keys = index.tz_localize(None).to_period("W")
    elif freq.upper() == "Q":
        keys = index.tz_localize(None).to_period("Q")
    else:
        raise ValueError("freq must be 'W', 'M' or 'Q'")
    s = pd.Series(index, index=index)
    return [g.index[0] for _, g in s.groupby(keys)]


def run_backtest(
    panel: pd.DataFrame,
    score: pd.DataFrame,
    cost_model: CostModel,
    config: PortfolioConfig | None = None,
    rebalance: str = "M",
    initial_capital: float = 2_100_000.0,
) -> BacktestResult:
    """Long-only, cost-aware, monthly-rebalanced NIFTY-50 backtest.

    Execution: weights decided from the close of date *t* are held from *t+1*
    onward. The one-bar lag is what removes look-ahead.
    """
    index = panel.index.intersection(score.index)
    px = panel.loc[index]
    sc = score.loc[index]

    rets = px.pct_change(fill_method=None).fillna(0.0)
    vol = rets.rolling(config.vol_lookback, min_periods=20).std()

    rb = [d for d in _rebalance_dates(px.index, rebalance) if d in sc.index]
    rb = rb[1:]  # first date has no factor history

    # --- target weights on rebalance dates, with turnover budget applied
    tgt_raw = build_rebalance_weights(sc.loc[rb], rb, vol.loc[rb], config)
    tgt = tgt_raw.copy()
    for i in range(1, len(tgt)):
        prev = tgt.iloc[i - 1]
        tgt.iloc[i] = apply_turnover_budget(tgt_raw.iloc[i], prev, config.turnover_budget)

    # --- hold weights between rebalances (reindex + ffill)
    held = tgt.reindex(px.index).ffill().fillna(0.0)

    # --- attribute returns + costs against a *compounding* normalised equity.
    #
    # Costs must be charged on the equity actually held at the time. Charging a bare
    # fraction of turnover (rather than of equity) understates the drag by an order of
    # magnitude on a book that compounds — precisely the optimistic bookkeeping that
    # GOAL.md §6.4 forbids.
    rt_bps = float(cost_model.all_in_round_trip_bps(_d(REF_POSITION_NOTIONAL)))
    rate = rt_bps / 10_000.0

    gross = (held.shift(1).fillna(0.0) * rets).sum(axis=1)
    turnover_by_date = pd.Series(0.0, index=px.index)
    turnover_by_date.loc[tgt.index] = (
        (tgt - tgt.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    ).values

    daily = pd.Series(0.0, index=px.index)
    eq = 1.0
    costs_total = 0.0
    for dt in px.index:
        prev_eq = eq
        eq *= (1.0 + float(gross.loc[dt]))
        turn_t = float(turnover_by_date.loc[dt])
        if turn_t > 0:
            cost_amt = turn_t * eq * rate
            eq -= cost_amt
            costs_total += cost_amt
        daily.loc[dt] = eq / prev_eq - 1.0

    equity = (1.0 + daily).cumprod()

    years = max(len(equity) / TRADING_DAYS, 1e-9)
    annual_turnover = float(turnover_by_date.sum() / years)
    # costs_total is measured in *normalised* equity units (equity starts at 1.0),
    # so divide by years to get the annual drag directly.
    cost_drag = costs_total / years

    metrics = compute_metrics(
        daily,
        equity,
        annual_turnover=annual_turnover,
        cost_drag_annual=cost_drag,
        trades_per_year=float(len(rb) / years),
    )
    return BacktestResult(
        returns=daily,
        equity=equity,
        weights=held,
        metrics=metrics,
        costs_paid=float(costs_total * initial_capital),
        diag={
            "n_rebalances": len(rb),
            "avg_names": float((held > 0).sum(axis=1).mean()),
            "avg_top_weight": float(
                held.where(held > 0).max(axis=1).mean()
            ),
            "round_trip_bps": rt_bps,
        },
    )


def _d(x):
    from decimal import Decimal

    return Decimal(str(x))
