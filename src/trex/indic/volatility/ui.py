from __future__ import annotations
from collections import deque
from math import sqrt
from typing import Callable
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator

class UlcerIndex(Indicator):
    """Ulcer Index — measures downside risk/drawdown."""
    _ind_name   = "UI"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14, value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.period = period; self._nf = float(period)
        self._win: deque = deque(maxlen=period)
    def _first_calculate(self, value: float, prev):
        self._win.append(value)
        if len(self._win) < self.period: return None
        return self._ui()
    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value); return self._ui()
    def _ui(self) -> float:
        w = list(self._win); hh = max(w)
        sq_sum = sum(((v - hh)/hh*100)**2 for v in w) if hh else 0.0
        return sqrt(sq_sum / self._nf)
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
