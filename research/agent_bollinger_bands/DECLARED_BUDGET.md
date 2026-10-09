# DECLARED PARAMETER BUDGET — bollinger_bands on NSE NIFTY-50

Written **before any backtest was run** (only the TRAIN descriptive forward-return
table in `01_diagnostics.py` had been produced). Budget = **5 distinct parameter
variants**, per `research/AGENT_BRIEF.md` section 4. Exceeding 5 invalidates the run.

## Signal (faithful port, verified bar-for-bar in `01_diagnostics.py`)

```
sig = (close_t - mean(close_{t-p+1..t})) / (n_std * sd(close_{t-p+1..t}))
long  when  sig < -entry
```

The catalog strategy's SHORT leg (`sig > +entry`) is dropped: an Indian delivery
account cannot short (brief section 5). Verified that the long leg of the vectorised
port agrees with `BollingerBandsStrategy.signal` on 4429/4429 RELIANCE bars for every
parameter set below.

## The 5 variants

| # | name | period | n_std | entry | score construction | gate in sigmas |
|---|------|--------|-------|-------|--------------------|---------------|
| V1 | `bb_pure_default`  | 20 | 2.0 | 1.0 | `pure` — rank gated names by oversold depth | z < -2.0 |
| V2 | `bb_hybrid_mom6m`  | 20 | 2.0 | 1.0 | `hybrid` — rank gated names by 126d momentum (brief s5) | z < -2.0 |
| V3 | `bb_pure_deep`     | 20 | 2.5 | 1.0 | `pure` | z < -2.5 |
| V4 | `bb_pure_slow`     | 60 | 2.0 | 1.0 | `pure` | z < -2.0 |
| V5 | `bb_pure_fast`     | 10 | 2.0 | 1.0 | `pure` | z < -2.0 |

`entry` is held at the catalog default 1.0 for every variant; the effective band depth
is `entry * n_std`, so V3 probes a deeper band without spending a second parameter.

V1 is the catalog default. V2 is the construction the brief prescribes, and it is a
Bollinger+momentum **hybrid** — any performance it shows is not attributable to
Bollinger alone. V3/V4/V5 probe whether band depth or baseline speed is the lever.

## Selection rule (fixed in advance)

Choose **highest TRAIN Sharpe**. Tie-break: lower TRAIN annual cost drag.
Selection uses TRAIN only. The selected variant is then run on TEST **unchanged**.

## Baselines and controls (not parameter variants — reported, never selected)

- buy-and-hold equal-weight universe, same window, same costs (brief s4.5)
- `build_composite_score` (the nsealgo production composite)
- random-signal control: same number of names selected per day as the variant,
  chosen uniformly at random, fixed seed