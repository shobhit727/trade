from __future__ import annotations

import logging

from cryptobot.execution.venue.base import Venue
from cryptobot.execution.venue.ccxt_venue import CcxtVenue

logger = logging.getLogger(__name__)


class BinanceVenue(CcxtVenue):
    """Live / testnet Binance adapter (thin specialization of :class:`CcxtVenue`).

    Kept as a named class for backwards compatibility; all behaviour comes
    from the generic ccxt adapter with ``exchange_id="binance"``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        market_type: str = "future",
        sandbox: bool | None = None,
        rate_limit_ms: int = 200,
        max_retries: int = 3,
    ):
        super().__init__(
            exchange_id="binance",
            api_key=api_key,
            api_secret=api_secret,
            market_type=market_type,
            sandbox=sandbox,
            rate_limit_ms=rate_limit_ms,
            max_retries=max_retries,
        )


# Re-export the protocol type for typing convenience.
_venue_base: type[Venue] = Venue

__all__ = ["BinanceVenue"]
