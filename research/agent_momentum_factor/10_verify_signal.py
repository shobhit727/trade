"""10 — prove the vectorised signal IS the assigned catalog strategy, bar for bar.

Compares ``common.strategy_signal`` against the real
``cryptobot.strategies.catalog.momentum_factor_strategy.MomentumFactorStrategy.signal``
over every symbol and every declared parameter set. A single mismatch is a failed run.
"""

from __future__ import annotations

import common
import numpy as np

from cryptobot.strategies.catalog.momentum_factor_strategy import (
    MomentumFactorConfig,
    MomentumFactorStrategy,
)

panel, symbols, _ = common.load_panel()
cols = list(panel.columns)

print("catalog class  :", MomentumFactorStrategy.name)
print("catalog default:", MomentumFactorConfig())
print()

ok = True
for v in common.VARIANTS:
    vec = common.strategy_signal(panel, v.period, v.threshold)
    strat = MomentumFactorStrategy(
        MomentumFactorConfig(period=v.period, threshold=v.threshold)
    )
    n = 0
    bad = 0
    for sym in cols:
        s = panel[sym]
        # The catalog class consumes a bar-by-bar rolling window ending at t.
        # Only compare where the trailing window is fully populated.
        valid = s.notna().to_numpy()
        arr = s.to_numpy(dtype=float)
        for t in range(v.period, len(arr)):
            if not valid[t]:
                continue
            window = arr[t - v.period: t + 1]
            if np.isnan(window).any():
                continue
            expect = strat.signal(window, window, window, window)
            got = vec.iloc[t][sym]
            n += 1
            if int(expect) != int(got):
                bad += 1
                if bad <= 3:
                    print(f"  MISMATCH {sym} t={panel.index[t].date()} "
                          f"expect={expect} got={got}")
    status = "IDENTICAL" if bad == 0 else f"{bad} MISMATCHES"
    print(f"{v.tag:3s} period={v.period:4d} thr={v.threshold:<6} "
          f"bars compared {n:>8,}  -> {status}")
    ok = ok and bad == 0

print()
print("SIGNAL EQUIVALENCE:", "PASS" if ok else "FAIL")

# ---- Signal liveness: fraction of name-bars long / flat / short (brief §6 check 3)
for v in common.VARIANTS:
    sig = common.strategy_signal(panel, v.period, v.threshold)
    for label, s, e in (("TRAIN", common.TRAIN_START, common.TRAIN_END),
                        ("TEST", common.TEST_START, common.TEST_END)):
        w = sig.loc[(sig.index >= s) & (sig.index <= e)]
        cells = w.to_numpy().ravel()
        cells = cells[~np.isnan(cells)]
        long_f = float((cells > 0).mean())
        flat_f = float((cells == 0).mean())
        short_f = float((cells < 0).mean())
        # Eligible per day (names passing the gate, either leg)
        elig = int((w > 0).sum(axis=1).mean())
        print(f"{v.tag:3s} {label:5s} long {long_f * 100:5.1f}%  "
              f"flat {flat_f * 100:5.1f}%  short {short_f * 100:5.1f}%  "
              f"avg long-eligible names/day {elig}")
