from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class CandlePattern(Indicator):
    """Base class for candlestick pattern indicators.

    Emits +1 (bullish), -1 (bearish), or 0 (no pattern) on each bar.
    Subclasses override detect(bars) -> int.
    """
    _key_params = ()

    def __init__(self, lookback: int = 1) -> None:
        super().__init__(value_extractor=None)
        self.lookback = lookback
        self._bars: deque[OHLCV] = deque(maxlen=lookback + 1)

    def init_depends(self) -> None:
        pass

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def add_input_value(self, raw: object) -> None:
        if not isinstance(raw, OHLCV):
            return
        self._bars.append(raw)
        if len(self._bars) >= self.lookback:
            sig = self.detect(list(self._bars))
            self._pipe.emit(sig)

    def detect(self, bars: list[OHLCV]) -> int:
        """Override in subclasses. bars[-1] is the current bar."""
        return 0

    def _first_calculate(self, value, prev):
        return None

    def _calculate_new_value(self, value, prev):
        return None

    def series_defs(self):
        return []
