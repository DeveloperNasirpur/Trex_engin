from __future__ import annotations
"""
trex.indic.oscillator.cci
~~~~~~~~~~~~~~~~~~~~~~~~~~
Commodity Channel Index — measures deviation from statistical mean.

Formula:
    TP        = (High + Low + Close) / 3
    SMA_TP    = SMA(TP, period)
    MeanDev   = Σ |TP[i] − SMA_TP| / period
    CCI       = (TP − SMA_TP) / (0.015 × MeanDev)

Hot-path (run phase):
    O(1) SMA update + O(period) mean-deviation scan
    zero explicit branch
"""

from collections import deque

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

_SCALE = 1.0 / 0.015


class CCI(Indicator):
    """
    Commodity Channel Index.

    Receives raw OHLCV bars.
    Output: ``float``  (first emitted after ``period`` ticks)
    """
    _ind_name   = "CCI"
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
        super().__init__(save_input=False)
        self.period   = period
        self._n_f:    float        = float(period)
        self._win:    deque[float] = deque(maxlen=period)
        self._s:      float        = 0.0    # Σ TP

    @staticmethod
    def _tp(ohlcv: OHLCV) -> float:
        return (ohlcv.high + ohlcv.low + ohlcv.close) / 3.0

    def _cci(self, tp: float) -> float:
        sma = self._s / self._n_f
        mean_dev = sum(abs(x - sma) for x in self._win) / self._n_f
        return (tp - sma) / (mean_dev * _SCALE + 1e-10) * _SCALE

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        tp = self._tp(ohlcv)
        self._win.append(tp)
        self._s += tp
        if len(self._win) < self.period:
            return None
        return self._cci(tp)

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        tp         = self._tp(ohlcv)
        self._s   += tp - self._win[0]
        self._win.append(tp)
        return self._cci(tp)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.cci(self.period, key=self.indicator_key())]
