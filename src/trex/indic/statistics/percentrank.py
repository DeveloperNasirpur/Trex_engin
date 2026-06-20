from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class PercentRank(Indicator):
    """Percent Rank — position of current value in its lookback window."""
    _ind_name   = "PERCENTRANK"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 20, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period; self._win: deque = deque(maxlen=period)
    def _first_calculate(self, value: float, prev):
        self._win.append(value)
        if len(self._win) < self.period: return None
        count = sum(1 for v in self._win if v <= value)
        return (count / self.period) * 100.0
    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)
        count = sum(1 for v in self._win if v <= value)
        return (count / self.period) * 100.0
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win)
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._win = deque(state.get("win", []), maxlen=self.period)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
