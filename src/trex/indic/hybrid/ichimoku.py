from __future__ import annotations
"""
trex.indic.hybrid.ichimoku
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ichimoku Kinko Hyo — Japanese equilibrium view system.

Components:
    Tenkan-sen  (Conversion)  = (max_high + min_low) / 2  over tenkan_period  (9)
    Kijun-sen   (Base)        = (max_high + min_low) / 2  over kijun_period   (26)
    Senkou A    (Leading A)   = (Tenkan + Kijun) / 2      ← current value
    Senkou B    (Leading B)   = (max_high + min_low) / 2  over senkou_period  (52)
    Chikou     (Lagging)      = current close (plotted kijun_period bars back)

For a streaming context the displacement is interpreted as:
    • Senkou A/B are the *current* values (not shifted forward in the feed)
    • Chikou is the close from kijun_period bars ago

Hot-path (run phase):
    Four rolling max/min lookups via deques + arithmetic    ← zero explicit if
"""

from collections import deque
from dataclasses import dataclass

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


@dataclass(slots=True)
class IchimokuVal:
    """Ichimoku output."""
    tenkan:   float   # Conversion line
    kijun:    float   # Base line
    senkou_a: float   # Leading span A
    senkou_b: float   # Leading span B
    chikou:   float   # Lagging span (close from kijun_period bars ago)


class Ichimoku(Indicator):
    """
    Ichimoku Kinko Hyo.

    Receives raw OHLCV bars.
    Output: ``IchimokuVal``  (first emitted after ``senkou_period`` ticks)

    Parameters
    ----------
    tenkan_period : Conversion line period  (default 9)
    kijun_period  : Base line period  (default 26)
    senkou_period : Senkou B period  (default 52)
    """

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
        tenkan_period: int = 9,
        kijun_period:  int = 26,
        senkou_period: int = 52,
    ) -> None:
        super().__init__(save_input=False)
        self.tenkan_period = tenkan_period
        self.kijun_period  = kijun_period
        self.senkou_period = senkou_period
        self._win_h_t: deque[float] = deque(maxlen=tenkan_period)
        self._win_l_t: deque[float] = deque(maxlen=tenkan_period)
        self._win_h_k: deque[float] = deque(maxlen=kijun_period)
        self._win_l_k: deque[float] = deque(maxlen=kijun_period)
        self._win_h_s: deque[float] = deque(maxlen=senkou_period)
        self._win_l_s: deque[float] = deque(maxlen=senkou_period)
        # Chikou: close from kijun_period bars ago
        self._chikou_buf: deque[float] = deque(maxlen=kijun_period + 1)

    def _compute(self, close: float) -> IchimokuVal:
        tenkan   = (max(self._win_h_t) + min(self._win_l_t)) * 0.5
        kijun    = (max(self._win_h_k) + min(self._win_l_k)) * 0.5
        senkou_a = (tenkan + kijun) * 0.5
        senkou_b = (max(self._win_h_s) + min(self._win_l_s)) * 0.5
        chikou   = self._chikou_buf[0] if len(self._chikou_buf) == self.kijun_period + 1 else 0.0
        return IchimokuVal(
            tenkan=tenkan, kijun=kijun,
            senkou_a=senkou_a, senkou_b=senkou_b,
            chikou=chikou,
        )

    def _push(self, ohlcv: OHLCV) -> None:
        self._win_h_t.append(ohlcv.high); self._win_l_t.append(ohlcv.low)
        self._win_h_k.append(ohlcv.high); self._win_l_k.append(ohlcv.low)
        self._win_h_s.append(ohlcv.high); self._win_l_s.append(ohlcv.low)
        self._chikou_buf.append(ohlcv.close)

    # ------------------------------------------------------------------
    # Boot
    # ------------------------------------------------------------------
    def _first_calculate(self, ohlcv: OHLCV, prev: OHLCV | None) -> object:
        self._push(ohlcv)
        if len(self._win_h_s) < self.senkou_period:
            return None
        return self._compute(ohlcv.close)

    # ------------------------------------------------------------------
    # Run — zero explicit branch
    # ------------------------------------------------------------------
    def _calculate_new_value(self, ohlcv: OHLCV, prev: OHLCV) -> IchimokuVal:
        self._push(ohlcv)
        return self._compute(ohlcv.close)

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return Overlay.ichimoku()

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        return {
            "ichi_tenkan":   [Point(time=timestamp, value=value.tenkan)],
            "ichi_kijun":    [Point(time=timestamp, value=value.kijun)],
            "ichi_senkou_a": [Point(time=timestamp, value=value.senkou_a)],
            "ichi_senkou_b": [Point(time=timestamp, value=value.senkou_b)],
            "ichi_chikou":   [Point(time=timestamp, value=value.chikou)],
        }
