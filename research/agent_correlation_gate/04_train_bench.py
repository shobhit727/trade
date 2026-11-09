"""Validate the benchmark/control code on TRAIN before TEST is ever touched."""
import benchmarks as B
import numpy as np
from common import TRAIN_END, TRAIN_START, fmt_metrics, load

panel, _, _ = load()
sig, res = B.strategy(panel, 10, 0.01, TRAIN_START, TRAIN_END)
print("TRAIN reference points (champion V2 vs benchmarks / controls)")
print(fmt_metrics("  correlation_gate V2", res.metrics, f"names={res.diag['avg_names']:.1f}"))
r, e, m = B.bh_gross(panel, TRAIN_START, TRAIN_END)
print(fmt_metrics("  B&H equal-weight (gross)", m))
bh = B.bh_constrained(panel, TRAIN_START, TRAIN_END)
print(fmt_metrics("  B&H 22-name constrained", bh.metrics, f"names={bh.diag['avg_names']:.1f}"))
c = B.composite(panel, TRAIN_START, TRAIN_END)
print(fmt_metrics("  nsealgo composite", c.metrics, f"names={c.diag['avg_names']:.1f}"))
lf = float((sig.loc[TRAIN_START:TRAIN_END] > 0).to_numpy().mean())
print(f"\n  live fraction fed to the random control: {lf * 100:.1f}%")
ctl = B.random_control(panel, lf, TRAIN_START, TRAIN_END, seed=1, n=5)
for i, m in enumerate(ctl, 1):
    print(fmt_metrics(f"  random control #{i}", m))
a = np.array([m.sharpe for m in ctl])
print(f"\n  control Sharpe mean {a.mean():.2f} sd {a.std(ddof=1):.2f} "
      f"| strategy Sharpe {res.metrics.sharpe:.2f} "
      f"-> beats {int((a < res.metrics.sharpe).sum())}/{len(a)} controls")
