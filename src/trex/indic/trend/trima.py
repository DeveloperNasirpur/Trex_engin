from __future__ import annotations
from collections import deque
from math import ceil
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class TRIMA(Indicator):
    _ind_name   = "TRIMA"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 20, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        p1 = ceil((period + 1) / 2)
        p2 = period - p1 + 1
        self._p1, self._p2 = p1, p2
        self._p1f, self._p2f = float(p1), float(p2)
        self._win1: deque = deque(maxlen=p1)
        self._win2: deque = deque(maxlen=p2)
        self._sum1 = self._sum2 = 0.0
    def _first_calculate(self, value: float, prev):
        self._win1.append(value); self._sum1 += value
        if len(self._win1) < self._p1: return None
        sma1 = self._sum1 / self._p1f
        self._win2.append(sma1); self._sum2 += sma1
        if len(self._win2) < self._p2: return None
        return self._sum2 / self._p2f
    def _calculate_new_value(self, value: float, prev) -> float:
        self._sum1 += value - self._win1[0]; self._win1.append(value)
        sma1 = self._sum1 / self._p1f
        self._sum2 += sma1 - self._win2[0]; self._win2.append(sma1)
        return self._sum2 / self._p2f
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win1"] = list(self._win1); s["win2"] = list(self._win2); s["sum1"] = self._sum1; s["sum2"] = self._sum2
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win1 = deque(state.get("win1", []), maxlen=self._p1)
            self._win2 = deque(state.get("win2", []), maxlen=self._p2)
            self._sum1 = state.get("sum1", 0.0); self._sum2 = state.get("sum2", 0.0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.sma(self.period, key=self.indicator_key())]
