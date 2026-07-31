from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Deque, Dict, List, Optional

import numpy as np

from cryptobot.core.events import Event, OrderEvent, OrderSide, OrderType
from cryptobot.ml.features import build_features, future_returns
from cryptobot.ml.models.direction import DirectionClassifier, DirectionConfig


@dataclass
class MLStrategyConfig:
    """Configuration for ML-driven trading strategy."""
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT"])
    lookback: int = 100
    horizon: int = 5
    threshold: float = 0.55
    train_min_samples: int = 50
    retrain_every: int = 20
    quantity: Decimal = Decimal("1")


class MLStrategy:
    """ML-driven trading strategy using direction classifier.

    Uses ML features and a logistic regression direction classifier to predict
    short-term price direction. Enters long when probability > threshold,
    short when probability < (1 - threshold). Retrains periodically using
    walk-forward expanding window.
    """

    name = "ml_strategy"

    def __init__(self, config: Optional[MLStrategyConfig] = None):
        self.config = config or MLStrategyConfig()
        self._prices: Dict[str, Deque[float]] = {}
        self._classifier: Optional[DirectionClassifier] = None
        self._bars_seen: int = 0
        self._last_signal: Dict[str, int] = {}

    def feed(self, symbol: str, price: float) -> Optional[OrderEvent]:
        """Feed a price tick and return an OrderEvent if a signal fires.

        Args:
            symbol: Trading symbol.
            price: Current price.

        Returns:
            OrderEvent if ML signal triggers a trade, None otherwise.
        """
        buf = self._prices.setdefault(
            symbol,
            deque(maxlen=max(self.config.lookback, self.config.train_min_samples + self.config.horizon)),
        )
        buf.append(price)
        self._bars_seen += 1

        # Need enough history to compute features and train
        if len(buf) < self.config.train_min_samples + self.config.horizon:
            return None

        # Periodically retrain the classifier
        if (
            self._classifier is None
            or self._bars_seen % self.config.retrain_every == 0
        ):
            self._retrain(buf)

        if self._classifier is None or not self._classifier._fitted:
            return None

        # Build features from current buffer
        try:
            arr = np.fromiter(buf, dtype=float)
            features = build_features(arr)
            if features.shape[0] == 0:
                return None
            latest_features = features[-1:]
        except Exception:
            return None

        try:
            proba = self._classifier.predict_proba(latest_features)[0]
        except Exception:
            return None

        signal = 0
        if proba > self.config.threshold:
            signal = 1
        elif proba < (1.0 - self.config.threshold):
            signal = -1

        prev_signal = self._last_signal.get(symbol, 0)
        self._last_signal[symbol] = signal

        # Only emit order on signal change (avoid whipsaw)
        if signal == 0 or signal == prev_signal:
            return None

        side = OrderSide.BUY if signal > 0 else OrderSide.SELL
        order_type = OrderType.MARKET

        return OrderEvent(
            type=order_type,
            symbol=symbol,
            quantity=self.config.quantity,
            side=side,
        )

    def _retrain(self, buf: Deque[float]) -> None:
        """Retrain the direction classifier on recent data."""
        try:
            arr = np.fromiter(buf, dtype=float)
            features = build_features(arr)
            labels_arr = future_returns(arr, horizon=self.config.horizon)
            if features.shape[0] == 0 or labels_arr.size == 0:
                return
            # Align features and labels
            n_common = min(features.shape[0], labels_arr.size)
            X = features[-n_common:]
            y = (labels_arr[-n_common:] > 0).astype(int)

            clf_config = DirectionConfig(
                threshold=self.config.threshold,
                horizon=self.config.horizon,
            )
            clf = DirectionClassifier(clf_config)
            clf.fit(X, y)
            self._classifier = clf
        except Exception:
            self._classifier = None

    def on_order_update(self, event: Event) -> List[OrderEvent]:
        """Handle order update events (default: no action)."""
        return []

    def get_name(self) -> str:
        return self.name


__all__ = ["MLStrategy", "MLStrategyConfig"]
