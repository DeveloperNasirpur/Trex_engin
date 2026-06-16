from __future__ import annotations
"""
trex.indic.hybrid.psar
~~~~~~~~~~~~~~~~~~~~~~~
Parabolic SAR — J. Welles Wilder's trailing stop-and-reverse system.

State machine (uptrend / downtrend) via function pointer.
The only ``if`` in the run phase is the trend-reversal check, which
occurs rarely and triggers a one-time pointer rebind.

Formula (uptrend):
    SAR  = prev_SAR + AF × (EP − prev_SAR)
    SAR  = min(SAR, low[-1], low[-2])          ← floor at recent lows
    EP   = max(EP, high)                        ← track new highs
    AF   = min(AF + step, max_af)  when new EP is set
    Reverse if  low < SAR

Formula (downtrend): symmetric with high/low swapped.

Hot-path (steady trend): one comparison + SAR update arithmetic.
"""

from dataclasses import dataclass
from typing import Callable

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


@dataclass(slots=True)
class PSARVal:
    """Parabolic SAR output."""
    sar:        float
    is_uptrend: bool
    af:         float
    ep:         float


class ParabolicSAR(Indicator):
    """
    Parabolic Stop and Reverse (SAR).

    Receives raw OHLCV bars (warmup=2 to prime prev low/high pair).
    Output: ``PSARVal``  (first emitted after 3 ticks)

    Parameters
    ----------
    step   : AF increment  (default 0.02)
    max_af : Maximum AF    (default 0.20)
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self, step: float = 0.02, max_af: float = 0.20) -> None:
        super().__init__(warmup=2, save_input=True, max_input=3)
        self.step   = step
        self.max_af = max_af
        self._sar:  float = 0.0
        self._ep:   float = 0.0
        self._af:   float = step
        self._prev_low:  float = 0.0
        self._prev2_low: float = 0.0
        self._prev_high:  float = 0.0
        self._prev2_high: float = 0.0
        # Function pointer
        self._trend_step: Callable = self._uptrend_step

    # ------------------------------------------------------------------
    # Trend step functions
    # ------------------------------------------------------------------
    def _uptrend_step(self, ohlcv: OHLCV) -> PSARVal:
        self._sar = self._sar + self._af * (self._ep - self._sar)
        self._sar = min(self._sar, self._prev_low, self._prev2_low)
        if ohlcv.high > self._ep:
            self._ep  = ohlcv.high
            self._af  = min(self._af + self.step, self.max_af)
        self._prev2_low = self._prev_low
        self._prev_low  = ohlcv.low
        if ohlcv.low < self._sar:           # ← one if: trend reversal
            self._sar        = self._ep
            self._ep         = ohlcv.low
            self._af         = self.step
            self._trend_step = self._downtrend_step
            return PSARVal(sar=self._sar, is_uptrend=False, af=self._af, ep=self._ep)
        return PSARVal(sar=self._sar, is_uptrend=True, af=self._af, ep=self._ep)

    def _downtrend_step(self, ohlcv: OHLCV) -> PSARVal:
        self._sar = self._sar + self._af * (self._ep - self._sar)
        self._sar = max(self._sar, self._prev_high, self._prev2_high)
        if ohlcv.low < self._ep:
            self._ep  = ohlcv.low
            self._af  = min(self._af + self.step, self.max_af)
        self._prev2_high = self._prev_high
        self._prev_high  = ohlcv.high
        if ohlcv.high > self._sar:          # ← one if: trend reversal
            self._sar        = self._ep
            self._ep         = ohlcv.high
            self._af         = self.step
            self._trend_step = self._uptrend_step
            return PSARVal(sar=self._sar, is_uptrend=True, af=self._af, ep=self._ep)
        return PSARVal(sar=self._sar, is_uptrend=False, af=self._af, ep=self._ep)

    # ------------------------------------------------------------------
    # Boot — initialize SAR from first three candles
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV) -> object:
        # input_values has the three warmup+boot candles
        bars = list(self.input_values)
        if len(bars) < 3:
            return None
        c1, c2, c3 = bars[-3], bars[-2], bars[-1]
        if c3.close > c1.close:             # start in uptrend
            self._ep          = c3.high
            self._sar         = c1.low
            self._prev_low    = c2.low
            self._prev2_low   = c1.low
            self._trend_step  = self._uptrend_step
        else:                               # start in downtrend
            self._ep          = c3.low
            self._sar         = c1.high
            self._prev_high   = c2.high
            self._prev2_high  = c1.high
            self._trend_step  = self._downtrend_step
        self._af = self.step
        return PSARVal(sar=self._sar, is_uptrend=(c3.close > c1.close),
                       af=self._af, ep=self._ep)

    # ------------------------------------------------------------------
    # Run — one if only on reversal (function pointer dispatch)
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> PSARVal:
        return self._trend_step(ohlcv)

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.psar(self.step, self.max_af)]

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        color = "#089981" if value.is_uptrend else "#F23645"
        return {"psar": [Point(time=timestamp, value=value.sar, color=color)]}
