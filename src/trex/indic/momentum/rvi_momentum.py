from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class RVI(Indicator):
    """Relative Vigor Index — close vs range ratio."""
    _ind_name   = "RVI"
    _key_params = ("period",)

    def init_depends(self): pass

    def __init__(self, period: int = 10):
        super().__init__(value_extractor=None)
        self.period = period
        self._rvi_win: deque = deque(maxlen=period)
        self._rvi_sum = 0.0
        self._bars: deque = deque(maxlen=4)
        self._count = 0

    def _sym(self, bars, fn):
        if len(bars) < 4: return 0.0
        b = list(bars)
        return (fn(b[3]) + 2 * fn(b[2]) + 2 * fn(b[1]) + fn(b[0])) / 6.0

    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw
        self._bars.append(raw)
        self._count += 1
        if self._count < 4: return
        num = self._sym(self._bars, lambda b: b.close - b.open)
        den = self._sym(self._bars, lambda b: b.high - b.low)
        if len(self._rvi_win) == self.period: self._rvi_sum -= self._rvi_win[0]
        rvi_val = num / den if den else 0.0
        self._rvi_win.append(rvi_val); self._rvi_sum += rvi_val
        if self._count < self.period + 3: return
        rvi = self._rvi_sum / self.period
        self._pipe.emit(rvi)

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["rvi_win"] = list(self._rvi_win); s["rvi_sum"] = self._rvi_sum
            s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._rvi_win = deque(state.get("rvi_win", []), maxlen=self.period)
            self._rvi_sum = state.get("rvi_sum", 0.0)
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
