"""Bug-4 probe: why does the engine hold only ~56% when the cap should allow 90%?

``PortfolioConfig.cash_buffer`` is 0.10, so a fully-built book should carry ~90%
gross exposure. The V3 book sits at 56.3%. Two candidate causes:

  (a) ``build_rebalance_weights`` only considers the top ``n_positions`` candidates
      that are *valid* (finite score AND finite vol). When the signal flags only
      ~10 names, the candidate set is ~10, and inverse-vol scaling should still sum
      to 1.0 -> exposure should still be ~90%.
  (b) ``_project_constraints`` enforces the 25% sector cap, and ``_spill`` refuses
      to move mass outside the names the book *already* holds. If the flagged set is
      concentrated in a few sectors AND those names are already at the 12% single-name
      cap, the freed mass has nowhere legal to go and is left as cash.

This separates them by re-running the identical signal with the sector cap relaxed.
If exposure jumps when the sector cap is removed, (b) is the cause.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from coinlib import (  # noqa: E402
    PF_CFG,
    TEST_END,
    TEST_START,
    build_score_window,
    evaluate,
)

from nsealgo.backtest.engine import PortfolioConfig, sector_of  # noqa: E402

W, ENTRY = 126, 1.0


def main() -> None:
    px, score = build_score_window((TEST_START, TEST_END), W, ENTRY, "depth")
    flag = score.notna()
    print(f"flagged names per rebalance: mean {flag.sum(axis=1).mean():.1f}  "
          f"median {flag.sum(axis=1).median():.0f}  max {flag.sum(axis=1).max():.0f}")

    # Sector concentration of the flagged set, on a rebalance sample.
    sample = flag.iloc[::21]
    sec = {c: sector_of(c) for c in px.columns}
    sec_s = sample.apply(lambda row: pd.Series(
        {sec[c]: int(v) for c, v in row.items() if v}), axis=1).fillna(0.0)
    conc = (sec_s.sum() / sec_s.sum().sum()).sort_values(ascending=False)
    spanned = (sec_s > 0).sum(axis=1)
    print(f"sectors spanned per flagged bar: mean {spanned.mean():.1f} "
          f"median {spanned.median():.0f} (of {len(set(sec.values()))} known sectors)")
    print("top sectors by share of flagged slots:")
    for s, v in conc.head(6).items():
        print(f"   {s:<14} {v * 100:5.1f}%")

    print("\n" + "=" * 92)
    print("SAME SIGNAL, DIFFERENT CONSTRAINT SETTINGS (TEST, V3, corrected costs)")
    print("=" * 92)
    cases = [
        ("stock (sector cap 25%)", PF_CFG),
        ("sector cap 100%", PortfolioConfig(n_positions=22, max_sector_weight=1.0)),
        ("sector cap 50%", PortfolioConfig(n_positions=22, max_sector_weight=0.50)),
        ("no cash buffer", PortfolioConfig(n_positions=22, cash_buffer=0.0)),
        ("n_positions 30", PortfolioConfig(n_positions=30)),
        ("turnover budget 1.0", PortfolioConfig(n_positions=22, turnover_budget=1.0)),
        ("turnover budget 2.0", PortfolioConfig(n_positions=22, turnover_budget=2.0)),
        ("turnover 1.0 + no cash", PortfolioConfig(n_positions=22, turnover_budget=1.0,
                                                   cash_buffer=0.0)),
    ]
    base = None
    for label, cfg in cases:
        r = evaluate(label, px, score, config=cfg)
        e = r.diag["avg_exposure"]
        if base is None:
            base = e
        print(f"  {label:<26} exposure {e * 100:5.1f}%  names "
              f"{r.diag['avg_names']:5.1f}  CAGR {r.metrics.cagr * 100:>6.2f}%  "
              f"Sharpe {r.metrics.sharpe:>5.2f}")

    print("\ninterpretation: if removing the sector cap materially lifts exposure,")
    print("the cause is _spill refusing to redistribute outside the held names,")
    print("and the book is structurally under-invested for a thin, sector-concentrated")
    print("signal. Raw CAGR is then NOT comparable across strategies whose signals")
    print("flag different numbers of names.")


if __name__ == "__main__":
    main()
