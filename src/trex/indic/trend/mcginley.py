from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class McGinley(Indicator):
    _ind_name   = "MCGINLEY"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        self._pf = float(period)
        self._buf: list = []
    def _first_calculate(self, value: float, prev):
        self._buf.append(value)
        if len(self._buf) < self.period: return None
        seed = sum(self._buf) / self._pf
        self._buf = None
        return seed
    def _calculate_new_value(self, value: float, prev) -> float:
        md = self._pipe.prev_output
        if not md: return value
        return md + (value - md) / (self._pf * (value / md) ** 4)
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
