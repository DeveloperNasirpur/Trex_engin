from __future__ import annotations
"""
trex.indic.trend.ema
~~~~~~~~~~~~~~~~~~~~
Exponential Moving Average — SMA-seeded, multiplier = 2/(period+1).

Matches TradingView EMA output exactly.

Hot-path (run phase):
    prev_output × k1 + value × k      ← two multiplications + one addition, zero branch
"""

from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class EMA(Indicator):
    """
    Exponential Moving Average.

    Output: ``float``  (first emitted after ``period`` ticks)

    Seeding
    -------
    First ``period`` values are averaged (SMA) to seed the running EMA —
    identical to TradingView's behavior.
    """
    _ind_name   = "EMA"
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
        period:          int      = 14,
        value_extractor: Callable|None = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period   = period
        k             = 2.0 / (period + 1.0)
        self._k:  float            = k
        self._k1: float            = 1.0 - k
        self._buf: Optional[list]  = []

    # ------------------------------------------------------------------
    # Boot — accumulate period values, seed EMA
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._buf.append(value)
        if len(self._buf) < self.period:
            return None
        seed      = sum(self._buf) / self.period
        self._buf = None          # sentinel: seeding done
        return seed

    # ------------------------------------------------------------------
    # Run — pure EMA, zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: float) -> float:
        return self._pipe.prev_output * self._k1 + value * self._k

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["buf_cleared"] = True
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._buf = None

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.ema(self.period, key=self.indicator_key())]
