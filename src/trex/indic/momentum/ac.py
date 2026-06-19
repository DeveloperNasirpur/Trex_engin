from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class AC(Indicator):
    """Accelerator/Decelerator Oscillator = AO - SMA(AO, 5)."""
    _ind_name   = "AC"
    _key_params = ()

    def init_depends(self): pass

    def __init__(self):
        super().__init__(value_extractor=None)
        self._w5: deque = deque(maxlen=5)
        self._w34: deque = deque(maxlen=34)
        self._s5 = self._s34 = 0.0
        self._ao_buf: deque = deque(maxlen=5)
        self._ao_sum = 0.0
        self._count = 0

    def add_input_value(self, raw) -> None:
        if isinstance(raw, OHLCV):
            mp = (raw.high + raw.low) / 2.0
            self._count += 1
            if len(self._w5) == 5: self._s5 -= self._w5[0]
            if len(self._w34) == 34: self._s34 -= self._w34[0]
            self._w5.append(mp); self._s5 += mp
            self._w34.append(mp); self._s34 += mp
            self._last_raw = raw
            if self._count >= 34:
                ao = self._s5 / 5.0 - self._s34 / 34.0
                if len(self._ao_buf) == 5: self._ao_sum -= self._ao_buf[0]
                self._ao_buf.append(ao); self._ao_sum += ao
                if self._count >= 38:
                    self._pipe.emit(ao - self._ao_sum / 5.0)

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["w5"] = list(self._w5); s["w34"] = list(self._w34)
            s["s5"] = self._s5; s["s34"] = self._s34
            s["ao_buf"] = list(self._ao_buf); s["ao_sum"] = self._ao_sum
            s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._w5 = deque(state.get("w5", []), maxlen=5)
            self._w34 = deque(state.get("w34", []), maxlen=34)
            self._s5 = state.get("s5", 0.0); self._s34 = state.get("s34", 0.0)
            self._ao_buf = deque(state.get("ao_buf", []), maxlen=5)
            self._ao_sum = state.get("ao_sum", 0.0); self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(14, key=self.indicator_key())]
