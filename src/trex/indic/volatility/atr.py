from __future__ import annotations
"""
trex.indic.volatility.atr
~~~~~~~~~~~~~~~~~~~~~~~~~
Average True Range — Wilder's smoothed moving average.

Architecture
------------
ATR is driven by a ``Tr`` sub-indicator via callback, NOT by ``add_input_value``.
This avoids running the OHLCV extractor on already-extracted TR floats.

``_first_calculate`` accumulates TR values until ``period`` are available, then
seeds the Wilder EMA with a simple mean.  After that, ``_calculate_new_value``
is the single-line Wilder update:

    ATR_t = (ATR_{t-1} × (period−1) + TR_t) / period
"""

from trex.base.ohlcv import OHLCV
from trex.base import ListenerKey
from trex.engine.indicator import Indicator


class Atr(Indicator):
    """
    Average True Range.

    Output: ``float``  (first emitted after ``period`` TR values)

    Formula (Wilder EMA, same as TradingView)::

        ATR₀ = mean(TR[0 … period−1])          ← simple seed
        ATRₙ = (ATRₙ₋₁ × (period−1) + TRₙ) / period
    """
    _ind_name   = "ATR"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        self.key = api.tr(self.context_symbol, self.tf,listener=self._on_tr)

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.key)

    def __init__(self, period: int = 14) -> None:
        super().__init__(save_input=False)
        self.key:ListenerKey|None = None
        self.period   = period
        self._pm1_f:  float = float(period - 1)
        self._p_f:    float = float(period)
        self._count:  int   = 0
        self._tr_sum: float = 0.0

    # ------------------------------------------------------------------
    # TR callback — routes float directly into the user
    # ------------------------------------------------------------------
    def _on_tr(self, tr_val: float) -> None:
        """Forward a TR float into the correct user phase."""
        pipe = self._pipe
        if pipe.is_running:
            pipe._run_step(tr_val, self)
        else:
            pipe._boot_step(tr_val, self)
        pipe.prev_value = tr_val

    # ------------------------------------------------------------------
    # Boot — accumulate TR floats until period is reached
    # ------------------------------------------------------------------
    def _first_calculate(self, value: float, prev: object) -> object:
        self._tr_sum += value
        self._count  += 1
        if self._count < self.period:
            return None
        return self._tr_sum / self._p_f   # simple mean seed

    # ------------------------------------------------------------------
    # Run — Wilder EMA, single line, zero conditionals
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: float, prev: object) -> float:
        return (self._pipe.prev_output * self._pm1_f + value) / self._p_f

    # ------------------------------------------------------------------
    # Block accidental OHLCV pushes
    # ------------------------------------------------------------------
    def add_input_value(self, raw: object) -> None:
        """ATR is driven by Tr callback only; direct input is ignored."""

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.atr(self.period, key=self.indicator_key())]
