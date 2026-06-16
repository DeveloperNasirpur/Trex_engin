from __future__ import annotations
"""trex.source.candle_source — Abstract base for candle data sources."""

from abc import ABC, abstractmethod


class CandleSource(ABC):
    """Abstract base for OHLCV data providers."""

    @abstractmethod
    def run(self, table_symbol: str = "BTC_USDT") -> None: ...


__all__ = ["CandleSource"]
