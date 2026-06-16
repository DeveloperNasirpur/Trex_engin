from __future__ import annotations
"""
trex.indic.volatility.stddev
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Rolling Standard Deviation — O(1) incremental update via Welford sums.

Variance formula (population):
    var = (Σx² − (Σx)² / n) / n

Hot-path (run phase):
    s  += value − oldest          (rolling sum)
    ss += value² − oldest²        (rolling sum-of-squares)
    return sqrt(ss/n − (s/n)²)   ← zero branch
"""

from collections import deque
from math import sqrt
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class StdDev(Indicator):
    """
    Rolling Standard Deviation (population).

    Output: ``float``  (first emitted after ``period`` ticks)
    """
    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(
        self,
        period:          int      = 20,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period   = period
        self._n_f:    float        = float(period)
        self._win:    deque[float] = deque(maxlen=period)
        self._s:      float        = 0.0   # Σ value
        self._ss:     float        = 0.0   # Σ value²

    # ------------------------------------------------------------------
    # Boot — fill window, seed sums
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._win.append(value)
        self._s  += value
        self._ss += value * value
        if len(self._win) < self.period:
            return None
        mean = self._s / self._n_f
        return sqrt(self._ss / self._n_f - mean * mean)

    # ------------------------------------------------------------------
    # Run — O(1) sliding, zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: float) -> float:
        oldest    = self._win[0]
        self._win.append(value)
        self._s  += value - oldest
        self._ss += value * value - oldest * oldest
        mean      = self._s / self._n_f
        return sqrt(max(self._ss / self._n_f - mean * mean, 0.0))

    def series_defs(self):
        from trex.presentation.indicators import Volatility
        return [Volatility.std_dev(self.period)]
