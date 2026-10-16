# Instrument cost model — NSE

**Deliverable:** `research/instruments.py` (this report explains it; run
`.venv/bin/python research/instruments.py` to print every table live).

**Scope:** a cost model, not a strategy. It answers one question — what does one round
trip cost in each of three instruments, and how much of a 24 bp/yr edge does that
consume? It does not recommend an instrument.

**Research date:** 2026-10-16. Every rate below carries a source URL and an "as of"
date in the source file. Anything not confirmed against a primary source is tagged
`UNVERIFIED` and says what would settle it.

---

## 0. Headline

| | delivery equity | **Nifty 50 ETF** | Nifty futures |
|---|---|---|---|
| statutory, per round trip | 22.34 bp | **2.42 bp** | 5.88 bp |
| + slippage (2 × per-side) | +10 bp | +4 bp | +2 bp |
| **all-in, per round trip** | **32.34 bp** | **6.42 bp** | **7.88 bp** |
| expressed against *total turnover* | 11.17 bp | 1.21 bp | 2.94 bp |
| annual bill at 12 round trips | 388 bp/yr | **81 bp/yr** | 115 bp/yr |
| round trips/yr affordable on a 24 bp edge | 0.74 | **3.12** | 0.51 |

The ETF is **5.0× cheaper per round trip than delivery equity**, and **1.2× cheaper than
index futures**. The 5× is the headline; note that futures are far closer to the ETF than
to delivery equity, so "switch to futures" buys very little on cost grounds alone.

It is also **not enough on its own.** At 12 round trips/yr the ETF still costs 81 bp/yr
against a 24 bp/yr edge. It cuts the gap from ~16× to ~3.4×; it does not close it. The
brief's hypothesis ("~131 bp/yr → ~20 bp/yr, flips to break-even") does not survive
contact with the rate card, and §5 explains why the ETF cannot get to 20 bp/yr at that
turnover.

---

## 1. Verified rate table

### 1.1 Delivery equity (NSE, retail, Zerodha-class zero-brokerage delivery)

| charge | rate | side | source | as of |
|---|---|---|---|---|
| STT | 0.100% | **buy and sell** | [NSE STT & other levies](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies) | w.e.f. 2026-04-01 |
| NSE txn (+IPFT) | 0.00307% | both | [NSE/FA/73061](https://nsearchives.nseindia.com/content/circulars/FA73061.pdf) | eff. 2026-03-01 |
| SEBI turnover | 0.0001% (₹10/cr) | both | NSE STT & levies page | 2026-10-16 |
| Stamp duty | 0.015% (₹1500/cr) | **buy** | [NSE stamp duty](https://www.nseindia.com/static/invest/first-time-investor-stamp-duty-charges-taxes) | since 2020-07-01 |
| Brokerage | ₹0 (delivery) | — | [zerodha.com/charges](https://zerodha.com/charges/) | 2026-10-16 |
| DP | ₹15.93 + GST | **sell**, flat | [Zerodha DP](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/what-do-dp-charges-mean) | 2026-10-16 |
| GST | 18% on (brokerage + txn + SEBI) only | — | zerodha.com/charges | 2026-10-16 |

**Re-verification result: the existing 11.92 bp figure is correct in substance.** At the
size of the published itemisations (₹1,40,000 buy + ₹1,47,000 sell) this module gives
**11.76 bp of total turnover** against the two independent figures in
`reports/FACTOR_EVIDENCE.md` §4.3 of 11.65 and 11.66. The 0.10 bp gap is entirely GST on
the DP charge, which the broker does bill (Zerodha: ₹13 + 18% GST) and which `costs.py`
omits. Because DP is flat, the bps figure is size-dependent and this module reports it at
the size asked for: 13.01 bp at ₹50k, 12.06 bp at ₹1L, 11.78 bp at ₹1.43L, 11.17 bp at
₹21L.

Two corrections to the *surrounding* documentation, not the rate:

- **STT on delivery is two-sided and has been since Oct 2024.** Confirmed unchanged for
  the 1 Apr 2026 revision. A one-sided model understates delivery cost ~2×.
- **`costs.py` DP of ₹15.93 vs Zerodha's published ₹15.34** (₹13 + 18% GST). Zerodha's
  is the lower, published-today figure; this module keeps ₹15.93 as the pre-GST base and
  adds GST on top, giving ₹18.80 — deliberately the pessimistic side.

### 1.2 Nifty 50 ETF (NIFTYBEES — equity-oriented, delivery)

| charge | rate | side | source | as of | status |
|---|---|---|---|---|---|
| STT | **0% buy / 0.001% sell** | sell | [NSE STT table](https://www.nseindia.com/static/invest/first-time-investor-sebi-turnover-fees-stt-other-levies); [Zerodha ETF STT](https://support.zerodha.com/category/account-opening/resident-individual/ri-charges/articles/stt-etfs) | 2026-10-16 | `CONFLICT` |
| NSE txn (+IPFT) | 0.00307% | both | NSE/FA/73061 | 2026-03-01 | `UNVERIFIED` |
| SEBI turnover | 0.0001% | both | NSE STT page | 2026-10-16 | VERIFIED |
| Stamp duty | 0.015% | buy | NSE stamp duty page | 2020-07-01 | `UNVERIFIED` |
| Brokerage | ₹0 | — | zerodha.com/charges | 2026-10-16 | VERIFIED |
| DP | ₹13 + GST | sell, flat | Zerodha DP page | 2026-10-16 | VERIFIED |
| **Expense ratio** | **0.04%/yr (4 bp)** | carried | [Nippon factsheet](https://mf.nipponindiaim.com/FundsAndPerformance/Presentation/NipponIndia-ETF-Nifty-50-BeES-Aug-2026.pdf) | 2026-08-31 | VERIFIED |

**Why the ETF is cheap: STT is 99.95% smaller.** Delivery pays 0.1% on each side
(20 bps of notional per round trip); the ETF pays 0.001% on the sell only
(0.1 bps). That alone is **19.9 bp of the 29.9 bp saving.**

Conflicts and gaps, stated rather than papered over:

- `CONFLICT` — one Zerodha Fundhouse page quotes ETF STT at **0.002%**, contradicting
  Zerodha's own Varsity page and the Finance Act schedule, both of which say 0.001%.
  The statutory 0.001% is used; the higher broker-quoted figure is recorded.
- `UNVERIFIED` — NSE publishes a cash-segment transaction charge and ETPs trade in the
  capital market segment, but **no NSE tariff line specific to ETPs could be located**.
  Assuming the cash rate (0.00307%). *To settle it:* the ETP line of the NSE Schedule of
  Charges for FY 2026-27, or one ETF contract note. Even if it were double the cash rate
  the ETF would still win by ~4 bp — the conclusion is not sensitive to this.
- `UNVERIFIED` — NSE's stamp table says 0.015% for "transfer of security other than
  debenture on delivery basis" but does not say whether a mutual-fund unit falls in that
  phrase. Zerodha states ETF charges match equity apart from STT. 0.015% assumed — the
  conservative reading. *To settle it:* the stamp line of one ETF contract note. If ETF
  stamp duty were **nil**, the ETF round trip drops from 2.42 to 0.92 bp — a material
  1.5 bp, so this one is worth checking before acting on these numbers.

### 1.3 Nifty 50 index futures

| charge | rate | side | source | as of |
|---|---|---|---|---|
| **STT** | **0.050%** | **sell only** | [NSE equity-deriv STT](https://www.nseindia.com/static/products-services/equity-derivatives-securities-transaction-tax); [BSE notice 20260331-7](https://www.bseindia.com/downloads/UploadDocs/Notices/20260331-7/20260331-7.pdf) | **eff. 2026-04-01** |
| NSE futures txn (+IPFT) | 0.00183% | both | NSE/FA/73061 | eff. 2026-03-01 |
| SEBI turnover | 0.0001% | both | NSE STT page | 2026-10-16 |
| Stamp duty | 0.002% (₹200/cr) | **buy** | [NSE stamp duty](https://www.nseindia.com/static/invest/first-time-investor-stamp-duty-charges-taxes); [CCIL](https://www.ccilindia.com/tr-stamp-duty); [SEBI FAQ](https://www.sebi.gov.in/sebi_data/faqfiles/dec-2021/1639980911330.pdf) | since 2020-07-01 |
| Brokerage | min(0.03%, ₹20)/order | both | zerodha.com/charges | 2026-10-16 |
| DP | none | — | — | — |

Two findings that contradict common assumptions:

1. **Futures STT more than doubled.** The **Finance Act 2026** raised equity-futures STT
   from **0.02% to 0.05%** on the sell side, effective **1 April 2026**. Any futures cost
   estimate built before April 2026 is understated by 3 bp per round trip. This is the
   single most important change to the schedule and it makes futures *less* attractive
   than the brief anticipated.

2. **Futures are not stamp-duty-free.** Since the Finance Act 2019 amendments took effect
   on 1 July 2020, stamp duty at **0.002% has applied to equity futures, on the buyer
   side** — confirmed by NSE's own stamp-duty table, CCIL, and the SEBI FAQ. The brief's
   premise that futures have no stamp duty is wrong. The rate is small, but it is real
   and it sits on the *opposite* side from futures STT.

Net effect of both: a futures round trip is **7.88 bp** all-in, not the ~3 bp a
pre-2026 practitioner would assume. **Futures are the second-cheapest option here, and
behind the ETF.**

---

## 2. Annual cost bill

At ₹21,00,000 per position, in bp of mission capital per year. "Round trips/yr" counts
complete buy+sell cycles on the same notional.

| round trips/yr | delivery equity | **Nifty 50 ETF** | Nifty futures |
|---|---|---|---|
| 0.5x | 16.2 | **7.2** | 23.9 |
| 1x | 32.3 | **10.4** | 27.9 |
| 2x | 64.7 | **16.8** | 35.8 |
| 4x | 129.4 | **29.7** | 51.5 |
| 12x | 388.1 | **81.0** | 114.6 |

Futures figures include 4 rolls/yr × 5 bp = 20 bp of assumed roll cost (§4). The ETF
figure includes its 4 bp/yr expense ratio. Delivery has no carried drag.

### Breakeven turnover

Against the measured median gross edge of **24 bp/yr**
(`reports/PERSTOCK_EDGE_VS_COST.md`: +1.0 bp/day × 244 sessions):

| instrument | round trips/yr affordable | net at 12 RT/yr | verdict |
|---|---|---|---|
| delivery equity | 0.74 | **−364 bp** | fails badly |
| **Nifty 50 ETF** | **3.12** | **−57 bp** | closest to viable |
| Nifty futures | 0.51 | **−91 bp** | fails |

**The binding operational conclusion: with a 24 bp/yr edge, no instrument on this list
survives monthly rebalancing.** The ETF gets the project to roughly 3 round trips per
year — a quarterly signal — before the cost consumes the whole edge. That is a real
finding and it is more actionable than a 5× cost reduction alone: it converts
"the signal is too weak" into a specific, testable turnover budget.

---

## 3. Drop-in verification

`Instrument.fee_schedule(notional)` returns `research.optimize.config.FeeSchedule` —
**the optimizer's own class, constructed with the optimizer's own constructor**. There is
no wrapper, no adapter, no signature change, and no edit to `src/nsealgo/costs.py` or
`research/optimize/`. Proof, from the module's `drop_in_demo()`, running
`dual_moving_average` on RELIANCE daily bars, 2008-01-01 → 2026-10-01, capital
₹21,00,000, monthly rebalance, tax off:

```
  existing FeeSchedule (config.STATUTORY_BPS=11.92): fees=Rs 111,984.78  CAGR=-0.84%
  delivery_equity   statutory_bps=22.34               fees=Rs 161,966.18  CAGR=-1.04%
  nifty_etf         statutory_bps= 2.42               fees=Rs  33,866.19  CAGR=-0.52%
  nifty_futures     statutory_bps= 5.88               fees=Rs  41,444.96  CAGR=-0.59%
```

Same call signature, same strategy, same data, only `fees=` differs.

**Why the bridge works.** `FeeSchedule` carries two numbers, and
`backtest._fee` charges `round_trip_bps / 2` on a single leg's traded notional. So the
field it actually needs is **statutory cost in bps of the one-way notional** — exactly
what `Instrument.round_trip_bps(notional)` returns. `notional` is a required argument,
not a default, because collapsing the flat DP charge and the ₹20 brokerage cap into one
bps rate is only valid at one trade size.

### ⚠️ The bridge also exposed a live bug in `research/optimize/config.py`

`config.STATUTORY_BPS = 11.92` is **a bps-of-turnover number being consumed as
bps-of-notional.** `backtest._fee` divides by one leg's notional; `costs.py`
`round_trip_bps` divides by `2 × notional`. Those differ by ~2×. The error is partly
masked because slippage is packed into the same field and the DP charge inflates the
turnover-denominated figure.

Net effect on the sweep: **per round trip the true delivery bill is ~32.3 bp of notional,
not 21.92 — an understatement of 1.475×.** See §6. I do not own `config.py`, so I have
not changed it; `research/instruments.py` produces the corrected schedules and the
demonstration above is the fix's test case.

---

## 4. Risks — what is modelled and what is not

### Modelled
Statutory and regulatory charges per instrument, itemised per side, in Decimal; one-way
and two-way bps; brokerage caps; flat DP charges; per-notional slippage (equity 5 bp,
ETF 2 bp, futures 1 bp — **assumptions**, no exchange publishes them); futures roll cost
(5 bp/roll, **assumption**); ETF expense ratio (4 bp/yr, verified).

### Not modelled — and these are not small

**Futures-specific, and they dominate everything the bps table says:**

- **Margin.** ~10% SPAN means ₹21 lakh of notional immobilises ~₹2.1 lakh. This model
  prices the *trade*; it does not charge for the capital that margin locks up, nor for
  margin calls at 12–20% intraday. A 5% adverse overnight gap against a 10% margin
  position is a ~50% equity event that appears nowhere in these bps.
- **Overnight gap risk.** Futures mark to market daily at the settlement price. The
  model charges nothing for being wrong overnight; it only charges the eventual round
  trip. **A cost model that reports 7.88 bp and hides gap risk is worse than no model**,
  which is why this is stated here rather than buried.
- **Forced liquidation.** Broker auto-square-off and exchange surveillance margins can
  close a position at the worst moment. A tail cost with no mean, and not in these bps.
- **Loss-makers' tax.** Futures business income is taxed at slab rates with no
  capital-gains treatment, and audit losses cannot offset salary. Structurally worse
  than delivery for a retail book.
- **Basis risk.** The futures price is not the spot index. A model fitted to spot Nifty
  and traded on futures is trading a different series.
- **Collateral income** (~6% on T-bills) would partly offset the margin cost and is not
  netted anywhere here.

**Also not modelled:**

- **Capital gains tax** — the single largest omission. STCG 20% / LTCG 12.5% is charged
  by `backtest._settle_tax`, not here. `reports/FACTOR_EVIDENCE.md` §4.3 already
  identifies income tax, not STT, as the binding drag (~4%/yr when realising monthly
  gains). **Moving to an ETF does not change this.**
- Tracking error and NAV-vs-price premium/discount for the ETF.
- The ETF expense ratio's own history — applying today's 4 bp/yr to a backtest starting
  in 2008 understates the early-years drag, when NIFTYBEES' TER was far higher.
- Demat AMC (~₹354/yr above ₹4 lakh holdings), pledge/unpledge, MTF interest,
  intraday square-off charges.
- Market impact beyond the linear slippage assumption on large orders.

### The structural objection, stated plainly

Trading a Nifty 50 ETF means the portfolio **is** the Nifty 50. That is not a cheaper
version of the current strategy — it is a different strategy:

- The current edge is a **cross-sectional, 50-name stock-selection** signal
  (`PERSTOCK_EDGE_VS_COST.md`: "timing channel"). One ETF collapses 50 independent
  decisions into **one** time-series bet on the index. The measured edge does not
  transfer; it must be re-measured on Nifty 50 itself.
- Diversification across 50 names — the only channel that amortises fixed per-decision
  cost — disappears entirely.
- Long-only, like delivery. The report notes three catalog signals are *inverted* and
  that shorting them would flip −9.6 bp/day to +9.6. An ETF does not enable that; only
  shorting or index futures do. **This is the strongest argument for futures, and it is
  an argument about the signal, not about cost.**

So: the ETF is the cheapest instrument *and* it destroys the cross-sectional structure
of the research question. Futures keep long/short optionality at 7.88 bp instead of
6.42 bp — a 1.5 bp premium for a materially different (and currently untested)
research programme. **That 1.5 bp is the cheapest experiment available in this project.**

---

## 5. Why the brief's "~20 bp/yr" does not survive

The brief hoped a cheaper instrument would cut ~131 bp/yr to ~20 bp/yr and flip the
−7% timing component to break-even. Taking that at face value, 20 bp/yr at 12 round
trips/yr implies **1.67 bp per round trip all-in**. Here is the full stack that would
have to disappear:

| component | ETF, per round trip |
|---|---|
| stamp duty (buy, 0.015%) | 1.50 bp |
| exchange txn (0.00307% × 2) | 0.61 bp |
| GST 18% on txn + SEBI | 0.11 bp |
| STT (sell, 0.001%) | 0.10 bp |
| DP + GST (flat) | 0.07 bp |
| SEBI (0.0001% × 2) | 0.02 bp |
| **slippage, 2 bp/side** | **4.00 bp** |
| **statutory total** | **2.42 bp** |

**Statutory cost cannot go below ~2.4 bp at this turnover** — and the statutory floor
*rises* with turnover while the slippage floor does not fall. At 12 round trips the
cheapest conceivable instrument is ~6.4 bp, i.e. **77 bp/yr** (81 bp/yr including the
ETF's 4 bp expense ratio), not 20. The brief's 20 bp/yr is only reachable on the ETF by
**cutting turnover to ~3.1 round trips per year** — a quarterly signal, not the monthly
rebalancing the sweep assumes.

That is the real answer, and it is more useful than a cost reduction would have been:
the 20 bp/yr target is not unreachable because the instrument is wrong, it is
unreachable because the *horizon* is wrong. `PERSTOCK_EDGE_VS_COST.md` already found the
binding constraint is "the sweep's 5–60 day holding mandate"; the cost arithmetic puts a
number on it.

The corollary is the genuinely useful one: **the turnover budget is the lever.** At the
ETF's 6.42 bp all-in, a quarterly signal (3.12 round trips/yr) is the break-even point
against a 24 bp/yr edge. Any re-test of this thesis should start by re-measuring the
signal on a quarterly horizon, because that is where the cost arithmetic says the
question becomes answerable.

---

## 6. Sanity check against the project's measured numbers (task 5)

**Upwards — statutory arithmetic.** Reproduces the two published itemisations to within
1%:

```
Rs 140,000 buy + Rs 147,000 sell: this model Rs 337.54 (published Rs 334.33) = 11.76 bp of turnover
Rs 150,000 buy + Rs 160,000 sell: this model Rs 362.90 (published Rs 361.37) = 11.71 bp of turnover
```

Slightly **above** published because this model adds GST on the DP charge (which
`costs.py` omits) and uses DP ₹15.93 rather than Zerodha's ₹15.34. Wrong in the
conservative direction, which is the correct direction.

**Against the sweep — 169 bp/yr at ~2–9× turnover.**

| | bps of notional per round trip | 169 bp/yr implies |
|---|---|---|
| `config.py` as shipped | 21.92 | 7.71 round trips/yr |
| this module, correct | 32.34 | 5.23 round trips/yr |

**Both cannot be right, and the model is.** 169 bp/yr is internally consistent with
`config.py`'s schedule at ~7.7 round trips/yr — comfortably inside the stated 2–9× band
— but `config.py` is charging **21.92 bp of notional** when the true statutory stack is
**22.34 bp of notional before any slippage at all**. Correctly priced, the *same trading
pattern* costs **249 bp/yr, not 169**.

So the answer to "which of the two is wrong" is: **the sweep's fee schedule, not the
cost model.** Root cause is in §3 — a bps-of-turnover constant consumed as
bps-of-notional.

**Direction of the error.** This makes the project's existing conclusion *stronger*:
the cost drag it is trying to outrun is ~1.5× larger than
`PERSTOCK_EDGE_VS_COST.md` states, and `PERSTOCK_EDGE_VS_COST.md`'s own line "12 switches/yr ⇒ 131 bp/yr"
is itself arithmetically inconsistent with its own 21.92 bps/round-trip (12 × 21.92 =
263 bp/yr; 131 bp/yr implies ~6 round trips, not 12).

**A second measurement, for calibration.** Running the corrected delivery schedule over
the same RELIANCE slice: ₹8,638/yr on ₹21 lakh = **41 bp/yr** of cost drag, versus 28
bp/yr under the shipped schedule.

---

## 7. Reproduce it

```bash
.venv/bin/python research/instruments.py     # rates, arithmetic, tables, cross-check, drop-in
.venv/bin/ruff check research/instruments.py # clean
```

Open items, stated as open:

1. **ETF stamp duty** (`UNVERIFIED`) — check one ETF contract note. Worth 1.5 bp/RT.
2. **ETF exchange transaction charge** (`UNVERIFIED`) — check the NSE FY 2026-27 Schedule
   of Charges ETP line. Conclusion not sensitive.
3. **DP charge** varies by broker and DP; ₹15.93 is used everywhere as the conservative
   pre-GST figure. Zerodha publishes ₹15.34 all-in.
4. **Slippage and roll cost are assumptions**, not rates. They are the Gate-4 stress
   variables and should be swept, not trusted.
5. `research/optimize/config.py:41` still holds the bps-of-turnover constant. Correcting
   it will **worsen every sweep result**, which is the expected and desired direction
   under `GOAL.md` §6.4 — but it is a real change to a shared file and is not mine to make.