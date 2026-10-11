"""Data-cleaning tests — `reports/DATA_AUDIT.md` §5 rules C1-C9.

The dataset shipped with 58 unadjusted split artifacts concentrated in 2002-2007. If
these rules regress, the backtest silently becomes meaningless, so each rule gets a
dedicated test built from synthetic frames that reproduce the exact defect.
"""

from __future__ import annotations

import os

import numpy as np
import pandas as pd
import pytest

from nsealgo.data.loader import (
    CLEAN_START,
    FROZEN_RUN_MIN,
    MAX_ABS_RETURN,
    CleaningReport,
    DataIntegrityError,
    load_symbol,
    load_universe,
)


def write_csv(tmp_path, name: str, rows: list[tuple]) -> str:
    df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol"])
    path = tmp_path / name
    df.to_csv(path, index=False)
    return str(path)


def ts(year, month, day, hour=0):
    return int(pd.Timestamp(f"{year}-{month:02d}-{day:02d}", tz="Asia/Kolkata")
               .tz_convert("UTC").timestamp() * 1000)


class TestC1Pre2008:
    def test_pre_2008_rows_are_dropped(self, tmp_path) -> None:
        rows = [
            (ts(2005, 1, 1), 10, 11, 9, 10.0, 100),
            (ts(2010, 1, 1), 10, 11, 9, 10.5, 100),
            (ts(2011, 1, 1), 10, 11, 9, 11.0, 100),
        ]
        p = write_csv(tmp_path, "AAA_1d.csv", rows)
        out = load_symbol(p, "AAA")
        assert out.index.min() >= CLEAN_START
        assert len(out) == 2


class TestC2ArtifactDates:
    def test_2005_artifact_dates_removed(self, tmp_path) -> None:
        rows = [
            (ts(2008, 1, 1), 10, 11, 9, 10.0, 100),
            (ts(2005, 7, 28), 10, 11, 9, 100.0, 100),
            (ts(2005, 7, 29), 10, 11, 9, 10.0, 100),
            (ts(2009, 1, 1), 10, 11, 9, 12.0, 100),
        ]
        p = write_csv(tmp_path, "BBB_1d.csv", rows)
        out = load_symbol(p, "BBB")
        dates = {str(d.date()) for d in out.index}
        assert "2005-07-28" not in dates
        assert "2005-07-29" not in dates


class TestC4NonPositivePrices:
    def test_nonpositive_prices_dropped_never_filled(self, tmp_path) -> None:
        rows = [
            (ts(2008, 1, 1), 10, 11, 9, 10.0, 100),
            (ts(2009, 1, 1), -0.01, -0.01, -0.01, -0.01, 100),   # adanient-style
            (ts(2010, 1, 1), 10, 11, 9, 11.0, 100),
        ]
        p = write_csv(tmp_path, "CCC_1d.csv", rows)
        out = load_symbol(p, "CCC")
        assert len(out) == 2
        assert (out[["open", "high", "low", "close"]] > 0).all().all()

    def test_nan_price_dropped(self, tmp_path) -> None:
        path = tmp_path / "DDD_1d.csv"
        pd.DataFrame(
            [(ts(2008, 1, 1), 10, 11, 9, 10.0, 100),
             (ts(2009, 1, 1), np.nan, np.nan, np.nan, np.nan, 100),
             (ts(2010, 1, 1), 10, 11, 9, 11.0, 100)],
            columns=["ts", "open", "high", "low", "close", "vol"],
        ).to_csv(path, index=False)
        out = load_symbol(str(path), "DDD")
        assert len(out) == 2


class TestC5ExtremeMoves:
    def test_impossible_daily_move_dropped(self, tmp_path) -> None:
        """A -92.6% single-day move cannot happen in a daily-limit market.

        We assert the *invariant* (no impossible move survives) rather than an exact
        row count, because removing the artifact also makes the rebound out of it look
        extreme, and single-pass cleaning drops both. That residual over-deletion is a
        deliberate trade-off — see the C5 comment in `loader.py` and the crash test
        below, which pins the behaviour that must NOT change.
        """
        rows = [
            (ts(2010, 1, 1), 100, 101, 99, 100.0, 100),
            (ts(2010, 2, 1), 100, 101, 99, 7.4, 100),     # -92.6% -> impossible
            (ts(2010, 3, 1), 100, 101, 99, 105.0, 100),
        ]
        p = write_csv(tmp_path, "EEE_1d.csv", rows)
        out = load_symbol(p, "EEE")
        assert 7.4 not in set(out["close"].tolist()), "the corrupt price must be gone"
        remaining = out["close"].pct_change().abs().dropna()
        assert (remaining <= MAX_ABS_RETURN).all(), "no impossible move may survive"

    def test_genuine_crash_is_not_eaten_by_cascading_cleans(self, tmp_path) -> None:
        """Regression, and the most dangerous data bug this project has had.

        An earlier iterative implementation (drop -> recompute -> repeat) removed an
        artifact row and then treated every subsequent day of a REAL crash as another
        extreme return, because the stale earlier price was still the reference. It
        deleted bajajfinsv's entire 2008 collapse (60 rows). Deleting real drawdowns
        silently flatters MaxDD, which is exactly what GOAL.md §6 forbids.
        """
        # A sustained crash: each day -8% off the previous. All plausible; none may go.
        px = 100.0
        rows = []
        for d in pd.date_range("2008-01-01", periods=12, freq="MS", tz="Asia/Kolkata"):
            px *= 0.92
            rows.append((int(d.tz_convert("UTC").timestamp() * 1000),
                         px, px, px, px, 100))
        p = write_csv(tmp_path, "CRASH_1d.csv", rows)
        out = load_symbol(p, "CRASH")
        assert len(out) == len(rows), "a real crash must survive cleaning intact"
        assert out["close"].is_monotonic_decreasing

    def test_realistic_large_move_is_kept(self, tmp_path) -> None:
        """A -35% day is plausible (COVID-era, pre-filter 2008). Must NOT be dropped —
        over-cleaning would flatter the drawdown and hide real risk."""
        rows = [
            (ts(2010, 1, 1), 100, 101, 99, 100.0, 100),
            (ts(2010, 2, 1), 100, 101, 65, 65.0, 100),    # -35%
            (ts(2010, 3, 1), 66, 69, 64, 68.0, 100),     # +4.6%, fine
        ]
        p = write_csv(tmp_path, "FFF_1d.csv", rows)
        out = load_symbol(p, "FFF")
        assert len(out) == 3


class TestC6Integrity:
    def test_duplicate_timestamps_raise(self, tmp_path) -> None:
        rows = [
            (ts(2009, 1, 1), 10, 11, 9, 10.0, 100),
            (ts(2009, 1, 1), 10, 11, 9, 10.0, 100),
        ]
        p = write_csv(tmp_path, "GGG_1d.csv", rows)
        with pytest.raises(DataIntegrityError, match="duplicate"):
            load_symbol(p, "GGG")

    def test_missing_column_raises(self, tmp_path) -> None:
        path = tmp_path / "HHH_1d.csv"
        pd.DataFrame([(ts(2009, 1, 1), 10, 11, 9, 100)],
                     columns=["ts", "open", "high", "low", "vol"]).to_csv(path, index=False)
        with pytest.raises(DataIntegrityError, match="missing columns"):
            load_symbol(str(path), "HHH")

    def test_unsorted_input_is_sorted(self, tmp_path) -> None:
        rows = [
            (ts(2010, 1, 1), 10, 11, 9, 11.0, 100),
            (ts(2008, 1, 1), 10, 11, 9, 10.0, 100),
            (ts(2009, 1, 1), 10, 11, 9, 10.5, 100),
        ]
        p = write_csv(tmp_path, "III_1d.csv", rows)
        out = load_symbol(p, "III")
        assert out.index.is_monotonic_increasing


class TestC9FrozenCloses:
    """C9 — a vendor feed that stops updating repeats its last close verbatim.

    C5 only catches moves that are too LARGE, so a run of exactly zero returns
    survived every previous rule and poisoned each 200d/252d window that overlapped
    it. Measured on the real panel: nestleind had 214 + 279 consecutive frozen
    closes (2008-01-01 -> 2010-01-07 at Rs 433) and bajajauto 46.
    """

    @staticmethod
    def _series(closes: list[float]) -> list[tuple]:
        rows = []
        for i, px in enumerate(closes):
            d = pd.Timestamp("2010-01-01", tz="Asia/Kolkata") + pd.Timedelta(days=i)
            rows.append((int(d.tz_convert("UTC").timestamp() * 1000), px, px, px, px, 1000))
        return rows

    def test_frozen_run_is_cleaned_at_known_length(self, tmp_path) -> None:
        """10 repeated bars in a 40-bar series must go, and only they.

        The frozen level is 109.0 and it appears nowhere else in the series, so the
        assertion that 109.0 is *absent* from the output is exact: not one frozen
        print survives.
        """
        closes = [100.0 + i for i in range(10)]           # 100..109
        closes += [109.0] * 10                             # the freeze (10 repeats)
        closes += [110.0 + i for i in range(20)]           # 110..129
        p = write_csv(tmp_path, "FRZ_1d.csv", self._series(closes))

        rep = CleaningReport()
        out = load_symbol(p, "FRZ", rep)

        assert 109.0 not in set(out["close"].tolist()), "no frozen print may survive"
        # The run is 11 bars wide: the 10 repeats PLUS the last genuine bar, whose
        # close the freeze started from. C9 drops the whole run, anchor included,
        # so that no bar at the frozen level remains.
        assert rep.dropped_frozen == 11
        assert len(out) == len(closes) - 11
        assert rep.frozen_log[0][3] == 11, "logged run length must be the full run"

    def test_frozen_rows_are_dropped_never_interpolated(self, tmp_path) -> None:
        """C4 holds for C9: the void stays a void, it is never back-filled."""
        closes = [100.0 + i for i in range(10)]
        closes += [109.0] * 10
        closes += [110.0 + i for i in range(20)]
        p = write_csv(tmp_path, "FRZ2_1d.csv", self._series(closes))
        out = load_symbol(p, "FRZ2")

        gap = out.loc["2010-01-10":"2010-01-20", "close"]
        assert gap.isna().all() or gap.empty, "no synthetic price may fill the freeze"

    def test_legitimate_flat_bars_are_not_over_cleaned(self, tmp_path) -> None:
        """A limit-lock day, an illiquid flat day and a 4-bar chain are REAL data.

        The measured run-length distribution has nothing between 4 and 46 bars, so
        a 4-bar chain is the longest genuine cluster in the dataset and must survive
        intact. Over-cleaning here would destroy real market data to catch a defect.
        """
        closes = [
            100.0, 101.0,
            101.0,                      # single flat bar (run of 2)
            102.0, 103.0,
            103.0,                      # another single flat bar
            104.0,
            105.0, 105.0, 105.0, 105.0,  # 4-bar limit-lock chain (run of 4)
            106.0, 107.0, 107.0,        # flat again
            108.0, 109.0,
        ]
        p = write_csv(tmp_path, "FLAT_1d.csv", self._series(closes))
        rep = CleaningReport()
        out = load_symbol(p, "FLAT", rep)

        assert len(out) == len(closes), "genuine flat bars must survive"
        assert rep.dropped_frozen == 0
        assert rep.frozen_log == []
        assert out["close"].tolist() == closes

    @pytest.mark.parametrize(
        ("run_len", "expect_dropped"),
        [
            (FROZEN_RUN_MIN - 1, 0),      # 4 — the longest legitimate cluster seen
            (FROZEN_RUN_MIN, FROZEN_RUN_MIN),
            (FROZEN_RUN_MIN + 1, FROZEN_RUN_MIN + 1),
        ],
    )
    def test_threshold_boundary(self, tmp_path, run_len, expect_dropped) -> None:
        """C9 fires at exactly FROZEN_RUN_MIN and not one bar below it.

        The bar before the run carries a different close, so the run of identical
        closes is exactly ``run_len`` bars wide.
        """
        closes = [100.0, 101.0] + [102.0] * run_len + [103.0, 104.0, 105.0]
        p = write_csv(tmp_path, f"THR{run_len}_1d.csv", self._series(closes))

        rep = CleaningReport()
        out = load_symbol(p, f"THR{run_len}", rep)

        assert rep.dropped_frozen == expect_dropped
        assert len(out) == len(closes) - expect_dropped

    def test_freeze_does_not_cascade_into_c5(self, tmp_path) -> None:
        """Removing a freeze must not turn into deleting the real crash behind it.

        This is the C5 single-pass failure mode all over again: drop an artifact and
        a genuine move can look impossible. C9 runs after C5 and never re-triggers
        it, so a real 30% collapse that happens to sit after a freeze must survive.
        """
        closes = [100.0, 101.0, 102.0]
        closes += [102.0] * 8                       # freeze
        closes += [71.4, 70.0, 68.5]                # genuine -30% collapse
        p = write_csv(tmp_path, "CASC_1d.csv", self._series(closes))

        rep = CleaningReport()
        out = load_symbol(p, "CASC", rep)

        assert rep.dropped_frozen == 9              # 8 repeats + the 102.0 anchor
        assert rep.dropped_extreme == 0, "C5 must not fire on the survivors"
        assert 71.4 in set(out["close"].tolist()), "the real collapse must survive"

    def test_report_counter_and_log_increment(self, tmp_path) -> None:
        closes = [100.0, 101.0, 102.0]
        closes += [102.0] * 8
        closes += [103.0, 104.0]
        p = write_csv(tmp_path, "RPT_1d.csv", self._series(closes))

        rep = CleaningReport()
        load_symbol(p, "RPT", rep)

        assert rep.dropped_frozen == 9
        assert len(rep.frozen_log) == 1
        sym, first, last, length, level = rep.frozen_log[0]
        assert (sym, length, level) == ("RPT", 9, 102.0)
        assert (first, last) == ("2010-01-03", "2010-01-11")

        s = rep.summary()
        assert s["dropped_frozen"] == 9
        assert s["n_frozen_runs"] == 1
        assert s["frozen_symbols"] == ["RPT"]
        assert "dropped frozen" in rep.describe()

    def test_counter_accumulates_across_symbols(self, tmp_path) -> None:
        """`load_universe` merges per-symbol reports; the counter must add up."""
        closes = [100.0, 101.0, 102.0] + [102.0] * 8 + [103.0, 104.0]
        for name in ("AAA", "BBB"):
            write_csv(tmp_path, f"{name}_1d.csv", self._series(closes))

        _, _, rep = load_universe(str(tmp_path), min_bars=1)

        assert rep.dropped_frozen == 18
        assert rep.frozen_symbols == ["AAA", "BBB"]
        assert rep.summary()["n_frozen_runs"] == 2

    def test_clean_series_reports_nothing(self, tmp_path) -> None:
        """No false positives on a series with no freeze at all."""
        closes = [100.0 + i for i in range(30)]
        p = write_csv(tmp_path, "CLEAN_1d.csv", self._series(closes))
        rep = CleaningReport()
        out = load_symbol(p, "CLEAN", rep)
        assert len(out) == 30
        assert rep.dropped_frozen == 0
        assert rep.frozen_symbols == []


class TestUniverseLoading:
    def _make_universe(self, tmp_path, n: int = 3, days: int = 2000) -> None:
        start = pd.Timestamp("2010-01-01", tz="Asia/Kolkata")
        for s in range(n):
            rows = []
            for i in range(days):
                d = start + pd.Timedelta(days=i)
                px = 100.0 + i * 0.01 + s
                rows.append((int(d.tz_convert("UTC").timestamp() * 1000),
                             px, px + 1, px - 1, px, 1000))
            write_csv(tmp_path, f"SYM{s}_1d.csv", rows)

    def test_loads_multiple_symbols(self, tmp_path) -> None:
        self._make_universe(tmp_path, n=4)
        panel, syms, rep = load_universe(str(tmp_path))
        assert len(syms) >= 3
        assert panel.shape[1] == 4
        assert rep.rows_out > 0

    def test_excluded_symbol_is_skipped(self, tmp_path) -> None:
        self._make_universe(tmp_path, n=3)
        panel, syms, rep = load_universe(str(tmp_path), exclude=frozenset({"SYM0"}))
        assert "SYM0" not in syms
        assert "SYM0" in rep.excluded_symbols

    def test_short_history_symbol_dropped(self, tmp_path) -> None:
        self._make_universe(tmp_path, n=2)
        rows = [(ts(2020, 1, i + 1), 100, 101, 99, 100.0, 10) for i in range(5)]
        write_csv(tmp_path, "SHORT_1d.csv", rows)
        panel, syms, _ = load_universe(str(tmp_path), min_bars=100)
        assert "SHORT" not in syms

    def test_empty_directory_raises(self, tmp_path) -> None:
        with pytest.raises(DataIntegrityError, match="no usable symbols"):
            load_universe(str(tmp_path))

    def test_report_is_auditable(self, tmp_path) -> None:
        self._make_universe(tmp_path, n=2)
        _, _, rep = load_universe(str(tmp_path))
        s = rep.summary()
        assert "rows_in" in s and "rows_dropped" in s
        assert "CLEANING REPORT" in rep.describe()


#: The real dataset is ~68MB of OHLCV CSVs and is deliberately gitignored, so these
#: run wherever the data is mounted (dev host, the research/nsealgo containers) and
#: skip on a clean CI checkout. The audit itself is reproducible via
#: `research/audit_data.py`; see reports/DATA_AUDIT.md.
REAL_DATA = os.path.join(os.environ.get("NSE_DATA", "data/nse"), "asianpaint_1d.csv")
requires_real_data = pytest.mark.skipif(
    not os.path.exists(REAL_DATA),
    reason=f"real dataset not mounted at {REAL_DATA} (68MB, gitignored)",
)


@requires_real_data
class TestRealDataset:
    """Checks against the actual shipped data — the regression net for the audit."""

    def test_real_data_loads_and_is_clean(self) -> None:
        panel, syms, rep = load_universe("data/nse")
        assert len(syms) >= 40, "Gate 1 requires >= 40 usable symbols"
        assert panel.index.min().year >= 2008, "C1 must exclude pre-2008"
        vals = panel.to_numpy()
        assert np.nanmin(vals[np.isfinite(vals)]) > 0, \
            "C4: no non-positive prices remain"
        assert not panel.index.has_duplicates

    def test_real_data_has_enough_history(self) -> None:
        panel, syms, _ = load_universe("data/nse")
        long_books = (panel.notna().sum() / 244) >= 15
        assert long_books.sum() >= 40, "Gate 1 requires >= 40 symbols with 15+ years"

    def test_no_artifact_survives(self) -> None:
        _, _, rep = load_universe("data/nse")
        assert rep.dropped_artifact == 0, "artifacts should already be pre-2008"

    def test_no_frozen_run_survives(self) -> None:
        """C9 regression net against the real panel.

        A vendor re-fetch that reintroduces a freeze must fail here rather than
        silently reach a rolling window.
        """
        panel, _, rep = load_universe("data/nse")
        assert rep.dropped_frozen > 0, "the shipped dataset is known to contain freezes"

        worst = 0
        for sym in panel.columns:
            closes = panel[sym].dropna().to_numpy()
            if closes.size < 2:
                continue
            new_run = np.empty(closes.size, dtype=bool)
            new_run[0] = True
            np.not_equal(closes[1:], closes[:-1], out=new_run[1:])
            run_len = np.bincount(np.cumsum(new_run) - 1)
            worst = max(worst, int(run_len.max()))
        assert worst < FROZEN_RUN_MIN, (
            f"a run of {worst} identical closes survived cleaning; "
            f"C9 must cap every run below {FROZEN_RUN_MIN}"
        )
