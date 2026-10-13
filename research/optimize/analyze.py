"""Analysis: how many pairs beat their OWN null, after FDR correction.

The headline this file is built to produce is **not** a leaderboard.

We measured, in the cross-sectional harness, that 100 of 100 random 22-name books were
profitable (mean +8.59%/yr). Against a null that generous, the maximum of any number of
trials looks spectacular by construction. Here that is 84 strategies x 50 stocks = 4,200
trials, plus a parameter search inside each one.

So the questions asked are, in order:

1. How many pairs beat their **own** timing null at q < 0.05 (Benjamini-Hochberg)?
2. How many beat their own **buy-and-hold**?
3. How many clear **both**, and how large is their alpha?
4. How concentrated is the result -- if everything passes for one stock, that is a
   property of the stock, not of the strategies.
5. Is any single pair significant once multiplicity is priced in?

A "yes" to (1) is the precondition for believing anything. Without it, (2)-(5) are noise
with a nice decimal point.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict

import numpy as np

from . import config as C

log = logging.getLogger(__name__)


def load_rows(path=None) -> list[dict]:
    path = path or C.TEST_JSONL
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("stage") == "test" and r.get("ok"):
                rows.append(r)
    return rows


def benjamini_hochberg(pvals: list[float], alpha: float = C.FDR_ALPHA) -> np.ndarray:
    """Return a boolean array: True where the hypothesis is significant at ``alpha``.

    Standard BH step-up. Returns False everywhere if no p-value clears.
    """
    n = len(pvals)
    if n == 0:
        return np.zeros(0, dtype=bool)
    p = np.asarray(pvals, dtype=float)
    order = np.argsort(p)
    ranked = p[order]
    thresh = (np.arange(1, n + 1) / n) * alpha
    passed = ranked <= thresh
    if not passed.any():
        out = np.zeros(n, dtype=bool)
        return out
    cutoff = np.max(np.where(passed)[0])
    sig = np.zeros(n, dtype=bool)
    sig[order[: cutoff + 1]] = True
    return sig


def analyse(rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else load_rows()
    out: dict = {
        "n_pairs": len(rows),
        "n_failed_candidates_total": sum(r.get("n_failed_candidates", 0) for r in rows),
    }
    if not rows:
        out["error"] = f"no completed pairs in {C.TEST_JSONL}"
        return out

    cagr = np.array([r["test"]["cagr"] for r in rows])
    alpha_bh = np.array([r["alpha_vs_buy_hold"] for r in rows])
    p_timing = np.array([r["p_timing"] for r in rows])
    p_params = np.array([r["p_params"] for r in rows])
    maxyr = np.array([r.get("test_max_year_share", 0.0) for r in rows])
    exposure = np.array([r["test"]["exposure"] for r in rows])
    tax = np.array([r.get("total_tax_test", 0.0) for r in rows])

    sig_t = benjamini_hochberg(p_timing.tolist())
    sig_p = benjamini_hochberg(p_params.tolist())
    beats_bh = alpha_bh > 0
    both = sig_t & beats_bh

    out.update({
        "fdr_alpha": C.FDR_ALPHA,
        "n_significant_vs_timing_null": int(sig_t.sum()),
        "n_significant_vs_params_null": int(sig_p.sum()),
        "n_beats_buy_hold": int(beats_bh.sum()),
        "n_significant_and_beats_bh": int(both.sum()),
        "pct_significant": round(100.0 * sig_t.sum() / len(rows), 3),
        "expected_false_positives_at_alpha": round(C.FDR_ALPHA * len(rows), 1),
        "cagr": _desc(cagr),
        "sharpe": _desc(np.array([r["test"]["sharpe"] for r in rows])),
        "alpha_vs_bh": _desc(alpha_bh),
        "exposure": _desc(exposure),
        "total_tax_inr": _desc(tax),
    })

    by_stock: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_stock[r["stock"]].append(r)
    stock_alpha = {
        s: float(np.mean([x["alpha_vs_buy_hold"] for x in v])) for s, v in by_stock.items()
    }
    best_stocks = sorted(stock_alpha.items(), key=lambda kv: -kv[1])[:10]
    out["best_stocks_mean_alpha"] = [
        {"stock": s, "mean_alpha": round(a, 4)} for s, a in best_stocks
    ]
    out["n_stocks_with_positive_mean_alpha"] = sum(1 for a in stock_alpha.values() if a > 0)
    out["n_stocks"] = len(by_stock)

    by_strat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_strat[r["strategy"]].append(r)
    strat_alpha = {
        s: float(np.mean([x["alpha_vs_buy_hold"] for x in v])) for s, v in by_strat.items()
    }
    out["best_strategies_mean_alpha"] = [
        {"strategy": s, "mean_alpha": round(a, 4)}
        for s, a in sorted(strat_alpha.items(), key=lambda kv: -kv[1])[:10]
    ]
    out["n_strategies_with_positive_mean_alpha"] = sum(
        1 for a in strat_alpha.values() if a > 0
    )
    out["n_strategies"] = len(by_strat)

    out["concentration"] = {
        "n_pairs_with_max_year_share_gt_35pct": int((maxyr > 0.35).sum()),
        "median_max_year_share": round(float(np.median(maxyr)), 4),
        "goalmd_year_gate": 0.35,
    }
    out["verdict"] = _verdict(out)
    return out


def _desc(a: np.ndarray) -> dict:
    if a.size == 0:
        return {}
    return {
        "mean": round(float(a.mean()), 4),
        "median": round(float(np.median(a)), 4),
        "p10": round(float(np.percentile(a, 10)), 4),
        "p90": round(float(np.percentile(a, 90)), 4),
        "min": round(float(a.min()), 4),
        "max": round(float(a.max()), 4),
    }


def _verdict(out: dict) -> str:
    n, sig = out["n_pairs"], out["n_significant_vs_timing_null"]
    if n == 0:
        return "NO DATA - run the sweep first."
    if sig == 0:
        return (
            f"NO EDGE. 0 of {n} pairs beat their own timing null at FDR q<{C.FDR_ALPHA}. "
            f"About {C.FDR_ALPHA * n:.0f} would be expected by chance alone. Nothing here "
            "survives multiple-testing correction, so no pair may be deployed or quoted."
        )
    return (
        f"{sig} of {n} pairs ({100 * sig / n:.2f}%) beat their own timing null at "
        f"q<{C.FDR_ALPHA}, against ~{C.FDR_ALPHA * n:.0f} expected by chance. "
        f"{out['n_significant_and_beats_bh']} of those also beat their own stock's "
        f"buy-and-hold. Read the per-pair table before quoting any of them."
    )


def write_report(out: dict) -> str:
    lines = [
        "# Per-stock sweep — analysis",
        "",
        f"**Headline: {out.get('verdict', 'no data')}**",
        "",
        "| | |",
        "|---|---|",
        f"| pairs completed | {out.get('n_pairs')} |",
        f"| strategies x stocks | {out.get('n_strategies')} x {out.get('n_stocks')} |",
        f"| beat own timing null (FDR q<{C.FDR_ALPHA}) | **{out.get('n_significant_vs_timing_null')}** |",
        f"| expected by chance | ~{out.get('expected_false_positives_at_alpha')} |",
        f"| beat own stock's buy-and-hold | {out.get('n_beats_buy_hold')} |",
        f"| significant AND beats buy-and-hold | {out.get('n_significant_and_beats_bh')} |",
        f"| stocks with positive mean alpha | {out.get('n_stocks_with_positive_mean_alpha')} / {out.get('n_stocks')} |",
        f"| strategies with positive mean alpha | {out.get('n_strategies_with_positive_mean_alpha')} / {out.get('n_strategies')} |",
        "",
        "## Distribution",
        "",
        "| metric | mean | median | p10 | p90 | min | max |",
        "|---|---|---|---|---|---|---|",
    ]
    for label, key in (("TEST CAGR", "cagr"), ("alpha vs buy&hold", "alpha_vs_bh"),
                       ("exposure", "exposure"), ("CGT paid (Rs)", "total_tax_inr")):
        d = out.get(key) or {}
        if d:
            lines.append(
                f"| {label} | {d['mean']} | {d['median']} | {d['p10']} | {d['p90']} | "
                f"{d['min']} | {d['max']} |"
            )
    lines += ["", "## Concentration (GOAL.md Gate 4 caps one year at 35%)", "",
              f"- pairs exceeding the year cap: **{out.get('concentration', {}).get('n_pairs_with_max_year_share_gt_35pct')}**",
              f"- median largest-year share: {out.get('concentration', {}).get('median_max_year_share')}", ""]

    lines += ["## Best stocks by mean alpha", "", "| stock | mean alpha |", "|---|---|"]
    for r in out.get("best_stocks_mean_alpha", []):
        lines.append(f"| {r['stock']} | {r['mean_alpha']:+.4f} |")
    lines += ["", "## Best strategies by mean alpha", "", "| strategy | mean alpha |", "|---|---|"]
    for r in out.get("best_strategies_mean_alpha", []):
        lines.append(f"| {r['strategy']} | {r['mean_alpha']:+.4f} |")

    lines += [
        "",
        "---",
        "",
        "**This file deliberately reports no leaderboard of the single best pair.** With "
        f"{out.get('n_pairs')} trials against a null that is generous by construction, the "
        "maximum is not informative. Read the counts above first.",
        "",
    ]
    text = "\n".join(lines)
    C.ANALYZE_MD.parent.mkdir(parents=True, exist_ok=True)
    C.ANALYZE_MD.write_text(text, encoding="utf-8")
    return text

def main() -> int:  # noqa: D103
    out = analyse()
    write_report(out)
    print(out.get("verdict", "NO DATA"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
