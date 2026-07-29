from __future__ import annotations

from decimal import Decimal


def max_abs_correlation(correlations: dict[tuple[str, str], Decimal]) -> Decimal:
    if not correlations:
        return Decimal("0")
    return max(abs(value) for value in correlations.values())


__all__ = ["max_abs_correlation"]
