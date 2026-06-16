from __future__ import annotations
"""
trex.indic.volatility.tr
~~~~~~~~~~~~~~~~~~~~~~~~
True Range — the building block for ATR.

Performance design
------------------
``warmup=1`` ensures ``_first_calculate`` is called only once (for the first
bar, which has no previous close).  Every subsequent tick goes directly to
``_calculate_new_value`` with no conditional checks.
"""

from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class Tr(Indicator):
    """
    True Range.

    Output: ``float`` = max(High−Low, |High−prev_Close|, |Low−prev_Close|)

    The first bar emits ``High − Low`` since there is no previous close.
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
        # warmup=1: absorb one tick so prev_value is available on first calc
        super().__init__(warmup=1)

    # ------------------------------------------------------------------
    # Boot — one-shot for the first real bar
    # ------------------------------------------------------------------
    def _first_calculate(self, value: OHLCV, prev: OHLCV) -> float:
        """First bar: TR = High − Low (no previous close)."""
        return value.high - value.low

    # ------------------------------------------------------------------
    # Run — full TR formula, zero conditionals
    # ------------------------------------------------------------------
    def _calculate_new_value(self, value: OHLCV, prev: OHLCV) -> float:
        hl = value.high - value.low
        hc = abs(value.high - prev.close)
        lc = abs(value.low  - prev.close)
        return hl if hl >= hc and hl >= lc else (hc if hc >= lc else lc)

    def series_defs(self):
        from trex.domain.types import SeriesDef
        return [SeriesDef(key="tr", label="True Range", pane="sub",
                          kind="line", color="#B71C1C", pane_id="pane_tr",
                          pane_height=80, digits=4)]
