from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class VROC(Indicator):
    """Volume Rate of Change."""
    _ind_name   = "VROC"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14):
        super().__init__(value_extractor=None)
        self.period = period
        self._win: deque = deque(maxlen=period+1); self._count = 0
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        self._win.append(raw.volume)
        if self._count > self.period and self._win[0]:
            self._pipe.emit((raw.volume - self._win[0]) / self._win[0] * 100.0)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win); s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._win = deque(state.get("win", []), maxlen=self.period+1); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
