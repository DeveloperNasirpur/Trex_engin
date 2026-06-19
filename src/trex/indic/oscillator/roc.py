from __future__ import annotations
"""
trex.indic.oscillator.roc
~~~~~~~~~~~~~~~~~~~~~~~~~~
Rate of Change — percentage change over ``period`` bars.

Formula:
    ROC = (close − close[period]) / close[period] × 100

Hot-path (run phase):
    oldest = win[0]
    win.append(value)
    return (value − oldest) / oldest × 100    ← zero branch
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class ROC(Indicator):
    """
    Rate of Change (momentum oscillator).

    Output: ``float`` (% change)   first emitted after ``period + 1`` ticks
    """
    _ind_name   = "ROC"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(
        self,
        period:          int      = 12,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period  = period
        # ring buffer of size period+1; win[0] is the value period bars ago
        self._win: deque[float] = deque(maxlen=period + 1)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._win.append(value)
        if len(self._win) <= self.period:
            return None
        return (value - self._win[0]) / self._win[0] * 100.0

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: float) -> float:
        oldest = self._win[0]
        self._win.append(value)
        return (value - oldest) / oldest * 100.0

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.roc(self.period, key=self.indicator_key())]
