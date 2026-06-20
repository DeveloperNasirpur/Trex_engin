from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class Variance(Indicator):
    """Rolling population variance."""
    _ind_name   = "VAR"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 20, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period; self._nf = float(period)
        self._win: deque = deque(maxlen=period); self._s = self._ss = 0.0
    def _first_calculate(self, value: float, prev):
        self._win.append(value); self._s += value; self._ss += value*value
        if len(self._win) < self.period: return None
        mean = self._s / self._nf
        return max(self._ss / self._nf - mean*mean, 0.0)
    def _calculate_new_value(self, value: float, prev) -> float:
        old = self._win[0]; self._s += value-old; self._ss += value*value - old*old
        self._win.append(value); mean = self._s / self._nf
        return max(self._ss / self._nf - mean*mean, 0.0)
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
