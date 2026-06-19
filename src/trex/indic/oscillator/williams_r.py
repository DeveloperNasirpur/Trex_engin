from __future__ import annotations
"""
trex.indic.oscillator.williams_r
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Williams %R — momentum oscillator measuring overbought/oversold levels.

Formula:
    %R = (highest_high − close) / (highest_high − lowest_low) × −100

Range: [−100, 0]   (−80 to −100 = oversold, 0 to −20 = overbought)

Hot-path (run phase):
    win_h.append(high); win_l.append(low)
    hh = max(win_h); ll = min(win_l)
    return (hh − close) / (hh − ll + ε) × −100    ← zero branch
"""

from collections import deque

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

_EPS = 1e-10


class WilliamsR(Indicator):
    """
    Williams %R.

    Receives raw OHLCV bars.
    Output: ``float`` ∈ [−100, 0]  (first emitted after ``period`` ticks)
    """
    _ind_name   = "WR"
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
        self.period   = period
        self._win_h: deque[float] = deque(maxlen=period)
        self._win_l: deque[float] = deque(maxlen=period)

    def _wr(self, close: float) -> float:
        hh = max(self._win_h)
        ll = min(self._win_l)
        return (hh - close) / (hh - ll + _EPS) * -100.0

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        if len(self._win_h) < self.period:
            return None
        return self._wr(ohlcv.close)

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        return self._wr(ohlcv.close)

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win_h"] = list(self._win_h)
            s["win_l"] = list(self._win_l)
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win_h = deque(state.get("win_h", []), maxlen=self.period)
            self._win_l = deque(state.get("win_l", []), maxlen=self.period)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.williams_r(self.period, key=self.indicator_key())]
