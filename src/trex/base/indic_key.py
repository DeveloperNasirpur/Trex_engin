from __future__ import annotations
"""trex.base.indic_key — ListenerKey dataclass."""

from dataclasses import dataclass


@dataclass(slots=True)
class ListenerKey:
    """Identifies a ``(symbol, listener, indicator)`` triple for de-attachment."""

    listener:  str
    indicator: str
    symbol:    str

    def __init__(self, symbol: str, key: str, indicator: str) -> None:
        self.listener  = key
        self.indicator = indicator
        self.symbol    = symbol


__all__ = ["ListenerKey"]
