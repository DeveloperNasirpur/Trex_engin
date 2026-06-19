from __future__ import annotations
"""
trex.indic.momentum.trix
~~~~~~~~~~~~~~~~~~~~~~~~~
TRIX — 1-period % rate of change of a triple-smoothed EMA.

Formula:
    EMA₃  = triple-smoothed EMA(close, period)   ← TEMA
    TRIX  = (EMA₃ − prev_EMA₃) / prev_EMA₃ × 100

Architecture
------------
TRIX delegates triple-EMA computation to a TEMA sub-indicator via callback.
Raw input is forwarded to TEMA (which forwards to its own EMA chain).

Data flow::

    raw ──► TEMA(period) ──► (EMA₃ − prev_EMA₃) / prev_EMA₃ × 100 ──► emit
"""

from typing import Callable

from trex.base import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType


class TRIX(Indicator):
    """
    TRIX Oscillator.

    Output: ``float``  (first emitted after ``3 × period + 1`` ticks)
    """
    _ind_name   = "TRIX"
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
        self.period      = period
        self._ve         = value_extractor
        self._prev_e3:   float | None = None
        self._tema = None
        self.keys:ListenerKey|None = None
    def init_depends(self) -> None:
        self.keys = api.tema(self.context_symbol, self.tf,self.period, self._ve, self._on_tema)

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.keys)

    def _on_tema(self, val: float) -> None:
        prev = self._prev_e3
        self._prev_e3 = val
        if prev is not None and prev != 0.0:
            self.emit((val - prev) / prev * 100.0)

    def add_input_value(self, raw: object) -> None:
        self._tema.add_input_value(raw)

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.trix(self.period, key=self.indicator_key())]
