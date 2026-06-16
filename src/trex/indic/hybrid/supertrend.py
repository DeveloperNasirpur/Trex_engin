from __future__ import annotations
"""
trex.indic.hybrid.supertrend
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Supertrend — ATR-based trend-following band indicator.

Formula:
    hl2         = (High + Low) / 2
    basic_upper = hl2 + mult × ATR
    basic_lower = hl2 − mult × ATR
    final_upper = min(basic_upper, prev_upper)  if prev_close ≤ prev_upper else basic_upper
    final_lower = max(basic_lower, prev_lower)  if prev_close ≥ prev_lower else basic_lower
    direction:  close > prev_supertrend → uptrend  → supertrend = final_lower
                else downtrend → supertrend = final_upper

Architecture
------------
Supertrend uses ATR sub-indicator for True Range computation.
The ATR callback fires once per bar, providing the current ATR value.
Supertrend also needs the raw OHLCV for hl2/close calculations.

Design: add_input_value forwards OHLCV to ATR's Tr sub-indicator (standalone)
or ATR is fed via CTF (production).  ATR callback fires first (Tr → ATR user),
then Supertrend's own user processes the OHLCV with the already-updated ATR.

State machine via function pointer (_trend_step).
"""

from dataclasses import dataclass
from typing import Callable

from trex.engine.indicator import Indicator
from trex.base import ListenerKey
from trex.base.ohlcv import OHLCV


@dataclass(slots=True)
class SupertrendVal:
    """Supertrend output."""
    value:      float
    is_uptrend: bool


class Supertrend(Indicator):
    """
    Supertrend.

    Receives raw OHLCV bars.
    Output: ``SupertrendVal``

    Parameters
    ----------
    period     : ATR period  (default 10)
    multiplier : band width multiplier  (default 3.0)
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def __init__(self, period: int = 10, multiplier: float = 3.0) -> None:
        super().__init__(warmup=0, save_input=False)
        self.period       = period
        self.multiplier   = multiplier
        self._atr_val:    float | None = None
        self._upper:      float = 0.0
        self._lower:      float = 0.0
        self._trend_step: Callable = self._uptrend_step
        self._atr_ind = None
        self.atr_keys:ListenerKey|None = None

    def init_depends(self) -> None:
        self.atr_keys = api.atr(self.context_symbol,self.tf,self.period, self._on_atr)

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.atr_keys)

    def _on_atr(self, atr_val: float) -> None:
        self._atr_val = atr_val

    # ------------------------------------------------------------------
    # Trend step functions
    # ------------------------------------------------------------------
    def _uptrend_step(self, ohlcv: OHLCV, atr: float) -> SupertrendVal:
        hl2         = (ohlcv.high + ohlcv.low) * 0.5
        new_lower   = hl2 - self.multiplier * atr
        self._lower = max(new_lower, self._lower)
        if ohlcv.close < self._lower:
            self._upper      = hl2 + self.multiplier * atr
            self._trend_step = self._downtrend_step
            return SupertrendVal(value=self._upper, is_uptrend=False)
        return SupertrendVal(value=self._lower, is_uptrend=True)

    def _downtrend_step(self, ohlcv: OHLCV, atr: float) -> SupertrendVal:
        hl2         = (ohlcv.high + ohlcv.low) * 0.5
        new_upper   = hl2 + self.multiplier * atr
        self._upper = min(new_upper, self._upper)
        if ohlcv.close > self._upper:
            self._lower      = hl2 - self.multiplier * atr
            self._trend_step = self._uptrend_step
            return SupertrendVal(value=self._lower, is_uptrend=True)
        return SupertrendVal(value=self._upper, is_uptrend=False)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        atr = self._atr_val
        if atr is None:
            return None
        hl2          = (ohlcv.high + ohlcv.low) * 0.5
        self._upper  = hl2 + self.multiplier * atr
        self._lower  = hl2 - self.multiplier * atr
        is_up        = ohlcv.close > hl2
        self._trend_step = self._uptrend_step if is_up else self._downtrend_step
        val          = self._lower if is_up else self._upper
        return SupertrendVal(value=val, is_uptrend=is_up)

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> Optional[SupertrendVal]:
        atr = self._atr_val
        if atr is None:
            return None
        return self._trend_step(ohlcv, atr)

    def add_input_value(self, raw: object) -> None:
        # In standalone mode: feed Tr first (so ATR callback fires before user)
        # then feed own user
        self._atr_ind._tr.add_input_value(raw)
        self._pipe.tick(raw, self)

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.supertrend(self.period, self.multiplier)]

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        color = "#089981" if value.is_uptrend else "#F23645"
        return {f"st_{self.period}_{self.multiplier}": [
            Point(time=timestamp, value=value.value, color=color)
        ]}
