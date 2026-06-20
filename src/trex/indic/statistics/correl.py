from __future__ import annotations
from collections import deque
from math import sqrt
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class Correlation(Indicator):
    """Rolling Pearson Correlation of price with linear time index."""
    _ind_name   = "CORREL"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 20, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period; n = period
        self._nf = float(n)
        xs = list(range(n)); xm = sum(xs)/n
        self._xm = xm
        self._sxx = sum((x-xm)**2 for x in xs)
        self._win: deque = deque(maxlen=n); self._sy = self._sxy = 0.0
    def _first_calculate(self, value: float, prev):
        self._win.append(value)
        if len(self._win) < self.period: return None
        w = list(self._win); ym = sum(w)/self._nf
        syy = sum((y-ym)**2 for y in w)
        sxy = sum((i-self._xm)*(y-ym) for i,y in enumerate(w))
        denom = sqrt(self._sxx * syy)
        return sxy / denom if denom else 0.0
    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)
        w = list(self._win); ym = sum(w)/self._nf
        syy = sum((y-ym)**2 for y in w)
        sxy = sum((i-self._xm)*(y-ym) for i,y in enumerate(w))
        denom = sqrt(self._sxx * syy)
        return sxy / denom if denom else 0.0
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win)
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._win = deque(state.get("win", []), maxlen=self.period)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
