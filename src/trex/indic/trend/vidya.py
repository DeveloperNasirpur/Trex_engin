from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class VIDYA(Indicator):
    _ind_name   = "VIDYA"
    _key_params = ("cmo_period", "smooth")
    def init_depends(self): pass
    def __init__(self, cmo_period: int = 9, smooth: int = 12, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.cmo_period = cmo_period
        self.smooth = smooth
        self._alpha = 2.0 / (smooth + 1.0)
        self._gains: deque = deque(maxlen=cmo_period)
        self._losses: deque = deque(maxlen=cmo_period)
        self._sum_up = self._sum_dn = 0.0
        self._vidya = 0.0
        self._count = 0
    def _cmo(self) -> float:
        t = self._sum_up + self._sum_dn
        return (self._sum_up - self._sum_dn) / t if t else 0.0
    def _first_calculate(self, value: float, prev):
        self._count += 1
        if prev is not None:
            d = value - prev
            g = max(d, 0.0); l = max(-d, 0.0)
            if len(self._gains) == self.cmo_period: self._sum_up -= self._gains[0]; self._sum_dn -= self._losses[0]
            self._gains.append(g); self._losses.append(l)
            self._sum_up += g; self._sum_dn += l
        if self._count <= self.cmo_period: return None
        self._vidya = value
        return value
    def _calculate_new_value(self, value: float, prev) -> float:
        d = value - prev
        g = max(d, 0.0); l = max(-d, 0.0)
        if len(self._gains) == self.cmo_period: self._sum_up -= self._gains[0]; self._sum_dn -= self._losses[0]
        self._gains.append(g); self._losses.append(l)
        self._sum_up += g; self._sum_dn += l
        self._vidya += self._alpha * abs(self._cmo()) * (value - self._vidya)
        return self._vidya
    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["gains"] = list(self._gains); s["losses"] = list(self._losses)
            s["sum_up"] = self._sum_up; s["sum_dn"] = self._sum_dn
            s["vidya"] = self._vidya; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._gains = deque(state.get("gains", []), maxlen=self.cmo_period)
            self._losses = deque(state.get("losses", []), maxlen=self.cmo_period)
            self._sum_up = state.get("sum_up", 0.0); self._sum_dn = state.get("sum_dn", 0.0)
            self._vidya = state.get("vidya", 0.0); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.smooth, key=self.indicator_key())]
