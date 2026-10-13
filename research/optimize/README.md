# Per-stock strategy optimisation sweep

Optimises every catalog strategy **independently for each NIFTY-50 stock**, so each
`(strategy, stock)` pair is its own tuned unit rather than one global parameter set.

- **84 strategies** × **48 stocks** = **4,032 pairs** (`adanient`/`jiofin` excluded as
  corrupt, matching `nsealgo.data.loader`)
- **166 searchable parameters**; `quantity` is held fixed — it sizes orders, it is not a
  signal knob
- Selection on **TRAIN only**; TEST opened once, at the end

---

## ⚠️ Read this before you run it

The previous harness produced **100 of 100 random 22-name books as profitable**, averaging
**+8.59%/yr**. We also measured that picking the best of 18 parameter cells was
*provably negative-value* (−0.38pp/yr).

Against a null that generous, **the maximum of 4,032 trials will look spectacular by
construction.** If this hands you a +25%/yr "winner", that is almost certainly noise.

So the output is deliberately **not a leaderboard**. The headline is:

> **How many pairs beat their own timing null at FDR q<0.05?**

with an explicit count of how many would be expected by chance alone. If the answer is 0,
that is the answer, and it is a real one.

---

## Run it

```bash
# correctness check (~5 seconds). NOT a result.
PYTHONPATH=src .venv/bin/python -m research.optimize.run --smoke

# the real sweep
PYTHONPATH=src nohup .venv/bin/python -m research.optimize.run \
    --budget 40 --workers 8 --resume > logs/optimize.log 2>&1 &

# analysis (run any time, or when the sweep finishes)
PYTHONPATH=src .venv/bin/python -m research.optimize.analyze
```

Interrupt freely — `--resume` skips pairs already in
`out/test_results.jsonl`. A finished pair is written to JSONL the moment it completes, so a
hard kill loses at most one pair.

### Useful flags

| flag | default | meaning |
|---|---|---|
| `--budget` | 40 | configs per pair. `12` for a fast pass |
| `--workers` | 8 | processes. Don't exceed physical cores |
| `--no-tax` | off | pre-tax view; expect ~0.7–1pp/yr higher on low-turnover books |
| `--rebalance` | `M` | `M`, `W` or `D`. `W` uses a different week anchor than `nsealgo` |
| `--strategies` / `--stocks` | all | subsets, for targeted reruns |
| `--dry-run` | off | list the work and exit |
| `--list` | off | print every strategy with its search space |
| `--no-resume` | off | ignore existing results and start over |

### Cost

`--budget 40` → ~161k backtests. On 8 cores: **hours**, not minutes. Start with
`--budget 12` if you want a fast read.

---

## What is modelled

| | |
|---|---|
| Capital | **₹21,00,000** per stock |
| Direction | Long / flat only — NSE delivery cannot short, so `-1` goes to cash |
| Costs | 21.92 bps round trip (STT, exch txn, SEBI, stamp, DP, brokerage, 18% GST) |
| **Capital gains tax** | **Yes.** STCG 20% ≤365 days, LTCG 12.5% beyond, FIFO lot ledger |
| Dividends | **No** — panel is price-only. Understates by ~1.15%/yr |
| Execution | Decide on close of *t*, held from *t+1*. No look-ahead (tested) |

Tax is on by default because the entire prior validation chain was pre-tax.

---

## Log / output format

**Send me these three, and nothing else:**

1. `logs/optimize.log` — the tail is enough; progress lines look like
   `[1200/4032] ok=1198 fail=2 1.83 pair/s elapsed=10.9m eta=25.7m`
2. `research/optimize/out/analyze.md` — generated verdict
3. `research/optimize/out/manifest.json` — the run's parameters

Per-pair rows land in `out/test_results.jsonl`, one JSON object per line:

```json
{"strategy":"rsi_strategy","stock":"tcs","test":{"cagr":0.0031,"sharpe":0.07,...},
 "alpha_vs_buy_hold":-0.169,"p_timing":0.42,"p_params":0.11,
 "total_tax_test":69998,"test_max_year_share":0.61,"params":{...}}
```

Failed pairs are recorded too, with `ok:false` and the reason — a silently shrinking
result set is how an earlier agent lost a verdict.

---

## Files

| file | role |
|---|---|
| `config.py` | capital, fees, tax rates, windows, seeds |
| `catalog.py` | discovers 84 strategies; builds the search space from `Config` annotations |
| `backtest.py` | single-stock long/flat engine + FIFO CGT ledger |
| `metrics.py` | CAGR/Sharpe/Sortino/MaxDD/Calmar + per-year concentration |
| `nulls.py` | buy-and-hold, random-timing null, params null |
| `splitter.py` | per-symbol loading + strict TRAIN/TEST isolation |
| `engine.py` | parallel orchestrator, resume, JSONL, crash-safe |
| `analyze.py` | Benjamini–Hochberg FDR, verdict, report |
| `run.py` | CLI |

---

## Two bugs the smoke test caught (and the tests now pin)

Both would have produced a full sweep of plausible, wrong numbers with **no error raised**:

1. **Base-class resolution.** Every catalog module imports `SignalStrategy`, and the naive
   name-suffix scan picked the *base* class for all 84 — whose `signal()` returns 0
   unconditionally. Every pair would have reported **0.00% CAGR**. Fixed by requiring
   `obj.__module__ == mod.__name__`.
2. **Double cash debit.** The buy path subtracted the purchase price from cash twice,
   driving equity to zero and CAGR to **−100%**.

Both are guarded by mutation-tested assertions in
`tests/unit/test_nsealgo_perstock_optimizer.py`.

---

## Known limits

1. **Survivorship bias, uncorrected (~7.3%/yr).** Today's NIFTY-50, backfilled.
2. **No dividends.** Understates by ~1.15%/yr.
3. **Daily bars only.** 5m/15m give ~7 weeks; 1m is unusable. No intraday edge testable.
4. **4,032 hypotheses.** FDR corrects the reported count; it cannot create signal.
5. **₹21L in one mid-cap is not liquid.** Real fills exceed 5bps slippage.
6. **The optimiser will learn tax avoidance, not alpha** — it can pick holding periods to
   fall under the 365-day LTCG line. Expect long holds to look good for the wrong reason.