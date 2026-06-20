from __future__ import annotations
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class PVT(Indicator):
    """Price Volume Trend."""
    _ind_name   = "PVT"
    _key_params = ()
    def init_depends(self): pass
    def __init__(self):
        super().__init__(value_extractor=None)
        self._pvt = 0.0; self._prev_close = None
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw
        if self._prev_close:
            self._pvt += raw.volume * (raw.close - self._prev_close) / self._prev_close
        self._prev_close = raw.close
        self._pipe.emit(self._pvt)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["pvt"] = self._pvt; s["prev_close"] = self._prev_close
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._pvt = state.get("pvt", 0.0); self._prev_close = state.get("prev_close")
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(1, key=self.indicator_key())]
