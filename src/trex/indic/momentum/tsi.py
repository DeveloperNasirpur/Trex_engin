from __future__ import annotations
from typing import Callable
from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class TSI(Indicator):
    """True Strength Index — double-smoothed momentum."""
    _ind_name   = "TSI"
    _key_params = ("r_period", "s_period")

    def init_depends(self): pass

    def __init__(self, r_period: int = 25, s_period: int = 13,
                 value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.r_period = r_period; self.s_period = s_period
        kr = 2.0 / (r_period + 1); ks = 2.0 / (s_period + 1)
        self._kr, self._kr1 = kr, 1.0 - kr
        self._ks, self._ks1 = ks, 1.0 - ks
        self._pc_r = self._apc_r = 0.0
        self._pc_s = self._apc_s = 0.0
        self._count = 0

    def _first_calculate(self, value: float, prev):
        self._count += 1
        if prev is None: return None
        pc = value - prev; apc = abs(pc)
        if self._count == 2:
            self._pc_r = pc; self._apc_r = apc
            self._pc_s = pc; self._apc_s = apc
            return None
        self._pc_r = self._pc_r * self._kr1 + pc * self._kr
        self._apc_r = self._apc_r * self._kr1 + apc * self._kr
        self._pc_s = self._pc_s * self._ks1 + self._pc_r * self._ks
        self._apc_s = self._apc_s * self._ks1 + self._apc_r * self._ks
        if self._count < self.r_period + self.s_period: return None
        return 100.0 * self._pc_s / self._apc_s if self._apc_s else 0.0

    def _calculate_new_value(self, value: float, prev) -> float:
        pc = value - prev; apc = abs(pc)
        self._pc_r = self._pc_r * self._kr1 + pc * self._kr
        self._apc_r = self._apc_r * self._kr1 + apc * self._kr
        self._pc_s = self._pc_s * self._ks1 + self._pc_r * self._ks
        self._apc_s = self._apc_s * self._ks1 + self._apc_r * self._ks
        return 100.0 * self._pc_s / self._apc_s if self._apc_s else 0.0

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["pc_r"] = self._pc_r; s["apc_r"] = self._apc_r
            s["pc_s"] = self._pc_s; s["apc_s"] = self._apc_s
            s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._pc_r = state.get("pc_r", 0.0); self._apc_r = state.get("apc_r", 0.0)
            self._pc_s = state.get("pc_s", 0.0); self._apc_s = state.get("apc_s", 0.0)
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.r_period, key=self.indicator_key())]
