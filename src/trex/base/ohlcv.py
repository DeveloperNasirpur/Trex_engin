from __future__ import annotations
"""trex.base.ohlcv — OHLCV data model و factory utilities."""

from dataclasses import dataclass, field
from datetime import datetime
from itertools import zip_longest
from typing import Any


@dataclass(slots=True)
class OHLCV:
    """Single candlestick bar.

    Attributes:
        side: 0 = bearish (open > close), 1 = bullish (close >= open).
        timeframe: Duration in minutes.
        str_time: Human-readable timeframe label (e.g. ``"1m"``, ``"4H"``).
    """

    open:      float | None = None
    high:      float | None = None
    low:       float | None = None
    close:     float | None = None
    volume:    float | None = None
    time:      datetime     = field(default_factory=datetime.utcnow)
    side:      int          = 0
    timeframe: int          = 1
    str_time:  str          = "1m"
    symbol:    str          = "BTCUSDT"

    @property
    def key(self) -> tuple[str, str]:
        """Unique ``(symbol, timeframe)`` identity."""
        return self.symbol, self.str_time

    def to_dict(self) -> dict[str, Any]:
        return {
            "open": self.open, "high": self.high, "low": self.low,
            "close": self.close, "volume": self.volume,
            "time": self.time.isoformat() if self.time else None,
            "side": self.side, "timeframe": self.timeframe,
            "str_time": self.str_time, "symbol": self.symbol,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "OHLCV":
        return OHLCV(
            open=data.get("open"), high=data.get("high"),
            low=data.get("low"),   close=data.get("close"),
            volume=data.get("volume"),
            time=(datetime.fromisoformat(data["time"])
                  if data.get("time") else datetime.utcnow()),
            side=data.get("side", 0),
            timeframe=data.get("timeframe", 1),
            str_time=data.get("str_time", "1m"),
            symbol=data.get("symbol", "BTCUSDT"),
        )

    @staticmethod
    def from_bar(bar: Any, *, symbol: str, str_time: str = "1m", timeframe: int = 1) -> "OHLCV":
        """Build an OHLCV from a ``trex.domain.types.Bar`` (unix-seconds timestamp)."""
        o, c = float(bar.open), float(bar.close)
        return OHLCV(
            open=o, high=float(bar.high), low=float(bar.low), close=c,
            volume=float(bar.volume),
            time=datetime.utcfromtimestamp(bar.time),
            side=0 if o > c else 1,
            timeframe=timeframe,
            str_time=str_time,
            symbol=symbol,
        )


# ── Factory ───────────────────────────────────────────────────────────────────

class OHLCVFactory:
    """Build lists of :class:`OHLCV` from various raw-data layouts."""

    @staticmethod
    def from_matrix(values: list[list[Any]]) -> list[OHLCV]:
        """Row layout: ``[[O,H,L,C], …]`` with optional V and T columns."""
        result: list[OHLCV] = []
        for x in values:
            n = len(x)
            o, c = float(x[0]), float(x[3])
            result.append(OHLCV(
                open=o, high=float(x[1]), low=float(x[2]), close=c,
                volume=float(x[4]) if n >= 5 else None,
                time=x[5]          if n >= 6 else datetime.utcnow(),
                side=0 if o > c else 1,
            ))
        return result

    @staticmethod
    def from_matrix2(values: list[list[Any]]) -> list[OHLCV]:
        """Column layout: ``[[opens], [highs], [lows], [closes], …]``."""
        cols = list(values) + [[] for _ in range(6 - len(values))]
        return OHLCVFactory.from_matrix([list(r) for r in zip_longest(*cols[:6])])

    @staticmethod
    def from_dict(values: dict[str, list[Any]]) -> list[OHLCV]:
        """Dict layout with optional keys ``open``, ``high``, ``low``, ``close``, ``volume``, ``time``."""
        return OHLCVFactory.from_matrix2([
            values.get("open",   []), values.get("high",   []),
            values.get("low",    []), values.get("close",  []),
            values.get("volume", []), values.get("time",   []),
        ])


# ── Value extractors ──────────────────────────────────────────────────────────

class ValueExtractor:
    """Static OHLCV field extractors برای pipeline ``extractor`` parameter."""

    @staticmethod
    def extract_open(v: OHLCV)   -> float: return float(v.open)   if v.open   is not None else 0.0
    @staticmethod
    def extract_high(v: OHLCV)   -> float: return float(v.high)   if v.high   is not None else 0.0
    @staticmethod
    def extract_low(v: OHLCV)    -> float: return float(v.low)    if v.low    is not None else 0.0
    @staticmethod
    def extract_close(v: OHLCV)  -> float: return float(v.close)  if v.close  is not None else 0.0
    @staticmethod
    def extract_volume(v: OHLCV) -> float: return float(v.volume) if v.volume is not None else 0.0

    @staticmethod
    def extract_hl2(v: OHLCV) -> float:
        h = float(v.high)  if v.high is not None else 0.0
        l = float(v.low)   if v.low  is not None else 0.0
        return (h + l) / 2.0

    @staticmethod
    def extract_hlc3(v: OHLCV) -> float:
        return ((v.high or 0.0) + (v.low or 0.0) + (v.close or 0.0)) / 3.0

    @staticmethod
    def extract_hlcc4(v: OHLCV) -> float:
        return ((v.high or 0.0) + (v.low or 0.0) + (v.close or 0.0) * 2.0) / 4.0


__all__ = ["OHLCV", "OHLCVFactory", "ValueExtractor"]
