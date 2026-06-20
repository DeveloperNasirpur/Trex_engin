from __future__ import annotations
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class PVI(Indicator):
    """Positive Volume Index — price change on increasing volume days."""
    _ind_name   = "PVI"
    _key_params = ()
    def init_depends(self): pass
    def __init__(self):
        super().__init__(value_extractor=None)
        self._pvi = 1000.0; self._prev_close = self._prev_vol = None
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw
        if self._prev_close is not None and self._prev_vol is not None:
            if raw.volume > self._prev_vol and self._prev_close:
                self._pvi += (raw.close - self._prev_close) / self._prev_close * self._pvi
        self._prev_close = raw.close; self._prev_vol = raw.volume
        self._pipe.emit(self._pvi)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["pvi"] = self._pvi; s["prev_close"] = self._prev_close; s["prev_vol"] = self._prev_vol
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._pvi = state.get("pvi", 1000.0); self._prev_close = state.get("prev_close"); self._prev_vol = state.get("prev_vol")
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(1, key=self.indicator_key())]
