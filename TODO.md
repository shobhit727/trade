# TODO — Per-stock strategy optimisation sweep

**Status:** harness complete, tested, **full sweep NOT run** (by design).
**You run the sweep. I read the logs.**

---

## 0. What this is

Optimise every catalog strategy **independently for each NIFTY-50 stock**, so each
`(strategy, stock)` pair becomes its own tuned unit instead of one global parameter set
applied to a 22-name book.

| | |
|---|---|
| Strategies | **84** (all load cleanly) |
| Stocks | **48** (`adanient`/`jiofin` excluded as corrupt, matching `nsealgo`) |
| Pairs | **4,032** |
| Searchable params | **166** (`quantity` held fixed — it sizes orders, not signals) |
| Configs per pair | 40 by default |
| Total backtests | ~161,000 |

---

## 1. Why per-stock is the right call

The previous cross-sectional design had three measured problems:

| Problem | Evidence |
|---|---|
| Tie-break decided the book | Composite tied on **177/225** rebalances; alphabetical resolution moved the headline 0.19pp/yr |
| Parameter selection was negative-value | Picking blind beat searching by **−0.38pp/yr** |
| The "signal" was cross-sectional | Selection term **−0.40pp/yr**; 100/100 random books profitable at **+8.59%/yr** |

Single-stock testing has **no ranking step**, so the first and third problems *cannot
occur*. And a 60%-vol small cap genuinely warrants different parameters than a 15%-vol
bank — this is defensible on its merits, not just as damage control.

---

## 2. 🚨 The trap, stated once and clearly

A random 22-name book earned **+8.59%/yr** on this data. Over **4,032 trials**, the
maximum of that null **will look spectacular by construction**.

**If the sweep hands you a +25%/yr "winner", that is almost certainly noise.** This is not
pessimism — it is the measured behaviour of this exact harness.

So the pipeline reports **"N of 4,032 beat their own timing null at FDR q<0.05"**, plus how
many would be expected by chance — **not** a leaderboard of the best pair.

---

## 3. What is modelled

| | |
|---|---|
| Capital | **₹21,00,000** per stock (matches `GOAL.md`) |
| Direction | Long/flat only — delivery cannot short, so `-1` → cash |
| Costs | 21.92 bps round trip (STT, exch txn, SEBI, stamp, DP, brokerage, 18% GST) |
| **Capital gains tax** | **Yes** — STCG 20% ≤365d, LTCG 12.5% beyond, FIFO lot ledger |
| Dividends | **No** — panel is price-only, understates by ~1.15%/yr |
| Execution | Decide on close of *t*, held from *t+1*. No look-ahead (tested) |
| Splits | TRAIN `2016-01-01`–`2023-12-31` · TEST `2024-01-01`–`2026-10-01`, opened once |

Tax is on by default because the whole prior validation chain was pre-tax. `--no-tax` gives
the pre-tax view; expect ~0.7–1pp/yr difference on low-turnover books.

---

## 4. Tasks

- [x] 1. `config.py` — ₹21L, 21.92bps, STCG 20% / LTCG 12.5%, seeds
- [x] 2. `catalog.py` — 84 strategies, 166 searchable params, bounds from annotations
- [x] 3. `backtest.py` — long/flat engine, costs, FIFO CGT ledger
- [x] 4. `metrics.py` — CAGR/Sharpe/Sortino/MaxDD/Calmar + per-year concentration
- [x] 5. `nulls.py` — buy-and-hold, exposure-matched timing null, params null
- [x] 6. `splitter.py` — per-symbol loading + strict TRAIN/TEST isolation
- [x] 7. `engine.py` — parallel (joblib), resumable, crash-safe, JSONL
- [x] 8. `analyze.py` — Benjamini–Hochberg FDR, verdict, report
- [x] 9. `run.py` — CLI (`--smoke`, `--budget`, `--workers`, `--resume`, `--dry-run`)
- [x] 10. `README.md` — how to run, log format, what to send me
- [x] 11. `tem/` — in-repo scratch dir (gitignored); nothing written to `/tmp`
- [x] 12. Unit tests — **27 passing**, mutation-verified
- [x] 13. Smoke test — 2 strategies × 2 stocks × 4 configs, end-to-end
- [x] 14. Lint clean (`ruff check`)
- [ ] 15. **YOU:** run the full sweep
- [ ] 16. **ME:** read your 3 artefacts → `reports/PERSTOCK_v1.md`

---

## 5. How you run it

> **All copy/paste commands are in [`RUN.md`](RUN.md).**

```bash
# correctness check (~5 s) — NOT a result
PYTHONPATH=src .venv/bin/python -m research.optimize.run --smoke

# the real sweep
PYTHONPATH=src nohup .venv/bin/python -m research.optimize.run \
    --budget 40 --workers 8 --resume > logs/optimize.log 2>&1 &

# analysis
PYTHONPATH=src .venv/bin/python -m research.optimize.analyze
```

`--budget 12` for a fast first pass. Interrupt any time; `--resume` skips completed pairs.

### Send me exactly three things

1. `logs/optimize.log` (tail is fine — progress lines look like
   `[1200/4032] ok=1198 fail=2 1.83 pair/s elapsed=10.9m eta=25.7m`)
2. `research/optimize/out/analyze.md`
3. `research/optimize/out/manifest.json`

I will not re-run anything.

---

## 6. Two bugs the smoke test caught (tests now pin both)

Each would have produced a **full sweep of plausible, wrong numbers with no error raised**:

1. **Base-class resolution.** Every module imports `SignalStrategy`; a name-suffix scan
   picked the *base* class for all 84. Its `signal()` returns 0 unconditionally → every
   pair would have reported **0.00% CAGR**. Fixed via `obj.__module__ == mod.__name__`.
2. **Double cash debit.** The buy path subtracted the purchase price from cash twice →
   equity to zero, CAGR **−100%**.

Both verified by mutation: reverting each turns the suite red (2 and 3 failures).

A third real bug: `pd.to_datetime` on epoch-**ms** assumed seconds, silently emptying
every slice. Caught because the smoke run returned 0 bars rather than a number.

---

## 7. Known limits — read before trusting output

1. **Survivorship bias, uncorrected (~7.3%/yr).** Today's NIFTY-50, backfilled. Real
   performance is lower than anything here.
2. **No dividends.** Understates by ~1.15%/yr.
3. **Daily bars only.** 5m/15m give ~7 weeks; 1m unusable. No intraday edge testable.
4. **4,032 hypotheses.** FDR corrects the reported count; it cannot create signal.
5. **₹21L in one mid-cap is not liquid.** Real fills exceed 5bps slippage.
6. **The optimiser will learn tax avoidance, not alpha.** It can pick holding periods to
   fall under 365 days for LTCG at 12.5%. Expect long holds to look good for the wrong
   reason — check the realised holding period before believing a low-turnover winner.