> **Source:** evidence survey commissioned for this project, 2026-10-05.
> Full web-survey output with per-claim citations is preserved below.
> This document drove several design decisions in `src/nsealgo/` — in particular
> removing the mean-reversion core and moving from weekly to monthly rebalance.

# Evidence Survey: Systematic Long-Only NIFTY-50 Swing Trading

**Scope**: Academic + regulator + index-vendor + practitioner evidence on Indian equities, NSE cash delivery, daily bars, 5–60 day holds.
**Evidence labels used throughout**: `[PEER-REVIEWED]` · `[REGULATOR]` · `[INDEX VENDOR]` · `[WORKING PAPER]` · `[PRACTITIONER]` · `[MY INFERENCE]`

---

## 1. CROSS-SSECTIONAL FACTORS IN INDIAN EQUITIES

### 1.0 A critical reading instruction

Almost every Indian factor headline number below is an **arithmetic mean of monthly long-short returns**, not a compounded return an investor could capture. The gap is enormous and it is the single most important calibration fact in this report.

The canonical example is the IIMA factor library paper: it reports momentum at **21.9% average annual return** and **cumulative return of 341%** over the same Jan 1994–Dec 2014 window `[WORKING PAPER: Agarwalla, Jacob & Varma, IIMA WP 2013-09-05 rev. 2014]`. A 341% cumulative gain = 4.41x over ~21 years = **~7.3% compounded annually** `[MY INFERENCE]`. The same paper reports HML at 15.3% average annual but 216% cumulative = **~4.7% compounded** `[MY INFERENCE]`. These are 3x gaps between arithmetic and geometric.

**Do not put arithmetic factor returns in a return projection.** The journal-version, volatility-reported numbers (Agarwalla, Jacob & Varma 2018) are the ones to use.

---

### 1.1 MOMENTUM (12-1 month) — the strongest Indian factor, but with a long-only caveat

| Source | Universe / Period | Reported statistic | Label |
|---|---|---|---|
| Agarwalla, Jacob & Varma, *"Size, Value, and Momentum in Indian Equities"*, **Journal of Emerging Markets** 2018; doi 10.1177/0256090917733848 | NSE/BSE broad, Jan 1994–Mar 2017 | **WML (winners−losers): 17.3% annualized, 17.06% annualized vol → Sharpe ≈ 1.01** `[MY INFERENCE, derived]`. "By far the best performing of all the factors." 10 drawdowns >20%; worst 49%; median DD duration 1y, max 2.4y | PEER-REVIEWED |
| Agarwalla, Jacob & Varma, IIMA WP 2013-09-05 (rev. 2014) | CMIE Prowess, survivorship-corrected, Oct 1993–Dec 2014 | Momentum 21.9% avg annual (cum. 341%); HML 15.3% (cum. 216%); SMB ≈0% (cum. −58%); MRP 11.5%. Factor correlations low (WML vs MRP = −16%) | WORKING PAPER |
| Kedia, *"A Multi-Factor and Portfolio-Based Approach of Momentum Anomaly…"*, **J. UNITS Econ. Fin. Sci.** 2024 | NSE 500, 232 firms, Jul 2015–Jun 2024 | **WML Sharpe 6.21 (3×3) to 8.78 (6×12)** | ⚠️ **NOT CREDIBLE — see below** |
| *"Physical Momentum in the Indian Stock Market"*, arXiv:2302.13245 (2023) | NSE 500, 2014–2021, long-short physical momentum | **ALL momentum portfolios had Sharpe < 1** ("not suitable for investment"). Best contrarian 1-2mo: Sharpe 0.55; best traditional: ~0.39. Daily/weekly timescale shows *reversal*, not continuation | WORKING PAPER |
| Nigam & Pandey, *"How smart is a momentum strategy? An empirical study of Indian equities"*, **Algorithmic Finance** 10(1-2), 2023, 21-37 | India, long-only | **Lagged 6-month compounded return with quarterly rebalancing = best risk-adjusted.** Accelerated momentum (Ardila et al.) **underperforms** | PEER-REVIEWED |
| Raju, *"Shades of Momentum"*, SSRN 4977717 (2024) | Dec 2008–Sep 2024 | Volatility-adjusted and information-discreteness momentum beat raw price momentum on risk-adjusted return. **Momentum dissipates significantly as holding period extends 3→12 months** | WORKING PAPER |
| Sehgal, Pandey & Sen (2024), *Relative, absolute or combined strength momentum strategies: what works for India?* | All NSE-listed | **Combined relative + absolute strength momentum beats conventional price momentum.** Rational pricing models cannot explain any of them; investor overreaction is the driver | PEER-REVIEWED |
| Singh & Walia, *"Time-Series and Cross-Sectional Momentum in Indian Financial Market"* (2020) | India | **Time-series momentum generates superior returns to cross-sectional momentum, and "net long investments in time-series momentum strategies is the main source of difference."** TSMOM persists and does not reverse long-run | PEER-REVIEWED |
| *"52-Week High Effect in Indian Stocks"*, SSRN 4587697 | 2004–2023 | Stocks near 52-week high beat momentum on **both return and risk-adjusted return**; more stable alpha; weaker long-term reversals | WORKING PAPER |
| Sharma, Subramaniam & Sehgal, *"Are Prominent Equity Market Anomalies in India Fading Away?"*, **Global Business Review** 2021 | NSE 500, Jul 2005–Jun 2016 | **Value AND momentum anomalies ARE explained by risk models** (contrary to earlier Indian evidence). Size and volume faded substantially. "Indian market seems informationally more efficient" | PEER-REVIEWED |

#### ⚠️ Flag: Kedia (2024) WML Sharpe of 6-8 is almost certainly broken
A Sharpe ratio of 6–8 on an unlevered long-short equity portfolio implies ~6–8x leverage to express as an annualised return, i.e. several hundred percent per annum. That is not attainable in NIFTY-500 stocks. The likeliest causes are unbounded/levered portfolio construction, zero costs, and a 9-year sample (Jul 2015–Jun 2024) that spans an unusually clean momentum run. **This is exactly the number that gets quoted online as "Indian momentum works." Do not use it.** The arXiv physical-momentum study, which reports Sharpe < 1, is the more honest read of long-only implementability.

#### LONG-ONLY VIABILITY OF MOMENTUM — mixed, and this is the crux

- **Long-short WML is NOT available to a retail delivery account.** Most of the headline statistics above are long-short.
- **QED Capital's long-only study** — *"Long Factors, not Short change: Long Only Factor Portfolios in India"*, SSRN 4000418 — monthly-rebalanced, equal-weighted, long-only winner portfolios from the **top 200 Indian stocks**, Jan 2007–Oct 2021 (178 months), FF4 over 172 months: momentum, low-volatility and quality each deliver positive alpha, and **alpha for all three survives real-world implementation costs** `[WORKING PAPER]`.
- **But the same paper finds two crucial caveats**: (i) *"The market exposure is significant across all the style strategies we looked at. Therefore, correlations between the strategies are significantly higher than those observed for academic factor returns"*; and (ii) *"there is not one factor-style that is a consistent winner."*
- **Consequence `[MY INFERENCE]`**: a long-only momentum tilt in India is largely a **beta-tilting** trade. Roughly half the long-short spread is unavailable to you, and what remains is correlated with the index. Long-only momentum should be expected to deliver **low-to-mid single-digit percentage points** of alpha, not the full spread.
- The most promising long-only variant is **time-series momentum** (Singh & Walia): its signal is a per-stock sign, so the short leg is cash. This is implementable in a pure delivery account and has India-specific published support.
- Momentum's lookback: **Nigam & Pandey's 6-month compounded return is the best long-only risk-adjusted result in the peer-reviewed Indian literature.** The 12-1 convention is the academic standard but not the best long-only performer here.

---

### 1.2 SHORT-TERM REVERSAL — Indian evidence points the OPPOSITE way

This is a case where transferring US intuition is actively dangerous.

| Source | Finding | Label |
|---|---|---|
| *"Contrarian and Momentum Strategies in the Indian Capital Market"*, **IIMC/IBSA** (doi 10.1177/0256090920020103) | **There is CONTINUATION in short-term returns in India — momentum on short-horizon past returns gives significantly positive payoffs.** Reversal appears only at long horizons with a 1-year formation-to-holding gap, and the contrarian payoff is "moderately positive" | PEER-REVIEWED |
| Sehgal & Jain (2011), *J. Advances in Management Research* 8(1); Sehgal & Balakrishnan (2004) | Strong short-term momentum; weak long-term reversal only after skipping a year | PEER-REVIEWED |
| Mohapatra & Misra (2018), Singh & Walia (2020), Balakrishnan (2021, *Financial Innovation* 10.1186/s43093-021-00097-2) | **No momentum reversal observed at 2–5 year holding periods in India** — a direct contradiction of Lee-Swaminathan / Jegadeesh-Titman. Momentum returns are decomposed: time-series pattern is the largest component, then cross-sectional risk, then lead-lag | PEER-REVIEWED |
| Sehgal, Balakrishnan & Jain — long-run reversal re-examination (JBI) | Past-36-month losers beat past-36-month winners by **21.33% ACAR over the next 36 months (annualised 7.11%), significant only at the 36-month hold**. **Fully explained by FF3 — losers load heavily on size and value; they are small, distressed, illiquid stocks** | PEER-REVIEWED |
| Da, Liu & Schaumburg (US, but mechanism-relevant) | Within-industry reversal earns **0.92%/month 3-factor alpha**; the *standard cross-industry* reversal earns only **0.33%/month, insignificant (t=1.37)**. Much of "reversal" is industry momentum in disguise | PEER-REVIEWED |
| Sharma, Subramaniam & Sehgal (2021) | Momentum explained by risk models; bivariate sorts do not beat univariate | PEER-REVIEWED |

**Conclusion for a daily-bar, long-only, NIFTY-50 swing system `[MY INFERENCE]`:**
1. **Do not build a short-term mean-reversion core.** The best Indian evidence says 1-month continuation, not reversal, and the reversal literature that exists is a 36-month, size/value-loaded, long-short distressed effect you cannot implement long-only in large caps.
2. The 2008-style practitioner claim that "buy the dip on NIFTY 50 constituents works" is **contraindicated by the factor literature**, and a survivorship-corrected practitioner backtest explicitly reports that "daily buy-the-dip tricks die under honest testing" `[PRACTITIONER: ReaperOAK/survivorship-free-backtester]`.
3. The one place a short-horizon contrarian tilt has any support is the arXiv physical-momentum study, which found **reversal only at the daily/weekly timescale** — i.e. intraday-to-weekly, which is exactly the regime your data cannot support.

---

### 1.3 LOW VOLATILITY — works in India, and it is mostly the low-BETA effect

| Source | Universe / Period | Reported statistic | Label |
|---|---|---|---|
| Joshipura & Joshipura, *"The Volatility Effect: Evidence from India"* (2016) | All present+past Nifty 200 constituents, Capitaline, **Jan 2001–Jun 2015** | **Low-vol decile annualised excess return 11.40% vs high-vol decile 1.30%.** Statistically & economically significant. Survives controls for size, value, momentum. FFC alpha for top-decile volatility 9.78% (vs FF3 7.91%) | PEER-REVIEWED |
| — same paper, critical caveat | | **"The volatility effect is not statistically significant after controlling for the beta effect."** The low-vol portfolio is composed of **large and growth stocks**, not small/illiquid ones. Low-vol beat benchmark in *both* up and down markets | PEER-REVIEWED |
| QED Capital, *"Low-Risk Anomaly: Evidence from India"*, SSRN 4398656 (2023) | **4,400 companies, 19 years** | Five low-risk factors (realised vol, ex-ante beta, CAPM beta, IVOL). **Strong CONVEX** returns–volatility relationship. Lower-risk portfolios have higher risk-adjusted returns. **"The strength of the anomaly does not appear to diminish over time."** Survives standard academic factor controls | WORKING PAPER |
| Saraf & Lavanya, MSE Working Paper 215 | NIFTY 500, Jul 2010–Jun 2020 | VA "predominant in the medium to long term (5 to 10 years), but negligible in the ultra-short and short time frames (6 months to 3 years)." Most significant when window ≥3 years | WORKING PAPER |
| Pandey & Sehgal (2017), *IIMB Management Review* 29(1):3 | India | Volatility effect survives controlling for firm quality | PEER-REVIEWED |
| Agarwalla et al. (2014) | India | Betting-against-beta exists in India | WORKING PAPER |

**LONG-ONLY VIABILITY: excellent — this is the best-behaved factor for your constraints `[MY INFERENCE]`.**
- Low-vol portfolios are inherently long-only constructs (shorting high-vol is not required to harvest the tilt).
- They are composed of large/growth stocks → structurally compatible with a NIFTY-50 universe.
- Low turnover (see §5, QED long-only paper).
- **Caution**: because it is largely a beta effect, a low-vol screen inside NIFTY 50 will deliver you a **beta-drag relative to the benchmark in bull markets**, and outperformance will show up mostly in drawdowns. Joshipura & Joshipura confirm outperformance "not only in down market but also in up market conditions" — but the magnitude is regime-dependent and I found no Indian study quantifying the bull-market give-up.

---

### 1.4 VALUE — the weakest pillar. Do not build on it.

The evidence is genuinely contradictory, and the most careful studies find it has decayed.

| Source | Finding | Label |
|---|---|---|
| Connor & Sehgal (2001), **Journal of Banking & Finance** | FF3 works in India, but: **"strong size effect and a conditional value effect, the latter being present only for small stocks."** Value evidence "mixed"; "there is definitely a (negative) size premium, and there may be a value premium" | PEER-REVIEWED |
| Subramaniam, Sharma & Sehgal (2018), *"Changing Nature of the Value Premium in the Indian Stock Market"*, Vikalp 23(2) | Using P/B: **"post the global crisis, the value premium has nearly ceased to exist."** Robust to CAPM, FF3, EW/VW/Winsorized/trimmed returns. Chow test confirms structural parameter change | PEER-REVIEWED |
| Sharma, Jain & McMillan (2020), *Applied Economics* 8(1) | **"Value Anomaly exists in India, but with growth portfolios outperforming value."** Size-linked | PEER-REVIEWED |
| *(Industry-level, BSE 1999–2020)*, Vikalp (doi 10.1177/09722629221130214) | Value effect significant in 15 of 17 industry groups over 21.5 years, **but value-growth premiums declined 51–76% pre→post 2008-09; industry portfolio excess returns declined 62%. Model explanatory power fell post-crisis** | PEER-REVIEWED |
| Vasishth & Sehgal (2019) | Value premium exists **but is explained by CAPM/FF3** — "merely a compensation for risk." However, **growth premium also exists**, correlation between value and growth premiums is **−0.214**, and **bivariate value+growth portfolios remain unexplained even by FF5** — i.e. the *combination* is the alpha, not either leg | PEER-REVIEWED |
| Cakici, Fabozzi & Tan (2013); Invesco (2026) | Value results vary substantially across countries; some subsamples weak/negative. Invesco notes **generic value portfolios tilt toward resource-heavy markets (Russia)** — a country bet, not a value bet | PEER-REVIEWED / PRACTITIONER |
| Lalwani, *"Are Factor Investing Strategies Successful Out-of-Sample? Evidence from the Nifty Indices"*, **Applied Finance Letters** (AUT) | Tests 9 NSE strategy indices, **in-sample (pre-launch) vs out-of-sample (post-launch)**: ~4 of 9 significant alpha in training; **NOT ONE significant alpha in the test period after controlling for size, value, momentum.** 4 of 9 showed *significant decline*. Quality indices "modest in training… never really took off." Average market beta rose ~0.09 in the test period | PEER-REVIEWED |

**Verdict `[MY INFERENCE]`: value is the one factor where I would advise near-zero allocation of risk budget.** Two independent peer-reviewed studies find growth beats value; the most-cited Indian value paper finds the premium has "nearly ceased to exist"; the only out-of-sample test of Indian factor *indices* found zero significant alpha. Any value sleeve in a NIFTY-50 portfolio will be a concentrated bet on distressed financials and cyclicals — the exact factor that failed post-2008.

---

### 1.5 QUALITY / PROFITABILITY — the strongest India-specific alpha claim, and the best long-only fit

| Source | Universe / Period | Reported statistic | Label |
|---|---|---|---|
| IIMA, *"Performance of Quality Factor in Indian Equity Market"*, SSRN 4284686 | India | **QMJ four-factor alpha = 0.92%/month**, significantly outperforming market, size, value and momentum factors. **Long-only Quality factor alpha = 0.69%/month** (~8.5% p.a.) `[MY INFERENCE, annualised]`. Significant by Harvey-Liu-Zhu (2016) thresholds | WORKING PAPER (IIMA) |
| — same paper, mechanism | | Key drivers are **profitability and payout**, consistent with a promoter-tunnelling/governance hypothesis specific to EM. Also: **low portfolio churn, lower risk, shorter drawdowns, and viability of long-only strategies restricted to large caps** | WORKING PAPER |
| Invesco, *"Factor Investing in Emerging Markets"* (May 2026) | EM aggregate | Long-short FF-database Sharpes: value 0.99, **momentum 0.96, quality 0.67**. Multi-signal construction: value 1.13, momentum 0.56, **quality 0.36**. Enhanced: value 0.81, momentum 0.84, **quality 0.15** | PRACTITIONER (asset mgr) |
| NSE Indices / Mondovisione, NIFTY Multi-Factor Indices whitepaper | Apr 2005 – May 2017 backtest | Multi-factor return-to-risk **0.87–1.08 since inception vs ~0.58 for cap-weighted**. NIFTY Alpha Low-Vol 30 beat NIFTY 50 by 6.86% p.a.; NIFTY Alpha Quality Low-Vol 30 by 5.22% p.a. (backtest, not live) | INDEX VENDOR |

**LONG-ONLY VIABILITY: the best-documented one of all factors.** The IIMA paper explicitly states quality works long-only, restricted to large caps, with low churn — which is precisely your universe and your constraint. Quality also loads negatively on the market factor in some specifications, which partly addresses the beta problem.

**Caveat `[MY INFERENCE]`**: a 0.69%/month long-only alpha is a very large single-study claim. It comes from one IIMA working paper, not replicated in the peer-reviewed Indian literature. Note also that Invesco's cross-market evidence rates **quality as the weakest of the three** factors once you move from raw generic definitions to implemented ones (0.67 → 0.36 → 0.15 Sharpe). **Treat quality as promising, not established.**

---

### 1.6 LIQUIDITY PREMIUM — well documented, but incompatible with NIFTY 50

Amihud illiquidity, volume and turnover effects are real in India:
- Volume/turnover anomaly: returns vary inversely with volume; volume sorted portfolios gave **2.2% monthly** unadjusted returns (third-highest of all univariate styles tested) `[PEER-REVIEWED: "Profitability of Style based Investment Strategies: Evidence from India"]`.
- Size was the single highest-return univariate style: **2.7% per month unadjusted** in that study.
- **But**: IIMA's survivorship-corrected data put the **size factor (SMB) at ≈0% average annual return, cumulative −58% over 21 years** `[WORKING PAPER]`. That directly contradicts the 2.7%/month size figure, and the difference is almost certainly a liquidity/illiquidity exposure that a real ₹21L account cannot harvest.
- The QED long-only paper restricted everything to the **top 200 stocks** precisely because of this.

**Verdict `[MY INFERENCE]`: the liquidity premium is real in India and effectively unharvestable for you.** A ₹21,00,000 account buying NIFTY 50 names at ₹10,000–₹15,000/share can achieve adequate liquidity with a handful of days of ADV participation. You are structurally barred from the factor that returns the most in the Indian cross-section.

---

## 2. MARKET STRUCTURE REALITY

### 2.1 What NIFTY-50 long-only actually returns

**Official / index-vendor sources `[INDEX VENDOR, NSE]`:**

| Period | Price Return (PRI) | Total Return (TRI) | Source |
|---|---|---|---|
| Since 3 Nov 1995 base → 30 Jun 2026 | 10.90% | **12.41%** | Nifty 50 Factsheet, Jun 2026 |
| 20 years to 27 Feb 2026 | 11.09% | **12.44%** | Nifty 50 Whitepaper 2026 |
| 10 years to 17 Jul 2026 | 11.04% | **12.39%** | NSE Indices Return Profile |
| Since 30 Jun 1999 → 15 Dec 2021 | — | **14.2% CAGR, 22.9% annualised vol** | *"25 Years Journey of Nifty 50"* |

Derived Sharpe on the NSE 22.9% vol / 14.2% CAGR figure: **≈0.62 gross, ≈0.50 net of a 6% risk-free rate** `[MY INFERENCE, derived]`.

**Rolling-window distribution (Nifty 50 TRI, since 30 Jun 1999) `[PRACTITIONER: Craytheon, computed from NSE data]`:**

| Holding period | Windows | Avg CAGR | Worst | Best | % negative |
|---|---|---|---|---|---|
| 1 year | 316 | +15.6% | −51.7% (Nov 2008) | +97.3% (Apr 2004) | 25.3% |
| 3 years | 292 | +15.1% | −12.6% (Mar 2003) | +59.5% (Apr 2006) | 6.5% |
| 5 years | 268 | +15.4% | +0.2% (Oct 2012) | +46.7% (Oct 2007) | 0.0% |
| 10 years | 208 | **+14.0%** | **+6.4%** | +22.1% | **0.0%** |

**Calendar-year TRI returns 2005–2026YTD `[INDEX VENDOR]`:** 2005 +39.3% · 2006 +41.9% · 2007 +56.8% · **2008 −51.3%** · 2009 +77.6% · 2010 +19.2% · **2011 −23.8%** · 2012 +29.4% · 2013 +8.1% · 2014 +32.9% · 2015 −3.0% · 2016 +4.4% · 2017 +30.3% · 2018 +4.6% · 2019 +13.5% · 2020 +16.1% · 2021 +25.6% · 2022 +5.7% · 2023 +21.3% · 2024 +10.1% · 2025 +11.9% · **2026 YTD (to 30 Jun) −8.1%**

**Two additional calibration points:**
- Long-run real return: 12.7% nominal from the 1991 base ≈ **7.3% real** after ~5% average inflation `[PRACTITIONER, derived]`.
- 18 of 21 completed calendar years 2005–2025 were positive. **Note 2026 YTD is −8.1% — your data ends in a drawdown, not a bull market.** This matters for walk-forward design.

### 2.2 The target: is 3%/month (42.6% p.a.) achievable long-only?

**No. It is not achievable, and the gap is not marginal.**

| Comparison | Value | Ratio to target |
|---|---|---|
| Your target | **42.6% p.a.** | — |
| Nifty 50 TRI, 20yr to Feb 2026 | 12.44% | target is **3.4x** |
| Nifty 50 TRI, since 1999 | 14.2% | target is **3.0x** |
| Best single calendar year in 30y (2009) | +77.6% | — |
| Second-best (2006) | +41.9% | **one good year ≈ one full year of your target** |
| Best published Indian long-only factor study (QED Conservative Formula) | 24% cumulative over ~16 yrs ≈ **1.4% p.a. compounded** `[MY INFERENCE, derived from "returned 24% since 2006"]` | target is **30x** |
| Best Indian long-short WML, peer-reviewed, volatility-reported (Agarwalla et al. 2018) | 17.3% p.a. long-short, gross | target is **2.5x** |
| Longest 10-yr Nifty 50 TRI window on record | +22.1% | target is **1.9x** |

**Required feat for 42.6% net `[MY INFERENCE]`**: sustained capture of roughly the top decile of Indian equity returns, every single year, net of costs and taxes, with survivorship-free data. Nothing in the academic, regulatory, index-vendor or credible practitioner literature surveyed here supports anything above ~20% gross for a long-only Indian strategy, and the honest long-only evidence clusters at **10–16% net**.

### 2.3 Fund manager underperformance — the relevant prior is ZERO net alpha

| Source | Finding | Label |
|---|---|---|
| **Mehta, Raj & Jaffer, *"Alpha In Indian Mutual Fund Returns"*, SSRN 5370113 (2025)** | **425 actively managed funds, Jan 2013–Dec 2024. "Net returns for actively managed funds do not show a statistically significant positive alpha"** after accounting for size, value, momentum, profitability **AND management fees**. Outcome is persistent even for the largest and best-performing funds | WORKING PAPER |
| Lalwani, *Applied Finance Letters* | 9 NSE factor indices: **0 of 9 generated significant alpha out-of-sample** after factor controls | PEER-REVIEWED |
| CRISIL-AMFI | CRISIL-AMFI Equity Fund Performance Index **22% p.a. since 1 Apr 1997 vs CNX NIFTY 12% and CNX 500 13%**. "Never given a negative return for any five-year period on a daily rolling basis" | ⚠️ **SELECTION/SURVIVORSHIP-BIASED — see below** |
| CRISIL (Apr 2010–Mar 2021) | Average underperformance of active funds vs benchmark: **31% at 1-year horizon, 3% at 5-year horizon** | REGULATOR-ADJACENT |
| S&P DJ SPIVA India 2018 | Large-cap: **36% of funds beat benchmark over 10y, 9% over 3y.** Mid/small-cap: 45% over 10y, 44% over 3y | PEER-REVIEWED (index vendor) |
| Mhatre & Kanekar (2026), *Int. J. Adv. Res.* 14(01) | Active funds to Oct 2025: **large-cap — alpha underperformance 38.5%, information-ratio underperformance 61.5%, volatility-adjusted alpha underperformance 69.2%, M²-alpha underperformance 88.5%.** Mid-cap worse. Small-cap has raw-alpha capacity but poor risk utilisation | PEER-REVIEWED (low-tier journal) |
| Velora, from AMFI tables, 30 Sep 2026 | 65% of active equity funds beat benchmark over 10y, **median +0.63pp/yr**; large-cap **54% (13/24), median +0.07pp/yr** — "close to a coin toss before costs." Authors concede this **flatters active management** (survivors only, direct plans only; regular plans cost 0.5–1.5pp more) | PRACTITIONER |

#### ⚠️ The CRISIL-AMFI 22%-vs-12% figure is widely quoted and badly biased
The methodology is explicit: constituents are "funds which are ranked under CRISIL Mutual Fund Rankings," weighted by assets. That is **top-quartile-ranked surviving funds only** `[INDEX VENDOR, own methodology]`. It simultaneously selects on past performance and excludes dead funds. It is not a valid estimate of what an investor or a systematic strategy can capture. The ICFAI IIMC author of this critique notes "the starting point bias in the SPIVA report and the lack of asset weighting" and that fund houses pick their own benchmarks.

**The defensible read `[MY INFERENCE]`**: after fees, Indian active managers produce approximately **zero** net alpha, with the large-cap category indistinguishable from a coin toss. A systematic retail strategy should be underwritten on the assumption that it captures **2–5pp/yr of gross factor alpha**, net of ~0.2–1.5pp costs and ~2–4pp tax drag — not on beating a 10pp professional alpha that does not exist.

---

## 3. WHAT ACTUALLY FAILS

### 3.1 Retail and excessive trading — the regulator's own data `[REGULATOR]`

**SEBI, *Analysis of Intraday trading by Individuals in Equity Cash Segment* (Jul 2024).** Sample: top-10 NSE brokers ≈ 86% of individual cash clients in FY23. Peer-reviewed by a working group with academia, brokers, market experts.

| Finding | Number |
|---|---|
| Intraday loss-makers FY19 → FY22 → FY23 | **65% → 69% → 71%** |
| Loss-makers among >500 trades/yr | **80%** |
| Loss-makers, age <30 | **76%** |
| Loss-makers with >₹1 cr annual turnover | **76%**; avg P&L **−₹34,977** |
| Avg trades/yr: >₹1 cr turnover group vs <₹1 cr group | **742 vs 25** |
| Avg loss, >500 trades/yr group | **−₹61,394** |
| Avg loss, >₹1cr turnover AND >500 trades | **−₹75,443**, **81% loss-makers** |
| **Cost as % of losses, all loss-makers** | **+57%** |
| Cost as % of losses, >500 trades/yr | **+72%** |
| Cost as % of profits, profit-makers | **19%** |
| Loss-makers with 3 years' prior experience (FY19+FY22+FY23) | **54%** — better than 71% but still majority losing |

**SEBI, *Analysis of Profits & Losses in the Equity Derivatives Segment FY22–FY24* (Sep 2024):** 91.1% of individual F&O traders lost in FY24. Cumulative net loss **₹1,81,383 crore** over three years. Only **7.2%** profitable over 3 years; avg loss ₹2 lakh per person. Transaction costs **₹49,480 crore** = **25.0% of gross P&L magnitude**. Only **1.1%** of traders made >₹1 lakh profit.

**SEBI, *Equity Derivatives Segment FY25–FY26* (Aug 2026):** 87.7% of individual traders lost in FY26; aggregate net losses ₹91,685 crore; ₹25,000 crore transaction costs in FY26 (~₹1 lakh crore cumulative FY22–FY26). **STT share of transaction costs rose from 13% to 27%** while brokerage fell from 52% to 44%. 92% of aggregate losses from options. **Loss rate falls with portfolio size: 93% (no equity holdings) → 58% (>₹10 cr equity portfolio).** Among those losing in two consecutive years, **~90% lost again in year three**. Trading intensity is one of the strongest predictors of loss.

**Agarwal, Ghosh, Prabhala & Zhao, *"Animal Spirits on Steroids: Evidence from Retail Options Trading in India"*** — NSE full-panel data, 2007–June 2021, 99.6% of Indian options volume:
- Cumulative retail losses **INR 506 billion (~US$6.3 bn)**; average loss per investor **₹109,900**.
- **Lowest-volume decile: average trading return −21%.** Highest-volume decile least negative. *"Trading returns decrease monotonically as we move to the group of lowest volume traders."*
- Day trading reached **90% of volume**; 78.7% of open index-option positions were directional and unhedged.

**The transferable lesson for a swing system `[MY INFERENCE]`: turnover is the enemy, and it is monotonically so.** SEBI's own gradient (25 → 742 trades/yr; 65% → 80% loss rate) is the strongest available dose-response evidence. Every design decision that increases rebalance frequency should be justified against it.

### 3.2 Technical indicators — the literature is split for an identifiable reason

#### The "optimized indicators beat buy-and-hold" papers are data snooping

| Study | Finding |
|---|---|
| Mahajan (2015), *Asian J. Research in Banking & Finance* 5(12); IJRTE v8i3 | **"Buy and hold strategy results in profitable investments than standard MACD and RSI indicators."** On 50 Nifty 50 stocks Jan 2013–Sep 2018, **standard MACD returned −33% vs buy-and-hold**; standard RSI beat B&H by only 40%. "Optimized" MACD/RSI (parameters 10/8/11) beat B&H by 615%/470% — **fitted on the same data they report** |
| *Application of Optimized Technical Indicators*, Paripex (2017), 30 stocks Apr 2012–Mar 2015 | **"Only application of standard MACD and RSI indicators are not sufficient to trade profitably in Indian equity market."** Buy-and-hold beat standard MACD/RSI in all but 2 of 30 stocks |
| Sharma & Kennedy (1977) | Negative results for India |
| Mitra (2011) | Indian SMA-crossover rules positive **gross, but "when transaction costs were considered, this profitability did not sustain itself"** — explicitly for India |
| Lahmiri & Bouri (2018), *Finance Research Letters* / BRICS study | Technical analysis beat B&H in India and Russia, but **"in these same markets, the increase in transaction costs shifted significantly the range of the short-term MAs that were better."** Few MA combinations beat B&H |

None of these apply a multiple-testing correction. None use out-of-sample parameter selection. The "optimized beats buy-and-hold" result is the expected signature of in-sample parameter search, and it is the single most-cited Indian technical-analysis result online.

#### The one properly-corrected study — and it favours trend, not reversal

**"Technical-Indicator Strategy Performance in Indian Equities: A Joint Test of Market Efficiency, 2015–2025"** — 13 strategy configurations from 6 indicator families, **78 NSE F&O-eligible stocks**, 1 Jan 2015 – 30 Apr 2025, **Romano-Wolf (2005) StepM multiple-testing correction at 5% family-wise error rate**, 0.05% round-trip transaction cost `[WORKING PAPER]`.

| Result | Statistic |
|---|---|
| Configurations surviving correction | **8 of 13** |
| Of the 8 survivors, trend-following | **7** — SMA_10_50, SMA_20_100, SMA_50_200, MACD_12_26_9, MACD_26_52_18, Donchian_20, Donchian_55 |
| Best configuration | **Donchian_20: annualised Sharpe 1.26, RW-adjusted p = 0.0006, 12.1% p.a., alpha +7.1pp over Nifty 50 B&H** |
| SMA_10_50 | Sharpe 1.26, 12.1% p.a., alpha +7.1pp |
| MACD_26_52_18 | Sharpe 1.23 (95% CI [0.571, 1.931]), alpha +6.4pp |
| **RSI mean-reversion failures** | RSI_25_75 and RSI_30_70 **FAIL**, adjusted p = 0.071–0.473 |
| **Bollinger Band failures** | BB_20_2.0 and BB_20_2.5 **FAIL**, adjusted p 0.071–0.473 |
| **Multi-indicator confluence** | **FAILS**, adjusted p = 0.209 |
| Contrast benchmark | Bajgrowicz & Scaillet (2012): **no** technical rule survives correction on developed-market data after 1987 |

**The paper's own conclusion**: *"the failure of market efficiency is concentrated in trend-following rules and in a single aggressive mean-reversion variant, and does not extend to looser mean-reversion or Bollinger Band strategies."*

**This independently reproduces the factor finding (§1.2) at the technical-rule level: trend works, mean-reversion does not survive costs.** Two methodologically disjoint literatures converging on the same asymmetry is the strongest single piece of evidence in this report.

#### Intraday cost arithmetic

**Alphabench (Aug 2026) `[PRACTITIONER]`** — 20 NSE large-caps, minute bars, 1,633 complete sessions, ₹1,00,000 position:
- All-in intraday round trip = **10.63 bps**, of which **8.27 bps (78%) is statutory** (STT, stamp duty, exchange txn, GST, SEBI, brokerage).
- Best-of-240 gross edge found anywhere in the sweep: **3.828 bps**.
- **Variants clearing each cost bar: 0 of 240 at 10.63 bps; 0 of 240 at 8.27 bps; 0 of 240 even at the 5.91 bps perfect-maker floor.**
- 10 of 240 variants had |t| > 3 (e.g. WIPRO 15-min/15-min: +0.612 bps, t = 4.30). The author's framing: *"a t-statistic of 4.30 on an edge of 0.612 basis points is a precisely measured irrelevance."*
- **Scope limit stated by the author**: only one signal family (trailing 5/15/30-min moves) tested; no forward out-of-sample claim.

**Independently corroborated by SEBI**: intraday cost = 57%–72% of losses for frequent traders. **Intraday is structurally unviable in Indian cash equity, and the reason is the fee schedule, not signal quality.**

---

## 4. KNOWN IMPLEMENTATION PITFALLS IN INDIAN BACKTESTING

### 4.1 Survivorship bias — quantified, and non-constant

| Source | Universe / Period | Measured bias | Label |
|---|---|---|---|
| **Jain, *"Survivorship Bias in Indian Equities Is Not a Number"*, SSRN 7099378 (2026)** | PIT top-500 universes; 2×2 design: vintages {2013, 2015} × survivor definitions {"alive in panel", "resolvable on yfinance"} | **+0.8 to +3.3 pp/yr — a factor of four, same market, same construction, common end date.** Terminal-wealth inflation **+7% to +38%**. ~25% of a top-500 universe becomes invisible within a decade. **24% of a 2015 universe unresolvable on yfinance** | WORKING PAPER |
| Kohli & Deb, India Fama-French documentation (rkohli3.github.io/india-famafrench) | NIFTY 500, all-time constituents | **Annual survivorship bias, long-only EW: Value 4.4%, Size 3.53%, Momentum 3.97%.** VW: Value 3.22%, Size 1.80%, Momentum 0.57%. Of 1,117 firms: 76 vanished via merger, **78 via non-merger reasons**. Explicitly argues Agarwalla/Jacob/Varma's "negligible" bias is "significantly underestimated" | WORKING PAPER |
| arXiv:2603.19380, NIFTY Smallcap 250 | 1,437 stocks, 2016–2025 | Survivor-only overstates annual returns by **4.94 pp (26.17% → 21.23%, +23.3% relative)** and Sharpe by **0.097 (1.160 → 1.063, +9.1%)**. 82.5% removal rate: 16.1% delisted (avg −7.7%), 33.1% graduated (avg **+18.5%**), 33.2% demoted. **Bias is bidirectional** | WORKING PAPER |
| Finance-broski/backtest-bias `[PRACTITIONER, measured]` | Kaggle NSE dataset, 2010–2021 | Index-membership look-ahead added **+10% terminal wealth cap-weighted, +43% equal-weighted**. Death curve across six top-500 vintages (2012–2022): **~5–8% by 3y, 11–14% by 5y, 17–21% by 7y, 24–30% by 10y** | PRACTITIONER |
| ReaperOAK/survivorship-free-backtester `[PRACTITIONER]` | India, PIT Nifty 100/200/500 | **"Raw momentum 'Sharpe ~1.5' → ~1.0 corrected"** — survivorship inflates Sharpe by ~+0.4 to +0.9 | PRACTITIONER |
| QuantRocket primer `[PRACTITIONER]` | Global | Looking back 10 years: North America missing 75%, Europe 50%, **Asia ~25%** of what traded | PRACTITIONER |

#### The critical caveat for YOUR universe `[MY INFERENCE]`
**Every bias figure above is measured on NIFTY 500 / NIFTY Smallcap 250 / top-500 universes — none on NIFTY 50.** The mechanism differs qualitatively:
- Top-500 universes have 17–30% of names dead within a decade (measured). NIFTY 50 has near-zero *delisting* — its failures (Satyam, IL&FS, DHFL, Yes Bank, Vodafone Idea) stayed listed and tradable while going to zero, so their returns are in your price data regardless of index removal.
- NIFTY 50 reconstitution history is well documented by NSE Indices, and membership is a live, publicly specified rule.
- **Expect low-single-digit pp/yr of survivorship bias for a NIFTY-50 backtest, not 4–5pp.** The commonly quoted "5% per year survivorship bias in India" is a *small/mid-cap* number and is almost certainly not applicable to you.

**Diagnostic test `[PRACTITIONER, agree]`**: if your NIFTY-50 panel contains **zero** names whose price series terminates before your end date, your panel is broken. A correct NIFTY 50 panel 2002→2026 will contain Satyam (delisted/merged 2013), IL&FS, DHFL, Yes Bank, Vodafone Idea, Jet Airways and similar.

### 4.2 Corporate action handling — the traps specific to India

- **Satyam Computer Services**: trading near ₹188 before the 7 Jan 2009 confession of ₹5,040 crore fictitious cash (part of a ~₹7,136 crore fraud); **fell to ₹11.50 within days — ~94% loss**. Was a NIFTY 50 constituent and an NYSE ADR. Merged into Tech Mahindra June 2013. *"For any strategy that held it through the 2008–2009 period, it was a near-complete capital loss."* `[PRACTITIONER, but the facts are well documented]`
- **Kingfisher Airlines**: operations suspended 20 Oct 2012; formally delisted from NSE 30 May 2018. *"For any strategy screening for 'consumer brand stocks' or 'aviation sector exposure' in the early 2010s, Kingfisher was precisely the kind of company that would have appeared and precisely the kind of loss that would have been invisible."*
- **Ticker reuse / demergers are an unsolved problem in Indian free data**: `nsepit` (practitioner) states it ships **no default rename map** because *"a rename that rides on a demerger carries a real price break that needs a human decision."* Tata Motors → TMPV; Zomato → ETERNAL. Without manual intervention the old print sits under the new symbol and the price history is silently stitched.
- **Static-CSV membership lists are unverifiable**: `nsepit` refuses to emit output unless it passes an exactly-50-members-at-every-month-end invariant, no duplicate symbols, every name mapped to a traded symbol, plus 20 hard-coded spot checks against known index events.
- **Corporate-action "snapping" is fallible**: `nsepit` states plainly, *"A real disaster that gaps exactly like a clean ratio on both legs will still fool it; the harness measures that failure rate, it does not abolish it."* `[MY INFERENCE]`: Satyam is exactly such a case — a 94% single-day collapse that a ratio-detector could misread as a split.
- **Free data silently erases the dead**: *"delisted names are exactly the ones free price vendors erase."* The NSE bhavcopy (daily settlement file) is identified as the one free source that cannot have that hole, because it lists every security that traded that day.

### 4.3 STT and the cost stack — the number is smaller than you think

**Zerodha official rates, equity delivery `[BROKER, primary source]`:**

| Charge | Delivery rate |
|---|---|
| Brokerage | **₹0** |
| **STT** | **0.1% on buy AND 0.1% on sell** |
| Exchange transaction (NSE) | 0.00307% of turnover (BSE 0.00375%) |
| GST | **18% on (brokerage + SEBI + transaction charges) — NOT on STT or stamp duty** |
| SEBI | ₹10 / crore = 0.0001% |
| Stamp duty | **0.015% on buy side only** |
| DP charges | ~₹13.5 + 18% GST ≈ **₹15.9 per scrip per delivery sell**, flat, independent of size |

**Two independent itemised round-trips converge tightly on ~11.7 bps of turnover:**
- ₹1,40,000 buy + ₹1,47,000 sell = ₹2,87,000 turnover → total charges **₹334.33** = **11.65 bps of turnover** (STT ₹287, stamp ₹21, exchange ₹8.53, DP ₹15.93, SEBI ₹0.29, GST ₹1.58) `[PRACTITIONER: OneTradeJournal, line-by-line itemisation]`
- ₹1,50,000 buy + ₹1,60,000 sell = ₹3,10,000 turnover → total charges **₹361.37** = **11.66 bps of turnover** `[PRACTITIONER: sum.money, line-by-line itemisation]`

⚠️ **Two broker calculators state higher figures and appear wrong**: decidecalc says "about 0.22% of trade value"; calxo computes STT as 0.1% of *turnover* rather than 0.1% of each leg. Both contradict the itemised arithmetic above by roughly 2x. **Use 11.7 bps of turnover.**

#### The implication for your rebalance frequency `[MY INFERENCE]`

| Annual two-way turnover | Annual cost drag at 11.7 bps |
|---|---|
| 100% (sell everything, buy everything, once a year) | **0.12%/yr** |
| 200% (monthly full rotation of a 20-stock book) | **0.23%/yr** |
| 400% (weekly partial rotation) | **0.47%/yr** |
| 1000% (aggressive) | **1.17%/yr** |

**STT is NOT the binding constraint on a weekly/biweekly NIFTY-50 swing system.** Even at 400% annual turnover the drag is under 0.5%/yr. This is the opposite of the usual folk wisdom and it is a direct consequence of the 0.1%-each-side structure being applied to a *low-turnover* book.

Two caveats:
1. **DP charges are a small-book tax.** ₹15.9 per scrip per sell, flat. Selling 20 names daily costs ₹318/day = ~₹77,000/yr ≈ **3.7% of a ₹21L book** `[MY INFERENCE]`. At weekly/biweekly rebalance with ~20 names, DP ≈ ₹16,000–32,000/yr = 0.08–0.15%/yr. Manageable but not zero — it penalises small per-trade sizes, not small portfolios.
2. **Income tax is the real drag, not STT.** LTCG on equity above ₹1.25L is 12.5%; STCG is 20%. A backtest reporting pre-tax returns overstates net returns substantially. One practitioner backtest explicitly books a **4.02% annual tax drag**, taking Value-Quality from ~15.4% gross to **11.38% net** `[PRACTITIONER: BacktestIndia]`.

### 4.4 Index rebalancing effects

- **Mechanics**: NIFTY 50 reconstitutes semi-annually (effective March and September); NIFTY 500 also semi-annual. Passive AUM forced-selling at the rebalance creates a temporary price dislocation in the removed name.
- **NSE Indices' own evidence on multi-factor construction** `[INDEX VENDOR, backtest Apr 2005–May 2017]`:
  - 2008 downturn: NIFTY Alpha portfolio **−66.96%** vs NIFTY Alpha Quality Low-Volatility 30 **−43.93%** — a **23pp drawdown reduction** from factor diversification.
  - 2016: Low-Volatility portfolio +1.83% vs NIFTY Alpha Low-Volatility +8.02%.
  - Multi-factor return-to-risk **0.87–1.08 since inception vs ~0.58 for cap-weighted**.
  - Sector concentration reduced by combining factors (Quality was IT/consumer/pharma/auto-heavy; Low-Vol was consumer/energy/financial-services-heavy).
- **The dropout effect — practitioner evidence only, weak**: 25 NIFTY 50 removals since 2014 (non-merger exits), returns from removal date to 19 Mar 2025: **13 of 25 beat NIFTY 50**; excluding 4 fundamentally broken names (Vodafone Idea, IndiaBulls Housing Finance, Yes Bank, Zee Entertainment), **61.9% of the remaining beat the index.** Standouts: Tata Power **+348.6%** after 2017 removal vs NIFTY +133.2%; JSW Steel +461.6% vs +181.8% after 2015; Bharti Infratel +275.2% after 2020 removal `[PRACTITIONER: Echo-nomist, n=25, hindsight, no costs, no sector controls]`.
  - **Note the perverse implication `[MY INFERENCE]`: this argues for preferring index members over non-members, not the reverse.** Being kicked out of NIFTY 50 correlated with later fundamental problems in the excluded names. And the effect is not implementable at ₹21L without event-driven capacity.
- **⚠️ Flag: the "NIFTY factor indices beat NIFTY 50 by 5–7pp p.a." claim is in-sample backtested marketing material** `[INDEX VENDOR]`. The same construction tested out-of-sample by Lalwani found **zero of nine indices with significant alpha post-launch**, and average market beta *increased* by ~0.09 in the test period. Treat the whitepaper as evidence about *construction principles*, not about *returns*.

### 4.5 The data-reality constraint specific to your situation

`GOAL.md`'s own audit stands: 1-minute history is ~1,800 bars / ~30 days and intraday is banned. This survey found no evidence that contradicts that and found strong evidence *for* it: the Alphabench 240-variant intraday sweep (0 of 240 clearing even a perfect-maker cost floor), SEBI's 71%/91%/88% retail loss rates, and 57–72% cost-to-loss ratios. **The intraday ban in your constitution is empirically correct and should not be revisited.**

---

## 5. ROBUST RECOMMENDATIONS — FACTOR COMBINATIONS WITH THE BEST LONG-ONLY TRACK RECORD

### 5.1 The best-documented Indian long-only multi-factor construct: the Conservative Formula

**Van Vliet & Blitz (2018) Conservative Formula, replicated for India** — QED Capital, SSRN 4163613 / qedcap PDF `[WORKING PAPER]`:

- **Rule**: rank 100 most-liquid stocks by (i) **low realised volatility**, (ii) **high net payout yield**, (iii) **positive price momentum**. Quarterly rebalance. **No accounting data required.**
- **Result**: outperformed S&P BSE 100 by **12.6% p.a. compound**. Returned 24% cumulative since 2006. Outperformed the mirror-image "Speculative" portfolio (high risk, low payout, negative momentum) by **17% cumulative**. **"The returns hold the nett of fees."**
- **Factor decomposition**: positive loadings on low-vol, momentum (WML) and quality (RMW). FF3 alpha 7.9% p.a.; **FF5 alpha 5.5% p.a. and less significant; adding low-vol as a 7th factor leaves no alpha.** So the entire edge is explained by three known factors.
- **Regime behaviour**: outperformed the benchmark and the speculative portfolio across different business cycles.
- **Turnover**: explicitly low unoptimised turnover; hence survives costs.
- Portfolio volatility 22.6%.
- **It beat "all Fama-French combinations of common investment strategies based on size, value, profitability, investment and momentum."**

### 5.2 The best-documented Indian long-only factor-comparison study

**QED Capital, *"Long Factors, not Short change: Long Only Factor Portfolios in India"*, SSRN 4000418** `[WORKING PAPER]` — monthly-rebalanced, equal-weighted, long-only winner portfolios from the **top 200 Indian stocks**, Jan 2007–Oct 2021 (178 months; FF4 over 172 months):

- Momentum, low-volatility and quality each deliver alpha; **alpha survives real-world implementation costs.**
- **Market exposure is significant across all style strategies → inter-strategy correlations far higher than academic long-short factor correlations.**
- **Not all implementations of a factor are the same** — alternative calculation methodologies matter.
- **Low-volatility and quality show fairly low turnover; momentum does not.**
- **Size and sectoral preferences of factors are dynamic**, which reduces perceived diversification benefits.
- Factor exposure persistence varies by strategy and must be considered at implementation.
- Cites Raju & Chandrasekaran (2019): a large-cap long-only momentum factor-tilt portfolio in India shows **partial** exposure to the momentum factor. Also cites Raju (2019) on the quality factor tilt in Indian large-caps, adapting Asness et al. (2018).
- Supports Blitz et al. (2020): **most of the value-add from long-short factor strategies comes from the long legs.**
- Supports Huij et al. (2014) and Arnott et al. (2017): long-only and long-short factor implementations are materially different.

### 5.3 Indian evidence on blending specifically

| Source | Finding | Label |
|---|---|---|
| Invesco (May 2026) | Multi-signal construction improves EM factor Sharpes materially over generic definitions — **value 0.45 → 1.13, momentum 0.56, quality 0.36**. Gains come from **signal diversification reducing idiosyncratic noise**. But residual country/industry tilts persist (multi-signal momentum still shows −16.0% to +16.5% industry tilts) | PRACTITIONER |
| NSE Indices / Mondovisione | Multi-factor return-to-risk **0.87–1.08 vs 0.58 cap-weighted**; 23pp drawdown reduction in 2008 | INDEX VENDOR (in-sample backtest) |
| Vasishth & Sehgal (2019) | **Value and growth premiums are negatively correlated (−0.214)**; **bivariate value+growth portfolios are unexplained even by FF5**. Univariate value/growth returns ARE explained by CAPM/FF3 — *"the return earned by univariate growth and value investing style is merely a compensation for risk"* | PEER-REVIEWED |
| "Profitability of Style based Investment Strategies: Evidence from India" (NSE 200) | **Best risk-adjusted strategies are conditional bivariate combinations**: E2L1 (earnings momentum–liquidity), M2S1 (price momentum–size), E2M3 (earnings momentum–price momentum) at **1.1%/month**. **But bivariate strategies do NOT outperform univariate on absolute-return basis.** FF3 explains 42% of residual strategies; **Carhart and FF5 add almost no incremental explanatory power** → FF3 recommended as the India baseline. **Long-run momentum weaker than short-term → contrarian strategies abandoned** | PEER-REVIEWED |
| BacktestIndia 18-yr NSE study (1,700+ stocks incl. delisted, Dec 2006–Jun 2025, EODHD) `[PRACTITIONER]` | Quality-Momentum **17.95% CAGR, Sharpe 0.86, −61.7% DD, 41mo recovery**; Multi-factor 14.61% CAGR, Sharpe 0.48, −55.0% DD, 20mo recovery; Momentum 14.01%, Sharpe 0.35, −70.5% DD, 65mo recovery; Low-vol 12.38%, Sharpe 0.38, −44.6% DD, 7mo recovery; Value-Quality 11.38% net after 4.02% tax drag; **Nifty 50 10.42% CAGR, Sharpe 0.21, −55.1% DD, 60mo recovery** | PRACTITIONER — see warning |

⚠️ **Warning on the 17.95% figure.** A 7.5pp/yr excess over Nifty with −61.7% drawdown and Sharpe 0.86 implies **high systematic beta and a large size tilt**, not a low-risk factor blend. It comes from one non-peer-reviewed source with undisclosed universe construction. Do not use it as a return target.

### 5.4 Explicit evidence gap: rebalance frequency

**There is no published Indian study supporting a weekly or biweekly rebalance for a factor strategy.** The Indian evidence clusters at:
- **Quarterly** — Conservative Formula (QED), Nigam & Pandey
- **Monthly** — QED long-only factor portfolios (SSRN 4000418)
- **Monthly** — academic long-short constructions throughout

**`[MY INFERENCE]` Your planned weekly/biweekly rebalance is not supported by any Indian evidence I could find, and the three independent lines of evidence above all point the other way:**
1. QED long-only study: **low-vol and quality show fairly low turnover; momentum does not.** Weekly rebalancing applies full turnover to the highest-turnover factor.
2. SEBI gradient: turnover is monotonically associated with losses (25 → 742 trades/yr).
3. STT: weekly rotation at 400% annual turnover costs 0.47%/yr vs 0.12%/yr for annual.

**Recommendation**: use **monthly signal evaluation with quarterly portfolio realisation**, or at minimum add a turnover budget (e.g. "no more than 20% of the book changes per rebalance; carry the rest"). This is a design change from your current spec, and it is the single highest-value, best-evidenced adjustment in this report.

### 5.5 Evidence gaps — stated explicitly, not filled with guesses

1. **No peer-reviewed, point-in-time, cost-net, walk-forward study of a long-only NIFTY-50 (as opposed to NIFTY 200/500) swing strategy exists** that I could locate. The strongest long-only India evidence is on NSE 200/500, top-200, or BSE 100 universes.
2. **No India-specific short-term (1-month) reversal result net of costs.** The evidence points to *continuation* instead.
3. **No rigorous quantification of NIFTY-50 survivorship bias.** All measured figures are for top-500/small-cap universes.
4. **No rigorous India study of index-rebalancing effects as an exploitable factor.**
5. **No Indian evidence on a market-timing or cash-regime overlay.** The QED long-only study's finding that long-only factor portfolios carry *significant market exposure* implies a de-risking overlay has real work to do — but Singh & Walia's time-series momentum is the only India-specific published support, and it has not been tested as a standalone overlay.
6. **No published Indian Sharpe ratio above ~1.0 net of costs for a long-only equity strategy.** The arXiv physical-momentum study found *all* long-short momentum portfolios below 1.0; the Corrected-Technical-Indicators study's 1.26 Sharpe is long-short and trend-following.

---

## BOTTOM LINE

### The 5 most defensible design choices for a long-only NIFTY-50 swing system

**1. Make trend/momentum the primary alpha engine; do not build a mean-reversion core.**
Two methodologically disjoint literatures converge. The Indian factor literature finds **short-term continuation, not reversal** (Sehgal/Jain; IIMC 2020), and finds **no long-horizon momentum reversal** in India at 2–5 years (contradicting Lee-Swaminathan). Independently, the only multiple-testing-corrected Indian technical study found **7 of 8 surviving rules were trend-following**, with RSI mean-reversion and Bollinger variants all failing (adjusted p 0.071–0.473). Best Indian long-only risk-adjusted result: **lagged 6-month compounded return, quarterly rebalance** (Nigam & Pandey 2023). Best peer-reviewed long-short read: **17.3% p.a. at 17.06% vol → Sharpe ≈ 1.01** (Agarwalla et al. 2018) — but you cannot harvest a long-short spread long-only.
*Avoid entirely:* the "optimized MACD/RSI beats buy-and-hold" claim. Its own source paper reports **standard MACD at −33%**; the outperformance appears only after in-sample parameter fitting.

**2. Make low-volatility / low-beta the second pillar — it is your best long-only-constrained factor.**
India-specific, large-cap-compatible, low-turnover, and long-only by construction: **low-vol decile 11.40% vs high-vol 1.30% annualised excess**, surviving size/value/momentum controls (Joshipura & Joshipura 2016), confirmed on 4,400 stocks over 19 years with no time decay (QED SSRN 4398656). It is **largely a beta effect** — accept that you will lag the benchmark in strong bull markets and be paid in drawdowns.

**3. Add quality/profitability-payout as the third pillar — it is the best-documented long-only fit and the most India-specific claim.**
Long-only quality alpha of **0.69%/month**, driven by profitability and payout, with **explicitly low churn, lower risk, shorter drawdowns, and stated viability long-only in large caps** (IIMA SSRN 4284686). Use **net payout yield** as the proxy — it requires no accounting data, which is exactly why the Conservative Formula generalises.

**4. Blend all three rather than picking one — and expect the blend's edge to be factor exposure, not skill.**
The Conservative Formula (low vol + high net payout + positive momentum, 100 stocks, quarterly) is the single best-documented Indian long-only construct: **outperformed BSE 100 by 12.6% p.a., beat the speculative mirror portfolio by 17%, and held up net of fees** (QED SSRN 4163613). Its own factor decomposition shows **no alpha left** once low-vol, momentum and quality are controlled — that is, the edge *is* the factor exposure. NSE's own multi-factor indices show return-to-risk of 0.87–1.08 vs 0.58 cap-weighted. QED's long-only study is the key warning: these portfolios are **beta-laden** and **"not one factor-style is a consistent winner."**
**Explicitly exclude value.** Post-2008 the Indian value premium has "nearly ceased to exist" (Subramaniam/Sharma/Sehgal 2018); growth beat value in a peer-reviewed study (Sharma/Jain/McMillan 2020); and of nine NSE factor indices, **zero generated significant alpha out-of-sample** (Lalwani). **Explicitly exclude size/liquidity** — you cannot harvest it at ₹21L, and IIMA's survivorship-corrected SMB is ≈0%.

**5. Change the rebalance cadence and treat the return target honestly. Turnover discipline, not STT, is your main lever.**
Your weekly/biweekly plan is **unsupported by any Indian evidence** — the Indian factor literature uses monthly or quarterly. At **11.65–11.66 bps of turnover** (two independent itemisations), a weekly 400%-turnover book pays **0.47%/yr** vs **0.12%/yr** annually — and against SEBI's monotone loss gradient (25 → 742 trades/yr; 65% → 80% loss rate) that is a bad trade. Move to monthly signal evaluation / quarterly realisation, or impose a turnover budget. **The binding drag on your net return is income tax (~4%/yr when realising gains), not STT.** And underwrite the project on the assumption that Indian active managers earn **≈0 net alpha after fees** (425 funds, Jan 2013–Dec 2024, SSRN 5370113) — not on beating a 10pp professional edge that does not exist.

### Realistic vs fantasy return levels

| Level | Verdict | Basis |
|---|---|---|
| **10–14% p.a. net** (~0.8–1.1%/month) | ✅ **REALISTIC. This is your target.** | Sits at/above Nifty 50 TRI long-run CAGR (12.44% 20yr; 14.2% since 1999) and vastly above the median Indian large-cap active fund (+0.07pp/yr vs benchmark, direct plan, survivors only). Requires 2–5pp/yr of gross factor alpha net of ~0.2–1.5pp costs and ~2–4pp tax drag. |
| **15–18% p.a. gross, Sharpe 0.6–0.9** | ⚠️ **STRETCH but defensible — top of the honest band.** | Consistent with the strongest Indian multi-factor studies (Conservative Formula +12.6pp over BSE 100; a practitioner 18-yr Quality-Momentum at 17.95% vs Nifty 10.42%). But note these are in-sample-flavoured, and the Sharpe 0.86 / −61.7% DD profile implies substantial beta and size exposure, not low risk. **Also: no 10-year Nifty 50 TRI window on record exceeded 22.1%** — an 18% strategy would need to sit near the historical ceiling for a decade. |
| **Shrinkage: expect Sharpe 0.3–0.6 net** | ✅ The honest expectation | Long-only factor portfolios in India are beta-laden (QED); the arXiv physical-momentum study found **all** momentum portfolios at Sharpe < 1.0; a practitioner corrected survivorship moved momentum from "Sharpe ~1.5" to "~1.0". |
| **42.6% p.a. (3%/month)** | ❌ **FANTASY. Do not build the system around it.** | **3.0–3.4x** the entire long-run TRI return of the index (14.2% since 1999 / 12.44% over 20yr). **2.5x** the best peer-reviewed Indian long-short WML. **~30x** the compounded return of the Conservative Formula. **1.9x** the single best 10-year window on record. One calendar year (2006, +41.9%) equals a full year of the target. **No academic, regulatory, index-vendor or credible practitioner source in this survey supports anything above ~20% gross for a long-only Indian strategy.** |
| **Anything above 20% p.a.** | ❌ Fantasy at this capital size | No Indian source exceeds this for a long-only strategy, and you are structurally excluded from the size and liquidity factors that return the most in the Indian cross-section (2.7%/month and 2.2%/month respectively in the NSE 200 study) because ₹21L cannot harvest them. |

### Widely claimed but poorly evidenced — do not use these

1. **"Indian momentum has a Sharpe ratio of 6–8"** (Kedia 2024) — economically impossible unlevered; almost certainly unbounded construction + zero costs.
2. **"Optimized MACD/RSI beats buy-and-hold in India"** — data snooping. The same paper reports *standard* MACD at **−33%**.
3. **"Indian active funds returned 22% p.a. vs 12% for NIFTY since 1997"** (CRISIL-AMFI) — asset-weighted, and constituents restricted to CRISIL-**ranked** (surviving, top-quartile) funds. Selects on past performance and excludes dead funds.
4. **"NIFTY factor indices beat NIFTY 50 by 5–7pp p.a."** — index-vendor in-sample backtest. The same construction tested OOS yields **zero significant alpha post-launch**.
5. **"Multi-factor Indian portfolios deliver 17–18% CAGR"** — one non-peer-reviewed backtest, likely embedding size and high-beta exposure (note the −61.7% drawdown).
6. **"Survivorship bias is ~5% per year in India"** — that is a *NIFTY 500 / Smallcap 250* measurement. For NIFTY 50, where constituents delist almost never but instead trade to zero, expect low-single-digit pp/yr. Unmeasured for your universe.
7. **"SEBI data proves retail can't win"** — it proves *frequent* retail can't win. The SEBI gradient is monotone in turnover, and 54% of traders with 3 years' prior experience still lost, but that group is still losing more than half the time. This evidence constrains cadence, not the existence of an edge.
