from __future__ import annotations
"""
trex.indic.trend.dema
~~~~~~~~~~~~~~~~~~~~~
Double EMA — eliminates lag by applying EMA twice.

Formula:  DEMA = 2 × EMA₁ − EMA₂
"""

from typing import Callable

from trex.base.indic_key import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType
from trex.indic.trend.ema import EMA


class DEMA(Indicator):
    """Double Exponential Moving Average.

    Output: ``float`` (first emitted after ``2 × period`` ticks)
    """
    _ind_name   = "DEMA"
    _key_params = ("period",)

    def __init__(
        self,
        period:          int                  = 14,
        value_extractor: Callable[..., float] = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period     = period
        self._ve        = value_extractor
        self._ema1_val: float | None = None
        self._ema1 = self._ema2 = None
        self.key: ListenerKey | None = None

    def init_depends(self) -> None:
        api = self._ctx.api
        p = self.period
        self.key = api.ema(self.context_symbol, self.tf, p, self._ve, self._on_ema1)

        self._ema2 = EMA(period=p, value_extractor=None)
        self._ema2.context_key    = f"{self.context_key}:ema2"
        self._ema2.context_symbol = self.context_symbol
        self._ema2.tf             = self.tf
        self._ema2.source_tf      = self.source_tf
        self._ema2.init_depends()
        self._ema2.add_callback_listener(self.context_key, self._on_ema2)

    def dispatch(self) -> None:
        self._ctx.api.de_attach_by_key(self.key)
        del self._ema2

    def _on_ema1(self, val: float) -> None:
        self._ema1_val = val
        if self._ema2:
            self._ema2.add_input_value(val)

    def _on_ema2(self, val: float) -> None:
        if self._ema1_val is not None:
            self.emit(2.0 * self._ema1_val - val)

    def add_input_value(self, raw: object) -> None:
        # EMA₁ is registered in the same CTF and receives input directly.
        pass

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["ema1_val"] = self._ema1_val
            if self._ema2 is not None:
                s["ema2"] = self._ema2.get_state()
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._ema1_val = state.get("ema1_val")
            if self._ema2 is not None and "ema2" in state:
                self._ema2.set_state(state["ema2"])

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.dema(self.period, key=self.indicator_key())]
