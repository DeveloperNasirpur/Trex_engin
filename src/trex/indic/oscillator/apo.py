from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class APO(Indicator):
    """Absolute Price Oscillator = EMA_fast - EMA_slow."""
    _ind_name   = "APO"
    _key_params = ("fast_period", "slow_period")

    def init_depends(self): pass

    def __init__(self, fast_period: int = 12, slow_period: int = 26,
                 value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.fast_period = fast_period; self.slow_period = slow_period
        kf = 2.0 / (fast_period + 1); ks = 2.0 / (slow_period + 1)
        self._kf, self._kf1 = kf, 1 - kf
        self._ks, self._ks1 = ks, 1 - ks
        self._ef = self._es = 0.0; self._count = 0

    def _first_calculate(self, value: float, prev):
        self._count += 1
        if self._count == 1: self._ef = self._es = value; return None
        self._ef = self._ef * self._kf1 + value * self._kf
        self._es = self._es * self._ks1 + value * self._ks
        if self._count < self.slow_period: return None
        return self._ef - self._es

    def _calculate_new_value(self, value: float, prev) -> float:
        self._ef = self._ef * self._kf1 + value * self._kf
        self._es = self._es * self._ks1 + value * self._ks
        return self._ef - self._es

    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["ef"] = self._ef; s["es"] = self._es; s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._ef = state.get("ef", 0.0); self._es = state.get("es", 0.0)
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.slow_period, key=self.indicator_key())]
