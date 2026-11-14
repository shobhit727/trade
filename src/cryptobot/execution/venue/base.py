from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from cryptobot.core.events import OrderEvent


class Venue(ABC):
    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        """Submit an order to the venue and return its updated execution event."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order by ID and report whether cancellation succeeded."""
        pass

    @abstractmethod
    async def get_price(self, symbol: str) -> Decimal:
        """Return the venue's current price for a symbol as a Decimal."""
        pass


__all__ = ["Venue"]
