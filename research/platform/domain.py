"""Shared domain types for the multi-market research platform."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType


class Market(StrEnum):
    """Financial environments that must never share capital or portfolios."""

    NSE = "nse"
    CRYPTO = "crypto"


class ResearchTrack(StrEnum):
    """Independent asset-level and portfolio-level research tracks."""

    NSE_INDIVIDUAL = "nse_individual"
    NSE_PORTFOLIO = "nse_portfolio"
    CRYPTO_INDIVIDUAL = "crypto_individual"
    CRYPTO_PORTFOLIO = "crypto_portfolio"


TRACK_MARKET: MappingProxyType[ResearchTrack, Market] = MappingProxyType(
    {
        ResearchTrack.NSE_INDIVIDUAL: Market.NSE,
        ResearchTrack.NSE_PORTFOLIO: Market.NSE,
        ResearchTrack.CRYPTO_INDIVIDUAL: Market.CRYPTO,
        ResearchTrack.CRYPTO_PORTFOLIO: Market.CRYPTO,
    }
)


class DataResolution(StrEnum):
    """Canonical resolution identifiers used by data manifests."""

    TICK = "tick"
    ORDER_BOOK_EVENT = "order_book_event"
    ORDER_BOOK_SNAPSHOT = "order_book_snapshot"
    ONE_SECOND = "1s"
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"
    ONE_MONTH = "1mo"


class AlgorithmFamily(StrEnum):
    """Algorithm families available to the future experiment orchestrator."""

    EXISTING_STRATEGY = "existing_strategy"
    RANDOM_SEARCH = "random_search"
    GRID_SEARCH = "grid_search"
    BAYESIAN = "bayesian"
    DIFFERENTIAL_EVOLUTION = "differential_evolution"
    GENETIC_PROGRAMMING = "genetic_programming"
    NEUROEVOLUTION = "neuroevolution"
    STRATEGY_COMPOSITION = "strategy_composition"
    PARETO_SEARCH = "pareto_search"
    HYBRID = "hybrid"


@dataclass(frozen=True, slots=True)
class MarketSpec:
    """Market-level research budget; this is simulated capital only."""

    market: Market
    base_currency: str
    initial_simulated_capital: Decimal
    account_scope: str

    def __post_init__(self) -> None:
        # Reject invalid budgets or ambiguous currency/account scope at construction.
        if self.initial_simulated_capital <= Decimal("0"):
            raise ValueError("initial simulated capital must be positive")
        if self.base_currency != "INR":
            raise ValueError("the initial research budgets are denominated in INR")
        if not self.account_scope.strip():
            raise ValueError("account_scope must be non-empty")


MARKET_SPECS: MappingProxyType[Market, MarketSpec] = MappingProxyType(
    {
        Market.NSE: MarketSpec(
            market=Market.NSE,
            base_currency="INR",
            initial_simulated_capital=Decimal("2100000.00"),
            account_scope="nse-research-only",
        ),
        Market.CRYPTO: MarketSpec(
            market=Market.CRYPTO,
            base_currency="INR",
            initial_simulated_capital=Decimal("2100000.00"),
            account_scope="crypto-research-only",
        ),
    }
)
