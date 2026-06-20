from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class EOM(Indicator):
    """Ease of Movement — volume-normalized price change."""
    _ind_name   = "EOM"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14, divisor: float = 1_000_000.0):
        super().__init__(value_extractor=None)
        self.period = period; self.divisor = divisor
        self._win: deque = deque(maxlen=period); self._sum = 0.0
        self._prev_mp = None; self._count = 0
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        mp = (raw.high + raw.low) / 2.0
        if self._prev_mp is not None:
            box_ratio = (raw.volume / self.divisor) / (raw.high - raw.low) if (raw.high - raw.low) else 0.0
            eom1 = (mp - self._prev_mp) / box_ratio if box_ratio else 0.0
            if len(self._win) == self.period: self._sum -= self._win[0]
            self._win.append(eom1); self._sum += eom1
            if self._count >= self.period + 1:
                self._pipe.emit(self._sum / self.period)
        self._prev_mp = mp
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["win"] = list(self._win); s["sum"] = self._sum; s["prev_mp"] = self._prev_mp; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win = deque(state.get("win", []), maxlen=self.period)
            self._sum = state.get("sum", 0.0); self._prev_mp = state.get("prev_mp"); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
