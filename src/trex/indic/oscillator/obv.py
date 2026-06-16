from __future__ import annotations
"""
trex.indic.oscillator.obv
~~~~~~~~~~~~~~~~~~~~~~~~~~
On Balance Volume — cumulative volume with direction from price change.

Formula:
    sign = +1 if close ≥ prev_close, −1 if close < prev_close
    OBV  = cumulative Σ(sign × volume)

Hot-path (run phase):
    sign = (close > prev_close) − (close < prev_close)   ← boolean subtraction
    OBV += sign × volume                                  ← zero explicit branch
"""

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class OBV(Indicator):
    """
    On Balance Volume.

    Receives raw OHLCV bars.
    Output: ``float``  (first emitted after 2 ticks)
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self) -> None:
        super().__init__(warmup=1, save_input=False)
        self._obv: float = 0.0

    # ------------------------------------------------------------------
    # Boot — one-shot for the first real bar
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        sign       = (ohlcv.close > prev.close) - (ohlcv.close < prev.close)
        self._obv += sign * ohlcv.volume
        return self._obv

    # ------------------------------------------------------------------
    # Run — boolean subtraction, zero explicit branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        sign       = (ohlcv.close > prev.close) - (ohlcv.close < prev.close)
        self._obv += sign * ohlcv.volume
        return self._obv

    def series_defs(self):
        from trex.presentation.indicators import Volume
        return [Volume.obv()]
