from __future__ import annotations
"""
trex.indic.hybrid.vwap
~~~~~~~~~~~~~~~~~~~~~~~
VWAP — Volume-Weighted Average Price, reset every session (trading day).

Formula (cumulative within session):
    TP    = (High + Low + Close) / 3
    VWAP  = Σ(TP × Volume) / Σ(Volume)

Session detection uses UTC date boundary by default, or the configured
timezone.  The date boundary triggers a function-pointer swap so that the
reset overhead is only paid on the first bar of each new session.

Hot-path (intra-session, run phase):
    cum_tpv += tp × volume
    cum_vol  += volume
    return cum_tpv / cum_vol             ← zero branch
"""

from datetime import date
from typing import Callable

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class VWAP(Indicator):
    """
    VWAP — Volume-Weighted Average Price.

    Receives raw OHLCV bars.
    Output: ``float``  (first emitted after 1 tick)

    Resets on every new calendar day (UTC or locally-converted timestamp).
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def __init__(self) -> None:
        super().__init__(warmup=0, save_input=False)
        self._cum_tpv:    float         = 0.0
        self._cum_vol:    float         = 0.0
        self._cur_date:   Optional[date] = None
        # Function pointer: handles intra-session vs session-start
        self._session_step: Callable = self._new_session_step

    # ------------------------------------------------------------------
    # Session steps (rebound on day boundary)
    # ------------------------------------------------------------------
    def _new_session_step(self, ohlcv: OHLCV) -> float:
        """Called on first bar of a new session."""
        self._cur_date = ohlcv.time.date() if ohlcv.time else None
        tp             = (ohlcv.high + ohlcv.low + ohlcv.close) / 3.0
        self._cum_tpv  = tp * ohlcv.volume
        self._cum_vol  = ohlcv.volume
        self._session_step = self._intra_session_step   # switch for next ticks
        return self._cum_tpv / self._cum_vol

    def _intra_session_step(self, ohlcv: OHLCV) -> float:
        """Called on every bar within the current session."""
        cur_date = ohlcv.time.date() if ohlcv.time else self._cur_date
        if cur_date != self._cur_date:
            # Day changed — rebind and delegate
            self._session_step = self._new_session_step
            return self._new_session_step(ohlcv)
        tp             = (ohlcv.high + ohlcv.low + ohlcv.close) / 3.0
        self._cum_tpv += tp * ohlcv.volume
        self._cum_vol += ohlcv.volume
        return self._cum_tpv / self._cum_vol

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        return self._session_step(ohlcv)

    # ------------------------------------------------------------------
    # Run — zero branch (session boundary handled by pointer rebind)
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> float:
        return self._session_step(ohlcv)

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.vwap()]
