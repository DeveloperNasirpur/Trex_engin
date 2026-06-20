from __future__ import annotations
from .base import CandlePattern
from trex.base.ohlcv import OHLCV


def _body(b: OHLCV) -> float:
    return abs(b.close - b.open)

def _is_bull(b: OHLCV) -> bool:
    return b.close >= b.open

def _is_doji(b: OHLCV, threshold: float = 0.1) -> bool:
    rng = b.high - b.low
    return rng > 0 and _body(b) / rng <= threshold


class MorningStar(CandlePattern):
    """Morning Star: bearish → small body gap down → bullish recovery."""
    _ind_name = "MORNING_STAR"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        mid_a = (a.open + a.close) / 2
        if not _is_bull(a) and _body(b) < _body(a) * 0.5 and _is_bull(c):
            if b.close < a.close and c.close > mid_a:
                return 1
        return 0


class EveningStar(CandlePattern):
    """Evening Star: bullish → small body gap up → bearish reversal."""
    _ind_name = "EVENING_STAR"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        mid_a = (a.open + a.close) / 2
        if _is_bull(a) and _body(b) < _body(a) * 0.5 and not _is_bull(c):
            if b.close > a.close and c.close < mid_a:
                return -1
        return 0


class MorningDojiStar(CandlePattern):
    """Morning Doji Star: bearish → doji → bullish."""
    _ind_name = "MORNING_DOJI_STAR"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        mid_a = (a.open + a.close) / 2
        if not _is_bull(a) and _is_doji(b) and _is_bull(c):
            if c.close > mid_a:
                return 1
        return 0


class EveningDojiStar(CandlePattern):
    """Evening Doji Star: bullish → doji → bearish."""
    _ind_name = "EVENING_DOJI_STAR"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        mid_a = (a.open + a.close) / 2
        if _is_bull(a) and _is_doji(b) and not _is_bull(c):
            if c.close < mid_a:
                return -1
        return 0


class ThreeWhiteSoldiers(CandlePattern):
    """Three White Soldiers: three consecutive bullish candles, each higher close."""
    _ind_name = "THREE_WHITE_SOLDIERS"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        if _is_bull(a) and _is_bull(b) and _is_bull(c):
            if b.close > a.close and c.close > b.close:
                if b.open > a.open and c.open > b.open:
                    return 1
        return 0


class ThreeBlackCrows(CandlePattern):
    """Three Black Crows: three consecutive bearish candles, each lower close."""
    _ind_name = "THREE_BLACK_CROWS"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        if not _is_bull(a) and not _is_bull(b) and not _is_bull(c):
            if b.close < a.close and c.close < b.close:
                if b.open < a.open and c.open < b.open:
                    return -1
        return 0


class ThreeInsideUp(CandlePattern):
    """Three Inside Up: bearish, harami bullish, then confirming bullish."""
    _ind_name = "THREE_INSIDE_UP"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        if (not _is_bull(a) and _is_bull(b) and _is_bull(c)
                and b.open > a.close and b.close < a.open
                and c.close > b.close):
            return 1
        return 0


class ThreeInsideDown(CandlePattern):
    """Three Inside Down: bullish, harami bearish, then confirming bearish."""
    _ind_name = "THREE_INSIDE_DOWN"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        if (_is_bull(a) and not _is_bull(b) and not _is_bull(c)
                and b.open < a.close and b.close > a.open
                and c.close < b.close):
            return -1
        return 0


class Deliberation(CandlePattern):
    """Deliberation: three bullish candles, third is small (bearish warning)."""
    _ind_name = "DELIBERATION"

    def __init__(self) -> None:
        super().__init__(lookback=3)

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        if _is_bull(a) and _is_bull(b) and _is_bull(c):
            if b.close > a.close and c.close > b.close:
                if _body(c) < _body(b) * 0.5:
                    return -1
        return 0


class IdenticalThreeCrows(CandlePattern):
    """Identical Three Crows: three bearish candles opening near prior close."""
    _ind_name = "IDENTICAL_THREE_CROWS"

    def __init__(self, tolerance: float = 0.002) -> None:
        super().__init__(lookback=3)
        self.tolerance = tolerance

    def detect(self, bars):
        if len(bars) < 3:
            return 0
        a, b, c = bars[-3], bars[-2], bars[-1]
        if not _is_bull(a) and not _is_bull(b) and not _is_bull(c):
            rng = a.high - a.low or 1
            tol = rng * self.tolerance
            if (abs(b.open - a.close) <= tol and abs(c.open - b.close) <= tol
                    and b.close < a.close and c.close < b.close):
                return -1
        return 0
