from __future__ import annotations
"""
trex.indic.oscillator.stochastic
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Stochastic Oscillator — %K and %D lines.

Formula:
    %K = (close − lowest_low) / (highest_high − lowest_low) × 100
    %D = SMA(%K, d_period)

Architecture
------------
Stochastic computes %K inline (needs OHLCV high/low/close).
The %D signal line is delegated to a private SMA sub-indicator that
receives %K float values.

Data flow::

    OHLCV ──► [rolling high/low windows] ──► %K ──► SMA(d_period)[private] ──► emit StochVal

The private SMA must NOT be registered in CTF.
"""

from collections import deque
from dataclasses import dataclass

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator
from trex.indic.trend.sma import SMA

_EPS = 1e-10


@dataclass(slots=True)
class StochVal:
    """Stochastic output."""
    k: float
    d: float


class Stochastic(Indicator):
    """
    Stochastic Oscillator (%K and %D).

    Receives raw OHLCV bars.
    Output: ``StochVal``  (first emitted after ``k_period + d_period − 1`` ticks)

    Parameters
    ----------
    k_period : look-back for %K  (default 14)
    d_period : SMA period for %D  (default 3)
    """
    _ind_name   = "STOCH"
    _key_params = ("k_period", "d_period")

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        sym, tf = self.context_symbol, self.tf

        self._sma_d = SMA(period=self.d_period, value_extractor=None)
        self._sma_d.context_key    = f"{self.context_key}:sma_d"
        self._sma_d.context_symbol = sym
        self._sma_d.tf             = tf
        self._sma_d.source_tf      = self.source_tf
        self._sma_d.init_depends()

        self._sma_d.add_callback_listener(self.context_key, self._on_sma_d)

    def dispatch(self) -> None:
        self._sma_d.remove_callback_listener(self.context_key)

    def __init__(self, k_period: int = 14, d_period: int = 3) -> None:
        super().__init__(save_input=False)
        self.k_period   = k_period
        self.d_period   = d_period
        self._win_h:  deque[float] = deque(maxlen=k_period)
        self._win_l:  deque[float] = deque(maxlen=k_period)
        self._cur_k:  float | None = None
        self._sma_d  = None

    def _k_value(self, ohlcv: OHLCV) -> float:
        hh = max(self._win_h)
        ll = min(self._win_l)
        return (ohlcv.close - ll) / (hh - ll + _EPS) * 100.0

    def _on_sma_d(self, d_val: float) -> None:
        k = self._cur_k
        if k is not None:
            self.emit(StochVal(k=k, d=d_val))

    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        if len(self._win_h) < self.k_period:
            return None
        k = self._k_value(ohlcv)
        self._cur_k = k
        self._sma_d.add_input_value(k)
        return True  # SMA %D callback handles emission

    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> None:
        self._win_h.append(ohlcv.high)
        self._win_l.append(ohlcv.low)
        k = self._k_value(ohlcv)
        self._cur_k = k
        self._sma_d.add_input_value(k)

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win_h"] = list(self._win_h)
            s["win_l"] = list(self._win_l)
            s["cur_k"] = self._cur_k
            if self._sma_d is not None:
                s["sma_d"] = self._sma_d.get_state()
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win_h = deque(state.get("win_h", []), maxlen=self.k_period)
            self._win_l = deque(state.get("win_l", []), maxlen=self.k_period)
            self._cur_k = state.get("cur_k")
            if self._sma_d is not None and "sma_d" in state:
                self._sma_d.set_state(state["sma_d"])

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return Oscillator.stochastic(self.k_period, d=self.d_period,
                                     key_prefix=self.indicator_key())

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = self.indicator_key()
        return {
            f"{prefix}_k": [Point(time=timestamp, value=value.k)],
            f"{prefix}_d": [Point(time=timestamp, value=value.d)],
        }
