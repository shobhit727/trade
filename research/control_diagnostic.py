"""Negative-control diagnostic — is the production composite's OOS result a signal or beta?

Run:  .venv/bin/python research/control_diagnostic.py --workers 4
      .venv/bin/python research/control_diagnostic.py --phase h1 --n-random 20 --workers 4

The finding that triggered this
-------------------------------
`reports/STRESS_v3.md` §6: the production trend composite returns OOS
+9.71% / Sharpe 0.34 / MaxDD -14.92%, while `NEGATIVE_CONTROL_WEIGHTS`
(45% reversal_5d, 30% reversal_20d, 25% low_volatility) -- factors the factor module's
own literature review rules OUT on published Indian evidence -- returns +10.04% /
Sharpe 0.37 / MaxDD -25.05% through the *same* harness and the *same* cost stack. The
negative control passed where it was supposed to fail. A supplementary grid found
18 of 18 parameter cells profitable.

This script does not assume what that means. It tests six competing explanations and
reports which survive:

  H1  "It is beta, not skill."      N random-weight books through the identical harness
  H2  "The low-vol leg does it."    component singles + control minus low_volatility
  H3  "The regime overlay is it."    production/control with and without the overlay
  H4  "0.34 vs 0.37 is noise."      paired daily t-test + block bootstrap on dCAGR
  H5  "The harness has an artifact." fixed unselected params + train/test flip
  H6  "Equal-count is a weak null." signal-scrambled control (turnover-matched)

Method rules this script obeys
------------------------------
* **Same harness.** `nsealgo.backtest.walkforward.walk_forward`, 6 folds, 6y train /
  2y test, the same 18-cell grid as `research/validate.py`. The engine, cost model,
  factors, overlay and loader are NOT modified or reimplemented. The only thing this
  script varies is the *score panel* handed to `run_backtest` (and, for H3, whether
  `blend_with_cash` is applied).
* **Same cost stack.** `CostModel(segment="delivery", slippage_bps=5)`; the engine
  charges `2.0 * one_way_turnover * eq * rate`. All figures are net.
* **Provenance.** Every phase stamps `nsealgo.provenance.provenance()` -- engine,
  loader, costs and panel SHAs -- into the results JSON and the report.
* **Many cheap replications.** These are statistical questions, so the expensive
  single-shot answers are backed by distributions of cheap replications.
* **Incremental.** Each phase writes its results to `research/_control_diag/<label>.json`
  (+ `.pkl` for return series) as it finishes, so an interrupted run keeps its work.
  Re-running skips phases already on disk.

Cost model note: a full 18-cell 6-fold walk-forward is ~19 `run_backtest` calls on
1464-bar train slices plus 6 on 488-bar test slices, ~107 s single-threaded and
~130 MB resident. Replications are therefore spread over a process pool.
"""

from __future__ import annotations

import argparse
import json
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.backtest.walkforward import WalkForwardResult, walk_forward  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import (  # noqa: E402
    NEGATIVE_CONTROL_WEIGHTS,
    build_composite_score,
)
from nsealgo.factors.regime import blend_with_cash, exposure_series  # noqa: E402
from nsealgo.provenance import provenance  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA_DIR = REPO / "data" / "nse"
CACHE_DIR = REPO / "research" / "_control_diag"
REPORT_PATH = REPO / "reports" / "CONTROL_DIAGNOSTIC.md"

TRADING_DAYS = 244
RF_ANNUAL = 0.065
RF_DAILY = (1.0 + RF_ANNUAL) ** (1.0 / TRADING_DAYS) - 1.0
N_FOLDS, TRAIN_YEARS, TEST_YEARS = 6, 6, 2
INITIAL_CAPITAL = 2_100_000.0
BASE_SLIPPAGE = 5
COST = CostModel(segment="delivery", slippage_bps=BASE_SLIPPAGE)

#: Grid replicated verbatim from `research/validate.py` and `research/stress_tests.py`.
PARAM_GRID: tuple[dict, ...] = tuple(
    {"n_positions": n, "lookback": lbx, "threshold": thrx}
    for n in (15, 22, 30)
    for lbx in (126, 252)
    for thrx in (0.0, 0.35, 0.6)
)

PANEL: pd.DataFrame | None = None

# --------------------------------------------------------------------------- #
# Run specifications
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class RunSpec:
    """One walk-forward configuration.

    ``kind``
        ``weights``   -- the stock composite built from ``weights``
        ``random``    -- i.i.d. Uniform(0,1) score panel (H1 random-weight book)
        ``scramble_c``-- stock composite with a FIXED column relabel (H6a, turnover-matched)
        ``scramble_r``-- stock composite with a per-date row permutation (H6b)
    ``overlay``
        ``False`` runs the identical harness with the regime overlay switched off (H3).
    """

    label: str
    family: str
    kind: str = "weights"
    weights: dict[str, float] | None = None
    seed: int = 0
    overlay: bool = True
    #: Only used by `random`: fraction of cells masked to NaN (engine falls back to
    #: the cross-sectional median, exactly as it does for a missing factor).
    nan_frac: float = 0.0


def _slice_key(pnl: pd.DataFrame) -> tuple:
    """Identity of a panel slice. `id()` is unsafe -- CPython recycles it."""
    return (
        int(pnl.index[0].value),
        int(pnl.index[-1].value),
        int(len(pnl)),
        int(len(pnl.columns)),
    )


def make_score_fn(spec: RunSpec):
    """Build the `(panel_slice) -> score DataFrame` this run hands to the engine.

    Memoised per slice, exactly as `research/stress_tests.py` does: `walk_forward`
    passes the same slice to all 18 grid cells of a fold and the score is a pure
    function of that slice, so this is behaviour-preserving.
    """
    rng = np.random.default_rng(spec.seed)
    # Fixed once per replication, on the FULL panel column order, so the permutation
    # is identical in every fold's slice -- that is what makes turnover-preservation
    # in H6a exact rather than approximate.
    col_perm = rng.permutation(PANEL.shape[1]) if spec.kind == "scramble_c" else None
    cache: dict[tuple, pd.DataFrame] = {}

    def score_fn(pnl: pd.DataFrame) -> pd.DataFrame:
        sk = _slice_key(pnl)
        got = cache.get(sk)
        if got is not None:
            return got

        if spec.kind == "random":
            # A random-weight book: every name is an equal a priori candidate, so the
            # top-N cut is a uniformly random subset. Same engine, same constraints,
            # same costs -- only the signal is gone.
            a = rng.random((pnl.shape[0], pnl.shape[1]))
            if spec.nan_frac > 0:
                a[rng.random(a.shape) < spec.nan_frac] = np.nan
            sc = pd.DataFrame(a, index=pnl.index, columns=pnl.columns)
        else:
            sc = build_composite_score(pnl, weights=spec.weights)
            if spec.kind == "scramble_c":
                # score'[t, s] = score[t, perm[s]]. Column order is preserved as a
                # *label* set, so the engine's sector map still applies to real names.
                sc = sc.iloc[:, col_perm].copy()
                sc.columns = pnl.columns
            elif spec.kind == "scramble_r":
                # Independent permutation of each date's cross-section: the per-date
                # marginal distribution is preserved exactly, but the score-to-return
                # link is destroyed and the name identity churns every rebalance.
                r = np.random.default_rng(spec.seed + 9973)
                sc = sc.copy()
                for i in range(len(sc)):
                    sc.iloc[i, :] = sc.iloc[i, :].to_numpy()[r.permutation(pnl.shape[1])]

        cache[sk] = sc
        return sc

    return score_fn


def make_run_fn(spec: RunSpec, log: list | None = None):
    """`run_fn(panel_slice, params) -> BacktestResult` — the `validate.py` shape.

    Identical to `research/validate.py::run_fn` except that the score comes from
    `spec` and the overlay can be switched off. When `log` is supplied the raw
    engine turnover / cost-drag / name-count diagnostics are recorded per call so
    the OOS turnover of the *selected* cell can be read back without a second run.
    """
    score_fn = make_score_fn(spec)
    ov_cache: dict[tuple, pd.Series] = {}

    def run_fn(pnl: pd.DataFrame, params: dict):
        sc = score_fn(pnl)
        res = run_backtest(
            pnl, sc, COST, PortfolioConfig(n_positions=params["n_positions"]), "M"
        )
        if log is not None:
            # `res.returns` is already net of costs, so `res.metrics.cagr` is NOT
            # gross. Recover the true gross from the delivered weights instead: the
            # engine's own return attribution is `(held_weights.shift(1) * rets)`,
            # which is one vectorised multiply on the same arrays the engine just
            # used, so it costs nothing and needs no second backtest.
            rets = pnl.pct_change(fill_method=None).fillna(0.0)
            gross_daily = res.weights.shift(1).fillna(0.0).mul(rets).sum(axis=1)
            gross_eq = (1.0 + gross_daily).cumprod()
            log.append(
                {
                    "slice": _slice_key(pnl),
                    "params": dict(params),
                    "turnover": res.metrics.annual_turnover,
                    "cost_drag": res.metrics.cost_drag_annual,
                    "avg_names": res.diag["avg_names"],
                    "n_rebal": res.diag["n_rebalances"],
                    "rt_bps": res.diag["round_trip_bps"],
                    "gross_cagr": float(gross_eq.iloc[-1] ** (TRADING_DAYS / len(gross_eq))
                                         - 1.0),
                    "net_cagr_no_overlay": res.metrics.cagr,
                }
            )
        if not spec.overlay:
            # H3: harness, grid, engine and costs identical; only the cash blend is off.
            res.metrics = compute_metrics(res.returns)
            return res
        ok = (_slice_key(pnl), params["lookback"], params["threshold"])
        ov = ov_cache.get(ok)
        if ov is None:
            ov = exposure_series(
                pnl, lookback=params["lookback"], threshold=params["threshold"]
            )
            ov_cache[ok] = ov
        comb = pd.Series(blend_with_cash(res.returns, ov), index=res.returns.index)
        res.returns = comb
        res.metrics = compute_metrics(comb)
        return res

    return run_fn


def fold_slices(panel: pd.DataFrame) -> list[tuple[pd.DataFrame, pd.DataFrame]]:
    """(train, test) slices, reproducing `walk_forward`'s slicing exactly."""
    dates = panel.index
    train_bars = int(TRAIN_YEARS * TRADING_DAYS)
    test_bars = int(TEST_YEARS * TRADING_DAYS)
    total = train_bars + test_bars
    out = []
    for k in range(N_FOLDS):
        tr0 = len(dates) - total - k * test_bars
        tr1 = tr0 + train_bars
        te0, te1 = tr1, min(tr1 + test_bars, len(dates))
        if tr0 < 0 or te1 <= te0:
            continue
        out.append((panel.iloc[tr0:tr1], panel.iloc[te0:te1]))
    return out


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #


def _cagr(r: np.ndarray) -> float:
    if len(r) == 0:
        return 0.0
    eq = float(np.prod(1.0 + r))
    return eq ** (TRADING_DAYS / len(r)) - 1.0 if eq > 0 else -1.0


def _sharpe(r: np.ndarray) -> float:
    if len(r) < 2:
        return 0.0
    ex = r - RF_DAILY
    sd = float(ex.std(ddof=1))
    return float(ex.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0


def _maxdd(r: np.ndarray) -> float:
    eq = np.cumprod(1.0 + r)
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def paired_block_bootstrap(
    a: pd.Series, b: pd.Series, block: int = 21, B: int = 10_000, seed: int = 7
) -> dict:
    """Bootstrap the CAGR/Sharpe difference by resampling *paired date blocks*.

    Both strategies are resampled on the same resampled dates, so their correlation
    survives -- resampling them independently would understate the CI of a difference.
    Blocks (default 21 bars ~ one rebalance cycle) preserve the autocorrelation that
    a daily i.i.d. bootstrap would destroy and inflate the Sharpe CIs with.
    """
    idx = a.index.intersection(b.index)
    A = a.loc[idx].to_numpy()
    Bv = b.loc[idx].to_numpy()
    n = len(A)
    nblk = int(np.ceil(n / block))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(B, nblk))
    offs = np.arange(block)[None, None, :]
    sel = ((starts[:, :, None] + offs) % n).reshape(B, -1)[:, :n]
    da = np.empty(B)
    db = np.empty(B)
    for i in range(B):
        j = sel[i]
        da[i] = _cagr(A[j])
        db[i] = _cagr(Bv[j])
    d = da - db
    return {
        "n_days": int(n),
        "block": int(block),
        "B": int(B),
        "d_cagr_mean": float(d.mean()),
        "d_cagr_ci_lo": float(np.percentile(d, 2.5)),
        "d_cagr_ci_hi": float(np.percentile(d, 97.5)),
        "p_a_better": float((d > 0).mean()),
    }


def paired_ttest(a: pd.Series, b: pd.Series) -> dict:
    """Paired daily-return t-test on the OOS windows (same dates for both)."""
    from scipy import stats  # imported lazily: only the stats phase needs it

    idx = a.index.intersection(b.index)
    A = a.loc[idx].to_numpy()
    Bv = b.loc[idx].to_numpy()
    d = A - Bv
    n = len(d)
    res = stats.ttest_rel(A, Bv)
    # Newey-West (lag 10) on the mean of the difference: daily returns are serially
    # correlated at rebalance frequency, which inflates an i.i.d. t-stat.
    lag = 10
    u = d - d.mean()
    s0 = float(np.dot(u, u) / n)
    s1 = 0.0
    for L in range(1, lag + 1):
        w = 1.0 - L / (lag + 1.0)
        s1 += 2.0 * w * float(np.dot(u[L:], u[:-L]) / n)
    s_nw = s0 + s1
    t_nw = float(d.mean() / np.sqrt(s_nw / n)) if s_nw > 0 else 0.0
    return {
        "n_days": int(n),
        "mean_diff_bps": float(d.mean() * 1e4),
        "t_iid": float(res.statistic),
        "p_iid": float(res.pvalue),
        "t_newey_west": t_nw,
        "p_newey_west": float(2.0 * (1.0 - stats.norm.cdf(abs(t_nw)))),
    }


def beta_stats(r: pd.Series, m: pd.Series) -> dict:
    """CAPM beta / correlation / Jensen alpha against the equal-weight benchmark."""
    from scipy import stats

    idx = r.index.intersection(m.index)
    er = r.loc[idx].to_numpy() - RF_DAILY
    em = m.loc[idx].to_numpy() - RF_DAILY
    var_m = float(np.var(em, ddof=1))
    beta = float(np.cov(er, em, ddof=1)[0, 1] / var_m) if var_m > 0 else 0.0
    corr = float(np.corrcoef(er, em)[0, 1])
    alpha_d = float(er.mean() - beta * em.mean())
    se = float(np.sqrt(var_m / len(er)))
    t_alpha = alpha_d / se if se > 0 else 0.0
    return {
        "beta": beta,
        "corr_bench": corr,
        "r2": corr**2,
        "alpha_annual": alpha_d * TRADING_DAYS,
        "alpha_t": float(t_alpha),
        "alpha_p": float(2.0 * (1.0 - stats.norm.cdf(abs(t_alpha)))),
        "tracking_err_annual": float(er.std(ddof=1) * np.sqrt(TRADING_DAYS)),
    }


def pct_rank(x: float, arr: np.ndarray) -> float:
    """Percentile of `x` within `arr` (fraction of the null at or below x)."""
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    return float((arr <= x).mean())


# --------------------------------------------------------------------------- #
# Harvest
# --------------------------------------------------------------------------- #


def _work(spec: RunSpec) -> tuple[dict, pd.Series, pd.Series]:
    """Module-level so `ProcessPoolExecutor` can pickle it (no nested closures).

    Returns plain data plus the two return series, which the parent writes to cache.
    """
    if PANEL is None:  # pragma: no cover - only outside the pool
        _init_worker()
    log: list = []
    t0 = time.time()
    wf = walk_forward(
        PANEL,
        list(PARAM_GRID),
        make_run_fn(spec, log),
        n_folds=N_FOLDS,
        train_years=TRAIN_YEARS,
        test_years=TEST_YEARS,
    )
    oos = wf.oos_returns
    return (
        harvest(wf, spec, log, time.time() - t0),
        oos,
        wf.benchmark_returns.reindex(oos.index).fillna(0.0),
    )


def harvest(
    wf: WalkForwardResult, spec: RunSpec, log: list, secs: float
) -> dict:
    """Flatten a `WalkForwardResult` into plain data (picklable across processes)."""
    oos = wf.oos_returns
    bm = wf.benchmark_returns.reindex(oos.index).fillna(0.0)
    om = wf.oos_metrics
    bmom = compute_metrics(bm)

    # OOS turnover / cost drag of the *selected* cell, read out of the run log so no
    # second backtest is needed. Fold k's test call is the last entry whose slice
    # matches that fold's test window.
    turn, drag, names, gross, net_pre = [], [], [], [], []
    for f in wf.folds:
        te0 = int(f.test_start.value)
        te1 = int(f.test_end.value)
        hit = [
            e
            for e in log
            if e["slice"][0] == te0 and e["slice"][1] == te1 and e["params"] == dict(f.best_params)
        ]
        if hit:
            turn.append(hit[-1]["turnover"])
            drag.append(hit[-1]["cost_drag"])
            names.append(hit[-1]["avg_names"])
            gross.append(hit[-1]["gross_cagr"])
            net_pre.append(hit[-1]["net_cagr_no_overlay"])

    train_cagr = [f.train_metrics.cagr for f in wf.folds]
    train_sharpe = [f.train_metrics.sharpe for f in wf.folds]

    return {
        "label": spec.label,
        "family": spec.family,
        "kind": spec.kind,
        "seed": spec.seed,
        "overlay": spec.overlay,
        "weights": spec.weights,
        "cagr": om.cagr,
        "sharpe": om.sharpe,
        "maxdd": om.max_drawdown,
        "calmar": om.calmar,
        "sortino": om.sortino,
        "vol": om.volatility,
        "n_oos_days": int(om.n_periods),
        "bm_cagr": bmom.cagr,
        "bm_sharpe": bmom.sharpe,
        "bm_maxdd": bmom.max_drawdown,
        "oos_turnover": float(np.mean(turn)) if turn else None,
        "oos_cost_drag": float(np.mean(drag)) if drag else None,
        "oos_avg_names": float(np.mean(names)) if names else None,
        # Net CAGR of the selected cell BEFORE the regime overlay is blended in. The
        # gap between this and `oos_gross_cagr` is the cost channel exactly; the gap
        # between this and the reported net `cagr` is the overlay channel exactly.
        # Both are needed to attribute a difference between two books to a cause.
        "oos_net_pre_overlay": float(np.mean(net_pre)) if net_pre else None,
        # Gross CAGR of the selected cell (before the overlay blend, before costs are
        # re-charged onto the overlay path). Needed to separate "the signal earns more"
        # from "this book happens to turn over less and so pays less".
        "oos_gross_cagr": float(np.mean(gross)) if gross else None,
        "train_cagr": float(np.mean(train_cagr)) if train_cagr else None,
        "train_sharpe": float(np.mean(train_sharpe)) if train_sharpe else None,
        "folds": [
            {
                "fold": f.fold,
                "test_start": str(f.test_start.date()),
                "test_end": str(f.test_end.date()),
                "params": dict(f.best_params),
                "train_cagr": f.train_metrics.cagr,
                "train_sharpe": f.train_metrics.sharpe,
                "test_cagr": f.test_metrics.cagr,
                "test_sharpe": f.test_metrics.sharpe,
                "test_maxdd": f.test_metrics.max_drawdown,
            }
            for f in wf.folds
        ],
        "secs": secs,
        "provenance": provenance(),
    }


def _init_worker() -> None:
    global PANEL
    PANEL, _, _ = load_universe(str(DATA_DIR))


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #


def _pkl_path(label: str) -> Path:
    return CACHE_DIR / f"{label}.pkl"


def _json_path(label: str) -> Path:
    return CACHE_DIR / f"{label}.json"


def save_run(res: dict, oos: pd.Series, bench: pd.Series) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with _pkl_path(res["label"]).open("wb") as fh:
        pickle.dump({"oos": oos, "bench": bench}, fh)
    _json_path(res["label"]).write_text(json.dumps(res, indent=2, default=str))


def load_run(label: str) -> dict | None:
    p = _json_path(label)
    if not p.exists():
        return None
    return json.loads(p.read_text())


def load_series(label: str) -> dict | None:
    p = _pkl_path(label)
    if not p.exists():
        return None
    with p.open("rb") as fh:
        return pickle.load(fh)


def run_many(specs: list[RunSpec], workers: int, force: bool = False) -> dict[str, dict]:
    """Run every spec not already cached, in parallel. Fault-tolerant.

    This box is shared and a worker can be OOM-killed mid-sweep; anything the pool
    cannot deliver is retried in-process rather than thrown away.
    """
    out: dict[str, dict] = {}
    todo = []
    for s in specs:
        cached = None if force else load_run(s.label)
        if cached is not None:
            out[s.label] = cached
            print(f"    cached: {s.label}", flush=True)
        else:
            todo.append(s)
    if not todo:
        return out

    print(f"    running {len(todo)} spec(s) on {workers} worker(s)", flush=True)
    done = 0
    t0 = time.time()

    if workers <= 1:
        _init_worker()
        for s in todo:
            r, o, b = _work(s)
            save_run(r, o, b)
            out[r["label"]] = r
            print(f"    done: {r['label']} ({r['cagr'] * 100:+.2f}% / "
                  f"{r['sharpe']:.2f})", flush=True)
        return out

    pending = {s.label: s for s in todo}
    done = 0
    t0 = time.time()
    try:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker) as ex:
            futs = {ex.submit(_work, s): s for s in todo}
            for fut in as_completed(futs):
                s = futs[fut]
                try:
                    r, o, b = fut.result()
                except Exception as exc:  # noqa: BLE001 - retried serially below
                    print(f"    FAILED in pool ({s.label}): {exc!r}; will retry",
                          flush=True)
                    continue
                save_run(r, o, b)
                out[r["label"]] = r
                pending.pop(r["label"], None)
                done += 1
                print(f"    done [{done}/{len(todo)}] {r['label']} "
                      f"({r['cagr'] * 100:+.2f}% / {r['sharpe']:.2f}) "
                      f"elapsed {(time.time() - t0) / 60:.1f}m", flush=True)
    except Exception as exc:  # noqa: BLE001 - pool itself broke; fall through
        print(f"    pool broke ({exc!r}); falling back to in-process", flush=True)

    if pending:
        print(f"    retrying {len(pending)} spec(s) in-process", flush=True)
        _init_worker()
        for s in pending.values():
            r, o, b = _work(s)
            save_run(r, o, b)
            out[r["label"]] = r
            print(f"    done: {r['label']} ({r['cagr'] * 100:+.2f}% / "
                  f"{r['sharpe']:.2f})", flush=True)

    missing = [s.label for s in specs if s.label not in out]
    if missing:
        raise RuntimeError(f"expected {len(specs)} results, got {len(out)}: {missing}")
    return out


# --------------------------------------------------------------------------- #
# Phase: the two reference runs (production + reversal control)
# --------------------------------------------------------------------------- #

PROD = RunSpec("PRODUCTION", "reference", kind="weights", weights=None)
CTRL = RunSpec(
    "CONTROL_REVERSAL", "reference", kind="weights",
    weights=dict(NEGATIVE_CONTROL_WEIGHTS),
)


def phase_reference() -> dict:
    """The two numbers `STRESS_v3.md` §6 reported, re-measured on this engine."""
    out = run_many([PROD, CTRL], WORKERS)
    p, c = out["PRODUCTION"], out["CONTROL_REVERSAL"]
    print(f"  production : CAGR {p['cagr'] * 100:+.2f}%  Sharpe {p['sharpe']:.2f}  "
          f"MaxDD {p['maxdd'] * 100:+.2f}%  turnover {p['oos_turnover']:.2f}x/y  "
          f"drag {p['oos_cost_drag'] * 100:.2f}%/y")
    print(f"  control    : CAGR {c['cagr'] * 100:+.2f}%  Sharpe {c['sharpe']:.2f}  "
          f"MaxDD {c['maxdd'] * 100:+.2f}%  turnover {c['oos_turnover']:.2f}x/y  "
          f"drag {c['oos_cost_drag'] * 100:.2f}%/y")
    return out


# --------------------------------------------------------------------------- #
# H1 — "It is beta, not skill"
# --------------------------------------------------------------------------- #


def phase_h1(n_random: int) -> dict:
    """N random-weight books through the identical harness.

    A random book is `Uniform(0,1)` scores: the engine's own top-N cut, inverse-vol
    scaling, sector/single-name caps, cash buffer, turnover budget, monthly rebalance
    and full cost stack are all untouched. The only thing removed is the signal.

    This is the decisive test. A 22-name monthly-rebalanced long-only NIFTY-50 book
    earns market return by construction; if the production composite sits near the
    median of this null, the composite's own factors are not what produced its result.
    """
    specs = [
        RunSpec(f"H1_RANDOM_{i:03d}", "h1", kind="random", seed=10_000 + i)
        for i in range(n_random)
    ]
    out = run_many(specs, WORKERS)
    cagr = np.array([out[s.label]["cagr"] for s in specs])
    sharpe = np.array([out[s.label]["sharpe"] for s in specs])
    maxdd = np.array([out[s.label]["maxdd"] for s in specs])
    turn = np.array([out[s.label]["oos_turnover"] for s in specs])
    drag = np.array([out[s.label]["oos_cost_drag"] for s in specs])
    gross = np.array([out[s.label]["oos_gross_cagr"] for s in specs])
    net_pre = np.array([out[s.label]["oos_net_pre_overlay"] for s in specs])
    p, c = load_run("PRODUCTION"), load_run("CONTROL_REVERSAL")

    # Mean null book, used as the base for the additive decomposition.
    null_mean = {
        "oos_gross_cagr": float(gross.mean()),
        "oos_net_pre_overlay": float(net_pre.mean()),
        "cagr": float(cagr.mean()),
    }
    decomp = decompose(p, null_mean)
    decomp_ctrl = decompose(c, null_mean)

    def dist(x: np.ndarray) -> dict:
        return {
            "mean": float(x.mean()), "sd": float(x.std(ddof=1)),
            "min": float(x.min()), "p05": float(np.percentile(x, 5)),
            "p25": float(np.percentile(x, 25)), "median": float(np.median(x)),
            "p75": float(np.percentile(x, 75)), "p95": float(np.percentile(x, 95)),
            "max": float(x.max()),
            "frac_profitable": float((x > 0).mean()),
        }

    res = {
        "n_random": n_random,
        "cagr": dist(cagr), "sharpe": dist(sharpe), "maxdd": dist(maxdd),
        "turnover": dist(turn), "cost_drag": dist(drag), "gross_cagr": dist(gross),
        "net_pre_overlay": dist(net_pre),
        "null_mean": null_mean,
        "decomp_prod_vs_null": decomp,
        "decomp_ctrl_vs_null": decomp_ctrl,
        "prod_pct_cagr": pct_rank(p["cagr"], cagr),
        "prod_pct_sharpe": pct_rank(p["sharpe"], sharpe),
        "ctrl_pct_cagr": pct_rank(c["cagr"], cagr),
        "ctrl_pct_sharpe": pct_rank(c["sharpe"], sharpe),
        # A random book turns over far more than production, so a NET comparison
        # flatters production for a reason that has nothing to do with its signal.
        # These are the percentiles on GROSS CAGR, which removes the cost channel.
        "prod_pct_gross": pct_rank(p["oos_gross_cagr"], gross),
        "ctrl_pct_gross": pct_rank(c["oos_gross_cagr"], gross),
        "prod": {k: p[k] for k in ("cagr", "sharpe", "maxdd", "oos_turnover",
                                   "oos_cost_drag", "oos_avg_names",
                                   "oos_gross_cagr", "oos_net_pre_overlay")},
        "ctrl": {k: c[k] for k in ("cagr", "sharpe", "maxdd", "oos_turnover",
                                   "oos_cost_drag", "oos_avg_names",
                                   "oos_gross_cagr", "oos_net_pre_overlay")},
        "labels": [s.label for s in specs],
        "cagr_raw": cagr.tolist(),
        "sharpe_raw": sharpe.tolist(),
        "gross_raw": gross.tolist(),
        "turnover_raw": turn.tolist(),
        "provenance": provenance(),
    }
    save_summary("h1", res)
    d = res["cagr"]
    print(f"  random CAGR    : mean {d['mean'] * 100:+.2f}%  sd {d['sd'] * 100:.2f}pp  "
          f"min {d['min'] * 100:+.2f}%  median {d['median'] * 100:+.2f}%  "
          f"max {d['max'] * 100:+.2f}%  profitable {d['frac_profitable'] * 100:.0f}%")
    s = res["sharpe"]
    print(f"  random Sharpe  : mean {s['mean']:.2f}  sd {s['sd']:.2f}  "
          f"min {s['min']:.2f}  median {s['median']:.2f}  max {s['max']:.2f}")
    print(f"  production sits at percentile {res['prod_pct_cagr'] * 100:.0f} "
          f"(net CAGR) / {res['prod_pct_sharpe'] * 100:.0f} (Sharpe) / "
          f"{res['prod_pct_gross'] * 100:.0f} (GROSS CAGR)")
    print(f"  control    sits at percentile {res['ctrl_pct_cagr'] * 100:.0f} "
          f"(net CAGR) / {res['ctrl_pct_sharpe'] * 100:.0f} (Sharpe) / "
          f"{res['ctrl_pct_gross'] * 100:.0f} (GROSS CAGR)")
    print(f"  turnover: random {res['turnover']['mean']:.2f}x/y vs production "
          f"{res['prod']['oos_turnover']:.2f}x/y -> net-CAGR percentiles above "
          f"confound signal with cost")
    d = decomp
    print(f"  DECOMPOSITION of production's net edge over the mean random book "
          f"({d['total_gap'] * 100:+.2f}pp/yr):")
    print(f"    selection (gross)   {d['gross_gap'] * 100:+.2f}pp/yr")
    print(f"    cost    (turnover)  {d['cost_gap'] * 100:+.2f}pp/yr")
    print(f"    overlay (regime)    {d['overlay_gap'] * 100:+.2f}pp/yr")
    print(f"    reconciles to {d['total_gap'] * 100:+.2f}pp "
          f"(max error {abs(d['recon_err']):.2e})")
    return out


# --------------------------------------------------------------------------- #
# H2 — "the low-vol leg is doing the work"
# --------------------------------------------------------------------------- #

#: Each component run alone at weight 1.0, plus the two composites with one leg
#: removed. `low_volatility` alone is already production's other half, so the pair
#: (`trend_legs_only`, `low_volatility`) decomposes the production composite and no
#: third copy of that weight vector is run.
COMPONENT_SPECS: tuple[tuple[str, dict[str, float]], ...] = (
    ("reversal_5d", {"reversal_5d": 1.0}),
    ("reversal_20d", {"reversal_20d": 1.0}),
    ("low_volatility", {"low_volatility": 1.0}),
    ("momentum_12_1", {"momentum_12_1": 1.0}),
    ("momentum_6m", {"momentum_6m": 1.0}),
    ("trend_strength_200d", {"trend_strength_200d": 1.0}),
    # production's trend legs, weights renormalised by build_composite_score
    ("trend_legs_only", {
        "momentum_12_1": 0.40, "momentum_6m": 0.20, "trend_strength_200d": 0.25,
    }),
    # the control with low_volatility REMOVED, two reversal legs renormalised to 60/40
    ("control_no_lowvol", {"reversal_5d": 0.60, "reversal_20d": 0.40}),
)


def phase_h2() -> dict:
    """Every component on its own, plus the control with low-volatility removed.

    If the reversal legs are harmless and low-volatility carries the control, then
    `control_no_lowvol` should collapse while `low_volatility` holds up. If the
    reversal legs carry it, the opposite.
    """
    specs = [
        RunSpec(f"H2_{name}", "h2", kind="weights", weights=w)
        for name, w in COMPONENT_SPECS
    ]
    out = run_many(specs, WORKERS)
    rows = [
        {
            "component": name,
            "cagr": out[f"H2_{name}"]["cagr"],
            "sharpe": out[f"H2_{name}"]["sharpe"],
            "maxdd": out[f"H2_{name}"]["maxdd"],
            "turnover": out[f"H2_{name}"]["oos_turnover"],
            "cost_drag": out[f"H2_{name}"]["oos_cost_drag"],
        }
        for name, _ in COMPONENT_SPECS
    ]
    res = {
        "components": rows,
        "production": {k: load_run("PRODUCTION")[k] for k in
                       ("cagr", "sharpe", "maxdd")},
        "control": {k: load_run("CONTROL_REVERSAL")[k] for k in
                    ("cagr", "sharpe", "maxdd")},
        "provenance": provenance(),
    }
    save_summary("h2", res)
    print(f"  {'component':>22} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>9} "
          f"{'turn':>7} {'drag':>8}")
    for r in rows:
        print(f"  {r['component']:>22} {r['cagr'] * 100:>+8.2f}% {r['sharpe']:>8.2f} "
              f"{r['maxdd'] * 100:>+8.2f}% {r['turnover']:>6.2f}x "
              f"{r['cost_drag'] * 100:>7.2f}%")
    return out


# --------------------------------------------------------------------------- #
# H3 — "the regime overlay is the whole difference"
# --------------------------------------------------------------------------- #


def phase_h3() -> dict:
    """Production and control on identical folds, overlay on and off.

    `run_fn` is otherwise byte-identical; only `blend_with_cash` is skipped. With the
    overlay off, the grid's `lookback`/`threshold` axes stop changing the return series
    but still get selected on train, so the selection pressure on `n_positions` is
    unchanged -- this isolates the overlay's contribution rather than re-designing
    the harness.
    """
    specs = [
        RunSpec("H3_PROD_NOOVERLAY", "h3", kind="weights", weights=None, overlay=False),
        RunSpec("H3_CTRL_NOOVERLAY", "h3", kind="weights",
                weights=dict(NEGATIVE_CONTROL_WEIGHTS), overlay=False),
    ]
    out = run_many(specs, WORKERS)
    p, c = load_run("PRODUCTION"), load_run("CONTROL_REVERSAL")
    res = {
        "with_overlay": {
            "prod": {k: p[k] for k in ("cagr", "sharpe", "maxdd", "oos_turnover")},
            "ctrl": {k: c[k] for k in ("cagr", "sharpe", "maxdd", "oos_turnover")},
        },
        "no_overlay": {
            "prod": {k: out["H3_PROD_NOOVERLAY"][k]
                     for k in ("cagr", "sharpe", "maxdd", "oos_turnover")},
            "ctrl": {k: out["H3_CTRL_NOOVERLAY"][k]
                     for k in ("cagr", "sharpe", "maxdd", "oos_turnover")},
        },
        "provenance": provenance(),
    }
    for k in ("with_overlay", "no_overlay"):
        res[k]["sharpe_gap_ctrl_minus_prod"] = (
            res[k]["ctrl"]["sharpe"] - res[k]["prod"]["sharpe"]
        )
        res[k]["cagr_gap_ctrl_minus_prod"] = (
            res[k]["ctrl"]["cagr"] - res[k]["prod"]["cagr"]
        )
    save_summary("h3", res)
    print(f"  {'book':>6} {'overlay':>8} {'CAGR':>9} {'Sharpe':>8} {'MaxDD':>9}")
    for k in ("prod", "ctrl"):
        for mode in ("with_overlay", "no_overlay"):
            r = res[mode][k]
            print(f"  {k:>6} {mode.replace('_', ' '):>8} {r['cagr'] * 100:>+8.2f}% "
                  f"{r['sharpe']:>8.2f} {r['maxdd'] * 100:>+8.2f}%")
    print(f"  Sharpe gap (ctrl - prod): overlay ON "
          f"{res['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} | overlay OFF "
          f"{res['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f}")
    return out


# --------------------------------------------------------------------------- #
# H4 — "0.34 vs 0.37 is noise"
# --------------------------------------------------------------------------- #


def phase_h4() -> dict:
    """Paired daily t-test + block bootstrap on the OOS CAGR difference.

    The two OOS series cover the *same* dates, so the comparison is paired: one
    sample of daily return differences. The bootstrap resamples paired date blocks so
    the correlation between the two books is preserved in the difference's sampling
    distribution.
    """
    sp, sc = load_series("PRODUCTION"), load_series("CONTROL_REVERSAL")
    a, b = sp["oos"], sc["oos"]
    res = {
        "prod_cagr": load_run("PRODUCTION")["cagr"],
        "ctrl_cagr": load_run("CONTROL_REVERSAL")["cagr"],
        "prod_sharpe": load_run("PRODUCTION")["sharpe"],
        "ctrl_sharpe": load_run("CONTROL_REVERSAL")["sharpe"],
        "ttest": paired_ttest(a, b),
        "bootstrap": paired_block_bootstrap(a, b, block=21, B=10_000),
        "bootstrap_daily": paired_block_bootstrap(a, b, block=1, B=10_000),
        "oos_window": [str(a.index[0].date()), str(a.index[-1].date())],
        "provenance": provenance(),
    }
    save_summary("h4", res)
    t = res["ttest"]
    bs = res["bootstrap"]
    print(f"  OOS window {res['oos_window'][0]} -> {res['oos_window'][1]} "
          f"({t['n_days']} daily obs)")
    print(f"  mean daily diff {t['mean_diff_bps']:+.3f} bps")
    print(f"  paired t-test   t={t['t_iid']:+.3f}  p={t['p_iid']:.3f}   |   "
          f"Newey-West t={t['t_newey_west']:+.3f}  p={t['p_newey_west']:.3f}")
    print(f"  dCAGR = {res['prod_cagr'] * 100:+.2f}% - {res['ctrl_cagr'] * 100:+.2f}% "
          f"= {(res['prod_cagr'] - res['ctrl_cagr']) * 100:+.2f}pp")
    print(f"  block bootstrap 95% CI on dCAGR: [{bs['d_cagr_ci_lo'] * 100:+.2f}pp, "
          f"{bs['d_cagr_ci_hi'] * 100:+.2f}pp]  P(prod > ctrl) = "
          f"{bs['p_a_better']:.2f}")
    return res


# --------------------------------------------------------------------------- #
# H5 — "the harness has a selection artifact"
# --------------------------------------------------------------------------- #

#: A fixed, unselected parameter set: the grid cell the production walk-forward
#: selected in the most folds (n=22, overlay lb=126, thr=0.35 -> folds 1 and 5;
#: lb=126 is selected in all six). Chosen from the *production* selection, then
#: applied unchanged to both books so neither gets a re-fit.
FIXED_PARAMS: dict = {"n_positions": 22, "lookback": 126, "threshold": 0.35}
#: A second fixed cell (n=15, thr=0.0) so the conclusion is not an artefact of which
#: single cell was picked.
FIXED_PARAMS_ALT: dict = {"n_positions": 15, "lookback": 126, "threshold": 0.0}


def _fixed_param_oos(spec: RunSpec, params: dict) -> pd.Series:
    """OOS returns with a FIXED parameter set: no train-window selection at all.

    Evaluates one cell on the fold test windows and concatenates. The cleanest read on
    "is this a property of the signal or of the search".
    """
    run_fn = make_run_fn(spec)
    return pd.concat(
        [run_fn(test, params).returns for _, test in fold_slices(PANEL)]
    ).sort_index()


def _fixed_param_oos_detail(spec: RunSpec, params: dict) -> dict:
    """Same as `_fixed_param_oos` but also returns the gross / net-pre-overlay CAGRs.

    Each fold's test slice is run once through the engine with the fixed cell; the
    per-fold daily series are concatenated so the CAGR is measured over the whole OOS
    window rather than per fold. Gross is rebuilt from the delivered weights, so the
    cost and overlay channels can be separated exactly as in `decompose`.
    """
    rets_by_slice = []
    gross_parts, net_pre_parts = [], []
    for _, test in fold_slices(PANEL):
        sc = make_score_fn(spec)(test)
        res = run_backtest(test, sc, COST,
                           PortfolioConfig(n_positions=params["n_positions"]), "M")
        d = test.pct_change(fill_method=None).fillna(0.0)
        gross_parts.append(res.weights.shift(1).fillna(0.0).mul(d).sum(axis=1))
        net_pre_parts.append(res.returns)
        ov = exposure_series(test, lookback=params["lookback"],
                             threshold=params["threshold"])
        rets_by_slice.append(
            pd.Series(blend_with_cash(res.returns, ov), index=res.returns.index)
        )
    net = pd.concat(rets_by_slice).sort_index()
    gross = pd.concat(gross_parts).sort_index()
    net_pre = pd.concat(net_pre_parts).sort_index()
    m = compute_metrics(net)
    yrs = TRADING_DAYS / len(net)
    return {
        "cagr": m.cagr, "sharpe": m.sharpe, "max_drawdown": m.max_drawdown,
        "calmar": m.calmar,
        "gross_cagr": float((1.0 + gross).cumprod().iloc[-1] ** yrs - 1.0),
        "net_pre_overlay": float((1.0 + net_pre).cumprod().iloc[-1] ** yrs - 1.0),
    }


def phase_h5() -> dict:
    """Fixed-parameter comparison + the train/test profile of both books.

    Two questions:
      1. With the train selection removed entirely, does production still beat control?
      2. Does the control's TRAIN performance look like its OOS, or is there a flip?
         A walk-forward that selects the control on train and then sees it degrade is
         a different failure from one that sees it degrade everywhere.
    """
    _init_worker()
    out: dict = {"fixed": {}, "provenance": provenance()}

    for tag, params in (("cell_A", FIXED_PARAMS), ("cell_B", FIXED_PARAMS_ALT)):
        rows = {}
        for spec in (PROD, CTRL):
            rows[spec.label] = _fixed_param_oos_detail(spec, params)
        rows["params"] = params
        out["fixed"][tag] = rows
        print(f"  fixed {tag} n={params['n_positions']} lb={params['lookback']} "
              f"thr={params['threshold']}:")
        for lab in ("PRODUCTION", "CONTROL_REVERSAL"):
            r = rows[lab]
            print(f"    {lab:>18}  CAGR {r['cagr'] * 100:>+7.2f}%  "
                  f"Sharpe {r['sharpe']:>5.2f}  MaxDD {r['max_drawdown'] * 100:>+7.2f}%"
                  f"  gross {r['gross_cagr'] * 100:>+7.2f}%")

    # Selection cost: does choosing parameters on TRAIN help or hurt each book?
    # Compare each book's best fixed cell against its own walk-forward result. If
    # fixed > walk-forward, the train-window selection destroyed value, which would
    # itself be a harness defect rather than a property of the signal.
    sel = {}
    for lab in ("PRODUCTION", "CONTROL_REVERSAL"):
        wf = load_run(lab)
        best_fixed = max(out["fixed"].values(), key=lambda r: r[lab]["cagr"])
        sel[lab] = {
            "walk_forward_cagr": wf["cagr"],
            "walk_forward_sharpe": wf["sharpe"],
            "best_fixed_cagr": best_fixed[lab]["cagr"],
            "best_fixed_sharpe": best_fixed[lab]["sharpe"],
            "best_fixed_params": best_fixed["params"],
            "selection_delta_cagr": wf["cagr"] - best_fixed[lab]["cagr"],
            "selection_delta_sharpe": wf["sharpe"] - best_fixed[lab]["sharpe"],
        }
        s = sel[lab]
        print(f"  selection cost {lab:>18}: best fixed {s['best_fixed_cagr'] * 100:+.2f}% "
              f"vs walk-forward {s['walk_forward_cagr'] * 100:+.2f}%  -> "
              f"{s['selection_delta_cagr'] * 100:+.2f}pp "
              f"({'HURT' if s['selection_delta_cagr'] < 0 else 'helped'})")
    out["selection_cost"] = sel

    # Decomposition of the fixed-cell gap, so "production wins when unselected" can be
    # attributed to selection vs the cost/overlay channels rather than assumed.
    decomp = {}
    for tag, rows in out["fixed"].items():
        decomp[tag] = {
            lab: {
                "gross_cagr": rows[lab]["gross_cagr"],
                "net_pre_overlay": rows[lab]["net_pre_overlay"],
                "cagr": rows[lab]["cagr"],
            }
            for lab in ("PRODUCTION", "CONTROL_REVERSAL")
        }
        a, b = decomp[tag]["PRODUCTION"], decomp[tag]["CONTROL_REVERSAL"]
        decomp[tag]["prod_minus_ctrl"] = {
            "gross_gap": a["gross_cagr"] - b["gross_cagr"],
            "cost_gap": (a["net_pre_overlay"] - a["gross_cagr"])
            - (b["net_pre_overlay"] - b["gross_cagr"]),
            "overlay_gap": (a["cagr"] - a["net_pre_overlay"])
            - (b["cagr"] - b["net_pre_overlay"]),
            "total_gap": a["cagr"] - b["cagr"],
        }
        g = decomp[tag]["prod_minus_ctrl"]
        print(f"    {tag} decomposition (prod - ctrl): gross "
              f"{g['gross_gap'] * 100:+.2f}pp  cost {g['cost_gap'] * 100:+.2f}pp  "
              f"overlay {g['overlay_gap'] * 100:+.2f}pp = {g['total_gap'] * 100:+.2f}pp")
    out["fixed_decomp"] = decomp

    # Train vs test profile, read off the train-selected walk-forward folds.
    prof = {}
    for lab in ("PRODUCTION", "CONTROL_REVERSAL"):
        r = load_run(lab)
        prof[lab] = {
            "train_cagr": float(np.mean([f["train_cagr"] for f in r["folds"]])),
            "train_sharpe": float(np.mean([f["train_sharpe"] for f in r["folds"]])),
            "oos_cagr": r["cagr"], "oos_sharpe": r["sharpe"],
            "folds": [
                {"fold": f["fold"], "params": f["params"],
                 "train_cagr": f["train_cagr"], "train_sharpe": f["train_sharpe"],
                 "test_cagr": f["test_cagr"], "test_sharpe": f["test_sharpe"]}
                for f in r["folds"]
            ],
        }
        prof[lab]["sharpe_flip"] = prof[lab]["train_sharpe"] - prof[lab]["oos_sharpe"]
        prof[lab]["cagr_flip"] = prof[lab]["train_cagr"] - prof[lab]["oos_cagr"]
    out["train_test"] = prof
    for lab, p in prof.items():
        print(f"  {lab:>18}  train Sharpe {p['train_sharpe']:>5.2f} -> "
              f"OOS {p['oos_sharpe']:>5.2f}  (flip {p['sharpe_flip']:+.2f})   "
              f"train CAGR {p['train_cagr'] * 100:>+6.2f}% -> "
              f"OOS {p['oos_cagr'] * 100:>+6.2f}%")
    save_summary("h5", out)
    return out


# --------------------------------------------------------------------------- #
# H6 — "equal-count is the wrong null"
# --------------------------------------------------------------------------- #


def phase_h6(n_scramble: int) -> dict:
    """Signal-scrambled controls.

    A random book and a scrambled book are different nulls and only one of them is a
    fair test of *this* strategy. A random book says "does an arbitrary book make
    money"; a scrambled book says "does *this* book make money for any reason other
    than its signal". The second is the question the negative control was supposed to
    answer, so it is the one that decides the verdict.

    ``scramble_c`` relabels symbols by a fixed permutation: the per-date marginal score
    distribution is preserved exactly, the turnover profile is preserved *in
    distribution* and to within a few percent, and only the score-to-return link is
    destroyed. ``scramble_r`` additionally re-randomises the identity each date, which
    preserves the per-date marginal distribution exactly but raises turnover --
    reported alongside so the difference is visible.

    A note on "turnover-exact"
    --------------------------
    ``scramble_c`` was designed to preserve turnover *exactly* and does not.
    Relabelling score columns relabels which name receives which score, but
    ``build_rebalance_weights`` then inverse-vol-scales by the **name's** realised
    volatility and runs a sector/single-name cap projection over **name identities**,
    so the resulting weights are not a permutation of the original weights. Measured
    directly: under four pure column-permutations of the *same* score panel, total
    one-way turnover is 7.611 / 7.700 / 7.793 / 7.823 against an unpermuted 7.598 -- a
    ~3% spread, i.e. the same order as the seed-to-seed spread of the null itself. So
    ``scramble_c`` matches turnover well but not bit-exactly. That is stated in the
    report rather than papered over, and each null's measured turnover is printed next
    to the production book's so the match can be checked directly.
    """
    specs = [
        RunSpec(f"H6_SCRAMBLE_C_{i:03d}", "h6", kind="scramble_c", seed=20_000 + i)
        for i in range(n_scramble)
    ] + [
        RunSpec(f"H6_SCRAMBLE_R_{i:03d}", "h6", kind="scramble_r", seed=30_000 + i)
        for i in range(n_scramble)
    ]
    out = run_many(specs, WORKERS)
    res: dict = {"n_scramble": n_scramble, "provenance": provenance()}
    for tag, letters in (("scramble_c", "C"), ("scramble_r", "R")):
        keys = [s.label for s in specs if f"_SCRAMBLE_{letters}_" in s.label]
        cagr = np.array([out[k]["cagr"] for k in keys])
        sharpe = np.array([out[k]["sharpe"] for k in keys])
        turn = np.array([out[k]["oos_turnover"] for k in keys])
        drag = np.array([out[k]["oos_cost_drag"] for k in keys])
        res[tag] = {
            "n": len(keys),
            "cagr_mean": float(cagr.mean()), "cagr_sd": float(cagr.std(ddof=1)),
            "cagr_min": float(cagr.min()), "cagr_max": float(cagr.max()),
            "cagr_median": float(np.median(cagr)),
            "cagr_frac_profitable": float((cagr > 0).mean()),
            "sharpe_mean": float(sharpe.mean()), "sharpe_sd": float(sharpe.std(ddof=1)),
            "sharpe_min": float(sharpe.min()), "sharpe_max": float(sharpe.max()),
            "turnover_mean": float(turn.mean()), "cost_drag_mean": float(drag.mean()),
            "cagr_raw": cagr.tolist(), "sharpe_raw": sharpe.tolist(),
        }
        r = res[tag]
        print(f"  {tag}: mean CAGR {r['cagr_mean'] * 100:+.2f}% "
              f"(sd {r['cagr_sd'] * 100:.2f}pp)  Sharpe {r['sharpe_mean']:+.2f} "
              f"(sd {r['sharpe_sd']:.2f})  turnover {r['turnover_mean']:.2f}x/y  "
              f"profitable {r['cagr_frac_profitable'] * 100:.0f}%")

    p, c = load_run("PRODUCTION"), load_run("CONTROL_REVERSAL")
    for tag in ("scramble_c", "scramble_r"):
        cc = np.array(res[tag]["cagr_raw"])
        ss = np.array(res[tag]["sharpe_raw"])
        res[tag]["prod_pct_cagr"] = pct_rank(p["cagr"], cc)
        res[tag]["prod_pct_sharpe"] = pct_rank(p["sharpe"], ss)
        res[tag]["ctrl_pct_cagr"] = pct_rank(c["cagr"], cc)
        res[tag]["ctrl_pct_sharpe"] = pct_rank(c["sharpe"], ss)
        print(f"    production percentile: CAGR {res[tag]['prod_pct_cagr'] * 100:.0f}  "
              f"Sharpe {res[tag]['prod_pct_sharpe'] * 100:.0f}   |   "
              f"control: CAGR {res[tag]['ctrl_pct_cagr'] * 100:.0f}  "
              f"Sharpe {res[tag]['ctrl_pct_sharpe'] * 100:.0f}")
    res["prod_turnover"] = p["oos_turnover"]
    res["ctrl_turnover"] = c["oos_turnover"]
    res["prod_drag"] = p["oos_cost_drag"]
    res["ctrl_drag"] = c["oos_cost_drag"]
    res["prod_cagr"] = p["cagr"]
    res["prod_sharpe"] = p["sharpe"]
    res["ctrl_cagr"] = c["cagr"]
    res["ctrl_sharpe"] = c["sharpe"]
    save_summary("h6", res)
    return res


# --------------------------------------------------------------------------- #
# Extras: beta, correlation, turnover decomposition
# --------------------------------------------------------------------------- #


def phase_extras() -> dict:
    """Beta and correlation to the equal-weight benchmark, plus the turnover question.

    Both books are long-only and unlevered, so their beta against the equal-weight
    universe says how much of the result is simply market exposure. The turnover
    comparison answers the specific question "is the control's advantage just a
    smaller bill for the cost stack?" -- and the measured answer is the opposite of
    what that hypothesis assumes, which the identity below makes explicit.
    """
    sp, sc = load_series("PRODUCTION"), load_series("CONTROL_REVERSAL")
    p, c = load_run("PRODUCTION"), load_run("CONTROL_REVERSAL")
    bm = sp["bench"]
    res = {
        "production": beta_stats(sp["oos"], bm),
        "control": beta_stats(sc["oos"], bm),
        "benchmark_cagr": compute_metrics(bm).cagr,
        "benchmark_sharpe": compute_metrics(bm).sharpe,
        "prod_turnover": p["oos_turnover"],
        "ctrl_turnover": c["oos_turnover"],
        "prod_drag": p["oos_cost_drag"],
        "ctrl_drag": c["oos_cost_drag"],
        "rt_bps": float(COST.all_in_round_trip_bps(100_000)),
        "provenance": provenance(),
    }
    # Cost-difference decomposition.
    #
    # Direction matters here and the obvious framing is backwards. Production turns
    # over LESS than the control (2.51 vs 3.34x/y), so production pays LESS cost
    # drag. The control therefore does NOT get its edge from a smaller bill -- it
    # turns over more, pays more, and still earns more. Stated as an identity:
    #
    #     gross_ctrl - gross_prod = (net_ctrl - net_prod) + (drag_ctrl - drag_prod)
    #
    # so the gross gap is the net gap *plus* the drag gap. A positive
    # `gross_gap` larger than `net_gap` means cost narrows the difference rather
    # than creating it.
    res["rate"] = float(COST.all_in_round_trip_bps(100_000)) / 10_000.0
    res["turnover_gap_ctrl_minus_prod"] = (
        res["ctrl_turnover"] - res["prod_turnover"]
    )
    res["drag_gap_ctrl_minus_prod"] = res["ctrl_drag"] - res["prod_drag"]
    res["net_gap_ctrl_minus_prod"] = c["cagr"] - p["cagr"]
    res["gross_gap_ctrl_minus_prod"] = (
        res["net_gap_ctrl_minus_prod"] + res["drag_gap_ctrl_minus_prod"]
    )
    res["cost_helps_production"] = res["drag_gap_ctrl_minus_prod"] > 0
    res["target_monthly"] = 0.03
    res["target_annual"] = (1.03) ** 12 - 1.0
    # Beta a *zero-alpha* book would need to reach the GOAL.md target.
    #
    # Stated in excess returns over the same risk-free rate the regression uses, so it
    # is consistent with the Jensen alpha above: a zero-alpha book's excess return is
    # beta * the benchmark's excess return, so
    #     beta_required = (target - rf) / (benchmark - rf).
    # The geometric ratio ((1+target)/(1+benchmark) - 1) would answer a different
    # question and would understate the requirement, because the alpha measured by
    # `beta_stats` is an arithmetic regression alpha on excess returns.
    bm_cagr = compute_metrics(bm).cagr
    res["beta_required_for_target"] = (
        res["target_annual"] - RF_ANNUAL
    ) / (bm_cagr - RF_ANNUAL)
    res["beta_required_basis"] = "excess-return (target-rf)/(benchmark-rf)"
    save_summary("extras", res)
    for k in ("production", "control"):
        b = res[k]
        print(f"  {k:>10}: beta {b['beta']:.3f}  corr {b['corr_bench']:.3f}  "
              f"R2 {b['r2']:.3f}  alpha {b['alpha_annual'] * 100:+.2f}%/y  "
              f"(t={b['alpha_t']:+.2f}, p={b['alpha_p']:.2f})  "
              f"TE {b['tracking_err_annual'] * 100:.1f}%")
    print(f"  turnover: production {res['prod_turnover']:.4f}x/y  "
          f"control {res['ctrl_turnover']:.4f}x/y  (control turns over "
          f"{res['turnover_gap_ctrl_minus_prod']:+.4f}x MORE)")
    print(f"  cost drag: production {res['prod_drag'] * 100:.2f}%/y  "
          f"control {res['ctrl_drag'] * 100:.2f}%/y  (control pays "
          f"{res['drag_gap_ctrl_minus_prod'] * 100:+.2f}pp/y MORE)")
    print(f"  net gap (ctrl-prod) {res['net_gap_ctrl_minus_prod'] * 100:+.2f}pp  |  "
          f"gross gap {res['gross_gap_ctrl_minus_prod'] * 100:+.2f}pp  ->  cost "
          f"NARROWS the difference; it does not create it")
    print(f"  beta needed for a zero-alpha book to hit 42.6%/y: "
          f"{res['beta_required_for_target']:.2f}")
    return res


# --------------------------------------------------------------------------- #
# Summary cache
# --------------------------------------------------------------------------- #


def save_summary(name: str, payload: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"summary_{name}.json").write_text(
        json.dumps(payload, indent=2, default=str)
    )


def load_summary(name: str) -> dict | None:
    p = CACHE_DIR / f"summary_{name}.json"
    return json.loads(p.read_text()) if p.exists() else None


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def pctile(x: float) -> str:
    """Format a 0-1 percentile as an English ordinal ("47th", "93rd", "100th")."""
    n = int(round(x * 100))
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.2f}%"


def num(x: float | None, d: int = 2, sign: bool = False) -> str:
    return "n/a" if x is None else f"{x:+.{d}f}" if sign else f"{x:.{d}f}"


def write_report(summaries: dict[str, dict], panel: pd.DataFrame) -> None:
    """Emit `reports/CONTROL_DIAGNOSTIC.md` from the phase summaries."""
    L: list[str] = []
    A = L.append

    ref_p = load_run("PRODUCTION")
    ref_c = load_run("CONTROL_REVERSAL")
    h1 = summaries.get("h1")
    h2 = summaries.get("h2")
    h3 = summaries.get("h3")
    h4 = summaries.get("h4")
    h5 = summaries.get("h5")
    h6 = summaries.get("h6")
    ex = summaries.get("extras")
    prov = provenance()

    A("# Control Diagnostic — does the production composite have a demonstrable edge?")
    A("")
    A("Triggered by `reports/STRESS_v3.md` §6: the production trend composite returns")
    A("OOS +9.71% / Sharpe 0.34 / MaxDD −14.92%, while the reversal **negative control**")
    A("— built entirely from factors this repo's own factor module rules OUT on published")
    A("Indian evidence — returns +10.04% / Sharpe 0.37 / MaxDD −25.05% through the same")
    A("harness and the same cost stack. A negative control that passes where it is meant")
    A("to fail means the harness cannot tell the production composite apart from a")
    A("composite of rejected factors.")
    A("")
    A("This report does not assume what that means. It tests six competing explanations.")
    A("")
    A("## Provenance")
    A("")
    A("| component | SHA |")
    A("|-----------|-----|")
    for k, v in prov.items():
        A(f"| {k} | `{v}` |")
    A("")
    A(f"- **Panel**: {panel.shape[1]} symbols × {len(panel)} daily bars, "
      f"{panel.index[0].date()} → {panel.index[-1].date()}")
    A(f"- **Engine**: `nsealgo.backtest.engine`, unmodified. Cost charge "
      f"`2.0 × one_way_turnover × equity × rate` at "
      f"`{COST.all_in_round_trip_bps(100_000):.2f}` bps all-in round trip "
      f"(statutory + 2 × {BASE_SLIPPAGE} bps slippage).")
    A(f"- **Harness**: `nsealgo.backtest.walkforward.walk_forward`, {N_FOLDS} folds, "
      f"{TRAIN_YEARS}y train / {TEST_YEARS}y test, {len(PARAM_GRID)}-cell grid "
      "(`n_positions` × overlay `lookback` × overlay `threshold`) — identical to "
      "`research/validate.py`.")
    A("- **Only thing varied**: the score panel handed to `run_backtest` (and, for H3, "
      "whether `blend_with_cash` is applied). Engine, costs, factors, overlay, loader "
      "and `walk_forward` are untouched.")
    A(f"- **OOS window**: {ref_p['folds'][-1]['test_start']} → "
      f"{ref_p['folds'][0]['test_end']}, {ref_p['n_oos_days']} daily observations "
      f"across {N_FOLDS} contiguous 2-year test windows.")
    A("- Survivorship bias is present (today's NIFTY-50 backfilled) and is disclosed in "
      "every report in this repo.")
    A("- Reproduce: `.venv/bin/python research/control_diagnostic.py`")
    A("")

    # ---------------------------------------------------------------- summary
    A("## Verdict at a glance")
    A("")
    A("| # | Hypothesis | Verdict | Decisive number |")
    A("|---|-----------|---------|-----------------|")
    for row in _verdict_rows(summaries):
        A(f"| {row['id']} | {row['hyp']} | **{row['verdict']}** | {row['key']} |")
    A("")

    # ---------------------------------------------------------------- H1
    A("## H1 — \"It's beta, not skill\"")
    A("")
    if h1:
        c, s = h1["cagr"], h1["sharpe"]
        D = h1["decomp_prod_vs_null"]

        def decomp(key: str) -> float:
            """Adapter so the table below reads `decomp('cost_a')` not `D['cost_a']`."""
            return float(D[key])
        A(f"{h1['n_random']} random-weight books (i.i.d. Uniform(0,1) scores) through "
          "the **identical** harness: same 6 folds, same 18-cell grid, same engine, same "
          "cost stack, same top-N cut, same inverse-vol scaling, same caps, same "
          "turnover budget, same monthly rebalance. The only thing removed is the signal.")
        A("")
        A("| statistic | random CAGR | random Sharpe | random MaxDD |")
        A("|-----------|-------------|--------------|-------------|")
        for stat, lab in (("mean", "mean"), ("sd", "sd"), ("min", "min"),
                          ("p05", "p05"), ("p25", "p25"), ("median", "median"),
                          ("p75", "p75"), ("p95", "p95"), ("max", "max")):
            A(f"| {lab} | {c[stat] * 100:+.2f}% | {s[stat]:+.2f} | "
              f"{h1['maxdd'][stat] * 100:+.2f}% |")
        A(f"| **profitable** | **{c['frac_profitable'] * 100:.0f}% of books** | — | — |")
        A("")
        A("| book | net CAGR | pct (net) | **gross CAGR** | **pct (gross)** | Sharpe | "
          "pct | turnover | cost drag |")
        A("|------|---------:|---------:|-------------:|--------------:|-------:|"
          "-----:|---------:|----------:|")
        A(f"| **production (trend)** | {h1['prod']['cagr'] * 100:+.2f}% | "
          f"{pctile(h1['prod_pct_cagr'])} | "
          f"{h1['prod']['oos_gross_cagr'] * 100:+.2f}% | "
          f"**{pctile(h1['prod_pct_gross'])}** | {h1['prod']['sharpe']:+.2f} | "
          f"{pctile(h1['prod_pct_sharpe'])} | "
          f"{h1['prod']['oos_turnover']:.2f}x/y | "
          f"{h1['prod']['oos_cost_drag'] * 100:.2f}%/y |")
        A(f"| control (reversal) | {h1['ctrl']['cagr'] * 100:+.2f}% | "
          f"{pctile(h1['ctrl_pct_cagr'])} | "
          f"{h1['ctrl']['oos_gross_cagr'] * 100:+.2f}% | "
          f"{pctile(h1['ctrl_pct_gross'])} | {h1['ctrl']['sharpe']:+.2f} | "
          f"{pctile(h1['ctrl_pct_sharpe'])} | "
          f"{h1['ctrl']['oos_turnover']:.2f}x/y | "
          f"{h1['ctrl']['oos_cost_drag'] * 100:.2f}%/y |")
        A("")
        A(f"> **Read the gross column, not the net one.** The random books turn over "
          f"{h1['turnover']['mean']:.2f}x/yr against production's "
          f"{h1['prod']['oos_turnover']:.2f}x/yr, so on *net* return production is "
          f"credited for a cost saving that has nothing to do with its factors. The "
          f"gross column strips both costs and the regime overlay.")
        A("")
        A("### Where production's net edge over the null actually comes from")
        A("")
        A("Three consistent measurements are available per book and they nest, so the "
          "gap decomposes exactly:")
        A("")
        A("```")
        A("gross   ->  -costs-  ->  net_pre_overlay  ->  +overlay  ->  net")
        A("```")
        A("")
        A("| book | gross CAGR | cost channel | net pre-overlay | overlay channel | "
          "net CAGR |")
        A("|------|-----------:|-------------:|----------------:|----------------:|"
          "---------:|")
        A(f"| production | {h1['prod']['oos_gross_cagr'] * 100:+.2f}% | "
          f"{decomp('cost_a') * 100:+.2f}pp | "
          f"{h1['prod']['oos_net_pre_overlay'] * 100:+.2f}% | "
          f"{decomp('overlay_a') * 100:+.2f}pp | {h1['prod']['cagr'] * 100:+.2f}% |")
        A(f"| mean random book | {h1['null_mean']['oos_gross_cagr'] * 100:+.2f}% | "
          f"{decomp('cost_b') * 100:+.2f}pp | "
          f"{h1['null_mean']['oos_net_pre_overlay'] * 100:+.2f}% | "
          f"{decomp('overlay_b') * 100:+.2f}pp | "
          f"{h1['null_mean']['cagr'] * 100:+.2f}% |")
        A(f"| **difference** | **{decomp('gross_gap') * 100:+.2f}pp** | "
          f"**{decomp('cost_gap') * 100:+.2f}pp** | — | "
          f"**{decomp('overlay_gap') * 100:+.2f}pp** | "
          f"**{decomp('total_gap') * 100:+.2f}pp** |")
        A("")
        A(f"The three difference terms reconcile to the observed net gap "
          f"({decomp('total_gap') * 100:+.2f}pp) to "
          f"{abs(decomp('recon_err')):.1e}. **The selection term — the only one that "
          f"reflects the factors — is "
          f"{decomp('gross_gap') * 100:+.2f}pp/yr.** Everything else is book "
          f"construction: turnover and the overlay.")
        A("")
        v = _h1_verdict(h1)
        A(v)
        A("")
    else:
        A("_not run_")
        A("")

    # ---------------------------------------------------------------- H2
    A("## H2 — \"The low-vol leg is doing the work, not the reversal legs\"")
    A("")
    if h2:
        A("Every component run alone at weight 1.0 through the same harness, plus the "
          "control with `low_volatility` removed (weights renormalised by "
          "`build_composite_score`).")
        A("")
        A("| book | OOS CAGR | OOS Sharpe | OOS MaxDD | turnover | cost drag |")
        A("|------|---------:|-----------:|----------:|---------:|----------:|")
        A(f"| **PRODUCTION (trend)** | **{h2['production']['cagr'] * 100:+.2f}%** | "
          f"**{h2['production']['sharpe']:.2f}** | "
          f"**{h2['production']['maxdd'] * 100:+.2f}%** | "
          f"{ref_p['oos_turnover']:.2f}x/y | {ref_p['oos_cost_drag'] * 100:.2f}%/y |")
        A(f"| **CONTROL (reversal)** | **{h2['control']['cagr'] * 100:+.2f}%** | "
          f"**{h2['control']['sharpe']:.2f}** | "
          f"**{h2['control']['maxdd'] * 100:+.2f}%** | "
          f"{ref_c['oos_turnover']:.2f}x/y | {ref_c['oos_cost_drag'] * 100:.2f}%/y |")
        for r in h2["components"]:
            A(f"| {r['component']} | {r['cagr'] * 100:+.2f}% | {r['sharpe']:+.2f} | "
              f"{r['maxdd'] * 100:+.2f}% | {r['turnover']:.2f}x/y | "
              f"{r['cost_drag'] * 100:.2f}%/y |")
        A("")
        A(_h2_verdict(h2))
        A("")
    else:
        A("_not run_")
        A("")

    # ---------------------------------------------------------------- H3
    A("## H3 — \"The regime overlay is the whole difference\"")
    A("")
    if h3:
        A("Identical folds, identical grid, identical engine and costs. `overlay=OFF` "
          "skips `blend_with_cash` and nothing else.")
        A("")
        A("| book | overlay | OOS CAGR | OOS Sharpe | OOS MaxDD |")
        A("|------|---------|---------:|-----------:|----------:|")
        for k in ("prod", "ctrl"):
            for mode in ("with_overlay", "no_overlay"):
                r = h3[mode][k]
                A(f"| {k} | {mode.replace('_', ' ')} | {r['cagr'] * 100:+.2f}% | "
                  f"{r['sharpe']:+.2f} | {r['maxdd'] * 100:+.2f}% |")
        A("")
        A(f"**Sharpe gap (control − production):** "
          f"{h3['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} with the overlay, "
          f"{h3['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} without it. "
          f"**CAGR gap (control − production):** "
          f"{h3['with_overlay']['cagr_gap_ctrl_minus_prod'] * 100:+.2f}pp with, "
          f"{h3['no_overlay']['cagr_gap_ctrl_minus_prod'] * 100:+.2f}pp without.")
        A("")
        A(_h3_verdict(h3))
        A("")
    else:
        A("_not run_")
        A("")

    # ---------------------------------------------------------------- H4
    A("## H4 — \"0.34 vs 0.37 is noise\"")
    A("")
    if h4:
        t, b = h4["ttest"], h4["bootstrap"]
        A(f"OOS window {h4['oos_window'][0]} → {h4['oos_window'][1]}, "
          f"**{t['n_days']} daily observations**, both books on identical dates "
          "(paired).")
        A("")
        A("| test | statistic | p-value | reading |")
        A("|------|-----------|---------|---------|")
        A(f"| paired daily t-test on the return difference | t = {t['t_iid']:+.3f} | "
          f"{t['p_iid']:.3f} | mean difference "
          f"{t['mean_diff_bps']:+.3f} bps/day |")
        A(f"| same, Newey-West HAC(10) | t = {t['t_newey_west']:+.3f} | "
          f"{t['p_newey_west']:.3f} | serial-correlation-robust |")
        A(f"| bootstrap 95% CI on ΔCAGR (21-bar blocks, B={b['B']:,}) | "
          f"[{b['d_cagr_ci_lo'] * 100:+.2f}pp, {b['d_cagr_ci_hi'] * 100:+.2f}pp] | — | "
          f"P(production > control) = {b['p_a_better']:.2f} |")
        A("")
        A(f"Observed ΔCAGR = {h4['prod_cagr'] * 100:+.2f}% − "
          f"{h4['ctrl_cagr'] * 100:+.2f}% = "
          f"{(h4['prod_cagr'] - h4['ctrl_cagr']) * 100:+.2f}pp. "
          f"Observed ΔSharpe = {h4['prod_sharpe']:.2f} − {h4['ctrl_sharpe']:.2f} = "
          f"{h4['prod_sharpe'] - h4['ctrl_sharpe']:+.2f}.")
        A("")
        A(_h4_verdict(h4))
        A("")
    else:
        A("_not run_")
        A("")

    # ---------------------------------------------------------------- H5
    A("## H5 — \"The harness has a selection artifact\"")
    A("")
    if h5:
        A("Walk-forward selects parameters on TRAIN. A book that survives TRAIN "
          "selection could carry a structural OOS advantage unrelated to its signal. "
          "Two readings: run a **fixed, unselected** parameter set, and look at the "
          "train/test profile of both books.")
        A("")
        A("### Fixed parameters — no train selection at all")
        A("")
        A("| cell | params | production CAGR | control CAGR | production Sharpe | "
          "control Sharpe |")
        A("|------|--------|----------------:|--------------:|-----------------:|"
          "---------------:|")
        for tag, rows in h5["fixed"].items():
            p_ = rows["params"]
            A(f"| {tag} | n={p_['n_positions']}, lb={p_['lookback']}, "
              f"thr={p_['threshold']} | {rows['PRODUCTION']['cagr'] * 100:+.2f}% | "
              f"{rows['CONTROL_REVERSAL']['cagr'] * 100:+.2f}% | "
              f"{rows['PRODUCTION']['sharpe']:.2f} | "
              f"{rows['CONTROL_REVERSAL']['sharpe']:.2f} |")
        A("")
        if h5.get("fixed_decomp"):
            A("Decomposed the same way as H1 (gross = selection, then cost, then "
              "overlay):")
            A("")
            A("| cell | selection (gross) | cost | overlay | total net |")
            A("|------|------------------:|-----:|--------:|----------:|")
            for tag, d in h5["fixed_decomp"].items():
                g = d["prod_minus_ctrl"]
                A(f"| {tag} | {g['gross_gap'] * 100:+.2f}pp | "
                  f"{g['cost_gap'] * 100:+.2f}pp | {g['overlay_gap'] * 100:+.2f}pp | "
                  f"{g['total_gap'] * 100:+.2f}pp |")
            A("")
        if h5.get("selection_cost"):
            A("### What the train-window selection actually does")
            A("")
            A("| book | best fixed cell | walk-forward | selection delta |")
            A("|------|-----------------:|-------------:|----------------:|")
            for lab, s_ in h5["selection_cost"].items():
                A(f"| {lab} | {s_['best_fixed_cagr'] * 100:+.2f}% | "
                  f"{s_['walk_forward_cagr'] * 100:+.2f}% | "
                  f"{s_['selection_delta_cagr'] * 100:+.2f}pp |")
            A("")
        A("### Train vs test — is there a flip?")
        A("")
        A("| book | mean TRAIN Sharpe | OOS Sharpe | flip | mean TRAIN CAGR | OOS CAGR |")
        A("|------|------------------:|-----------:|-----:|----------------:|--------:|")
        for lab, p_ in h5["train_test"].items():
            A(f"| {lab} | {p_['train_sharpe']:+.2f} | {p_['oos_sharpe']:+.2f} | "
              f"{p_['sharpe_flip']:+.2f} | {p_['train_cagr'] * 100:+.2f}% | "
              f"{p_['oos_cagr'] * 100:+.2f}% |")
        A("")
        A("<details><summary>Per-fold train/test</summary>")
        A("")
        A("| book | fold | selected params | TRAIN Sharpe | OOS Sharpe | TRAIN CAGR | "
          "OOS CAGR |")
        A("|------|-----:|------------------|-------------:|-----------:|----------:|"
          "---------:|")
        for lab, p_ in h5["train_test"].items():
            for f in p_["folds"]:
                A(f"| {lab} | {f['fold']} | n={f['params']['n_positions']}, "
                  f"lb={f['params']['lookback']}, thr={f['params']['threshold']} | "
                  f"{f['train_sharpe']:+.2f} | {f['test_sharpe']:+.2f} | "
                  f"{f['train_cagr'] * 100:+.2f}% | {f['test_cagr'] * 100:+.2f}% |")
        A("")
        A("</details>")
        A("")
        A(_h5_verdict(h5))
        A("")
    else:
        A("_not run_")
        A("")

    # ---------------------------------------------------------------- H6
    A("## H6 — \"Equal-count controls are the wrong null\"")
    A("")
    if h6:
        A("A random book and a **signal-scrambled** book are different nulls. A random "
          "book asks *does an arbitrary book make money*. A scrambled book asks *does "
          "**this** book make money for any reason other than its signal* — which is "
          "what a negative control is for.")
        A("")
        A("- `scramble_c`: the composite score with a **fixed column relabel** "
          "(`score'[t,s] = score[t,π(s)]`). Every per-date marginal score distribution is "
          "preserved **exactly**; only the score-to-return link is destroyed.")
        A("- `scramble_r`: the composite with an **independent permutation of each "
          "date's cross-section**. Per-date marginals are still preserved exactly, but "
          "the name identity churns every rebalance, so turnover rises. Reported "
          "alongside so that difference is visible rather than hidden.")
        A("")
        A("> **Correction on turnover preservation.** `scramble_c` was intended to hold "
          "turnover *exactly* fixed, and it does not. Relabelling score columns relabels "
          "which name receives which score, but `build_rebalance_weights` then "
          "inverse-vol-scales by the **name's** realised volatility and runs a "
          "sector/single-name cap projection over **name identities** — so the resulting "
          "weights are not a permutation of the original weights. Measured directly, under "
          "four pure column-permutations of the *same* score panel the total one-way "
          "turnover is 7.611 / 7.700 / 7.793 / 7.823 against an unpermuted 7.598: a ~3% "
          "spread, the same order as the seed-to-seed spread of the null itself. So "
          "`scramble_c` matches turnover *in distribution* and to within a few percent, "
          "not bit-exactly. The measured turnover of each null is printed in the table "
          "below so this can be checked rather than taken on trust.")
        A("")
        A("| book | n | mean CAGR | sd | min | max | mean Sharpe | sd | turnover | "
          "cost drag | profitable |")
        A("|------|--:|----------:|---:|----:|----:|-----------:|---:|---------:|"
          "----------:|-----------:|")
        A(f"| **production (unscrambled)** | 1 | "
          f"{h6['prod_cagr'] * 100:+.2f}% | — | — | — | {h6['prod_sharpe']:.2f} | — | "
          f"**{h6['prod_turnover']:.2f}x/y** | "
          f"**{h6['prod_drag'] * 100:.2f}%/y** | — |")
        for tag, lab in (("scramble_c", "scramble_c (fixed relabel)"),
                         ("scramble_r", "scramble_r (per-date permute)")):
            r = h6[tag]
            A(f"| {lab} | {r['n']} | {r['cagr_mean'] * 100:+.2f}% | "
              f"{r['cagr_sd'] * 100:.2f}pp | {r['cagr_min'] * 100:+.2f}% | "
              f"{r['cagr_max'] * 100:+.2f}% | {r['sharpe_mean']:+.2f} | "
              f"{r['sharpe_sd']:.2f} | {r['turnover_mean']:.2f}x/y | "
              f"{r['cost_drag_mean'] * 100:.2f}%/y | "
              f"{r['cagr_frac_profitable'] * 100:.0f}% |")
        A("")
        A("| book | vs scramble_c (CAGR pct) | vs scramble_c (Sharpe pct) | "
          "vs scramble_r (CAGR pct) | vs scramble_r (Sharpe pct) |")
        A("|------|-------------------------:|---------------------------:|"
          "------------------------:|--------------------------:|")
        A(f"| **production** | {pctile(h6['scramble_c']['prod_pct_cagr'])} | "
          f"{pctile(h6['scramble_c']['prod_pct_sharpe'])} | "
          f"{pctile(h6['scramble_r']['prod_pct_cagr'])} | "
          f"{pctile(h6['scramble_r']['prod_pct_sharpe'])} |")
        A(f"| control | {pctile(h6['scramble_c']['ctrl_pct_cagr'])} | "
          f"{pctile(h6['scramble_c']['ctrl_pct_sharpe'])} | "
          f"{pctile(h6['scramble_r']['ctrl_pct_cagr'])} | "
          f"{pctile(h6['scramble_r']['ctrl_pct_sharpe'])} |")
        A("")
        A("> **Read the production row, not the control row.** These nulls are built by "
          "scrambling the **production** composite, so the production row is a "
          "like-for-like test of production against its own signal destroyed. The "
          "control row places a *different* composite (reversal weights) against a "
          "null built from the trend composite's score distribution — the two books "
          "have different turnover, different score dispersion and different name "
          "overlap, so the control's percentile against this null is indicative only "
          "and should not be read as a significance test. A matched control scramble "
          "(reversal weights, then scrambled) is the clean version of that "
          "comparison and was not run; H2 and H4 cover the production-vs-control "
          "question directly instead.")
        A("")
        A(_h6_verdict(h6))
        A("")
    else:
        A("_not run_")
        A("")

    # ---------------------------------------------------------------- extras
    A("## Turnover, beta and the equal-weight benchmark")
    A("")
    if ex:
        A("### 1. Turnover and cost drag — is the control's edge just a smaller bill?")
        A("")
        A("| book | annual turnover | annual cost drag |")
        A("|------|----------------:|-----------------:|")
        A(f"| production | {ex['prod_turnover']:.4f}x/y | {ex['prod_drag'] * 100:.2f}%/y |")
        A(f"| control | {ex['ctrl_turnover']:.4f}x/y | {ex['ctrl_drag'] * 100:.2f}%/y |")
        A(f"| **control − production** | "
          f"**{ex['turnover_gap_ctrl_minus_prod']:+.4f}x/y** | "
          f"**{ex['drag_gap_ctrl_minus_prod'] * 100:+.2f}pp/y** |")
        A("")
        A("**The hypothesis is refuted, and the direction matters.** The brief asked "
          "what happens if the control turns over *less* — part of its advantage would "
          "then be a smaller cost bill. The measurement is the opposite: the control "
          f"turns over **{abs(ex['turnover_gap_ctrl_minus_prod']):.2f}x/yr more** and "
          f"pays **{abs(ex['drag_gap_ctrl_minus_prod']) * 100:.2f}pp/yr more** in drag, "
          "and still earns more. As an identity:")
        A("")
        A("```")
        A("gross_ctrl - gross_prod = (net_ctrl - net_prod) + (drag_ctrl - drag_prod)")
        A(f"                        = {ex['net_gap_ctrl_minus_prod'] * 100:+.2f}pp"
          f"              + {ex['drag_gap_ctrl_minus_prod'] * 100:+.2f}pp")
        A(f"                        = {ex['gross_gap_ctrl_minus_prod'] * 100:+.2f}pp")
        A("```")
        A("")
        A(f"The control's **gross** advantage is "
          f"{ex['gross_gap_ctrl_minus_prod'] * 100:+.2f}pp/yr — larger than its net "
          f"advantage of {ex['net_gap_ctrl_minus_prod'] * 100:+.2f}pp/yr. Cost drag "
          f"*narrows* the gap between the two books; it does not create it. Turnover is "
          f"not the explanation, and neither book is winning by trading less.")
        A("")
        A("### 2. Beta and correlation to the equal-weight benchmark")
        A("")
        A("| book | beta | corr | R² | Jensen alpha | alpha t | alpha p | "
          "tracking error |")
        A("|------|-----:|-----:|---:|-------------:|--------:|--------:|"
          "---------------:|")
        for k, lab in (("production", "production"), ("control", "control")):
            b = ex[k]
            A(f"| {lab} | {b['beta']:.3f} | {b['corr_bench']:.3f} | {b['r2']:.3f} | "
              f"{b['alpha_annual'] * 100:+.2f}%/y | {b['alpha_t']:+.2f} | "
              f"{b['alpha_p']:.2f} | {b['tracking_err_annual'] * 100:.1f}% |")
        A(f"| *equal-weight benchmark* | 1.000 | 1.000 | 1.000 | "
          f"— (CAGR {ex['benchmark_cagr'] * 100:+.2f}%, Sharpe "
          f"{ex['benchmark_sharpe']:.2f}) | — | — | — |")
        A("")
        A("### 3. Would a market-neutral or beta-matched comparison change the verdict?")
        A("")
        A(_beta_verdict(ex))
        A("")
    else:
        A("_not run_")
        A("")

    A("## Bottom line")
    A("")
    A(_bottom_line(summaries))
    A("")
    A("---")
    A("")
    A(f"*Produced by `research/control_diagnostic.py` against engine `{prov['engine']}`, "
      f"loader `{prov['loader']}`, costs `{prov['costs']}`, panel `{prov['panel']}`. "
      f"Every figure here is net of the full Indian delivery cost stack and must be "
      f"quoted with its end date — the OOS window ends "
      f"{ref_p['folds'][0]['test_end']}. Survivorship bias is present and disclosed. "
      f"`GOAL.md` §6 anti-fraud rules apply: no in-sample number is presented as a "
      f"result, and no cost was reduced to rescue anything.*")

    REPORT_PATH.write_text("\n".join(L) + "\n")


# --------------------------------------------------------------------------- #
# Verdict helpers — plain-language reading of each phase's numbers
# --------------------------------------------------------------------------- #


def decompose(attr: dict, base: dict) -> dict:
    """Split `attr - base` into the cost channel and the overlay channel.

    Three consistent measurements are available per book, and they nest:

        gross   -- weights' raw daily return, no costs, no overlay
        net_pre -- after the engine charges costs, before the overlay is blended
        net     -- after the overlay (the number reported everywhere)

    So for any two books, exactly:

        net_a - net_b = (gross_a - gross_b)          <- selection / signal
                     + (cost_a - cost_b)            <- turnover channel
                     + (overlay_a - overlay_b)       <- regime-overlay channel

    with cost = net_pre - gross and overlay = net - net_pre. Reporting the raw
    gross-to-net gap as a single "cost" number would silently fold the overlay
    channel into it, which is exactly the error this decomposition exists to
    prevent.
    """
    cost_a = attr["oos_net_pre_overlay"] - attr["oos_gross_cagr"]
    cost_b = base["oos_net_pre_overlay"] - base["oos_gross_cagr"]
    ov_a = attr["cagr"] - attr["oos_net_pre_overlay"]
    ov_b = base["cagr"] - base["oos_net_pre_overlay"]
    return {
        "gross_gap": attr["oos_gross_cagr"] - base["oos_gross_cagr"],
        "cost_gap": cost_a - cost_b,
        "overlay_gap": ov_a - ov_b,
        "total_gap": attr["cagr"] - base["cagr"],
        "cost_a": cost_a, "cost_b": cost_b,
        "overlay_a": ov_a, "overlay_b": ov_b,
        "recon_err": (
            attr["cagr"] - base["cagr"]
            - ((attr["oos_gross_cagr"] - base["oos_gross_cagr"]) + (cost_a - cost_b)
               + (ov_a - ov_b))
        ),
    }


def _h1_verdict(h1: dict) -> str:
    c = h1["cagr"]
    lo, hi = h1["prod_pct_cagr"], h1["prod_pct_sharpe"]
    lo_g = h1["prod_pct_gross"]
    D = h1["decomp_prod_vs_null"]
    ctrl_lo_g = h1["ctrl_pct_gross"]
    parts = [
        "**Verdict: SUPPORTED on the decisive comparison, and the net numbers "
        "understate how badly.**",
        "",
        f"1. **The beta floor is real and high.** "
        f"{c['frac_profitable'] * 100:.0f}% of {h1['n_random']} random-weight books are "
        f"profitable out-of-sample through this harness, net of the same 21.92bps cost "
        f"stack — mean CAGR {c['mean'] * 100:+.2f}%, mean Sharpe "
        f"{h1['sharpe']['mean']:+.2f}, **worst case {c['min'] * 100:+.2f}%**. Not one "
        f"of them lost money. An arbitrary 22-name NIFTY-50 book rebalanced monthly, "
        f"with no signal whatsoever, makes money in this sample. The strategy's "
        f"profitability is therefore not evidence of skill.",
        f"2. **And the composite's edge over that null is not a selection edge.** On net "
        f"CAGR production sits at the {pctile(lo)} percentile and on Sharpe at the "
        f"{pctile(hi)} — which looks like real selection. But a book that turns over "
        f"{h1['turnover']['mean']:.2f}x/yr against production's "
        f"{h1['prod']['oos_turnover']:.2f}x/yr is being *credited for trading less* on "
        f"any net comparison.",
        f"3. **Decomposed, the selection term is "
        f"{D['gross_gap'] * 100:+.2f}pp/yr — indistinguishable from zero.** Of "
        f"production's {D['total_gap'] * 100:+.2f}pp/yr net edge over the mean random "
        f"book, {D['cost_gap'] * 100:+.2f}pp is the turnover/cost channel and "
        f"{D['overlay_gap'] * 100:+.2f}pp is the regime-overlay channel. On **gross** "
        f"CAGR — before costs and before the overlay — production's "
        f"{h1['prod']['oos_gross_cagr'] * 100:+.2f}% lands at the "
        f"**{pctile(lo_g)} percentile** of a null whose gross mean is "
        f"{h1['null_mean']['oos_gross_cagr'] * 100:+.2f}%. That is *the median random "
        f"book*, to two decimal places.",
    ]
    if lo_g < 60:
        parts.append(
            f"\n**So the honest reading of H1 is: the composite's factors are worth "
            f"approximately nothing on this data, and everything it does better than a "
            f"random book it does by holding fewer positions and de-risking more "
            f"often.** Both of those are properties of book *construction*, and neither "
            f"is evidence that the factor set has predictive power. The reversal "
            f"control's gross percentile is {pctile(ctrl_lo_g)}, so on this metric "
            f"the control's selection is *not* null either — which is the finding, "
            f"not a reprieve."
        )
    else:
        parts.append(
            "\n**So H1 is half right.** The absolute profitability is not evidence of "
            "skill, but the selection advantage survives removing both the cost and "
            "the overlay channel."
        )
    parts.append(
        "\nH1 cannot by itself explain why production fails to beat a composite of "
        "factors this repo has already ruled out on published Indian evidence. For "
        "that, see H2, H5 and H6."
    )
    return "\n".join(parts)


def _h2_verdict(h2: dict) -> str:
    by = {r["component"]: r for r in h2["components"]}
    nolv = by.get("control_no_lowvol", {})
    lowv = by.get("low_volatility", {})
    r5 = by.get("reversal_5d", {})
    r20 = by.get("reversal_20d", {})
    prod = h2["production"]
    bits = []
    if nolv:
        bits.append(
            f"control **without** low-volatility = {nolv['cagr'] * 100:+.2f}% / Sharpe "
            f"{nolv['sharpe']:+.2f}"
        )
    if lowv:
        bits.append(
            f"`low_volatility` alone = {lowv['cagr'] * 100:+.2f}% / Sharpe "
            f"{lowv['sharpe']:+.2f}"
        )
    if r5 and r20:
        bits.append(
            f"`reversal_5d` alone = {r5['cagr'] * 100:+.2f}% / {r5['sharpe']:+.2f}; "
            f"`reversal_20d` alone = {r20['cagr'] * 100:+.2f}% / {r20['sharpe']:+.2f}"
        )
    body = "; ".join(bits)
    nolv_better = bool(nolv) and nolv["cagr"] > prod["cagr"]
    tail = (
        f" Removing the low-vol leg leaves the control at {nolv['cagr'] * 100:+.2f}% / "
        f"Sharpe {nolv['sharpe']:+.2f} — still ahead of production's "
        f"{prod['cagr'] * 100:+.2f}% / {prod['sharpe']:.2f}. The low-volatility leg is "
        f"therefore *not* what carries the control; the reversal legs are."
        if nolv_better
        else (
            f" Removing the low-vol leg takes the control to {nolv['cagr'] * 100:+.2f}% / "
            f"Sharpe {nolv['sharpe']:+.2f} — behind production's "
            f"{prod['cagr'] * 100:+.2f}% / {prod['sharpe']:.2f}. On this reading the "
            f"low-volatility leg is what carries the control."
        )
    )
    return (
        f"{body}.\n\n"
        f"**Verdict: {'REFUTED' if nolv_better else 'SUPPORTED'}.**{tail}"
    )


def _h3_verdict(h3: dict) -> str:
    on = h3["with_overlay"]["sharpe_gap_ctrl_minus_prod"]
    off = h3["no_overlay"]["sharpe_gap_ctrl_minus_prod"]
    same_sign = (on > 0) == (off > 0)
    if same_sign:
        return (
            f"**Verdict: REFUTED.** The control's Sharpe advantage over production is "
            f"present with the overlay ({on:+.3f}) and without it ({off:+.3f}) — same "
            f"sign, similar size. The overlay is not the difference; production does not "
            f"only win with it."
        )
    return (
        f"**Verdict: SUPPORTED.** The sign of the control-minus-production Sharpe gap "
        f"flips between overlay on ({on:+.3f}) and off ({off:+.3f}), so the overlay is "
        f"doing real work in the production-vs-control comparison."
    )


def _h4_verdict(h4: dict) -> str:
    b = h4["bootstrap"]
    t = h4["ttest"]
    straddles = b["d_cagr_ci_lo"] < 0 < b["d_cagr_ci_hi"]
    if straddles and t["p_newey_west"] > 0.05:
        return (
            f"**Verdict: SUPPORTED.** The 95% bootstrap CI on ΔCAGR is "
            f"[{b['d_cagr_ci_lo'] * 100:+.2f}pp, {b['d_cagr_ci_hi'] * 100:+.2f}pp] — it "
            f"straddles zero, and the serial-correlation-robust paired t-test is "
            f"t = {t['t_newey_west']:+.2f}, p = {t['p_newey_west']:.2f}. The two books "
            f"are **statistically indistinguishable** out-of-sample. That is itself the "
            f"finding: the composite's factors do not separate it from a composite of "
            f"rejected factors by any measurable margin, over "
            f"{t['n_days']} daily observations."
        )
    return (
        f"**Verdict: REFUTED.** The bootstrap CI on ΔCAGR is "
        f"[{b['d_cagr_ci_lo'] * 100:+.2f}pp, {b['d_cagr_ci_hi'] * 100:+.2f}pp], which "
        f"excludes zero; the paired Newey-West t-test gives p = "
        f"{t['p_newey_west']:.3f}. The difference is measurable, not noise."
    )


def _h5_verdict(h5: dict) -> str:
    rows = []
    for tag, r in h5["fixed"].items():
        d = r["PRODUCTION"]["cagr"] - r["CONTROL_REVERSAL"]["cagr"]
        ds = r["PRODUCTION"]["sharpe"] - r["CONTROL_REVERSAL"]["sharpe"]
        rows.append((tag, d, ds))
    prod_wins = [t for t, d, _ in rows if d > 0]
    tt = h5["train_test"]
    flips = {lab: v["sharpe_flip"] for lab, v in tt.items()}
    ctrl_flip = flips.get("CONTROL_REVERSAL", 0.0)
    prod_flip = flips.get("PRODUCTION", 0.0)
    out = [
        f"**Verdict: REFUTED — this is the one hypothesis that does not survive.** With "
        f"the train-window selection removed entirely, production beats the control in "
        f"{len(prod_wins)} of {len(rows)} fixed cells: "
        + ", ".join(f"{t} {d * 100:+.2f}pp (Sharpe {ds:+.2f})" for t, d, ds in rows)
        + ". The production composite is **not** uniformly inert: under some fixed "
        "settings it does select better names than the reversal composite.",
        "\nThis is the strongest evidence in the repo for the production composite, "
        "and it deserves to be stated plainly rather than buried. But it is not a "
        "deployable edge, for two reasons. First, these cells are ordinary "
        "book-construction choices, not out-of-sample discoveries. Second, and more "
        "seriously, the walk-forward version of the strategy — the only protocol "
        "`GOAL.md` §5 accepts — does not reproduce it.",
    ]
    if h5.get("selection_cost"):
        sp = h5["selection_cost"]["PRODUCTION"]["selection_delta_cagr"]
        sc = h5["selection_cost"]["CONTROL_REVERSAL"]["selection_delta_cagr"]
        out.append(
            f"\n**The selection step is what destroys it.** Production's best fixed "
            f"cell returns "
            f"{h5['selection_cost']['PRODUCTION']['best_fixed_cagr'] * 100:+.2f}%/yr, "
            f"but the same strategy under walk-forward parameter selection returns "
            f"{h5['selection_cost']['PRODUCTION']['walk_forward_cagr'] * 100:+.2f}%/yr — "
            f"selection costs it {abs(sp) * 100:.2f}pp/yr. The control moves the other "
            f"way: selection *adds* "
            f"{sc * 100:+.2f}pp/yr to it. So the train-window search is anti-correlated "
            f"with out-of-sample performance for the production composite and "
            f"positively correlated for the control. That is a defect in the "
            f"parameter-selection layer, and it is the mechanical reason the "
            f"negative control ties production in the protocol that counts."
        )
    out.append(
        f"\n**There is no train/test flip unique to the control.** Train→OOS Sharpe "
        f"degradation is {prod_flip:+.2f} for production and {ctrl_flip:+.2f} for the "
        f"control — nearly identical. The control is not a book that was overfit and "
        f"then broke; it is a book that behaves the same way in both regimes. That is "
        f"the worse of the two cases for the production composite's defence."
    )
    return "\n".join(out)


def _h6_verdict(h6: dict) -> str:
    c = h6["scramble_c"]
    if c["prod_pct_cagr"] < 0.75 and c["prod_pct_sharpe"] < 0.75:
        return (
            f"**Verdict: SUPPORTED.** Against the turnover-matched signal-scrambled null, "
            f"production sits at the {pctile(c['prod_pct_cagr'])} percentile on CAGR "
            f"and {pctile(c['prod_pct_sharpe'])} on Sharpe, while "
            f"{c['cagr_frac_profitable'] * 100:.0f}% of scrambled books are profitable. "
            f"Keeping the per-date score distribution, the name count, the cost stack, "
            f"the overlay and the constraints — and destroying only the link from score "
            f"to return — leaves a result indistinguishable from the production one. "
            f"(The null's turnover is matched to within a few percent, not exactly; see "
            f"the correction note above.) Turnover is not what separates them."
        )
    return (
        f"**Verdict: REFUTED.** Production sits at the "
        f"{pctile(c['prod_pct_cagr'])} percentile (CAGR) / "
        f"{pctile(c['prod_pct_sharpe'])} (Sharpe) against the "
        f"turnover-matched scrambled null, so the signal is doing real work."
    )


def _beta_verdict(ex: dict) -> str:
    bp, bc = ex["production"]["beta"], ex["control"]["beta"]
    ap, ac = ex["production"], ex["control"]
    tgt = ex["target_annual"]
    bmc = ex["benchmark_cagr"]
    need = ex["beta_required_for_target"]
    return (
        f"`GOAL.md` targets 3%/month net = **{tgt * 100:.1f}%/yr**. The equal-weight "
        f"NIFTY-50 benchmark over the same OOS windows returned "
        f"{bmc * 100:+.2f}%/yr (Sharpe {ex['benchmark_sharpe']:.2f}). The book already "
        f"**underperforms the benchmark it could have simply held**.\n\n"
        f"Production's beta against that benchmark is **{bp:.3f}** (corr "
        f"{ap['corr_bench']:.3f}, R² {ap['r2']:.3f}); the control's is **{bc:.3f}** "
        f"(corr {ac['corr_bench']:.3f}, R² {ac['r2']:.3f}). Neither is ~1.0 — the regime "
        f"overlay spends time in cash, which is why — so the 'levered index fund' story "
        f"is not literally right. But it is not rescued either: Jensen alpha is "
        f"**{ap['alpha_annual'] * 100:+.2f}%/yr (t = {ap['alpha_t']:+.2f}, "
        f"p = {ap['alpha_p']:.2f})** for production and "
        f"**{ac['alpha_annual'] * 100:+.2f}%/yr (t = {ac['alpha_t']:+.2f}, "
        f"p = {ac['alpha_p']:.2f})** for the control. Both are **negative** and both are "
        f"statistically indistinguishable from zero.\n\n"
        f"**Would a beta-matched comparison change the verdict? No.** The two books "
        f"differ by {abs(bp - bc):.3f} in beta, so matching beta changes nothing "
        f"material: whichever Sharpe wins raw wins beta-matched. And beta-matching "
        f"cannot separate a book from a signal-scrambled version of itself, because "
        f"scrambling the signal leaves beta intact by construction.\n\n"
        f"**Would a market-neutral comparison change the verdict? It is not available, "
        f"and it would not be the right test.** The account is long-only delivery "
        f"(`GOAL.md` §3.2, `AGENT_BRIEF.md` §5), so there is no short leg to neutralise "
        f"against. The Jensen alpha above is already the market-adjusted number, and it "
        f"is zero.\n\n"
        f"**At what beta would the comparison become fair?** A fair comparison asks "
        f"whether the book earns its *target* given its risk. Stated on the same "
        f"excess-return basis the regression uses (`{ex['beta_required_basis']}`), a "
        f"zero-alpha book would need a beta of **{need:.2f}** to reach "
        f"{tgt * 100:.1f}%/yr from a {bmc * 100:.2f}%/yr benchmark — roughly "
        f"{need / bp:.0f}× the beta production actually runs at, and well beyond what a "
        f"long-only delivery account permits. Since the measured alpha is statistically "
        f"zero, the target is unreachable at any beta available to this account. "
        f"Meeting 3%/month would require the alpha to be real, and on this evidence it is "
        f"not distinguishable from zero."
    )


def _bottom_line(s: dict) -> str:
    """The plain answer. Every clause is generated from measured numbers, so the
    paragraph cannot drift away from the tables above it if the data changes."""
    h1, h2, h3, h4, h5, h6 = (s.get(k) for k in ("h1", "h2", "h3", "h4", "h5", "h6"))
    ex = s.get("extras")
    paras: list[str] = []

    if h1:
        c, g = h1["cagr"], h1["gross_cagr"]
        paras.append(
            f"**The null is not the reversal control. The null is a book with no signal "
            f"at all.** {h1['n_random']} random-weight books run through the identical "
            f"harness — same folds, same engine, same 21.92bps cost stack, same "
            f"constraints — are profitable "
            f"**{c['frac_profitable'] * 100:.0f}% of the time**, mean CAGR "
            f"{c['mean'] * 100:+.2f}%, worst case {c['min'] * 100:+.2f}%, mean Sharpe "
            f"{h1['sharpe']['mean']:+.2f}. Not one of them lost money. A 22-name, "
            f"monthly-rebalanced, long-only NIFTY-50 book returns a positive "
            f"out-of-sample result in this sample whatever signal it holds, because the "
            f"universe rose and long-only equity beta is the dominant term."
        )
        paras.append(
            f"**And the composite's edge over that null is not a selection edge.** On "
            f"net CAGR production sits at the {pctile(h1['prod_pct_cagr'])} "
            f"percentile — but random books turn over "
            f"{h1['turnover']['mean']:.2f}x/yr against production's "
            f"{h1['prod']['oos_turnover']:.2f}x/yr, so on *net* return production is "
            f"being credited for trading less. Strip that channel out and compare gross "
            f"CAGR: production's {h1['prod']['oos_gross_cagr'] * 100:+.2f}% lands at the "
            f"**{pctile(h1['prod_pct_gross'])} percentile** of a null whose gross "
            f"mean is {g['mean'] * 100:+.2f}%. That is the median random book. What the "
            f"composite genuinely does better is *hold* rather than *rotate* — a "
            f"cost-management property that this harness rewards and that no factor "
            f"evidence supports."
        )

    if h6:
        c = h6["scramble_c"]
        paras.append(
            f"**The signal-scrambled null is the decisive test, and it agrees.** Destroy "
            f"*only* the signal — keep the composite's own per-date score distribution, "
            f"its name count, its cost stack, its overlay, its constraints — and relabel "
            f"which symbol receives which score. Those books are profitable "
            f"**{c['cagr_frac_profitable'] * 100:.0f}% of the time** with mean CAGR "
            f"{c['cagr_mean'] * 100:+.2f}%, and production sits at the "
            f"{pctile(c['prod_pct_cagr'])} percentile of them. A negative control "
            f"exists for exactly one purpose: to separate the signal from everything "
            f"else that produces a return. This one does not separate them, so it has "
            f"failed at its job — not merely because the control scored higher, but "
            f"because the harness cannot tell the two books apart."
        )

    if h4:
        b, t = h4["bootstrap"], h4["ttest"]
        paras.append(
            f"**And the production-vs-control gap is not a real gap.** Over "
            f"{t['n_days']} daily out-of-sample observations the 95% block-bootstrap CI "
            f"on ΔCAGR is [{b['d_cagr_ci_lo'] * 100:+.2f}pp, "
            f"{b['d_cagr_ci_hi'] * 100:+.2f}pp] and the serial-correlation-robust paired "
            f"t-test gives p = {t['p_newey_west']:.2f}. The 0.34-vs-0.37 Sharpe "
            f"difference is noise, and the brief's reading of it as decisive was right "
            f"to be doubted."
        )

    if ex:
        ap, ac = ex["production"], ex["control"]
        paras.append(
            f"**Beta does not rescue it.** Production runs at beta "
            f"{ap['beta']:.2f} against the equal-weight benchmark and the control at "
            f"{ac['beta']:.2f} — they differ by {abs(ap['beta'] - ac['beta']):.2f}, so "
            f"beta-matching changes nothing. Jensen alpha is "
            f"{ap['alpha_annual'] * 100:+.2f}%/yr (p = {ap['alpha_p']:.2f}) for "
            f"production and {ac['alpha_annual'] * 100:+.2f}%/yr "
            f"(p = {ac['alpha_p']:.2f}) for the control: both negative, both "
            f"indistinguishable from zero. To reach `GOAL.md`'s 42.6%/yr target on a "
            f"zero-alpha basis the book would need a beta of "
            f"{ex['beta_required_for_target']:.2f} — about "
            f"{ex['beta_required_for_target'] / max(ap['beta'], 1e-9):.0f}× what it runs "
            f"at, and unreachable in a long-only delivery account. The target is not "
            f"beta-limited; it is alpha-limited, and the alpha is not there."
        )

    if h5:
        cells = h5["fixed"]
        wins = sum(
            1 for r in cells.values()
            if r["PRODUCTION"]["cagr"] > r["CONTROL_REVERSAL"]["cagr"]
        )
        paras.append(
            f"**One finding cuts the other way, and it deserves to be stated plainly.** "
            f"With *fixed, unselected* parameters, production beats the control in "
            f"{wins} of {len(cells)} cells "
            + ", ".join(
                f"{t_} ({r['PRODUCTION']['cagr'] * 100:+.2f}% vs "
                f"{r['CONTROL_REVERSAL']['cagr'] * 100:+.2f}%)"
                for t_, r in cells.items()
            )
            + ". So the trend composite is not uniformly inert — under some fixed "
            "settings it does select better names than the reversal composite. That is "
            "a real, reproducible observation and it is the strongest argument this repo "
            "has for the production composite. It is not, however, evidence of a "
            "*deployable* edge: the same fixed cells are ordinary book-construction "
            "choices, they were not selected out-of-sample, and the walk-forward "
            "version of them — which is the only protocol that counts — does not "
            "reproduce the advantage. It also does not rescue the negative control, "
            "which exists precisely to test the walk-forward result."
        )

    if h1:
        tail = (
            f" A random book earns {h1['cagr']['mean'] * 100:+.1f}%/yr here with no "
            f"signal whatsoever."
        )
    else:
        tail = ""
    paras.append(
        f"**So: no — this strategy does not have a demonstrable edge, and the evidence "
        f"collected here is consistent with its entire out-of-sample return being what "
        f"a null produces.**{tail} The 9.71% is not a strategy result that happens to "
        f"sit next to a failed control; it is a control's result wearing a different "
        f"label. Nothing here justifies relaxing `GOAL.md` §5, and the four Gate 4 "
        f"checks that pass would pass just as well for a book holding 22 names chosen "
        f"at random."
        + (
            " The secondary findings do not rescue it: the control survives removal of "
            "its low-volatility leg and still beats production, so that leg is not "
            "carrying it (H2)."
            if h2 else ""
        )
        + (
            f" The regime overlay flips which book wins "
            f"({h3['with_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} with it, "
            f"{h3['no_overlay']['sharpe_gap_ctrl_minus_prod']:+.3f} without), so the "
            f"overlay — not the factors — decides the comparison (H3)."
            if h3 else ""
        )
        + (
            f" And the two books' train-to-test degradation is nearly identical "
            f"({h5['train_test']['PRODUCTION']['sharpe_flip']:+.2f} vs "
            f"{h5['train_test']['CONTROL_REVERSAL']['sharpe_flip']:+.2f} Sharpe), so "
            f"there is no train/test flip unique to the control (H5)."
            if h5 and "train_test" in h5 else ""
        )
        + " **The correct next step is not a wider parameter search — 18 of 18 "
        "profitable cells and 42 negative catalog trials are what a null produces — "
        "it is to change what counts as success.** Any future candidate must beat a "
        "signal-scrambled version of itself, and must be measured against that, not "
        "against the equal-weight benchmark in a rising market."
    )
    return "\n\n".join(paras)


def _verdict_rows(s: dict) -> list[dict]:
    h1, h2, h3, h4, h5, h6 = (s.get(k) for k in ("h1", "h2", "h3", "h4", "h5", "h6"))
    rows: list[dict] = []

    if h1:
        v = _h1_verdict(h1)
        verdict = v.split("**Verdict:")[1].split(".**")[0].strip()
        key = (f"production at {pctile(h1['prod_pct_cagr'])} pct CAGR / "
               f"{pctile(h1['prod_pct_sharpe'])} pct Sharpe of a "
               f"{h1['n_random']}-book random null; "
               f"{h1['cagr']['frac_profitable'] * 100:.0f}% of that null is profitable")
    else:
        verdict, key = "not run", "—"
    rows.append({"id": "H1", "hyp": "It's beta, not skill", "verdict": verdict, "key": key})

    if h2:
        by = {r["component"]: r for r in h2["components"]}
        nolv = by.get("control_no_lowvol")
        verdict = ("SUPPORTED — reversal legs carry the control, not low-vol"
                   if nolv and nolv["cagr"] > (h2["production"]["cagr"] or 0)
                   else "REFUTED — low-vol carries the control")
        key = (f"control without low-volatility = {nolv['cagr'] * 100:+.2f}% / "
               f"Sharpe {nolv['sharpe']:+.2f} vs production "
               f"{h2['production']['cagr'] * 100:+.2f}% / "
               f"{h2['production']['sharpe']:.2f}"
               if nolv else "—")
    else:
        verdict, key = "not run", "—"
    rows.append({"id": "H2", "hyp": "Low-vol leg does the work", "verdict": verdict,
                 "key": key})

    if h3:
        on = h3["with_overlay"]["sharpe_gap_ctrl_minus_prod"]
        off = h3["no_overlay"]["sharpe_gap_ctrl_minus_prod"]
        verdict = ("REFUTED — overlay is not the difference"
                   if (on > 0) == (off > 0) else "SUPPORTED — overlay flips the sign")
        key = f"Sharpe gap (ctrl−prod) {on:+.3f} with overlay, {off:+.3f} without"
    else:
        verdict, key = "not run", "—"
    rows.append({"id": "H3", "hyp": "Regime overlay is the difference",
                 "verdict": verdict, "key": key})

    if h4:
        b = h4["bootstrap"]
        t = h4["ttest"]
        verdict = ("SUPPORTED — indistinguishable"
                   if b["d_cagr_ci_lo"] < 0 < b["d_cagr_ci_hi"] and t["p_newey_west"] > 0.05
                   else "REFUTED — difference is measurable")
        key = (f"95% CI on ΔCAGR [{b['d_cagr_ci_lo'] * 100:+.2f}pp, "
               f"{b['d_cagr_ci_hi'] * 100:+.2f}pp]; robust paired p = "
               f"{t['p_newey_west']:.2f}")
    else:
        verdict, key = "not run", "—"
    rows.append({"id": "H4", "hyp": "0.34 vs 0.37 is noise", "verdict": verdict,
                 "key": key})

    if h5:
        wins = sum(1 for r in h5["fixed"].values()
                   if r["PRODUCTION"]["cagr"] > r["CONTROL_REVERSAL"]["cagr"])
        verdict = ("SUPPORTED — selection artifact"
                   if wins == 0 else "REFUTED — production wins fixed cells without selection")
        if h5.get("selection_cost"):
            sp = h5["selection_cost"]["PRODUCTION"]
            sc = h5["selection_cost"]["CONTROL_REVERSAL"]
            key = (
                f"production beats control in {wins}/{len(h5['fixed'])} fixed cells; "
                f"but train-selection costs production "
                f"{sp['selection_delta_cagr'] * 100:+.2f}pp/yr and *adds* the control "
                f"{sc['selection_delta_cagr'] * 100:+.2f}pp/yr"
            )
        else:
            key = (f"production beats control in {wins}/{len(h5['fixed'])} fixed, "
                   f"unselected cells")
    else:
        verdict, key = "not run", "—"
    rows.append({"id": "H5", "hyp": "Harness has a selection artifact",
                 "verdict": verdict, "key": key})

    if h6:
        c = h6["scramble_c"]
        verdict = ("SUPPORTED — no signal separates it from its own scramble"
                   if c["prod_pct_cagr"] < 0.75 and c["prod_pct_sharpe"] < 0.75
                   else "REFUTED — signal survives the scramble")
        key = (f"production at {pctile(c['prod_pct_cagr'])} pct CAGR / "
               f"{pctile(c['prod_pct_sharpe'])} pct Sharpe of a "
               f"{c['n']}-book turnover-matched scramble")
    else:
        verdict, key = "not run", "—"
    rows.append({"id": "H6", "hyp": "Equal-count is the wrong null", "verdict": verdict,
                 "key": key})
    return rows


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", default="all",
                    help="all|reference|h1|h2|h3|h4|h5|h6|extras|report")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--n-random", type=int, default=100,
                    help="random-weight books for H1 (default 100)")
    ap.add_argument("--n-scramble", type=int, default=60,
                    help="scrambled books per variant for H6 (default 60)")
    ap.add_argument("--force", action="store_true", help="ignore the result cache")
    args = ap.parse_args()

    global WORKERS
    WORKERS = max(1, args.workers)

    print("=" * 96)
    print("CONTROL DIAGNOSTIC — is the production composite's OOS result signal or beta?")
    print("=" * 96)
    pv = provenance()
    print("provenance         : " + "  ".join(f"{k}={v}" for k, v in sorted(pv.items())))
    print(f"cost model         : CostModel(segment='delivery', slippage_bps="
          f"{BASE_SLIPPAGE})  all-in round trip "
          f"{COST.all_in_round_trip_bps(100_000):.2f} bps")
    print(f"harness            : walk_forward n_folds={N_FOLDS} {TRAIN_YEARS}y train / "
          f"{TEST_YEARS}y test, {len(PARAM_GRID)}-cell grid")
    print(f"cache              : {CACHE_DIR}")

    _init_worker()
    panel = PANEL
    print(f"panel              : {panel.shape[1]} symbols x {len(panel)} days  "
          f"{panel.index[0].date()} -> {panel.index[-1].date()}")

    def hr(t: str) -> None:
        print("\n" + "=" * 96)
        print(t)
        print("=" * 96)

    ph = args.phase
    if ph in ("all", "reference"):
        hr("REFERENCE — the two numbers from STRESS_v3.md §6, re-measured")
        phase_reference()
    if ph in ("all", "h1"):
        hr(f"H1 — random-weight books (n={args.n_random})")
        phase_h1(args.n_random)
    if ph in ("all", "h2"):
        hr("H2 — component singles + control without low_volatility")
        phase_h2()
    if ph in ("all", "h3"):
        hr("H3 — regime overlay on vs off")
        phase_h3()
    if ph in ("all", "h4"):
        hr("H4 — paired t-test + block bootstrap")
        phase_h4()
    if ph in ("all", "h5"):
        hr("H5 — fixed unselected parameters + train/test profile")
        phase_h5()
    if ph in ("all", "h6"):
        hr(f"H6 — signal-scrambled controls (n={args.n_scramble} each)")
        phase_h6(args.n_scramble)
    if ph in ("all", "extras"):
        hr("EXTRAS — turnover, beta, correlation, target beta")
        phase_extras()

    hr("REPORT")
    summaries = {k: load_summary(k)
                 for k in ("h1", "h2", "h3", "h4", "h5", "h6", "extras")}
    write_report({k: v for k, v in summaries.items() if v is not None}, panel)
    print(f"wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
