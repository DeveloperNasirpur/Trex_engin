from __future__ import annotations
from collections import deque
from math import sqrt, log
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class HV(Indicator):
    """Historical Volatility — annualized std dev of log returns."""
    _ind_name   = "HV"
    _key_params = ("period", "annual_factor")
    def init_depends(self): pass
    def __init__(self, period: int = 20, annual_factor: float = 252.0, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period; self.annual_factor = annual_factor
        self._nf = float(period); self._ann = sqrt(annual_factor)
        self._win: deque = deque(maxlen=period); self._s = self._ss = 0.0
        self._prev = None
    def _first_calculate(self, value: float, prev):
        if prev and prev > 0:
            r = log(value / prev)
            self._win.append(r); self._s += r; self._ss += r*r
        if len(self._win) < self.period: return None
        mean = self._s / self._nf
        var = self._ss / self._nf - mean*mean
        return sqrt(max(var, 0.0)) * self._ann * 100.0
    def _calculate_new_value(self, value: float, prev) -> float:
        if prev and prev > 0:
            r = log(value / prev)
            old = self._win[0] if len(self._win) == self.period else 0.0
            self._s += r - old; self._ss += r*r - old*old
            self._win.append(r)
        mean = self._s / self._nf
        var = self._ss / self._nf - mean*mean
        return sqrt(max(var, 0.0)) * self._ann * 100.0
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win); s["s"] = self._s; s["ss"] = self._ss
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._win = deque(state.get("win", []), maxlen=self.period); self._s = state.get("s", 0.0); self._ss = state.get("ss", 0.0)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
