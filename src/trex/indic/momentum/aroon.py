from __future__ import annotations
"""
trex.indic.momentum.aroon
~~~~~~~~~~~~~~~~~~~~~~~~~~
Aroon — measures how recently highest-high / lowest-low occurred.

Formula:
    Aroon Up   = ((period − bars_since_highest_high) / period) × 100
    Aroon Down = ((period − bars_since_lowest_low)   / period) × 100
    Oscillator = Aroon Up − Aroon Down

Hot-path (run phase):
    win_h.append(high); win_l.append(low)
    idx_h = argmax(win_h);  idx_l = argmin(win_l)   ← builtin, zero explicit if
    up    = (period − (period − idx_h)) / period × 100
    down  = (period − (period − idx_l)) / period × 100
"""

from collections import deque
from dataclasses import dataclass

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


@dataclass(slots=True)
class AroonVal:
    """Aroon output."""
    up:         float
    down:       float
    oscillator: float


class Aroon(Indicator):
    """
    Aroon Indicator.

    Receives raw OHLCV bars.
    Output: ``AroonVal``  (first emitted after ``period + 1`` ticks)
    """
    _ind_name   = "AROON"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self, period: int = 25) -> None:
        super().__init__(save_input=False)
        self.period    = period
        self._factor:  float = 100.0 / period
        self._win_h: deque[float] = deque(maxlen=period + 1)
        self._win_l: deque[float] = deque(maxlen=period + 1)

    def _aroon(self) -> AroonVal:
        wh = list(self._win_h)
        wl = list(self._win_l)
        n  = len(wh)
        # index of max/min (most-recent = rightmost = highest index)
        idx_h  = max(range(n), key=wh.__getitem__)
        idx_l  = min(range(n), key=wl.__getitem__)
        up     = idx_h   * self._factor
        down   = idx_l   * self._factor
        return AroonVal(up=up, down=down, oscillator=up - down)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        if len(self._win_h) <= self.period:
            return None
        return self._aroon()

    # ------------------------------------------------------------------
    # Run — zero explicit branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> AroonVal:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        return self._aroon()

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return Oscillator.aroon(self.period, key_prefix=self.indicator_key())

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = self.indicator_key()
        return {
            f"{prefix}_up":   [Point(time=timestamp, value=value.up)],
            f"{prefix}_down": [Point(time=timestamp, value=value.down)],
        }
