from __future__ import annotations
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class AD(Indicator):
    """Accumulation/Distribution Line."""
    _ind_name   = "AD"
    _key_params = ()
    def init_depends(self): pass
    def __init__(self):
        super().__init__(value_extractor=None)
        self._ad = 0.0
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw
        rng = raw.high - raw.low
        if rng:
            clv = ((raw.close - raw.low) - (raw.high - raw.close)) / rng
            self._ad += clv * raw.volume
        self._pipe.emit(self._ad)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["ad"] = self._ad
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._ad = state.get("ad", 0.0)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(1, key=self.indicator_key())]
