from __future__ import annotations
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

class NATR(Indicator):
    """Normalized Average True Range = ATR/close * 100."""
    _ind_name   = "NATR"
    _key_params = ("period",)
    def init_depends(self): pass
    def __init__(self, period: int = 14):
        super().__init__(value_extractor=None)
        self.period = period
        self._pm1 = float(period - 1); self._pf = float(period)
        self._tr_sum = 0.0; self._count = 0
        self._prev_close = None
    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        pc = self._prev_close
        tr = raw.high - raw.low
        if pc: tr = max(tr, abs(raw.high - pc), abs(raw.low - pc))
        self._prev_close = raw.close
        if self._count <= self.period:
            self._tr_sum += tr
            if self._count == self.period and raw.close:
                self._pipe.emit(self._tr_sum / self._pf / raw.close * 100.0)
            return
        atr = (self._pipe.prev_output * raw.close / 100.0 * self._pm1 + tr) / self._pf
        if raw.close: self._pipe.emit(atr / raw.close * 100.0)
    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None
    def get_state(self) -> dict:
        s = super().get_state()
        if s: s["tr_sum"] = self._tr_sum; s["count"] = self._count; s["prev_close"] = self._prev_close
        return s
    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state: self._tr_sum = state.get("tr_sum", 0.0); self._count = state.get("count", 0); self._prev_close = state.get("prev_close")
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
