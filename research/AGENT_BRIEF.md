# AGENT BRIEF — make one catalog strategy work on NSE NIFTY-50

You have been assigned **exactly one** strategy file. Your job: make it work and make
money on NSE data, honestly.

Read this file first, completely. Then do the work. Do not ask questions — make the
judgement calls yourself and record them.

---

## 1. Your assignment

Your strategy is named in your task prompt, e.g. `supertrend_strategy`.
Its source: `src/cryptobot/strategies/catalog/<name>.py`

---

## 2. Data — already on disk, do not download anything

```
data/nse/<symbol>_<tf>.csv     columns: ts,open,high,low,close,vol   (ts = epoch ms)
```

| Timeframe | Symbols | Span | Use it for |
|-----------|---------|------|-----------|
| `1d` | 50 | 2002-07-01 → 2026-10-01 | **PRIMARY.** daily-bar strategies |
| `1h` | 50 | 2024-11-18 → 2026-10-06 | intraday strategies, ~2y |
| `5m` | 50 | 2026-08-18 → 2026-10-06 | ~7 weeks only |
| `15m` | 50 | 2026-08-18 → 2026-10-06 | ~7 weeks only |

There is **no 1m and no 30m data** (5m/15m cover only ~7 weeks, far too short to
validate anything). Do not attempt intraday work on 5m/15m and call the result
validated — you can report an observation, but you must label it as ~7 weeks,
single-regime, not evidence of an edge.

Symbols are NSE names (RELIANCE, TCS, HDFCBANK…). ~50 of them.

### Mandatory first step
```python
import sys; sys.path.insert(0, "src")
from nsealgo.data.loader import load_universe
panel, symbols, report = load_universe("data/nse")   # cleaned daily close panel
print(report.describe())
```
`load_universe` already applies the cleaning rules (drops pre-2008 vendor artifacts,
non-positive prices, impossible moves) and returns an auditable report.

---

## 3. Infrastructure you MUST reuse — do not reinvent

| Need | Use |
|------|-----|
| Indian cost stack | `from nsealgo.costs import CostModel` — `CostModel(segment="delivery", slippage_bps=5)` |
| Cost sanity check | `.venv/bin/python -m nsealgo.cli costs` |
| Portfolio/backtest | `from nsealgo.backtest.engine import PortfolioConfig, run_backtest, build_rebalance_weights` |
| Metrics | `from nsealgo.backtest.metrics import compute_metrics, yearly_returns` |
| Factors (for ranking) | `from nsealgo.factors.core import build_composite_score, zscore_cross_sectional, rank_cross_sectional` |
| Risk overlay (optional) | `from nsealgo.factors.regime import exposure_series, blend_with_cash` |

**Costs are mandatory.** Every result you report must be net of the full Indian
delivery stack. A result that only works at zero cost is not a result.

Use the **right number**:
- `round_trip_bps(100_000)` = **11.92 bps** — statutory charges only (STT, stamp,
  exchange txn, SEBI, DP, GST).
- `all_in_round_trip_bps(100_000)` = **21.92 bps** — what `run_backtest` actually
  charges, because a portfolio simulator never calls `fill_price`, so the engine folds
  in slippage as `rt_bps + 2 × slippage_bps`.

**When you backtest via `run_backtest`, report results net of 21.92 bps.** Report the
11.92 figure only if you are calling `CostModel` directly. Do not mix the two. Reporting
a gross-of-slippage number as if it were fully loaded is the single most common way a
result in this project gets overstated.

---

## 4. THE PROTOCOL — this is the part that decides whether your work means anything

Your strategy will make money on the last 6 months if you let it. So will a random
coin. The only thing that separates them is whether it still works on data it has
never seen.

**Split (non-negotiable):**

| Set | Window | Purpose |
|-----|--------|---------|
| **TRAIN** | 2016-01-01 → 2023-12-31 | everything you tune on |
| **TEST** | 2024-01-01 → 2026-10-01 | touched exactly once, at the end |

Rules:
1. Choose parameters on **TRAIN only**.
2. Then evaluate **unchanged** on TEST.
3. Report the **TEST** numbers. Label every number TRAIN or TEST.
4. Never look at TEST while iterating. If you do, say so in your report — that is a
   failed run and I need to know.
5. Also report the TEST result of **buy-and-hold** over the identical window
   (`panel.pct_change().mean(axis=1)`), net of the same costs. Beating nothing is
   not beating the market.

**Parameter budget — declare it before you start, in your report:**
You may test at most **5 distinct parameter variants** of your strategy. Write the list
down first, then run them. Exceeding 5 invalidates the run — report that it happened
rather than hiding it. You may NOT tune thresholds until the equity curve looks good.

**No lookahead.** Decisions on day *t* may only use data up to *t*. If you forward-fill,
forward-fill from the past, never from the future.

---

## 5. Construction guidance (the strategy is time-series; the book is cross-sectional)

Most catalog strategies are **per-symbol time-series indicators** returning +1/0/−1.
The NSE book is **long-only and cross-sectional**. So:

- Turn your signal into a cross-sectional score. A strong, proven approach: rank the
  signalled names by trailing momentum among the ones your strategy flags.
  ```python
  score = (panel/panel.shift(126) - 1.0).where(signal_panel > 0).rank(axis=1, pct=True)
  ```
- Respect the portfolio constraints in `PortfolioConfig` (22 names, 12% single name,
  25% sector, 10% cash buffer). `run_backtest` enforces these — do not bypass them.
- Long-only: never short. Shorting is not available in an Indian delivery account.

---

## 6. Sanity checks before you report — run these or your number is probably wrong

1. **Plausibility.** An unlevered long-only NIFTY-50 book cannot exceed roughly 40–50%
   CAGR. If you produce 200%+, you have a bug — usually a lookahead, a mis-indexed
   score panel, or a compounding bug. Find it before reporting.
2. **Weight count.** Print the average number of names held. If it is 48 rather than
   ~22, your residual weights are accumulating — that was a real bug here before.
3. **Signal liveness.** Print what fraction of bars your strategy is long. If it is
   below ~5%, it is effectively always-flat and "loses only to costs" — say so.
4. **Cost drag.** Report it. If gross return is positive but net is negative, the
   strategy is unviable and that is the finding.
5. **Negative control.** Report whether your strategy beat a **random** signal with the
   same % of bars long. Beating a coin flip is the minimum bar.

---

## 7. What to report (be concise, be honest)

1. Strategy name, what signal it generates, and the exact variants you tested
   (your declared budget).
2. **TEST** (out-of-sample) table: CAGR, Sharpe, MaxDD, Calmar, turnover/yr, cost
   drag, avg names held.
3. Same metrics for **buy-and-hold** over the identical TEST window.
4. TEST vs buy-and-hold: better or worse, by how much, on return AND on drawdown.
5. Random-signal control result.
6. Did it beat the nsealgo composite? (`build_composite_score` on the same panel.)
7. **Plain verdict in one sentence**: does this strategy make money on NSE, yes or no?
8. If it failed, state the most likely reason and the one thing you would try next.

**Do not oversell.** A strategy that loses out-of-sample is a useful, publishable
result. A strategy that only wins in-sample is a trap, and reporting it as a win is
worse than reporting nothing.

## 8. Write your report EARLY and incrementally

This work may be interrupted. Structure your output so nothing is lost:

1. Write `research/agent_<name>/REPORT.md` with the header, assigned strategy, declared
   parameter budget, and data used **before you run anything**. Commit to it early.
2. Append results as you get them. A partial report with real numbers beats a complete
   report that never got written.
3. If you find a bug — in your strategy, in your harness, or in `src/nsealgo` — write
   it down immediately and separately. Bugs are the most valuable output here.

## 9. Rules

- Write scratch scripts under `research/agent_<yourstrategy>/`. Do not modify
  `src/nsealgo/**`, `src/cryptobot/**`, or any test file.
- Lint with `.venv/bin/ruff check <your files>`.
- Do NOT commit or push.
- Do not modify `GOAL.md` or anything in `reports/`.
- If your strategy is crypto-specific (funding, liquidations, stablecoin pegs,
  options IV, spot-futures basis) it has **no NSE meaning** — say so immediately in one
  line and stop. That is a complete and acceptable answer.