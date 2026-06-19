from __future__ import annotations
"""
trex.indic.volatility.keltner
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Keltner Channel — EMA ± (multiplier × ATR).

Formula:
    middle = EMA(close, period)
    upper  = middle + mult × ATR(atr_period)
    lower  = middle − mult × ATR(atr_period)

Architecture
------------
KeltnerChannel uses EMA and ATR sub-indicators via callbacks.

Data flow::

    raw ──► EMA(period)     [shared via ctx] ──┐
                                                ├──► middle ± mult×atr ──► emit KeltnerVal
    raw ──► ATR(atr_period) [shared via ctx] ──┘

Both sub-indicators receive the same raw OHLCV input.
Emission occurs once both values are available for the current bar.
"""

from dataclasses import dataclass
from trex.base import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType


@dataclass(slots=True)
class KeltnerVal:
    """Keltner Channel output."""
    upper:  float
    middle: float
    lower:  float

class KeltnerChannel(Indicator):
    """
    Keltner Channel.

    Receives raw OHLCV bars.
    Output: ``KeltnerVal``

    Parameters
    ----------
    period     : EMA period for middle line  (default 20)
    atr_period : ATR period  (default 10)
    mult       : ATR multiplier  (default 2.0)
    """
    _ind_name   = "KC"
    _key_params = ("period", "atr_period", "mult")

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        sym, tf = self.context_symbol, self.tf
        self.keys.append(api.ema(sym, tf,self.period,ValueExtractor.extract_close, self._on_ema))
        self.keys.append(api.atr(sym, tf,self.period,ValueExtractor.extract_close, self._on_atr))

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.keys)

    def __init__(
        self,
        period:     int   = 20,
        atr_period: int   = 10,
        mult:       float = 2.0,
    ) -> None:
        super().__init__(save_input=False)
        self.keys:list[ListenerKey] = []
        self.period     = period
        self.atr_period = atr_period
        self.mult       = mult
        self._ema_val:   float | None = None
        self._atr_val:   float | None = None
        self._ema_ready: bool = False
        self._atr_ready: bool = False
        self._ema = self._atr = None

    def _on_ema(self, val: float) -> None:
        self._ema_val   = val
        self._ema_ready = True
        if self._atr_ready:
            self._emit_channel()
            self._ema_ready = self._atr_ready = False

    def _on_atr(self, val: float) -> None:
        self._atr_val   = val
        self._atr_ready = True
        if self._ema_ready:
            self._emit_channel()
            self._ema_ready = self._atr_ready = False

    def _emit_channel(self) -> None:
        band = self.mult * self._atr_val
        self.emit(KeltnerVal(upper=self._ema_val + band,
                             middle=self._ema_val,
                             lower=self._ema_val - band))

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return Overlay.keltner(self.period, self.mult,
                               key_prefix=self.indicator_key())

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = self.indicator_key()
        return {
            f"{prefix}_upper":  [Point(time=timestamp, value=value.upper)],
            f"{prefix}_mid":    [Point(time=timestamp, value=value.middle)],
            f"{prefix}_lower":  [Point(time=timestamp, value=value.lower)],
        }
