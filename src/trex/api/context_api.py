from __future__ import annotations
"""
trex.api.context_api
====================
ContextApi — یک wrapper که همه api functions را با یک context instance خاص
اجرا می‌کند. این به init_depends اجازه می‌دهد sub-indicatorها را در همان
context که indicator در آن register شده ثبت کند، نه در global singleton.

استفاده در init_depends:
    def init_depends(self) -> None:
        api = self._ctx.api          # ← همان context
        self.keys.append(api.ema(self.context_symbol, self.tf, 14, self._ve, self._on_ema))
"""

from typing import TYPE_CHECKING, Any, Callable

from trex.base.indic_key import ListenerKey
from trex.base.ohlcv import ValueExtractor
from trex.base.timeframe import Timeframe

if TYPE_CHECKING:
    from trex.engine.context import ContextIndicator


class ContextApi:
    """Thin façade: همه api functions را با یک context instance خاص wire می‌کند."""

    __slots__ = ("_ctx",)

    def __init__(self, ctx: "ContextIndicator") -> None:
        self._ctx = ctx

    def _register(
        self,
        cnl:       Any,
        symbol:    str,
        timeframe: str,
        listener:  Callable[[Any], None] | None,
        **params:  Any,
    ) -> ListenerKey:
        from trex.engine.indicator import Indicator
        inst: Indicator = self._ctx.get(cnl=cnl, symbol=symbol, timeframe=timeframe, **params)
        # Sub-indicator: NOT primary — کاربر این را مستقیم register نکرده
        # (ContextApi توسط init_depends صدا می‌شود)
        key = ""
        if listener is not None:
            key = self._ctx.make_listener_key(inst, listener)
            inst.add_callback_listener(key, listener)
        return ListenerKey(symbol, key, inst.context_key)

    # ── Trend ─────────────────────────────────────────────────────────────────

    def sma(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 20,
            value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
            listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.trend.sma import SMA
        return self._register(SMA, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    def ema(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 14,
            value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
            listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.trend.ema import EMA
        return self._register(EMA, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    def wma(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 20,
            value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
            listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.trend.wma import WMA
        return self._register(WMA, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    def dema(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 14,
             value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
             listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.trend.dema import DEMA
        return self._register(DEMA, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    def tema(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 14,
             value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
             listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.trend.tema import TEMA
        return self._register(TEMA, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    def hma(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 10,
            value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
            listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.trend.hma import HMA
        return self._register(HMA, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    # ── Volatility ────────────────────────────────────────────────────────────

    def tr(self, symbol: str, timeframe: str = Timeframe.m1,
           listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.volatility.tr import Tr
        return self._register(Tr, symbol, timeframe, listener)

    def atr(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 14,
            listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.volatility.atr import Atr
        return self._register(Atr, symbol, timeframe, listener, period=period)

    def stddev(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 20,
               value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
               listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.volatility.stddev import StdDev
        return self._register(StdDev, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    # ── Momentum ──────────────────────────────────────────────────────────────

    def rsi(self, symbol: str, timeframe: str = Timeframe.m1, period: int = 14,
            value_extractor: Callable[..., Any] = ValueExtractor.extract_close,
            listener: Callable[[Any], None] | None = None) -> ListenerKey:
        from trex.indic.momentum.rsi import RSI
        return self._register(RSI, symbol, timeframe, listener,
                               period=period, value_extractor=value_extractor)

    def de_attach_by_key(self, keys: "ListenerKey | list[ListenerKey]") -> bool:
        return self._ctx.de_attach_by_key(keys)


__all__ = ["ContextApi"]
