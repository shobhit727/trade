"""`nsealgo` CLI — the single entrypoint used by Docker, tests and humans.

    python -m nsealgo.cli --help
    python -m nsealgo.cli validate --walk-forward
    python -m nsealgo.cli paper --cycles 4
    python -m nsealgo.cli limits
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from decimal import Decimal as D

import pandas as pd

from .backtest.engine import PortfolioConfig, run_backtest
from .backtest.metrics import compute_metrics
from .backtest.walkforward import walk_forward
from .costs import CostModel
from .data.loader import load_universe
from .factors.core import build_composite_score
from .factors.regime import blend_with_cash, exposure_series, market_proxy
from .risk.limits import LIMITS, limits_as_dict

log = logging.getLogger("nsealgo.cli")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def _load(data_dir: str):
    panel, symbols, report = load_universe(data_dir)
    return panel, symbols, report


# --------------------------------------------------------------------------- #


def cmd_audit(args: argparse.Namespace) -> int:
    panel, symbols, report = _load(args.data_dir)
    print(report.describe())
    print(f"{len(symbols)} symbols | {panel.index[0].date()} -> {panel.index[-1].date()}")
    return 0


def cmd_costs(args: argparse.Namespace) -> int:
    cm = CostModel(segment="delivery", slippage_bps=5)
    print("Indian delivery cost model (slippage 5bps/side):")
    print(f"{'notional/side':>14} {'round-trip bps':>16}")
    for n in (20_000, 50_000, 100_000, 200_000, 500_000, 2_100_000):
        print(f"{n:>14,} {cm.round_trip_bps(D(n)):>16}")
    print("\nPublished reference: 11.65-11.66 bps (two independent itemisations).")
    print("Our model at Rs 1,00,000/side matches.")
    if args.json:
        print(json.dumps(
            {str(n): str(cm.round_trip_bps(D(n)))
             for n in (100_000, 2_100_000)}, indent=2))
    return 0


def cmd_limits(args: argparse.Namespace) -> int:
    print("GOAL.md §3.3 hard risk limits (NOT configurable):")
    for k, v in limits_as_dict().items():
        print(f"  {k:<26} {v}")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    panel, symbols, _ = _load(args.data_dir)
    score = build_composite_score(panel)
    res = run_backtest(
        panel, score, CostModel(segment="delivery", slippage_bps=5),
        PortfolioConfig(n_positions=args.positions), rebalance=args.rebalance,
    )
    bm = compute_metrics(market_proxy(panel).fillna(0.0))
    print(f"Universe: {len(symbols)} symbols, {len(panel)} days\n")
    print("STRATEGY (in-sample, full cost stack)")
    print(res.summary())
    print("\nBENCHMARK equal-weight buy&hold")
    print(bm.fmt())
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Walk-forward validation. The only result that counts (GOAL.md §5)."""
    panel, symbols, _ = _load(args.data_dir)
    base = CostModel(segment="delivery", slippage_bps=5)

    def run_fn(pnl: pd.DataFrame, params: dict):
        sc = build_composite_score(pnl)
        cfg = PortfolioConfig(n_positions=params["n_positions"])
        res = run_backtest(pnl, sc, base, cfg, "M")
        ov = exposure_series(pnl, lookback=params["lookback"],
                             threshold=params["threshold"])
        comb = pd.Series(blend_with_cash(res.returns, ov), index=res.returns.index)
        res.returns = comb
        res.metrics = compute_metrics(comb)
        return res

    grid = [
        {"n_positions": n, "lookback": lb, "threshold": t}
        for n in (15, 22, 30)
        for lb in (126, 252)
        for t in (0.0, 0.35, 0.6)
    ]
    wf = walk_forward(panel, grid, run_fn, n_folds=args.folds,
                      train_years=6, test_years=2)
    print(f"Universe: {len(symbols)} symbols\n")
    print(wf.summary())
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    from .live.engine import build_paper_engine

    panel, symbols, report = _load(args.data_dir)
    print(report.describe())
    print("\nPAPER MODE — no capital, no orders leave this process.")
    print(f"Capital: Rs {LIMITS.initial_capital:,} | universe {len(symbols)}")

    eng, broker = build_paper_engine(panel)
    dates = panel.index[-args.cycles:]
    for i, d in enumerate(dates):
        window = panel.loc[:d]
        eng.load_market_data(window)
        rep = eng.run_cycle(d)
        print(f"  {rep.summary()}")
        if i == 0:
            print(f"  risk limits in force: drawdown halt "
                  f"-{LIMITS.max_drawdown_halt:.0%}, daily "
                  f"-{LIMITS.max_daily_loss:.0%}")
    print(f"\nfinal paper equity: Rs {broker.portfolio_value():,.0f}")
    print(f"costs charged (real stack): Rs {broker.total_costs:,.0f}")
    return 0


def cmd_flatten(args: argparse.Namespace) -> int:
    from .execution.kite import KiteBroker
    from .live.engine import Engine

    b = KiteBroker()
    if not b.configured:
        print("KITE_API_KEY / KITE_ACCESS_TOKEN not set — refusing to pretend.", file=sys.stderr)
        return 2
    eng = Engine(broker=b)
    n = eng.flatten(reason=args.reason)
    print(f"flattened {n} positions ({args.reason})")
    return 0


# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("nsealgo", description="NSE NIFTY-50 systematic trading")
    p.add_argument("--data-dir", default="data/nse")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("audit", help="data audit + cleaning report").set_defaults(fn=cmd_audit)
    cs = sub.add_parser("costs", help="cost model calibration")
    cs.add_argument("--json", action="store_true")
    cs.set_defaults(fn=cmd_costs)
    sub.add_parser("limits", help="print hard risk limits").set_defaults(fn=cmd_limits)

    b = sub.add_parser("backtest", help="single in-sample backtest")
    b.add_argument("--positions", type=int, default=22)
    b.add_argument("--rebalance", default="M")
    b.set_defaults(fn=cmd_backtest)

    v = sub.add_parser("validate", help="walk-forward out-of-sample validation")
    v.add_argument("--folds", type=int, default=6)
    v.add_argument("--walk-forward", action="store_true", default=True)
    v.set_defaults(fn=cmd_validate)

    pa = sub.add_parser("paper", help="run paper trading cycles")
    pa.add_argument("--cycles", type=int, default=5)
    pa.set_defaults(fn=cmd_paper)

    fl = sub.add_parser("flatten", help="go flat on the live account")
    fl.add_argument("--reason", default="manual")
    fl.set_defaults(fn=cmd_flatten)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.verbose)
    return int(args.fn(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
