from __future__ import annotations
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class VO(Indicator):
    """Volume Oscillator — fast/slow EMA of volume."""
    _ind_name   = "VO"
    _key_params = ("fast_period", "slow_period")
    def init_depends(self): pass
    def __init__(self, fast_period: int = 5, slow_period: int = 10):
        super().__init__(value_extractor=None)
        self.fast_period = fast_period; self.slow_period = slow_period
        kf = 2.0/(fast_period+1); ks = 2.0/(slow_period+1)
        self._kf, self._kf1 = kf, 1-kf; self._ks, self._ks1 = ks, 1-ks
        self._ef = self._es = 0.0; self._count = 0
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        vol = raw.volume
        if self._count == 1: self._ef = self._es = vol
        else: self._ef = self._ef * self._kf1 + vol * self._kf; self._es = self._es * self._ks1 + vol * self._ks
        if self._count >= self.slow_period and self._es:
            self._pipe.emit((self._ef - self._es) / self._es * 100.0)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["ef"] = self._ef; s["es"] = self._es; s["count"] = self._count
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._ef = state.get("ef", 0.0); self._es = state.get("es", 0.0); self._count = state.get("count", 0)
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.slow_period, key=self.indicator_key())]
