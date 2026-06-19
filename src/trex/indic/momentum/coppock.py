from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class Coppock(Indicator):
    """Coppock Curve — WMA of sum of two ROCs."""
    _ind_name   = "COPPOCK"
    _key_params = ("r1", "r2", "wma_period")

    def init_depends(self): pass

    def __init__(self, r1: int = 14, r2: int = 11, wma_period: int = 10,
                 value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.r1 = r1; self.r2 = r2; self.wma_period = wma_period
        max_r = max(r1, r2) + 1
        self._win: deque = deque(maxlen=max_r)
        self._denom = wma_period * (wma_period + 1) / 2.0
        self._wwin: deque = deque(maxlen=wma_period)
        self._wsum = self._psum = 0.0
        self._count = 0

    def _roc(self, r: int) -> float:
        w = list(self._win)
        if len(w) > r and w[-r-1]: return (w[-1] - w[-r-1]) / w[-r-1] * 100.0
        return 0.0

    def _wma(self, val: float) -> float | None:
        if len(self._wwin) == self.wma_period:
            self._wsum -= self._psum; self._psum -= self._wwin[0]
        self._wwin.append(val); self._psum += val
        self._wsum += self.wma_period * val
        if len(self._wwin) < self.wma_period: return None
        ws = sum((i + 1) * v for i, v in enumerate(self._wwin))
        return ws / self._denom

    def _first_calculate(self, value: float, prev):
        self._count += 1
        self._win.append(value)
        if self._count <= max(self.r1, self.r2): return None
        roc_sum = self._roc(self.r1) + self._roc(self.r2)
        return self._wma(roc_sum)

    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)
        roc_sum = self._roc(self.r1) + self._roc(self.r2)
        return self._wma(roc_sum) or 0.0

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win"] = list(self._win); s["wwin"] = list(self._wwin)
            s["wsum"] = self._wsum; s["psum"] = self._psum; s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win = deque(state.get("win", []), maxlen=max(self.r1, self.r2) + 1)
            self._wwin = deque(state.get("wwin", []), maxlen=self.wma_period)
            self._wsum = state.get("wsum", 0.0); self._psum = state.get("psum", 0.0)
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(14, key=self.indicator_key())]
