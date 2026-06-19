from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class Vortex(Indicator):
    """Vortex Indicator — VI+ and VI-."""
    _ind_name   = "VORTEX"
    _key_params = ("period",)

    def init_depends(self): pass

    def __init__(self, period: int = 14):
        super().__init__(value_extractor=None)
        self.period = period
        self._vm_plus: deque  = deque(maxlen=period)
        self._vm_minus: deque = deque(maxlen=period)
        self._tr: deque       = deque(maxlen=period)
        self._prev_high = self._prev_low = self._prev_close = None
        self._count = 0

    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw
        self._count += 1
        if self._prev_close is not None:
            vmp = abs(raw.high - self._prev_low)
            vmm = abs(raw.low  - self._prev_high)
            tr  = max(raw.high - raw.low,
                      abs(raw.high - self._prev_close),
                      abs(raw.low  - self._prev_close))
            self._vm_plus.append(vmp); self._vm_minus.append(vmm); self._tr.append(tr)
            if self._count > self.period:
                tr_sum = sum(self._tr)
                if tr_sum:
                    self._pipe.emit(sum(self._vm_plus) / tr_sum)
        self._prev_high = raw.high; self._prev_low = raw.low; self._prev_close = raw.close

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["vm_plus"] = list(self._vm_plus); s["vm_minus"] = list(self._vm_minus)
            s["tr"] = list(self._tr)
            s["prev_high"] = self._prev_high; s["prev_low"] = self._prev_low
            s["prev_close"] = self._prev_close
            s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._vm_plus  = deque(state.get("vm_plus", []),  maxlen=self.period)
            self._vm_minus = deque(state.get("vm_minus", []), maxlen=self.period)
            self._tr       = deque(state.get("tr", []),       maxlen=self.period)
            self._prev_high = state.get("prev_high")
            self._prev_low = state.get("prev_low")
            self._prev_close = state.get("prev_close")
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        key = self.indicator_key()
        return [
            Oscillator.rsi(self.period, key=f"{key}_plus"),
            Oscillator.rsi(self.period, key=f"{key}_minus"),
        ]
