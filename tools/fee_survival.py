"""Fee-survival analysis over the HFT matrix raw results (phase 2).

For every (symbol, timeframe, algo) row:
  - taker scenario is what the sweep measured (5bps fee + 3bps slip per side)
  - maker scenario re-prices the SAME trades at 1bps maker + 0 slip
    (approximation: ret_maker ~= ret_taker + trades * round_trip_cost_delta,
     where cost delta = 2*(8bps) applied to average notional share of equity)

Outputs a ranked survival table: which algos stay green at each timeframe
under taker, and which flip positive only under maker execution.
"""

from __future__ import annotations

import json
from pathlib import Path

RAW = Path("PROJECT_MEMORY/30_hft_matrix_raw.json")
OUT = Path("PROJECT_MEMORY/31_Fee_Survival.md")

TAKER_RT_COST = 2 * (5 + 3) / 10_000   # 16bps round trip
MAKER_RT_COST = 2 * (1 + 0) / 10_000   # 2bps round trip (VIP0 maker 1bp)


def main() -> None:
    rows = json.loads(RAW.read_text())
    valid = [r for r in rows if r.get("error") is None]

    # average equity fraction per trade ~1.0 for rf=1.0 strategies; the delta
    # below scales the measured return by the realized trade count.
    lines = [
        "# Fee survival — taker vs maker execution (2026-08-23 night analysis)",
        "",
        "Sweep measured taker costs (5bps+3bps/side). Maker column re-prices",
        "the same trade counts at 1bps maker / no slip. `flips` = losers at",
        "taker that become winners at maker => maker-only execution candidates.",
        "",
    ]
    flips_by_tf: dict[str, list] = {}
    survivors_by_tf: dict[str, list] = {}

    for sym in ("BTCUSDT", "ETHUSDT"):
        for tf in ("1m", "5m", "15m", "1h", "4h", "1d"):
            grid = [r for r in valid if r["symbol"] == sym and r["tf"] == tf]
            if not grid:
                continue
            table_rows = []
            for r in grid:
                n = r.get("trades") or 0
                ret_t = r.get("ret") or 0.0
                # return scales with compounding; linear fee adjustment on the
                # arithmetic return is a good first-order approximation here.
                ret_m = ret_t + n * (TAKER_RT_COST - MAKER_RT_COST)
                r["ret_maker_est"] = ret_m
                if ret_t > 0:
                    survivors_by_tf.setdefault(f"{sym} {tf}", []).append(
                        (r["name"], ret_t, ret_m))
                elif ret_m > 0 and n > 0:
                    flips_by_tf.setdefault(f"{sym} {tf}", []).append(
                        (r["name"], ret_t, ret_m))

            lines.append(f"## {sym} {tf}")
            lines.append("")
            lines.append("| survivor at taker | ret | | maker-flip candidates | ret(t) | ret(m) est |")
            lines.append("|---|---|---|---|---|---|")
            surv = sorted(survivors_by_tf.get(f"{sym} {tf}", []),
                          key=lambda x: x[1], reverse=True)[:8]
            flips = sorted(flips_by_tf.get(f"{sym} {tf}", []),
                           key=lambda x: x[2], reverse=True)[:8]
            for i in range(max(len(surv), len(flips))):
                left = f"{surv[i][0]} | {surv[i][1]:.1%} |" if i < len(surv) else " | |"
                right = (f"{flips[i][0]} | {flips[i][1]:.1%} | {flips[i][2]:.1%} |"
                         if i < len(flips) else " | |")
                lines.append(f"| {left} {right} |")
            lines.append("")

    OUT.write_text("\n".join(lines))
    print(f"wrote {OUT}")
    print("survivor counts:", {k: len(v) for k, v in sorted(survivors_by_tf.items())})
    print("flip counts:", {k: len(v) for k, v in sorted(flips_by_tf.items())})

    # persist enriched rows for phase 3 selection
    Path("PROJECT_MEMORY/30_hft_matrix_raw_enriched.json").write_text(
        json.dumps(valid, indent=1))


if __name__ == "__main__":
    main()
