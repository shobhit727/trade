"""v1 reference numbers, read-only, for the diff tables.

`reports/CONTROL_DIAGNOSTIC.md` (v1) was computed on engine `d93815344bd3` and its
underlying per-book results are still on disk under `research/_control_diag/`. Those are
the authoritative v1 values — full float precision, not the 2-decimal rounding the report
prints — so the diff tables are computed from them rather than transcribed by hand.

Nothing here is ever *reused as a result*. These numbers exist only to be subtracted
from the v2 numbers. Where a v2 number is unchanged, the diff table says so and points at
the measurement that explains why (see `research/revalidate_v2/tie_invariance.py`).

`reports/STRESS_v3.md` has **no** cache on disk, so its numbers are transcribed into
`STRESS_V3` below, each carrying the report section it came from. They are read from the
report and not re-derived, which is stated in `STRESS_v4.md` rather than hidden.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
V1_CACHE = REPO / "research" / "_control_diag"

V1_ENGINE = "d93815344bd3"
V2_ENGINE = "29764f562cd5"


def _s(name: str) -> dict:
    return json.loads((V1_CACHE / f"summary_{name}.json").read_text())


def v1_control() -> dict:
    """Every v1 control-diagnostic number, at full precision, from the v1 cache."""
    return {
        "provenance": _s("h1")["provenance"],
        "h1": _s("h1"),
        "h2": _s("h2"),
        "h3": _s("h3"),
        "h4": _s("h4"),
        "h5": _s("h5"),
        "h6": _s("h6"),
        "extras": _s("extras"),
    }


def v1_control_verdicts() -> dict[str, str]:
    """The six verdicts as v1 printed them, for a literal verdict-diff table."""
    h1, h2, h3, h4, h5, h6 = (_s(k) for k in ("h1", "h2", "h3", "h4", "h5", "h6"))
    by = {r["component"]: r for r in h2["components"]}
    nolv = by["control_no_lowvol"]
    h3_on = h3["with_overlay"]["sharpe_gap_ctrl_minus_prod"]
    h3_off = h3["no_overlay"]["sharpe_gap_ctrl_minus_prod"]
    b, t = h4["bootstrap"], h4["ttest"]
    wins = sum(1 for tag in ("cell_A", "cell_B")
               if h5["fixed"][tag]["PRODUCTION"]["cagr"]
               > h5["fixed"][tag]["CONTROL_REVERSAL"]["cagr"])
    c = h6["scramble_c"]
    return {
        "H1": ("SUPPORTED on the decisive comparison, and the net numbers understate "
               "how badly" if h1["prod_pct_gross"] < 0.60 else "SUPPORTED"),
        "H2": ("SUPPORTED — reversal legs carry the control, not low-vol"
               if nolv["cagr"] > h2["production"]["cagr"] else "REFUTED"),
        "H3": ("SUPPORTED — overlay flips the sign"
               if (h3_on > 0) != (h3_off > 0) else "REFUTED"),
        "H4": ("SUPPORTED — indistinguishable"
               if b["d_cagr_ci_lo"] < 0 < b["d_cagr_ci_hi"] and t["p_newey_west"] > 0.05
               else "REFUTED — difference is measurable"),
        "H5": ("SUPPORTED — selection artifact" if wins == 0
               else "REFUTED — production wins fixed cells without selection"),
        "H6": ("SUPPORTED — no signal separates it from its own scramble"
               if c["prod_pct_cagr"] < 0.75 and c["prod_pct_sharpe"] < 0.75
               else "REFUTED — signal survives the scramble"),
    }


# --------------------------------------------------------------------------- #
# reports/STRESS_v3.md — transcribed, no cache exists on disk
# --------------------------------------------------------------------------- #

#: Every headline figure `reports/STRESS_v3.md` prints, with the section it came from.
#: Values are the report's own printed precision — that is what a reader of v3 saw.
STRESS_V3: dict = {
    "_source": "reports/STRESS_v3.md (transcribed; the script keeps no result cache)",
    "_engine_stamped_in_footer": "970713f3eecf",
    "_engine_that_produced_these_numbers": "d93815344bd3",
    "baseline": {  # §0
        "cagr": 0.0971, "sharpe": 0.34, "maxdd": -0.1492, "calmar": 0.65,
        "bm_cagr": 0.1712, "bm_sharpe": 0.68, "bm_maxdd": -0.3797,
        "turnover": 1.9964, "cost_drag": 0.061692, "avg_names": 21.9,
    },
    "folds": [  # §0 details block
        (1, "2024-10-18", "2026-10-01", (22, 126, 0.35), -0.0080, -0.85, -0.1059),
        (2, "2022-10-25", "2024-10-17", (22, 126, 0.60), 0.2880, 1.68, -0.0753),
        (3, "2020-11-04", "2022-10-24", (22, 126, 0.60), 0.1322, 0.57, -0.1177),
        (4, "2018-11-09", "2020-11-03", (15, 126, 0.00), 0.0135, -0.42, -0.1492),
        (5, "2016-11-22", "2018-11-07", (15, 126, 0.35), 0.1316, 0.71, -0.1162),
        (6, "2014-11-26", "2016-11-21", (30, 126, 0.60), 0.0508, -0.07, -0.1124),
    ],
    "slip": {  # §1 — (slip_bps, cagr, sharpe, maxdd)
        5: (0.0971, 0.34, -0.1492),
        10: (0.0925, 0.30, -0.1496),
        15: (0.0879, 0.26, -0.1499),
    },
    "slip_alpha_cagr": {5: -0.0741, 10: -0.0787, 15: -0.0833},  # §1
    "perturb": {  # §2 — label -> (cagr, sharpe, maxdd)
        "mom_long 244->195 (-20%)": (0.1014, 0.38, -0.1492),
        "mom_long 244->293 (+20%)": (0.0931, 0.30, -0.1741),
        "mom_skip 21->17 (-20%)": (0.1019, 0.37, -0.1785),
        "mom_skip 21->25 (+20%)": (0.0964, 0.33, -0.1584),
        "mom_6m 126->101 (-20%)": (0.0980, 0.34, -0.1751),
        "mom_6m 126->151 (+20%)": (0.0975, 0.34, -0.1605),
        "trend_lb 200->160 (-20%)": (0.0867, 0.25, -0.1582),
        "trend_lb 200->240 (+20%)": (0.0976, 0.34, -0.1492),
        "vol_lb 60->48 (-20%)": (0.0890, 0.26, -0.1492),
        "vol_lb 60->72 (+20%)": (0.0938, 0.31, -0.1492),
        "overlay lookback x0.80 (-20%)": (0.0849, 0.23, -0.2194),
        "overlay lookback x1.20 (+20%)": (0.0911, 0.28, -0.1820),
        "overlay threshold x0.80 (-20%)": (0.0982, 0.35, -0.1492),
        "overlay threshold x1.20 (+20%)": (0.0971, 0.33, -0.1492),
    },
    "yearly": {  # §3 — year -> share of total P&L
        2014: 0.0012, 2015: 0.0147, 2016: 0.0377, 2017: 0.1591, 2018: -0.0037,
        2019: 0.0738, 2020: -0.0582, 2021: 0.1517, 2022: 0.0362, 2023: 0.2583,
        2024: 0.3580, 2025: 0.1209, 2026: -0.1497,
    },
    "max_year": (0.3580, 2024),  # §3
    "per_stock_top1": (0.0801, "trent"),  # §4
    "per_stock_top5_share": 0.2793,  # §4
    "total_net_stock_pnl": 1.0357,  # §4
    "cash_leg": 0.1420,  # §4
    "neighbours": {  # §5 — label -> (cagr, sharpe, maxdd)
        "mom_6m 126->101 (-20%)": (0.0980, 0.34, -0.1751),
        "mom_6m 126->151 (+20%)": (0.0975, 0.34, -0.1605),
        "trend_lb 200->160 (-20%)": (0.0867, 0.25, -0.1582),
        "trend_lb 200->240 (+20%)": (0.0976, 0.34, -0.1492),
        "overlay lookback x0.80 (-20%)": (0.0849, 0.23, -0.2194),
        "overlay lookback x1.20 (+20%)": (0.0911, 0.28, -0.1820),
    },
    "fixed_grid": {  # §5 supplementary — (n, lb, thr) -> (cagr, sharpe, maxdd)
        (15, 126, 0.00): (0.0928, 0.30, -0.1492), (15, 126, 0.35): (0.0936, 0.30, -0.2147),
        (15, 126, 0.60): (0.0935, 0.29, -0.2611), (15, 252, 0.00): (0.0802, 0.19, -0.1780),
        (15, 252, 0.35): (0.0853, 0.23, -0.2157), (15, 252, 0.60): (0.0883, 0.24, -0.2611),
        (22, 126, 0.00): (0.1043, 0.41, -0.1615), (22, 126, 0.35): (0.1101, 0.45, -0.2211),
        (22, 126, 0.60): (0.1136, 0.45, -0.2635), (22, 252, 0.00): (0.0947, 0.31, -0.1701),
        (22, 252, 0.35): (0.1037, 0.38, -0.2211), (22, 252, 0.60): (0.1096, 0.41, -0.2635),
        (30, 126, 0.00): (0.1009, 0.38, -0.1787), (30, 126, 0.35): (0.1070, 0.42, -0.2380),
        (30, 126, 0.60): (0.1108, 0.43, -0.2801), (30, 252, 0.00): (0.0884, 0.26, -0.1787),
        (30, 252, 0.35): (0.0988, 0.35, -0.2380), (30, 252, 0.60): (0.1056, 0.39, -0.2801),
    },
    "control": {  # §6
        "cagr": 0.1004, "sharpe": 0.37, "maxdd": -0.2505,
    },
    "gates": {  # §7 / verdict table
        "G4.1 slippage": "PASS", "G4.2 perturbation": "PASS",
        "G4.3 no year > 35%": "FAIL", "G4.4 no stock > 20%": "PASS",
        "G4.5 >= 4/6 neighbours": "PASS", "X turnover/drag": "PASS",
        "X negative control": "FAIL",
    },
    "c9": {  # §0 C9 attribution block
        "pre_c9_turnover": 1.9913, "pre_c9_drag": 0.059297,
        "pre_c9_insample_cagr": 0.1663, "pre_c9_oos_cagr": 0.0971,
        "pre_c9_oos_sharpe": 0.3365,
        "c9_turnover": 1.9964, "c9_drag": 0.061692,
        "c9_insample_cagr": 0.1687, "c9_oos_cagr": 0.0971,
        "c9_oos_sharpe": 0.3365,
    },
}
