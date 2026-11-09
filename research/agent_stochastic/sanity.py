"""Sanity checks (brief §6) + the `upper`-is-a-dead-parameter claim (§1.3).

Nothing here selects parameters. The winner was already chosen on TRAIN.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, "src")

from nsealgo.backtest.engine import ENGINE_SHA, PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import build_score, signal_panel, stoch_k_panel  # noqa: E402
from evaluate import TEST, TRAIN, VARIANTS, load_all  # noqa: E402

OUT = Path(__file__).resolve().parent


def main() -> None:
    panel, symbols, high, low, _ = load_all()
    cm = CostModel(segment="delivery", slippage_bps=5)
    zero = CostModel(segment="delivery", slippage_bps=0)
    cfg = PortfolioConfig()
    s, e = TEST
    te = panel.loc[s:e]
    vname = "V5"  # construction is fixed at momentum (see REPORT §2)
    p = VARIANTS[vname]

    report = {"engine_sha": ENGINE_SHA}

    k = stoch_k_panel(high, low, panel, int(p["period"]))
    sig = signal_panel(k, p["lower"], p["upper"])
    raw = (panel / panel.shift(126) - 1.0).where(sig > 0)
    score = build_score(raw)

    print("=" * 78)
    print("CHECK 1 -- plausibility (brief §6.1)")
    print("=" * 78)
    res = run_backtest(te, score.loc[te.index], cm, cfg, rebalance="M")
    print(f"TEST CAGR {res.metrics.cagr*100:.2f}%  -- unlevered long-only NIFTY-50")
    print(f"  plausible (<=50%): {res.metrics.cagr < 0.50}")
    report["cagr"] = res.metrics.cagr

    print()
    print("=" * 78)
    print("CHECK 2 -- weight count (brief §6.2)")
    print("=" * 78)
    w = res.weights
    nheld = (w > 1e-4).sum(axis=1)
    print(f"avg names held      : {nheld.mean():.2f}   (config n_positions=22, max_names=30)")
    print(f"median names held   : {nheld.median():.1f}")
    print(f"min / max           : {nheld.min()} / {nheld.max()}")
    print(f"weight sum  mean    : {w.sum(axis=1).mean():.4f}  (target <= 1-cash_buffer = 0.90)")
    print(f"weight sum  max     : {w.sum(axis=1).max():.4f}")
    print(f"max single weight   : {w.max().max():.4f}  (cap 0.12)")
    elig = (sig.loc[te.index] > 0).sum(axis=1)
    print(f"mean ELIGIBLE names : {elig.mean():.2f}  <- binding constraint when < 22")
    report["avg_names"] = float(nheld.mean())
    report["mean_eligible"] = float(elig.mean())

    print()
    print("=" * 78)
    print("CHECK 3 -- signal liveness (brief §6.3)")
    print("=" * 78)
    live = float((sig.loc[te.index] > 0).sum(axis=1).mean() / len(symbols))
    print(f"fraction of bars long        : {live*100:.2f}%  (floor is ~5%)")
    print(f"fraction of symbol-days long : "
          f"{float((sig.loc[te.index] > 0).sum().sum()/(len(te)*len(symbols)))*100:.2f}%")
    print(f"  -> well above the 5% always-flat floor: {live > 0.05}")
    report["liveness"] = live

    print()
    print("=" * 78)
    print("CHECK 4 -- cost drag: gross vs net (brief §6.4)")
    print("=" * 78)
    rz = run_backtest(te, score.loc[te.index], zero, cfg, rebalance="M")
    net_c, gross_c = res.metrics.cagr, rz.metrics.cagr
    print(f"gross  (slippage_bps=0, statutory only): CAGR {gross_c*100:7.2f}%  "
          f"Sh {rz.metrics.sharpe:6.2f}")
    print(f"net    (slippage_bps=5, 21.92 bps)   : CAGR {net_c*100:7.2f}%  "
          f"Sh {res.metrics.sharpe:6.2f}")
    print(f"cost drag reported by engine           : {res.metrics.cost_drag_annual*100:.2f}%/y")
    print(f"turnover                              : {res.metrics.annual_turnover:.2f}x/y")
    print(f"  -> gross positive, net positive: "
          f"{gross_c > 0 and net_c > 0} (viable); gross+ net- would be unviable")
    report["gross_cagr"] = gross_c
    report["net_cagr"] = net_c
    report["cost_drag"] = res.metrics.cost_drag_annual

    print()
    print("=" * 78)
    print("CLAIM §1.3 -- `upper` is a DEAD parameter in a long-only book")
    print("=" * 78)
    outs = {}
    for up in (10.0, 20.0, 50.0, 70.0, 80.0, 95.0, 99.0):
        sg = signal_panel(k, p["lower"], up)
        rw = (panel / panel.shift(126) - 1.0).where(sg > 0)
        sc = build_score(rw)
        r = run_backtest(te, sc.loc[te.index], cm, cfg, rebalance="M")
        outs[up] = (r.metrics.cagr, r.metrics.sharpe, r.diag["avg_names"])
        print(f"  upper={up:5.1f} -> CAGR {r.metrics.cagr*100:7.4f}%  "
              f"Sh {r.metrics.sharpe:7.4f}  names {r.diag['avg_names']:.4f}")
    cagrs = {round(v[0], 12) for v in outs.values()}
    print(f"  distinct CAGR values across 7 upper settings: {len(cagrs)}")
    print(f"  -> upper has NO effect: {len(cagrs) == 1}")
    report["upper_dead"] = len(cagrs) == 1
    report["upper_sweep"] = {str(k2): v for k2, v in outs.items()}

    print()
    print("=" * 78)
    print("CHECK 5 -- behaviour by TRAIN/TEST + market beta")
    print("=" * 78)
    for label, (a, b) in (("TRAIN", TRAIN), ("TEST", TEST)):
        w2 = panel.loc[a:b]
        # Compute the factor on the FULL panel, THEN slice. Slicing first would
        # leave the first 126 bars of the window with NaN momentum -- a different,
        # weaker strategy than the one selected on TRAIN.
        k2 = stoch_k_panel(high, low, panel, int(p["period"])).loc[a:b]
        s2 = signal_panel(k2, p["lower"], p["upper"])
        mom2 = panel / panel.shift(126) - 1.0
        raw2 = mom2.loc[a:b].where(s2 > 0)
        sc2 = build_score(raw2)
        r2 = run_backtest(w2, sc2.loc[w2.index], cm, cfg, rebalance="M")
        mk = w2.pct_change(fill_method=None).fillna(0.0).mean(axis=1)
        bta = float(np.cov(r2.returns, mk)[0, 1] / np.var(mk, ddof=1))
        print(f"{label:6s} CAGR {r2.metrics.cagr*100:7.2f}%  Sh {r2.metrics.sharpe:6.2f}  "
              f"DD {r2.metrics.max_drawdown*100:7.2f}%  names {r2.diag['avg_names']:4.1f}  "
              f"beta {bta:5.2f}  avg exposure {r2.weights.sum(axis=1).mean():.3f}")
        report[f"{label.lower()}_beta"] = bta

    print()
    print("=" * 78)
    print("DETERMINISM -- rerun the TEST backtest and compare")
    print("=" * 78)
    res2 = run_backtest(te, score.loc[te.index], cm, cfg, rebalance="M")
    same = bool((res.returns - res2.returns).abs().max() < 1e-15)
    print(f"max |return diff| across reruns : "
          f"{float((res.returns - res2.returns).abs().max()):.3e}")
    print(f"byte-identical: {same}   engine_sha both: {res.engine_sha} / {res2.engine_sha}")
    report["deterministic"] = same

    (OUT / "sanity.json").write_text(json.dumps(report, indent=2, default=str))
    print(f"\nwrote {OUT/'sanity.json'}")


if __name__ == "__main__":
    main()
