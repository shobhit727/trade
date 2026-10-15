"""Parallel, resumable, crash-safe driver for the per-stock sweep.

Design constraints, each of which came from a specific failure:

* **Resumable.** A 4,200-pair sweep will be interrupted. Every completed pair is appended
  to a JSONL file and skipped on re-run. Checkpoint is the file itself -- there is no
  separate state to corrupt.
* **Crash-safe.** One strategy that throws must not kill the sweep. Failures are recorded
  as rows with ``ok=False`` and the reason, so a broken module is visible rather than
  silently shrinking the result set. (An earlier agent lost a verdict to a harness that
  silently returned a flat book.)
* **Cheap first, expensive last.** Only the frozen best config is evaluated on TEST. TEST
  is opened exactly once per pair.
* **Parallel across pairs, not within.** Pairs are independent; a pair's internal search is
  serial. That keeps memory flat and makes the resume key trivially a pair id.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import traceback
from pathlib import Path

import numpy as np

from . import config as C
from . import metrics as M
from . import nulls as N
from . import splitter as S
from .backtest import BacktestError, run_single_stock
from .catalog import StrategySpec

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# JSONL helpers
# --------------------------------------------------------------------------- #
def _append(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, default=_json_default) + "\n")


def _json_default(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if hasattr(o, "to_dict"):
        return o.to_dict()
    if hasattr(o, "__dict__"):
        return {k: v for k, v in vars(o).items() if not k.startswith("_")}
    return str(o)


def repair_jsonl(path: Path) -> int:
    """Drop a trailing partial line left by a hard kill. Returns bytes discarded.

    Without this, the next append *fuses* onto the truncated line, producing one
    unparseable line -- which silently destroyed an already-completed pair. Reproduced:
    a good row followed by `{"strategy":"zzz",...,"stage":"te`; after appending,
    ``load_rows`` returned 1 of 2 completed pairs and that pair re-ran forever.
    """
    if not path.exists() or path.stat().st_size == 0:
        return 0
    with path.open("rb") as fh:
        fh.seek(-1, 2)
        if fh.read(1) == b"\n":
            return 0
    data = path.read_bytes()
    cut = data.rfind(b"\n")
    if cut == -1:
        path.write_bytes(b"")
        return len(data)
    path.write_bytes(data[: cut + 1])
    return len(data) - (cut + 1)


def _read_jsonl(path: Path) -> set[tuple[str, str]]:
    """Pair ids already present in a results file."""
    done: set[tuple[str, str]] = set()
    if not path.exists():
        return done
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue  # truncated final line from a hard kill
            if row.get("stage") == "test" and row.get("ok"):
                done.add((row.get("strategy", ""), row.get("stock", "")))
    return done


# --------------------------------------------------------------------------- #
# One pair
# --------------------------------------------------------------------------- #
def pair_seed(strategy: str, stock: str, master: int) -> int:
    """Deterministic per-pair seed so any pair is reproducible in isolation.

    Derived by hashing rather than by Python's ``hash()``, which is salted per process
    unless ``PYTHONHASHSEED`` is pinned -- a resume would then replay a different search
    than the one it was resuming.
    """
    digest = hashlib.blake2b(f"{master}|{strategy}|{stock}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big")


def optimise_pair(
    spec: StrategySpec,
    stock: str,
    cfg: C.RunConfig,
    *,
    timeframe: str = "1d",
) -> tuple[dict, dict | None]:
    """Search Config space on TRAIN, then evaluate the frozen winner on TEST once.

    Returns ``(test_row, train_summary)``. ``test_row`` is written even on failure so the
    failure is auditable.
    """
    fees = cfg.fees()
    seed = pair_seed(spec.name, stock, cfg.seed)
    rng = np.random.default_rng(seed)

    tr = S.train_bars(stock, timeframe)
    te = S.test_bars(stock, timeframe)

    base = {
        "strategy": spec.name,
        "stock": stock,
        "stage": "test",
        "seed": seed,
        "capital": float(C.CAPITAL_INR),
        "tax_enabled": cfg.tax_enabled,
        "rebalance": cfg.rebalance,
        "budget": cfg.budget,
    }

    if tr.empty:
        return {**base, "ok": False, "error": "empty TRAIN slice"}, None
    if te.empty:
        return {**base, "ok": False, "error": "empty TEST slice"}, None

    # ---- search on TRAIN only -------------------------------------------------
    candidates: list[tuple[str, dict]] = [("default", dict(spec.default))]
    seen = {json.dumps(spec.default, sort_keys=True, default=str)}
    # Bail out rather than spin forever: a spec whose space is a single bool or a
    # 2-valued Literal can never reach `budget` distinct draws.
    max_draws = cfg.budget * 50
    draws = 0
    while len(candidates) < cfg.budget and draws < max_draws:
        draws += 1
        p = spec.sample(rng)
        k = json.dumps(p, sort_keys=True, default=str)
        if k in seen:
            continue
        seen.add(k)
        candidates.append((f"random_{len(candidates) - 1}", p))

    train_rows, failures = [], {}
    for label, params in candidates:
        try:
            res = run_single_stock(
                tr, spec, params, fees=fees, rebalance=cfg.rebalance,
                tax_enabled=cfg.tax_enabled, allow_short=C.ALLOW_SHORT,
            )
            m = M.compute(res.equity, exposure=res.exposure, turnover=res.turnover,
                          total_fees=res.total_fees, total_tax=res.total_tax,
                          n_trades=len(res.trades))
        except BacktestError as exc:
            failures[label] = str(exc)[:200]
            continue
        except Exception as exc:  # noqa: BLE001 - a bad module must not kill the sweep
            failures[label] = f"{type(exc).__name__}: {exc}"[:200]
            continue
        train_rows.append({"label": label, "params": params, "metrics": m.to_dict()})

    if not train_rows:
        # Keep the per-candidate reasons, both in a side field and inline. This row
        # exists precisely so a broken strategy is auditable; returning only a count
        # threw the diagnosis away and forced a re-run just to learn why.
        sample = "; ".join(f"{k}: {v}" for k, v in list(failures.items())[:3])[:400]
        return {**base, "ok": False,
                "error": (f"no candidate backtested ({len(failures)} failures) "
                          f"[{sample}]"),
                "failures": failures,
                "params": None}, None

    # Selection objective: Sharpe, then Calmar as a tiebreak. Chosen a priori.
    best = max(train_rows, key=lambda r: (r["metrics"]["sharpe"], r["metrics"]["calmar"]))
    best_label = best["label"]

    # ---- nulls, on TRAIN, computed against the same window --------------------
    train_cagr_null = np.array([r["metrics"]["cagr"] for r in train_rows], dtype=float)
    timing_null = N.timing_null_cagr(
        tr, best["metrics"]["exposure"], seed + 1, cfg.null_replicas,
        start=S.TRAIN.start, end=S.TRAIN.end,
    )

    # ---- TEST, opened exactly once -------------------------------------------
    try:
        res = run_single_stock(
            te, spec, best["params"], fees=fees, rebalance=cfg.rebalance,
            tax_enabled=cfg.tax_enabled, allow_short=C.ALLOW_SHORT,
        )
        tm = M.compute(res.equity, exposure=res.exposure, turnover=res.turnover,
                       total_fees=res.total_fees, total_tax=res.total_tax,
                       n_trades=len(res.trades))
        yearly = M.per_year(res.equity)
        max_year_share = M.max_single_year_share(res.equity)
    except BacktestError as exc:
        return {**base, "ok": False, "error": f"TEST: {exc}",
                "train_best": best_label}, None
    except Exception as exc:  # noqa: BLE001
        return {**base, "ok": False,
                "error": f"TEST {type(exc).__name__}: {exc}"[:200],
                "train_best": best_label}, None

    bh_cagr = N.buy_and_hold_cagr(te)
    timing_null_test = N.timing_null_cagr(
        te, tm.exposure, seed + 2, cfg.null_replicas,
        start=S.TEST.start, end=S.TEST.end,
    )

    row = {
        **base,
        "ok": True,
        "best_label": best_label,
        "params": best["params"],
        "n_candidates": len(train_rows),
        "n_failed_candidates": len(failures),
        "failures": failures,
        "train": best["metrics"],
        "test": tm.to_dict(),
        "test_yearly": yearly,
        "test_max_year_share": max_year_share,
        "test_buy_hold_cagr": bh_cagr,
        "alpha_vs_buy_hold": tm.cagr - bh_cagr,
        # Null comparisons. p_params asks "did the SEARCH beat random configs on TRAIN";
        # p_timing asks "did the TIMING beat random timing at matched exposure on TEST".
        "p_params": N.p_value(best["metrics"]["cagr"], train_cagr_null),
        "p_timing": N.p_value(tm.cagr, timing_null_test),
        "timing_null_median": float(np.median(timing_null_test)) if timing_null_test.size else 0.0,
        "timing_null_p90": float(np.percentile(timing_null_test, 90)) if timing_null_test.size else 0.0,
        "n_trades_test": len(res.trades),
        "total_tax_test": res.total_tax,
        "total_fees_test": res.total_fees,
        "engine": ENGINE_STAMP,
    }
    summary = {
        "strategy": spec.name, "stock": stock, "stage": "train",
        "n_candidates": len(train_rows), "n_failed": len(failures),
        "best_label": best_label, "best_train": best["metrics"],
        "default_train": next((r["metrics"] for r in train_rows if r["label"] == "default"), None),
        "timing_null_median_train": float(np.median(timing_null)) if timing_null.size else 0.0,
    }
    return row, summary


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def engine_stamp() -> str:
    """Fingerprint of the files that decide a result, so a run is attributable."""
    parts = []
    for name in ("config.py", "catalog.py", "backtest.py", "metrics.py", "nulls.py", "splitter.py"):
        p = Path(__file__).with_name(name)
        parts.append(hashlib.blake2b(p.read_bytes(), digest_size=8).hexdigest())
    try:
        from nsealgo.provenance import provenance

        parts.append(json.dumps(provenance(), sort_keys=True))
    except Exception:  # noqa: BLE001
        parts.append("nsealgo-provenance-unavailable")
    return hashlib.blake2b("|".join(parts).encode(), digest_size=8).hexdigest()[:12]


ENGINE_STAMP = engine_stamp()


def run_sweep(specs: list[StrategySpec], stocks: list[str], cfg: C.RunConfig,
              *, resume: bool = True, workers: int | None = None,
              timeframe: str = "1d") -> dict:
    """Run every (strategy, stock) pair. Returns a run manifest."""
    C.ensure_dirs()
    workers = workers or cfg.workers

    repair_jsonl(C.TEST_JSONL)
    repair_jsonl(C.RESULTS_JSONL)
    done: set[tuple[str, str]] = _read_jsonl(C.TEST_JSONL) if resume else set()
    if not resume:
        # Both files: leaving a stale results.jsonl behind while replacing
        # test_results.jsonl makes the two disagree.
        for stale in (C.TEST_JSONL, C.RESULTS_JSONL):
            if stale.exists():
                stale.unlink()

    tasks = [(sp, st) for sp in specs for st in stocks if (sp.name, st) not in done]
    total = len(specs) * len(stocks)
    log.info("sweep: %d pairs (%d already done), %d workers, budget=%d",
             len(tasks), len(done), workers, cfg.budget)

    manifest = {
        "engine": ENGINE_STAMP,
        "capital": float(C.CAPITAL_INR),
        "cost_bps": float(C.ALL_IN_ROUND_TRIP_BPS),
        "tax_enabled": cfg.tax_enabled,
        "stcg": float(C.STCG_RATE),
        "ltcg": float(C.LTCG_RATE),
        "rebalance": cfg.rebalance,
        "budget": cfg.budget,
        "null_replicas": cfg.null_replicas,
        "seed": cfg.seed,
        "workers": workers,
        "n_strategies": len(specs),
        "n_stocks": len(stocks),
        "n_pairs_total": total,
        "n_pairs_skipped": len(done),
        "train": [S.TRAIN.start, S.TRAIN.end],
        "test": [S.TEST.start, S.TEST.end],
    }
    C.MANIFEST_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    t0 = time.time()
    ok = fail = 0

    def _work(task, test_path: str = "", train_path: str = ""):
        sp, st = task
        # loky re-imports config in the child, so module-level C.TEST_JSONL resolves to
        # the *default* path and ignores any caller override -- silently appending rows
        # to the real 4,032-pair artefact during a scratch run. Paths are passed
        # explicitly so the child cannot get them wrong.
        tp, rp = Path(test_path or C.TEST_JSONL), Path(train_path or C.RESULTS_JSONL)
        try:
            row, summ = optimise_pair(sp, st, cfg, timeframe=timeframe)
        except Exception as exc:  # noqa: BLE001 - never let one pair kill the run
            row = {"strategy": sp.name, "stock": st, "stage": "test", "ok": False,
                   "error": f"UNCAUGHT {type(exc).__name__}: {exc}"[:300],
                   "traceback": traceback.format_exc()[-800:]}
            summ = None
        _append(tp, row)
        if summ is not None:
            _append(rp, summ)
        return row.get("ok", False), row.get("error")

    if workers <= 1:
        for i, task in enumerate(tasks, 1):
            o, _ = _work(task)
            ok += o
            fail += not o
            if i % 25 == 0 or i == len(tasks):
                _progress(i, len(tasks), t0, ok, fail)
    else:
        from joblib import Parallel, delayed

        results = Parallel(n_jobs=workers, batch_size=1, backend="loky", verbose=0)(
            delayed(_work)(t, str(C.TEST_JSONL), str(C.RESULTS_JSONL)) for t in tasks
        )
        ok = sum(1 for o, _ in results if o)
        fail = len(results) - ok
        _progress(len(tasks), len(tasks), t0, ok, fail)

    # Skips that belong to THIS sweep's scope. `done` is read from the whole results
    # file, so a 1-pair rerun of a 2-row file previously reported n_pairs_skipped: 2
    # alongside n_pairs_total: 1 -- the manifest overstated its own work.
    scope = {(sp.name, st) for sp in specs for st in stocks}
    manifest.update({"n_pairs_run": len(tasks), "n_ok": ok, "n_failed": fail,
                     "n_pairs_skipped_in_scope": len(done & scope),
                     "n_pairs_skipped_other_scope": len(done - scope),
                     "elapsed_s": round(time.time() - t0, 1)})
    C.MANIFEST_JSON.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log.info("sweep complete: %d ok, %d failed in %.1fs", ok, fail, time.time() - t0)
    return manifest


def _progress(i: int, n: int, t0: float, ok: int, fail: int) -> None:
    el = time.time() - t0
    rate = i / el if el > 0 else 0.0
    eta = (n - i) / rate if rate > 0 else float("nan")
    msg = (f"[{i}/{n}] ok={ok} fail={fail} {i / max(el, 1e-9):.2f} pair/s "
           f"elapsed={el / 60:.1f}m eta={eta / 60:.1f}m")
    log.info(msg)
    print(msg, flush=True)


def set_thread_env(n: int = 1) -> None:
    """Stop BLAS from oversubscribing when we fan out with joblib."""
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
              "NUMEXPR_NUM_THREADS"):
        os.environ.setdefault(v, str(n))
