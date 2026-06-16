from __future__ import annotations
"""
trex.indic.volatility.donchian
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Donchian Channel — rolling highest-high / lowest-low over ``period`` bars.

Formula:
    upper  = max(high[0 … period-1])
    lower  = min(low[0  … period-1])
    middle = (upper + lower) / 2

Hot-path (run phase):
    win_high.append(high); win_low.append(low)
    upper  = max(win_high); lower = min(win_low)   ← zero branch (builtin max/min)
"""

from collections import deque
from dataclasses import dataclass

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


@dataclass(slots=True)
class DonchianVal:
    """Donchian Channel output."""
    upper:  float
    middle: float
    lower:  float


class DonchianChannel(Indicator):
    """
    Donchian Channel.

    Receives raw OHLCV bars.
    Output: ``DonchianVal``  (first emitted after ``period`` ticks)
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self, period: int = 20) -> None:
        super().__init__(save_input=False)
        self.period    = period
        self._win_h: deque[float] = deque(maxlen=period)
        self._win_l: deque[float] = deque(maxlen=period)

    def _bands(self) -> DonchianVal:
        upper = max(self._win_h)
        lower = min(self._win_l)
        return DonchianVal(upper=upper, middle=(upper + lower) * 0.5, lower=lower)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        if len(self._win_h) < self.period:
            return None
        return self._bands()

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> DonchianVal:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        return self._bands()

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return Overlay.donchian(self.period, key_prefix=f"dc_{self.period}")

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = f"dc_{self.period}"
        return {
            f"{prefix}_upper":  [Point(time=timestamp, value=value.upper)],
            f"{prefix}_mid":    [Point(time=timestamp, value=value.middle)],
            f"{prefix}_lower":  [Point(time=timestamp, value=value.lower)],
        }
