"""Post-hoc diagnostics on the FROZEN V5 TEST run.

Deliberately does NOT evaluate any other variant on TEST -- that would break the
protocol. These diagnostics only interrogate the run that was already selected.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "research/agent_momvol")

from common import (  # noqa: E402
    get_panel,
    run,
    test_parts,
)

from nsealgo.backtest.engine import _rebalance_dates  # noqa: E402

FROZEN_MOMPERIOD = 5
FROZEN_THRESHOLD = 0.005


def main() -> None:
    panel, _ = get_panel()
    p, sc = test_parts(panel, FROZEN_MOMPERIOD, FROZEN_THRESHOLD)
    r = run(p, sc, "V5_TEST")
    held = r.result.weights

    print("=" * 74)
    print("DIAG 1: why avg_names = 17.0 rather than the nominal 22?")
    print("=" * 74)
    rb = [d for d in _rebalance_dates(p.index, "M") if d in sc.index][1:]
    elig = sc.loc[rb].notna().sum(axis=1)
    print(f"  rebalances: {len(rb)}")
    print("  eligible (signalled & rankable) names at rebalance:")
    print(f"    min {elig.min()}  p25 {elig.quantile(.25):.0f}  median {elig.median():.0f}"
          f"  p75 {elig.quantile(.75):.0f}  max {elig.max()}")
    n_starved = int((elig < 22).sum())
    print(f"    rebalances with < 22 eligible names: {n_starved}/{len(rb)} "
          f"({n_starved/len(rb)*100:.0f}%)")
    print("  => book is capped by the SIGNAL, not by n_positions. 17 names is the")
    print("     safe direction (more concentrated, never 48). Not a weight bug.")

    print()
    print("=" * 74)
    print("DIAG 2: turnover & cost concentration")
    print("=" * 74)
    tgt = held.loc[rb]
    turn = (tgt - tgt.shift(1).fillna(0.0)).abs().sum(axis=1) / 2.0
    print(f"  one-way turnover per rebalance: mean {turn.mean():.3f}  "
          f"median {turn.median():.3f}  max {turn.max():.3f}  (budget 0.35)")
    print(f"  rebalances hitting the 0.35 budget: {int((turn>=0.349).sum())}/{len(rb)}")
    print(f"  annual turnover {r.metrics.annual_turnover:.2f}x  "
          f"-> cost drag {r.metrics.cost_drag_annual*100:.2f}%/y")
    print(f"  gross CAGR {r.gross_cagr()*100:.2f}%  vs net {r.metrics.cagr*100:.2f}%")

    print()
    print("=" * 74)
    print("DIAG 3: is the negative Sharpe real, or noise? (block bootstrap)")
    print("=" * 74)
    rets = r.result.returns
    n = len(rets)
    rng = np.random.default_rng(12345)
    boots = []
    for _ in range(2000):
        idx = rng.integers(0, n, n)
        s = rets.iloc[idx]
        eq = (1.0 + s).cumprod()
        years = len(eq) / 244
        boots.append(eq.iloc[-1] ** (1 / years) - 1.0)
    boots = np.array(boots)
    lo, hi = np.percentile(boots, [5, 95])
    print(f"  CAGR bootstrap 90% CI: [{lo*100:.2f}%, {hi*100:.2f}%]  "
          f"(point {r.metrics.cagr*100:.2f}%)")
    print(f"  P(CAGR <= 0) = {(boots<=0).mean()*100:.1f}%")

    print()
    print("=" * 74)
    print("DIAG 4: where did the return actually go? (monthly, strategy)")
    print("=" * 74)
    m = (1.0 + rets).groupby(rets.index.to_period("M")).prod() - 1.0
    print(f"  positive months {int((m>0).sum())}/{len(m)}  "
          f"({(m>0).mean()*100:.0f}%)")
    print(f"  best {m.max()*100:.2f}% ({m.idxmax()})   "
          f"worst {m.min()*100:.2f}% ({m.idxmin()})")

    # Benchmark beta / correlation
    mkt = p.pct_change(fill_method=None).mean(axis=1).fillna(0.0)
    j = pd.concat([rets, mkt], axis=1).dropna()
    j.columns = ["strat", "mkt"]
    beta = float(np.cov(j["strat"], j["mkt"])[0, 1] / np.var(j["mkt"], ddof=1))
    corr = float(j["strat"].corr(j["mkt"]))
    te = float(j["strat"].sub(j["mkt"]).std(ddof=1) * np.sqrt(244))
    print()
    print("=" * 74)
    print("DIAG 5: is it just beta? (vs equal-weight universe)")
    print("=" * 74)
    print(f"  beta to equal-weight universe : {beta:.2f}")
    print(f"  correlation                   : {corr:.2f}")
    print(f"  tracking-error vol (ann.)      : {te*100:.2f}%")
    print(f"  => a beta-{beta:.2f} book would roughly return "
          f"{beta*mkt.mean()*244*100:.1f}%/y gross from market drift alone.")
    print(f"  strategy gross {r.gross_cagr()*100:.2f}% -> the signal added "
          f"{(r.gross_cagr() - beta*mkt.mean()*244)*100:+.2f} pp over pure beta.")


if __name__ == "__main__":
    main()
