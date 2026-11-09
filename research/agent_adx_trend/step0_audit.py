"""Step 0 — audit the source strategy and confirm the data before spending budget."""

from __future__ import annotations

import sys

sys.path.insert(0, "research/agent_adx_trend")

import harness as H  # noqa: E402


def main() -> None:
    panel, symbols = H.load_panel()
    print("=" * 78)
    print("SOURCE SIGNAL AUDIT  (cryptobot/strategies/catalog/adx_trend.py)")
    print("=" * 78)
    for k, v in H.verify_source_signal().items():
        print(f"  {k:<28}{v}")

    print()
    print("=" * 78)
    print("DATA")
    print("=" * 78)
    print(f"  symbols={len(symbols)}  bars={len(panel)}  "
          f"{panel.index.min().date()} -> {panel.index.max().date()}")

    tr = panel.loc[H.TRAIN_START:H.TRAIN_END]
    te = panel.loc[H.TEST_START:H.TEST_END]
    print(f"  TRAIN {tr.index.min().date()} -> {tr.index.max().date()}  "
          f"bars={len(tr)}  names w/ >80% coverage="
          f"{int((tr.notna().mean() > 0.8).sum())}")
    print(f"  TEST  {te.index.min().date()} -> {te.index.max().date()}  "
          f"bars={len(te)}  names w/ >80% coverage="
          f"{int((te.notna().mean() > 0.8).sum())}")
    thin = sorted(set(tr.columns[tr.notna().mean() <= 0.5]))
    print(f"  names with <=50% TRAIN coverage (dropped from ranking universe): {thin}")

    print()
    print("=" * 78)
    print("COST MODEL")
    print("=" * 78)
    from decimal import Decimal  # noqa: PLC0415

    statutory = float(
        H.COST_MODEL.round_trip_bps(Decimal("100000"))
    )
    print(f"  statutory round trip @ Rs 1,00,000/side = {statutory:.2f} bps "
          f"(brief/CLI reference ~11.9)  [COST_MODEL.round_trip_bps]")
    print(f"  + slippage 5 bps x 2 legs              = {H.RT_BPS - statutory:.2f} bps")
    print(f"  ALL-IN used by the backtest engine     = {H.RT_BPS:.2f} bps "
          f"[all_in_round_trip_bps]")
    print("  -> the brief's 11.9 is statutory-only; the engine adds slippage, so 21.92")
    print("     is the honest figure and every number below is net of it.")
    for notional in (25_000, 50_000, 100_000, 200_000):
        d = Decimal(str(notional))
        print(f"    Rs {notional:>8,} -> statutory "
              f"{float(H.COST_MODEL.round_trip_bps(d)):>5.2f}  all-in "
              f"{float(H.COST_MODEL.all_in_round_trip_bps(d)):>5.2f} bps")

    print()
    print("=" * 78)
    print("SIGNAL LIVENESS  (fraction of name-days the strategy is LONG)")
    print("=" * 78)
    flag = H.signal_flag(panel)
    print(f"  full history      {(flag > 0).to_numpy().mean() * 100:.2f}%")
    print(f"  TRAIN             {(flag.loc[H.TRAIN_START:H.TRAIN_END] > 0).to_numpy().mean() * 100:.2f}%")
    print(f"  TEST              {(flag.loc[H.TEST_START:H.TEST_END] > 0).to_numpy().mean() * 100:.2f}%")
    print("  (brief's liveness floor is ~5%; anything below is effectively flat)")

    print()
    print("=" * 78)
    print("DECLARED PARAMETER BUDGET -- 5 variants, written before any run")
    print("=" * 78)
    for k, v in H.VARIANTS.items():
        print(f"  {k:<12}{v}")
    print(f"  held constant: {H.FIXED}")
    print("  selection rule: highest TRAIN Sharpe (tie-break Calmar), "
          "then ONE frozen run on TEST")


if __name__ == "__main__":
    main()
