from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class HWMA(Indicator):
    _ind_name   = "HWMA"
    _key_params = ("alpha", "beta")
    def init_depends(self): pass
    def __init__(self, alpha: float = 0.2, beta: float = 0.1, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.alpha = alpha; self.beta = beta
        self._a1c = 1.0 - alpha; self._b1c = 1.0 - beta
        self._level = self._trend = 0.0; self._count = 0
    def _first_calculate(self, value: float, prev):
        self._count += 1
        if self._count == 1: self._level = value; return None
        old = self._level
        self._level = self.alpha * value + self._a1c * (self._level + self._trend)
        self._trend = self.beta * (self._level - old) + self._b1c * self._trend
        if self._count < 3: return None
        return self._level + self._trend
    def _calculate_new_value(self, value: float, prev) -> float:
        old = self._level
        self._level = self.alpha * value + self._a1c * (self._level + self._trend)
        self._trend = self.beta * (self._level - old) + self._b1c * self._trend
        return self._level + self._trend
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["level"] = self._level; s["trend"] = self._trend; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._level = state.get("level", 0.0); self._trend = state.get("trend", 0.0); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(14, key=self.indicator_key())]
