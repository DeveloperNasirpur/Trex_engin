from __future__ import annotations
"""
trex.indic.trend.sma
~~~~~~~~~~~~~~~~~~~~
Simple Moving Average — O(1) incremental update.

Performance design
------------------
``_first_calculate`` accumulates values until the window is full and seeds
``_total``.  After that, ``_calculate_new_value`` is:

    _total += value - oldest
    return _total / period

— one subtraction, one addition, one division — with the deque acting as an
O(1) FIFO for the oldest value.
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class SMA(Indicator):
    """
    Simple Moving Average.

    Output: ``float``  (first emitted after ``period`` ticks)
    """
    _ind_name   = "SMA"
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
        period:          int      = 20,
        value_extractor: Callable|None = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor, save_input=False)
        self.period:   int          = period
        self._period_f: float       = float(period)
        self._win:     deque[float] = deque(maxlen=period)
        self._total:   float        = 0.0

    # ------------------------------------------------------------------
    # Boot — fill window, seed _total
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._win.append(value)
        self._total += value
        if len(self._win) < self.period:
            return None
        return self._total / self._period_f

    # ------------------------------------------------------------------
    # Run — O(1) sliding update, no conditionals
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: object) -> float:
        self._total += value - self._win[0]
        self._win.append(value)
        return self._total / self._period_f

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win"]   = list(self._win)
            s["total"] = self._total
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win   = deque(state["win"], maxlen=self.period)
            self._total = state["total"]

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.sma(self.period, key=self.indicator_key())]
