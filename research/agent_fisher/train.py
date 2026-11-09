"""TRAIN-only sweep over the 5 declared variants. TEST is not touched here."""

from __future__ import annotations

import json

import pandas as pd
from common import TRAIN, bt, fisher_score, fmt, load, slice_metrics, window_diag

VARIANTS = [
    ("V1", 10, 0.50),
    ("V2", 20, 0.50),
    ("V3", 10, 1.00),
    ("V4", 20, 1.00),
    ("V5", 5, 1.50),
]


def signal_purity(result, sig, panel) -> float:
    """Share of book weight sitting in names the Fisher signal flags +1 *that day*.

    Quantifies how much of the held book is actually the strategy's idea versus
    turnover-budget residue from earlier picks.
    """
    w = result.weights
    flagged = (sig > 0).reindex(w.index).fillna(False)
    return float((w.where(flagged, 0.0).sum(axis=1) / w.sum(axis=1)).mean())


def main() -> None:
    panel, _symbols = load()
    rows = []
    for name, period, entry in VARIANTS:
        score, sig = fisher_score(panel, period, entry)
        res = bt(panel, score)
        gross = bt(panel, score, zero_cost=True)
        m = slice_metrics(res.equity, res.returns, *TRAIN)
        dg = window_diag(res, *TRAIN, gross_result=gross)
        purity = signal_purity(res, sig, panel)
        n_flag = float(score.notna().sum(axis=1).mean())
        live = float((sig > 0).to_numpy().mean())
        rows.append(
            {
                "variant": name, "period": period, "entry": entry,
                "cagr": m.cagr, "sharpe": m.sharpe, "max_dd": m.max_drawdown,
                "calmar": m.calmar, "total": m.total_return, "vol": m.volatility,
                "gross_cagr": None,
                **{k: v for k, v in dg.items()},
                "flagged_names_per_day": n_flag,
                "frac_bars_long": live,
                "signal_purity": purity,
            }
        )
        print(fmt(m, f"{name} p{period}/e{entry}"))
        print(
            f"{'':22} turnover {dg['annual_turnover']:.2f}x/y  "
            f"costDrag {dg['cost_drag_annual']*100:.2f}%/y  "
            f"names(all/material) {dg['avg_names']:.1f}/{dg['avg_material_names']:.1f}  "
            f"bookwt {dg['avg_book_weight']:.3f}  "
            f"purity {purity*100:.0f}%  flagged/day {n_flag:.1f}  "
            f"long-frac {live*100:.1f}%  vol {m.volatility*100:.1f}%"
        )

    df = pd.DataFrame(rows).set_index("variant")
    print("\n=== TRAIN summary (selection set — nothing here is a result) ===")
    print(
        df[
            ["period", "entry", "cagr", "sharpe", "max_dd", "calmar", "vol",
             "annual_turnover", "cost_drag_annual", "avg_names",
             "avg_material_names", "signal_purity", "frac_bars_long"]
        ].to_string(float_format=lambda v: f"{v:,.4f}")
    )

    # Selection rule, fixed in advance: highest TRAIN Sharpe among variants keeping at
    # least ~10 material positions (otherwise the "result" is a handful of stocks).
    elig = df[df.avg_material_names >= 10.0]
    pick = elig.sharpe.idxmax() if len(elig) else df.sharpe.idxmax()
    print(f"\nSELECTED (TRAIN Sharpe, >=10 material names): {pick}")
    print(f"  period={df.loc[pick,'period']:.0f}  entry={df.loc[pick,'entry']:.2f}")
    with open("train_selection.json", "w") as fh:
        json.dump({"selected": str(pick)}, fh)


if __name__ == "__main__":
    main()
