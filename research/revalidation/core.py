"""Shared machinery for tie-break re-validation.

Read-only with respect to `src/`, `tests/` and every existing agent directory.

The question this module exists to answer: `build_rebalance_weights` used to rank with
``np.argsort(-score, kind="stable")``, so a tied score resolved by *column position* --
and the panel's columns are alphabetical. The fix (``ENGINE_SHA`` ``d93815344bd3`` ->
``29764f562cd5``) replaced that with ``blake2b("{date}|{symbol}")`` via ``np.lexsort``.

Rather than trusting any agent's stored numbers, this module reconstructs the **old**
engine from git and runs *both* engines on the same score panel. The difference is a
measurement, not an inference from prose.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from nsealgo.backtest.engine import (  # noqa: E402
    PortfolioConfig,
    _rebalance_dates,
    run_backtest,
)
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

EXPECTED_ENGINE = "29764f562cd5"
OLD_ENGINE = "d93815344bd3"
TIEBREAK_COMMIT = "f4fff7c"

COST = CostModel(segment="delivery", slippage_bps=5)
ALL_IN_BPS = float(COST.all_in_round_trip_bps(Decimal("100000")))
CONFIG = PortfolioConfig()

IST = "Asia/Kolkata"
TRAIN = (pd.Timestamp("2016-01-01", tz=IST), pd.Timestamp("2023-12-31", tz=IST))
TEST = (pd.Timestamp("2024-01-01", tz=IST), pd.Timestamp("2026-10-01", tz=IST))

_PANEL_CACHE: dict[str, pd.DataFrame] = {}


def panel() -> pd.DataFrame:
    """Cleaned daily close panel (the substrate every agent used)."""
    if "px" not in _PANEL_CACHE:
        px, _syms, _rep = load_universe(str(REPO / "data/nse"))
        _PANEL_CACHE["px"] = px
    return _PANEL_CACHE["px"]


def check_provenance() -> dict[str, str]:
    p = provenance()
    if p["engine"] != EXPECTED_ENGINE:
        raise SystemExit(
            f"ABORT: engine is {p['engine']}, expected {EXPECTED_ENGINE}. "
            "Every number in this report would be against an unknown engine."
        )
    return p


def load_old_engine():
    """Import the pre-fix engine (`d93815344bd3`) as a live, callable module.

    Loaded from git rather than reconstructed by hand so the comparison is exact.
    The module name is placed inside the ``nsealgo.backtest`` package so its relative
    imports (``from ..costs import CostModel``) resolve normally.
    """
    src = REPO / "research/revalidation/_old_engine_src.py"
    raw = subprocess.run(  # noqa: S603
        ["git", "show", f"{TIEBREAK_COMMIT}^:src/nsealgo/backtest/engine.py"],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    src.write_text(raw.stdout)
    name = "nsealgo.backtest.engine_old"
    spec = importlib.util.spec_from_file_location(name, src)
    if spec is None or spec.loader is None:  # pragma: no cover
        raise RuntimeError("could not load old engine")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    # The old module does `from ..provenance import ENGINE_SHA`, so it inherits the
    # *current* fingerprint and would mislabel its own results. Force the true label.
    mod.ENGINE_SHA = OLD_ENGINE
    return mod


OLD = load_old_engine()


# --------------------------------------------------------------------------- #
# Tie exposure -- the root-cause question, measured without trusting any prose.
# --------------------------------------------------------------------------- #


def tie_exposure(
    score: pd.DataFrame,
    n_positions: int = 22,
    rebalance: str = "M",
) -> dict:
    """How often is the top-``n_positions`` cut decided by a tie?

    Two distinct failure modes, reported separately because they need different fixes:

    * ``flat_mask_frac`` -- the whole eligible set shares one score value. Every
      eligible name ties, so the cut is *entirely* arbitrary. This is the degenerate
      binary-mask case.
    * ``cut_tied_frac`` -- the score at rank ``n_positions`` equals the score at rank
      ``n_positions + 1``. Names on both sides of the cut are interchangeable, so *which*
      name is bought was decided by the tie-break.
    * ``cut_tied_names`` -- on those dates, how many names sit in the straddling tie
      block. That is the size of the coin-flip.
    """
    rb = [d for d in _rebalance_dates(score.index, rebalance) if d in score.index]
    rb = rb[1:]  # engine drops the first rebalance date
    n_flat = n_cut_tied = n_saturated = 0
    block_sizes: list[int] = []
    eligible_counts: list[int] = []
    n_uniq: list[int] = []

    for d in rb:
        row = pd.to_numeric(score.loc[d], errors="coerce").dropna()
        eligible_counts.append(len(row))
        n_uniq.append(int(row.nunique()))
        if row.empty:
            continue
        vals = np.sort(row.to_numpy(dtype=float))[::-1]
        if len(np.unique(vals)) == 1:
            n_flat += 1
        if len(vals) > n_positions:
            n_saturated += 1
            cut = vals[n_positions - 1]
            if vals[n_positions] == cut:
                n_cut_tied += 1
                block_sizes.append(int((vals == cut).sum()))

    n = max(len(rb), 1)
    return {
        "n_rebalances": len(rb),
        "eligible_mean": float(np.mean(eligible_counts)) if eligible_counts else float("nan"),
        "eligible_max": int(max(eligible_counts)) if eligible_counts else 0,
        "uniq_vals_mean": float(np.mean(n_uniq)) if n_uniq else float("nan"),
        "frac_saturated": n_saturated / n,
        "flat_mask_frac": n_flat / n,
        "cut_tied_frac": n_cut_tied / n,
        "cut_tied_names_mean": float(np.mean(block_sizes)) if block_sizes else 0.0,
        "cut_tied_names_max": int(max(block_sizes)) if block_sizes else 0,
    }


# --------------------------------------------------------------------------- #
# Old vs new, on the same panel.
# --------------------------------------------------------------------------- #


@dataclass
class Probe:
    label: str
    old: object
    new: object
    book_diff_frac: float
    name_diff_frac: float
    tie: dict
    empty_rebalances: int = 0

    def row(self) -> dict:
        o, nw = self.old, self.new
        # Labels come from `core`, not from the results. The old module inherits the live
        # ENGINE_SHA through `from ..provenance import ...`, so its own `engine_sha`
        # attribute would misreport the code that produced the number.
        return {
            "label": self.label,
            "old": {
                "cagr": o.metrics.cagr,
                "sharpe": o.metrics.sharpe,
                "sortino": o.metrics.sortino,
                "maxdd": o.metrics.max_drawdown,
                "calmar": o.metrics.calmar,
                "turnover": o.metrics.annual_turnover,
                "avg_names": o.diag.get("avg_names", float("nan")),
                "avg_invested_weight": o.diag.get("avg_invested_weight", float("nan")),
                "min_names": o.diag.get("min_names", float("nan")),
                "engine_sha": OLD_ENGINE,
            },
            "new": {
                "cagr": nw.metrics.cagr,
                "sharpe": nw.metrics.sharpe,
                "sortino": nw.metrics.sortino,
                "maxdd": nw.metrics.max_drawdown,
                "calmar": nw.metrics.calmar,
                "turnover": nw.metrics.annual_turnover,
                "avg_names": nw.diag.get("avg_names", float("nan")),
                "avg_invested_weight": nw.diag.get("avg_invested_weight", float("nan")),
                "min_names": nw.diag.get("min_names", float("nan")),
                "engine_sha": nw.engine_sha,
            },
            "delta_cagr_pp": 100.0 * (nw.metrics.cagr - o.metrics.cagr),
            "delta_sharpe": nw.metrics.sharpe - o.metrics.sharpe,
            "delta_maxdd_pp": 100.0 * (nw.metrics.max_drawdown - o.metrics.max_drawdown),
            "book_diff_frac": self.book_diff_frac,
            "name_diff_frac": self.name_diff_frac,
            "tie": self.tie,
            "empty_rebalances": self.empty_rebalances,
        }


def probe(
    label: str,
    px: pd.DataFrame,
    score: pd.DataFrame,
    window: tuple[pd.Timestamp, pd.Timestamp] | None = None,
    config: PortfolioConfig | None = None,
    rebalance: str = "M",
) -> Probe:
    """Run a score panel through both engines and quantify the difference.

    ``book_diff_frac`` -- share of rebalance dates whose *target book* differs at all.
    This is the quantity the tie-break can actually move; a different top-k candidate
    set that converges to the same book after caps and the turnover budget is not a
    different book.
    """
    cfg = config or CONFIG
    if window is not None:
        px = px.loc[window[0] : window[1]]
        score = score.reindex(px.index)

    # The new engine raises `EmptyScorePanelError` on a rebalance date where no name is
    # eligible at all. The old engine swallowed that and returned a flat book, which is
    # indistinguishable downstream from "the strategy chose to sit in cash". Some frozen
    # panels genuinely hit this (RSI at `lower=40` has rebalances with nothing oversold).
    # Filling those dates with 0.0 -- for BOTH engines -- keeps the old-vs-new comparison
    # a clean isolation of the tie-break, while the count is reported separately because
    # "the new engine would refuse to score this panel at all" is its own finding.
    rb_all = [d for d in _rebalance_dates(score.index, rebalance) if d in score.index]
    empty = [
        d
        for d in rb_all[1:]
        if not np.isfinite(
            pd.to_numeric(score.loc[d], errors="coerce").to_numpy(dtype=float)
        ).any()
    ]
    if empty:
        score = score.copy()
        for d in empty:
            score.loc[d] = 0.0

    old = OLD.run_backtest(px, score, COST, cfg, rebalance=rebalance)
    new = run_backtest(px, score, COST, cfg, rebalance=rebalance)

    rb = [d for d in _rebalance_dates(px.index, rebalance) if d in old.weights.index]
    rb = rb[1:]
    diff_b = 0
    diff_n = 0
    for d in rb:
        a = old.weights.loc[d]
        b = new.weights.loc[d]
        diff_b += int(not np.allclose(a.to_numpy(), b.to_numpy(), atol=1e-9))
        diff_n += int(set(a[a > 0].index) != set(b[b > 0].index))
    k = max(len(rb), 1)
    return Probe(
        label=label,
        old=old,
        new=new,
        book_diff_frac=diff_b / k,
        name_diff_frac=diff_n / k,
        tie=tie_exposure(score, cfg.n_positions, rebalance),
        empty_rebalances=len(empty),
    )


def fmt_pr(p: Probe) -> str:
    r = p.row()
    o, n = r["old"], r["new"]
    return (
        f"{p.label:34s} book_diff {r['book_diff_frac']:6.1%} "
        f"cut_tied {r['tie']['cut_tied_frac']:6.1%} "
        f"flat {r['tie']['flat_mask_frac']:6.1%} "
        f"| CAGR {o['cagr']:7.2%} -> {n['cagr']:7.2%} ({r['delta_cagr_pp']:+6.2f}pp) "
        f"| Shp {o['sharpe']:5.2f} -> {n['sharpe']:5.2f} "
        f"| names {o['avg_names']:5.1f} -> {n['avg_names']:5.1f} "
        f"| turn {o['turnover']:5.2f} -> {n['turnover']:5.2f}"
        + (f" [empty_rb={r['empty_rebalances']}]" if r["empty_rebalances"] else "")
    )


def buy_and_hold(window: tuple[pd.Timestamp, pd.Timestamp] | None = None) -> dict:
    """Equal-weight buy-and-hold over the same window, net of the same cost stack."""
    px = panel()
    if window is not None:
        px = px.loc[window[0] : window[1]]
    r = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    from nsealgo.backtest.metrics import compute_metrics

    eq = (1.0 + r).cumprod()
    m = compute_metrics(r, eq)
    return {"cagr": m.cagr, "sharpe": m.sharpe, "maxdd": m.max_drawdown}


TRADING_DAYS = 244
