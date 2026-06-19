from __future__ import annotations
"""
trex.indic.trend.wma
~~~~~~~~~~~~~~~~~~~~
Linearly-Weighted Moving Average — O(1) incremental update.

Performance design
------------------
``_first_calculate`` seeds ``_wsum`` (weighted sum) and ``_psum`` (plain sum)
from the full window.  After that, ``_calculate_new_value`` uses the identity:

    wsum_new = wsum_old − psum_old + period × new_value
    psum_new = psum_old − oldest   + new_value
    WMA      = wsum_new / denom                  denom = period*(period+1)/2

No loop, no conditional — just three additions and one division per tick.
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class WMA(Indicator):
    """
    Linearly-Weighted Moving Average.

    Weights: most-recent bar has weight ``period``, oldest has weight 1.

    Output: ``float``  (first emitted after ``period`` ticks)
    """
    _ind_name   = "WMA"
    _key_params = ("period",)

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
        value_extractor: Callable|None = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor, save_input=False)
        self.period:    int          = period
        self._period_f: float        = float(period)
        self._denom:    float        = period * (period + 1) / 2.0
        self._win:      deque[float] = deque(maxlen=period)
        self._wsum:     float        = 0.0   # Σ(weight_i × value_i)
        self._psum:     float        = 0.0   # Σ(value_i)

    # ------------------------------------------------------------------
    # Boot — fill window, seed running sums
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._win.append(value)
        if len(self._win) < self.period:
            return None
        ws = ps = 0.0
        for i, v in enumerate(self._win, 1):
            ws += i * v
            ps += v
        self._wsum = ws
        self._psum = ps
        return self._wsum / self._denom

    # ------------------------------------------------------------------
    # Run — O(1) update, zero conditionals
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: object) -> float:
        oldest       = self._win[0]
        self._wsum   = self._wsum - self._psum + self._period_f * value
        self._psum   = self._psum - oldest + value
        self._win.append(value)
        return self._wsum / self._denom

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.wma(self.period, key=self.indicator_key())]
