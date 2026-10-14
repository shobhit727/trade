# Per-stock sweep — analysis

**Headline: 2145 of 4032 pairs (53.20%) beat their own timing null at q<0.05, against ~202 expected by chance. 723 of those also beat their own stock's buy-and-hold. Read the per-pair table before quoting any of them.**

| | |
|---|---|
| pairs completed | 4032 |
| strategies x stocks | 84 x 48 |
| beat own timing null (FDR q<0.05) | **2145** |
| expected by chance | ~201.6 |
| beat own stock's buy-and-hold | 1123 |
| significant AND beats buy-and-hold | 723 |
| stocks with positive mean alpha | 11 / 48 |
| strategies with positive mean alpha | 0 / 84 |

## Distribution

| metric | mean | median | p10 | p90 | min | max |
|---|---|---|---|---|---|---|
| TEST CAGR | -0.0087 | 0.0 | -0.0865 | 0.0623 | -0.3241 | 0.2855 |
| alpha vs buy&hold | -0.0729 | -0.0749 | -0.2242 | 0.0846 | -0.5441 | 0.362 |
| exposure | 0.284 | 0.3007 | 0.0 | 0.5547 | 0.0 | 0.9693 |
| CGT paid (Rs) | 63737.406 | 35684.5647 | 0.0 | 171763.1057 | 0.0 | 574383.5176 |

## Concentration (GOAL.md Gate 4 caps one year at 35%)

- pairs exceeding the year cap: **2571**
- median largest-year share: 0.6976

## Best stocks by mean alpha

| stock | mean alpha |
|---|---|
| tmpv | +0.2084 |
| tcs | +0.1168 |
| asianpaint | +0.0972 |
| itc | +0.0956 |
| wipro | +0.0722 |
| hindunilvr | +0.0681 |
| infy | +0.0619 |
| hdfclife | +0.0585 |
| hdfcbank | +0.0447 |
| tataconsum | +0.0094 |

## Best strategies by mean alpha

| strategy | mean alpha |
|---|---|
| williams_r_strategy | -0.0386 |
| gaussian_strategy | -0.0397 |
| rsi_momentum_strategy | -0.0404 |
| vwap_strategy | -0.0426 |
| volatility_scaling | -0.0496 |
| anchored_vwap | -0.0499 |
| zscore_strategy | -0.0500 |
| cci_strategy | -0.0502 |
| stablecoin_peg_strategy | -0.0508 |
| implied_realized_volatility | -0.0513 |

---

**This file deliberately reports no leaderboard of the single best pair.** With 4032 trials against a null that is generous by construction, the maximum is not informative. Read the counts above first.
