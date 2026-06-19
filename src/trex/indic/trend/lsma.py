from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class LSMA(Indicator):
    _ind_name   = "LSMA"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 25, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        n = period
        self._nf = float(n)
        self._sx  = n * (n - 1) / 2.0
        self._sx2 = n * (n - 1) * (2*n - 1) / 6.0
        self._denom = n * self._sx2 - self._sx ** 2
        self._win: deque = deque(maxlen=n)
    def _linreg(self) -> float:
        sy = sxy = 0.0
        for i, v in enumerate(self._win): sy += v; sxy += i * v
        b = (self._nf * sxy - self._sx * sy) / self._denom
        a = (sy - b * self._sx) / self._nf
        return a + b * (self._nf - 1)
    def _first_calculate(self, value: float, prev):
        self._win.append(value)
        if len(self._win) < self.period: return None
        return self._linreg()
    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value); return self._linreg()
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
