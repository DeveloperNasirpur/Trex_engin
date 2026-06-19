from __future__ import annotations
"""
trex.indic.trend.hma
~~~~~~~~~~~~~~~~~~~~
Hull Moving Average: WMA(2·WMA(n/2) − WMA(n), √n)
"""

from math import isqrt
from typing import Callable

from trex.base.indic_key import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType
from trex.indic.trend.wma import WMA


class HMA(Indicator):
    """Hull Moving Average.

    Output: ``float`` (first emitted after enough bars to seed all three WMAs)
    """
    _ind_name   = "HMA"
    _key_params = ("period",)

    def __init__(
        self,
        period:          int                  = 10,
        value_extractor: Callable[..., float] = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor, warmup=period)
        self.period = period
        self._ve    = value_extractor
        self._wma_full = self._wma_half = self._wma_sqrt = None
        self.keys:  list[ListenerKey] = []

    def init_depends(self) -> None:
        p = self.period
        self.keys.append(api.wma(self.context_symbol, self.tf, p,         self._ve, self._on_full))
        self.keys.append(api.wma(self.context_symbol, self.tf, p // 2,    self._ve, self._on_half))

        sqrt_p = isqrt(p)
        self._wma_sqrt = WMA(period=sqrt_p, value_extractor=None)
        self._wma_sqrt.context_key    = f"{self.context_key}:wma_sqrt"
        self._wma_sqrt.context_symbol = self.context_symbol
        self._wma_sqrt.tf             = self.tf
        self._wma_sqrt.source_tf      = self.source_tf
        self._wma_sqrt.init_depends()
        self._wma_sqrt.add_callback_listener(self.context_key, self._on_sqrt)

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.keys)
        del self._wma_sqrt

    def _on_full(self, _: float) -> None:
        pass

    def _on_half(self, half_val: float) -> None:
        full_val = self._wma_full.prev_output if self._wma_full else None
        if full_val is not None and self._wma_sqrt:
            self._wma_sqrt.add_input_value(2.0 * half_val - full_val)

    def _on_sqrt(self, val: float) -> None:
        self.emit(val)

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.hma(self.period, key=self.indicator_key())]
