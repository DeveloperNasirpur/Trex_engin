from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class KST(Indicator):
    """Know Sure Thing — weighted sum of smoothed ROCs."""
    _ind_name   = "KST"
    _key_params = ("r1", "r2", "r3", "r4", "s1", "s2", "s3", "s4")

    def init_depends(self): pass

    def __init__(self, r1=10, r2=13, r3=14, r4=15, s1=10, s2=13, s3=14, s4=15,
                 signal: int = 9,
                 value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.r1=r1; self.r2=r2; self.r3=r3; self.r4=r4
        self.s1=s1; self.s2=s2; self.s3=s3; self.s4=s4
        self.signal = signal
        max_r = max(r1, r2, r3, r4) + 1
        self._win: deque = deque(maxlen=max_r)
        self._rw = [deque(maxlen=s) for s in [s1, s2, s3, s4]]
        self._rs = [0.0] * 4
        self._count = 0
        self._rs_periods = [r1, r2, r3, r4]
        self._sm_periods = [s1, s2, s3, s4]

    def _roc(self, r: int) -> float | None:
        w = list(self._win)
        if len(w) > r: return (w[-1] - w[-r-1]) / w[-r-1] * 100.0 if w[-r-1] else 0.0
        return None

    def _first_calculate(self, value: float, prev):
        self._count += 1
        self._win.append(value)
        kst = 0.0
        all_ready = True
        for i, (r, sp) in enumerate(zip(self._rs_periods, self._sm_periods)):
            roc = self._roc(r)
            if roc is None: all_ready = False; continue
            if len(self._rw[i]) == sp: self._rs[i] -= self._rw[i][0]
            self._rw[i].append(roc); self._rs[i] += roc
            if len(self._rw[i]) < sp: all_ready = False
            else: kst += (self._rs[i] / sp) * (i + 1)
        if not all_ready: return None
        return kst

    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)
        kst = 0.0
        for i, (r, sp) in enumerate(zip(self._rs_periods, self._sm_periods)):
            roc = self._roc(r)
            if roc is None: roc = 0.0
            if len(self._rw[i]) == sp: self._rs[i] -= self._rw[i][0]
            self._rw[i].append(roc); self._rs[i] += roc
            kst += (self._rs[i] / sp) * (i + 1)
        return kst

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win"] = list(self._win); s["count"] = self._count
            s["rs"] = list(self._rs)
            s["rw"] = [list(q) for q in self._rw]
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win = deque(state.get("win", []), maxlen=max(self._rs_periods) + 1)
            self._rs = state.get("rs", [0.0] * 4)
            self._rw = [deque(q, maxlen=sp) for q, sp in zip(state.get("rw", [[]] * 4), self._sm_periods)]
            self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(14, key=self.indicator_key())]
