"""Data loading and cleaning for NSE daily bars.

Implements the mandatory cleaning plan from `reports/DATA_AUDIT.md` §5.
No backtest may run on unclean data (`GOAL.md` §5 Gate 1).

Cleaning rules (binding):
  C1  restrict to 2008-01-01 .. latest        (2002-07 slice is poisoned, see audit)
  C2  drop 2005-07-28 and 2005-07-29          (12-symbol systematic artifact)
  C3  exclude corrupt symbols (adanient)      (47 non-positive prices)
  C4  drop non-positive price rows, never ffill
  C5  drop surviving |return| > 45% days, and log them
  C6  assert no dupes / NaN close / non-monotonic ts
  C7  emit an auditable CleaningReport
  C9  drop frozen closes (vendor feed freeze), and log the affected runs
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #

#: C1 — first date we are willing to backtest.
CLEAN_START = pd.Timestamp("2008-01-01", tz="Asia/Kolkata")

#: C2 — the two-day 12-symbol artifact.
ARTIFACT_DATES: frozenset[pd.Timestamp] = frozenset(
    pd.Timestamp(d, tz="Asia/Kolkata") for d in ("2005-07-28", "2005-07-29")
)

#: C3 — symbols with structural corruption in the raw files.
EXCLUDE_SYMBOLS: frozenset[str] = frozenset({"adanient"})

#: C5 — a surviving daily move beyond this is not market data, it is a glitch.
MAX_ABS_RETURN = 0.45

#: C9 — a run of at least this many *identical consecutive closes* is a vendor feed
#: freeze, not market data.
#:
#: C5 only catches moves that are too LARGE. It cannot see a vendor that stops
#: updating and simply repeats yesterday's close, which produces a run of exactly
#: zero returns. Those bars silently poison every 200d/252d rolling window, every
#: volatility estimate, and every momentum lookback that overlaps them.
#:
#: The threshold is taken from the *measured* run-length distribution over all 50
#: symbols after C1-C8 (211,951 runs, 213,628 bars), not guessed:
#:
#:     run len        n_runs    mean zero-volume share
#:         1         210,811    0.000
#:         2           1,133    0.226
#:       3-4              4    0.250
#:      5-19              0        -
#:     20-49              1    0.978
#:   200-499              2    1.000
#:
#: Two things make this defensible rather than arbitrary:
#:
#: 1. There is a hard EMPTY GAP: no run of length 5-19 exists anywhere in the
#:    dataset, while the longest legitimate cluster is 4. Every threshold in
#:    [5, 46] therefore produces byte-identical output on this data.
#: 2. Zero volume corroborates independently and monotonically. Short runs never
#:    exceed 25% zero-volume bars; long runs are 98-100% zero-volume. A real
#:    limit-lock session still trades; a frozen feed does not.
#:
#: We pick 5 — the *smallest* value above the longest legitimate cluster. That is
#: the conservative side of the gap: it keeps the maximum amount of genuine data
#: while still catching every freeze observed. Picking 46 (or 50) would delete the
#: same rows today but would silently fail on a shorter freeze that this sample
#: happens not to contain.
FROZEN_RUN_MIN = 5

OHLCV = ["open", "high", "low", "close", "vol"]


class DataIntegrityError(RuntimeError):
    """Raised when a dataset fails a hard integrity assertion (C6)."""


# --------------------------------------------------------------------------- #


@dataclass
class CleaningReport:
    """Audit trail of what cleaning did. `GOAL.md` §6.6 requires reproducibility."""

    rows_in: int = 0
    rows_out: int = 0
    dropped_pre_2008: int = 0
    dropped_artifact: int = 0
    dropped_nonpositive: int = 0
    dropped_extreme: int = 0
    dropped_frozen: int = 0
    excluded_symbols: list[str] = field(default_factory=list)
    extreme_log: list[tuple[str, str, float]] = field(default_factory=list)
    #: (symbol, first date, last date, run length, frozen close) per frozen run.
    frozen_log: list[tuple[str, str, str, int, float]] = field(default_factory=list)

    def merge(self, other: CleaningReport) -> None:
        self.rows_in += other.rows_in
        self.rows_out += other.rows_out
        self.dropped_pre_2008 += other.dropped_pre_2008
        self.dropped_artifact += other.dropped_artifact
        self.dropped_nonpositive += other.dropped_nonpositive
        self.dropped_extreme += other.dropped_extreme
        self.dropped_frozen += other.dropped_frozen
        self.excluded_symbols.extend(other.excluded_symbols)
        self.extreme_log.extend(other.extreme_log)
        self.frozen_log.extend(other.frozen_log)

    @property
    def rows_dropped(self) -> int:
        return self.rows_in - self.rows_out

    @property
    def frozen_symbols(self) -> list[str]:
        return sorted({sym for sym, *_ in self.frozen_log})

    def summary(self) -> dict[str, object]:
        return {
            "rows_in": self.rows_in,
            "rows_out": self.rows_out,
            "rows_dropped": self.rows_dropped,
            "dropped_pre_2008": self.dropped_pre_2008,
            "dropped_artifact": self.dropped_artifact,
            "dropped_nonpositive": self.dropped_nonpositive,
            "dropped_extreme": self.dropped_extreme,
            "dropped_frozen": self.dropped_frozen,
            "excluded_symbols": sorted(set(self.excluded_symbols)),
            "n_extreme_events": len(self.extreme_log),
            "n_frozen_runs": len(self.frozen_log),
            "frozen_symbols": self.frozen_symbols,
        }

    def describe(self) -> str:
        s = self.summary()
        return (
            f"CLEANING REPORT\n"
            f"  rows in            : {s['rows_in']:>9,}\n"
            f"  rows out           : {s['rows_out']:>9,}\n"
            f"  dropped pre-2008   : {s['dropped_pre_2008']:>9,}\n"
            f"  dropped artifact   : {s['dropped_artifact']:>9,}\n"
            f"  dropped non-positive: {s['dropped_nonpositive']:>6,}\n"
            f"  dropped extreme    : {s['dropped_extreme']:>9,}\n"
            f"  dropped frozen     : {s['dropped_frozen']:>9,}\n"
            f"  frozen runs        : {s['n_frozen_runs']:>9,}"
            f"  in {s['frozen_symbols']}\n"
            f"  excluded symbols   : {s['excluded_symbols']}\n"
            f"  extreme events     : {s['n_extreme_events']}\n"
        )


# --------------------------------------------------------------------------- #


def _assert_integrity(df: pd.DataFrame, symbol: str) -> None:
    """C6 — post-clean structural checks (ts already consumed; date index is the key)."""
    if df.index.has_duplicates:
        n = int(df.index.duplicated().sum())
        raise DataIntegrityError(f"{symbol}: {n} duplicate dates")
    if df["close"].isna().any():
        raise DataIntegrityError(f"{symbol}: {int(df['close'].isna().sum())} NaN closes")
    if not df.index.is_monotonic_increasing:
        raise DataIntegrityError(f"{symbol}: date index not monotonic")


def _run_ids(values: np.ndarray) -> np.ndarray:
    """Id of the maximal run of identical consecutive values each entry belongs to.

    Runs are numbered 0, 1, 2, ... in time order, so `np.bincount(run_ids)` gives
    the length of every run. Requires ``values.size >= 1``.

    Exact float equality is deliberate. A tolerance would merge merely *similar*
    prices (which are different observations) and would make the audit trail
    depend on an arbitrary epsilon; exact repeats are unambiguous evidence.
    """
    new_run = np.empty(values.size, dtype=bool)
    new_run[0] = True
    np.not_equal(values[1:], values[:-1], out=new_run[1:])
    return np.cumsum(new_run) - 1


def load_symbol(
    path: str, symbol: str, report: CleaningReport | None = None
) -> pd.DataFrame:
    """Load one daily CSV and apply C1-C9. Returns tz-aware, indexed-by-date frame."""
    rep = report or CleaningReport()

    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"ts", *OHLCV} - set(df.columns)
    if missing:
        raise DataIntegrityError(f"{symbol}: missing columns {sorted(missing)}")

    rep.rows_in += len(df)
    df = df[["ts", *OHLCV]].copy()
    df["ts"] = df["ts"].astype("int64")
    df = df.sort_values("ts").reset_index(drop=True)

    # ---- C6 (early): structural checks on the raw epoch column, before we
    # discard it. Fail loudly rather than silently backtest on garbage.
    if df["ts"].duplicated().any():
        raise DataIntegrityError(
            f"{symbol}: {int(df['ts'].duplicated().sum())} duplicate timestamps"
        )
    if not df["ts"].is_monotonic_increasing:
        raise DataIntegrityError(f"{symbol}: timestamps not monotonic")

    # ---- C4: drop non-positive / NaN prices. Never forward-fill.
    ohlc = df[["open", "high", "low", "close"]]
    bad = (ohlc.isna().any(axis=1)) | (ohlc <= 0).any(axis=1)
    n_bad = int(bad.sum())
    if n_bad:
        df = df.loc[~bad].reset_index(drop=True)
        rep.dropped_nonpositive += n_bad

    df["date"] = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert(
        "Asia/Kolkata"
    )
    df["date"] = df["date"].dt.normalize()
    df = df.drop(columns="ts").set_index("date")

    # ---- C1: pre-2008 is unusable (audit §4.2)
    pre = df.index < CLEAN_START
    n_pre = int(pre.sum())
    if n_pre:
        df = df.loc[~pre]
        rep.dropped_pre_2008 += n_pre

    # ---- C2: artifact dates
    art = df.index.isin(ARTIFACT_DATES)
    n_art = int(art.sum())
    if n_art:
        df = df.loc[~art]
        rep.dropped_artifact += n_art

    if df.empty:
        rep.rows_out += 0
        return df

    # ---- C5: residual extreme moves.
    #
    # SINGLE PASS, deliberately. An earlier version iterated (drop, recompute, repeat)
    # to avoid deleting the neighbour of a corrupt print. That was a serious mistake:
    # when one artifact row was removed, every subsequent day in a genuine crash became
    # a >45% return against the *stale* earlier price, so the loop ate the whole 2008
    # collapse (60 rows from bajajfinsv alone). Deleting real drawdowns is precisely
    # the failure mode `GOAL.md` §6 forbids, and it flatters MaxDD.
    #
    # The trade-off we accept: an artifact leaves its neighbours looking extreme, so
    # a handful of contaminated rows survive. Residual artifacts are logged in
    # `CleaningReport.extreme_log` and disclosed in `reports/DATA_AUDIT.md` §5.3.
    # Under-cleaning is recoverable and visible; over-cleaning is silent and fatal.
    ret = df["close"].pct_change()
    extreme = (ret.abs() > MAX_ABS_RETURN).fillna(False)
    n_ext = int(extreme.sum())
    if n_ext:
        for idx in df.index[extreme]:
            rep.extreme_log.append((symbol, str(idx.date()), float(ret.loc[idx])))
        df = df.loc[~extreme]
        rep.dropped_extreme += n_ext

    df = df.sort_index()

    # ---- C9: frozen closes (vendor feed freeze).
    #
    # A vendor that stops updating repeats its last close verbatim, giving a run of
    # exactly zero returns. C5 cannot see this — zero is not "extreme" — so the bars
    # survive every other rule and quietly poison rolling windows, volatility
    # estimates and momentum lookbacks that overlap them.
    #
    # We DROP the whole run rather than interpolating it. `GOAL.md` C4 forbids
    # inventing prices, and for this defect interpolation could not help anyway:
    # nestleind's frozen level (433.07) was roughly 4x the true price on the first
    # real bar after the freeze (102.74 on 2010-01-11) — the vendor was carrying a
    # stale pre-corporate-action price, so no amount of smoothing recovers it.
    #
    # C9 deliberately runs AFTER C5 and is NOT allowed to re-trigger it. Removing a
    # freeze makes the two surviving neighbours adjacent, and the genuine crash that
    # was hidden behind the frozen level then shows up as one large return (bajajauto
    # -42.4% on 2008-05-26). That return is REAL and must survive: re-running C5
    # would delete it and flatter MaxDD, which is the exact failure C5's single-pass
    # design already exists to prevent (see the crash regression test).
    if len(df) >= FROZEN_RUN_MIN:
        close = df["close"].to_numpy()
        run_id = _run_ids(close)
        run_len = np.bincount(run_id)
        frozen = run_len[run_id] >= FROZEN_RUN_MIN
        n_frozen = int(frozen.sum())
        if n_frozen:
            for rid in np.flatnonzero(run_len >= FROZEN_RUN_MIN):
                pos = np.flatnonzero(run_id == rid)
                rep.frozen_log.append(
                    (
                        symbol,
                        str(df.index[pos[0]].date()),
                        str(df.index[pos[-1]].date()),
                        int(run_len[rid]),
                        float(close[pos[0]]),
                    )
                )
            df = df.loc[~frozen]
            rep.dropped_frozen += n_frozen

    _assert_integrity(df, symbol)
    rep.rows_out += len(df)
    if report is not None:
        report.merge(rep) if report is not rep else None
    return df


def load_universe(
    data_dir: str | None = None,
    exclude: frozenset[str] | None = None,
    min_bars: int = 1000,
) -> tuple[pd.DataFrame, list[str], CleaningReport]:
    """Load every ``*_1d.csv`` into a wide close panel.

    Returns
    -------
    (panel, symbols, report)
        ``panel`` is a DataFrame indexed by date with one column per symbol (close).
        ``symbols`` is the tradable universe actually retained.
    """
    data_dir = data_dir or os.environ.get("NSE_DATA", "data/nse")
    exclude = EXCLUDE_SYMBOLS if exclude is None else exclude

    report = CleaningReport()
    series: dict[str, pd.Series] = {}
    dropped: list[str] = []

    for fname in sorted(os.listdir(data_dir)):
        if not fname.endswith("_1d.csv"):
            continue
        symbol = fname[: -len("_1d.csv")]
        if symbol in exclude:
            dropped.append(symbol)
            continue
        local = CleaningReport()
        try:
            df = load_symbol(os.path.join(data_dir, fname), symbol, local)
        except DataIntegrityError:
            dropped.append(symbol)
            continue
        if len(df) < min_bars:
            dropped.append(symbol)
            continue
        series[symbol] = df["close"].rename(symbol)
        report.merge(local)

    report.excluded_symbols.extend(dropped)

    if not series:
        raise DataIntegrityError("no usable symbols found")

    panel = pd.DataFrame(series).sort_index()
    # C4 again at panel level: a symbol can be NaN on dates others are not.
    panel = panel.dropna(how="all")

    # ---- C8: drop non-trading days.
    #
    # A handful of raw CSVs carry a stray weekend bar (e.g. 2010-02-06, a Saturday).
    # Each one lands as an interior NaN in every other symbol's column, so every
    # rolling/ewm indicator is wrong for `period` bars after that hole -- silently,
    # because the loader's C6 check only validates *within* each symbol.
    #
    # The NSE does not trade Saturday or Sunday, so any such index entry is a vendor
    # artefact. Drop them outright rather than carrying interior holes into factors.
    weekend = panel.index.dayofweek >= 5
    if weekend.any():
        panel = panel.loc[~weekend]

    # Belt-and-braces: drop any remaining date with implausibly thin coverage.
    coverage = panel.notna().mean(axis=1)
    sparse = coverage < 0.05
    if sparse.any():
        panel = panel.loc[~sparse]

    return panel, list(panel.columns), report


def load_returns(panel: pd.DataFrame) -> pd.DataFrame:
    """Daily simple returns of the close panel."""
    return panel.pct_change(fill_method=None)
