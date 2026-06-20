from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class ChandelierExit(Indicator):
    """Chandelier Exit — trailing stop based on ATR."""
    _ind_name   = "CHANDELIER"
    _key_params = ("period", "multiplier")
    def init_depends(self): pass
    def __init__(self, period: int = 22, multiplier: float = 3.0):
        super().__init__(value_extractor=None)
        self.period = period; self.multiplier = multiplier
        self._pm1 = float(period - 1); self._pf = float(period)
        self._hi: deque = deque(maxlen=period); self._lo: deque = deque(maxlen=period)
        self._atr = 0.0; self._prev_close = None; self._count = 0
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        pc = self._prev_close
        tr = raw.high - raw.low
        if pc: tr = max(tr, abs(raw.high - pc), abs(raw.low - pc))
        self._hi.append(raw.high); self._lo.append(raw.low)
        self._prev_close = raw.close
        if self._count <= self.period:
            self._atr += tr
            if self._count == self.period:
                self._atr /= self._pf
                self._pipe.emit(max(self._hi) - self.multiplier * self._atr)
            return
        self._atr = (self._atr * self._pm1 + tr) / self._pf
        self._pipe.emit(max(self._hi) - self.multiplier * self._atr)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["hi"] = list(self._hi); s["lo"] = list(self._lo); s["atr"] = self._atr; s["prev_close"] = self._prev_close; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._hi = deque(state.get("hi", []), maxlen=self.period); self._lo = deque(state.get("lo", []), maxlen=self.period)
            self._atr = state.get("atr", 0.0); self._prev_close = state.get("prev_close"); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.period, key=self.indicator_key())]
