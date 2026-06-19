from __future__ import annotations
"""
trex.indic.trend.vwma
~~~~~~~~~~~~~~~~~~~~~
Volume-Weighted Moving Average — gives more weight to high-volume candles.

Formula:  VWMA = Σ(close × volume) / Σ(volume)   over period bars

Hot-path (run phase): O(1) rolling update using two running sums:
    pv_sum += close × volume − oldest_close × oldest_volume
    v_sum  += volume         − oldest_volume
    return pv_sum / v_sum                           ← zero branch
"""

from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class VWMA(Indicator):
    """
    Volume-Weighted Moving Average.

    Receives raw OHLCV bars (no value extractor).
    Output: ``float``  (first emitted after ``period`` ticks)
    """
    _ind_name   = "VWMA"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self, period: int = 20) -> None:
        # No extractor: receives OHLCV objects directly
        super().__init__(save_input=False)
        self.period       = period
        self._win_close:  deque[float] = deque(maxlen=period)
        self._win_volume: deque[float] = deque(maxlen=period)
        self._pv_sum: float = 0.0   # Σ price × volume
        self._v_sum:  float = 0.0   # Σ volume

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        pv = ohlcv.close * ohlcv.volume
        self._pv_sum         += pv
        self._v_sum          += ohlcv.volume
        self._win_close.append(ohlcv.close)
        self._win_volume.append(ohlcv.volume)
        if len(self._win_close) < self.period:
            return None
        return self._pv_sum / self._v_sum

    # ------------------------------------------------------------------
    # Run — O(1) sliding update, zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        old_close  = self._win_close[0]
        old_volume = self._win_volume[0]
        self._pv_sum += ohlcv.close * ohlcv.volume - old_close * old_volume
        self._v_sum  += ohlcv.volume - old_volume
        self._win_close.append(ohlcv.close)
        self._win_volume.append(ohlcv.volume)
        return self._pv_sum / self._v_sum

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.vwma(self.period, key=self.indicator_key())]
