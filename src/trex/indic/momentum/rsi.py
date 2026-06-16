from __future__ import annotations
"""
trex.indic.momentum.rsi
~~~~~~~~~~~~~~~~~~~~~~~
Relative Strength Index — Wilder's smoothed moving average method.

Matches TradingView RSI output exactly.
"""

from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class Rsi(Indicator):
    """RSI (Relative Strength Index) using Wilder's Smoothed Moving Average.

    Output: ``float`` ∈ [0, 100]

    Seeding: The first ``period`` values are averaged into ``avg_gain`` /
    ``avg_loss`` using a simple mean of absolute changes.
    """

    def init_depends(self) -> None:
        pass

    def __init__(
        self,
        period:          int                    = 14,
        value_extractor: Callable[..., float]   = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor, save_input=False)
        self.period     = period
        self._pm1:      int         = period - 1
        self._period_f: float       = float(period)
        self.avg_gain:  float       = 0.0
        self.avg_loss:  float       = 0.0
        self._buf:      list[float] | None = []

    def _first_calculate(self, value: float, prev: float | None) -> object:
        if self._buf is None:
            d    = value - prev if prev is not None else 0.0
            gain = d  if d > 0.0 else 0.0
            loss = -d if d < 0.0 else 0.0
            pm1  = self._pm1
            p    = self._period_f
            self.avg_gain = (self.avg_gain * pm1 + gain) / p
            self.avg_loss = (self.avg_loss * pm1 + loss) / p
            if self.avg_gain == 0.0 and self.avg_loss == 0.0:
                return None
            return self._rsi()

        self._buf.append(value)
        if len(self._buf) < self.period:
            return None

        gains = losses = 0.0
        buf = self._buf
        for i in range(1, self.period):
            d = buf[i] - buf[i - 1]
            if d > 0.0: gains  +=  d
            else:       losses += -d

        pm1_f = float(self._pm1)
        self.avg_gain = gains  / pm1_f
        self.avg_loss = losses / pm1_f
        self._buf = None

        if self.avg_gain == 0.0 and self.avg_loss == 0.0:
            return None
        return self._rsi()

    def _calculate_new_value(self, value: float, prev: float) -> float:
        d = value - prev
        gain = d  if d > 0.0 else 0.0
        loss = -d if d < 0.0 else 0.0
        self.avg_gain = (self.avg_gain * self._pm1 + gain) / self._period_f
        self.avg_loss = (self.avg_loss * self._pm1 + loss) / self._period_f
        return self._rsi()

    def _rsi(self) -> float:
        if self.avg_loss == 0.0:
            return 100.0
        return round(100.0 - 100.0 / (1.0 + self.avg_gain / self.avg_loss), 2)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period)]
