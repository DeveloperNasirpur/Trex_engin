from __future__ import annotations
"""
trex.api
========
Public API — تمیز، بدون circular import، با typing مدرن.

تغییرات نسبت به نسخه قدیمی
-----------------------------
- ``libs.trex.*`` → ``trex.*``
- حذف ``dash_key`` / ``dash_mapping`` (به presentation layer تعلق دارد)
- ``Optional[X]`` → ``X | None``
- ``List``, ``Dict`` → ``list``, ``dict``
- lazy import در ``_register`` برای جلوگیری از circular import
- ``vwma`` syntax error رفع شد
- ``_ctx`` parameter: indicator.init_depends می‌تواند context instance خود را پاس دهد
  تا sub-indicatorها در همان context register شوند (نه global singleton)
"""

from typing import Any, Callable, Type

from trex.base.indic_key import ListenerKey
from trex.base.ohlcv import ValueExtractor
from trex.base.timeframe import Timeframe
from trex.engine.context import IndicatorInfo, ctx as _global_ctx, ctx
from trex.engine.indicator import Indicator


# ── Indicator tree renderer ───────────────────────────────────────────────────

def render_indicator_tree(infos: dict[str, IndicatorInfo]) -> str:
    """Render a dependency tree for all indicators on one symbol."""
    deps  = {k: set(v.dependencies) for k, v in infos.items()}
    roots = set(deps) - {d for ds in deps.values() for d in ds}
    visited: set[str] = set()
    lines:   list[str] = []

    def _walk(key: str, level: int = 0) -> None:
        if key in visited:
            return
        visited.add(key)
        info = infos[key]
        tf_label = (
            f"[{info.source_tf} → {info.timeframe}]"
            if info.source_tf and info.source_tf != info.timeframe
            else f"[{info.timeframe}]"
        )
        lines.append("  " * level + f"├── {info.name} {tf_label}")
        for dep in sorted(deps.get(key, [])):
            _walk(dep, level + 1)

    for root in sorted(roots):
        _walk(root)
    return "\n".join(lines)


# ── Internal registration helper ──────────────────────────────────────────────

def _register(
    cnl:       Type[Indicator],
    symbol:    str,
    timeframe: str,
    listener:  Callable[[Any], None] | None,
    _ctx:      Any | None = None,
    **params:  Any,
) -> ListenerKey:
    """Register indicator in *_ctx* (or global ctx if None) and attach *listener*."""
    # Extract meta-flags — must not be passed to the indicator constructor
    visible: bool = bool(params.pop("visible", False))

    context = _ctx if _ctx is not None else _global_ctx
    inst = context.get(cnl=cnl, symbol=symbol, timeframe=timeframe, **params)

    # Mark as primary: این indicator توسط کاربر (نه sub-indicator) register شده
    inst._is_primary = True
    if visible:
        inst._visible = True  # type: ignore[attr-defined]

    # Wire into AutoEngine if it is running
    from trex.engine import auto as _auto_mod
    if _auto_mod._engine is not None:
        _auto_mod._engine.wire_indicator(symbol, inst)

    key = ""
    if listener is not None:
        key = context.make_listener_key(inst, listener)
        inst.add_callback_listener(key, listener)
    return ListenerKey(symbol, key, inst.context_key)


# ── Trend indicators ──────────────────────────────────────────────────────────

def sma(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 20,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Simple Moving Average."""
    from trex.indic.trend.sma import SMA
    return _register(SMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def ema(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Exponential Moving Average."""
    from trex.indic.trend.ema import EMA
    return _register(EMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def wma(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 20,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Weighted Moving Average."""
    from trex.indic.trend.wma import WMA
    return _register(WMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def hma(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 10,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Hull Moving Average."""
    from trex.indic.trend.hma import HMA
    return _register(HMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def dema(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Double Exponential Moving Average."""
    from trex.indic.trend.dema import DEMA
    return _register(DEMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def tema(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Triple Exponential Moving Average."""
    from trex.indic.trend.tema import TEMA
    return _register(TEMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def zlema(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Zero-Lag EMA."""
    from trex.indic.trend.zlema import ZLEMA
    return _register(ZLEMA, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def vwma(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 20,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Volume-Weighted Moving Average (uses OHLCV)."""
    from trex.indic.trend.vwma import VWMA
    return _register(VWMA, symbol, timeframe, listener, period=period, **kw)


def kama(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    er_period:       int                    = 10,
    fast:            int                    = 2,
    slow:            int                    = 30,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Kaufman Adaptive Moving Average."""
    from trex.indic.trend.kama import KAMA
    return _register(KAMA, symbol, timeframe, listener,
                     er_period=er_period, fast=fast, slow=slow,
                     value_extractor=value_extractor, **kw)


# ── Volatility indicators ─────────────────────────────────────────────────────

def tr(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """True Range."""
    from trex.indic.volatility.tr import Tr
    return _register(Tr, symbol, timeframe, listener, **kw)


def atr(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any] | None = None,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Average True Range."""
    from trex.indic.volatility.atr import Atr
    return _register(Atr, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def stddev(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 20,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Rolling Standard Deviation."""
    from trex.indic.volatility.stddev import StdDev
    return _register(StdDev, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def bbands(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 20,
    mult:            float                  = 2.0,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Bollinger Bands → BBVal(upper, middle, lower)."""
    from trex.indic.volatility.bbands import BollingerBands
    return _register(BollingerBands, symbol, timeframe, listener,
                     period=period, mult=mult, value_extractor=value_extractor, **kw)


def keltner(
    symbol:     str,
    timeframe:  str                    = Timeframe.m1,
    period:     int                    = 20,
    atr_period: int                    = 10,
    mult:       float                  = 2.0,
    listener:   Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Keltner Channel → KeltnerVal(upper, middle, lower)."""
    from trex.indic.volatility.keltner import KeltnerChannel
    return _register(KeltnerChannel, symbol, timeframe, listener,
                     period=period, atr_period=atr_period, mult=mult, **kw)


def donchian(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 20,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Donchian Channel → DonchianVal(upper, middle, lower)."""
    from trex.indic.volatility.donchian import DonchianChannel
    return _register(DonchianChannel, symbol, timeframe, listener, period=period, **kw)


# ── Momentum / RSI-family ─────────────────────────────────────────────────────

def rsi(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """RSI (Wilder EMA)."""
    from trex.indic.momentum.rsi import RSI
    return _register(RSI, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def macd(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    fast_period:     int                    = 12,
    slow_period:     int                    = 26,
    signal_period:   int                    = 9,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """MACD → MACDVal(macd, signal, histogram)."""
    from trex.indic.momentum.macd import MACD
    return _register(MACD, symbol, timeframe, listener,
                     fast_period=fast_period, slow_period=slow_period,
                     signal_period=signal_period, value_extractor=value_extractor, **kw)


def trix(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """TRIX Oscillator."""
    from trex.indic.momentum.trix import TRIX
    return _register(TRIX, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def adx(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 14,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """ADX → ADXVal(adx, plus_di, minus_di)."""
    from trex.indic.momentum.adx import ADX
    return _register(ADX, symbol, timeframe, listener, period=period, **kw)


def aroon(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 25,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Aroon → AroonVal(up, down, oscillator)."""
    from trex.indic.momentum.aroon import Aroon
    return _register(Aroon, symbol, timeframe, listener, period=period, **kw)


# ── Oscillators ───────────────────────────────────────────────────────────────

def stochastic(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    k_period:  int                    = 14,
    d_period:  int                    = 3,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Stochastic → StochVal(k, d)."""
    from trex.indic.oscillator.stochastic import Stochastic
    return _register(Stochastic, symbol, timeframe, listener,
                     k_period=k_period, d_period=d_period, **kw)


def cci(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 20,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Commodity Channel Index."""
    from trex.indic.oscillator.cci import CCI
    return _register(CCI, symbol, timeframe, listener, period=period, **kw)


def williams_r(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 14,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Williams %R."""
    from trex.indic.oscillator.williams_r import WilliamsR
    return _register(WilliamsR, symbol, timeframe, listener, period=period, **kw)


def roc(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 12,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Rate of Change."""
    from trex.indic.oscillator.roc import ROC
    return _register(ROC, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def momentum(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 10,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Momentum Oscillator."""
    from trex.indic.oscillator.mom import Momentum
    return _register(Momentum, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


def mfi(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    period:    int                    = 14,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Money Flow Index."""
    from trex.indic.oscillator.mfi import MFI
    return _register(MFI, symbol, timeframe, listener, period=period, **kw)


def obv(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """On Balance Volume."""
    from trex.indic.oscillator.obv import OBV
    return _register(OBV, symbol, timeframe, listener, **kw)


def cmo(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    period:          int                    = 14,
    value_extractor: Callable[..., Any]     = ValueExtractor.extract_close,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Chande Momentum Oscillator."""
    from trex.indic.oscillator.cmo import CMO
    return _register(CMO, symbol, timeframe, listener,
                     period=period, value_extractor=value_extractor, **kw)


# ── Hybrid / compound ─────────────────────────────────────────────────────────

def vwap(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """VWAP — resets each trading day."""
    from trex.indic.hybrid.vwap import VWAP
    return _register(VWAP, symbol, timeframe, listener, **kw)


def supertrend(
    symbol:     str,
    timeframe:  str                    = Timeframe.m1,
    period:     int                    = 10,
    multiplier: float                  = 3.0,
    listener:   Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Supertrend → SupertrendVal(value, is_uptrend)."""
    from trex.indic.hybrid.supertrend import Supertrend
    return _register(Supertrend, symbol, timeframe, listener,
                     period=period, multiplier=multiplier, **kw)


def ichimoku(
    symbol:        str,
    timeframe:     str                    = Timeframe.m1,
    tenkan_period: int                    = 9,
    kijun_period:  int                    = 26,
    senkou_period: int                    = 52,
    listener:      Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Ichimoku Kinko Hyo → IchimokuVal."""
    from trex.indic.hybrid.ichimoku import Ichimoku
    return _register(Ichimoku, symbol, timeframe, listener,
                     tenkan_period=tenkan_period, kijun_period=kijun_period,
                     senkou_period=senkou_period, **kw)


def psar(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    step:      float                  = 0.02,
    max_af:    float                  = 0.20,
    listener:  Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Parabolic SAR → PSARVal(sar, is_uptrend, af, ep)."""
    from trex.indic.hybrid.psar import ParabolicSAR
    return _register(ParabolicSAR, symbol, timeframe, listener,
                     step=step, max_af=max_af, **kw)


def zigzag_base(
    symbol:          str,
    timeframe:       str                    = Timeframe.m1,
    min_accept_size: float                  = 0.0,
    listener:        Callable[[Any], None] | None = None,
    **kw: Any,
) -> ListenerKey:
    """Channel-break ZigZag → ZigZagVal."""
    from trex.indic.ZIG import ZigZagBase
    return _register(ZigZagBase, symbol, timeframe, listener,
                     min_accept_size=min_accept_size, **kw)


# ── Context helpers ───────────────────────────────────────────────────────────

def attach_listener_timeframe(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    listener:  Callable[..., Any] | None = None,
) -> None:
    if listener is None:
        return
    ctx.set_dispatch_timeframe(
        symbol, timeframe,
        f"{listener.__name__}{listener.__module__}",
        listener,
    )


def de_attach_listener_timeframe(
    symbol:    str,
    timeframe: str                    = Timeframe.m1,
    listener:  Callable[..., Any] | None = None,
) -> None:
    if listener is None:
        return
    ctx.remove_dispatch_timeframe(
        symbol, timeframe,
        f"{listener.__name__}{listener.__module__}",
    )


def de_attach(indicator: Indicator, key: str) -> None:
    """Remove a listener from an indicator (decrements reference count)."""
    indicator.remove_callback_listener(key)


def de_attach_by_key(keys: ListenerKey | list[ListenerKey]) -> bool:
    """Remove listener(s) identified by ListenerKey."""
    return ctx.de_attach_by_key(keys)


def indicators(symbol: str) -> str:
    """Return a pretty-printed dependency tree for *symbol*."""
    return render_indicator_tree(ctx.indicators_info(symbol))


def init(
    db_config:          Any    | None = None,
    timezone:           str           = "Asia/Tehran",
    fetch_size:         int           = 100_000,
    source_timeframe:   str           = Timeframe.m1,
    start_provide_from: str   | None  = None,
) -> None:
    """Configure the global trex context. Must be called once before use.

    Args:
        db_config: :class:`~trex.source.config.ConfigPostgres` instance.
        timezone: IANA timezone name for CTF bar-open detection.
        fetch_size: PostgreSQL batch size.
        source_timeframe: Incoming data timeframe (default ``"1m"``).
        start_provide_from: ISO date string; skip bars before this.
    """
    ctx.configure(
        start_provide_from=start_provide_from,
        db_config=db_config,
        time_zone=timezone,
        fetch_size=fetch_size,
        source_timeframe=source_timeframe,
    )


def start_history_provide(
    table_symbol: str                    = "BTC_USDT",
    start_from:   str | None             = None,
    count_first:  int                    = 1,
    on_first:     Callable[..., Any] | None = None,
    on_provide:   Callable[..., Any] | None = None,
    on_finish:    Callable[..., Any] | None = None,
) -> None:
    """Stream historical candles from PostgreSQL into all registered indicators."""
    from trex.source.postgres import CandleSourcePostgres
    CandleSourcePostgres(
        start_from=start_from,
        on_first=on_first,
        on_provide=on_provide,
        on_finish=on_finish,
        count_first=count_first,
    ).run(table_symbol=table_symbol)


# backward-compat alias
api = type("api", (), {
    name: staticmethod(fn)
    for name, fn in {
        "sma": sma, "ema": ema, "wma": wma, "hma": hma,
        "dema": dema, "tema": tema, "zlema": zlema, "vwma": vwma, "kama": kama,
        "tr": tr, "atr": atr, "stddev": stddev, "bbands": bbands,
        "keltner": keltner, "donchian": donchian,
        "rsi": rsi, "macd": macd, "trix": trix, "adx": adx, "aroon": aroon,
        "stochastic": stochastic, "cci": cci, "williams_r": williams_r,
        "roc": roc, "momentum": momentum, "mfi": mfi, "obv": obv, "cmo": cmo,
        "vwap": vwap, "supertrend": supertrend, "ichimoku": ichimoku,
        "psar": psar, "zigzag_base": zigzag_base,
        "de_attach_by_key": de_attach_by_key,
    }.items()
})()
