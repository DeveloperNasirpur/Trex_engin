from __future__ import annotations
from .base import CandlePattern
from trex.base.ohlcv import OHLCV


def _body(b: OHLCV) -> float:
    return abs(b.close - b.open)

def _range(b: OHLCV) -> float:
    return b.high - b.low

def _upper_shadow(b: OHLCV) -> float:
    return b.high - max(b.close, b.open)

def _lower_shadow(b: OHLCV) -> float:
    return min(b.close, b.open) - b.low

def _is_bull(b: OHLCV) -> bool:
    return b.close >= b.open

def _mid(b: OHLCV) -> float:
    return (b.open + b.close) / 2


class Doji(CandlePattern):
    """Doji: body <= 10% of range."""
    _ind_name = "DOJI"

    def __init__(self, threshold: float = 0.1) -> None:
        super().__init__(lookback=1)
        self.threshold = threshold

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        return 1 if _body(b) / rng <= self.threshold else 0


class DragonFlyDoji(CandlePattern):
    """DragonFly Doji: tiny body at top, long lower shadow."""
    _ind_name = "DRAGONFLY_DOJI"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if body / rng <= 0.1 and lower >= rng * 0.6 and upper <= rng * 0.1:
            return 1
        return 0


class GravestoneDoji(CandlePattern):
    """Gravestone Doji: tiny body at bottom, long upper shadow."""
    _ind_name = "GRAVESTONE_DOJI"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if body / rng <= 0.1 and upper >= rng * 0.6 and lower <= rng * 0.1:
            return -1
        return 0


class Hammer(CandlePattern):
    """Hammer: bullish reversal, long lower shadow, small body at top."""
    _ind_name = "HAMMER"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if lower >= 2 * body and upper <= body * 0.5 and body / rng >= 0.1:
            return 1
        return 0


class InvertedHammer(CandlePattern):
    """Inverted Hammer: long upper shadow, small body at bottom."""
    _ind_name = "INVERTED_HAMMER"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if upper >= 2 * body and lower <= body * 0.5 and body / rng >= 0.1:
            return 1
        return 0


class HangingMan(CandlePattern):
    """Hanging Man: bearish reversal, same shape as Hammer but after uptrend."""
    _ind_name = "HANGING_MAN"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if lower >= 2 * body and upper <= body * 0.5 and body / rng >= 0.1:
            return -1
        return 0


class ShootingStar(CandlePattern):
    """Shooting Star: bearish reversal, long upper shadow, small body at bottom."""
    _ind_name = "SHOOTING_STAR"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if upper >= 2 * body and lower <= body * 0.5 and body / rng >= 0.1:
            return -1
        return 0


class Marubozu(CandlePattern):
    """Marubozu: large body with minimal shadows (>=95% body)."""
    _ind_name = "MARUBOZU"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        if body / rng >= 0.95:
            return 1 if _is_bull(b) else -1
        return 0


class SpinningTop(CandlePattern):
    """Spinning Top: small body with shadows on both sides."""
    _ind_name = "SPINNING_TOP"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        upper = _upper_shadow(b)
        lower = _lower_shadow(b)
        if (body / rng <= 0.3 and upper >= rng * 0.2 and lower >= rng * 0.2):
            return 1 if _is_bull(b) else -1
        return 0


class LongLeggedDoji(CandlePattern):
    """Long Legged Doji: tiny body, long shadows on both sides."""
    _ind_name = "LONG_LEGGED_DOJI"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        upper = _upper_shadow(b)
        lower = _lower_shadow(b)
        if body / rng <= 0.05 and upper >= rng * 0.35 and lower >= rng * 0.35:
            return 1
        return 0


class BullishBelt(CandlePattern):
    """Bullish Belt Hold: bullish marubozu opening at low."""
    _ind_name = "BULLISH_BELT"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0 or not _is_bull(b):
            return 0
        lower = _lower_shadow(b)
        body = _body(b)
        if lower <= body * 0.05 and body / rng >= 0.7:
            return 1
        return 0


class BearishBelt(CandlePattern):
    """Bearish Belt Hold: bearish marubozu opening at high."""
    _ind_name = "BEARISH_BELT"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0 or _is_bull(b):
            return 0
        upper = _upper_shadow(b)
        body = _body(b)
        if upper <= body * 0.05 and body / rng >= 0.7:
            return -1
        return 0


class HighWave(CandlePattern):
    """High Wave: small body, very long shadows on both sides."""
    _ind_name = "HIGH_WAVE"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        upper = _upper_shadow(b)
        lower = _lower_shadow(b)
        if body / rng <= 0.15 and upper >= rng * 0.4 and lower >= rng * 0.4:
            return 1 if _is_bull(b) else -1
        return 0


class RickshawMan(CandlePattern):
    """Rickshaw Man: doji with equal long shadows, body near center."""
    _ind_name = "RICKSHAW_MAN"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        rng = _range(b)
        if rng == 0:
            return 0
        body = _body(b)
        upper = _upper_shadow(b)
        lower = _lower_shadow(b)
        mid_body = _mid(b)
        mid_range = b.low + rng / 2
        if (body / rng <= 0.05 and upper >= rng * 0.35 and lower >= rng * 0.35
                and abs(mid_body - mid_range) <= rng * 0.1):
            return 1
        return 0


class UmbrellaLine(CandlePattern):
    """Umbrella Line: lower shadow >= 2x body, small upper shadow."""
    _ind_name = "UMBRELLA_LINE"

    def __init__(self) -> None:
        super().__init__(lookback=1)

    def detect(self, bars):
        b = bars[-1]
        body = _body(b)
        lower = _lower_shadow(b)
        upper = _upper_shadow(b)
        if body == 0:
            return 0
        if lower >= 2 * body and upper <= body:
            return 1 if _is_bull(b) else -1
        return 0
