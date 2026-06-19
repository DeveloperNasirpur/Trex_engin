from __future__ import annotations
from collections import deque
from math import log10
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class CHOP(Indicator):
    """Choppiness Index — measures market trendiness vs choppiness."""
    _ind_name   = "CHOP"
    _key_params = ("period",)

    def init_depends(self): pass

    def __init__(self, period: int = 14):
        super().__init__(value_extractor=None)
        self.period = period
        self._log_p = log10(period)
        self._atr1: deque = deque(maxlen=period)
        self._hi: deque   = deque(maxlen=period)
        self._lo: deque   = deque(maxlen=period)
        self._prev_close  = None; self._count = 0

    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        pc = self._prev_close
        if pc is not None:
            tr = max(raw.high - raw.low, abs(raw.high - pc), abs(raw.low - pc))
            self._atr1.append(tr)
        self._hi.append(raw.high); self._lo.append(raw.low)
        self._prev_close = raw.close
        if self._count <= self.period: return
        atr_sum = sum(self._atr1)
        hh = max(self._hi); ll = min(self._lo)
        rng = hh - ll
        if rng and atr_sum:
            chop = 100.0 * log10(atr_sum / rng) / self._log_p
            self._pipe.emit(round(chop, 2))

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["atr1"] = list(self._atr1); s["hi"] = list(self._hi); s["lo"] = list(self._lo)
            s["prev_close"] = self._prev_close; s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._atr1 = deque(state.get("atr1", []), maxlen=self.period)
            self._hi   = deque(state.get("hi", []),   maxlen=self.period)
            self._lo   = deque(state.get("lo", []),   maxlen=self.period)
            self._prev_close = state.get("prev_close"); self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
