from __future__ import annotations
"""
trex.indic.oscillator.mom
~~~~~~~~~~~~~~~~~~~~~~~~~~
Momentum — absolute price change over ``period`` bars.

Formula:
    Momentum = close − close[period]

Hot-path (run phase):
    oldest = win[0]
    win.append(value)
    return value − oldest       ← zero branch
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class Momentum(Indicator):
    """
    Momentum Oscillator.

    Output: ``float``  (first emitted after ``period + 1`` ticks)
    """
    _ind_name   = "MOM"
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
        period:          int      = 10,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period  = period
        self._win: deque[float] = deque(maxlen=period + 1)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._win.append(value)
        if len(self._win) <= self.period:
            return None
        # win is full (period+1 entries): win[0] is the oldest, win[-1]=value
        # emit value - oldest, which shifts window ready for run phase
        oldest = self._win[0]
        return value - oldest

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: float) -> float:
        self._win.append(value)   # push new value → oldest drops off
        return value - self._win[0]  # win[0] is now close[n-period]

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win"] = list(self._win)
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win = deque(state["win"], maxlen=self.period + 1)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.momentum(self.period, key=self.indicator_key())]
