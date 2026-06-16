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

    def series_defs(self):
        from trex.presentation.indicators import Volume
        return [Volume.mfi(self.period)]
