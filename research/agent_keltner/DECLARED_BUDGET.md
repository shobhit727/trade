# DECLARED PARAMETER BUDGET — `keltner_channel` on NSE NIFTY-50

Written **before any backtest was run**. Per brief §4, exceeding 5 distinct parameter
variants invalidates the run. Budget = **5**. Nothing below may be added after TEST
is touched.

## The strategy

`src/cryptobot/strategies/catalog/keltner_channel.py` delegates to
`cryptobot.strategies.indicators.keltner_mid` (an EMA of closes) and
`cryptobot.strategies.indicators.atr` (simple mean of the last `period` true ranges):

```
mid = ema(closes, period)                       # prefix-stable recursion, seeded at bar 0
b   = mean(TR[last period])                     # TR = max(h-l, |h-pc|, |l-pc|)
+1  if close < mid - multiplier * b             # close BELOW lower Keltner band  -> LONG
-1  if close > mid + multiplier * b             # close ABOVE upper Keltner band  -> SHORT
 0  otherwise
```

Defaults: `period=20, multiplier=2.0`.

This is a **mean-reversion / volatility-band** signal — emphatically **not**
crypto-specific (no funding, no liquidations, no pegs, no options IV, no spot-futures
basis), so it has a legitimate NSE interpretation and is **in scope**.

## NSE adaptation (brief §5)

The NSE book is long-only; an Indian delivery account cannot short. The `-1` upper-band
leg is therefore dropped. The NSE strategy is the LONG leg only:

> Hold names whose close is below their `period`-day EMA by more than
> `multiplier x ATR(period)`.

The two score constructions differ so the result can be decomposed rather than blurred:

* **`pure`** — rank gated names by *band depth*: how many ATRs below the lower band the
  close sits. This isolates the Keltner signal.
* **`hybrid`** — rank gated names by **126-day momentum** (brief §5's recipe). This is a
  Keltner + momentum *hybrid*; its performance is **not** attributable to Keltner alone
  and is labelled as such wherever it appears.

## The 5 variants (exhaustive — this list is closed)

| # | name | period | multiplier | construction | note |
|---|------|--------|-----------|--------------|------|
| V1 | `kelt_pure_p20_m2`    | 20 | 2.0 | `pure`   | catalog defaults |
| V2 | `kelt_hybrid_p20_m2`  | 20 | 2.0 | `hybrid` | catalog defaults + brief §5 recipe |
| V3 | `kelt_pure_p20_m25`   | 20 | 2.5 | `pure`   | rarer/deeper band touch |
| V4 | `kelt_pure_p40_m2`    | 40 | 2.0 | `pure`   | slower EMA, longer ATR |
| V5 | `kelt_hybrid_p20_m25` | 20 | 2.5 | `hybrid` | rarer gate + momentum rank |

Rationale for the spread: V1/V2 establish the default reading in both constructions;
V3/V5 test whether the gate is too frequent (2.5 ATRs is a genuinely rarer event);
V4 tests whether a slower mid-line/ATR changes the character of the signal.

**Not tested** (deliberately, so the budget is not exceeded): multiplier 1.5 or 3.0,
periods 10/30/60, weekly rebalance, and any threshold tuned after seeing equity.
The multiplier/period grid was fixed by the *shape* of the indicator, not by results.

## Selection rule — fixed in advance, TRAIN only

1. Compute all 5 on **TRAIN (2016-01-01 → 2023-12-31) only**.
2. **Liveness gate first:** a variant whose TRAIN `avg_names` < 8 is disqualified as
   "effectively always-flat" (brief §6.3). Disqualified variants cannot win.
3. Among survivors, select **highest TRAIN Sharpe** (Sharpe is risk-adjusted, which
   brief §7 asks for; CAGR alone is a trap).
4. Tie within 0.05 Sharpe → prefer higher TRAIN Calmar (drawdown-adjusted).
5. If no variant clears the liveness gate, report that as the finding and stop; do not
   widen the budget.

## Protocol commitments

* TRAIN selection script physically truncates the panel at 2023-12-31 in-process and
  `assert`s it, so it is structurally incapable of seeing TEST.
* TEST is touched exactly once, in `03_test_eval.py`, which reads the frozen selection
  from JSON and chooses nothing.
* All numbers reported from `run_backtest` are **net of 21.92 bps**
  (`all_in_round_trip_bps(100_000)` = 11.92 statutory + 2x5 bps slippage).