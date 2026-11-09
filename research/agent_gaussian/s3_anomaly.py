"""Step 3 — investigate the anomaly: universe daily-mean return annualises to
+8.83%/yr but equal-weight buy-and-hold compounds to -36.6% CAGR.

That is arithmetically impossible for a book of the same series, so one of the two is
wrong. Diagnose before reporting either number.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "src")

from nsealgo.data.loader import load_universe  # noqa: E402

pd.set_option("display.width", 220)
TEST = ("2024-01-01", "2026-10-01")


def main() -> None:
    panel, symbols, _ = load_universe("data/nse")
    px = panel.loc[TEST[0] : TEST[1]]
    rets = px.pct_change(fill_method=None)

    print("=== 1. worst single-symbol single-day moves on TEST ===")
    stack = rets.stack().sort_values()
    print(stack.head(25).to_string())
    print()
    print("=== 2. how many symbol-days below -20% / +20% ===")
    print(f"  < -20%: {(stack < -0.20).sum()}")
    print(f"  > +20%: {(stack > 0.20).sum()}")
    print(f"  < -30%: {(stack < -0.30).sum()}")
    print()

    print("=== 3. per-symbol TEST total return (worst 12) ===")
    tot = (px.iloc[-1] / px.iloc[0] - 1.0).sort_values()
    print(tot.head(12).to_string())
    print("  ...")
    print(tot.tail(5).to_string())
    print()

    print("=== 4. arithmetic vs geometric on the equal-weight daily mean ===")
    r_un = rets.fillna(0.0).mean(axis=1)
    print(f"  sum of daily mean      : {r_un.sum() * 100:.2f}%")
    print(f"  compounded daily mean  : {((1 + r_un).prod() - 1) * 100:.2f}%")
    print(f"  daily-mean vol         : {r_un.std() * np.sqrt(244) * 100:.2f}%")
    print(f"  daily-mean CAGR        : {(((1 + r_un).prod()) ** (244 / len(r_un)) - 1) * 100:.2f}%")
    print("  -> the daily MEAN is a rebalanced equal-weight return; it compounds")
    print("     correctly. A buy-and-hold basket does NOT rebalance, so its return is")
    print("     the geometric mean of the constituents, which the daily mean cannot show.")
    print()

    print("=== 5. so compare like with like: rebalanced vs held ===")
    bh = px.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
    print(f"  rebalanced EW (daily mean, net of nothing): CAGR {(((1 + bh).prod()) ** (244 / len(bh)) - 1) * 100:>7.2f}%")
    # true buy-and-hold: equal capital into each name at t0, held to the end
    n = px.shape[1]
    final = (px.iloc[-1] / px.iloc[0]).fillna(0.0) / n
    print(f"  buy-and-hold EW basket: total {final.sum() * 100:.2f}%  "
          f"CAGR {(final.sum() ** (244 / len(px)) - 1) * 100:.2f}%")
    print(f"  arithmetic mean of constituent returns: {tot.mean() * 100:.2f}%")
    print()

    print("=== 6. is the gap a few names or broad? ===")
    print(f"  names with TEST total return < -40%: {(tot < -0.40).sum()} / {len(tot)}")
    print(f"  names with TEST total return > +40%: {(tot > 0.40).sum()} / {len(tot)}")
    print()
    print("=== 7. do the losers have a single cliff day? (split signature) ===")
    for sym in tot.head(6).index:
        s = rets[sym].dropna()
        worst = s.nsmallest(3)
        days_before = px[sym].shift(1).loc[worst.index]
        print(f"  {sym:<12} worst days: "
              + "  ".join(
                  f"{d.date()} {v * 100:>7.1f}% (prev close {p:>9.1f})"
                  for d, v, p in zip(worst.index, worst.values, days_before.values, strict=False)
              ))


if __name__ == "__main__":
    main()
