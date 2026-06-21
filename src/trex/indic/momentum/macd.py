from __future__ import annotations
"""
trex.indic.momentum.macd
~~~~~~~~~~~~~~~~~~~~~~~~~
MACD — Moving Average Convergence/Divergence.

Formula:
    MACD line  = EMA(fast_period) − EMA(slow_period)
    Signal     = EMA(macd_line, signal_period)
    Histogram  = MACD − Signal

Architecture
------------
MACD uses three EMA sub-indicators via callbacks.

Data flow::

    raw ──► EMA(fast)  [shared via ctx] ──┐
                                           ├──► macd = fast − slow
    raw ──► EMA(slow)  [shared via ctx] ──┘        └──► EMA(signal)[private] ──► emit

Raw input is forwarded to both shared EMAs.  EMA(signal) is private and
receives MACD-line floats.

To avoid double emission (fast and slow both call _try_macd), a per-tick
toggle tracks whether both EMAs have fired for the current bar.
"""

from dataclasses import dataclass
from typing import Callable

from trex.base import ListenerKey
from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator, ValueType
from trex.indic.trend.ema import EMA


@dataclass(slots=True)
class MACDVal:
    """MACD output."""
    macd:      float
    signal:    float
    histogram: float


class MACD(Indicator):
    """
    MACD — Moving Average Convergence/Divergence.

    Output: ``MACDVal``
    Parameters: fast_period=12, slow_period=26, signal_period=9
    """
    _ind_name   = "MACD"
    _key_params = ("fast_period", "slow_period", "signal_period")

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        api = self._ctx.api
        fast_key = api.ema(self.context_symbol, self.tf, self.fast_period,  self._ve, self._on_fast)
        slow_key = api.ema(self.context_symbol, self.tf, self.slow_period,  self._ve, self._on_slow)
        self.keys.append(fast_key)
        self.keys.append(slow_key)

        # Resolve indicator instances (needed for add_input_value forwarding)
        bucket = self._ctx._indicators.get(self.context_symbol, {})
        self._ema_fast = bucket.get(fast_key.indicator)
        self._ema_slow = bucket.get(slow_key.indicator)

        # Signal EMA — private; receives MACD-line floats
        self._ema_sig = EMA(period=self.signal_period, value_extractor=None)
        self._ema_sig.context_key    = f"{self.context_key}:sig"
        self._ema_sig.context_symbol = self.context_symbol
        self._ema_sig.tf             = self.tf
        self._ema_sig.source_tf      = self.source_tf
        self._ema_sig._ctx           = self._ctx
        self._ema_sig.init_depends()
        self._ema_sig.add_callback_listener(self.context_key, self._on_signal)

    def dispatch(self) -> None:
        if self._ema_fast is not None:
            self._ema_fast.remove_callback_listener(self.context_key)
        if self._ema_slow is not None:
            self._ema_slow.remove_callback_listener(self.context_key)
        if self._ema_sig is not None:
            self._ema_sig.remove_callback_listener(f"{self.context_key}:sig")
            self._ema_sig = None

    def __init__(
        self,
        fast_period:     int      = 12,
        slow_period:     int      = 26,
        signal_period:   int      = 9,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.fast_period   = fast_period
        self.slow_period   = slow_period
        self.signal_period = signal_period
        self._ve           = value_extractor
        self._fast_val:   float | None = None
        self._slow_val:   float | None = None
        self._macd_val:   float | None = None
        # Per-tick flags to avoid double-computation
        self._fast_ready:  bool = False
        self._slow_ready:  bool = False
        self._ema_fast = self._ema_slow = self._ema_sig = None
        self.keys:list[ListenerKey] = []

    def _on_fast(self, val: float) -> None:
        self._fast_val   = val
        self._fast_ready = True
        if self._slow_ready:
            self._compute_macd()
            self._fast_ready = self._slow_ready = False

    def _on_slow(self, val: float) -> None:
        self._slow_val   = val
        self._slow_ready = True
        if self._fast_ready:
            self._compute_macd()
            self._fast_ready = self._slow_ready = False

    def _compute_macd(self) -> None:
        macd = self._fast_val - self._slow_val
        self._macd_val = macd
        self._ema_sig.add_input_value(macd)

    def _on_signal(self, sig: float) -> None:
        macd = self._macd_val
        if macd is not None:
            self.emit(MACDVal(macd=macd, signal=sig, histogram=macd - sig))

    def add_input_value(self, raw: object) -> None:
        # Sub-EMAs are registered in the same CTF and receive input directly.
        pass

    def _first_calculate(self, value: ValueType, prev: ValueType) -> bool:
        return True

    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> None:
        pass

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["fast_val"]   = self._fast_val
            s["slow_val"]   = self._slow_val
            s["macd_val"]   = self._macd_val
            s["fast_ready"] = self._fast_ready
            s["slow_ready"] = self._slow_ready
            # Persist sub-EMA states so they don't need to re-warm on restore
            if self._ema_fast is not None:
                s["ema_fast"] = self._ema_fast.get_state()
            if self._ema_slow is not None:
                s["ema_slow"] = self._ema_slow.get_state()
            if self._ema_sig is not None:
                s["ema_sig"] = self._ema_sig.get_state()
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._fast_val   = state.get("fast_val")
            self._slow_val   = state.get("slow_val")
            self._macd_val   = state.get("macd_val")
            self._fast_ready = state.get("fast_ready", False)
            self._slow_ready = state.get("slow_ready", False)
            if self._ema_fast is not None and "ema_fast" in state:
                self._ema_fast.set_state(state["ema_fast"])
            if self._ema_slow is not None and "ema_slow" in state:
                self._ema_slow.set_state(state["ema_slow"])
            if self._ema_sig is not None and "ema_sig" in state:
                self._ema_sig.set_state(state["ema_sig"])

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return Oscillator.macd(self.fast_period, self.slow_period, self.signal_period,
                               key_prefix=self.indicator_key())

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = self.indicator_key()
        return {
            f"{prefix}_line":   [Point(time=timestamp, value=value.macd)],
            f"{prefix}_signal": [Point(time=timestamp, value=value.signal)],
            f"{prefix}_hist":   [Point(time=timestamp, value=value.histogram,
                                       color="#089981" if value.histogram >= 0 else "#F23645")],
        }
