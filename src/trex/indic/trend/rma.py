from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class RMA(Indicator):
    _ind_name   = "RMA"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        self._pm1 = float(period - 1)
        self._pf  = float(period)
        self._buf: list = []
    def _first_calculate(self, value: float, prev):
        self._buf.append(value)
        if len(self._buf) < self.period: return None
        seed = sum(self._buf) / self._pf
        self._buf = None
        return seed
    def _calculate_new_value(self, value: float, prev) -> float:
        return (self._pipe.prev_output * self._pm1 + value) / self._pf
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["buf_cleared"] = True
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._buf = None
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.period, key=self.indicator_key())]
