from __future__ import annotations
from collections import deque
from math import comb
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class PWMA(Indicator):
    _ind_name   = "PWMA"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 10, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        n = period - 1
        row = [comb(n, i) for i in range(period)]
        t = sum(row)
        self._weights = [r / t for r in row]
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
