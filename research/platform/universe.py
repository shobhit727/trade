"""Point-in-time NIFTY-50 universe for the NSE research track (audit F-009).

A backtest that selects from today's fixed 50-name list flatters an equal-weight
construction by +8.94 pp/yr of CAGR over 2008-2026 (survivorship; see
``reports/DATA_GAP_ASSESSMENT.md``). This module exposes the index membership
*as it was known at a given date*, so a strategy can only select names that had
already joined.

Single source of parsing
------------------------
The membership matrix is parsed exclusively by ``tools/pit_membership.py``
(``load_membership``), the same loader the sweep harness uses. This module adds
the platform-facing query surface on top; it never re-reads or re-parses the
CSV itself. The tools directory is put on ``sys.path`` exactly like
``research/sweep/harness.py`` does.

Data
----
``data/nse_membership/nifty50_monthly_membership.csv`` (long format
``date,symbol,source``; ~10,950 rows, 104 distinct symbols), built by
``tools/build_pit_membership.py`` from ``reconstructed_github`` and independent
``wayback`` snapshot sources. The CSV is data: it lives outside version
control (gitignored) and is read at query time, never copied into the package.

Conventions (no look-ahead)
---------------------------
* Membership recorded at a month-end is effective *from that month-end*
  onward: ``universe_at(d)`` returns the set recorded at the last month-end
  ``<= d``. Selecting with this set can never admit a name before its recorded
  joining month-end (the sweep harness additionally lags to the prior
  month-end at selection time; querying a month's first day here yields the
  same lagged set).
* Rows dated on non-month-end days (intraday rebalance records such as
  2009-01-12 or 2019-08-27) never leak in early: the loader keys the dense
  matrix by month-ends only, so a name recorded mid-month first appears at
  that month's month-end.
* 45 of the 219 source month-ends between 2008-01 and 2026-10 have no records
  (several are rebalance months). They are enumerated in
  ``data/nse_membership/membership_meta.json`` and listed here:

  2008-03-31, 2008-09-30, 2009-03-31, 2009-06-30, 2009-08-31, 2009-09-30,
  2010-03-31, 2010-09-30, 2011-03-31, 2011-09-30, 2012-03-31, 2014-02-28,
  2014-03-31, 2014-09-30, 2015-03-31, 2015-05-31, 2015-09-30, 2016-03-31,
  2017-03-31, 2017-05-31, 2017-09-30, 2018-03-31, 2019-03-31, 2019-08-31,
  2019-09-30, 2020-03-31, 2020-08-31, 2020-09-30, 2023-06-30, 2024-02-29,
  2024-03-31, 2024-09-30, 2025-03-31, 2025-09-30, 2025-10-31, 2025-11-30,
  2025-12-31, 2026-01-31, 2026-02-28, 2026-03-31, 2026-04-30, 2026-05-31,
  2026-06-30, 2026-07-31, 2026-09-30

  A month-end absent from the source inherits the prior recorded month-end's
  set (the loader's documented forward-fill). This is deliberate: a missing
  month must not be read as "every name left the index".
* 2025-09 through 2026-08 is served entirely by forward-fill from the last
  verified 2025-08 snapshot. The loader marks it ``INFERRED``; downstream
  reports must disclose it.
* Four names are known-unobtainable from available sources and bias the
  universe optimistically: SATYAMCOMP, VSNL, MCDOWELLN, STER.

Query policy
------------
Dates outside the recorded coverage (before 2008-01-31, after 2026-10-31)
raise ``ValueError`` — an explicit failure is preferred over silently serving
an empty or extrapolated universe.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd

from .domain import Market

__all__ = ["PITUniverse", "members_range", "membership_csv_path", "universe_at"]

_MEMBERSHIP_RELPATH = Path("data") / "nse_membership" / "nifty50_monthly_membership.csv"


def membership_csv_path() -> Path:
    """Locate the membership CSV by walking up from this module.

    Worktree checkouts do not carry the gitignored ``data/`` tree, so the file
    must be resolved against the repository root found from ``__file__``, never
    against the current working directory (the loader's default path is
    cwd-relative and only works when the process runs at the repo root).
    """
    for ancestor in Path(__file__).resolve().parents:
        candidate = ancestor / _MEMBERSHIP_RELPATH
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"membership CSV not found in any ancestor of {Path(__file__).resolve()}; "
        f"expected {_MEMBERSHIP_RELPATH} — build it with `python tools/build_pit_membership.py`"
    )


def _load_membership(csv_path: Path | str | None = None):
    """Import the shared loader and build the dense month-end x symbol matrix."""
    path = Path(csv_path).resolve() if csv_path is not None else membership_csv_path()
    tools_dir = path.parents[3] / "tools"
    if not (tools_dir / "pit_membership.py").exists():
        # Fall back to this module's own repository root (checkout layouts may differ).
        tools_dir = Path(__file__).resolve().parents[2] / "tools"
    tools_str = str(tools_dir)
    if tools_str not in sys.path:
        sys.path.insert(0, tools_str)
    from pit_membership import load_membership  # noqa: E402  (repo-root tools/, see harness.py)

    return load_membership(str(path))


class PITUniverse:
    """Queryable point-in-time NIFTY-50 membership for the NSE track."""

    market = Market.NSE

    def __init__(self, csv_path: Path | str | None = None) -> None:
        self._membership = _load_membership(csv_path)

    @property
    def coverage(self) -> tuple[pd.Timestamp, pd.Timestamp]:
        """First and last month-end covered by the loaded membership history."""
        m = self._membership
        return m.start, m.end

    def universe_at(self, when: date | str | pd.Timestamp) -> frozenset[str]:
        """Index members exactly as known at ``when`` — no look-ahead.

        Returns the set recorded at the last month-end on or before ``when``
        (forward-filled across the 45 missing source month-ends). Raises
        ``ValueError`` outside the covered range.
        """
        return frozenset(self._membership.members(when))

    def members_range(
        self, start: date | str | pd.Timestamp, end: date | str | pd.Timestamp
    ) -> list[tuple[pd.Timestamp, frozenset[str]]]:
        """(month-end, members) pairs for every month-end in ``[start, end]``.

        Inclusive on both ends; the first returned date is the first month-end
        on or after ``start`` and the last is the last month-end on or before
        ``end``, so the dates are contiguous calendar month-ends. Raises
        ``ValueError`` if the interval is inverted or escapes coverage.
        """
        m = self._membership
        first, last = pd.Timestamp(start), pd.Timestamp(end)
        if first > last:
            raise ValueError(f"start {first.date()} is after end {last.date()}")
        if first < m.start or last > m.end:
            raise ValueError(
                f"[{first.date()}, {last.date()}] is outside membership coverage "
                f"[{m.start.date()}, {m.end.date()}]"
            )
        index = m.table.index
        lo = int(index.searchsorted(first, side="left"))
        hi = int(index.searchsorted(last, side="right"))
        return [(index[i], self.universe_at(index[i])) for i in range(lo, hi)]


_DEFAULT_UNIVERSE: PITUniverse | None = None


def _default_universe() -> PITUniverse:
    global _DEFAULT_UNIVERSE
    if _DEFAULT_UNIVERSE is None:
        _DEFAULT_UNIVERSE = PITUniverse()
    return _DEFAULT_UNIVERSE


def universe_at(when: date | str | pd.Timestamp) -> frozenset[str]:
    """Point-in-time NIFTY-50 members at ``when`` from the shared universe."""
    return _default_universe().universe_at(when)


def members_range(
    start: date | str | pd.Timestamp, end: date | str | pd.Timestamp
) -> list[tuple[pd.Timestamp, frozenset[str]]]:
    """Contiguous month-end membership pairs from the shared universe."""
    return _default_universe().members_range(start, end)
