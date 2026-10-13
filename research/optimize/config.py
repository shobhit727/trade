"""Static configuration for the per-stock optimisation sweep.

Everything that is a *fact about the world* (capital, fees, tax) lives here so that a
sweep can be reproduced from one file. Anything that is a *choice about the experiment*
(budget, seeds, rebalance frequency) is a CLI flag and defaults here.

Deliberate design notes
-----------------------
* **Capital is per stock.** We optimise one stock at a time, so the book is one name.
  It still sizes with the equity so that percentage costs (STT, stamp) are realistic
  rather than the flat-charges-dominated regime of a tiny account.
* **Tax is on by default.** The prior validation chain was entirely pre-tax, which
  understated a short-holding Indian equity book by roughly 2-4%/yr. See TODO.md.
* **Slippage is separate from the statutory stack** because the gate-4 stress test
  treats it as the tunable variable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal as D
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data" / "nse"
OUT_DIR = Path(__file__).resolve().parent / "out"
LOG_DIR = REPO / "logs"

# --------------------------------------------------------------------------- #
# Capital
# --------------------------------------------------------------------------- #
#: Per-stock book size. Confirmed as Rs 21,00,000, matching GOAL.md.
CAPITAL_INR = D("2100000")

# --------------------------------------------------------------------------- #
# Cost stack (statutory, per round trip, bps of turnover)
# --------------------------------------------------------------------------- #
#: Matches ``nsealgo.costs.CostModel.round_trip_bps`` for a delivery account:
#: STT 10bps + exchange txn 0.307bps + SEBI 0.10bps + stamp 3.00bps + DP ~0.52bps
#: + 18% GST on (brokerage + txn + SEBI). Zerodha charges zero brokerage on delivery.
STATUTORY_BPS = D("11.92")

#: Adverse slippage per side, in bps. Base 5bps is what every prior result used.
SLIPPAGE_BPS = D("5")

#: A complete round trip pays slippage on both legs.
ALL_IN_ROUND_TRIP_BPS = STATUTORY_BPS + SLIPPAGE_BPS * 2  # 21.92

# --------------------------------------------------------------------------- #
# Capital gains tax (Indian, FY2025-26 onward)
# --------------------------------------------------------------------------- #
#: Short-term: holding period <= 365 days.
STCG_RATE = D("0.20")
#: Long-term: holding period > 365 days.
LTCG_RATE = D("0.125")
#: Boundary in calendar days. <= 365 is short-term.
LTCG_THRESHOLD_DAYS = 365

#: NSE delivery accounts cannot go short. A bearish signal goes to cash, not to -1x.
ALLOW_SHORT = False

# --------------------------------------------------------------------------- #
# Walk-forward windows (hard-coded, never selected against)
# --------------------------------------------------------------------------- #
TRAIN_START = "2016-01-01"
TRAIN_END = "2023-12-31"
TEST_START = "2024-01-01"
TEST_END = "2026-10-01"

#: First date with usable cleaned data. Mirrors loader rule C1.
CLEAN_START = "2008-01-01"

# --------------------------------------------------------------------------- #
# Search space defaults
# --------------------------------------------------------------------------- #
#: Configs evaluated per (strategy, stock) pair, including the shipped default.
DEFAULT_BUDGET = 40

#: Master seed. Every per-pair seed derives from this plus (strategy, stock) so that
#: any single pair can be reproduced in isolation and the whole sweep is resumable.
MASTER_SEED = 20261013

#: Null-model replicas per pair. Enough to estimate an empirical p-value below 1/N.
DEFAULT_NULL_REPLICAS = 200

#: Benjamini-Hochberg false-discovery-rate threshold for the survival headline.
FDR_ALPHA = 0.05

#: Trading days per year for annualisation.
TRADING_DAYS = 244


@dataclass(frozen=True)
class FeeSchedule:
    """Per-round-trip fee in bps, resolved for a given slippage setting."""

    slippage_bps: D = SLIPPAGE_BPS
    statutory_bps: D = STATUTORY_BPS

    @property
    def round_trip_bps(self) -> D:
        return self.statutory_bps + self.slippage_bps * 2

    @property
    def one_way_bps(self) -> D:
        return self.round_trip_bps / 2


@dataclass(frozen=True)
class RunConfig:
    """Everything one sweep run needs. Built by ``run.py`` from CLI flags."""

    budget: int = DEFAULT_BUDGET
    null_replicas: int = DEFAULT_NULL_REPLICAS
    workers: int = 8
    rebalance: str = "M"
    tax_enabled: bool = True
    seed: int = MASTER_SEED
    strategies: tuple[str, ...] = field(default_factory=tuple)
    stocks: tuple[str, ...] = field(default_factory=tuple)

    def fees(self, slippage_bps: D | None = None) -> FeeSchedule:
        return FeeSchedule(slippage_bps=slippage_bps or SLIPPAGE_BPS)


# --------------------------------------------------------------------------- #
# Output paths
# --------------------------------------------------------------------------- #
RESULTS_JSONL = OUT_DIR / "results.jsonl"
TEST_JSONL = OUT_DIR / "test_results.jsonl"
NULLS_JSONL = OUT_DIR / "nulls.jsonl"
SUMMARY_JSON = OUT_DIR / "summary.json"
ANALYZE_MD = OUT_DIR / "analyze.md"
MANIFEST_JSON = OUT_DIR / "manifest.json"


def ensure_dirs() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
