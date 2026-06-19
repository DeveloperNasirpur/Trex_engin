from __future__ import annotations
from collections import deque
from math import sin, pi
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class SINWMA(Indicator):
    _ind_name   = "SINWMA"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        w = [sin((i + 1) * pi / (period + 1)) for i in range(period)]
        t = sum(w)
        self._weights = [x / t for x in w]
        self._win: deque = deque(maxlen=period)
    def _first_calculate(self, value: float, prev):
        self._win.append(value)
        if len(self._win) < self.period: return None
        return sum(w * v for w, v in zip(self._weights, self._win))
    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)
        return sum(w * v for w, v in zip(self._weights, self._win))
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win)
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._win = deque(state.get("win", []), maxlen=self.period)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.sma(self.period, key=self.indicator_key())]
