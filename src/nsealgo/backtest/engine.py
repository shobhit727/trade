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
from pathlib import Path

import numpy as np
import pandas as pd

from ..costs import CostModel
from .metrics import Metrics, compute_metrics

TRADING_DAYS = 244


def _engine_sha() -> str:
    """Stable hash of this engine's source (docstrings stripped).

    Agents found that concurrent edits to this file silently changed results
    mid-experiment -- identical scripts returned different numbers because
    ``apply_turnover_budget`` had been rewritten. Every BacktestResult now carries
    this hash so a report can state which engine produced it.
    """
    import ast
    import hashlib

    try:
        src = Path(__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                 ast.Module)):
                if node.body and isinstance(node.body[0], ast.Expr) and \
                        isinstance(getattr(node.body[0], "value", None), ast.Constant) and \
                        isinstance(node.body[0].value.value, str):
                    node.body.pop(0)
        payload = ast.dump(tree)
    except Exception:  # noqa: BLE001 - provenance must never break a backtest
        payload = "unknown"
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


ENGINE_SHA = _engine_sha()

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
    engine_sha: str = ENGINE_SHA
    diag: dict[str, float] = field(default_factory=dict)

    def summary(self) -> str:
        return f"[engine {self.engine_sha}]\n" + self.metrics.fmt()


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

    Weights at or below `DEAD_WEIGHT_EPS` are not tradable positions, so they are
    zeroed rather than carried; the survivors are the `max_names` largest.
    `apply_turnover_budget` picks what the book holds *before* this runs, so on the
    normal path there is nothing here to drop and this is the safety net that holds
    the position limit if a hand-built book arrives with too many names.
    """
    out = w.where(w > DEAD_WEIGHT_EPS, 0.0)
    if int((out > DEAD_WEIGHT_EPS).sum()) <= max_names:
        return out
    return out.where(out.index.isin(out.nlargest(max_names).index), 0.0)


def _one_way_turnover(tgt: pd.Series, cur: pd.Series) -> float:
    """One-way turnover: half the sum of absolute weight changes."""
    return float((tgt - cur).abs().sum() / 2.0)


def _exit_allocation(weights: pd.Series, cap: float) -> pd.Series:
    """Which unwanted positions to sell, in whole, spending at most ``cap`` in total.

    Sales are deliberately all-or-nothing. Half-selling a position leaves a residue
    small enough to be untradable but still costing its full former weight to clear
    later, and it holds a slot in ``max_names`` until it does — the exact tail of dust
    this function exists to prevent. So positions are taken smallest-first and one that
    does not fit in what is left of the budget is left alone rather than cut; the
    unsold names keep whole positions and are the smallest next time.

    Every position is sold when they fit the allowance together, which is the ordinary
    case. Capping only bites when the positions being dropped are worth more than the
    whole allowance, and then the budget — not the signal — is what decides.
    """
    ordered = weights.sort_values()
    if float(ordered.sum()) <= cap + CONSTRAINT_TOL:
        return ordered
    fits = (ordered.cumsum() <= cap + CONSTRAINT_TOL).to_numpy()
    sold = pd.Series(0.0, index=ordered.index)
    sold[fits] = ordered[fits]
    return sold


def apply_turnover_budget(
    weights: pd.Series,
    prev: pd.Series | None,
    budget: float,
    max_names: int,
) -> pd.Series:
    """Cap how much of the book may change at one rebalance, without diluting it.

    The evidence is unambiguous that turnover is the main drag (SEBI's own monotone
    loss gradient: 25 -> 742 trades/yr maps to a 65% -> 80% loss rate). Holding most
    of the book between rebalances is the cheapest way to respect that.

    The budget limits *how much* of the book may change, not *which way* it may change.
    Blending the whole book toward the new target made both directions equally slow, so
    a name that had dropped out of the target (``tgt[s] == 0``) only decayed by
    ``1 - lam`` per rebalance and was carried for many months: `_thin` kills a weight
    only below `DEAD_WEIGHT_EPS`, so the residue outlived the position by an order of
    magnitude. The delivered book then held mostly names the signal did not want, at a
    fraction of the intended exposure and a position count nothing like the configured
    one, so every headline number measured the dilution rather than the signal.

    So the movements are separated, and the exits get priority:

    * **Exits are unconditional and are paid for first.** A name the target no longer
      carries (or one that no longer fits inside ``max_names``) leaves, sold
      smallest-first and in whole (`_exit_allocation`). When the budget cannot clear
      them all, what stays stays whole and material — never a sliver.
    * **Adoption is whatever budget is left.** Only the surplus scales the new target.

    Names that are held *and* still wanted are carried at their current weight, which
    costs no turnover at all and is the cheapest way to keep the book invested.
    ``max_names`` is enforced by choosing which target names may be bought, not by
    dropping names afterwards, so the position limit cannot itself blow the budget.
    """
    if prev is None:
        return _thin(weights, max_names)

    universe = weights.index.union(prev.index)
    tgt = weights.reindex(universe).fillna(0.0)
    cur = prev.reindex(universe).fillna(0.0)

    # A target at or below the dead-weight threshold is not a position, so a name it
    # no longer carries must be sold rather than blended toward zero. Slots go to the
    # target's largest positions; anything past that limit is a drop, too.
    wanted = tgt > DEAD_WEIGHT_EPS
    kept = tgt[wanted].nlargest(max_names).index
    held_by_target = wanted & tgt.index.isin(kept)
    to_zero = (cur > 0) & ~held_by_target

    # `_one_way_turnover` is sum|dW| / 2, so the book's whole absolute change in one
    # rebalance may not exceed twice the one-way budget.
    cap = 2.0 * budget
    drop_amt = float(cur[to_zero].sum())

    # Carrying a name that is still wanted costs nothing, so it is the default.
    out = cur.where(~to_zero, 0.0)

    if drop_amt >= cap - CONSTRAINT_TOL:
        # The forced exits alone eat the whole allowance. They are compulsory, so they
        # take the budget and nothing new may be bought this rebalance.
        sold = _exit_allocation(cur[to_zero], cap).reindex(universe).fillna(0.0)
        out[to_zero] = cur[to_zero] - sold
    else:
        drift = float((tgt[held_by_target] - cur[held_by_target]).abs().sum())
        lam = min(1.0, (cap - drop_amt) / drift) if drift > 0.0 else 1.0
        out[held_by_target] = cur[held_by_target] + lam * (
            tgt[held_by_target] - cur[held_by_target]
        )

    out = _thin(out, max_names)
    if _one_way_turnover(out, cur) <= budget + CONSTRAINT_TOL:
        return out

    # Defensive only: the composition above is budget-feasible by construction, so
    # reaching here means `prev` was not already thinned to `max_names` (a hand-built
    # book rather than one this engine delivered). Holding it unchanged always fits.
    return _thin(cur, max_names)


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
    # `all_in_round_trip_bps` is quoted per unit of TOTAL turnover. A full rotation of
    # the book (sell 100%, buy 100%) is sum|dW| = 2.0, so the cost charged must be
    # sum|dW| * rate -- i.e. twice the one-way turnover. Charging `turnover * rate`
    # where turnover is already sum|dW|/2 under-charges by exactly 2x, which flatters
    # every CAGR in the project. Found by the agent_cointegration audit.
    turnover_by_date = pd.Series(0.0, index=px.index)
    turnover_by_date.loc[tgt.index] = (
        (tgt - tgt.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    ).values  # one-way convention, for reporting

    daily = pd.Series(0.0, index=px.index)
    eq = 1.0
    costs_total = 0.0
    for dt in px.index:
        prev_eq = eq
        eq *= (1.0 + float(gross.loc[dt]))
        turn_t = float(turnover_by_date.loc[dt])
        if turn_t > 0:
            # x2 converts the one-way turnover back to total turnover.
            cost_amt = 2.0 * turn_t * eq * rate
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
