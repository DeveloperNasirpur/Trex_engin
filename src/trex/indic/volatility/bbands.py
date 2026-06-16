from __future__ import annotations
"""
trex.indic.volatility.bbands
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Bollinger Bands — SMA ± (k × rolling StdDev).

Formula:
    middle = SMA(close, period)
    upper  = middle + mult × StdDev(close, period)
    lower  = middle − mult × StdDev(close, period)

Architecture
------------
BollingerBands uses SMA and StdDev sub-indicators via callbacks.

Data flow::

    raw ──► SMA(period)    [shared via ctx] ──┐
                                               ├──► middle ± mult×stddev ──► emit BBVal
    raw ──► StdDev(period) [shared via ctx] ──┘

Both SMA and StdDev receive the same raw input.  Emission occurs once
both values are available for the current bar (per-tick toggle).
"""
from dataclasses import dataclass
from typing import Callable
from trex.base import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType


@dataclass(slots=True)
class BBVal:
    """Bollinger Bands output."""
    upper:  float
    middle: float
    lower:  float


class BollingerBands(Indicator):
    """
    Bollinger Bands.

    Output: ``BBVal``  (first emitted after ``period`` ticks)

    Parameters
    ----------
    period : look-back window  (default 20)
    mult   : standard-deviation multiplier  (default 2.0)
    """
    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        api = self._ctx.api
        sym, tf, ve, p = self.context_symbol, self.tf, self._ve, self.period
        self.keys.append(api.sma(sym, tf, p, ve, self._on_sma))
        self.keys.append(api.stddev(sym, tf, p, ve, self._on_std))

    def dispatch(self) -> None:
        self._ctx.api.de_attach_by_key(self.keys)

    def __init__(
        self,
        period:          int      = 20,
        mult:            float    = 2.0,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period    = period
        self.mult      = mult
        self._ve       = value_extractor
        self._sma_val: float | None = None
        self._std_val: float | None = None
        self._sma_ready: bool = False
        self._std_ready: bool = False
        self.keys:list[ListenerKey] = []

    def _on_sma(self, val: float) -> None:
        self._sma_val   = val
        self._sma_ready = True
        if self._std_ready:
            self._emit_bands()
            self._sma_ready = self._std_ready = False

    def _on_std(self, val: float) -> None:
        self._std_val   = val
        self._std_ready = True
        if self._sma_ready:
            self._emit_bands()
            self._sma_ready = self._std_ready = False

    def _emit_bands(self) -> None:
        band = self.mult * self._std_val
        self.emit(BBVal(upper=self._sma_val + band,
                        middle=self._sma_val,
                        lower=self._sma_val - band))

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return Overlay.bollinger(self.period, self.mult,
                                 key_prefix=f"bb_{self.period}")

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = f"bb_{self.period}"
        return {
            f"{prefix}_upper":  [Point(time=timestamp, value=value.upper)],
            f"{prefix}_mid":    [Point(time=timestamp, value=value.middle)],
            f"{prefix}_lower":  [Point(time=timestamp, value=value.lower)],
        }
