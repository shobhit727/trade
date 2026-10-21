"""Hypothesis family bank: 35 waves x 40 distinct research assignments.

Each (wave, agent) pair gets a DIFFERENT thing to investigate. That matters
enormously at this scale: if 40 agents all searched "momentum variations",
they would produce 40 highly-correlated cells and the FDR layer would be
measuring one hypothesis 40 times.

The families are drawn from six regimes, rotating so that any one wave contains
a mix:

  A. price-derived structure   (shape, gaps, volume, seasonality, entropy)
  B. cross-sectional structure  (rank dynamics, crowding, dispersion, breadth)
  C. risk and drawdown         (vol targeting, correlation, tail shape, regime)
  D. portfolio construction    (weighting, buffering, position sizing, turnover)
  E. factor families           (momentum/trend/reversal variants, quality/value)
  F. instrument and execution  (ETF, futures, short side, rebalance timing)

Every entry carries a directive, not just a topic. The agent is told what to
BUILD and what to TEST, because a topic without a falsifiable mechanism produces
noise.
"""

from __future__ import annotations

#: (regime, directive) pairs. The agent must implement factors that satisfy the
#: directive and measure them against the null and the benchmark.
FAMILIES: list[tuple[str, str]] = [
    # --- A. price-derived structure ---------------------------------------
    ("A", "ACCELERATION: second differences of momentum. Does the CHANGE in a "
          "name's trend predict better than the level of it?"),
    ("A", "VOLUME-PRICE DIVERGENCE: price up with volume down, and the "
          "converse. A classic accumulation/distribution read."),
    ("A", "GAP PERSISTENCE: do overnight gaps mean-revert, and does a "
          "multi-day run of same-sign gaps predict the opposite?"),
    ("A", "RANGE COMPRESSION: the ratio of short-range to long-range "
          "volatility, as a breakout-pending indicator."),
    ("A", "PRICE POSITION WITHIN BAR: where the close sits in the day's range, "
          "as a daily-scale buying-pressure proxy."),
    ("A", "TRADING-DAY SEASONALITY: day-of-week and month-of-year effects in "
          "Indian equities. Documented in the literature and rarely tested."),
    ("A", "ENTROPY / COMPLEXITY: approximate entropy or Hurst exponent of the "
          "return series, distinguishing trending from chaotic names."),
    ("A", "SKEW AND TAIL DEPENDENCE: co-movement of tail events across names, "
          "as a crash-warning signal."),
    ("A", "EARNINGS-ANNOUNCEMENT PROXY: the classic post-earnings-announcement "
          "drift, approximated from price/volume patterns."),
    ("A", "CANDLE-SHAPE FACTORS: body, wick, and gap decomposition of the "
          "daily bar, used as a standalone cross-sectional score."),
    ("A", "INTRADAY-TO-OVERNIGHT RATIO: the share of a name's total move that "
          "happened overnight, as a signal of who is trading it."),
    ("A", "PRICE CLUSTERING: how far a name's current price sits from its own "
          "recent price distribution (a value-like anchor from price alone)."),
    ("A", "TREND CONSISTENCY: the fraction of up-days in the last 6 months, "
          "which measures smoothness rather than magnitude."),
    ("A", "MAXIMUM DRAWDOWN RECOVERY: time since the 52-week low, as a recovery "
          "momentum proxy."),
    ("A", "REALISED SKEW OF INTRADAY RANGES: using high/low, measure the "
          "asymmetry of daily ranges."),
    ("A", "CORRELATION TO THE RECENT PAST: a name's correlation to its own "
          "lagged returns, distinguishing stable from unstable regimes."),
    ("A", "PRICE-MEMORY EFFICIENCY: a simple Amihudi-style illiquidity measure "
          "on returns, as a tradability filter rather than an alpha source."),
    ("A", "OPEN-TO-CLOSE DRIFT: the average intraday return, as a "
          "quality-of-price-discovery proxy."),
    ("A", "RELATIVE STRENGTH VS OWN SECTOR: proxy a sector by clustering on "
          "correlation, then measure strength within the cluster."),
    ("A", "DOWNSIDE-CAPTURE BEHAVIOUR: how much of the market's decline a "
          "name captures, as a defensive characteristic."),
    # --- B. cross-sectional structure -------------------------------------
    ("B", "RANK PERSISTENCE: how long a name has held its cross-sectional "
          "rank. Does rank stability predict anything?"),
    ("B", "RANK MOMENTUM: the change in a name's cross-sectional rank over 1, "
          "3, 6 months."),
    ("B", "CROWDING: how many names are simultaneously at their 52-week high. "
          "Market-level, applied as an exposure overlay."),
    ("B", "DISPERSION: cross-sectional return dispersion, and whether high "
          "dispersion predicts mean reversion across the book."),
    ("B", "BREADTH OF THE UNIVERSE: what fraction of names are above their own "
          "moving averages, as a market-timing overlay."),
    ("B", "CROSS-SECTIONAL MAXIMUM: the identity and score of the single best "
          "name per date, as a concentration study."),
    ("B", "BOTTOM-QUARTILE CONSTRUCTION: build the book from the WORST names "
          "and check whether short-side is where the edge lives."),
    ("B", "MIDDLE-EXCLUSION: hold the top and bottom quartiles but exclude the "
          "middle, testing whether the tails carry the signal."),
    ("B", "RANK-BASED MOMENTUM OVERLAY: apply a rank-change overlay to an "
          "existing factor rather than to price directly."),
    ("B", "BREADTH-DIFFERENTIAL: the spread between the advance and decline "
          "counts in the universe, as a timing signal."),
    ("B", "LEADER-LAG STRUCTURE: do the top-ranked names lead the rest of the "
          "universe? A lead-lag cross-sectional factor."),
    ("B", "CORRELATION CONCENTRATION: measure how concentrated the universe's "
          "correlation is, as a risk-budget input."),
    ("B", "UNIVERSE-WIDE VOLATILITY: the market's own volatility, and whether "
          "it conditions the cross-sectional signal's efficacy."),
    ("B", "SECTOR-LIKE CLUSTERS: build correlation clusters and test whether "
          "within-cluster relative returns predict."),
    ("B", "TAIL CONCENTRATION: what fraction of total market move comes from "
          "the top 3 names, as a concentration risk measure."),
    ("B", "CROSS-SECTIONAL SKEW: the dispersion of cross-sectional returns, and "
          "whether extreme names mean-revert."),
    ("B", "INFORMATIONAL ITERATION: repeatedly apply a factor to its own output, "
          "testing whether compounding the signal amplifies it."),
    ("B", "CROSS-SECTIONAL ACCELERATION: the acceleration of a name's rank "
          "relative to the universe's mean rank acceleration."),
    ("B", "DECILE SPREAD BEHAVIOUR: build explicit decile portfolios and "
          "measure the monotonicity of the return spread."),
    ("B", "RANK STABILITY AS A RISK FILTER: use rank churn to gate exposure "
          "rather than to pick names."),
    # --- C. risk and drawdown ---------------------------------------------
    ("C", "VOLATILITY TARGETING: scale the book to a constant ex-ante "
          "volatility, and test whether the risk-adjusted return improves."),
    ("C", "CORRELATION-AWARE SIZING: size positions inversely to their "
          "correlation with the rest of the book."),
    ("C", "DRAWDOWN-AWARE SIZING: reduce exposure as the book's own drawdown "
          "approaches the -15% constitution limit."),
    ("C", "TAIL-RISK SIZING: size inversely to expected shortfall rather than "
          "to standard deviation."),
    ("C", "REGIME-CONDITIONED SIGNALS: test whether the same factor works "
          "better in trending versus mean-reverting market regimes."),
    ("C", "VOL-OF-VOL AS A RISK SWITCH: use instability in volatility to cut "
          "exposure before a drawdown."),
    ("C", "MAXIMUM-DRAWDOWN AVOIDANCE: screen out names with pathological "
          "drawdown history."),
    ("C", "GAP-RISK FILTER: exclude names with a history of large overnight "
          "gaps, which cause stop-out risk."),
    ("C", "CONCENTRATION-AWARE CONSTRUCTION: cap the contribution of any one "
          "name or cluster to the book's return."),
    ("C", "STRESS PERIOD BEHAVIOUR: measure each factor's behaviour in the "
          "2008 and 2020 crashes specifically."),
    ("C", "SLOW-FAST VOL RATIO AS A REGIME READ: the classic market-timing "
          "filter, measured properly."),
    ("C", "EARNINGS-RISK PROXY: use earnings-announcement gaps as a proxy for "
          "event risk and size around them."),
    ("C", "LIQUIDITY-ADJUSTED SIZING: size positions by the square root of "
          "liquidity, the standard capacity-aware construction."),
    ("C", "DOWNSIDE BETA: measure the beta to market DOWNSIDE moves only, and "
          "size against that."),
    ("C", "MAXIMUM-EXPOSURE SCHEDULING: instead of a regime filter, scale "
          "exposure continuously with a risk signal."),
    ("C", "RISK PARITY ACROSS FACTORS: split the book across factors in "
          "inverse-volatility proportion instead of one composite."),
    ("C", "CRASH-DETECTION OVERLAY: use breadth collapse as a de-risking "
          "signal with explicit hysteresis to avoid whipsaw."),
    ("C", "AUTOCORRELATION-AWARE SIZING: size inversely to a name's return "
          "autocorrelation."),
    ("C", "HURST-ADAPTIVE CONSTRUCTION: use the Hurst exponent to decide "
          "whether to trend-follow or mean-revert a name."),
    ("C", "TAIL-DEPENDENCE FILTER: remove names whose downside co-moves with "
          "the market's tail."),
    # --- D. portfolio construction ----------------------------------------
    ("D", "VOLATILITY-WEIGHTED EQUAL WEIGHT: weight positions by inverse "
          "volatility inside an equal-weight top-N book."),
    ("D", "RISK PARITY WEIGHTING: weight positions so each contributes equal "
          "risk, not equal capital."),
    ("D", "MOMENTUM-WEIGHTED POSITIONS: size positions by the strength of the "
          "signal, not equally."),
    ("D", "MULTI-STEP BUFFER: a two-stage hysteresis buffer, where a name "
          "must leave the top band twice before it is sold."),
    ("D", "TIME-BUFFERED REBALANCE: sell only if a name has been out of the "
          "band for a minimum number of days."),
    ("D", "PARTIAL-EXIT SIZING: trim a falling name rather than selling it "
          "outright, and test whether that preserves the rebound."),
    ("D", "REBALANCE STAGGERING: rebalance different names on different days "
          "to spread execution cost and reduce turnover clustering."),
    ("D", "CASH-BUFFER OPTIMISATION: sweep the cash buffer and see whether "
          "the -15% limit is reachable with less drag."),
    ("D", "POSITION-COUNT OPTIMISATION: sweep the number of held names finely, "
          "including very concentrated books."),
    ("D", "WEIGHTED-BUFFER ENTRY AND EXIT: use a different buffer for entry "
          "than for exit, so a book can fill slowly but exit fast."),
    ("D", "NEW-NAME FRICTION: require a new name to beat the incumbent by a "
          "margin before replacing it, reducing turnover."),
    ("D", "INCREMENTAL TURNOVER BUDGET: cap turnover per rebalance and let "
          "the book drift toward the target over several periods."),
    ("D", "DUAL-TIMEFRAME SELECTION: select on a slow signal but exit on a "
          "fast one, or the reverse."),
    ("D", "SIZE-SEGREGATED BOOKS: build separate books for large and small "
          "caps and measure them independently."),
    ("D", "CORRELATION-ADJUSTED POSITION COUNT: hold fewer names when the "
          "universe is highly correlated."),
    ("D", "SECTOR NEUTRALITY: neutralise cluster exposure so the book is a "
          "pure stock-selection bet."),
    ("D", "MULTI-PERIOD REBALANCE: rebalance a different slice of the book "
          "each period, so turnover spreads across the year."),
    ("D", "HOLD-THROUGH RULES: keep a name until a STOP rather than a signal, "
          "testing whether turnover costs more than the exit signal gains."),
    ("D", "ENTRIES-BEFORE-EXITS: order the rebalance so buys are funded by "
          "sells, and measure the cash drag."),
    ("D", "BUFFER SIZE AS A SEPARATE SIGNAL: treat buffer width itself as "
          "something to select rather than fix."),
    ("D", "CROSS-SECTIONAL EQUAL-RISK CONSTRUCTION: build the book so that "
          "each name's contribution to total variance is equal."),
    # --- E. factor families ------------------------------------------------
    ("E", "MOMENTUM VARIANTS: test the whole momentum family properly -- 1-12, "
          "3-12, 6-12, 12-1, 24-1, and their risk-adjusted forms."),
    ("E", "TREND VARIANTS: test moving-average distance, MA slope, MA "
          "crossovers, and channel position at many windows."),
    ("E", "REVERSAL VARIANTS: test short-horizon reversal from 1 day to 3 "
          "months, and where the sign flips."),
    ("E", "VOLATILITY VARIANTS: test every volatility measure as an alpha "
          "source, not just a risk control."),
    ("E", "QUALITY-LIKE CONSTRUCTIONS: build price-only quality scores and "
          "test whether quality survives without fundamentals."),
    ("E", "VALUE-LIKE CONSTRUCTIONS: build price-only value scores and test "
          "whether long-horizon reversal is a value premium."),
    ("E", "LIQUIDITY AS ALPHA: test whether illiquidity premium exists in "
          "Indian largecaps."),
    ("E", "SIZE-LIKE CONSTRUCTIONS: price and turnover are the only size "
          "proxies available; test them as alpha."),
    ("E", "BREADTH FACTORS: build cross-sectional breadth scores and test "
          "them standalone."),
    ("E", "MOMENTUM-CRASH INTERACTION: momentum that crashes hardest in "
          "crashes -- and how to avoid it."),
    ("E", "SKEW AS A FACTOR: negative skew as a standalone predictor of "
          "future returns."),
    ("E", "AUTOCORRELATION AS A FACTOR: test the documented negative "
          "autocorrelation premium."),
    ("E", "VARIANCE-RATIO AS A FACTOR: trend-persistence as a standalone "
          "cross-sectional score."),
    ("E", "MULTI-HORIZON BLENDS: blend momentum and reversal at many "
          "weightings and look for an interior optimum."),
    ("E", "FACTOR ORTHOGONALITY: measure the correlation structure of all "
          "factors and report which are genuinely different."),
    ("E", "NONLINEAR MOMENTUM: momentum conditioned on volatility or on the "
          "name's own range."),
    ("E", "CUMULATIVE-SUM CONSTRUCTIONS: build factors from cumulative sums of "
          "ranked signals over time."),
    ("E", "REVERSAL AFTER EXTREMES: the 52-week-low and 52-week-high "
          "constructions, and what happens after a limit-down."),
    ("E", "INTERMEDIATE MOMENTUM: the 12-month-excluding-3-month "
          "construction, and variants of the skip period."),
    ("E", "GROWTH-IN-PRICE: total return over multiple horizons, checking "
          "whether the signal is just a shorter momentum."),
    ("E", "FACTOR-DECAY CURVES: measure how quickly each factor's edge "
          "decays, which tells you the right holding period."),
    # --- F. instrument and execution ---------------------------------------
    ("F", "ETF COST STACK: re-run the best factors under the ETF cost stack "
          "(6.42 bp) instead of delivery (32.32 bp)."),
    ("F", "FUTURES COST STACK: measure under the futures stack, and state "
          "what margin and gap risk the number omits."),
    ("F", "SHORT SIDE: implement and measure the short side properly, "
          "including borrow and margin, and be honest about what is missing."),
    ("F", "REBALANCE TIMING: do the results depend on WHICH day in the period "
          "you rebalance? Test several anchors."),
    ("F", "SLIPPAGE SENSITIVITY: how does every factor's edge change as "
          "slippage goes from 0 to 20 bp per side?"),
    ("F", "COST-BREAKEVEN ANALYSIS: for each factor, compute the round trips "
          "per year at which its edge exactly equals its cost."),
    ("F", "EXCHANGE-OF-EXECUTION: does trading at the open rather than the "
          "close change anything?"),
    ("F", "INTRADAY-EXIT TIMING: exit on the next day's open to avoid the "
          "close-auction stamp, and measure the slippage of that choice."),
    ("F", "T+1 AND SETTLEMENT: model the cash drag of settlement delay on "
          "rebalance proceeds."),
    ("F", "PARTIAL-FILL REALISM: model that you cannot buy the full position "
          "at one price and measure the impact."),
    ("F", "CASH-AND-CARRY: the risk-free leg of a long book -- measure what "
          "parking cash in T-bills actually adds."),
    ("F", "FUNDING-COST SENSITIVITY: how much margin cost would a futures "
          "implementation need before the edge disappears?"),
    ("F", "MULTI-VENUE ARBITRAGE: does splitting orders across time reduce "
          "cost enough to matter?"),
    ("F", "SHORT-TERM MOMENTUM COSTS: test whether the 1-month momentum is "
          "purely a cost artefact by pricing it at every cost level."),
    ("F", "DELAYED-SIGNAL ROBUSTNESS: shift every signal by 1, 2, 5 days and "
          "see which factors survive realistic execution lag."),
    ("F", "PRICE-IMPACT ESTIMATION: estimate impact from the relationship "
          "between order size and the universe's own volatility."),
    ("F", "MULTI-ASSET DIVERSIFICATION: test whether adding a second, "
          "uncorrelated universe to the book improves the Sharpe."),
    ("F", "CASH-DRAG MINIMISATION: the book sits in cash between rebalances; "
          "measure what parking it in the highest-yielding liquid instrument "
          "would add."),
    ("F", "SETTLEMENT-DATE EFFECTS: test whether buying on settlement-day "
          "close versus T+1 changes the realised return."),
    ("F", "COST-OPTIMAL BUFFER: for each factor, compute the buffer that "
          "maximises edge-minus-cost, rather than fixing buffer at 20."),
    ("F", "MULTI-FACTOR BOOK SIZING: size each factor sleeve by its own "
          "measured edge, then re-measure the combined book."),
]

#: The bank is larger than one wave so that consecutive waves explore different
#: pairings. 40 agents in a wave must get 40 DISTINCT families -- if they
#: repeated one, the FDR layer would be measuring a single hypothesis 40 times.
BANK_SIZE = len(FAMILIES)


def assignment(wave: int, agent: int) -> tuple[str, str]:
    """The (regime, directive) an agent is given.

    The offset advances by 40 per wave, so wave N covers bank entries
    [40(N-1) .. 40N-1] mod BANK_SIZE. Within a wave, agent i gets entry
    40(N-1)+i, which is distinct for every i -- 40 agents, 40 distinct topics.
    """
    idx = (40 * (wave - 1) + agent) % BANK_SIZE
    return FAMILIES[idx]


def describe(wave: int, agent: int) -> str:
    regime, directive = assignment(wave, agent)
    return (f"wave {wave}, agent {agent} | regime {regime} | {directive}")
