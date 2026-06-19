from __future__ import annotations
"""
trex.indic.trend.kama
~~~~~~~~~~~~~~~~~~~~~
Kaufman Adaptive Moving Average — self-tuning EMA that slows in noisy
markets and accelerates in trending ones.

Formula:
    direction  = |close − close[er_period]|
    volatility = Σ |close[i] − close[i-1]|  over er_period bars
    ER         = direction / volatility           (Efficiency Ratio, 0–1)
    sc         = (ER × (fast_k − slow_k) + slow_k) ²
    KAMA       = prev_KAMA + sc × (close − prev_KAMA)

    fast_k = 2/(fast+1),  slow_k = 2/(slow+1)

Hot-path (run phase):
    direction  = abs(value − win[0])
    volatility = rolling_vol (O(1) update via deque sum)
    Entire calculation — zero branch
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class KAMA(Indicator):
    """
    Kaufman Adaptive Moving Average.

    Parameters
    ----------
    er_period : Efficiency Ratio look-back (default 10)
    fast      : Fast EMA period for trending markets (default 2)
    slow      : Slow EMA period for noisy markets (default 30)

    Output: ``float``  (first emitted after ``er_period + 1`` ticks)
    """
    _ind_name   = "KAMA"
    _key_params = ("er_period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass


    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(
        self,
        er_period:       int      = 10,
        fast:            int      = 2,
        slow:            int      = 30,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.er_period   = er_period
        fast_k           = 2.0 / (fast + 1.0)
        slow_k           = 2.0 / (slow + 1.0)
        self._fast_k: float = fast_k
        self._slow_k: float = slow_k
        self._sc_range: float = fast_k - slow_k
        # Ring buffer: win[0] = value er_period bars ago
        self._win:  deque[float] = deque(maxlen=er_period + 1)
        # Deque of per-bar |changes| for rolling volatility sum
        self._diffs: deque[float] = deque(maxlen=er_period)
        self._vol:  float         = 0.0   # Σ |Δclose| over er_period
        self._kama: float         = 0.0

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        self._win.append(value)
        if prev is not None:
            d = abs(value - prev)
            self._vol += d
            self._diffs.append(d)
        if len(self._win) <= self.er_period:
            return None
        # Seed KAMA as first close; advance to run phase without emission
        self._kama = self._win[0]
        return True   # advance → next tick will call _calculate_new_value

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: float) -> float:
        d   = abs(value - prev)
        # O(1) rolling volatility — diffs is always full after boot
        self._vol = self._vol - self._diffs[0] + d
        self._diffs.append(d)

        direction  = abs(value - self._win[0])
        self._win.append(value)

        er  = direction / (self._vol or 1e-10)
        sc  = (er * self._sc_range + self._slow_k) ** 2
        self._kama += sc * (value - self._kama)
        return self._kama

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win"]   = list(self._win)
            s["diffs"] = list(self._diffs)
            s["vol"]   = self._vol
            s["kama"]  = self._kama
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win   = deque(state["win"],   maxlen=self.er_period + 1)
            self._diffs = deque(state["diffs"], maxlen=self.er_period)
            self._vol   = state["vol"]
            self._kama  = state["kama"]

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.kama(self.er_period, key=self.indicator_key())]
