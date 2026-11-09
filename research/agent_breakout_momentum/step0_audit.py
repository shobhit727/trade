"""Step 0 (mandatory): data audit + cost sanity + bit-exact signal verification."""

from __future__ import annotations

import numpy as np
from common import (
    COST_MODEL,
    DATA_DIR,
    OUT_DIR,
    TEST_END,
    TEST_START,
    TRAIN_END,
    TRAIN_START,
    assert_ohlc_aligned,
    donchian_high_excl,
    donchian_high_incl,
    load_ohlc_universe,
    roc_panel,
    signal_long,
)

from cryptobot.strategies.catalog.breakout_momentum_strategy import (
    BreakoutMomentumConfig,
    BreakoutMomentumStrategy,
)
from nsealgo.backtest.engine import PortfolioConfig, build_rebalance_weights
from nsealgo.factors.core import build_composite_score

lines: list[str] = []


def out(s: str = "") -> None:
    print(s)
    lines.append(s)


def hdr(s: str) -> None:
    out()
    out("=" * 78)
    out(s)
    out("=" * 78)


hdr("STEP 0.1  DATA (mandatory: load_universe report)")
u = load_ohlc_universe(DATA_DIR)
out(u.report.describe())
out(f"symbols retained       : {len(u.symbols)}")
out(f"date span              : {u.close.index[0].date()} -> {u.close.index[-1].date()}")
out(f"panel shape            : {u.close.shape}")
out(f"excluded (from loader) : {sorted(set(u.report.excluded_symbols) - set(u.symbols))}")

# 1d is the PRIMARY substrate per the brief; confirm nothing is intraday.
out()
out("rows per symbol (1d) -- min/max/median:")
rows = u.close.notna().sum()
out(f"  min {int(rows.min())}  max {int(rows.max())}  median {int(rows.median())}")
out(f"  span days (calendar)  : {(u.close.index[-1] - u.close.index[0]).days}")
out(f"  trading bars          : {len(u.close.index)}")

# Listing staleness: which symbols have data covering the whole split?
out()
out("coverage over TRAIN start .. TEST end:")
win = u.close.loc[TRAIN_START:TEST_END]
cov = win.notna().mean()
short = cov[cov < 0.999].sort_values()
if len(short):
    out(f"  {len(short)} symbol(s) with <99.9% coverage in the split window:")
    for s, c in short.items():
        out(f"    {s:<12} {c * 100:>6.1f}%  (first bar {win[s].first_valid_index().date()})")
else:
    out("  all 50 symbols cover TRAIN..TEST fully")

out()
out(f"TRAIN window : {TRAIN_START.date()} -> {TRAIN_END.date()}  "
    f"({len(u.close.loc[TRAIN_START:TRAIN_END])} bars)")
out(f"TEST  window : {TEST_START.date()} -> {TEST_END.date()}  "
    f"({len(u.close.loc[TEST_START:TEST_END])} bars)")

n_fin_bars, n_noise = assert_ohlc_aligned(u)
out()
out("OHLC alignment + low<=close<=high integrity: OK")
out(f"  finite OHLC bars checked     : {n_fin_bars:,}")
out(f"  1-ULP float-noise bars      : {n_noise}  (relative tol 1e-9, disclosed)")

hdr("STEP 0.2  COST SANITY")
rt = COST_MODEL.all_in_round_trip_bps(100_000)
stat = COST_MODEL.round_trip_bps(100_000)
out("CostModel(delivery, slippage_bps=5)")
out(f"  statutory round-trip @ Rs 1L/side : {stat} bps")
out(f"  brief expects ~11.9 bps          : "
    f"{'MATCH' if 11.5 <= float(stat) <= 12.4 else 'MISMATCH'}")
out(f"  + 2x5bps slippage                : {rt} bps  <-- what run_backtest charges")
out("  (the brief's ~11.9 is the STATUTORY figure; the engine additionally charges")
out("   10bps of adverse slippage per round trip, so 21.92 is the honest all-in)")

hdr("STEP 0.3  SIGNAL REPLICATION -- is my vectorised port bit-exact?")
# Drive the catalog's own scalar signal() over real bars and compare to my panel.
period, mom = 20, 10
strat = BreakoutMomentumStrategy(BreakoutMomentumConfig(period=period, mom_period=mom))
out(f"catalog strategy: name={strat.name} period={period} mom_period={mom} "
    f"warmup={strat.warmup(None)}")

# 3 symbols x last 400 bars, driven through the REAL strategy object.
sig_incl = signal_long(u, period, mom, channel="incl")
sig_excl = signal_long(u, period, mom, channel="excl")
rocp = roc_panel(u.close, mom)
ch_incl = donchian_high_incl(u.high, period)
ch_excl = donchian_high_excl(u.high, period)

syms = u.symbols[:3]
rows_checked = 0
mismatch_incl = 0
mismatch_excl = 0
for sym in syms:
    df_c = u.close[sym].dropna()
    df_h = u.high[sym].reindex(df_c.index)
    df_l = u.low[sym].reindex(df_c.index)
    c = df_c.to_numpy()
    h = df_h.to_numpy()
    lo = df_l.to_numpy()
    for i in range(len(c)):
        # Replicate SignalStrategy's history slice convention: the object is handed
        # the series truncated to i+1 and reads the LAST element each time.
        hc = strat.signal(c[: i + 1], h[: i + 1], lo[: i + 1], None)
        dt = df_c.index[i]
        if dt < TRAIN_START:
            continue
        rows_checked += 1
        long_incl = bool(sig_incl.loc[dt, sym])
        long_excl = bool(sig_excl.loc[dt, sym])
        # catalog long leg: (close >= hh) and (roc > 0)  -> signal == 1
        if (hc == 1) != long_incl:
            mismatch_incl += 1
        if (hc == 1) != long_excl:
            mismatch_excl += 1

out(f"bars verified against catalog .signal(): {rows_checked}")
out(f"  mismatches, channel='incl' (faithful): {mismatch_incl}")
out(f"  mismatches, channel='excl'            : {mismatch_excl}")
out(f"  FAITHFUL PORT: {'BIT-EXACT' if mismatch_incl == 0 else 'BROKEN'}")
out("  (excl channel is intentionally a DIFFERENT strategy -- the standard "
    "Donchian reading -- so its mismatch count is expected to be non-zero and "
    "is itself the measure of how much the two readings differ)")

# How often does each reading fire, and what does the inclusive one imply?
out()
out("signal liveness (fraction of finite symbol-bars long), full sample:")
fin = np.isfinite(u.close.to_numpy(dtype=float))
n_fin = int(fin.sum())
out(f"  finite symbol-bars: {n_fin:,}")
for ch_name in ("incl", "excl"):
    s = signal_long(u, period, mom, channel=ch_name).to_numpy(dtype=float)
    out(f"  channel={ch_name:<5} fires {s.sum() / n_fin * 100:>6.3f}%  "
        f"({int(s.sum()):,} bars)")

# The inclusive channel's real meaning: close == today's high, today's high is
# the window max. Quantify it.
c_all = u.close
h_all = u.high
eq_high = (c_all >= h_all - 1e-9)
at_win_max = (h_all >= ch_incl - 1e-9)
out()
out("decomposition of the inclusive channel:")
out(f"  close == today's high          : {eq_high.to_numpy().sum() / n_fin * 100:>6.3f}% of bars")
out(f"  today's high == {period}d high      : "
    f"{at_win_max.to_numpy().sum() / n_fin * 100:>6.3f}% of bars")
out(f"  both (== inclusive breakout)   : "
    f"{(eq_high & at_win_max).to_numpy().sum() / n_fin * 100:>6.3f}% of bars")
out("  -> the catalog's `close >= donchian_high(highs)` is a CLOSE-AT-THE-DAY-"
    "HIGH condition, not a channel breakout.")
out("  -> the ROC filter removes some; the fired rate above is after it.")

hdr("STEP 0.4  ENGINE SMOKE TEST (TRAIN only -- TEST untouched)")
# Cheap structural check that build_rebalance_weights honours the caps, on TRAIN.
sc_train = build_composite_score(u.close.loc[TRAIN_START:TRAIN_END])
cfg = PortfolioConfig()
idx = u.close.loc[TRAIN_START:TRAIN_END].index
vol = u.close.loc[TRAIN_START:TRAIN_END].pct_change(fill_method=None).fillna(0.0) \
    .rolling(cfg.vol_lookback, min_periods=20).std()
dates = [d for d in idx[::21]]
w = build_rebalance_weights(sc_train.reindex(dates), dates, vol.reindex(dates), cfg)
out(f"weights rows={len(w)}  max single={w.to_numpy().max():.4f} "
    f"(cap {cfg.max_weight})  max row sum={w.sum(axis=1).max():.4f} "
    f"(cap {1 - cfg.cash_buffer:.2f})")
out(f"avg names in target book: {(w > 0).sum(axis=1).mean():.1f} "
    f"(config n_positions={cfg.n_positions}, max_names={cfg.max_names})")
assert w.to_numpy().max() <= cfg.max_weight + 1e-9, "single-name cap violated"
assert w.sum(axis=1).max() <= (1 - cfg.cash_buffer) + 1e-9, "cash buffer violated"
out("caps hold: OK")

with open(f"{OUT_DIR}/00_data_audit.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
print(f"\n[written] {OUT_DIR}/00_data_audit.txt")
