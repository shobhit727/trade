from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from cryptobot.core.events import OrderEvent


class Venue(ABC):
    @abstractmethod
    async def submit_order(self, order: OrderEvent) -> OrderEvent:
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        pass

    @abstractmethod
    async def get_price(self, symbol: str) -> Decimal:
        pass


__all__ = ["Venue"]
