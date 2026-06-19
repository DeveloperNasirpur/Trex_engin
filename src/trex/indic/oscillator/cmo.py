from __future__ import annotations
"""
trex.indic.oscillator.cmo
~~~~~~~~~~~~~~~~~~~~~~~~~~
Chande Momentum Oscillator — measures momentum without smoothing.

Formula:
    gains = Σ max(close[i] − close[i-1], 0)  over period bars
    losses= Σ max(close[i-1] − close[i], 0)  over period bars
    CMO   = 100 × (gains − losses) / (gains + losses)

Hot-path (run phase): O(1) rolling sums — zero branch
    gain = max(delta, 0.0)
    loss = max(-delta, 0.0)
    gain_sum += gain − oldest_gain
    loss_sum += loss − oldest_loss
    return 100 × (gain_sum − loss_sum) / (gain_sum + loss_sum + ε)
"""

from collections import deque
from typing import Callable

from trex.base.ohlcv import ValueExtractor, OHLCV
from trex.engine.indicator import Indicator


class CMO(Indicator):
    """
    Chande Momentum Oscillator.

    Output: ``float`` ∈ [−100, 100]  (first emitted after ``period + 1`` ticks)
    """
    _ind_name   = "CMO"
    _key_params = ("period",)

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
        period:          int      = 14,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period       = period
        self._gain_win:   deque[float] = deque(maxlen=period)
        self._loss_win:   deque[float] = deque(maxlen=period)
        self._gain_sum:   float = 0.0
        self._loss_sum:   float = 0.0

    def _cmo(self) -> float:
        total = self._gain_sum + self._loss_sum
        return 100.0 * (self._gain_sum - self._loss_sum) / (total + 1e-10)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: float | None) -> object:
        if prev is None:
            return None
        delta = value - prev
        gain  = max(delta,  0.0)
        loss  = max(-delta, 0.0)
        self._gain_sum += gain;  self._gain_win.append(gain)
        self._loss_sum += loss;  self._loss_win.append(loss)
        if len(self._gain_win) < self.period:
            return None
        return self._cmo()

    # ------------------------------------------------------------------
    # Run — zero branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: float) -> float:
        delta = value - prev
        gain  = max(delta,  0.0)
        loss  = max(-delta, 0.0)
        self._gain_sum += gain - self._gain_win[0]
        self._loss_sum += loss - self._loss_win[0]
        self._gain_win.append(gain)
        self._loss_win.append(loss)
        return self._cmo()

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["gain_win"] = list(self._gain_win)
            s["loss_win"] = list(self._loss_win)
            s["gain_sum"] = self._gain_sum
            s["loss_sum"] = self._loss_sum
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._gain_win = deque(state.get("gain_win", []), maxlen=self.period)
            self._loss_win = deque(state.get("loss_win", []), maxlen=self.period)
            self._gain_sum = state.get("gain_sum", 0.0)
            self._loss_sum = state.get("loss_sum", 0.0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.cmo(self.period, key=self.indicator_key())]
