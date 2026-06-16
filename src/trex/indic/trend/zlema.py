from __future__ import annotations
"""
trex.indic.trend.zlema
~~~~~~~~~~~~~~~~~~~~~~
Zero-Lag EMA — compensates EMA lag by using a de-lagged price series.

Formula:
    lag      = (period − 1) // 2
    adjusted = 2 × close − close[lag]
    ZLEMA    = EMA(adjusted, period)

Architecture
------------
ZLEMA maintains its own lag window (size = lag + 1).
On each tick it computes the adjusted value and feeds it into a private EMA
sub-indicator.  The private EMA emits the ZLEMA result via callback.

Data flow::

    raw ──► [extract close] ──► adjusted = 2×val − win[0]
                                          └──► EMA(period)[private float EMA] ──► emit
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator
from trex.indic.trend.ema import EMA


class ZLEMA(Indicator):
    """
    Zero-Lag Exponential Moving Average.

    Output: ``float``  (first emitted after ``period`` ticks)
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        sym, tf = self.context_symbol, self.tf

        self._ema = EMA(period=self.period, value_extractor=None)
        self._ema.context_key    = f"{self.context_key}:ema"
        self._ema.context_symbol = sym
        self._ema.tf             = tf
        self._ema.source_tf      = self.source_tf
        self._ema.init_depends()

        self._ema.add_callback_listener(self.context_key, self._on_ema)

    def dispatch(self) -> None:
        del self._ema

    def __init__(
        self,
        period:          int      = 14,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period = period
        lag         = (period - 1) // 2
        self._win:  deque[float] = deque(maxlen=lag + 1)
        self._ema   = None

    def _on_ema(self, val: float) -> None:
        self.emit(val)

    def _first_calculate(self, value: float, prev) -> object:
        self._win.append(value)
        adjusted = 2.0 * value - self._win[0]
        self._ema.add_input_value(adjusted)
        return True  # EMA callback handles emission

    def _calculate_new_value(self, value: float, prev: float) -> None:
        lag_val  = self._win[0]
        self._win.append(value)
        adjusted = 2.0 * value - lag_val
        self._ema.add_input_value(adjusted)

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.zlema(self.period)]
