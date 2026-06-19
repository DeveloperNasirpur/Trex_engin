from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class DPO(Indicator):
    """Detrended Price Oscillator — removes long-term trend."""
    _ind_name   = "DPO"
    _key_params = ("period",)

    def init_depends(self): pass

    def __init__(self, period: int = 20,
                 value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period
        self._pf = float(period)
        self._shift = period // 2 + 1
        buf_size = period + self._shift
        self._win: deque = deque(maxlen=buf_size)
        self._count = 0

    def _first_calculate(self, value: float, prev):
        self._count += 1
        self._win.append(value)
        if self._count < self.period + self._shift: return None
        sma_vals = list(self._win)
        sma = sum(sma_vals[-self.period - self._shift: -self._shift]) / self._pf
        dpo = sma_vals[-self._shift] - sma
        return dpo

    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)
        sma_vals = list(self._win)
        sma = sum(sma_vals[-self.period - self._shift: -self._shift]) / self._pf
        dpo = sma_vals[-self._shift] - sma
        return dpo

    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win); s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            buf_size = self.period + self._shift
            self._win = deque(state.get("win", []), maxlen=buf_size)
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
