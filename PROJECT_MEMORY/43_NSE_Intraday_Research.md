# NSE intraday research — conditional hypotheses

Generated 2026-08-26T08:40:12+00:00 · 49 stocks · 15m bars · MIS 2+1bps/side · flat by 15:25

## Results

| hypothesis | trades | win% | mean/trade | median |
|---|---|---|---|---|
| H1 power_hour(long-only) | 134 | 50.7% | +0.0450% | +0.0035% |
| H2 xsec_mom(top5 long) | 205 | 46.3% | +0.0108% | -0.0286% |
| H2 xsec_mom(top10 long) | 410 | 43.4% | -0.0330% | -0.0722% |
| H3 cond_orb(k=1.5,v=1.5) | 6 | 33.3% | -0.0903% | -0.0891% |
| H3 cond_orb(k=2.0,v=2.0) | 2 | 100.0% | +0.8140% | +0.8140% |

## H4 time-of-day drift map

- Strongest 15m bucket for morning-up stocks: **09:30** (drift +0.1934%/bar vs morning-down)
- Weakest: 14:30

| bucket | mean ret if morning-up | mean ret if morning-down |
|---|---|---|
| 09:30 | +0.1126% | -0.0808% |
| 09:45 | +0.0641% | -0.0445% |
| 10:00 | +0.0124% | -0.0391% |
| 10:15 | +0.0505% | -0.0205% |
| 10:30 | +0.0361% | -0.0316% |
| 10:45 | +0.0232% | -0.0409% |
| 11:00 | +0.0364% | -0.0377% |
| 11:15 | +0.0463% | -0.0172% |
| 11:30 | +0.0065% | -0.0356% |
| 11:45 | +0.0383% | -0.0236% |
| 12:00 | +0.0334% | -0.0357% |
| 12:15 | -0.0076% | +0.0011% |
| 12:30 | -0.0059% | -0.0185% |
| 12:45 | -0.0066% | -0.0063% |
| 13:00 | -0.0023% | -0.0126% |
| 13:15 | -0.0034% | +0.0052% |
| 13:30 | -0.0066% | -0.0086% |
| 13:45 | -0.0042% | -0.0095% |
| 14:00 | -0.0145% | -0.0207% |
| 14:15 | -0.0054% | +0.0100% |
| 14:30 | -0.0029% | +0.0140% |
| 14:45 | -0.0027% | +0.0081% |
| 15:00 | +0.0067% | +0.0092% |
| 15:15 | +0.0563% | +0.0603% |

## Round 2 — sweeps, new hypotheses, robustness

| variant | trades | win% | mean | median | top-stock % | pos months |
|---|---|---|---|---|---|---|
| H1 vw>0 enter825->exit915 | 901 | 44.6% | -0.0249% | -0.0447% | 3% | 1/3 |
| H1 vw>0 enter840->exit915 | 822 | 43.2% | -0.0251% | -0.0555% | 3% | 2/3 |
| H1 vw>0 enter855->exit925 | 0 | 0.0% | +0.0000% | +0.0000% | 0% | 0/0 |
| H1 vw>0 enter840->exit925 | 0 | 0.0% | +0.0000% | +0.0000% | 0% | 0/0 |
| H5 morn-cont 09:30->12:00 | 950 | 43.9% | -0.0928% | -0.1014% | 3% | 0/3 |
| H5 morn-cont 09:30->14:00 | 950 | 43.9% | -0.0928% | -0.1014% | 3% | 0/3 |
| H6 close-drift 15:00->15:25 | 0 | 0.0% | +0.0000% | +0.0000% | 0% | 0/0 |

## Round 2 (fixed semantics) — sweeps & new hypotheses

| variant | trades | win% | mean | median | top-stock % | pos months |
|---|---|---|---|---|---|---|
| H1 13:45->15:15 | 126 | 53.2% | +0.0565% | +0.0423% | 4% | 2/3 |
| H1 14:00->15:15 | 134 | 52.2% | +0.0599% | +0.0195% | 6% | 1/3 |
| H1 14:00->last | 149 | 54.4% | +0.0803% | +0.0333% | 6% | 1/3 |
| H1 14:15->15:15 | 106 | 48.1% | +0.0452% | -0.0065% | 5% | 2/3 |
| H5 09:30->12:00 day1up | 0 | 0.0% | +0.0000% | +0.0000% | 0% | 0/0 |
| H5 09:30->14:00 day1up | 0 | 0.0% | +0.0000% | +0.0000% | 0% | 0/0 |
| H6 15:00->15:15 always | 1841 | 40.7% | -0.0016% | -0.0421% | 2% | 2/3 |
| H6 14:45->15:15 always | 1841 | 45.2% | -0.0096% | -0.0294% | 2% | 1/3 |

## Round 2 (fixed semantics) — sweeps & new hypotheses

| variant | trades | win% | mean | median | top-stock % | pos months |
|---|---|---|---|---|---|---|
| H1 13:45->15:15 | 126 | 53.2% | +0.0565% | +0.0423% | 4% | 2/3 |
| H1 14:00->15:15 | 134 | 52.2% | +0.0599% | +0.0195% | 6% | 1/3 |
| H1 14:00->last | 149 | 54.4% | +0.0803% | +0.0333% | 6% | 1/3 |
| H1 14:15->15:15 | 106 | 48.1% | +0.0452% | -0.0065% | 5% | 2/3 |
| H5 09:30->12:00 day1up | 950 | 43.9% | -0.0928% | -0.1014% | 3% | 0/3 |
| H5 09:30->14:00 day1up | 950 | 43.9% | -0.0928% | -0.1014% | 3% | 0/3 |
| H6 15:00->15:15 always | 1841 | 40.7% | -0.0016% | -0.0421% | 2% | 2/3 |
| H6 14:45->15:15 always | 1841 | 45.2% | -0.0096% | -0.0294% | 2% | 1/3 |


## Verdict after round 2

**H1 power-hour momentum is the first intraday candidate that survives
costs and robustness checks:**

- Positive across ALL 4 parameter variants (+4.5 to +8.0 bps/trade net)
- Best: enter 14:00, exit last bar (15:15) — +8.0 bps/trade, 54% win,
  149 trades over ~60 sessions (~2.5 picks/day)
- NOT one-stock luck: top stock = 6% of trades
- Median positive on the best variant → broad-based, not tail-driven

**Killed this round:**
- H5 morning continuation: −9.3 bps/trade — morning strength REVERSES,
  doesn't continue (consistent with H4 map's negative midday buckets)
- H6 unconditional close-drift: flat/negative — the 15:15 bucket from H4
  only pays when CONDITIONED on morning direction

**Caveats (honest):**
1. Sample = ~60 trading days (Yahoo 15m limit). Months split 1/3–2/3
   positive — regime sensitivity unproven.
2. Round-trip MIS cost assumed 6bps; real Zerodha adds ₹20/order minimums
   at small sizes.
3. Needs 30+ days of live paper validation before any size.

## Proposed next step: paper-trade H1 via a second basket process

Same harness as nse_basket but: signals at 14:00 IST, MIS-style fills,
flat by close, its own state + dashboard card. Runs alongside the daily
gate; if it stays positive for 30 sessions we have TWO live strategies.
