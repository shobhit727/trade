"""Batch 3 -- agents whose harness is a single guarded script rather than a library.

Every `run.py` here sits behind `if __name__ == "__main__":`, so importing it runs no
experiment; it only binds functions and constants. Each agent's score builder is then
called with the variant that agent's own `results.json` records as selected on TRAIN.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_all as R  # noqa: E402
from agentlib import load  # noqa: E402
from core import panel  # noqa: E402

PX = panel()


@R.reg("dual_ma", "V5_5_20")
def _dma(a):
    m = load(a, "run")
    return m.dma_score(PX, 5, 20), "M"


@R.reg("ema_cross", "V2_5_20")
def _ec(a):
    m = load(a, "run")
    return m.ema_cross_score(PX, 5, 20), "M"


@R.reg("ensemble", "V2_10_14_2")
def _ens(a):
    m = load(a, "run")
    return m.ensemble_score(PX, 10, 14, 2), "M"


@R.reg("hull_ma", "V2_10")
def _hull(a):
    m = load(a, "run")
    return m.hull_score(PX, 10), "M"


@R.reg("kama", "V2_10")
def _kama(a):
    m = load(a, "run")
    return m.kama_score(PX, 10), "M"


@R.reg("macd", "V3_5_20_9")
def _macd(a):
    m = load(a, "run")
    return m.macd_score(PX, 5, 20, 9), "M"


@R.reg("trendmom", "V3")
def _tm(a):
    m = load(a, "run")
    v = m.VARIANTS["V3"]
    return m.tm_score(PX, v), "M"


@R.reg("triple_ma", "V1_5_15_30")
def _tma(a):
    m = load(a, "run")
    return m.tma_score(PX, 5, 15, 30), "M"


if __name__ == "__main__":
    R.main()
