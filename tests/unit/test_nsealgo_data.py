"""Data-cleaning tests — `reports/DATA_AUDIT.md` §5 rules C1-C7.

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
    MAX_ABS_RETURN,
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
