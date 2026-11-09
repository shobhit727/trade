"""Harness for `multi_factor_strategy` on NSE NIFTY-50.

Nothing here modifies `src/nsealgo/**` or `src/cryptobot/**`. Read-only use.

The strategy is a two-vote confluence filter:
    vote_trend = +1 if close > SMA(period) else -1
    vote_mom   = +1 if RSI(rsip)  > 50   else -1
    signal     = +1 if score >= 2 else (-1 if score <= -2 else 0)

Long-only book => we act on the +1 leg only (`both votes up`).
"""

from __future__ import annotations

import sys
from decimal import Decimal

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402

IST = "Asia/Kolkata"
TRAIN = (
    pd.Timestamp("2016-01-01", tz=IST),
    pd.Timestamp("2023-12-31", tz=IST),
)
TEST = (
    pd.Timestamp("2024-01-01", tz=IST),
    pd.Timestamp("2026-10-01", tz=IST),
)

CM = CostModel(segment="delivery", slippage_bps=5)
RATE = float(CM.all_in_round_trip_bps(Decimal("100000"))) / 10_000.0

PANEL, SYMBOLS, REPORT = load_universe("data/nse")


# --------------------------------------------------------------------------- #
# Strategy signal, vectorised. Must match MultiFactorStrategy.signal() exactly.
# --------------------------------------------------------------------------- #


def sma_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """`indicators.sma` — simple mean of the last `period` closes."""
    return panel.rolling(period, min_periods=period).mean()


def rsi_panel(panel: pd.DataFrame, period: int) -> pd.DataFrame:
    """`indicators.rsi` — simple-average gains/losses over the last `period` diffs.

    NOT Wilder-smoothed (the catalog uses the simple form). `losses == 0 -> 100.0`,
    exactly as the catalog does, including the no-move case.
    """
    d = panel.diff()
    gains = d.clip(lower=0.0).rolling(period, min_periods=period).sum() / period
    losses = -d.clip(upper=0.0).rolling(period, min_periods=period).sum() / period
    gains = gains.where(gains.notna() & losses.notna())
    losses = losses.where(losses.notna())
    rs = gains / losses.where(losses > 0)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.where(losses > 0, 100.0)


def long_mask(panel: pd.DataFrame, period: int, rsip: int) -> pd.DataFrame:
    """True where the strategy would emit +1 (both votes up). NaN -> False."""
    t = sma_panel(panel, period)
    r = rsi_panel(panel, rsip)
    ok = t.notna() & r.notna()
    return ((panel > t) & (r > 50.0) & ok).fillna(False)


def verify_against_catalog(n_checks: int = 300, seed: int = 0) -> tuple[int, int]:
    """Assert the vectorised long_mask equals the real strategy class's signal.

    This is the faithfulness check: if the vectorised version drifts from the
    catalog implementation, every number below is measuring the wrong strategy.
    """
    from cryptobot.strategies.catalog.multi_factor_strategy import (
        MultiFactorConfig,
        MultiFactorStrategy,
    )

    rng = np.random.default_rng(seed)
    strat = MultiFactorStrategy(MultiFactorConfig(period=20, rsip=14))
    agree = disagree = 0
    for _ in range(n_checks):
        c = int(rng.integers(0, len(SYMBOLS)))
        i = int(rng.integers(300, len(PANEL) - 1))
        sym = SYMBOLS[c]
        closes = PANEL[sym].iloc[: i + 1].dropna().tolist()
        if len(closes) < 40:
            continue
        truth = strat.signal(closes, closes, closes, closes) == 1
        mine = bool(long_mask(PANEL[[sym]], 20, 14).iloc[i].item())
        if truth == mine:
            agree += 1
        else:
            disagree += 1
    return agree, disagree


# --------------------------------------------------------------------------- #
# Cross-sectional score construction (AGENT_BRIEF.md §5)
# --------------------------------------------------------------------------- #


def score_variant(panel: pd.DataFrame, period: int, rsip: int, rank_days: int,
                  fill: bool = False) -> pd.DataFrame:
    """Long-only cross-sectional score: momentum rank among the strategy's picks.

    fill=False -> only flagged names are eligible (unflagged = NaN = never held).
    fill=True  -> flagged names sort above unflagged ones; unflagged ranked by the
                  same momentum, used only to top the book up to `n_positions`.
    """
    mom = panel / panel.shift(rank_days) - 1.0
    ranked = mom.rank(axis=1, pct=True, na_option="keep")
    if not fill:
        return ranked.where(long_mask(panel, period, rsip))
    return ranked.where(long_mask(panel, period, rsip), ranked - 1.0)


# --------------------------------------------------------------------------- #
# Metrics on a window slice of a full-history run
# --------------------------------------------------------------------------- #


def window_metrics(res, start, end) -> dict:
    """Metrics for [start, end] taken from a full-history run.

    The book entering `start` is the one the earlier history produced — we slice,
    we do not restart the simulator, because restarting would hand the first
    rebalance a free, un-blended target.
    """
    r = res.returns.loc[start:end]
    eq = (1.0 + r).cumprod()
    years = max(len(r) / 244.0, 1e-9)

    # Weights change only on rebalance dates, so held.diff() is the trade vector.
    turn = (res.weights.diff().abs().sum(axis=1) / 2.0).loc[start:end].fillna(0.0)
    # Engine charges cost AFTER that day's gross return: recover the pre-cost equity.
    post_cost = 1.0 - 2.0 * turn * RATE
    pre_cost_eq = eq / post_cost.where(post_cost > 0)
    cost_amt = 2.0 * turn * pre_cost_eq * RATE

    m = compute_metrics(
        r,
        eq,
        annual_turnover=float(turn.sum() / years),
        cost_drag_annual=float(cost_amt.sum() / years),
        trades_per_year=float((turn > 0).sum() / years),
    )
    d = m.as_dict()
    d["avg_names"] = float((res.weights.loc[start:end] > 0).sum(axis=1).mean())
    d["n_rebalances"] = int((turn > 0).sum())
    d["costs_total_frac"] = float(1.0 - float((1.0 - 2.0 * turn * RATE).prod()))
    return d


def gross_metrics(res, start, end) -> dict:
    """Metrics for the SAME portfolio with the cost charge removed.

    Recovered analytically rather than by re-running at zero cost:
    the engine books `daily = (1+g)*(1-2*turn*RATE) - 1`, so
    `(1+g) = (1+daily) / (1 - 2*turn*RATE)`. This isolates cost drag honestly
    without mutating the (mandatory) cost model.
    """
    r = res.returns.loc[start:end]
    turn = (res.weights.diff().abs().sum(axis=1) / 2.0).loc[start:end].fillna(0.0)
    g = (1.0 + r) / (1.0 - 2.0 * turn * RATE) - 1.0
    eq = (1.0 + g).cumprod()
    out = compute_metrics(g, eq).as_dict()
    out["avg_names"] = float((res.weights.loc[start:end] > 0).sum(axis=1).mean())
    out["n_rebalances"] = int((turn > 0).sum())
    return out


def fmt_row(name: str, d: dict) -> str:
    return (
        f"{name:<28} CAGR {d['cagr']*100:>7.2f}%  Sharpe {d['sharpe']:>6.2f}  "
        f"MaxDD {d['max_drawdown']*100:>7.2f}%  Calmar {d['calmar']:>6.2f}  "
        f"Turn {d['annual_turnover']:>4.2f}x/y  Drag {d['cost_drag_annual']*100:>5.2f}%/y  "
        f"Names {d['avg_names']:>4.1f}  Ret {d['total_return']*100:>8.1f}%"
    )


def pct_live(panel: pd.DataFrame, period: int, rsip: int,
             start, end) -> float:
    """Fraction of (name, bar) observations where the strategy is long."""
    m = long_mask(panel.loc[start:end], period, rsip)
    return float(m.values.mean())


# --------------------------------------------------------------------------- #
# Controls
# --------------------------------------------------------------------------- #


def buy_and_hold(panel: pd.DataFrame, start, end, cash_buffer: float = 0.10) -> dict:
    """Equal-weight buy-and-hold over [start, end], net of costs.

    `panel.pct_change().mean(axis=1)` — the brief's definition — implicitly
    rebalances daily. Two treatments are returned:

      eod_net   the raw series with ONE all-in round trip charged on the deployed
                sleeve at inception. This is the honest "what would parking the
                book in the index have earned" number.
      mly_net   equal weight on every name, rebalanced monthly, costs charged with
                the engine's own formula (2 * turnover * rate * equity). Directly
                comparable to the strategy's own monthly-rebalanced book.
    """
    rets = panel.pct_change(fill_method=None).fillna(0.0)

    # ---- eod treatment -------------------------------------------------- #
    # `panel.pct_change().mean(axis=1)` is the brief's definition: equal weight on
    # every name with a price that day, rebalanced daily. One all-in round trip is
    # charged once, on the deployed sleeve, at inception.
    r_eod = rets.mean(axis=1).loc[start:end].fillna(0.0)
    entry_cost = (1.0 - cash_buffer) * RATE
    d_eod = r_eod.copy()
    d_eod.iloc[0] = (1.0 - entry_cost) * (1.0 + r_eod.iloc[0]) - 1.0
    m_eod = compute_metrics(d_eod, (1.0 + d_eod).cumprod()).as_dict()
    m_eod["avg_names"] = float(len(panel.columns))
    m_eod["cost_drag_annual"] = entry_cost / max(len(d_eod) / 244.0, 1e-9)
    m_eod["annual_turnover"] = 0.0

    # ---- monthly treatment ---------------------------------------------- #
    w_eq = pd.Series(1.0 / len(panel.columns), index=panel.columns) * (
        1.0 - cash_buffer
    )
    idx = panel.loc[start:end].index
    rb_set = set(
        pd.Series(idx, index=idx).groupby(idx.tz_localize(None).to_period("M")).apply(
            lambda g: g.index[0]
        )
    )
    r = rets.fillna(0.0)
    daily, turn_sum, costs_total = [], 0.0, 0.0
    held_w, e, prev_e = None, 1.0, 1.0
    for dt in idx:
        turn = 0.0
        if held_w is None or dt in rb_set:
            if held_w is not None:
                turn = float((w_eq - held_w).abs().sum() / 2.0)
            held_w = w_eq.copy()
        grown = held_w * (1.0 + r.loc[dt])
        g = float((held_w * r.loc[dt]).sum())
        # Let the surviving weights drift with prices until the next rebalance,
        # otherwise a "buy and hold" book silently rebalances for free. The sleeve
        # must keep summing to (1 - cash_buffer); renormalising to 1.0 would delete
        # the cash buffer and compound away.
        tot = float(grown.sum())
        if tot > 0:
            held_w = grown * ((1.0 - cash_buffer) / tot)
        e *= (1.0 + g)
        c = 2.0 * turn * e * RATE
        e -= c
        turn_sum += turn
        costs_total += c
        daily.append(e / prev_e - 1.0)
        prev_e = e
    d_mly = pd.Series(daily, index=idx)
    years = max(len(d_mly) / 244.0, 1e-9)
    m_mly = compute_metrics(
        d_mly,
        (1.0 + d_mly).cumprod(),
        annual_turnover=turn_sum / years,
        cost_drag_annual=costs_total / years,
        trades_per_year=len(rb_set) / years,
    ).as_dict()
    m_mly["avg_names"] = float(len(panel.columns))

    return {"eod": m_eod, "mly": m_mly}


def random_control(panel: pd.DataFrame, long_frac: float, rank_days: int,
                   seeds: list[int], start, end) -> dict:
    """Null: random names flagged at the SAME overall % long, identical book rules."""
    rows = []
    for s in seeds:
        rng = np.random.default_rng(s)
        flag = pd.DataFrame(
            rng.random(panel.shape) < long_frac, index=panel.index, columns=panel.columns
        )
        mom = panel / panel.shift(rank_days) - 1.0
        sc = mom.rank(axis=1, pct=True, na_option="keep").where(flag)
        res = run_backtest(panel, sc, CM, PortfolioConfig(), rebalance="M")
        rows.append(window_metrics(res, start, end))
    return {
        "cagr": np.array([r["cagr"] for r in rows]),
        "sharpe": np.array([r["sharpe"] for r in rows]),
        "max_drawdown": np.array([r["max_drawdown"] for r in rows]),
        "median_cagr": float(np.median([r["cagr"] for r in rows])),
        "median_sharpe": float(np.median([r["sharpe"] for r in rows])),
    }
