"""trex.store
============
PostgreSQL persistence layer for the Trex Engine.

Public API
----------
- :class:`TrexStore` — the thread-safe, connection-pooled synchronous store.
- :class:`AsyncTrexStore` — the asyncio-based counterpart.
- :class:`DbConfig` — discrete connection configuration.

Example
-------
::

    from trex.store import TrexStore

    store = TrexStore("postgresql://postgres:pw@localhost:5432/trex")
    store.save_indicators("binance", "BTCUSDT", "1m", [
        {"time": 1720000000, "open": 42000, "high": 42100,
         "low": 41950, "close": 42080, "volume": 12.5,
         "RSI_14": 65.4,
         "MACD_12_26_9": {"macd": 125.3, "signal": 118.7, "histogram": 6.6}},
    ])
    series = store.get_indicator("binance", "BTCUSDT", "1m", "RSI_14")
    store.close()
"""
from __future__ import annotations

from trex.store.db_store import AsyncTrexStore, DbConfig, TrexStore
from trex.store.exceptions import (
    IndicatorError,
    MigrationError,
    SchemaError,
    StoreConnectionError,
    TableNotFoundError,
    TrexStoreError,
    ValidationError,
)

__all__ = [
    "TrexStore",
    "AsyncTrexStore",
    "DbConfig",
    "TrexStoreError",
    "StoreConnectionError",
    "SchemaError",
    "TableNotFoundError",
    "IndicatorError",
    "ValidationError",
    "MigrationError",
]
