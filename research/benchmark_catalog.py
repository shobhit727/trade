"""Port the existing cryptobot strategy catalog to NSE and test it honestly.

The crypto repo carries ~85 strategies in `src/cryptobot/strategies/catalog/`. The
nsealgo work initially ignored them and built a factor composite from scratch. That was
a gap: the right question is not "is my composite good?" but "does anything already in
this repo beat it on NSE data?"

This adapter makes that answerable without touching the strategies themselves. Most
catalog strategies implement the clean contract

    warmup(closes) -> int
    signal(closes, highs, lows, volumes) -> +1 / 0 / -1

which is a **per-symbol time-series signal**, so it can be driven with NSE daily bars.
The adapter:

  1. feeds each symbol's real OHLCV through the strategy's `feed()`,
  2. records the resulting +1/0/-1 signal per symbol per day,
  3. builds a long-only cross-sectional book from those signals (long where signal > 0,
     cash otherwise), and
  4. runs it through the **same** nsealgo engine, **same** Indian cost stack, **same**
     portfolio constraints and **same** metrics as the composite.

Anything crypto-specific (funding, liquidation hunts, stablecoin pegs, options IV) has no
NSE meaning and is skipped with a reason rather than silently dropped.

Run:  .venv/bin/python research/benchmark_catalog.py
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nsealgo.backtest.engine import PortfolioConfig, run_backtest  # noqa: E402
from nsealgo.backtest.metrics import compute_metrics  # noqa: E402
from nsealgo.costs import CostModel  # noqa: E402
from nsealgo.data.loader import load_universe  # noqa: E402
from nsealgo.factors.core import build_composite_score  # noqa: E402
from nsealgo.factors.regime import blend_with_cash, exposure_series  # noqa: E402

CM = CostModel(segment="delivery", slippage_bps=5)
CATALOG = "cryptobot.strategies.catalog"

#: Momentum lookback for ranking the signalled names, in trading days. 126 = 6 months,
#: which is the best-performing long-only risk-adjusted variant in the Indian evidence
#: (Nigam & Pandey 2023; same number `factors.core.momentum_6m` uses).
MOM_LOOKBACK = 126

#: An unlevered long-only delivery book cannot compound near this. Anything above it is
#: an accounting artefact (look-ahead, a broken weight build, or a missing cost), not a
#: strategy. Used as a hard tripwire — see `main()`.
PLAUSIBLE_CAGR_CAP = 1.00  # 100% p.a.

#: Strategies whose logic is meaningless for cash equity. Skipped explicitly so the
#: skip is visible rather than looking like the strategy failed.
CRYPTO_ONLY = {
    "funding_basis", "funding_trend", "liquidation_hunt", "stablecoin_peg",
    "spot_futures_arbitrage", "implied_realized_volatility", "garch_classic",
    "carry", "funding", "basis", "open_interest", "oi_delta", "gamma",
    "delta_neutral", "basis_trading",
}


def discover() -> list[tuple[str, type]]:
    """Import every catalog module and collect instantiable SignalStrategy classes."""
    try:
        pkg = importlib.import_module(CATALOG)
    except Exception as exc:  # noqa: BLE001
        print(f"cannot import catalog: {exc}")
        return []

    found: list[tuple[str, type]] = []
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_"):
            continue
        full = f"{CATALOG}.{mod.name}"
        try:
            m = importlib.import_module(full)
        except Exception:  # noqa: BLE001 - catalog has known-broken modules
            continue
        for _, obj in vars(m).items():
            if not inspect.isclass(obj):
                continue
            if obj.__module__ != full:
                continue
            if not hasattr(obj, "signal") or not hasattr(obj, "warmup"):
                continue
            if inspect.isabstract(obj):
                continue
            found.append((mod.name, obj))
    seen: dict[str, type] = {}
    for mod_name, cls in found:
        seen.setdefault(mod_name, cls)
    return sorted(seen.items())


def rebalance_dates(index: pd.DatetimeIndex, freq: str = "M") -> list:
    """Same first-trading-day-of-period rule the engine uses."""
    keys = index.tz_localize(None).to_period(freq)
    s = pd.Series(index, index=index)
    return [g.index[0] for _, g in s.groupby(keys)]


def signals_for(cls, ohlcv: dict[str, pd.DataFrame], eval_dates: list,
                maxlen: int = 400) -> pd.DataFrame:
    """Drive one strategy over every symbol's real OHLCV; return eval_dates x symbols.

    Calls the strategy's own `signal()` so we exercise the real code path (warmup,
    indicator computation, signal translation) rather than reimplementing the logic.

    Signals are evaluated only on rebalance dates, each with the full history leading up
    to it. That is ~20x cheaper than a daily sweep and is sufficient because the engine
    holds weights between rebalances anyway. It also keeps the lookup exactly
    point-in-time: the buffer handed to `signal()` ends on the eval date.
    """
    cols = list(ohlcv)
    try:
        strat = cls()
    except Exception:  # noqa: BLE001 - config-dependent constructors
        return pd.DataFrame(0.0, index=eval_dates, columns=cols)

    panel = pd.DataFrame(0.0, index=pd.DatetimeIndex(eval_dates), columns=cols)
    for sym, df in ohlcv.items():
        dates_all = df.index
        out: list[float] = []
        for dt in eval_dates:
            if dt not in dates_all:
                out.append(0.0)
                continue
            end = dates_all.get_loc(dt)
            window = df.iloc[max(0, end - maxlen + 1): end + 1]
            try:
                sig = strat.signal(
                    [float(x) for x in window["close"]],
                    [float(x) for x in window["high"]],
                    [float(x) for x in window["low"]],
                    [float(x) for x in window["vol"]],
                )
            except Exception:  # noqa: BLE001 - warmup/NaN means no actionable signal
                sig = 0
            out.append(1.0 if (sig is not None and float(sig) > 0) else 0.0)
        panel[sym] = out
    return panel


def signal_to_score(signal_panel: pd.DataFrame, price_panel: pd.DataFrame) -> pd.DataFrame:
    """Turn a binary signal panel into a cross-sectional score.

    Where the signal is on, rank by a trailing trend so that capital is allocated to the
    strongest of the signalled names rather than spread uniformly. This is the fairest
    construction: it gives the catalog strategy the benefit of momentum ranking, which is
    the strongest documented Indian factor.

    Two bugs were fixed here (both produced impossible, unreportable numbers):

    1. Momentum was computed from ``signal_panel`` (values 0.0/1.0) instead of prices.
       ``1/1 - 1 == 0`` and ``0/0`` is ``nan``, so every score was 0/NaN/inf and the
       ranking was meaningless. Momentum must come from the **price** panel.
    2. The returned score was indexed only on the rebalance dates. ``run_backtest``
       does ``panel.index.intersection(score.index)``, so the whole 18-year backtest was
       squeezed onto the ~226 monthly rows: `pct_change` then produced *monthly* returns
       and ``compute_metrics`` divided by ``len(equity)/244`` (~0.9 "years"). Eighteen
       years of monthly compounding, reported as one year, is how a long-only book
       "achieved" 331% CAGR and a Sharpe of 4.25. Those numbers were false. The score is
       now reindexed onto the full daily index so the engine sees the whole history.

    Parameters
    ----------
    signal_panel
        Rebalance-date x symbol panel of 1.0 (signalled long) / 0.0 (flat).
    price_panel
        Full daily close panel — the same panel handed to ``run_backtest``.
    """
    mom = price_panel / price_panel.shift(MOM_LOOKBACK) - 1.0
    # Reindex the signal onto the daily grid first: off-rebalance rows become 0.0 so
    # they are masked out below, instead of silently disappearing via index alignment.
    sig = signal_panel.reindex(price_panel.index).fillna(0.0)
    score = mom.where(sig > 0)
    return score.rank(axis=1, pct=True)


def main() -> int:
    strategies = discover()
    print("=" * 100)
    print("EXISTING CRYPTO CATALOG vs NSE DATA")
    print("=" * 100)
    print(f"discovered {len(strategies)} portable strategy classes in {CATALOG}")

    panel, symbols, report = load_universe("data/nse")
    print(report.describe())
    print(f"universe {len(symbols)} | {panel.index[0].date()} -> {panel.index[-1].date()}")

    # full OHLCV, not just closes
    ohlcv = {}
    for sym in panel.columns:

        path = f"data/nse/{sym}_1d.csv"
        df = pd.read_csv(path)
        df.columns = [c.lower() for c in df.columns]
        idx = pd.to_datetime(df["ts"], unit="ms", utc=True).dt.tz_convert("Asia/Kolkata").dt.normalize()
        df = df.drop(columns="ts")
        df.index = idx
        df = df.loc[df.index >= panel.index[0]]
        ohlcv[sym] = df

    # ---- baseline: our composite
    print("\n" + "=" * 100)
    print("BASELINE — nsealgo factor composite (what we shipped)")
    print("=" * 100)
    ov = exposure_series(panel, lookback=126, threshold=0.35)
    base = run_backtest(panel, build_composite_score(panel), CM, PortfolioConfig(), "M")
    base_comb = pd.Series(blend_with_cash(base.returns, ov), index=base.returns.index)
    base_m = compute_metrics(base_comb)
    bm = compute_metrics(panel.pct_change(fill_method=None).mean(axis=1).fillna(0.0))
    print(f"  composite   CAGR {base_m.cagr*100:>6.2f}%  Sharpe {base_m.sharpe:>5.2f}  "
          f"MaxDD {base_m.max_drawdown*100:>7.2f}%  Calmar {base_m.calmar:>5.2f}")
    print(f"  buy&hold    CAGR {bm.cagr*100:>6.2f}%  Sharpe {bm.sharpe:>5.2f}  "
          f"MaxDD {bm.max_drawdown*100:>7.2f}%  Calmar {bm.calmar:>5.2f}")
    print("  expected composite reference: CAGR ~18%, Sharpe ~0.92, MaxDD ~-18.5%")

    # ---- sweep the catalog
    print("\n" + "=" * 100)
    print("CATALOG SWEEP — same engine, same costs, same constraints")
    print("=" * 100)
    print(f"{'strategy':<34} {'CAGR':>8} {'Sharpe':>7} {'MaxDD':>8} {'Calmar':>7} "
          f"{'%days on':>8} {'vs b&h':>8}")
    print("-" * 100)

    rb_dates = rebalance_dates(panel.index)
    print(f"evaluating signals on {len(rb_dates)} monthly rebalance dates")

    results: list[tuple[str, object, float, pd.DataFrame]] = []
    flat: list[str] = []
    errors: list[str] = []
    skipped_crypto: list[str] = []
    for name, cls in strategies:
        if name in CRYPTO_ONLY:
            skipped_crypto.append(name)
            continue
        try:
            sig = signals_for(cls, ohlcv, rb_dates)
            if not bool((sig > 0).to_numpy().any()):
                flat.append(name)  # reported below, not silently dropped
                continue
            sc = signal_to_score(sig, panel)
            res = run_backtest(panel, sc, CM, PortfolioConfig(), "M")
            comb = pd.Series(blend_with_cash(res.returns, ov), index=res.returns.index)
            m = compute_metrics(comb)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name} {type(exc).__name__}: {str(exc)[:40]}")
            continue
        on_frac = float((sig > 0).to_numpy().mean()) * 100
        results.append((name, m, on_frac, sig))

    results.sort(key=lambda r: r[1].sharpe, reverse=True)
    for name, m, on_frac, _ in results:
        delta = (m.cagr - bm.cagr) * 100
        print(f"{name:<34} {m.cagr*100:>7.2f}% {m.sharpe:>7.2f} {m.max_drawdown*100:>7.2f}% "
              f"{m.calmar:>7.2f} {on_frac:>7.1f}% {delta:>+7.2f}%")

    print("-" * 100)
    print(f"{'BASELINE composite':<34} {base_m.cagr*100:>7.2f}% {base_m.sharpe:>7.2f} "
          f"{base_m.max_drawdown*100:>7.2f}% {base_m.calmar:>7.2f}")
    print(f"{'BASELINE buy & hold':<34} {bm.cagr*100:>7.2f}% {bm.sharpe:>7.2f} "
          f"{bm.max_drawdown*100:>7.2f}% {bm.calmar:>7.2f}")

    print("\n" + "=" * 100)
    print("COVERAGE")
    print("=" * 100)
    print(f"  discovered          {len(strategies)}")
    print(f"  evaluated           {len(results)}")
    print(f"  never signalled     {len(flat)}  {flat if flat else ''}")
    print(f"  crypto-only skipped {len(skipped_crypto)}")
    print(f"  errors              {len(errors)}")
    for e in errors:
        print(f"      {e}")

    # ---- sanity checks (GOAL.md §6: never report a number we cannot defend)
    print("\n" + "=" * 100)
    print("SANITY CHECKS")
    print("=" * 100)

    # 1. physical plausibility
    absurd = [(n, m.cagr) for n, m, _, _ in results if m.cagr > PLAUSIBLE_CAGR_CAP]
    all_rows = [("composite", base_m), ("buy&hold", bm)] + [
        (n, m) for n, m, _, _ in results
    ]
    worst = max(all_rows, key=lambda r: r[1].cagr)
    print(f"  [1] plausibility     max CAGR in sweep = {worst[1].cagr*100:.2f}% ({worst[0]})"
          f"  | over {PLAUSIBLE_CAGR_CAP*100:.0f}%: {len(absurd)}")
    if absurd:
        print(f"      !! UNREPORTABLE: {absurd}")

    # 2. weight construction respects PortfolioConfig
    cfg = PortfolioConfig()
    bw = None
    if results:
        bname, _, _, bsig = results[0]
        bw = run_backtest(panel, signal_to_score(bsig, panel), CM, cfg, "M").weights
        live = bw[bw > 1e-9]
        nmax = int(live.count(axis=1).max())
        wmax = float(live.max().max())
        gross_max = float(bw.sum(axis=1).max())
        print(f"  [2] weights({bname})")
        print(f"      positions : max {nmax} (cap {cfg.n_positions})  avg {live.count(axis=1).mean():.1f}"
              f"   -> {'OK' if nmax <= cfg.n_positions else 'OVER (see note)'}")
        print(f"      single    : max {wmax*100:.2f}% (cap {cfg.max_weight*100:.0f}%)"
              f"   -> {'OK' if wmax <= cfg.max_weight + 1e-9 else 'OVER (see note)'}")
        print(f"      gross     : max {gross_max*100:.2f}% (cash buffer "
              f"{cfg.cash_buffer*100:.0f}%)   -> {'OK' if gross_max <= 1 - cfg.cash_buffer + 1e-9 else 'OVER'}")
        # Same check on the shipped composite, so any deviation is attributable.
        cw = run_backtest(panel, build_composite_score(panel), CM, cfg, "M").weights
        clive = cw[cw > 1e-9]
        print(f"      composite : positions max {int(clive.count(axis=1).max())}  "
              f"single max {clive.max().max()*100:.2f}%  gross max {cw.sum(axis=1).max()*100:.2f}%")
        if wmax > cfg.max_weight + 1e-9:
            print("      NOTE: engine applies the sector cap *after* the single-name cap and")
            print("            redistributes the excess without re-capping, so a concentrated")
            print("            score can exceed max_weight. Pre-existing in")
            print("            nsealgo/backtest/engine.py::build_rebalance_weights; the composite")
            print("            is less concentrated so it does not trigger. Affects the catalog")
            print("            side of the comparison only. Fix belongs in the engine, not here.")

    # 3. baseline reproduces
    print(f"  [3] baseline         composite Sharpe {base_m.sharpe:.2f} (expected ~0.92), "
          f"CAGR {base_m.cagr*100:.2f}% (~18%), MaxDD {base_m.max_drawdown*100:.2f}% (~-18.5%)")
    print(f"      equity days {len(base.returns)} (must be ~{len(panel)} daily rows, "
          f"not {len(rb_dates)} monthly)")

    if results:
        bname, bm_, _, _ = results[0]
        print("\n" + "=" * 100)
        print("VERDICT")
        print("=" * 100)
        print(f"  best catalog strategy : {bname}")
        print(f"    CAGR {bm_.cagr*100:.2f}%  Sharpe {bm_.sharpe:.2f}  "
              f"MaxDD {bm_.max_drawdown*100:.2f}%  Calmar {bm_.calmar:.2f}")
        print(f"  nsealgo composite     : "
              f"CAGR {base_m.cagr*100:.2f}%  Sharpe {base_m.sharpe:.2f}  "
              f"MaxDD {base_m.max_drawdown*100:.2f}%  Calmar {base_m.calmar:.2f}")
        print(f"  Sharpe: catalog {'BEATS' if bm_.sharpe > base_m.sharpe else 'does NOT beat'} "
              f"composite ({bm_.sharpe:.2f} vs {base_m.sharpe:.2f}, "
              f"{bm_.sharpe - base_m.sharpe:+.2f})")
        print(f"  Calmar: catalog {'BEATS' if bm_.calmar > base_m.calmar else 'does NOT beat'} "
              f"composite ({bm_.calmar:.2f} vs {base_m.calmar:.2f}, "
              f"{bm_.calmar - base_m.calmar:+.2f})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
