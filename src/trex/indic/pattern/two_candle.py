from __future__ import annotations
from .base import CandlePattern
from trex.base.ohlcv import OHLCV


def _body(b: OHLCV) -> float:
    return abs(b.close - b.open)

def _is_bull(b: OHLCV) -> bool:
    return b.close >= b.open

def _top(b: OHLCV) -> float:
    return max(b.close, b.open)

def _bot(b: OHLCV) -> float:
    return min(b.close, b.open)


class BullishEngulfing(CandlePattern):
    """Bullish Engulfing: bearish then bullish candle that fully engulfs it."""
    _ind_name = "BULLISH_ENGULFING"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        if not _is_bull(p) and _is_bull(c):
            if c.open <= p.close and c.close >= p.open:
                return 1
        return 0


class BearishEngulfing(CandlePattern):
    """Bearish Engulfing: bullish then bearish candle that fully engulfs it."""
    _ind_name = "BEARISH_ENGULFING"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        if _is_bull(p) and not _is_bull(c):
            if c.open >= p.close and c.close <= p.open:
                return -1
        return 0


class BullishHarami(CandlePattern):
    """Bullish Harami: bearish then small bullish candle inside prior body."""
    _ind_name = "BULLISH_HARAMI"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        if not _is_bull(p) and _is_bull(c):
            if c.open > p.close and c.close < p.open:
                return 1
        return 0


class BearishHarami(CandlePattern):
    """Bearish Harami: bullish then small bearish candle inside prior body."""
    _ind_name = "BEARISH_HARAMI"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        if _is_bull(p) and not _is_bull(c):
            if c.open < p.close and c.close > p.open:
                return -1
        return 0


class Piercing(CandlePattern):
    """Piercing Line: bearish candle then bullish that closes > midpoint of prior."""
    _ind_name = "PIERCING"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        mid_p = (p.open + p.close) / 2
        if not _is_bull(p) and _is_bull(c):
            if c.open < p.close and c.close > mid_p and c.close < p.open:
                return 1
        return 0


class DarkCloudCover(CandlePattern):
    """Dark Cloud Cover: bullish then bearish that closes < midpoint of prior."""
    _ind_name = "DARK_CLOUD_COVER"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        mid_p = (p.open + p.close) / 2
        if _is_bull(p) and not _is_bull(c):
            if c.open > p.close and c.close < mid_p and c.close > p.open:
                return -1
        return 0


class Tweezer(CandlePattern):
    """Tweezer Top/Bottom: two candles with matching high (top) or low (bottom)."""
    _ind_name = "TWEEZER"

    def __init__(self, tolerance: float = 0.001) -> None:
        super().__init__(lookback=2)
        self.tolerance = tolerance

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        tol = (p.high - p.low) * self.tolerance
        if abs(p.high - c.high) <= tol and _is_bull(p) and not _is_bull(c):
            return -1
        if abs(p.low - c.low) <= tol and not _is_bull(p) and _is_bull(c):
            return 1
        return 0


class Kicking(CandlePattern):
    """Kicking: two marubozu candles of opposite color with gap."""
    _ind_name = "KICKING"

    def __init__(self) -> None:
        super().__init__(lookback=2)

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        p_rng = p.high - p.low
        c_rng = c.high - c.low
        if p_rng == 0 or c_rng == 0:
            return 0
        p_body = _body(p) / p_rng
        c_body = _body(c) / c_rng
        if p_body >= 0.9 and c_body >= 0.9:
            if not _is_bull(p) and _is_bull(c) and c.open > p.open:
                return 1
            if _is_bull(p) and not _is_bull(c) and c.open < p.open:
                return -1
        return 0


class OnNeck(CandlePattern):
    """On Neck: bearish candle then small bullish candle closing near prior low."""
    _ind_name = "ON_NECK"

    def __init__(self, tolerance: float = 0.002) -> None:
        super().__init__(lookback=2)
        self.tolerance = tolerance

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        tol = (p.high - p.low) * self.tolerance
        if not _is_bull(p) and _is_bull(c):
            if abs(c.close - p.low) <= tol:
                return -1
        return 0


class MatchingLow(CandlePattern):
    """Matching Low: two bearish candles closing at the same low — bullish reversal."""
    _ind_name = "MATCHING_LOW"

    def __init__(self, tolerance: float = 0.001) -> None:
        super().__init__(lookback=2)
        self.tolerance = tolerance

    def detect(self, bars):
        if len(bars) < 2:
            return 0
        p, c = bars[-2], bars[-1]
        tol = (p.high - p.low) * self.tolerance
        if not _is_bull(p) and not _is_bull(c):
            if abs(p.close - c.close) <= tol:
                return 1
        return 0
