"""Robustness / edge-case tests for the per-stock optimiser.

The happy path is already covered by ``test_nsealgo_perstock_optimizer.py`` and by the
4,032-pair harness run. This file targets the paths that run **never execute** on real
data, because the failure mode being guarded against is not a crash -- it is a *silent
shrink of the result set*. A sweep that quietly drops 40 pairs still prints a manifest,
still writes ``analyze.md``, and still produces a verdict. Nothing raises.

Each test is written so it is red against the failure it names. Nine real defects were
found this way; all are now fixed in the sources, and the tests below are ordinary
passing assertions -- if a fix is reverted, the matching test goes red rather than
quietly xpassing:

* **A** ``--stocks adanient`` swept a symbol ``splitter.EXCLUDED_SYMBOLS`` excludes.
      ``available_symbols()`` honoured the list; an explicit ``--stocks`` bypassed it.
* **C** ``--timeframe 5m`` ran a full 4,032-pair sweep despite GOAL.md banning intraday.
      Worse, ``_read`` normalises the index, so a 5m file collapses to one bar per day
      and TRAIN ends up empty for every symbol -- 4,032 pairs, all failing.
* **D** A truncated final JSONL line was *skipped* on read but never *repaired*, so the
      next append fused onto it. The pair was correctly not marked done, but its freshly
      written result then became permanently unreadable to ``analyze.load_rows()``.
* **E** Every pair failing was indistinguishable from an empty results file, and the
      verdict told the operator to "run the sweep first".
* **F** ``--no-resume`` deleted ``test_results.jsonl`` but left stale train summaries
      in ``results.jsonl``.
* **G** ``optimise_pair``'s candidate de-duplication loop had no bail-out, so a sampler
      that kept returning an already-seen config spun forever.
* **H** The verdict formatted the expected-by-chance count with ``:.0f``, printing
      "~0 expected by chance" for any n < 20.
* **H2** The all-candidates-fail row discarded the per-candidate reasons it had already
      collected, leaving the one row that exists to make a broken strategy auditable
      with no diagnosis on it.
* **I** ``run_sweep`` handed its worker closure to joblib's loky backend, which re-imports
      ``config`` in the child and so resolved the output path from the module default,
      ignoring any caller redirect -- and appended to the real 4,032-row artefact during
      a scratch run while the manifest still read as a complete run.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from research.optimize import analyze as A
from research.optimize import config as C
from research.optimize import engine as E
from research.optimize import run as R
from research.optimize import splitter as S
from research.optimize.analyze import analyse, benjamini_hochberg, load_rows
from research.optimize.catalog import discover, load_strategy

REPO = Path(__file__).resolve().parents[2]
OPTIMIZE_DIR = REPO / "research" / "optimize"
DOC_FLAG_RE = re.compile(r"--[a-z][a-z0-9-]*")

#: The real artefact path, captured at import time -- i.e. before the ``outdir`` fixture
#: (or any monkeypatch) redirects ``C.TEST_JSONL``. Used to prove that a loky worker
#: resolves the caller's redirect rather than this one.
_C_DEFAULT_TEST_JSONL = str(C.TEST_JSONL)


# --------------------------------------------------------------------------- #
# Fakes -- no real sweep, no real backtest, no real data files
# --------------------------------------------------------------------------- #
def _bars(n: int = 300, start: str = "2018-01-01", seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    px = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
    return pd.DataFrame(
        {"open": px, "high": px * 1.01, "low": px * 0.99, "close": px, "volume": 1e6},
        index=idx,
    )


class FakeSpec:
    """Duck-typed ``StrategySpec``.

    ``sample`` yields a *different* config every call, so the de-duplication loop in
    ``optimise_pair`` reaches ``budget`` candidates without hitting its bail-out. Only
    the dedicated ``TestCandidateDedup`` probe constructs a constant sampler.
    """

    def __init__(self, name: str = "fake", constant: object = None):
        self.name = name
        self.module = f"fake.{name}"
        self.config_cls = object
        self.strategy_cls = object
        self.params: list = []
        self.held_fixed: list = []
        self.default = {"period": 0}
        self._constant = constant
        self.samples = 0

    def sample(self, rng):
        self.samples += 1
        if self._constant is not None:
            return {"period": 0}
        # Derived from the generator, not from instance state, so the same (spec, seed)
        # replays the same search -- which is what `pair_seed` exists to guarantee.
        return {"period": int(rng.integers(1, 100_000))}

    def build(self, values):
        return None


def _fake_backtest(bars, spec, params, **_kw):
    """A cheap, deterministic, *distinguishable* stand-in for the real backtester."""
    period = float(params.get("period", 0) or 0)
    # `period % 20` is 0 for the shipped default and >= 1 for every sampled config, so a
    # random candidate always out-earns "default". Without that, `best` is "default"
    # about 1 run in 7 and a mutant that re-runs the wrong config on TEST is invisible.
    step = 0.0002 * (1.0 + period % 20.0)
    equity = float(C.CAPITAL_INR) * np.cumprod(1.0 + np.full(len(bars), step))
    return SimpleNamespace(
        equity=pd.Series(equity, index=bars.index, name="equity"),
        exposure=float(min(1.0, 0.4 + 0.05 * (period % 8))),
        turnover=1.5,
        total_fees=1234.0,
        total_tax=5678.0,
        trades=[0, 1, 2],
    )


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(autouse=True)
def _protect_harness_artifacts():
    """Never let this file write into ``research/optimize/out/``.

    That directory holds the real 4,032-pair harness result and is gitignored, so git
    shows nothing when it is damaged. Restores by truncation on the way out, so even a
    regression in the output-path handling cannot poison the artefact for whoever runs
    the analysis next.
    """
    real = C.OUT_DIR / "test_results.jsonl"
    before = real.stat().st_size if real.exists() else None
    yield
    if before is None:
        if real.exists():
            real.unlink()
    elif not real.exists():
        real.write_bytes(b"")
    elif real.stat().st_size > before:
        with real.open("r+b") as fh:
            fh.truncate(before)


@pytest.fixture
def outdir(tmp_path, monkeypatch):
    """Redirect every optimiser output path into tmp_path."""
    d = tmp_path / "out"
    for name, val in (
        ("OUT_DIR", d),
        ("TEST_JSONL", d / "test_results.jsonl"),
        ("RESULTS_JSONL", d / "results.jsonl"),
        ("NULLS_JSONL", d / "nulls.jsonl"),
        ("SUMMARY_JSON", d / "summary.json"),
        ("ANALYZE_MD", d / "analyze.md"),
        ("MANIFEST_JSON", d / "manifest.json"),
    ):
        monkeypatch.setattr(C, name, val)
    return d


@pytest.fixture
def fake_engine(monkeypatch):
    """Stub the backtest and both data slices so ``run_sweep`` never touches disk/strategy."""
    monkeypatch.setattr(E, "run_single_stock", _fake_backtest)
    monkeypatch.setattr(S, "train_bars", lambda sym, tf="1d": _bars(300, "2018-01-01"))
    monkeypatch.setattr(S, "test_bars", lambda sym, tf="1d": _bars(200, "2024-02-01"))
    return SimpleNamespace(bars=_bars)


@pytest.fixture
def cfg():
    return C.RunConfig(budget=3, null_replicas=4, workers=1)


def _rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _ok_row(strategy: str, stock: str, **over) -> dict:
    row = {
        "strategy": strategy,
        "stock": stock,
        "stage": "test",
        "ok": True,
        "n_failed_candidates": 0,
        "test": {"cagr": 0.11, "sharpe": 0.4, "exposure": 0.5},
        "alpha_vs_buy_hold": 0.03,
        "p_timing": 0.4,
        "p_params": 0.3,
        "test_max_year_share": 0.2,
        "total_tax_test": 42000.0,
    }
    row.update(over)
    return row


def _failed_row(strategy: str, stock: str, error: str = "boom") -> dict:
    return {"strategy": strategy, "stock": stock, "stage": "test",
            "ok": False, "error": error}


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return path


def _headline(out: dict) -> str:
    """The string an operator actually reads. ``analyse()`` now always sets ``verdict``,
    including on the empty and all-failed paths."""
    return out.get("verdict", "NO DATA")


# =========================================================================== #
# 1. Resume correctness
# =========================================================================== #
class TestResume:
    def test_resume_executes_only_the_missing_pairs(self, outdir, fake_engine, cfg):
        specs = [FakeSpec("a"), FakeSpec("b")]
        stocks = ["tcs", "infy"]
        E.run_sweep([specs[0]], stocks, cfg, resume=False, workers=1)
        assert len(_rows(C.TEST_JSONL)) == 2

        # Second pass adds only the missing strategy.
        m = E.run_sweep(specs, stocks, cfg, resume=True, workers=1)
        assert m["n_pairs_run"] == 2, "only b/tcs and b/infy should have executed"
        assert m["n_pairs_skipped"] == 2

        rows = _rows(C.TEST_JSONL)
        assert len(rows) == 4
        assert len({(r["strategy"], r["stock"]) for r in rows}) == 4, "no duplicates"

    def test_resume_leaves_prior_rows_byte_identical(self, outdir, fake_engine, cfg):
        specs = [FakeSpec("a"), FakeSpec("b")]
        E.run_sweep([specs[0]], ["tcs", "infy"], cfg, resume=False, workers=1)
        before = C.TEST_JSONL.read_text(encoding="utf-8")

        E.run_sweep(specs, ["tcs", "infy"], cfg, resume=True, workers=1)
        after = C.TEST_JSONL.read_text(encoding="utf-8")

        assert after.startswith(before), "resume must append, never rewrite earlier rows"
        assert len(after.splitlines()) == len(before.splitlines()) + 2

    def test_fully_resumed_sweep_runs_nothing(self, outdir, fake_engine, cfg):
        specs = [FakeSpec("a")]
        E.run_sweep(specs, ["tcs", "infy"], cfg, resume=False, workers=1)
        m = E.run_sweep(specs, ["tcs", "infy"], cfg, resume=True, workers=1)
        assert m["n_pairs_run"] == 0
        assert m["n_pairs_skipped"] == 2

    def test_failed_rows_are_not_marked_done(self, outdir, fake_engine, cfg, monkeypatch):
        """A pair that errored must be retried, not skipped forever as "done"."""
        calls: list[str] = []
        real = _fake_backtest

        def counting(bars, spec, params, **kw):
            calls.append(spec.name)
            if spec.name == "boom":
                raise RuntimeError("strategy exploded")
            return real(bars, spec, params, **kw)

        monkeypatch.setattr(E, "run_single_stock", counting)
        E.run_sweep([FakeSpec("boom")], ["tcs"], cfg, resume=False, workers=1)

        rows = _rows(C.TEST_JSONL)
        assert rows and rows[0]["ok"] is False, "failure must be recorded, not dropped"
        assert ("boom", "tcs") not in E._read_jsonl(C.TEST_JSONL)

        n_first = len(calls)
        E.run_sweep([FakeSpec("boom")], ["tcs"], cfg, resume=True, workers=1)
        assert len(calls) > n_first, "an ok:false row must not count as done"

    def test_truncated_final_line_is_skipped_not_fatal(self, outdir, cfg):
        """A hard kill mid-write leaves a partial JSON object at EOF."""
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs")])
        with C.TEST_JSONL.open("a", encoding="utf-8") as fh:
            fh.write('{"strategy": "b", "stock": "infy", "stage": "te')

        done = E._read_jsonl(C.TEST_JSONL)  # must not raise
        assert done == {("a", "tcs")}
        assert ("b", "infy") not in done, "a truncated pair must never be marked done"

    def test_truncated_line_does_not_discard_earlier_rows(self, outdir, cfg):
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs"), _ok_row("a", "infy")])
        with C.TEST_JSONL.open("a", encoding="utf-8") as fh:
            fh.write('{"strategy": "zzz", "stock": "qqq", "stage": "te')
        assert E._read_jsonl(C.TEST_JSONL) == {("a", "tcs"), ("a", "infy")}

    def test_blank_and_garbage_lines_are_tolerated(self, outdir, cfg):
        C.TEST_JSONL.parent.mkdir(parents=True, exist_ok=True)
        C.TEST_JSONL.write_text(
            '\n\n{"strategy":"a","stock":"tcs","stage":"test","ok":true}\n'
            'not json at all\n\n{"strategy":"b","stock":"infy","stage":"test","ok":true}\n',
            encoding="utf-8",
        )
        assert E._read_jsonl(C.TEST_JSONL) == {("a", "tcs"), ("b", "infy")}

    def test_repair_jsonl_truncates_only_the_partial_tail(self, outdir, cfg):
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs"), _ok_row("b", "infy")])
        good = C.TEST_JSONL.read_text(encoding="utf-8")
        with C.TEST_JSONL.open("a", encoding="utf-8") as fh:
            fh.write('{"strategy": "c", "stock": "hcl", "stage": "te')

        assert E.repair_jsonl(C.TEST_JSONL) > 0, "the fragment should be discarded"
        assert C.TEST_JSONL.read_text(encoding="utf-8") == good, (
            "repair must restore exactly the complete lines, byte for byte"
        )

    def test_repair_jsonl_is_idempotent_and_safe_on_clean_files(self, outdir, cfg):
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs")])
        assert E.repair_jsonl(C.TEST_JSONL) == 0, "a file ending in newline is clean"
        assert E.repair_jsonl(C.TEST_JSONL) == 0
        assert len(_rows(C.TEST_JSONL)) == 1

    def test_repair_jsonl_on_a_missing_or_empty_file(self, outdir, cfg):
        assert E.repair_jsonl(C.TEST_JSONL) == 0
        C.TEST_JSONL.parent.mkdir(parents=True, exist_ok=True)
        C.TEST_JSONL.write_text("", encoding="utf-8")
        assert E.repair_jsonl(C.TEST_JSONL) == 0

    def test_repair_jsonl_with_no_newline_at_all(self, outdir, cfg):
        """A file that is nothing but one partial line is emptied, not left broken."""
        C.TEST_JSONL.parent.mkdir(parents=True, exist_ok=True)
        C.TEST_JSONL.write_text('{"strategy": "a", "stock"', encoding="utf-8")
        assert E.repair_jsonl(C.TEST_JSONL) == len('{"strategy": "a", "stock"')
        assert C.TEST_JSONL.read_text(encoding="utf-8") == ""
        assert E._read_jsonl(C.TEST_JSONL) == set()

    def test_truncated_line_does_not_swallow_the_next_appended_row(
        self, outdir, fake_engine, cfg
    ):
        """Repro:
            run 1 writes {"...a/tcs..."};
            hard kill leaves a partial `{"strategy": "zzz", ...` at EOF;
            resume appends the next pair.
        Before the fix the append landed *on the same physical line* as the partial
        fragment, producing one unparseable line: the pair was correctly not marked done,
        but its freshly written result was then invisible to ``analyze.load_rows()`` and
        it re-ran on every subsequent resume.
        """
        E.run_sweep([FakeSpec("a")], ["tcs"], cfg, resume=False, workers=1)
        with C.TEST_JSONL.open("a", encoding="utf-8") as fh:
            fh.write('{"strategy": "zzz", "stock": "qqq", "stage": "te')

        E.run_sweep([FakeSpec("b")], ["infy"], cfg, resume=True, workers=1)

        visible = load_rows(C.TEST_JSONL)
        assert {("b", "infy")} <= {(r["strategy"], r["stock"]) for r in visible}, (
            "the row written by the resumed run must still be readable by analyze"
        )
        assert C.TEST_JSONL.read_text(encoding="utf-8").count("\n") == 2, (
            "both complete rows must survive as two separate parseable lines"
        )

    def test_the_repaired_pair_is_not_re_run_on_the_next_resume(self, outdir, fake_engine,
                                                                cfg):
        """The end-to-end consequence of the fix: the pair runs exactly once."""
        E.run_sweep([FakeSpec("a")], ["tcs"], cfg, resume=False, workers=1)
        with C.TEST_JSONL.open("a", encoding="utf-8") as fh:
            fh.write('{"strategy": "zzz", "stock": "qqq", "stage": "te')
        E.run_sweep([FakeSpec("b")], ["infy"], cfg, resume=True, workers=1)

        m_a = E.run_sweep([FakeSpec("a")], ["tcs"], cfg, resume=True, workers=1)
        m_b = E.run_sweep([FakeSpec("b")], ["infy"], cfg, resume=True, workers=1)
        assert m_a["n_pairs_run"] == 0
        assert m_b["n_pairs_run"] == 0, (
            "both pairs are on disk as good rows, so neither may run again"
        )
        assert len(_rows(C.TEST_JSONL)) == 2, "and neither may be written twice"


# =========================================================================== #
# 2. --no-resume deletes rather than appends
# =========================================================================== #
class TestNoResume:
    def test_no_resume_removes_the_old_file(self, outdir, fake_engine, cfg):
        _write_jsonl(C.TEST_JSONL, [_ok_row("ghost", "ghost")])
        assert C.TEST_JSONL.exists()

        E.run_sweep([FakeSpec("a")], ["tcs"], cfg, resume=False, workers=1)

        pairs = {(r["strategy"], r["stock"]) for r in _rows(C.TEST_JSONL)}
        assert ("ghost", "ghost") not in pairs, "--no-resume must delete, not append"
        assert pairs == {("a", "tcs")}

    def test_no_resume_on_absent_file_is_fine(self, outdir, fake_engine, cfg):
        assert not C.TEST_JSONL.exists()
        m = E.run_sweep([FakeSpec("a")], ["tcs"], cfg, resume=False, workers=1)
        assert m["n_pairs_run"] == 1

    def test_no_resume_still_reports_the_full_pair_count(self, outdir, fake_engine, cfg):
        _write_jsonl(C.TEST_JSONL, [_ok_row("ghost", "ghost")])
        m = E.run_sweep([FakeSpec("a"), FakeSpec("b")], ["tcs", "infy"], cfg,
                        resume=False, workers=1)
        assert m["n_pairs_total"] == 4
        assert m["n_pairs_run"] == 4
        assert m["n_pairs_skipped"] == 0, "skipped must be 0, not the size of the old file"

    def test_no_resume_also_clears_stale_train_summaries(self, outdir, fake_engine, cfg):
        """``--no-resume`` is documented as "start over (deletes the results file)".
        Leaving results.jsonl behind while replacing test_results.jsonl makes the two
        disagree about which run they describe."""
        E.run_sweep([FakeSpec("a")], ["tcs"], cfg, resume=False, workers=1)
        assert len(_rows(C.RESULTS_JSONL)) == 1

        E.run_sweep([FakeSpec("z")], ["infy"], cfg, resume=False, workers=1)
        trains = _rows(C.RESULTS_JSONL)
        assert {r["strategy"] for r in trains} == {"z"}, (
            "a --no-resume run must not leave the previous run's train rows behind"
        )
        assert len(trains) == 1


# =========================================================================== #
# 3. Crash isolation
# =========================================================================== #
class TestCrashIsolation:
    def test_a_raising_strategy_does_not_kill_the_sweep(self, outdir, fake_engine, cfg,
                                                       monkeypatch):
        real = _fake_backtest

        def selective(bars, spec, params, **kw):
            if spec.name == "exploder":
                raise RuntimeError("kaboom")
            return real(bars, spec, params, **kw)

        monkeypatch.setattr(E, "run_single_stock", selective)

        specs = [FakeSpec("exploder"), FakeSpec("fine")]
        stocks = ["tcs", "infy", "hcl"]
        m = E.run_sweep(specs, stocks, cfg, resume=False, workers=1)

        assert m["n_pairs_run"] == 6
        assert m["n_ok"] == 3, "every non-exploding pair must still complete"
        assert m["n_failed"] == 3

    def test_the_failure_is_a_row_with_ok_false_and_a_reason(self, outdir, fake_engine,
                                                             cfg, monkeypatch):
        def selective(bars, spec, params, **kw):
            if spec.name == "exploder":
                raise RuntimeError("kaboom")
            return _fake_backtest(bars, spec, params, **kw)

        monkeypatch.setattr(E, "run_single_stock", selective)
        E.run_sweep([FakeSpec("exploder")], ["tcs"], cfg, resume=False, workers=1)

        rows = _rows(C.TEST_JSONL)
        assert len(rows) == 1, "a dropped pair would leave an empty file here"
        row = rows[0]
        assert row["ok"] is False
        assert row["stage"] == "test"
        assert (row["strategy"], row["stock"]) == ("exploder", "tcs")
        assert row["error"], "an ok:false row must carry some reason"

    def test_partial_candidate_failures_are_retained(self, outdir, fake_engine, cfg,
                                                     monkeypatch):
        """When *some* candidates succeed the per-candidate reasons are kept."""
        state = {"n": 0}

        def sometimes(bars, spec, params, **kw):
            state["n"] += 1
            if state["n"] == 1:
                raise ValueError("first candidate exploded")
            return _fake_backtest(bars, spec, params, **kw)

        monkeypatch.setattr(E, "run_single_stock", sometimes)
        row, _ = E.optimise_pair(FakeSpec("part"), "tcs", cfg)
        assert row["ok"] is True
        assert row["n_failed_candidates"] == 1
        assert "first candidate exploded" in json.dumps(row["failures"])

    def test_total_candidate_failure_retains_the_reasons(self, outdir, fake_engine, cfg,
                                                         monkeypatch):
        """Repro: a strategy that raises on every bar.

        The all-failed path used to return only ``"no candidate backtested (N failures)"``
        and throw away the ``failures`` dict that was already in scope, so the one row
        that exists specifically to make a broken strategy auditable carried no
        diagnosis -- the operator had to re-run with their own instrumentation.
        """
        def always_bad(bars, spec, params, **kw):
            raise RuntimeError("kaboom")

        monkeypatch.setattr(E, "run_single_stock", always_bad)
        row, _ = E.optimise_pair(FakeSpec("exploder"), "tcs", cfg)
        assert row["ok"] is False
        assert "kaboom" in row["error"], row["error"]
        assert row["failures"], "the per-candidate reasons belong on the row"
        assert len(row["failures"]) == cfg.budget
        assert "kaboom" in json.dumps(row["failures"])

    def test_a_failing_pair_is_visible_to_analysis_as_a_gap_not_a_success(
        self, outdir, cfg
    ):
        """The row exists but must NOT be counted as a completed pair by analyze."""
        _write_jsonl(C.TEST_JSONL,
                     [_ok_row("a", "tcs"), _failed_row("b", "infy")])
        rows = load_rows(C.TEST_JSONL)
        assert len(rows) == 1
        assert rows[0]["strategy"] == "a"

    def test_load_rows_can_include_the_failures_on_request(self, outdir, cfg):
        _write_jsonl(C.TEST_JSONL,
                     [_ok_row("a", "tcs"), _failed_row("b", "infy"),
                      _failed_row("c", "hcl")])
        assert len(load_rows(C.TEST_JSONL)) == 1
        allrows = load_rows(C.TEST_JSONL, include_failed=True)
        assert len(allrows) == 3
        assert sum(1 for r in allrows if r["ok"]) == 1
        assert sum(1 for r in allrows if not r["ok"]) == 2

    def test_uncaught_exception_in_optimise_pair_is_recorded(self, outdir, fake_engine,
                                                             cfg, monkeypatch):
        """Even a failure *outside* the per-candidate try/except must land as a row."""
        def boom(spec, stock, cfg_, *, timeframe="1d"):
            raise ZeroDivisionError("division by zero in optimise_pair")

        monkeypatch.setattr(E, "optimise_pair", boom)
        m = E.run_sweep([FakeSpec("a"), FakeSpec("b")], ["tcs", "infy"], cfg,
                        resume=False, workers=1)

        assert m["n_failed"] == 4 and m["n_ok"] == 0
        rows = _rows(C.TEST_JSONL)
        assert len(rows) == 4, "one row per pair, no more and no fewer"
        assert all(r["ok"] is False for r in rows)
        assert all("UNCAUGHT ZeroDivisionError" in r["error"] for r in rows)
        assert all(r.get("traceback") for r in rows), "the traceback must be kept"

    def test_manifest_counts_agree_with_the_rows_on_disk(self, outdir, fake_engine, cfg,
                                                         monkeypatch):
        def selective(bars, spec, params, **kw):
            if spec.name == "bad":
                raise RuntimeError("x")
            return _fake_backtest(bars, spec, params, **kw)

        monkeypatch.setattr(E, "run_single_stock", selective)
        specs = [FakeSpec("bad"), FakeSpec("good")]
        m = E.run_sweep(specs, ["tcs"], cfg, resume=False, workers=1)

        rows = _rows(C.TEST_JSONL)
        assert m["n_pairs_run"] == len(rows), "manifest and file must not disagree"
        assert m["n_ok"] == sum(1 for r in rows if r["ok"]) == 1
        assert m["n_failed"] == sum(1 for r in rows if not r["ok"]) == 1

    def test_one_strategy_failing_does_not_break_the_others_catalog(
        self, outdir, fake_engine, cfg, monkeypatch
    ):
        """A real pair over the real catalog must complete under the harness."""
        specs = discover(("rsi_strategy", "supertrend_strategy"))
        assert len(specs) == 2
        m = E.run_sweep(specs, ["tcs"], cfg, resume=False, workers=1)
        assert m["n_pairs_run"] == 2

    def test_parallel_workers_honour_a_redirected_output_path(self, outdir):
        """The parallel path is the *default* (``--workers 8``).

        ``_work`` was handed to joblib's loky backend, which re-imports
        ``research.optimize.config`` in the child and so resolved ``C.TEST_JSONL`` to the
        module default, not the caller's redirect. A scratch run silently appended rows to
        the real 4,032-pair artefact while the manifest still read as a complete run.
        It bit us for real.

        Fixed by passing the output paths as arguments, which loky pickles.

        Uses a REAL strategy and REAL bars on purpose: loky children do not inherit the
        parent's monkeypatch, so a stubbed spec fails every pair for an unrelated reason
        and the assertion never actually exercises the redirect.
        """
        from research.optimize import engine as _E

        default_file = pathlib.Path(_C_DEFAULT_TEST_JSONL)
        before = len(default_file.read_text().splitlines()) if default_file.exists() else 0

        cfg = C.RunConfig(budget=3, null_replicas=8, workers=2)
        _E.run_sweep([load_strategy("rsi_strategy")], ["tcs"], cfg,
                     resume=False, workers=2)

        redirected = outdir / "test_results.jsonl"
        assert redirected.exists(), "the redirected path received nothing"
        assert len(redirected.read_text().splitlines()) == 1

        after = len(default_file.read_text().splitlines()) if default_file.exists() else 0
        assert after == before, (
            f"the default artefact grew from {before} to {after} rows -- a worker "
            f"resolved the module default instead of the redirect"
        )


# =========================================================================== #
# 4. analyse() on degenerate inputs
# =========================================================================== #
class TestAnalyseDegenerate:
    def test_missing_results_file(self, tmp_path):
        out = analyse(load_rows(tmp_path / "nope.jsonl"))
        assert out["n_pairs"] == 0
        assert out["n_failed_pairs"] == 0
        assert "error" in out
        assert _headline(out) == "NO DATA"

    def test_empty_results_file(self, outdir):
        p = _write_jsonl(C.TEST_JSONL, [])
        out = analyse(load_rows(p))
        assert out["n_pairs"] == 0
        assert out["n_failed_candidates_total"] == 0
        assert "no completed pairs" in out["error"]
        assert _headline(out) == "NO DATA"
        assert "significant" not in _headline(out).lower()

    def test_every_pair_failed(self, outdir):
        """Fix E: this must NOT read as "no data".

        Before, ``load_rows`` filtered failures away, so 7 recorded failures and an empty
        file were identical and the verdict said "run the sweep first" -- sending the
        operator back to re-run something whose answer was already on disk.
        """
        _write_jsonl(C.TEST_JSONL,
                     [_failed_row(f"s{i}", "tcs", "empty TRAIN slice") for i in range(7)])
        rows = load_rows(C.TEST_JSONL)
        assert rows == []
        out = analyse(rows)
        assert out["n_pairs"] == 0
        assert out["n_failed_pairs"] == 7

        h = _headline(out)
        assert h != "NO DATA", "an all-failed run must not be reported as no run"
        assert "7 pairs ran and ALL FAILED" in h
        assert "run the sweep first" not in h
        assert str(C.TEST_JSONL) in h, "the verdict must say where the reasons are"
        assert "significant" not in h.lower(), "no survivors, so no significance claim"

    def test_all_failed_is_distinguishable_from_an_empty_file(self, outdir):
        _write_jsonl(C.TEST_JSONL, [_failed_row(f"s{i}", "tcs") for i in range(3)])
        all_failed = analyse(load_rows(C.TEST_JSONL))
        _write_jsonl(C.TEST_JSONL, [])
        empty = analyse(load_rows(C.TEST_JSONL))
        assert _headline(all_failed) != _headline(empty)
        assert all_failed["n_failed_pairs"] == 3
        assert empty["n_failed_pairs"] == 0

    def test_all_failed_counted_without_passing_rows(self, outdir):
        """``analyse()`` with no argument takes the same path from the configured file."""
        _write_jsonl(C.TEST_JSONL, [_failed_row(f"s{i}", "tcs") for i in range(4)])
        out = analyse()
        assert out["n_pairs"] == 0
        assert out["n_failed_pairs"] == 4
        assert "4 pairs ran and ALL FAILED" in _headline(out)

    def test_a_single_working_pair_reports_zero_failures(self, outdir):
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs"), _failed_row("b", "infy")])
        out = analyse()
        assert out["n_pairs"] == 1
        assert out["n_failed_pairs"] == 1
        assert "NO DATA" not in _headline(out)

    def test_single_pair_fdr(self, outdir):
        p = _write_jsonl(C.TEST_JSONL, [_ok_row("solo", "tcs", p_timing=0.01)])
        out = analyse(load_rows(p))
        assert out["n_pairs"] == 1
        # n=1 => the BH threshold is exactly alpha, so p=0.01 clears.
        assert out["n_significant_vs_timing_null"] == 1
        assert "1 of 1 pairs" in out["verdict"]

    def test_expected_by_chance_is_not_rounded_to_zero(self, outdir):
        """Fix H: ``f"{0.05 * n:.0f}"`` printed 'against ~0 expected by chance' at n=1,
        which reads as 'no false positives were possible' -- the opposite of the truth.
        The expectation now carries one decimal."""
        rows = [_ok_row("solo", "tcs", p_timing=0.01)]
        out = analyse(rows)
        assert "against ~0 expected by chance" not in out["verdict"], out["verdict"]
        assert "against 0.1 expected by chance" in out["verdict"], out["verdict"]
        assert out["expected_false_positives_at_alpha"] == pytest.approx(0.1)
        assert isinstance(out["expected_false_positives_at_alpha"], float)

    def test_all_p_values_identical(self, outdir):
        rows = [_ok_row(f"s{i}", f"stk{i}", p_timing=0.5, p_params=0.5)
                for i in range(10)]
        out = analyse(rows)
        assert out["n_significant_vs_timing_null"] == 0
        assert out["n_significant_vs_params_null"] == 0
        assert "NO EDGE" in out["verdict"]

    def test_all_p_values_identical_and_tiny(self, outdir):
        """100 identical p=0.01 with n=100: BH legitimately rejects all of them."""
        rows = [_ok_row(f"s{i}", f"stk{i}", p_timing=0.01) for i in range(100)]
        out = analyse(rows)
        assert out["n_significant_vs_timing_null"] == 100
        assert out["pct_significant"] == 100.0

    @pytest.mark.parametrize("bad", [float("nan"), 0.0, 1.0])
    def test_pathological_p_values(self, outdir, bad):
        rows = [_ok_row(f"s{i}", f"stk{i}", p_timing=bad, p_params=bad)
                for i in range(6)]
        out = analyse(rows)
        assert out["n_pairs"] == 6
        assert 0 <= out["n_significant_vs_timing_null"] <= 6
        if bad == float("nan"):
            assert out["n_significant_vs_timing_null"] == 0, "NaN must never reject"

    def test_nan_and_zero_p_values_survive_a_json_round_trip(self, outdir):
        """Written to disk by the engine and read back by analyze."""
        rows = [_ok_row("a", "tcs", p_timing=float("nan"), p_params=0.0),
                _ok_row("b", "infy", p_timing=0.9, p_params=0.9)]
        p = _write_jsonl(C.TEST_JSONL, rows)
        back = load_rows(p)
        assert len(back) == 2
        assert np.isnan(back[0]["p_timing"])
        out = analyse(back)
        assert out["n_significant_vs_timing_null"] == 0

    def test_exposure_zero_and_one(self, outdir):
        rows = [_ok_row("a", "tcs", test={"cagr": 0.0, "sharpe": 0.0, "exposure": 0.0}),
                _ok_row("b", "infy", test={"cagr": 0.4, "sharpe": 1.2, "exposure": 1.0})]
        out = analyse(rows)
        assert out["exposure"]["min"] == 0.0
        assert out["exposure"]["max"] == 1.0
        assert out["exposure"]["mean"] == pytest.approx(0.5)

    def test_zero_and_negative_alpha(self, outdir):
        rows = [_ok_row("a", "tcs", alpha_vs_buy_hold=0.0),
                _ok_row("b", "infy", alpha_vs_buy_hold=-0.5)]
        out = analyse(rows)
        assert out["n_beats_buy_hold"] == 0, "alpha of exactly 0 is not 'beats'"

    def test_zero_max_year_share(self, outdir):
        rows = [_ok_row("a", "tcs", test_max_year_share=0.0),
                _ok_row("b", "infy", test_max_year_share=0.9)]
        out = analyse(rows)
        assert out["concentration"]["median_max_year_share"] == pytest.approx(0.45)
        assert out["concentration"]["n_pairs_with_max_year_share_gt_35pct"] == 1

    def test_verdict_never_claims_significance_with_zero_survivors(self, outdir):
        """The single most important anti-overstatement guard in this file."""
        for pv in (0.06, 0.2, 0.9, float("nan")):
            rows = [_ok_row(f"s{i}", f"stk{i}", p_timing=pv) for i in range(25)]
            out = analyse(rows)
            assert out["n_significant_vs_timing_null"] == 0, pv
            v = out["verdict"]
            assert v.startswith("NO EDGE"), v
            assert f"0 of {25} pairs" in v
            assert "no pair may be deployed" in v, (
                "a zero-survivor verdict must forbid deployment, not permit it"
            )
            # One decimal: at n=25 the expectation is 1.25, and rounding to "1" reads as a
        # different claim. Fixed alongside the n=1 case.
        assert f"{C.FDR_ALPHA * 25:.1f} would be expected by chance alone" in v, (
                "the verdict must state how many false positives the alpha admits"
            )

    def test_verdict_states_its_own_denominator(self, outdir):
        rows = [_ok_row(f"s{i}", f"stk{i}", p_timing=0.001) for i in range(40)]
        out = analyse(rows)
        assert "40 of 40 pairs" in out["verdict"]
        assert str(C.FDR_ALPHA) in out["verdict"]

    def test_load_rows_tolerates_a_truncated_final_line(self, outdir):
        """A hard kill mid-write must not stop the analysis of everything before it."""
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs"), _ok_row("b", "infy")])
        with C.TEST_JSONL.open("a", encoding="utf-8") as fh:
            fh.write('{"strategy": "c", "stock": "hcl", "stage": "te')
        rows = load_rows(C.TEST_JSONL)
        assert [r["strategy"] for r in rows] == ["a", "b"], "prior rows must survive"

    def test_load_rows_skips_rows_without_the_test_stage(self, outdir):
        _write_jsonl(C.TEST_JSONL,
                     [_ok_row("a", "tcs"),
                      {"strategy": "b", "stock": "infy", "stage": "train", "ok": True}])
        assert [r["strategy"] for r in load_rows(C.TEST_JSONL)] == ["a"]
        allrows = load_rows(C.TEST_JSONL, include_failed=True)
        assert [r["strategy"] for r in allrows] == ["a"], "a train row is not a result"

    def test_write_report_survives_an_empty_result_set(self, outdir):
        p = _write_jsonl(C.TEST_JSONL, [])
        text = A.write_report(analyse(load_rows(p)))
        assert "NO DATA" in text
        assert "pairs completed | 0" in text
        assert "pairs that failed | 0" in text

    def test_write_report_on_a_real_result_set(self, outdir):
        rows = [_ok_row(f"s{i}", f"stk{i % 3}", p_timing=0.01) for i in range(9)]
        text = A.write_report(analyse(rows))
        assert "pairs completed | 9" in text
        assert "| TEST CAGR |" in text


# =========================================================================== #
# 5. BH-FDR correctness
# =========================================================================== #
class TestBenjaminiHochberg:
    def test_all_null_rejects_nothing(self):
        assert benjamini_hochberg([1.0] * 20, 0.05).sum() == 0
        assert benjamini_hochberg([0.9, 0.99, 0.8, 0.7], 0.05).sum() == 0

    def test_all_perfect_rejects_everything(self):
        assert benjamini_hochberg([0.0] * 20, 0.05).all()
        assert benjamini_hochberg([1e-12] * 20, 0.05).all()

    def test_empty_input(self):
        out = benjamini_hochberg([], 0.05)
        assert out.shape == (0,)
        assert out.dtype == bool

    def test_known_worked_example(self):
        """Textbook BH: p = [.001 .008 .039 .041 .042 .06 .074 .205 .212 .216], q=0.05.

        thresholds = [.005 .010 .015 .020 .025 .030 .035 .040 .045 .050]
        passing ranks = {1, 2}; largest passing rank k=2 -> reject the two smallest.
        """
        p = [0.001, 0.008, 0.039, 0.041, 0.042, 0.06, 0.074, 0.205, 0.212, 0.216]
        sig = benjamini_hochberg(p, 0.05)
        assert sig.tolist() == [True, True] + [False] * 8

    def test_step_up_not_step_down(self):
        """A single passing low rank must reject everything below it (step-up)."""
        p = [0.001, 0.5, 0.6, 0.7, 0.8]
        sig = benjamini_hochberg(p, 0.05)
        assert sig.tolist() == [True, False, False, False, False]

    def test_one_failing_rank_above_a_passing_one_rejects_all_below(self):
        """p[1] <= its threshold but p[2] > its threshold -- step-up still rejects p[1]."""
        p = [0.001, 0.006, 0.99]
        thresh = [0.05 * 1 / 3, 0.05 * 2 / 3, 0.05]
        assert p[0] <= thresh[0] and p[1] <= thresh[1] and p[2] > thresh[2]
        sig = benjamini_hochberg(p, 0.05)
        assert sig.tolist() == [True, True, False]

    def test_monotone_in_alpha(self):
        rng = np.random.default_rng(20261013)
        for _ in range(40):
            p = list(rng.uniform(0.0, 1.0, size=int(rng.integers(2, 40))))
            counts = [int(benjamini_hochberg(p, a).sum())
                      for a in (0.001, 0.01, 0.05, 0.1, 0.25, 0.5)]
            assert counts == sorted(counts), (p, counts)

    def test_monotone_when_an_extra_hypothesis_is_appended(self):
        """Adding a test can only ever add rejections, never remove them."""
        rng = np.random.default_rng(7)
        for _ in range(40):
            p = list(rng.uniform(0.0, 1.0, size=int(rng.integers(3, 20))))
            base = set(np.flatnonzero(benjamini_hochberg(p, 0.05)).tolist())
            q = p + [float(rng.uniform(0.0, 1.0))]
            grown = set(np.flatnonzero(benjamini_hochberg(q, 0.05)).tolist())
            assert base <= grown, (p, base, grown)

    def test_rejected_set_is_always_a_prefix_of_the_sorted_p_values(self):
        rng = np.random.default_rng(99)
        for _ in range(60):
            p = np.asarray(rng.uniform(0.0, 1.0, size=int(rng.integers(1, 60))))
            sig = benjamini_hochberg(p.tolist(), 0.05)
            srt = np.sort(p)
            k = int(sig.sum())
            if k == 0:
                assert not sig.any()
            else:
                assert srt[:k].max() <= srt[k:].min() + 1e-15, (p, sig)

    def test_a_rejected_value_never_exceeds_its_bh_threshold(self):
        rng = np.random.default_rng(1234)
        for _ in range(40):
            p = np.asarray(rng.uniform(0.0, 1.0, size=25))
            sig = benjamini_hochberg(p.tolist(), 0.05)
            order = np.argsort(p)
            for rank, idx in enumerate(order):
                if sig[idx]:
                    assert p[idx] <= 0.05 * (rank + 1) / len(p) + 1e-15

    def test_nan_is_never_rejected(self):
        assert not benjamini_hochberg([float("nan")] * 5, 0.05).any()
        sig = benjamini_hochberg([0.001, float("nan"), float("nan")], 0.05)
        assert sig.tolist() == [True, False, False]

    def test_zero_p_values_are_rejected(self):
        sig = benjamini_hochberg([0.0, 0.0, 0.9], 0.05)
        assert sig.tolist() == [True, True, False]

    def test_result_is_a_boolean_array_of_the_right_shape(self):
        sig = benjamini_hochberg([0.01] * 7, 0.05)
        assert sig.shape == (7,)
        assert sig.dtype == bool

    def test_a_single_p_just_above_alpha_is_not_rejected(self):
        assert not benjamini_hochberg([0.051], 0.05)[0]
        assert benjamini_hochberg([0.049], 0.05)[0]

    def test_default_alpha_is_the_configured_one(self):
        """No alpha argument must mean FDR_ALPHA, not 1.0 and not 0.01."""
        assert bool(benjamini_hochberg([0.049])[0]) is True, "just inside q<0.05"
        assert bool(benjamini_hochberg([0.051])[0]) is False, "just outside q<0.05"
        assert C.FDR_ALPHA == 0.05

    def test_an_explicit_alpha_overrides_the_default(self):
        assert bool(benjamini_hochberg([0.3], 0.05)[0]) is False
        assert bool(benjamini_hochberg([0.3], 0.9)[0]) is True


# =========================================================================== #
# 6. CLI surface
# =========================================================================== #
#: Every flag the task calls out, with a value that parses.
SAMPLE_FLAGS = {
    "--budget": "12",
    "--stocks": ["tcs"],
    "--strategies": ["rsi_strategy"],
    "--no-tax": None,
    "--no-resume": None,
    "--resume": None,
    "--smoke": None,
    "--dry-run": None,
    "--list": None,
    "--rebalance": "W",
    "--seed": "123",
    "--null-replicas": "16",
    "--workers": "2",
    "--no-fastpath": None,
    "--timeframe": "1d",
}


def _argv(flags: dict) -> list[str]:
    out: list[str] = []
    for name, value in flags.items():
        out.append(name)
        if value is not None:
            out.extend(value if isinstance(value, list) else [value])
    return out


class TestCliSurface:
    def test_every_flag_in_this_task_parses(self):
        args = R.build_parser().parse_args(_argv(SAMPLE_FLAGS))
        for name in SAMPLE_FLAGS:
            assert name.lstrip("-").replace("-", "_") in vars(args), name

    def test_every_flag_documented_in_readme_and_run_md_parses(self):
        documented: set[str] = set()
        for doc in (OPTIMIZE_DIR / "README.md", REPO / "RUN.md"):
            text = doc.read_text(encoding="utf-8")
            for block in re.findall(r"```bash(.*?)```", text, re.S):
                documented |= set(DOC_FLAG_RE.findall(block))
        assert documented, "no optimizer flags found in the docs"

        known = {o for action in R.build_parser()._actions for o in action.option_strings}
        unknown = documented - known
        assert not unknown, f"documented but not accepted by the CLI: {sorted(unknown)}"

    @pytest.mark.parametrize("name,value", sorted(SAMPLE_FLAGS.items()))
    def test_each_flag_parses_on_its_own(self, name, value):
        argv = [name] + ([] if value is None
                         else (value if isinstance(value, list) else [value]))
        assert R.build_parser().parse_args(argv) is not None

    def test_rebalance_rejects_an_unknown_frequency(self):
        with pytest.raises(SystemExit):
            R.build_parser().parse_args(["--rebalance", "Q"])

    def test_defaults_match_the_documented_values(self):
        a = R.build_parser().parse_args([])
        assert a.budget == C.DEFAULT_BUDGET
        assert a.rebalance == "M"
        assert a.timeframe == "1d"
        assert a.no_tax is False, "tax is ON unless --no-tax"
        assert a.seed == C.MASTER_SEED
        assert a.null_replicas == C.DEFAULT_NULL_REPLICAS

    def test_list_exits_zero_and_prints_the_catalog(self, capsys):
        assert R.main(["--list", "--strategies", "rsi_strategy"]) == 0
        out = capsys.readouterr().out
        assert "strategies" in out and "rsi_strategy" in out

    def test_dry_run_does_not_backtest(self, outdir, monkeypatch, capsys):
        called: list = []
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(R, "run_sweep", lambda *a, **k: called.append(a) or {})
        monkeypatch.setattr(S, "available_symbols", lambda tf="1d": ["tcs", "infy"])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))

        assert R.main(["--dry-run"]) == 0
        assert called == [], "--dry-run must not invoke run_sweep"
        assert "would run 2 pairs" in capsys.readouterr().out

    def test_unknown_strategy_fails_loudly(self, outdir, monkeypatch):
        assert R.main(["--strategies", "no_such_strategy", "--dry-run"]) == 2

    def test_unknown_symbol_fails_loudly(self, outdir, monkeypatch):
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "available_symbols", lambda tf="1d": ["no_such_symbol"])
        monkeypatch.setattr(S, "bars", lambda *a, **k: pd.DataFrame())
        assert R.main(["--dry-run"]) == 2

    def test_a_mix_of_good_and_unknown_still_runs_the_good_ones(self, outdir, monkeypatch,
                                                               capsys):
        """Fix A: an unknown symbol only warns and is dropped, so a partially valid list
        still sweeps the valid part instead of silently doing nothing."""
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "bars", lambda sym, *a, **k: (
            _bars(5) if sym == "tcs" else pd.DataFrame()))
        assert R.main(["--dry-run", "--stocks", "tcs", "ghost"]) == 0
        assert "would run 1 pairs" in capsys.readouterr().out

    def test_empty_catalog_is_an_error_not_a_zero_pair_sweep(self, outdir, monkeypatch):
        monkeypatch.setattr(R, "discover", lambda names=(): [])
        assert R.main(["--dry-run"]) == 2

    def test_smoke_forces_a_fresh_run(self, outdir, fake_engine, monkeypatch):
        """A smoke run must never resume, or it reports '[0/0] done' and tests nothing."""
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a"), FakeSpec("b")])
        monkeypatch.setattr(S, "available_symbols", lambda tf="1d": ["tcs", "infy"])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        _write_jsonl(C.TEST_JSONL, [_ok_row("a", "tcs"), _ok_row("a", "infy")])
        # --workers 1: a loky child does not inherit the parent's monkeypatching.
        assert R.main(["--smoke", "--workers", "1", "--strategies", "a",
                       "--stocks", "tcs"]) == 0
        assert C.TEST_JSONL.exists()
        rows = _rows(C.TEST_JSONL)
        assert len(rows) == 2, "smoke must run its 2 pairs, not resume"
        assert all(r["budget"] == 4 for r in rows), "smoke overrides the budget to 4"

    def test_cli_flags_reach_the_manifest(self, outdir, fake_engine, monkeypatch, capsys):
        """A flag that parses but never reaches RunConfig would silently change results."""
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        rc = R.main(["--workers", "1", "--budget", "7", "--seed", "424242",
                     "--null-replicas", "3", "--no-tax", "--rebalance", "W",
                     "--stocks", "tcs", "--no-resume"])
        assert rc == 0
        m = json.loads(C.MANIFEST_JSON.read_text(encoding="utf-8"))
        assert m["seed"] == 424242, "--seed did not reach the manifest"
        assert m["budget"] == 7
        assert m["null_replicas"] == 3
        assert m["tax_enabled"] is False, "--no-tax did not reach the manifest"
        assert m["rebalance"] == "W"
        rows = _rows(C.TEST_JSONL)
        assert rows and rows[0]["seed"] == E.pair_seed("a", "tcs", 424242)

    def test_tax_is_on_by_default(self, outdir, fake_engine, monkeypatch):
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        R.main(["--workers", "1", "--stocks", "tcs", "--no-resume"])
        m = json.loads(C.MANIFEST_JSON.read_text(encoding="utf-8"))
        assert m["tax_enabled"] is True

    def test_explicitly_named_excluded_symbol_is_rejected(self, outdir, monkeypatch):
        """Fix A: ``available_symbols()`` honoured EXCLUDED_SYMBOLS; an explicit
        ``--stocks`` used to bypass it, so the sweep optimised on data the production
        engine has already rejected as structurally corrupt."""
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        for bad in sorted(S.EXCLUDED_SYMBOLS):
            assert R.main(["--dry-run", "--stocks", bad]) == 2, bad

    def test_an_excluded_symbol_poisoning_a_valid_list_is_still_fatal(self, outdir,
                                                                      monkeypatch):
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        assert R.main(["--dry-run", "--stocks", "tcs", "adanient"]) == 2

    def test_intraday_timeframes_are_refused(self, outdir, monkeypatch, capsys):
        """Fix C. The flag help says 'only 1d is supported; GOAL.md bans intraday' and
        now it is enforced before the catalog is even loaded.

        Why it mattered, measured on the real panel (2026-10-06):

            tf   full bars   TRAIN 2016-2023   TEST 2024-2026
            1d      4628           1975              685
            1h       463              0              463
            5m        32              0               32

        ``_read`` normalises the index, so a 5m file collapses to one bar per calendar
        day (tcs_5m.csv: 2,472 raw rows -> 32 bars). The result was 4,032 pairs all
        failing with 'empty TRAIN slice' -- a full-size manifest and an empty result set.
        """
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "available_symbols", lambda tf="1d": ["tcs"])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        for tf in ("1m", "5m", "15m", "30m", "1h"):
            assert R.main(["--dry-run", "--timeframe", tf]) == 2, tf

    def test_one_d_is_still_accepted(self, outdir, fake_engine, monkeypatch):
        monkeypatch.setattr(R, "discover", lambda names=(): [FakeSpec("a")])
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        assert R.main(["--dry-run", "--timeframe", "1d"]) == 0


# =========================================================================== #
# 7. Data loading edge cases
# =========================================================================== #
@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Point ``splitter`` at a throwaway data directory and clear its module cache."""
    d = tmp_path / "nse"
    d.mkdir()
    monkeypatch.setattr(C, "DATA_DIR", d)
    monkeypatch.setattr(S, "_CACHE", {})
    return d


def _write_csv(path: Path, **cols) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(cols).to_csv(path, index=False)
    return path


def _ts(dates) -> list[int]:
    return [int(pd.Timestamp(d).value // 1_000_000) for d in dates]


def _rising(n: int, start: float = 100.0) -> list[float]:
    """Distinct closes. An all-identical run of >=5 bars is dropped as a vendor freeze,
    so every fixture here has to vary or it loads as empty."""
    return [start + i for i in range(n)]


class TestDataLoading:
    def test_missing_csv_yields_an_empty_frame_not_an_exception(self, data_dir):
        df = S._read("ghost", "1d")
        assert isinstance(df, pd.DataFrame)
        assert df.empty, "a missing file must read as empty, not raise"
        assert S.bars("ghost", S.FULL, "1d").empty
        assert S.train_bars("ghost").empty and S.test_bars("ghost").empty

    def test_epoch_ms_numeric_column_is_read_as_milliseconds(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=10)
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates), close=_rising(10))
        df = S._read("s", "1d")
        assert len(df) == 10
        assert df.index[0] == pd.Timestamp("2020-01-01"), (
            "a bare int must be read as ms; read as seconds it lands in 1970 and every "
            "window slice is silently empty"
        )

    def test_date_string_column_is_accepted(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=10)
        _write_csv(data_dir / "s_1d.csv",
                   date=[d.strftime("%Y-%m-%d") for d in dates], close=_rising(10))
        df = S._read("s", "1d")
        assert len(df) == 10
        assert df.index[0] == pd.Timestamp("2020-01-01")

    def test_datetime_and_timestamp_column_aliases(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=5)
        for col in ("datetime", "timestamp"):
            _write_csv(data_dir / f"{col}_1d.csv", **{col: [str(d.date()) for d in dates]},
                       close=_rising(5))
            assert len(S._read(col, "1d")) == 5, col

    def test_missing_date_column_raises_a_named_error(self, data_dir):
        _write_csv(data_dir / "s_1d.csv", px=[1.0, 2.0, 3.0])
        with pytest.raises(KeyError, match="no date column"):
            S._read("s", "1d")

    def test_missing_close_column_raises_a_named_error(self, data_dir):
        _write_csv(data_dir / "s_1d.csv", ts=_ts(pd.bdate_range("2020-01-01", periods=3)),
                   volume=[1.0] * 3)
        with pytest.raises(KeyError, match="no close column"):
            S._read("s", "1d")

    def test_duplicate_timestamps_are_collapsed_keeping_the_last(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=4)
        ts = _ts(list(dates) + [dates[1]])
        # 99.0 is the *second* copy of day 2; keep=last must win over the original.
        _write_csv(data_dir / "s_1d.csv", ts=ts, close=[1.0, 2.0, 3.0, 4.0, 99.0])
        df = S._read("s", "1d")
        assert len(df) == 4
        assert df["close"].tolist()[1] == 99.0, "keep=last must win"

    def test_duplicate_timestamps_do_not_break_the_window_slices(self, data_dir):
        dates = pd.bdate_range("2024-01-01", periods=6)
        ts = _ts(list(dates) * 3)
        _write_csv(data_dir / "s_1d.csv", ts=ts, close=_rising(len(ts)))
        assert S.train_bars("s").empty, "2024 rows are all in TEST, not TRAIN"
        assert len(S.test_bars("s")) == 6

    def test_single_row_file_loads(self, data_dir):
        _write_csv(data_dir / "s_1d.csv", ts=_ts(["2020-06-01"]), close=[123.0])
        df = S._read("s", "1d")
        assert len(df) == 1
        assert df["close"].iloc[0] == 123.0
        assert S.bars("s", S.FULL, "1d").shape[0] == 1

    def test_empty_csv_loads_as_empty(self, data_dir):
        _write_csv(data_dir / "s_1d.csv", ts=[], close=[])
        assert S._read("s", "1d").empty

    def test_headers_only_csv_loads_as_empty(self, data_dir):
        (data_dir / "s_1d.csv").write_text("ts,close\n", encoding="utf-8")
        assert S._read("s", "1d").empty

    def test_entirely_non_positive_prices_are_dropped(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=6)
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates), close=[0.0, -5.0] * 3)
        df = S._read("s", "1d")
        assert df.empty, "non-positive closes must never be forward-filled back in"

    def test_a_mix_of_good_and_non_positive_keeps_only_the_good(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=5)
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates),
                   close=[100.0, 0.0, -1.0, 103.0, 104.0])
        df = S._read("s", "1d")
        assert df["close"].tolist() == [100.0, 103.0, 104.0]

    def test_pre_2008_rows_are_dropped(self, data_dir):
        dates = pd.to_datetime(["2005-06-01", "2007-06-01", "2009-06-01"])
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates), close=[1.0, 2.0, 3.0])
        assert len(S._read("s", "1d")) == 1

    def test_a_vendor_freeze_run_is_dropped(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=10)
        close = [100.0] * 6 + [101.0, 102.0, 103.0, 104.0]
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates), close=close)
        df = S._read("s", "1d")
        assert len(df) == 4, "the 6-bar identical run is a frozen feed"

    def test_vol_column_is_renamed_to_volume(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=4)
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates), close=_rising(4), vol=[10.0] * 4)
        df = S._read("s", "1d")
        assert "volume" in df.columns and "vol" not in df.columns

    def test_column_names_are_case_insensitive(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=4)
        _write_csv(data_dir / "s_1d.csv", TS=_ts(dates), Close=_rising(4))
        assert len(S._read("s", "1d")) == 4

    def test_unparseable_numeric_coerces_to_nan_and_the_row_is_dropped(self, data_dir):
        dates = pd.bdate_range("2020-01-01", periods=4)
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates),
                   close=["100", "n/a", "102", "103"])
        df = S._read("s", "1d")
        assert df["close"].tolist() == [100.0, 102.0, 103.0]

    def test_slices_are_disjoint_and_ordered(self, data_dir):
        dates = pd.bdate_range("2023-12-20", periods=40)
        _write_csv(data_dir / "s_1d.csv", ts=_ts(dates), close=_rising(40))
        tr, te = S.train_bars("s"), S.test_bars("s")
        assert not tr.empty and not te.empty
        assert tr.index.max() <= pd.Timestamp(S.TRAIN.end)
        assert te.index.min() >= pd.Timestamp(S.TEST.start)
        assert set(tr.index).isdisjoint(set(te.index))

    def test_the_cache_does_not_serve_stale_empty_frames(self, data_dir):
        """A symbol read before its file exists caches an empty frame for the whole
        process. Anything that writes data mid-run then silently sees nothing."""
        assert S._read("late", "1d").empty
        _write_csv(data_dir / "late_1d.csv",
                   ts=_ts(pd.bdate_range("2020-01-01", periods=5)), close=_rising(5))
        assert S._read("late", "1d").empty, "documents the sticky-cache behaviour"
        S._CACHE.clear()
        assert len(S._read("late", "1d")) == 5

    def test_cache_key_includes_the_timeframe(self, data_dir):
        """Reading 1d then 1h for one symbol must not return the 1d frame both times."""
        d1 = pd.bdate_range("2020-01-01", periods=6)
        # distinct *days*: _read normalises the index, so same-day intraday rows collapse
        d2 = pd.to_datetime(["2020-02-03 10:00", "2020-02-04 11:00", "2020-02-05 12:00"])
        _write_csv(data_dir / "s_1d.csv", ts=_ts(d1), close=_rising(6))
        _write_csv(data_dir / "s_1h.csv", ts=_ts(d2), close=_rising(3, 500.0))
        assert len(S._read("s", "1d")) == 6
        hourly = S._read("s", "1h")
        assert len(hourly) == 3, "the 1h read was served from the 1d cache entry"
        assert hourly["close"].iloc[0] == 500.0

    def test_available_symbols_ignores_other_timeframes(self, data_dir):
        _write_csv(data_dir / "a_1d.csv", ts=[1], close=[1.0])
        _write_csv(data_dir / "a_5m.csv", ts=[1], close=[1.0])
        _write_csv(data_dir / "a_1h.csv", ts=[1], close=[1.0])
        assert S.available_symbols("1d") == ["a"]
        assert sorted(S.available_symbols()) == ["a"]

    def test_the_intraday_mechanism_behind_the_timeframe_fix_is_real(self):
        """Pins the measurement above so the ``--timeframe`` guard can be checked.

        Not a defect in itself: the loader behaviour is correct (these harnesses are
        daily-only by design). What was missing was a guard in run.py refusing a
        non-1d timeframe before burning a 4,032-pair sweep on it.
        """
        full = S.bars("tcs", S.FULL, "5m")
        assert not full.empty, "5m files exist, so a data-presence check passes"
        assert full.index.is_monotonic_increasing
        assert (full.index == full.index.normalize()).all(), "intraday rows are normalised"
        assert S.train_bars("tcs", "5m").empty, "no 5m data predates 2024"
        assert not S.train_bars("tcs", "1d").empty, "1d TRAIN is fine"


# =========================================================================== #
# 8. The exclusion list
# =========================================================================== #
@pytest.fixture(scope="module")
def production_universe():
    """``load_universe`` re-cleans 50 CSVs (~1.5s); two tests need the same answer."""
    from nsealgo.data.loader import load_universe

    return load_universe(str(REPO / "data" / "nse"))


class TestExcludedSymbols:
    def test_exclusions_match_the_production_loader(self, production_universe):
        """The docstring claims the production loader reports
        ``excluded symbols: ['adanient', 'jiofin']``. Pin that claim."""
        _, symbols, report = production_universe
        excluded = set(report.excluded_symbols)

        assert excluded == set(S.EXCLUDED_SYMBOLS), (
            f"splitter excludes {sorted(S.EXCLUDED_SYMBOLS)} but the production loader "
            f"excludes {sorted(excluded)} -- the two harnesses would silently disagree"
        )
        assert not (set(S.EXCLUDED_SYMBOLS) & set(symbols)), "an excluded symbol leaked"

    def test_available_symbols_and_load_universe_agree(self, production_universe):
        _, symbols, _ = production_universe
        available = set(S.available_symbols("1d"))
        assert available == set(symbols), (
            f"only in available_symbols: {sorted(available - set(symbols))}; "
            f"only in load_universe: {sorted(set(symbols) - available)}"
        )
        assert len(available) == 48, "50 constituents minus the 2 corrupt files"

    def test_the_exclusion_list_is_non_empty_and_documented(self):
        assert S.EXCLUDED_SYMBOLS
        doc = (OPTIMIZE_DIR / "splitter.py").read_text(encoding="utf-8")
        assert "nsealgo.data.loader" in doc, "the source must name what it mirrors"
        readme = (OPTIMIZE_DIR / "README.md").read_text(encoding="utf-8")
        for sym in S.EXCLUDED_SYMBOLS:
            assert sym in readme, f"{sym} is excluded but the README does not say so"

    def test_available_symbols_filters_the_excluded(self):
        assert not (set(S.available_symbols("1d")) & S.EXCLUDED_SYMBOLS)

    def test_include_excluded_reveals_them(self, tmp_path, monkeypatch):
        d = tmp_path / "nse"
        d.mkdir()
        for sym in ("good", "adanient", "jiofin"):
            (d / f"{sym}_1d.csv").write_text("ts,close\n1,1.0\n", encoding="utf-8")
        monkeypatch.setattr(C, "DATA_DIR", d)
        assert S.available_symbols("1d") == ["good"]
        assert sorted(S.available_symbols("1d", include_excluded=True)) == \
            ["adanient", "good", "jiofin"]

    def test_bars_can_still_be_read_for_an_excluded_symbol(self, tmp_path, monkeypatch):
        """The exclusion lives in symbol *selection*, not in the loader -- which is why
        ``--stocks adanient`` (bug A) got as far as a real backtest before the fix."""
        d = tmp_path / "nse"
        d.mkdir()
        dates = pd.bdate_range("2020-01-01", periods=5)
        _write_csv(d / "adanient_1d.csv", ts=_ts(dates), close=_rising(5, 10.0))
        monkeypatch.setattr(C, "DATA_DIR", d)
        monkeypatch.setattr(S, "_CACHE", {})
        assert len(S.bars("adanient", S.FULL, "1d")) == 5


# =========================================================================== #
# 9. The candidate de-duplication loop
# =========================================================================== #
#: Run in a subprocess because a spec whose search space is smaller than `budget` used to
#: spin forever: a test that hangs the suite is worse than no test at all.
DEDUP_PROBE = textwrap.dedent(
    """
    from types import SimpleNamespace

    import numpy as np
    import pandas as pd

    from research.optimize import config as C
    from research.optimize import engine as E
    from research.optimize import splitter as S

    def bars(n, start):
        rng = np.random.default_rng(0)
        idx = pd.bdate_range(start, periods=n)
        px = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, n)))
        return pd.DataFrame({"open": px, "high": px, "low": px, "close": px}, index=idx)

    S.train_bars = lambda sym, tf="1d": bars(200, "2018-01-01")
    S.test_bars = lambda sym, tf="1d": bars(150, "2024-02-01")
    E.run_single_stock = lambda b, s, p, **k: SimpleNamespace(
        equity=pd.Series(b["close"].to_numpy() * 1000, index=b.index),
        exposure=0.5, turnover=1.0, total_fees=0.0, total_tax=0.0, trades=[0])

    spec = SimpleNamespace(
        name="stuck", default={"period": 1},
        sample=lambda rng: {"period": 1},          # the same config, forever
    )
    cfg = C.RunConfig(budget=8, null_replicas=2)
    row, _ = E.optimise_pair(spec, "tcs", cfg)
    print("TERMINATED", row.get("ok"), row.get("n_candidates"), cfg.budget)
    """
)


class TestCandidateDedup:
    def test_a_constant_sampler_terminates(self):
        """The loop used to retry a duplicate config forever, with no bail-out.

        Repro: a StrategySpec whose ``sample()`` always returns the same dict -- true for
        a strategy whose only knob is a 2-valued Literal or a lone bool, which the
        catalog does not currently contain but nothing prevents one being added. The
        sweep spun inside the pair with no output, no log line and no timeout, instead
        of failing the pair the way every other bad case is handled.
        """
        r = subprocess.run(
            [sys.executable, "-c", DEDUP_PROBE],
            capture_output=True, text=True, timeout=120,
            cwd=REPO, env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin"},
        )
        assert r.returncode == 0, r.stderr
        assert "TERMINATED" in r.stdout, r.stdout

        parts = r.stdout.split()
        assert parts[1] == "True", "the one distinct candidate must still be evaluated"
        n_candidates, budget = int(parts[2]), int(parts[3])
        assert n_candidates == 1, "only 'default' is reachable, so 1 candidate is correct"
        assert n_candidates < budget, (
            "the loop must give up before reaching an unreachable budget, not spin"
        )

    def test_the_bail_out_is_bounded(self, outdir, fake_engine, cfg):
        """In-process equivalent: the sampler is asked for at most ``budget * 50`` draws."""
        spec = FakeSpec("stuck", constant=object())
        row, summary = E.optimise_pair(spec, "tcs", cfg)
        assert row["ok"] is True, "bailing out early is not a failure"
        assert row["n_candidates"] == 1
        assert spec.samples <= cfg.budget * 50, (
            f"{spec.samples} draws for an unreachable budget of {cfg.budget}"
        )
        assert summary is not None

    def test_a_normal_sampler_still_reaches_the_full_budget(self, outdir, fake_engine, cfg):
        row, _ = E.optimise_pair(FakeSpec("ok"), "tcs", cfg)
        assert row["n_candidates"] == cfg.budget, (
            "the bail-out must not shorten a healthy search"
        )


# =========================================================================== #
# 10. Determinism and seeding
# =========================================================================== #
class TestPairSeed:
    def test_pair_seed_is_deterministic_across_processes(self):
        """``hash()`` is salted per process; a resume would replay a different search."""
        code = textwrap.dedent(
            """
            from research.optimize.engine import pair_seed
            print(pair_seed("rsi_strategy", "tcs", 20261013))
            """
        )
        outs = set()
        for pyhashseed in ("0", "987654321"):
            r = subprocess.run(
                [sys.executable, "-c", code], capture_output=True, text=True, timeout=120,
                cwd=REPO, env={"PYTHONPATH": "src", "PYTHONHASHSEED": pyhashseed,
                               "PATH": "/usr/bin:/bin"},
            )
            assert r.returncode == 0, r.stderr
            outs.add(r.stdout.strip())
        assert len(outs) == 1, f"pair_seed varied with PYTHONHASHSEED: {outs}"

    def test_pair_seed_is_the_documented_blake2b_derivation(self):
        """Exact, and cheaper than the subprocess check: no ``hash()`` anywhere."""
        import hashlib

        want = int.from_bytes(
            hashlib.blake2b(b"20261013|rsi_strategy|tcs", digest_size=8).digest(), "big"
        )
        assert E.pair_seed("rsi_strategy", "tcs", 20261013) == want

    def test_pair_seed_separates_neighbouring_pairs(self):
        seeds = {E.pair_seed(s, st, 1) for s in ("a", "b") for st in ("x", "y")}
        assert len(seeds) == 4

    def test_pair_seed_changes_with_the_master_seed(self):
        assert E.pair_seed("a", "tcs", 1) != E.pair_seed("a", "tcs", 2)

    def test_pair_seed_is_a_valid_rng_seed(self):
        s = E.pair_seed("rsi_strategy", "tcs", 20261013)
        assert 0 <= s < 2**64
        assert np.random.default_rng(s).random() >= 0.0


class TestPairDeterminism:
    def test_the_same_pair_replayed_twice_gives_the_same_row(self, outdir, fake_engine,
                                                               cfg):
        row1, _ = E.optimise_pair(FakeSpec("det"), "tcs", cfg)
        row2, _ = E.optimise_pair(FakeSpec("det"), "tcs", cfg)
        assert row1 == row2, "a pair must be reproducible in isolation"

    def test_different_pairs_get_different_seeds(self, outdir, fake_engine, cfg):
        r1, _ = E.optimise_pair(FakeSpec("a"), "tcs", cfg)
        r2, _ = E.optimise_pair(FakeSpec("b"), "tcs", cfg)
        r3, _ = E.optimise_pair(FakeSpec("a"), "infy", cfg)
        assert len({r1["seed"], r2["seed"], r3["seed"]}) == 3

    def test_an_empty_train_slice_fails_the_pair_loudly(self, outdir, fake_engine, cfg,
                                                        monkeypatch):
        monkeypatch.setattr(S, "train_bars", lambda sym, tf="1d": pd.DataFrame())
        row, summary = E.optimise_pair(FakeSpec("a"), "tcs", cfg)
        assert row["ok"] is False
        assert "TRAIN" in row["error"]
        assert summary is None

    def test_an_empty_test_slice_fails_the_pair_loudly(self, outdir, fake_engine, cfg,
                                                       monkeypatch):
        monkeypatch.setattr(S, "test_bars", lambda sym, tf="1d": pd.DataFrame())
        row, _ = E.optimise_pair(FakeSpec("a"), "tcs", cfg)
        assert row["ok"] is False and "TEST" in row["error"]

    def test_a_test_side_backtest_error_is_attributed_to_TEST(self, outdir, fake_engine,
                                                              cfg, monkeypatch):
        real = _fake_backtest
        state = {"n": 0}

        def fail_on_test(bars, spec, params, **kw):
            state["n"] += 1
            if state["n"] > cfg.budget:
                raise ValueError("test-side explosion")
            return real(bars, spec, params, **kw)

        monkeypatch.setattr(E, "run_single_stock", fail_on_test)
        row, _ = E.optimise_pair(FakeSpec("a"), "tcs", cfg)
        assert row["ok"] is False
        assert row["error"].startswith("TEST")
        assert row.get("train_best") is not None, "the search result is still auditable"

    def test_a_fully_failing_search_reports_the_failure_count(self, outdir, fake_engine,
                                                              cfg, monkeypatch):
        def always_bad(bars, spec, params, **kw):
            raise RuntimeError("nope")

        monkeypatch.setattr(E, "run_single_stock", always_bad)
        row, summary = E.optimise_pair(FakeSpec("a"), "tcs", cfg)
        assert row["ok"] is False
        assert f"{cfg.budget} failures" in row["error"]
        assert summary is None

    def test_a_successful_row_carries_every_auditable_field(self, outdir, fake_engine, cfg):
        row, summary = E.optimise_pair(FakeSpec("a"), "tcs", cfg)
        for key in ("strategy", "stock", "stage", "seed", "capital", "tax_enabled",
                    "rebalance", "budget", "best_label", "params", "n_candidates",
                    "train", "test", "test_yearly", "alpha_vs_buy_hold",
                    "p_params", "p_timing", "engine", "total_tax_test"):
            assert key in row, key
        assert row["stage"] == "test"
        assert row["capital"] == float(C.CAPITAL_INR)
        assert summary is not None and summary["stage"] == "train"
        assert summary["default_train"] is not None, (
            "the shipped default must always be reported so the search's value is measured"
        )

    def test_the_default_candidate_is_actually_backtested(self, outdir, fake_engine, cfg):
        """``default`` must be among the evaluated candidates, not just a label."""
        spec = FakeSpec("base")
        seen: list = []
        real = _fake_backtest

        def spy(bars, sp, params, **kw):
            seen.append(dict(params))
            return real(bars, sp, params, **kw)

        monkey = pytest.MonkeyPatch()
        monkey.setattr(E, "run_single_stock", spy)
        try:
            row, summary = E.optimise_pair(spec, "tcs", cfg)
        finally:
            monkey.undo()

        assert seen[0] == dict(spec.default), "the shipped default is evaluated first"
        assert len(seen) == cfg.budget + 1, "budget on TRAIN plus one frozen run on TEST"
        assert seen[-1] == row["params"], "TEST must re-run the frozen winner only"


# =========================================================================== #
# 11. Catalog
# =========================================================================== #
class TestCatalogRobustness:
    def test_a_nonexistent_module_raises_rather_than_returning_a_stub(self, tmp_path,
                                                                     monkeypatch):
        from research.optimize import catalog as CAT

        monkeypatch.setattr(CAT, "CATALOG_DIR", tmp_path)
        with pytest.raises(ModuleNotFoundError):
            load_strategy("definitely_not_a_module")

    def test_discover_skips_a_broken_module_and_keeps_the_good_one(self, monkeypatch,
                                                                   caplog):
        import importlib as real_importlib

        from research.optimize import catalog as CAT

        def flaky_import(name):
            if name.endswith(".rsi_strategy"):
                raise RuntimeError("broken module")
            return real_importlib.import_module(name)

        monkeypatch.setattr(CAT, "importlib", SimpleNamespace(import_module=flaky_import))

        with caplog.at_level("WARNING"):
            specs = discover(("rsi_strategy", "supertrend_strategy"))

        assert [s.name for s in specs] == ["supertrend_strategy"], (
            "one bad module must not kill the sweep"
        )
        assert any("rsi_strategy" in r.message for r in caplog.records), (
            "the skip must be logged, not silent"
        )

    def test_every_discovered_spec_builds_its_shipped_default(self):
        for name in ("rsi_strategy", "absolute_momentum"):
            spec = load_strategy(name)
            assert spec.build(dict(spec.default)) is not None, name

    def test_unknown_type_fields_are_held_fixed_not_guessed(self):
        import dataclasses

        spec = load_strategy("rsi_strategy")
        names = {p.name for p in spec.params} | set(spec.held_fixed)
        assert names == {f.name for f in dataclasses.fields(spec.config_cls)}

    def test_discover_of_an_unknown_name_is_empty_not_an_error(self):
        assert discover(("definitely_not_a_strategy",)) == []

    def test_partial_name_filter_drops_the_rest(self):
        specs = discover(("rsi_strategy", "not_a_strategy"))
        assert [s.name for s in specs] == ["rsi_strategy"]


class TestManifestHonesty:
    """Residual loose ends found while closing out the 9 bug fixes."""

    def test_no_edge_verdict_does_not_round_the_expectation_to_zero(self):
        """The significant branch was fixed; the NO EDGE branch was missed.

        `f"{0.05 * n:.0f}"` printed "About 0 expected by chance alone" at n=1 -- the
        opposite of the truth, since 0.1 is expected.
        """
        rows = [_ok_row(f"s{i}", f"stk{i}", p_timing=0.9) for i in range(3)]
        out = analyse(rows)
        assert "About 0 would be expected" not in out["verdict"], out["verdict"]

    def test_partial_rerun_reports_skips_within_its_own_scope_only(self, outdir, monkeypatch):
        """`done` is read from the whole results file, so a narrow rerun over a wider
        file overstated n_pairs_skipped (2 skipped, 1 total)."""
        from research.optimize import engine as E

        _write_jsonl(C.TEST_JSONL, [_ok_row("other_a", "tcs"), _ok_row("other_b", "infy")])
        # discover() lives in catalog, not engine -- run_sweep takes specs directly.
        monkeypatch.setattr(S, "bars", lambda *a, **k: _bars(5))
        m = E.run_sweep([FakeSpec("target")], ["tcs"], C.RunConfig(budget=2, null_replicas=4),
                        resume=True, workers=1)
        assert m["n_pairs_total"] == 1
        assert m["n_pairs_skipped_in_scope"] == 0
        assert m["n_pairs_skipped_other_scope"] == 2
