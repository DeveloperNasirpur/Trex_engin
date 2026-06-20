from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class CMF(Indicator):
    """Chaikin Money Flow."""
    _ind_name   = "CMF"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 20):
        super().__init__(value_extractor=None)
        self.period = period
        self._mfv: deque = deque(maxlen=period)
        self._vol: deque = deque(maxlen=period)
        self._mfv_sum = self._vol_sum = 0.0
        self._count = 0
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        rng = raw.high - raw.low
        mfv = ((raw.close - raw.low) - (raw.high - raw.close)) / rng * raw.volume if rng else 0.0
        if len(self._mfv) == self.period: self._mfv_sum -= self._mfv[0]; self._vol_sum -= self._vol[0]
        self._mfv.append(mfv); self._vol.append(raw.volume)
        self._mfv_sum += mfv; self._vol_sum += raw.volume
        if self._count >= self.period and self._vol_sum:
            self._pipe.emit(self._mfv_sum / self._vol_sum)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["mfv"] = list(self._mfv); s["vol"] = list(self._vol); s["mfv_sum"] = self._mfv_sum; s["vol_sum"] = self._vol_sum; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._mfv = deque(state.get("mfv", []), maxlen=self.period)
            self._vol = deque(state.get("vol", []), maxlen=self.period)
            self._mfv_sum = state.get("mfv_sum", 0.0); self._vol_sum = state.get("vol_sum", 0.0); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
