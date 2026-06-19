from __future__ import annotations
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class ForceIndex(Indicator):
    """Elder Force Index — price change * volume, EMA-smoothed."""
    _ind_name   = "FORCE"
    _key_params = ("period",)

    def init_depends(self): pass

    def __init__(self, period: int = 13):
        super().__init__(value_extractor=None)
        self.period = period
        k = 2.0 / (period + 1)
        self._k, self._k1 = k, 1.0 - k
        self._ema = 0.0; self._prev_close = None; self._count = 0

    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        if self._prev_close is None: self._prev_close = raw.close; return
        fi = (raw.close - self._prev_close) * raw.volume
        self._prev_close = raw.close
        if self._count == 2: self._ema = fi
        else: self._ema = self._ema * self._k1 + fi * self._k
        if self._count >= self.period + 1:
            self._pipe.emit(self._ema)

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["ema"] = self._ema; s["prev_close"] = self._prev_close; s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._ema = state.get("ema", 0.0)
            self._prev_close = state.get("prev_close")
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period, key=self.indicator_key())]
