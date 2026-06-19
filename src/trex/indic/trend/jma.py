from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class JMA(Indicator):
    _ind_name   = "JMA"
    _key_params = ("period", "phase", "power")
    def init_depends(self): pass
    def __init__(self, period: int = 7, phase: int = 0, power: int = 2, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period; self.phase = phase; self.power = power
        pr = max(0.5, min(2.5, phase / 100.0 + 1.5))
        beta = 0.45 * (period - 1) / (0.45 * (period - 1) + 2)
        self._alpha = beta ** power; self._beta = beta; self._pr = pr
        self._e0 = self._e1 = self._e2 = 0.0; self._count = 0
    def _first_calculate(self, value: float, prev):
        self._count += 1
        if self._count == 1: self._e0 = self._e1 = self._e2 = value; return None
        a, b, pr = self._alpha, self._beta, self._pr
        self._e0 = (1 - a) * value + a * self._e0
        self._e1 = (value - self._e0) * (1 - b) + b * self._e1
        self._e2 = self._e0 + pr * self._e1
        if self._count < self.period: return None
        return self._e2
    def _calculate_new_value(self, value: float, prev) -> float:
        a, b, pr = self._alpha, self._beta, self._pr
        self._e0 = (1 - a) * value + a * self._e0
        self._e1 = (value - self._e0) * (1 - b) + b * self._e1
        self._e2 = self._e0 + pr * self._e1
        return self._e2
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["e0"] = self._e0; s["e1"] = self._e1; s["e2"] = self._e2; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._e0 = state.get("e0", 0.0); self._e1 = state.get("e1", 0.0); self._e2 = state.get("e2", 0.0); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.period, key=self.indicator_key())]
