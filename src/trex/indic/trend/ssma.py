from __future__ import annotations
from math import exp, cos, pi
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class SSMA(Indicator):
    _ind_name   = "SSMA"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 20, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        a1 = exp(-1.414 * pi / period)
        b1 = 2 * a1 * cos(1.414 * pi / period)
        self._c2, self._c3 = b1, -(a1 ** 2)
        self._c1 = 1.0 - self._c2 - self._c3
        self._ss1 = self._ss2 = 0.0
        self._count = 0
    def _first_calculate(self, value: float, prev):
        self._count += 1
        if self._count == 1:
            self._ss1 = self._ss2 = value; return None
        ss = self._c1 * (value + (prev or value)) / 2 + self._c2 * self._ss1 + self._c3 * self._ss2
        self._ss2 = self._ss1; self._ss1 = ss
        if self._count < 3: return None
        return ss
    def _calculate_new_value(self, value: float, prev) -> float:
        ss = self._c1 * (value + prev) / 2 + self._c2 * self._ss1 + self._c3 * self._ss2
        self._ss2 = self._ss1; self._ss1 = ss
        return ss
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["ss1"] = self._ss1; s["ss2"] = self._ss2; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._ss1 = state.get("ss1", 0.0); self._ss2 = state.get("ss2", 0.0); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.period, key=self.indicator_key())]
