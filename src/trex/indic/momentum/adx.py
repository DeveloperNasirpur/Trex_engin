from __future__ import annotations
"""
trex.indic.momentum.adx
~~~~~~~~~~~~~~~~~~~~~~~~
ADX / +DI / −DI — trend strength measurement (Wilder, 1978).

Formula:
    TR   = True Range (delegated to Tr sub-indicator)
    +DM  = max(H − prevH, 0)  if  > max(prevL − L, 0)  else 0
    −DM  = max(prevL − L, 0)  if  > max(H − prevH, 0)  else 0
    TR_s, +DM_s, −DM_s  (Wilder smoothing, factor = 1/period)
    +DI  = 100 × +DM_s / TR_s
    −DI  = 100 × −DM_s / TR_s
    DX   = 100 × |+DI − −DI| / (+DI + −DI)
    ADX  = Wilder EMA of DX

Architecture
------------
ADX uses a Tr sub-indicator via callback for the True Range component.
OHLCV is also needed for +DM / −DM, so add_input_value is NOT blocked.

In standalone mode: Tr is fed first (to set _cur_tr), then the own user.
In ctx mode: Tr and ADX both receive OHLCV from CTF; Tr fires its callback
before ADX processes the bar because Tr is registered first.
"""

from dataclasses import dataclass

from trex.base import ListenerKey
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator

_EPS = 1e-10


@dataclass(slots=True)
class ADXVal:
    """ADX output."""
    adx:      float
    plus_di:  float
    minus_di: float


class ADX(Indicator):
    """
    Average Directional Index.

    Receives raw OHLCV bars.
    Output: ``ADXVal``  (first emitted after ``2 × period`` ticks)
    """
    _ind_name   = "ADX"
    _key_params = ("period",)

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def __init__(self, period: int = 14) -> None:
        super().__init__(warmup=1, save_input=False)
        self.period      = period
        k                = 1.0 / period
        self._k:  float  = k
        self._k1: float  = 1.0 - k
        self._tr_s:   float = 0.0
        self._pdm_s:  float = 0.0
        self._ndm_s:  float = 0.0
        self._adx_s:  float = 0.0
        self._dx_buf: list  = []
        self._phase:  int   = 0
        self._cur_tr: float = 0.0
        self._tr_ind = None
        self.tr_keys:ListenerKey|None = None

    def init_depends(self) -> None:
        self.tr_keys = api.tr(self.context_symbol, self.tf, self._on_tr)

    def dispatch(self) -> None:
        api = self._ctx.api
        api.de_attach_by_key(self.tr_keys)

    def _on_tr(self, tr_val: float) -> None:
        self._cur_tr = tr_val

    @staticmethod
    def _dm(ohlcv: OHLCV, prev: OHLCV):
        up  = ohlcv.high - prev.high
        dn  = prev.low   - ohlcv.low
        pdm = max(up, 0.0) * (up > dn)
        ndm = max(dn, 0.0) * (dn > up)
        return pdm, ndm

    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV) -> object:
        tr          = self._cur_tr
        pdm, ndm    = self._dm(ohlcv, prev)

        if self._phase == 0:
            self._tr_s  += tr
            self._pdm_s += pdm
            self._ndm_s += ndm
            if len(self._dx_buf) < self.period - 1:
                self._dx_buf.append(0.0)
                return None
            self._phase = 1
            pdi = 100.0 * self._pdm_s / (self._tr_s + _EPS)
            ndi = 100.0 * self._ndm_s / (self._tr_s + _EPS)
            dx  = 100.0 * abs(pdi - ndi) / (pdi + ndi + _EPS)
            self._dx_buf = [dx]
            return None

        if self._phase == 1:
            k, k1         = self._k, self._k1
            self._tr_s    = self._tr_s  * k1 + tr  * k
            self._pdm_s   = self._pdm_s * k1 + pdm * k
            self._ndm_s   = self._ndm_s * k1 + ndm * k
            pdi           = 100.0 * self._pdm_s / (self._tr_s + _EPS)
            ndi           = 100.0 * self._ndm_s / (self._tr_s + _EPS)
            dx            = 100.0 * abs(pdi - ndi) / (pdi + ndi + _EPS)
            self._dx_buf.append(dx)
            if len(self._dx_buf) < self.period:
                return None
            self._adx_s   = sum(self._dx_buf) / self.period
            self._dx_buf  = None
            self._phase   = 2
            return ADXVal(adx=self._adx_s, plus_di=pdi, minus_di=ndi)

    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> ADXVal:
        tr            = self._cur_tr
        pdm, ndm      = self._dm(ohlcv, prev)
        k, k1         = self._k, self._k1
        self._tr_s    = self._tr_s  * k1 + tr  * k
        self._pdm_s   = self._pdm_s * k1 + pdm * k
        self._ndm_s   = self._ndm_s * k1 + ndm * k
        pdi           = 100.0 * self._pdm_s / (self._tr_s + _EPS)
        ndi           = 100.0 * self._ndm_s / (self._tr_s + _EPS)
        dx            = 100.0 * abs(pdi - ndi) / (pdi + ndi + _EPS)
        self._adx_s   = self._adx_s * k1 + dx * k
        return ADXVal(adx=self._adx_s, plus_di=pdi, minus_di=ndi)

    def add_input_value(self, raw: object) -> None:
        # Feed Tr first so _on_tr fires before _calculate_new_value uses _cur_tr
        self._tr_ind.add_input_value(raw)
        self._pipe.tick(raw, self)

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["tr_s"]   = self._tr_s
            s["pdm_s"]  = self._pdm_s
            s["ndm_s"]  = self._ndm_s
            s["adx_s"]  = self._adx_s
            s["dx_buf"] = list(self._dx_buf) if self._dx_buf is not None else []
            s["phase"]  = self._phase
            s["cur_tr"] = self._cur_tr
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._tr_s   = state.get("tr_s",  0.0)
            self._pdm_s  = state.get("pdm_s", 0.0)
            self._ndm_s  = state.get("ndm_s", 0.0)
            self._adx_s  = state.get("adx_s", 0.0)
            self._dx_buf = state.get("dx_buf", [])
            self._phase  = state.get("phase", 2)
            self._cur_tr = state.get("cur_tr", 0.0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return Oscillator.adx(self.period, key_prefix=self.indicator_key())

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        prefix = self.indicator_key()
        return {
            f"{prefix}":        [Point(time=timestamp, value=value.adx)],
            f"{prefix}_plus":   [Point(time=timestamp, value=value.plus_di)],
            f"{prefix}_minus":  [Point(time=timestamp, value=value.minus_di)],
        }
