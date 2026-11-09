"""Step 00 — load the cleaned NSE daily panel and persist it.

Mandatory first step from the brief. Nothing is downloaded; everything is on disk.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "src")

import pandas as pd

from nsealgo.data.loader import load_universe

SCRATCH = "research/agent_keltner"
pd.set_option("display.width", 200)

panel, symbols, report = load_universe("data/nse")

print("=" * 78)
print("LOAD_UNIVERSE REPORT")
print("=" * 78)
print(report.describe())
print()

print("panel shape :", panel.shape)
print("index       :", panel.index.min(), "->", panel.index.max())
print("n symbols   :", len(symbols))
print("first 10    :", list(symbols)[:10])
print()

print("coverage per symbol (bars) — summary")
cov = panel.notna().sum()
print(cov.describe())
print()
print("symbols with < 1000 bars:")
print(cov[cov < 1000].to_string())
print()

print("NA fraction overall:", float(panel.isna().mean().mean()))
print("non-positive prices:", int(panel[panel > 0].isna().sum().sum()))
print()

print("train rows :", int(((panel.index >= "2016-01-01") & (panel.index <= "2023-12-31")).sum()))
print("test  rows :", int(((panel.index >= "2024-01-01") & (panel.index <= "2026-10-01")).sum()))
print()

panel.to_pickle(f"{SCRATCH}/panel.pkl")
with open(f"{SCRATCH}/symbols.txt", "w") as fh:
    fh.write("\n".join(symbols))

print(f"wrote {SCRATCH}/panel.pkl  shape={panel.shape}")

# --------------------------------------------------------------------------- #
# Data provenance.
#
# `BacktestResult.engine_sha` hashes `backtest/engine.py` ONLY. It says nothing
# about the LOADER, the COST MODEL or the panel itself -- and in this repo the
# loader gained an uncommitted rule (C9, frozen closes) mid-study that removed 539
# bars. A frozen close has near-zero true range, which shrinks ATR and inflates
# Keltner band depth: exactly the input this strategy is most sensitive to.
#
# So record a content hash of the panel itself. Any agent re-running this must be
# able to prove which data produced its numbers.
# --------------------------------------------------------------------------- #
import hashlib  # noqa: E402

import nsealgo.data.loader as _L  # noqa: E402

loader_sha = hashlib.sha256(
    open(_L.__file__, "rb").read()
).hexdigest()[:12]
panel_sha = hashlib.sha256(
    pd.util.hash_pandas_object(panel, index=True).values.tobytes()
).hexdigest()[:12]

print("=" * 78)
print("DATA PROVENANCE")
print("=" * 78)
print(f"loader module      : {_L.__file__}")
print(f"loader source sha  : {loader_sha}")
print(f"panel shape        : {panel.shape}")
print(f"panel content sha  : {panel_sha}")
print(f"rows in/out        : {report.rows_in:,} / {report.rows_out:,}")
if hasattr(report, "dropped_frozen"):
    print(f"dropped frozen (C9): {report.dropped_frozen:,} in {report.frozen_symbols}")
    print(f"frozen runs        : {len(report.frozen_log)}")
with open(f"{SCRATCH}/data_provenance.json", "w") as fh:
    import json

    json.dump(
        {
            "loader_path": _L.__file__,
            "loader_sha": loader_sha,
            "panel_shape": list(panel.shape),
            "panel_sha": panel_sha,
            "index_min": str(panel.index.min()),
            "index_max": str(panel.index.max()),
            "rows_in": int(report.rows_in),
            "rows_out": int(report.rows_out),
            "dropped_frozen": int(getattr(report, "dropped_frozen", 0)),
            "frozen_symbols": list(getattr(report, "frozen_symbols", [])),
            "n_frozen_runs": len(getattr(report, "frozen_log", [])),
        },
        fh,
        indent=2,
    )
print(f"wrote {SCRATCH}/data_provenance.json")
