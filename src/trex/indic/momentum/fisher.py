from __future__ import annotations
from collections import deque
from math import log
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class FisherTransform(Indicator):
    """Fisher Transform — converts price to Gaussian distribution."""
    _ind_name   = "FISHER"
    _key_params = ("period",)

    def init_depends(self): pass

    def __init__(self, period: int = 9):
        super().__init__(value_extractor=None)
        self.period = period
        self._hi: deque = deque(maxlen=period)
        self._lo: deque = deque(maxlen=period)
        self._prev_fish = 0.0
        self._count = 0

    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw
        hl2 = (raw.high + raw.low) / 2.0
        self._hi.append(raw.high); self._lo.append(raw.low)
        self._count += 1
        if self._count < self.period: return
        hh = max(self._hi); ll = min(self._lo)
        rng = hh - ll
        val = (hl2 - ll) / rng * 2.0 - 1.0 if rng else 0.0
        val = max(-0.999, min(0.999, val))
        fish = 0.5 * log((1 + val) / (1 - val))
        self._pipe.emit(fish)
        self._prev_fish = fish

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["hi"] = list(self._hi); s["lo"] = list(self._lo)
            s["prev_fish"] = self._prev_fish; s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._hi = deque(state.get("hi", []), maxlen=self.period)
            self._lo = deque(state.get("lo", []), maxlen=self.period)
            self._prev_fish = state.get("prev_fish", 0.0); self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
