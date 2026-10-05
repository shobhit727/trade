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

#: Numerical slack for the weight constraints. The projected weights must satisfy
#: every cap to within this; the acceptance tolerance on the result is far wider.
CONSTRAINT_TOL = 1e-12

#: Bounded sweeps of the alternating projection in `_project_constraints`.
#: Convergence is asserted, never assumed, so this only bounds pathological input.
PROJECT_ITERS = 200

#: Bounded water-filling passes used to place spilled weight. Each pass either lands
#: the whole remainder or exhausts at least one recipient, so this converges in 1-2.
SPILL_ITERS = 8

#: Weight below which a position is treated as dead. 1e-4 of a Rs 21,00,000 book
#: is Rs 210 — under one share at NIFTY-50 prices — so carrying it costs real
#: turnover (which `GOAL.md` §5 makes the dominant drag) and buys nothing.
DEAD_WEIGHT_EPS = 1e-4

#: Bounded attempts to re-fit the turnover budget after dead weights are dropped.
TURNOV_ITERS = 60


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


def _rooms(
    w: np.ndarray,
    sector_id: np.ndarray,
    n_sectors: int,
    max_weight: float,
    max_sector_weight: float,
) -> np.ndarray:
    """How much each name may still take, without breaking *either* cap.

    A name's room is the smaller of its own headroom and whatever is left in its
    sector, and the room inside a sector is shared across that sector's names rather
    than granted to each of them. That sharing is what stops a spill from satisfying
    one cap by breaking the other.
    """
    r = np.maximum(0.0, max_weight - w)
    room_by_sector = np.bincount(sector_id, weights=r, minlength=n_sectors)
    left = np.maximum(0.0, max_sector_weight - np.bincount(
        sector_id, weights=w, minlength=n_sectors))
    shrink = np.where(
        room_by_sector > left, left / np.maximum(room_by_sector, CONSTRAINT_TOL), 1.0
    )
    return r * shrink[sector_id]


def _spill(w: np.ndarray, room: np.ndarray, amount: float) -> None:
    """Move ``amount`` of weight into ``room``, in place.

    The book is spread across the names it *already* holds, in proportion to what each
    of them already has, so concentration is preserved — mass is never sprinkled across
    the whole universe to make a total look invested. Every recipient is clamped to its
    own room, and whatever exhausted recipients cannot absorb is offered to the rest,
    so a spill that has somewhere legal to go still lands in full. What nobody can
    legally take is left as cash rather than forced onto a capped name.
    """
    claim = np.maximum(w, 0.0)
    placed = np.zeros_like(w)
    todo = amount
    for _ in range(SPILL_ITERS):
        offered = np.where(room - placed > CONSTRAINT_TOL, claim, 0.0)
        total = float(offered.sum())
        if total <= CONSTRAINT_TOL or todo <= CONSTRAINT_TOL:
            break
        share = np.minimum(room - placed, todo * offered / total)
        placed += share
        todo -= float(share.sum())
    w += placed


def _constraints_hold(
    w: np.ndarray,
    sector_id: np.ndarray,
    n_sectors: int,
    max_weight: float,
    max_sector_weight: float,
) -> bool:
    """True when the single-name cap and every sector cap hold at once."""
    if float(w.max(initial=0.0)) > max_weight + CONSTRAINT_TOL:
        return False
    sector_totals = np.bincount(sector_id, weights=w, minlength=n_sectors)
    return bool(np.all(sector_totals <= max_sector_weight + CONSTRAINT_TOL))


def _project_constraints(
    w: np.ndarray,
    sector_id: np.ndarray,
    n_sectors: int,
    max_weight: float,
    max_sector_weight: float,
) -> np.ndarray:
    """Bring single-name and sector caps into force *simultaneously*.

    Neither cap can simply be applied last. Capping a sector has to move its excess
    somewhere, and that spill can land on a name already at the single-name cap;
    capping a name does the same into sectors that are already full. So the two are
    re-imposed on each other until both hold.

    Each sweep is monotone — spilling is bounded by the room in `_rooms`, so a sweep
    cannot create the violation the next sweep would have to undo — which is why this
    settles in a couple of sweeps instead of oscillating. Convergence is asserted, not
    assumed: mass that has nowhere legal to go is left as cash, never forced onto a
    name that would break a cap.

    ``w`` is projected in place and returned for convenience.
    """
    for _ in range(PROJECT_ITERS):
        if _constraints_hold(w, sector_id, n_sectors, max_weight, max_sector_weight):
            return w
        over = np.maximum(0.0, w - max_weight)
        if over.any():
            excess = float(over.sum())
            np.minimum(w, max_weight, out=w)
            _spill(w, _rooms(w, sector_id, n_sectors, max_weight, max_sector_weight),
                   excess)
        for si in range(n_sectors):
            member = sector_id == si
            tot = float(w[member].sum())
            if tot <= max_sector_weight + CONSTRAINT_TOL:
                continue
            excess = tot - max_sector_weight
            w[member] *= max_sector_weight / tot
            _spill(w, _rooms(w, sector_id, n_sectors, max_weight, max_sector_weight),
                   excess)
    raise RuntimeError(
        f"weight constraints did not converge in {PROJECT_ITERS} sweeps "
        f"(max single {float(w.max(initial=0.0)):.6f} vs cap {max_weight}, "
        f"max sector {float(np.bincount(sector_id, weights=w, minlength=n_sectors).max()):.6f}"
        f" vs cap {max_sector_weight})"
    )


def build_rebalance_weights(
    score: pd.DataFrame,
    dates: list,
    vol: pd.DataFrame,
    config: PortfolioConfig,
) -> pd.DataFrame:
    """Target weights on each rebalance date only. Fully vectorised per row."""
    cols = list(score.columns)
    n = len(cols)

    # Precompute sector membership: sector_id per name (names in no known sector are
    # all "other", which is itself a cap-relevant group).
    sectors = sorted({sector_of(c) for c in cols})
    sector_id = np.array([sectors.index(sector_of(c)) for c in cols])
    n_sectors = len(sectors)

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

        # ---- single-name AND sector caps, enforced simultaneously to convergence
        w_full = _project_constraints(
            w_full, sector_id, n_sectors, config.max_weight, config.max_sector_weight
        )

        # ---- cash buffer
        w_full *= (1.0 - config.cash_buffer)
        out[i] = w_full

    return pd.DataFrame(out, index=pd.DatetimeIndex(dates), columns=cols)


def _thin(w: pd.Series, max_names: int) -> pd.Series:
    """Drop dead residuals; keep at most ``max_names`` material positions.

    Blending toward a new target shrinks a dropped name's weight but never reaches
    zero, so without this the book accretes a tail of one- or two-paise positions
    every rebalance and ends up holding far more names than it is allowed to.
    Weights at or below `DEAD_WEIGHT_EPS` are not tradable positions, so they are
    zeroed rather than carried; the survivors are the `max_names` largest.
    """
    out = w.where(w > DEAD_WEIGHT_EPS, 0.0)
    if int((out > DEAD_WEIGHT_EPS).sum()) <= max_names:
        return out
    return out.where(out.index.isin(out.nlargest(max_names).index), 0.0)


def _one_way_turnover(tgt: pd.Series, cur: pd.Series) -> float:
    """One-way turnover: half the sum of absolute weight changes."""
    return float((tgt - cur).abs().sum() / 2.0)


def apply_turnover_budget(
    weights: pd.Series,
    prev: pd.Series | None,
    budget: float,
    max_names: int,
) -> pd.Series:
    """Cap how much of the book may change at one rebalance.

    The evidence is unambiguous that turnover is the main drag (SEBI's own monotone
    loss gradient: 25 -> 742 trades/yr maps to a 65% -> 80% loss rate). Holding most
    of the book between rebalances is the cheapest way to respect that.

    ``max_names`` is required rather than optional: the blended weights must always be
    thinned to that many material positions, or the book accretes dead residuals and
    drifts past its position limit. Thinning is re-checked against the budget, because
    dropping a name is itself a trade.
    """
    if prev is None:
        return _thin(weights, max_names)
    universe = weights.index.union(prev.index)
    tgt = weights.reindex(universe).fillna(0.0)
    cur = prev.reindex(universe).fillna(0.0)
    changed = _one_way_turnover(tgt, cur)
    lam = min(1.0, budget / changed) if changed > 0 else 1.0
    for _ in range(TURNOV_ITERS):
        out = _thin(cur + lam * (tgt - cur), max_names)
        if _one_way_turnover(out, cur) <= budget + CONSTRAINT_TOL:
            return out
        # Thinning broke the budget: zeroing a name is itself a trade. Re-fit lam so
        # the *kept* book spends exactly the budget — drift is linear in lam, and the
        # dropped names are frozen at their current weight, so this is closed-form.
        kept = out > 0
        drift = float((tgt - cur).abs()[kept].sum())
        room = 2.0 * budget - float(cur[~kept].sum())
        lam = room / drift if drift > 0 and room > 0 else 0.0
    raise RuntimeError(
        f"turnover budget {budget} unreachable while holding {max_names} names"
    )


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
    for i in range(len(tgt)):
        prev = tgt.iloc[i - 1] if i else None
        tgt.iloc[i] = apply_turnover_budget(
            tgt_raw.iloc[i], prev, config.turnover_budget, config.max_names
        )

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
