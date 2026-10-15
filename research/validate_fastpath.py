#!/usr/bin/env python
"""Exhaustive validation of the tail-slicing indicator fast path.

What is being claimed
---------------------
``research/optimize/fastpath.py`` replaces ``sma``, ``rsi``, ``roc`` and ``stochastic``
with wrappers that hand the underlying function only the *tail* of its input, then
rebinds every call site across ``sys.modules``. The claim under test is that this is a
**no-op on results**: each patched function reads nothing but the tail, so pre-slicing
cannot change the value.

This module tests the claim six ways (phases ``R1``-``R6``) and writes a machine-readable
bundle to ``tem/fastpath_results.json``; ``reports/FASTPATH_VALIDATION.md`` is written
from that bundle by hand.

Run
---
    .venv/bin/python research/validate_fastpath.py --phase all
    .venv/bin/python research/validate_fastpath.py --phase R3

Phases
------
``R1``  all 84 strategies x 48 symbols x {TRAIN, TEST}, shipped default config
``R2``  5 random configs per strategy (``StrategySpec.sample``) over all 48 symbols,
        plus 2 forced period configs (small=3 / large=200) over a documented 8-symbol
        subset, so the slice-size range is covered at both ends regardless of sampling
``R3``  synthetic edge lengths: len<period, ==period, ==period+1, ==2*period, plus
        all-constant (zero variance) and single-spike series
``R4``  container types for ``_tail``: list, tuple, ndarray, deque, pandas Series
``R5``  rebind completeness after ``install()``, incl. an audit for references the
        top-level ``__dict__`` walk in ``_rebind_all`` cannot reach
``R6``  determinism: same process twice, plus two fresh subprocesses

Why the harness owns its own install/uninstall
-----------------------------------------------
``fastpath.uninstall()`` restores ``indicators.sma/rsi/roc/stochastic`` but does **not**
undo the module-level rebind performed by ``_rebind_all()``, and it then clears
``_ORIGINALS`` -- throwing away the only record needed to undo it. This harness
therefore snapshots every binding *before* the first ``install()`` and restores from that
snapshot, a strict superset of what ``uninstall()`` does.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import logging
import os
import pathlib
import subprocess
import sys
import time
from typing import Any

REPO = pathlib.Path(__file__).resolve().parents[1]
# `research` is an implicit namespace package and `cryptobot` is installed from `src/`,
# so running this file as `python research/validate_fastpath.py` puts `research/` --
# not the repo root -- on sys.path. Put the root back.
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
TEM = REPO / "tem"
TEM.mkdir(exist_ok=True)
RESULTS_PATH = TEM / "fastpath_results.json"

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from cryptobot.strategies import indicators as I  # noqa: E402
from research.optimize import fastpath  # noqa: E402
from research.optimize import splitter as S  # noqa: E402
from research.optimize.backtest import BacktestError, run_single_stock  # noqa: E402
from research.optimize.catalog import discover  # noqa: E402

PATCHED_NAMES = ("sma", "rsi", "roc", "stochastic")
PERIOD_SEED = 20261013
DET_CASES = [("adx_trend", "tcs"), ("rsi_strategy", "infy"),
             ("stochastic_strategy", "sbin"), ("ensemble_signals_strategy", "hdfcbank")]

#: The pristine originals, captured at import time before anything is installed.
ORIG_GET = {n: getattr(I, n) for n in PATCHED_NAMES}

log = logging.getLogger("validate_fastpath")


# --------------------------------------------------------------------------- #
# Install / uninstall under harness control
# --------------------------------------------------------------------------- #
def snapshot_bindings() -> dict[str, dict[str, Any]]:
    """Record every module-level binding that currently holds one of the four originals."""
    targets = {id(getattr(I, n)) for n in PATCHED_NAMES}
    snap: dict[str, dict[str, Any]] = {}
    for modname, mod in list(sys.modules.items()):
        d = getattr(mod, "__dict__", None)
        if not d:
            continue
        hits = {a: v for a, v in d.items() if id(v) in targets}
        if hits:
            snap[modname] = hits
    return snap


def restore_bindings(snap: dict[str, dict[str, Any]]) -> int:
    n = 0
    for modname, hits in snap.items():
        mod = sys.modules.get(modname)
        if mod is None:
            continue
        for attr, val in hits.items():
            try:
                setattr(mod, attr, val)
                n += 1
            except Exception:  # noqa: BLE001 - read-only module namespace
                continue
    return n


def force_unpatched(snap: dict[str, dict[str, Any]]) -> None:
    """Return the process to the pristine, unpatched state."""
    fastpath._INSTALLED = False
    fastpath._ORIGINALS.clear()
    restore_bindings(snap)


def force_patched() -> None:
    """Install. Must be preceded by ``force_unpatched`` so the rebind sees the originals."""
    fastpath.install()


def _noop_ensure() -> bool:
    """Replacement for ``fastpath.ensure``.

    ``run_single_stock`` calls ``fastpath.ensure()`` unconditionally. Letting it run would
    install the fast path halfway through the unpatched arm, so the harness drives
    installation explicitly and this stub keeps ``run_single_stock`` from overriding it.
    Applied in this process only; ``research/optimize`` is never written to.
    """
    return False


fastpath.ensure = _noop_ensure  # noqa: E305 - deliberate; see docstring


# --------------------------------------------------------------------------- #
# Fingerprinting / exact comparison
# --------------------------------------------------------------------------- #
TRADE_FIELDS = ("date", "side", "shares", "price", "value", "fee", "tax", "pnl")
SCALAR_FIELDS = ("total_tax", "total_fees", "turnover", "exposure", "n_trades")


def fingerprint(res) -> dict:
    eq = res.equity.to_numpy(dtype=np.float64, copy=False)
    dr = res.daily_returns.to_numpy(dtype=np.float64, copy=False)
    trades = tuple(tuple(getattr(t, f) for f in TRADE_FIELDS) for t in res.trades)
    h = hashlib.blake2b(digest_size=16)
    h.update(eq.tobytes())
    h.update(dr.tobytes())
    for t in trades:
        h.update(repr(t).encode())
    for f in ("total_tax", "total_fees", "turnover"):
        h.update(repr(float(getattr(res, f))).encode())
    h.update(np.asarray([res.invested_bars, res.n_bars], dtype=np.int64).tobytes())
    return {
        "equity": res.equity,
        "daily_returns": res.daily_returns,
        "trades": trades,
        "total_tax": float(res.total_tax),
        "total_fees": float(res.total_fees),
        "turnover": float(res.turnover),
        "exposure": float(res.exposure),
        "n_trades": len(trades),
        "invested_bars": int(res.invested_bars),
        "n_bars": int(res.n_bars),
        "digest": h.hexdigest(),
    }


def _nan_aware_ne(a: pd.Series, b: pd.Series) -> int:
    x = a.to_numpy(dtype=np.float64)
    y = b.to_numpy(dtype=np.float64)
    same = (x == y) | (np.isnan(x) & np.isnan(y))
    return int((~same).sum())


def compare(fp: dict, fq: dict) -> list[str]:
    """Human-readable divergences between two fingerprints.

    Series are compared with ``.equals`` (exact and NaN-aware), never with a tolerance.
    """
    d: list[str] = []
    for name in ("equity", "daily_returns"):
        a, b = fp[name], fq[name]
        if len(a) != len(b):
            d.append(f"{name}: length {len(a)} != {len(b)}")
        elif not a.equals(b):
            x = a.to_numpy(dtype=np.float64)
            y = b.to_numpy(dtype=np.float64)
            both = ~(np.isnan(x) | np.isnan(y))
            maxdiff = float(np.max(np.abs(x[both] - y[both]))) if both.any() else float("nan")
            d.append(f"{name}: .equals() False, {_nan_aware_ne(a, b)} differing rows, "
                     f"max|diff|={maxdiff!r}")
    for f in SCALAR_FIELDS:
        if repr(fp[f]) != repr(fq[f]):
            d.append(f"{f}: {fp[f]!r} != {fq[f]!r}")
    for f in ("invested_bars", "n_bars"):
        if fp[f] != fq[f]:
            d.append(f"{f}: {fp[f]} != {fq[f]}")
    ta, tb = fp["trades"], fq["trades"]
    if len(ta) != len(tb):
        d.append(f"trade count {len(ta)} != {len(tb)}")
    else:
        for i, (x, y) in enumerate(zip(ta, tb, strict=True)):
            if repr(x) != repr(y):
                bad = [f for f, u, v in zip(TRADE_FIELDS, x, y, strict=True) if repr(u) != repr(v)]
                d.append(f"trade[{i}] fields differ: {bad} | {x} vs {y}")
                break
    if fp["digest"] != fq["digest"]:
        d.append(f"digest {fp['digest']} != {fq['digest']}")
    return d


def _safe(f, call):
    try:
        return ("ok", call(f))
    except Exception as exc:  # noqa: BLE001
        return ("exc", f"{type(exc).__name__}: {exc}"[:140])


def _same(a, b) -> bool:
    if a[0] != b[0]:
        return False
    if a[0] == "exc":
        return a[1] == b[1]
    x, y = a[1], b[1]
    if isinstance(x, float) and isinstance(y, float) and np.isnan(x) and np.isnan(y):
        return True
    return repr(x) == repr(y)


# --------------------------------------------------------------------------- #
# Config sampling
# --------------------------------------------------------------------------- #
PERIOD_LIKE = ("period", "lookback", "window", "length", "fast", "slow", "signal",
               "smooth", "atr", "std")


def period_fields(spec) -> list[str]:
    return [p.name for p in spec.params
            if p.kind == "int" and any(k in p.name.lower() for k in PERIOD_LIKE)]


def build_configs(spec, n_random: int) -> list[tuple[str, dict, str]]:
    """``[(label, params, kind), ...]`` -- default, seeded randoms, forced periods.

    ``StrategySpec.sample`` is used verbatim for the random draws. The RNG is seeded from
    ``(PERIOD_SEED, strategy name)`` so the entire matrix is reproducible.
    """
    cfgs: list[tuple[str, dict, str]] = [("default", dict(spec.default), "default")]
    seen = {json.dumps(spec.default, sort_keys=True, default=str)}
    rng = np.random.default_rng(
        int(hashlib.blake2b(f"{PERIOD_SEED}|{spec.name}".encode(), digest_size=8).hexdigest(),
                            16) % (2**63)
    )
    guard = 0
    while len(cfgs) < 1 + n_random and guard < 2000:
        guard += 1
        p = spec.sample(rng)
        k = json.dumps(p, sort_keys=True, default=str)
        if k in seen:
            continue
        seen.add(k)
        cfgs.append((f"random_{len(cfgs) - 1}", p, "random"))

    # Forced period coverage. Uniform sampling over [2, 250] leaves the small-period (<10)
    # end of the slice-size range untested for most strategies, and that is exactly where
    # an off-by-one in ``need = period + 1`` would hide.
    for pname in period_fields(spec):
        for tag, val in (("forced_small", 3), ("forced_large", 200)):
            vals = dict(spec.default)
            vals[pname] = val
            k = json.dumps(vals, sort_keys=True, default=str)
            if k in seen:
                continue
            seen.add(k)
            cfgs.append((f"{tag}:{pname}", vals, "forced"))
    return cfgs


def observed_periods(spec, cfgs) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {p: [] for p in period_fields(spec)}
    for _label, params, _kind in cfgs:
        for p in out:
            v = params.get(p)
            if isinstance(v, int):
                out[p].append(v)
    return out


# --------------------------------------------------------------------------- #
# Phase R1 / R2 -- backtest-level A/B over the full catalog
# --------------------------------------------------------------------------- #
_G: dict[str, Any] = {}


def _task_init(spec_name: str, stock: str, n_random: int, forced: bool) -> dict:
    """Run one (strategy, stock) pair both ways and compare, in-process, exactly."""
    if "specs" not in _G:
        _G["specs"] = {s.name: s for s in discover()}
        _G["snap"] = snapshot_bindings()
    spec = _G["specs"][spec_name]
    snap = _G["snap"]

    all_cfgs = build_configs(spec, n_random)
    cfgs = all_cfgs if forced else [c for c in all_cfgs if c[2] != "forced"]
    periods = observed_periods(spec, all_cfgs)

    tr = S.train_bars(stock)
    te = S.test_bars(stock)
    windows = {"TRAIN": tr, "TEST": te}

    arms: dict[str, dict[str, dict]] = {"unpatched": {}, "patched": {}}
    errors: dict[str, str] = {}
    live_wrapped: dict[str, bool] = {}

    for mode in ("unpatched", "patched"):
        if mode == "unpatched":
            force_unpatched(snap)
        else:
            force_patched()
            live_wrapped = {n: hasattr(getattr(I, n), "__wrapped__") for n in PATCHED_NAMES}
        for wname, bars in windows.items():
            if bars.empty:
                continue
            for label, params, _kind in cfgs:
                key = f"{wname}|{label}"
                try:
                    res = run_single_stock(bars, spec, params, rebalance="M")
                except (BacktestError, Exception) as exc:  # noqa: BLE001
                    errors[f"{mode}|{key}"] = f"{type(exc).__name__}: {exc}"[:160]
                    continue
                arms[mode][key] = fingerprint(res)

    divergences: list[dict] = []
    n_compared = 0
    for key in sorted(set(arms["unpatched"]) & set(arms["patched"])):
        n_compared += 1
        diffs = compare(arms["unpatched"][key], arms["patched"][key])
        if diffs:
            wname, label = key.split("|", 1)
            divergences.append({
                "strategy": spec_name, "stock": stock, "window": wname, "config": label,
                "params": next(p for lbl, p, _k in cfgs if lbl == label),
                "live_wrapped": live_wrapped,
                "unpatched_digest": arms["unpatched"][key]["digest"],
                "patched_digest": arms["patched"][key]["digest"],
                "detail": diffs,
            })
    return {
        "strategy": spec_name, "stock": stock,
        "n_configs": len(cfgs), "n_backtests": sum(len(v) for v in arms.values()),
        "n_compared": n_compared, "n_divergences": len(divergences),
        "n_errors": len(errors),
        "errors_unpatched": sum(1 for k in errors if k.startswith("unpatched")),
        "errors_patched": sum(1 for k in errors if k.startswith("patched")),
        "error_sample": dict(list(errors.items())[:4]),
        "equal_arms": set(arms["unpatched"]) == set(arms["patched"]),
        "all_live_wrapped": all(live_wrapped.values()) if live_wrapped else False,
        "divergences": divergences,
        "periods": periods,
    }


def phase_catalog(n_random: int, workers: int, forced_subset: list[str],
                  smoke: bool = False) -> dict:
    specs = discover()
    symbols = S.available_symbols("1d")
    if smoke:
        specs = specs[:2]
        symbols = symbols[:2]
    forced_set = set(forced_subset)
    tasks = [(s.name, st, n_random, st in forced_set) for s in specs for st in symbols]
    t0 = time.time()
    from joblib import Parallel, delayed

    print(f"[R1/R2] {len(specs)} strategies x {len(symbols)} symbols = {len(tasks)} pairs, "
          f"{workers} workers, {n_random} random configs/strategy", flush=True)
    rows = Parallel(n_jobs=workers, batch_size=4, backend="loky", verbose=5)(
        delayed(_task_init)(*t) for t in tasks
    )
    pvals: list[int] = [b for r in rows for v in r["periods"].values() for b in v]
    errs = [f"{r['strategy']}/{r['stock']}: {r['error_sample']}"
            for r in rows if r["n_errors"]]
    return {
        "n_strategies": len(specs),
        "n_symbols": len(symbols),
        "symbols": symbols,
        "forced_subset": forced_subset,
        "n_random_configs": n_random,
        "n_pairs": len(tasks),
        "elapsed_s": round(time.time() - t0, 1),
        "total_backtests": sum(r["n_backtests"] for r in rows),
        "total_compared": sum(r["n_compared"] for r in rows),
        "total_divergences": sum(r["n_divergences"] for r in rows),
        "total_errors": sum(r["n_errors"] for r in rows),
        "errors_unpatched": sum(r["errors_unpatched"] for r in rows),
        "errors_patched": sum(r["errors_patched"] for r in rows),
        "unbalanced_arms": [f"{r['strategy']}/{r['stock']}" for r in rows if not r["equal_arms"]],
        "arms_not_all_wrapped": [f"{r['strategy']}/{r['stock']}" for r in rows
                                 if not r["all_live_wrapped"]],
        "divergences": [d for r in rows for d in r["divergences"]][:200],
        "period_values_observed": {
            "n": len(pvals),
            "min": min(pvals) if pvals else None,
            "max": max(pvals) if pvals else None,
            "histogram": dict(collections.Counter(
                "<10" if b < 10 else "10-100" if b <= 100 else ">100" for b in pvals)),
        },
        "error_sample": errs[:25],
        "n_pairs_with_errors": len(errs),
    }


# --------------------------------------------------------------------------- #
# Phase R3 -- synthetic edge lengths
# --------------------------------------------------------------------------- #
def _series_variants(period: int) -> dict[str, np.ndarray]:
    n = max(2 * period, 8)
    rng = np.random.default_rng(period)
    walk = np.cumprod(1.0 + rng.normal(0, 0.01, n)) * 100.0
    spike = walk.copy()
    spike[-1] = walk[-1] * 3.0
    return {
        "len<period": walk[: max(1, period - 1)],
        "len==period-1": walk[: max(1, period - 1)],
        "len==period": walk[:period],
        "len==period+1": walk[: period + 1],
        "len==period+2": walk[: period + 2],
        "len==2*period": walk[: 2 * period],
        "len==2*period+1": walk[: 2 * period + 1],
        "constant_zero_variance": np.full(n, 42.0),
        "single_spike": spike,
        "ramp": np.arange(1, n + 1, dtype=float),
        "tiny_len1": walk[:1],
        "tiny_len2": walk[:2],
    }


def phase_edge_lengths() -> dict:
    force_unpatched({})
    snap = snapshot_bindings()
    orig = {n: getattr(I, n) for n in PATCHED_NAMES}
    force_patched()

    periods = [1, 2, 3, 4, 5, 9, 10, 14, 20, 21, 50, 99, 100, 101, 200, 250, 300]
    failures: list[dict] = []
    n_cases = 0
    n_rows = []
    for period in periods:
        for vname, closes in _series_variants(period).items():
            highs, lows = closes * 1.01, closes * 0.99
            cases = {
                "sma": (lambda f, c=closes, p=period: f(c, p), closes),
                "rsi": (lambda f, c=closes, p=period: f(c, p), closes),
                "roc": (lambda f, c=closes, p=period: f(c, p), closes),
                "stochastic": (lambda f, c=closes, h=highs, lo=lows,
                               p=period: f(c, h, lo, p), closes),
            }
            for fname, (call, _x) in cases.items():
                n_cases += 1
                exp, got = _safe(orig[fname], call), _safe(getattr(I, fname), call)
                ok = _same(exp, got)
                n_rows.append(ok)
                if not ok:
                    failures.append({
                        "period": period, "variant": vname, "fn": fname,
                        "len": int(len(closes)),
                        "expected": repr(exp[1]), "actual": repr(got[1]),
                        "repro": f"indicators.{fname}(series_of_{len(closes)}, "
                                 f"period={period})",
                    })

    # The default-argument path. `indicators.rsi` defaults to 14 and `stochastic` to 14;
    # the wrappers declare `period=20` / `period=14`. Any call that omits `period`
    # therefore takes a *different* period under the patch.
    default_failures = []
    for period in (3, 14, 60):
        closes = (np.cumprod(1.0 + np.random.default_rng(period).normal(0, 0.01, 120))
                  * 100.0)
        highs, lows = closes * 1.01, closes * 0.99
        for fname, mk in (("rsi", lambda f, c=closes: f(c)),
                          ("stochastic", lambda f, c=closes, h=highs,
                           lo=lows: f(c, h, lo))):
            n_cases += 1
            exp, got = _safe(orig[fname], mk), _safe(getattr(I, fname), mk)
            if not _same(exp, got):
                default_failures.append({
                    "fn": fname, "expected": repr(exp[1]), "actual": repr(got[1]),
                    "indicator_default": "rsi: period=14, stochastic: period=14",
                    "wrapper_default": "sma/rsi/roc: period=20, stochastic: period=14",
                    "repro": f"indicators.{fname}(series)   # period omitted",
                })
    failures.extend({**d, "variant": "default_arg", "period": "omitted"} for d in default_failures)

    # Out-of-search-space boundary probes: period <= 0 does not occur in the catalog
    # (NAME_BOUNDS floors every period knob at 2), but it is where `values[-0:]` changes
    # meaning, so it is recorded explicitly.
    probes = []
    for period in (0, -1, -5):
        closes = np.cumprod(1.0 + np.random.default_rng(7).normal(0, 0.01, 60)) * 100.0
        highs, lows = closes * 1.01, closes * 0.99
        for fname, call in {
            "sma": lambda f, c=closes, p=period: f(c, p),
            "rsi": lambda f, c=closes, p=period: f(c, p),
            "roc": lambda f, c=closes, p=period: f(c, p),
            "stochastic": lambda f, c=closes, h=highs, lo=lows, p=period: f(c, h, lo, p),
        }.items():
            exp, got = _safe(orig[fname], call), _safe(getattr(I, fname), call)
            ok = _same(exp, got)
            probes.append({"fn": fname, "period": period, "match": ok,
                           "expected": repr(exp[1]), "actual": repr(got[1])})
            if not ok:
                failures.append({
                    "period": period, "variant": "random60", "fn": fname,
                    "expected": repr(exp[1]), "actual": repr(got[1]),
                    "repro": f"indicators.{fname}(series, period={period})",
                    "note": "period outside the catalog search space",
                })

    # Non-integer periods. Every Config field is typed `int` and the search space only
    # produces ints, but the wrapper coerces with `int(period)` where the original does
    # not -- so a non-int argument is a place where the coercion itself changes behaviour.
    nonint_failures = []
    for period in (14.0, 14.5, "14", np.int64(14), True):
        closes = np.cumprod(1.0 + np.random.default_rng(5).normal(0, 0.01, 120)) * 100.0
        highs, lows = closes * 1.01, closes * 0.99
        for fname, call in {
            "sma": lambda f, c=closes, q=period: f(c, q),
            "rsi": lambda f, c=closes, q=period: f(c, q),
            "roc": lambda f, c=closes, q=period: f(c, q),
            "stochastic": lambda f, c=closes, h=highs, lo=lows, q=period: f(c, h, lo, q),
        }.items():
            n_cases += 1
            exp, got = _safe(orig[fname], call), _safe(getattr(I, fname), call)
            if not _same(exp, got):
                rec = {"fn": fname, "period": repr(period),
                       "expected": repr(exp[1]), "actual": repr(got[1]),
                       "repro": f"indicators.{fname}(series, period={period!r})",
                       "note": "non-int period; Config fields are typed int"}
                nonint_failures.append(rec)
                failures.append({**rec, "period": repr(period), "variant": "nonint_period"})

    force_unpatched(snap)
    return {
        "n_cases": n_cases, "periods": periods, "n_failures": len(failures),
        "nonint_period_failures": nonint_failures,
        "n_nonint_period_failures": len(nonint_failures),
        "failures": failures[:80],
        "default_arg_failures": default_failures,
        "n_default_arg_failures": len(default_failures),
        "out_of_space_probes": probes,
    }


# --------------------------------------------------------------------------- #
# Phase R4 -- container types
# --------------------------------------------------------------------------- #
def phase_containers() -> dict:
    from collections import deque

    force_unpatched({})
    snap = snapshot_bindings()
    orig = {n: getattr(I, n) for n in PATCHED_NAMES}
    force_patched()

    failures: list[dict] = []
    rows: list[dict] = []
    for period in (3, 14, 60, 200):
        base = np.cumprod(1.0 + np.random.default_rng(period).normal(0, 0.01, 400)) * 100.0
        mk = {
            "list": lambda a: list(a),
            "tuple": lambda a: tuple(a.tolist()),
            "ndarray": lambda a: a,
            "deque": lambda a: deque(a.tolist()),
            "pandas_Series": lambda a: pd.Series(a),
        }
        need = {"sma": period, "rsi": period + 1, "roc": period + 1, "stochastic": period}
        for cname, build in mk.items():
            closes, highs, lows = build(base), build(base * 1.01), build(base * 0.99)
            for fname, call in {
                "sma": lambda f, c=closes, p=period: f(c, p),
                "rsi": lambda f, c=closes, p=period: f(c, p),
                "roc": lambda f, c=closes, p=period: f(c, p),
                "stochastic": lambda f, c=closes, h=highs, lo=lows, p=period: f(c, h, lo, p),
            }.items():
                exp, got = _safe(orig[fname], call), _safe(getattr(I, fname), call)
                ok = _same(exp, got)
                trunc = _tail_truncated(build(base), need[fname])
                rows.append({"container": cname, "fn": fname, "period": period,
                             "match": ok, "truncated": trunc,
                             "exp_status": exp[0], "got_status": got[0]})
                if not ok:
                    failures.append({
                        "container": cname, "fn": fname, "period": period,
                        "expected": repr(exp[1]), "actual": repr(got[1]),
                        "truncated": trunc,
                        "repro": f"indicators.{fname}(<{cname} of 400 floats>, "
                                 f"period={period})",
                    })

    detail = {}
    for cname in {r["container"] for r in rows}:
        sub = [r for r in rows if r["container"] == cname]
        detail[cname] = {
            "n": len(sub),
            "all_match": all(r["match"] for r in sub),
            "any_truncated": any(r["truncated"] for r in sub),
            "all_truncated": all(r["truncated"] for r in sub),
            "raised": any(r["got_status"] == "exc" for r in sub),
        }
    force_unpatched(snap)
    return {"n_cases": len(rows), "n_failures": len(failures), "failures": failures[:40],
            "by_container": detail,
            "truncation": {c: sorted({r["truncated"] for r in rows if r["container"] == c})
                           for c in {r["container"] for r in rows}}}


def _tail_truncated(values, n) -> bool:
    try:
        before = len(values)
    except TypeError:
        return False
    try:
        out = fastpath._tail(values, n)
    except Exception as exc:  # noqa: BLE001
        return f"raised {type(exc).__name__}"
    if isinstance(out, str):
        return out
    try:
        return len(out) != before
    except TypeError:
        return "no_len"


# --------------------------------------------------------------------------- #
# Phase R7 -- the real production entry point
# --------------------------------------------------------------------------- #
R7_CASES = [("rsi_strategy", "infy"), ("stochastic_strategy", "sbin"),
            ("adx_trend", "tcs"), ("ensemble_signals_strategy", "hdfcbank"),
            ("moving_average_cross", "reliance"), ("multi_factor_strategy", "tcs"),
            ("breakout_momentum_strategy", "hdfcbank"), ("absolute_momentum", "itc"),
            ("bollinger_bands", "sunpharma"), ("triple_moving_average", "tatasteel")]


def phase_production_path(budget: int = 8, null_replicas: int = 4) -> dict:
    """Run ``engine.optimise_pair`` -- the code the 4,032-pair sweep actually executes --
    both ways and compare the emitted row dicts field by field.

    ``optimise_pair`` searches on TRAIN, selects on (sharpe, calmar), runs the timing null
    model and evaluates the frozen winner on TEST. Comparing its *output row* end to end
    covers the metric layer as well as the equity curve, and proves the harness's
    ``ensure()`` stub did not distort the comparison: the only thing this phase changes is
    whether ``fastpath`` is installed.
    """
    from research.optimize import config as C
    from research.optimize.engine import optimise_pair

    specs = {s.name: s for s in discover()}
    snap = snapshot_bindings()
    cfg = C.RunConfig(budget=budget, null_replicas=null_replicas, rebalance="M",
                      tax_enabled=True, seed=C.MASTER_SEED)

    rows, diffs, failures = [], [], []
    for sname, stock in R7_CASES:
        spec = specs.get(sname)
        if spec is None:
            failures.append({"case": sname, "error": "strategy not found"})
            continue
        out = {}
        for mode in ("unpatched", "patched"):
            if mode == "unpatched":
                force_unpatched(snap)
            else:
                force_patched()
            try:
                row, _summary = optimise_pair(spec, stock, cfg)
                out[mode] = row
            except Exception as exc:  # noqa: BLE001
                out[mode] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}
        a, b = out["unpatched"], out["patched"]
        keys = sorted(set(a) | set(b))
        bad = [k for k in keys
               if json.dumps(a.get(k), sort_keys=True, default=str)
               != json.dumps(b.get(k), sort_keys=True, default=str)]
        rows.append({
            "case": f"{sname}/{stock}", "ok_unpatched": a.get("ok"),
            "ok_patched": b.get("ok"), "best_label": a.get("best_label"),
            "n_trades_test": a.get("n_trades_test"), "n_fields_compared": len(keys),
            "identical": not bad,
        })
        if bad:
            diffs.append({"case": f"{sname}/{stock}", "fields": bad,
                          "unpatched": {k: a.get(k) for k in bad},
                          "patched": {k: b.get(k) for k in bad}})
    force_unpatched(snap)
    return {"n_cases": len(rows), "cases": rows, "n_divergences": len(diffs),
            "divergences": diffs, "failures": failures,
            "all_identical": not diffs and all(r["identical"] for r in rows)}



# --------------------------------------------------------------------------- #
# Phase R8 -- non-vacuity audit
# --------------------------------------------------------------------------- #
def _task_trades(spec_name: str, stock: str) -> tuple[str, int, int, int]:
    """Default-config TRAIN backtest; returns (strategy, stock, n_trades, n_bars)."""
    if "specs" not in _G:
        _G["specs"] = {s.name: s for s in discover()}
        _G["snap"] = snapshot_bindings()
    spec = _G["specs"][spec_name]
    force_patched()
    try:
        res = run_single_stock(S.train_bars(stock), spec, spec.default, rebalance="M")
        return spec_name, stock, len(res.trades), res.n_bars
    except Exception as exc:  # noqa: BLE001
        return spec_name, stock, -1, str(exc)[:80]


def phase_non_vacuity(workers: int) -> dict:
    """How many of the R1/R2 comparisons actually exercised a non-empty book?

    A "0 divergences" result is worthless if the two arms both produced a flat equity
    curve because the strategy never fired. This counts trades per default-config TRAIN
    backtest so the headline number can be read with its denominator.
    """
    specs = discover()
    symbols = S.available_symbols("1d")
    tasks = [(s.name, st) for s in specs for st in symbols]
    from joblib import Parallel, delayed

    rows = Parallel(n_jobs=workers, batch_size=8, backend="loky", verbose=0)(
        delayed(_task_trades)(*t) for t in tasks)
    hist = collections.Counter()
    per_strategy: dict[str, int] = {}
    for spec_name, _stock, n_trades, _nb in rows:
        hist["err" if n_trades < 0 else ("0" if n_trades == 0 else
              "1-9" if n_trades < 10 else "10-49" if n_trades < 50 else "50+")] += 1
        if n_trades > 0:
            per_strategy[spec_name] = per_strategy.get(spec_name, 0) + 1
    dead = sorted(s.name for s in specs if s.name not in per_strategy)
    return {
        "n_pairs": len(rows),
        "trade_count_histogram": dict(hist),
        "n_pairs_with_trades": sum(v for k, v in hist.items() if k != "0" and k != "err"),
        "n_pairs_flat": hist.get("0", 0),
        "n_pairs_errored": hist.get("err", 0),
        "n_strategies_that_ever_trade": len(per_strategy),
        "n_strategies_never_trading_on_TRAIN": len(dead),
        "strategies_never_trading": dead,
    }


# --------------------------------------------------------------------------- #
# Phase R5 -- rebind completeness
# --------------------------------------------------------------------------- #
def phase_rebind() -> dict:
    """Production ordering: catalog imported first, then ``install()`` from ``ensure()``."""
    specs = discover()
    catalog_mods = sorted(s.module for s in specs)
    force_unpatched({})
    snap = snapshot_bindings()

    pristine: dict[str, dict[str, Any]] = {}
    for modname in catalog_mods:
        pristine[modname] = {a: v for a, v in vars(sys.modules[modname]).items()
                             if a in PATCHED_NAMES and callable(v)}

    installed = fastpath.install()
    rebound = fastpath._rebind_all()  # second call: must be a no-op

    wrappers = {n: getattr(I, n) for n in PATCHED_NAMES}
    orig_ids = {id(v) for modname in snap for v in snap[modname].values()}

    escaped: list[dict] = []
    wrapped_per: dict[str, list[str]] = {n: [] for n in PATCHED_NAMES}
    unpatched_per: dict[str, list[str]] = {n: [] for n in PATCHED_NAMES}
    for modname in catalog_mods:
        mod = sys.modules[modname]
        for attr, val in list(vars(mod).items()):
            if id(val) in orig_ids and not (attr in wrappers and val is wrappers[attr]):
                escaped.append({"module": modname, "attr": attr})
            if attr in PATCHED_NAMES and callable(val):
                (wrapped_per if val is wrappers[attr] else unpatched_per)[attr].append(modname)

    # Reachability audit: `_rebind_all` only walks a module's top-level __dict__, so an
    # original stashed in a class body / dict / list / tuple / set is invisible to it.
    nested: list[dict] = []
    for modname, mod in list(sys.modules.items()):
        for attr, val in list(vars(mod).items()):
            if isinstance(val, (list, tuple, set, frozenset, dict)):
                items = list(val.values()) if isinstance(val, dict) else list(val)
                if any(id(i) in orig_ids for i in items):
                    nested.append({"module": modname, "attr": attr,
                                   "container": type(val).__name__})
            if isinstance(val, type):
                for cattr, cval in list(vars(val).items()):
                    if id(cval) in orig_ids:
                        nested.append({"module": modname, "attr": attr,
                                       "class": val.__name__, "class_attr": cattr})
    seen_nested = {json.dumps(d, sort_keys=True) for d in nested}
    nested = [json.loads(s) for s in sorted(seen_nested)]

    result = {
        "n_catalog_modules": len(catalog_mods),
        "install_returned": installed,
        "rebind_all_second_call_returned": rebound,
        "modules_binding_each_indicator": {
            n: sorted(m for m, d in pristine.items() if n in d) for n in PATCHED_NAMES
        },
        "n_modules_with_each_indicator": {
            n: sum(1 for d in pristine.values() if n in d) for n in PATCHED_NAMES
        },
        "n_modules_bound_to_wrapper": {n: len(v) for n, v in wrapped_per.items()},
        "n_modules_bound_to_original": {n: len(v) for n, v in unpatched_per.items()},
        "modules_bound_to_original": {n: sorted(v) for n, v in unpatched_per.items()},
        "escaped_top_level": escaped,
        "n_escaped_top_level": len(escaped),
        "n_nested_references": len(nested),
        "nested_references": nested[:40],
    }

    # uninstall() completeness.
    fastpath.uninstall()
    survivors = []
    for modname in catalog_mods:
        for attr, val in list(vars(sys.modules[modname]).items()):
            if attr in PATCHED_NAMES and callable(val) and val is not ORIG_GET[attr]:
                survivors.append({"module": modname, "attr": attr,
                                  "still_wrapped": bool(getattr(val, "__wrapped__", None))})
    result["uninstall_restores_indicators_module"] = all(
        getattr(I, k) is ORIG_GET[k] for k in PATCHED_NAMES)
    result["n_modules_still_wrapped_after_uninstall"] = len(survivors)
    result["modules_still_wrapped_after_uninstall"] = survivors
    result["uninstall_is_complete"] = (result["uninstall_restores_indicators_module"]
                                       and not survivors)

    # The A/B harness that ships with the module: install -> uninstall -> install. Record
    # what a caller gets, because `run_single_stock` calls `ensure()` on every batch and
    # the shipped unit test relies on this ordering.
    force_unpatched(snap)
    first = fastpath.install()
    after_install = [n for n in PATCHED_NAMES
                     if getattr(sys.modules[catalog_mods[0]], n, None) is getattr(I, n)]
    fastpath.uninstall()
    after_uninstall_wrapped = sum(
        1 for m in catalog_mods for n in PATCHED_NAMES
        if getattr(sys.modules[m], n, None) is not None
        and getattr(sys.modules[m], n) is not ORIG_GET[n])
    second = fastpath.install()
    result["reinstall_after_uninstall"] = {
        "first_install_returned": first,
        "second_install_returned": second,
        "catalog_still_wrapped_after_uninstall": after_uninstall_wrapped,
        "indicators_module_wrapped_after_reinstall": all(
            hasattr(getattr(I, n), "__wrapped__") for n in PATCHED_NAMES),
        "n_bare_names_checked": len(after_install),
    }
    force_unpatched(snap)
    return result


# --------------------------------------------------------------------------- #
# Phase R6 -- determinism
# --------------------------------------------------------------------------- #
def det_digest() -> dict:
    """Digest of a fixed set of backtests under the production install path."""
    specs = {s.name: s for s in discover()}
    out = {}
    for sname, stock in DET_CASES:
        spec = specs[sname]
        for wname, bars in (("TRAIN", S.train_bars(stock)), ("TEST", S.test_bars(stock))):
            force_unpatched({})
            snap = snapshot_bindings()
            force_patched()
            res = run_single_stock(bars, spec, spec.default, rebalance="M")
            out[f"{sname}|{stock}|{wname}"] = fingerprint(res)["digest"]
            force_unpatched(snap)
    return out


def phase_determinism() -> dict:
    a, b = det_digest(), det_digest()
    script = [sys.executable, str(REPO / "research" / "validate_fastpath.py"),
              "--phase", "det-digest"]
    env = dict(os.environ, PYTHONPATH=str(REPO))
    p1 = json.loads(subprocess.run(script, capture_output=True, text=True, env=env,
                                  cwd=str(REPO), check=True).stdout)
    p2 = json.loads(subprocess.run(script, capture_output=True, text=True, env=env,
                                  cwd=str(REPO), check=True).stdout)
    return {
        "cases": [f"{x}|{y}" for x, y in DET_CASES],
        "same_process_identical": a == b,
        "cross_process_identical": p1 == p2,
        "cross_process_matches_in_process": p1 == a,
        "digests": a, "subprocess_1": p1, "subprocess_2": p2,
    }


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Exhaustive fast-path validation")
    ap.add_argument("--phase", default="all",
                    choices=["all", "R1", "R2", "R3", "R4", "R5", "R6", "R7", "R8",
                             "det-digest"])
    ap.add_argument("--random-configs", type=int, default=5)
    ap.add_argument("--workers", type=int, default=max(1, os.cpu_count() or 2))
    ap.add_argument("--smoke", action="store_true",
                    help="2 strategies x 2 symbols only, to prove the worker path")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s | %(message)s")

    if args.phase == "det-digest":
        print(json.dumps(det_digest(), sort_keys=True))
        return 0

    symbols = S.available_symbols("1d")
    forced_subset = symbols[:4] + symbols[-4:]

    bundle: dict[str, Any] = (json.loads(RESULTS_PATH.read_text())
                              if RESULTS_PATH.exists() else {})

    def save() -> None:
        RESULTS_PATH.write_text(json.dumps(bundle, indent=2, default=str))

    if args.phase in ("all", "R1", "R2"):
        bundle["R1_R2"] = phase_catalog(args.random_configs, args.workers, forced_subset,
                                       smoke=args.smoke)
        save()
        r = bundle["R1_R2"]
        print(f"[R1/R2] {r['total_compared']} comparisons, "
              f"{r['total_divergences']} divergences, {r['total_errors']} errors, "
              f"{r['elapsed_s']}s", flush=True)

    for key, fn in (("R3", phase_edge_lengths), ("R4", phase_containers),
                    ("R5", phase_rebind), ("R6", phase_determinism),
                    ("R7", phase_production_path)):
        if args.phase in ("all", "R8"):
            bundle["R8"] = phase_non_vacuity(args.workers)
            save()
            print(f"[R8] {json.dumps(bundle['R8']['trade_count_histogram'])}",
                  flush=True)
        if args.phase in ("all", key):
            bundle[key] = fn()
            save()
            print(f"[{key}] {json.dumps({k: v for k, v in bundle[key].items()
                                         if not isinstance(v, (list, dict))})}", flush=True)
    save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
