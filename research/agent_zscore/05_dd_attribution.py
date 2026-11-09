"""Step 05 — drawdown attribution.

The strategy's TEST MaxDD (-12.52%) beats buy-and-hold (-15.90%). But the strategy
runs at ~61% invested on average and buy-and-hold runs at 100%. A book that is 39% cash
will mechanically have a shallower drawdown, and that is not selection skill.

This asks the honest question: would buy-and-hold, held at the strategy's own average
exposure, have had the same drawdown? No parameters are selected here — the exposure
scale is taken from the strategy's already-frozen TEST run.
"""

from __future__ import annotations

import json
from pathlib import Path

from common import buy_and_hold, test_panel

HERE = Path(__file__).resolve().parent
RES = json.loads((HERE / "test_results.json").read_text())


def main() -> None:
    te = test_panel()
    bh = buy_and_hold(te, "bh TEST")
    r = bh["returns"]

    strat_dd = RES["strategy"]["max_drawdown"]
    exposure = RES["mean_invested"]
    strat_cagr = RES["strategy"]["cagr"]
    bh_cagr = bh["metrics"].cagr

    print(f"strategy TEST  : CAGR {strat_cagr * 100:>6.2f}%  MaxDD {strat_dd * 100:>7.2f}%  "
          f"avg exposure {exposure * 100:.1f}%")
    print(f"buy-and-hold   : CAGR {bh_cagr * 100:>6.2f}%  MaxDD "
          f"{bh['metrics'].max_drawdown * 100:>7.2f}%  avg exposure 100.0%")
    print()

    print("buy-and-hold rescaled to the strategy's own average exposure (cash at RF):")
    rf_d = (1.065) ** (1 / 244) - 1.0
    print(f"{'exposure':>9} {'CAGR':>9} {'MaxDD':>9} {'Calmar':>8}")
    rows = []
    for e in (1.00, 0.80, 0.70, 0.65, exposure, 0.55, 0.50, 0.40):
        daily = e * r + (1.0 - e) * rf_d
        eq = (1.0 + daily).cumprod()
        peak = eq.cummax()
        dd = float((eq / peak - 1.0).min())
        cagr = float(eq.iloc[-1] ** (244 / len(eq)) - 1.0)
        calmar = cagr / abs(dd) if dd < 0 else 0.0
        tag = "  <- strategy's actual exposure" if abs(e - exposure) < 1e-9 else ""
        print(f"{e:>8.1%} {cagr:>8.2%} {dd:>8.2%} {calmar:>8.2f}{tag}")
        rows.append({"exposure": e, "cagr": cagr, "maxdd": dd, "calmar": calmar})

    # How much of the strategy's drawdown advantage survives at matched exposure?
    print()
    print("INTERPRETATION")
    adv = abs(strat_dd) - abs(bh["metrics"].max_drawdown)
    matched = min(rows, key=lambda r: abs(r["exposure"] - exposure))
    gap = abs(strat_dd) - abs(matched["maxdd"])
    print(f"  Strategy MaxDD        {strat_dd * 100:>7.2f}%")
    print(f"  Buy-and-hold @100%   {bh['metrics'].max_drawdown * 100:>7.2f}%   "
          f"(apparent strategy advantage: {adv * 100:+.2f} pts)")
    print(f"  Buy-and-hold @{exposure * 100:.0f}%   {matched['maxdd'] * 100:>7.2f}%   "
          f"(matched-exposure comparison:    {gap * 100:+.2f} pts)")
    print()
    if gap >= 0:
        print("  => The drawdown 'advantage' does NOT survive exposure matching. Buy-and-hold,")
        print("     held at the strategy's own 61% cash level, had a SHALLOWER drawdown than")
        print("     the strategy. The z-score signal makes the drawdown worse, not better;")
        print("     the only thing softening it was the cash the signal forced us to hold.")
    else:
        print(f"  => {abs(gap) * 100:.2f} pts of the apparent drawdown advantage survives")
        print("     exposure matching, so part of it is real selection, not just cash.")

    (HERE / "dd_attribution.json").write_text(json.dumps(rows, indent=2))
    print("\nwrote dd_attribution.json")


if __name__ == "__main__":
    main()
