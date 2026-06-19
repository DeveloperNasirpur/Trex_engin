from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class T3(Indicator):
    _ind_name   = "T3"
    _key_params = ("period", "volume_factor")
    def init_depends(self): pass
    def __init__(self, period: int = 5, volume_factor: float = 0.7, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        self.volume_factor = volume_factor
        v = volume_factor
        k = 2.0 / (period + 1.0)
        self._k, self._k1 = k, 1.0 - k
        self._c1 = -(v**3)
        self._c2 = 3*v**2 + 3*v**3
        self._c3 = -6*v**2 - 3*v - 3*v**3
        self._c4 = 1 + 3*v + v**3 + 3*v**2
        self._e = [0.0] * 6
        self._count = 0
        self._warmup = period * 6
    def _update_emas(self, value: float):
        k, k1, e = self._k, self._k1, self._e
        e[0] = e[0] * k1 + value * k
        for i in range(1, 6): e[i] = e[i] * k1 + e[i-1] * k
    def _t3(self) -> float:
        e = self._e
        return self._c1*e[5] + self._c2*e[4] + self._c3*e[3] + self._c4*e[2]
    def _first_calculate(self, value: float, prev):
        self._count += 1
        if self._count == 1:
            for i in range(6): self._e[i] = value
        else:
            self._update_emas(value)
        if self._count < self._warmup: return None
        return self._t3()
    def _calculate_new_value(self, value: float, prev) -> float:
        self._update_emas(value)
        return self._t3()
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["e"] = list(self._e); s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._e = state.get("e", [0.0]*6); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.period, key=self.indicator_key())]
