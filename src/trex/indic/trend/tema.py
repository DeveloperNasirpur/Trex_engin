from __future__ import annotations
"""
trex.indic.trend.tema
~~~~~~~~~~~~~~~~~~~~~
Triple EMA — maximum lag reduction with three cascaded EMAs.

Formula:  TEMA = 3 × EMA₁ − 3 × EMA₂ + EMA₃

Architecture
------------
TEMA uses three cascaded EMA sub-indicators via callbacks.

Data flow::

    raw ──► EMA₁(period) [shared via ctx]
                 └──► EMA₂(period) [private float EMA]
                              └──► EMA₃(period) [private float EMA]
                                         └──► 3×EMA₁ − 3×EMA₂ + EMA₃ ──► emit

EMA₁ is shared via ctx.  EMA₂ and EMA₃ are private and must NOT be
registered in CTF.  Raw input forwarded to EMA₁ for standalone use.
"""

from typing import Callable

from trex.base import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType
from trex.indic.trend.ema import EMA


class TEMA(Indicator):
    """
    Triple Exponential Moving Average.

    Output: ``float``  (first emitted after ``3 × period`` ticks)
    """
    _ind_name   = "TEMA"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def __init__(
        self,
        period:          int      = 14,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period     = period
        self._ve        = value_extractor
        self._ema1_val: float | None = None
        self._ema2_val: float | None = None
        self._ema1 = self._ema2 = self._ema3 = None
        self.key:ListenerKey|None = None

    def init_depends(self) -> None:
        sym, tf, ve, p = self.context_symbol, self.tf, self._ve, self.period

        self.key = api.ema(sym, tf, p,ve, self._on_ema1)

        self._ema2 = EMA(period=p, value_extractor=None)
        self._ema2.context_key = f"{self.context_key}:ema2"
        self._ema2.context_symbol = sym
        self._ema2.tf = tf
        self._ema2.source_tf = self.source_tf
        self._ema2.init_depends()

        self._ema3 = EMA(period=p, value_extractor=None)
        self._ema3.context_key = f"{self.context_key}:ema3"
        self._ema3.context_symbol = sym
        self._ema3.tf = tf
        self._ema3.source_tf = self.source_tf
        self._ema3.init_depends()

        self._ema2.add_callback_listener(self.context_key, self._on_ema2)
        self._ema3.add_callback_listener(self.context_key, self._on_ema3)

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.key)
        del self._ema2, self._ema3

    def _on_ema1(self, val: float) -> None:
        self._ema1_val = val
        self._ema2.add_input_value(val)

    def _on_ema2(self, val: float) -> None:
        self._ema2_val = val
        self._ema3.add_input_value(val)

    def _on_ema3(self, val: float) -> None:
        e1 = self._ema1_val
        e2 = self._ema2_val
        if e1 is not None and e2 is not None:
            self.emit(3.0 * e1 - 3.0 * e2 + val)

    def add_input_value(self, raw: object) -> None:
        self._ema1.add_input_value(raw)

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.tema(self.period, key=self.indicator_key())]
