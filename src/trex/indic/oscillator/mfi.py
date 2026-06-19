from __future__ import annotations
"""
trex.indic.oscillator.mfi
~~~~~~~~~~~~~~~~~~~~~~~~~~
Money Flow Index — volume-weighted RSI variant.

Formula:
    TP       = (High + Low + Close) / 3
    Raw MF   = TP × Volume
    Positive MF if TP ≥ prev_TP, else Negative MF
    MFI      = 100 − 100 / (1 + pos_sum / neg_sum)   over period bars

Hot-path (run phase):
    Uses boolean multiplication (True/False × float) for zero branching:
        is_pos    = tp >= prev_tp                  ← bool (0 or 1)
        pos_flow  = rmf × is_pos
        neg_flow  = rmf × (1 − is_pos)
    O(1) rolling sums — zero explicit branch
"""

from collections import deque

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class MFI(Indicator):
    """
    Money Flow Index.

    Receives raw OHLCV bars.
    Output: ``float`` ∈ [0, 100]  (first emitted after ``period + 1`` ticks)
    """
    _ind_name   = "MFI"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self, period: int = 14) -> None:
        super().__init__(save_input=False)
        self.period      = period
        self._prev_tp:   float         = 0.0
        self._pos_win:   deque[float]  = deque(maxlen=period)
        self._neg_win:   deque[float]  = deque(maxlen=period)
        self._pos_sum:   float         = 0.0
        self._neg_sum:   float         = 0.0

    @staticmethod
    def _tp(ohlcv: OHLCV) -> float:
        return (ohlcv.high + ohlcv.low + ohlcv.close) / 3.0

    def _mfi(self) -> float:
        if self._neg_sum == 0.0:
            return 100.0
        return 100.0 - 100.0 / (1.0 + self._pos_sum / self._neg_sum)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        tp  = self._tp(ohlcv)
        rmf = tp * ohlcv.volume
        if prev is not None:
            is_pos          = tp >= self._prev_tp
            pos             = rmf * is_pos
            neg             = rmf * (1 - is_pos)
            self._pos_sum  += pos
            self._neg_sum  += neg
            self._pos_win.append(pos)
            self._neg_win.append(neg)
        self._prev_tp = tp
        if len(self._pos_win) < self.period:
            return None
        return self._mfi()

    # ------------------------------------------------------------------
    # Run — boolean multiplication, zero explicit branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        tp     = self._tp(ohlcv)
        rmf    = tp * ohlcv.volume
        is_pos = tp >= self._prev_tp
        pos    = rmf * is_pos
        neg    = rmf * (1 - is_pos)

        self._pos_sum += pos - self._pos_win[0]
        self._neg_sum += neg - self._neg_win[0]
        self._pos_win.append(pos)
        self._neg_win.append(neg)
        self._prev_tp = tp
        return self._mfi()

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["prev_tp"]  = self._prev_tp
            s["pos_win"]  = list(self._pos_win)
            s["neg_win"]  = list(self._neg_win)
            s["pos_sum"]  = self._pos_sum
            s["neg_sum"]  = self._neg_sum
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._prev_tp = state.get("prev_tp", 0.0)
            self._pos_win = deque(state.get("pos_win", []), maxlen=self.period)
            self._neg_win = deque(state.get("neg_win", []), maxlen=self.period)
            self._pos_sum = state.get("pos_sum", 0.0)
            self._neg_sum = state.get("neg_sum", 0.0)

    def series_defs(self):
        from trex.presentation.indicators import Volume
        return [Volume.mfi(self.period, key=self.indicator_key())]
