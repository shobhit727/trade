"""Pinpoint WHERE weight is lost inside `apply_turnover_budget`.

Re-implements the engine's target loop read-only (calling the real
`_thin`, `_one_way_turnover`, `_project_constraints`) and records the book total
at each stage: raw target -> blended -> thinned.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_multifactor")

from harness import CM, PANEL, TRAIN, PortfolioConfig, run_backtest, score_variant  # noqa: E402

from nsealgo.backtest.engine import (  # noqa: E402
    _one_way_turnover,
    _rebalance_dates,
    _thin,
    build_rebalance_weights,
)

cfg = PortfolioConfig()
sc = score_variant(PANEL, 20, 14, 126, False)

idx = PANEL.index.intersection(sc.index)
px = PANEL.loc[idx]
vol = px.pct_change(fill_method=None).fillna(0.0).rolling(
    cfg.vol_lookback, min_periods=20
).std()
rb = [d for d in _rebalance_dates(px.index, "M") if d in sc.index][1:]
tgt_raw = build_rebalance_weights(sc.loc[rb], rb, vol.loc[rb], cfg)

rows = []
prev = None
for i in range(len(tgt_raw)):
    raw = tgt_raw.iloc[i]
    demanded = _one_way_turnover(raw, prev) if prev is not None else 0.0
    lam = min(1.0, cfg.turnover_budget / demanded) if demanded > 0 else 1.0
    blended = prev + lam * (raw - prev) if prev is not None else raw.copy()
    out = _thin(blended, cfg.max_names)
    rows.append(
        {
            "date": str(tgt_raw.index[i].date()),
            "sum_raw": raw.sum(),
            "demanded": demanded,
            "lam": lam,
            "sum_blend": blended.sum(),
            "n_blend": int((blended > 0).sum()),
            "sum_thin": out.sum(),
            "n_thin": int((out > 0).sum()),
        }
    )
    prev = out

print(f"budget={cfg.turnover_budget}  max_names={cfg.max_names}  "
      f"DEAD_WEIGHT_EPS=1e-4")
print(f"{'date':<12}{'sum_raw':>9}{'demanded':>10}{'lam':>7}"
      f"{'sum_blend':>11}{'n_blend':>9}{'sum_thin':>11}{'n_thin':>9}")
for r in rows[8::12]:
    print(f"{r['date']:<12}{r['sum_raw']:>9.3f}{r['demanded']:>10.3f}{r['lam']:>7.3f}"
          f"{r['sum_blend']:>11.3f}{r['n_blend']:>9d}{r['sum_thin']:>11.3f}"
          f"{r['n_thin']:>9d}")

n = len(rows)
m_lam = sum(r["lam"] for r in rows) / n
m_dem = sum(r["demanded"] for r in rows) / n
m_raw = sum(r["sum_raw"] for r in rows) / n
m_bl = sum(r["sum_blend"] for r in rows) / n
m_th = sum(r["sum_thin"] for r in rows) / n
m_nb = sum(r["n_blend"] for r in rows) / n
m_nt = sum(r["n_thin"] for r in rows) / n
print(f"\nmeans over {n} rebalances:")
print(f"  target total          {m_raw:.4f}   (config wants {1-cfg.cash_buffer:.2f})")
print(f"  demanded one-way turn {m_dem:.4f}   (budget {cfg.turnover_budget})")
print(f"  lam                   {m_lam:.4f}")
print(f"  total after blend     {m_bl:.4f}   names {m_nb:.1f}")
print(f"  total after _thin     {m_th:.4f}   names {m_nt:.1f}")
print(f"\n  => weight lost in the BLEND  : {m_bl - m_raw:+.4f}")
print(f"  => weight lost in _thin()    : {m_th - m_bl:+.4f}")
print(f"  => net shortfall vs 0.90    : {m_th - (1-cfg.cash_buffer):+.4f}")

# Does the book ever reach its target?
hits = sum(1 for r in rows if r["demanded"] <= cfg.turnover_budget + 1e-12)
print(f"\n  rebalances where turnover fit inside the budget: {hits}/{n} "
      f"({hits/n*100:.1f}%)")

res = run_backtest(PANEL, sc, CM, cfg, rebalance="M")
inv = res.weights.loc[TRAIN[0]:TRAIN[1]].sum(axis=1)
print(f"\n  realised TRAIN invested fraction: mean {inv.mean():.4f}")
print(f"  (run_backtest diag avg_names = {res.diag['avg_names']:.1f}, "
      f"rt_bps = {res.diag['round_trip_bps']})")
