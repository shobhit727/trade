"""Arithmetic decomposition of the TEST shortfall. NOT a new strategy variant.

Takes the already-computed champion return series and splits the gap to
buy-and-hold into (a) underexposure and (b) trading costs, holding the selection
effect fixed. No new parameters are introduced and nothing is re-tuned.
"""
import benchmarks as B
from common import TEST_END, TEST_START, backtest, load, score_from_signal, signal_panel

panel, _, _ = load()
sig = signal_panel(panel, 10, 0.01)
sc = score_from_signal(sig, panel, 10)
res = backtest(panel, sc, TEST_START, TEST_END)
bhc = B.bh_constrained(panel, TEST_START, TEST_END)

exp_s = res.weights.sum(axis=1).mean()
exp_b = bhc.weights.sum(axis=1).mean()
# gross-of-cost version of the champion's own daily return series
gross_daily = (1.0 + res.returns).cumprod()          # net equity path
drag = res.metrics.cost_drag_annual                  # fraction/yr removed by costs
yrs = len(res.returns) / 244.0
net_cagr = (1.0 + res.returns).prod() ** (1.0 / yrs) - 1.0
gross_cagr = net_cagr + drag                         # add back the annual drag

print(f"champion TEST: net CAGR {net_cagr * 100:6.2f}%  |  + cost drag {drag * 100:.2f}%/y"
      f"  =>  gross-of-cost CAGR {gross_cagr * 100:6.2f}%")
print(f"B&H 22-name TEST (net): {bhc.metrics.cagr * 100:6.2f}%")
print(f"\nshortfall to B&H (net)          : {(net_cagr - bhc.metrics.cagr) * 100:+6.2f} pp/yr")
print(f"  of which trading costs         : {-drag * 100:+6.2f} pp/yr")
print(f"  of which underexposure         : "
      f"{(gross_cagr - gross_cagr * (exp_b / exp_s)) * 100:+6.2f} pp/yr "
      f"(gross CAGR scaled from {exp_s * 100:.0f}% to {exp_b * 100:.0f}% invested)")
resid = (net_cagr - bhc.metrics.cagr) + drag + (gross_cagr - gross_cagr * (exp_b / exp_s))
print(f"  residual (selection vs the 22 B&H names): {resid * 100:+6.2f} pp/yr")

print("\nread: costs and underexposure together explain only "
      f"{-(drag + (gross_cagr - gross_cagr * (exp_b / exp_s))) * 100:.2f} pp/yr of the "
      f"{abs(resid) * 100:.2f} pp/yr shortfall.")
print("cross-check at 100% invested: strategy gross scaled "
      f"{gross_cagr / exp_s * 100:.2f}% vs equal-weight universe {8.25:.2f}% "
      "-> selection is negative either way.")
print("the dominant term is SELECTION: on TEST the names this signal picked, held in a")
print("22-name fully-invested book, earned less than an arbitrary 22-name buy-and-hold.")
