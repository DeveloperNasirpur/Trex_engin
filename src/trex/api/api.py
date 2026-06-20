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


_EXTRACTOR_SHORT: dict[str, str | None] = {
    "extract_close":  None,    # default, omit
    "extract_open":   "open",
    "extract_high":   "high",
    "extract_low":    "low",
    "extract_volume": "vol",
    "extract_hl2":    "hl2",
    "extract_hlc3":   "hlc3",
    "extract_hlcc4":  "hlcc4",
}


def _make_indicator_key(cnl: type, symbol: str, tf: str, params: dict) -> str:
    """Build human-readable key from indicator class and params."""
    name = getattr(cnl, "_ind_name", None) or cnl.__name__
    parts: list[str] = [name, symbol.upper(), tf]

    key_params: tuple[str, ...] = getattr(cnl, "_key_params", ())
    if key_params:
        for attr in key_params:
            if attr in params:
                v = params[attr]
                if v is not None and not callable(v):
                    parts.append(str(v))
    else:
        # fallback: sorted non-callable, non-extractor params
        for k in sorted(params):
            if k == "value_extractor":
                continue
            v = params[k]
            if v is not None and not callable(v):
                parts.append(str(v))

    # extractor suffix (only if non-default)
    ve = params.get("value_extractor")
    if ve is not None and callable(ve):
        fname = getattr(ve, "__name__", "")
        short = _EXTRACTOR_SHORT.get(fname, fname or None)
        if short:
            parts.append(short)

    return "_".join(str(p) for p in parts)


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

    # Inject human-readable key (idempotent — only set on first registration)
    if not inst._indicator_id:
        inst._indicator_id = _make_indicator_key(cnl, symbol, timeframe, params)

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


def rma(symbol: str, timeframe: str, period: int = 14,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.rma import RMA
    return _register(RMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def t3(symbol: str, timeframe: str, period: int = 5, volume_factor: float = 0.7,
       value_extractor=ValueExtractor.extract_close,
       listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.t3 import T3
    return _register(T3, symbol, timeframe, listener, _ctx,
                     period=period, volume_factor=volume_factor, value_extractor=value_extractor, visible=visible)

def trima(symbol: str, timeframe: str, period: int = 20,
          value_extractor=ValueExtractor.extract_close,
          listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.trima import TRIMA
    return _register(TRIMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def vidya(symbol: str, timeframe: str, cmo_period: int = 9, smooth: int = 12,
          value_extractor=ValueExtractor.extract_close,
          listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.vidya import VIDYA
    return _register(VIDYA, symbol, timeframe, listener, _ctx,
                     cmo_period=cmo_period, smooth=smooth, value_extractor=value_extractor, visible=visible)

def alma(symbol: str, timeframe: str, period: int = 20, sigma: float = 6.0, offset_pct: float = 0.85,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.alma import ALMA
    return _register(ALMA, symbol, timeframe, listener, _ctx,
                     period=period, sigma=sigma, offset_pct=offset_pct, value_extractor=value_extractor, visible=visible)

def mcginley(symbol: str, timeframe: str, period: int = 14,
             value_extractor=ValueExtractor.extract_close,
             listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.mcginley import McGinley
    return _register(McGinley, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def lsma(symbol: str, timeframe: str, period: int = 25,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.lsma import LSMA
    return _register(LSMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def fwma(symbol: str, timeframe: str, period: int = 10,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.fwma import FWMA
    return _register(FWMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def pwma(symbol: str, timeframe: str, period: int = 10,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.pwma import PWMA
    return _register(PWMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def swma(symbol: str, timeframe: str, period: int = 4,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.swma import SWMA
    return _register(SWMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def sinwma(symbol: str, timeframe: str, period: int = 14,
           value_extractor=ValueExtractor.extract_close,
           listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.sinwma import SINWMA
    return _register(SINWMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def ssma(symbol: str, timeframe: str, period: int = 20,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.ssma import SSMA
    return _register(SSMA, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def hwma(symbol: str, timeframe: str, alpha: float = 0.2, beta: float = 0.1,
         value_extractor=ValueExtractor.extract_close,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.hwma import HWMA
    return _register(HWMA, symbol, timeframe, listener, _ctx,
                     alpha=alpha, beta=beta, value_extractor=value_extractor, visible=visible)

def jma(symbol: str, timeframe: str, period: int = 7, phase: int = 0, power: int = 2,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.trend.jma import JMA
    return _register(JMA, symbol, timeframe, listener, _ctx,
                     period=period, phase=phase, power=power, value_extractor=value_extractor, visible=visible)


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


# ── Extended momentum indicators ─────────────────────────────────────────────

def ao(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.ao import AO
    return _register(AO, symbol, timeframe, listener, _ctx, visible=visible)

def ac(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.ac import AC
    return _register(AC, symbol, timeframe, listener, _ctx, visible=visible)

def tsi(symbol: str, timeframe: str, r_period: int = 25, s_period: int = 13,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.tsi import TSI
    return _register(TSI, symbol, timeframe, listener, _ctx,
                     r_period=r_period, s_period=s_period, value_extractor=value_extractor, visible=visible)

def dpo(symbol: str, timeframe: str, period: int = 20,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.dpo import DPO
    return _register(DPO, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=value_extractor, visible=visible)

def kst(symbol: str, timeframe: str, r1=10, r2=13, r3=14, r4=15, s1=10, s2=13, s3=14, s4=15, signal=9,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.kst import KST
    return _register(KST, symbol, timeframe, listener, _ctx,
                     r1=r1, r2=r2, r3=r3, r4=r4, s1=s1, s2=s2, s3=s3, s4=s4, signal=signal,
                     value_extractor=value_extractor, visible=visible)

def coppock(symbol: str, timeframe: str, r1: int = 14, r2: int = 11, wma_period: int = 10,
            value_extractor=ValueExtractor.extract_close,
            listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.coppock import Coppock
    return _register(Coppock, symbol, timeframe, listener, _ctx,
                     r1=r1, r2=r2, wma_period=wma_period, value_extractor=value_extractor, visible=visible)

def rvi(symbol: str, timeframe: str, period: int = 10,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.rvi_momentum import RVI
    return _register(RVI, symbol, timeframe, listener, _ctx, period=period, visible=visible)

def fisher(symbol: str, timeframe: str, period: int = 9,
           listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.fisher import FisherTransform
    return _register(FisherTransform, symbol, timeframe, listener, _ctx, period=period, visible=visible)

def vortex(symbol: str, timeframe: str, period: int = 14,
           listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.momentum.vortex import Vortex
    return _register(Vortex, symbol, timeframe, listener, _ctx, period=period, visible=visible)


# ── Extended oscillator indicators ────────────────────────────────────────────

def ppo(symbol: str, timeframe: str, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.oscillator.ppo import PPO
    return _register(PPO, symbol, timeframe, listener, _ctx,
                     fast_period=fast_period, slow_period=slow_period, signal_period=signal_period,
                     value_extractor=value_extractor, visible=visible)

def apo(symbol: str, timeframe: str, fast_period: int = 12, slow_period: int = 26,
        value_extractor=ValueExtractor.extract_close,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.oscillator.apo import APO
    return _register(APO, symbol, timeframe, listener, _ctx,
                     fast_period=fast_period, slow_period=slow_period,
                     value_extractor=value_extractor, visible=visible)

def stochrsi(symbol: str, timeframe: str, rsi_period: int = 14, stoch_period: int = 14,
             k_period: int = 3, d_period: int = 3,
             value_extractor=ValueExtractor.extract_close,
             listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.oscillator.stochrsi import StochRSI
    return _register(StochRSI, symbol, timeframe, listener, _ctx,
                     rsi_period=rsi_period, stoch_period=stoch_period,
                     k_period=k_period, d_period=d_period,
                     value_extractor=value_extractor, visible=visible)

def uo(symbol: str, timeframe: str, period1: int = 7, period2: int = 14, period3: int = 28,
       listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.oscillator.uo import UO
    return _register(UO, symbol, timeframe, listener, _ctx,
                     period1=period1, period2=period2, period3=period3, visible=visible)

def chop(symbol: str, timeframe: str, period: int = 14,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.oscillator.chop import CHOP
    return _register(CHOP, symbol, timeframe, listener, _ctx, period=period, visible=visible)

def force_index(symbol: str, timeframe: str, period: int = 13,
                listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.oscillator.force_index import ForceIndex
    return _register(ForceIndex, symbol, timeframe, listener, _ctx, period=period, visible=visible)


# ── Volume ────────────────────────────────────────────────────────────────────

def ad(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.ad import AD
    return _register(AD, symbol, timeframe, listener, _ctx, visible=visible)

def adosc(symbol: str, timeframe: str, fast_period: int = 3, slow_period: int = 10,
          listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.adosc import ADOSC
    return _register(ADOSC, symbol, timeframe, listener, _ctx,
                     fast_period=fast_period, slow_period=slow_period, visible=visible)

def cmf(symbol: str, timeframe: str, period: int = 20,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.cmf import CMF
    return _register(CMF, symbol, timeframe, listener, _ctx, period=period, visible=visible)

def eom(symbol: str, timeframe: str, period: int = 14, divisor: float = 10000.0,
        listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.eom import EOM
    return _register(EOM, symbol, timeframe, listener, _ctx,
                     period=period, divisor=divisor, visible=visible)

def nvi(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.nvi import NVI
    return _register(NVI, symbol, timeframe, listener, _ctx, visible=visible)

def pvi(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.pvi import PVI
    return _register(PVI, symbol, timeframe, listener, _ctx, visible=visible)

def pvt(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.pvt import PVT
    return _register(PVT, symbol, timeframe, listener, _ctx, visible=visible)

def vo(symbol: str, timeframe: str, fast_period: int = 5, slow_period: int = 10,
       listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.vo import VO
    return _register(VO, symbol, timeframe, listener, _ctx,
                     fast_period=fast_period, slow_period=slow_period, visible=visible)

def vroc(symbol: str, timeframe: str, period: int = 14,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volume.vroc import VROC
    return _register(VROC, symbol, timeframe, listener, _ctx, period=period, visible=visible)


# ── Statistics ────────────────────────────────────────────────────────────────

def zscore(symbol: str, timeframe: str, period: int = 20,
           value_extractor=None, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.statistics.zscore import ZScore
    from trex.base.ohlcv import ValueExtractor
    ve = value_extractor or ValueExtractor.extract_close
    return _register(ZScore, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=ve, visible=visible)

def variance(symbol: str, timeframe: str, period: int = 20,
             value_extractor=None, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.statistics.variance import Variance
    from trex.base.ohlcv import ValueExtractor
    ve = value_extractor or ValueExtractor.extract_close
    return _register(Variance, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=ve, visible=visible)

def linreg_slope(symbol: str, timeframe: str, period: int = 14,
                 value_extractor=None, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.statistics.linreg_slope import LinRegSlope
    from trex.base.ohlcv import ValueExtractor
    ve = value_extractor or ValueExtractor.extract_close
    return _register(LinRegSlope, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=ve, visible=visible)

def correl(symbol: str, timeframe: str, period: int = 20,
           listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.statistics.correl import Correl
    return _register(Correl, symbol, timeframe, listener, _ctx, period=period, visible=visible)

def percentrank(symbol: str, timeframe: str, period: int = 20,
                value_extractor=None, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.statistics.percentrank import PercentRank
    from trex.base.ohlcv import ValueExtractor
    ve = value_extractor or ValueExtractor.extract_close
    return _register(PercentRank, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=ve, visible=visible)


# ── Volatility (extra) ────────────────────────────────────────────────────────

def natr(symbol: str, timeframe: str, period: int = 14,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volatility.natr import NATR
    return _register(NATR, symbol, timeframe, listener, _ctx, period=period, visible=visible)

def ui(symbol: str, timeframe: str, period: int = 14,
       value_extractor=None, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volatility.ui import UI
    from trex.base.ohlcv import ValueExtractor
    ve = value_extractor or ValueExtractor.extract_close
    return _register(UI, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=ve, visible=visible)

def hv(symbol: str, timeframe: str, period: int = 20,
       value_extractor=None, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volatility.hv import HV
    from trex.base.ohlcv import ValueExtractor
    ve = value_extractor or ValueExtractor.extract_close
    return _register(HV, symbol, timeframe, listener, _ctx,
                     period=period, value_extractor=ve, visible=visible)

def chandelier(symbol: str, timeframe: str, period: int = 22, multiplier: float = 3.0,
               listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.volatility.chandelier import Chandelier
    return _register(Chandelier, symbol, timeframe, listener, _ctx,
                     period=period, multiplier=multiplier, visible=visible)


# ── Candlestick Patterns ──────────────────────────────────────────────────────

def doji(symbol: str, timeframe: str, threshold: float = 0.1,
         listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import Doji
    return _register(Doji, symbol, timeframe, listener, _ctx, threshold=threshold, visible=visible)

def dragonfly_doji(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import DragonFlyDoji
    return _register(DragonFlyDoji, symbol, timeframe, listener, _ctx, visible=visible)

def gravestone_doji(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import GravestoneDoji
    return _register(GravestoneDoji, symbol, timeframe, listener, _ctx, visible=visible)

def hammer(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import Hammer
    return _register(Hammer, symbol, timeframe, listener, _ctx, visible=visible)

def inverted_hammer(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import InvertedHammer
    return _register(InvertedHammer, symbol, timeframe, listener, _ctx, visible=visible)

def hanging_man(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import HangingMan
    return _register(HangingMan, symbol, timeframe, listener, _ctx, visible=visible)

def shooting_star(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import ShootingStar
    return _register(ShootingStar, symbol, timeframe, listener, _ctx, visible=visible)

def marubozu(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import Marubozu
    return _register(Marubozu, symbol, timeframe, listener, _ctx, visible=visible)

def spinning_top(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import SpinningTop
    return _register(SpinningTop, symbol, timeframe, listener, _ctx, visible=visible)

def long_legged_doji(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import LongLeggedDoji
    return _register(LongLeggedDoji, symbol, timeframe, listener, _ctx, visible=visible)

def bullish_belt(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import BullishBelt
    return _register(BullishBelt, symbol, timeframe, listener, _ctx, visible=visible)

def bearish_belt(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import BearishBelt
    return _register(BearishBelt, symbol, timeframe, listener, _ctx, visible=visible)

def high_wave(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import HighWave
    return _register(HighWave, symbol, timeframe, listener, _ctx, visible=visible)

def rickshaw_man(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import RickshawMan
    return _register(RickshawMan, symbol, timeframe, listener, _ctx, visible=visible)

def umbrella_line(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.single import UmbrellaLine
    return _register(UmbrellaLine, symbol, timeframe, listener, _ctx, visible=visible)

def bullish_engulfing(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import BullishEngulfing
    return _register(BullishEngulfing, symbol, timeframe, listener, _ctx, visible=visible)

def bearish_engulfing(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import BearishEngulfing
    return _register(BearishEngulfing, symbol, timeframe, listener, _ctx, visible=visible)

def bullish_harami(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import BullishHarami
    return _register(BullishHarami, symbol, timeframe, listener, _ctx, visible=visible)

def bearish_harami(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import BearishHarami
    return _register(BearishHarami, symbol, timeframe, listener, _ctx, visible=visible)

def piercing(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import Piercing
    return _register(Piercing, symbol, timeframe, listener, _ctx, visible=visible)

def dark_cloud_cover(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import DarkCloudCover
    return _register(DarkCloudCover, symbol, timeframe, listener, _ctx, visible=visible)

def tweezer(symbol: str, timeframe: str, tolerance: float = 0.001,
            listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import Tweezer
    return _register(Tweezer, symbol, timeframe, listener, _ctx, tolerance=tolerance, visible=visible)

def kicking(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import Kicking
    return _register(Kicking, symbol, timeframe, listener, _ctx, visible=visible)

def on_neck(symbol: str, timeframe: str, tolerance: float = 0.002,
            listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import OnNeck
    return _register(OnNeck, symbol, timeframe, listener, _ctx, tolerance=tolerance, visible=visible)

def matching_low(symbol: str, timeframe: str, tolerance: float = 0.001,
                 listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.two_candle import MatchingLow
    return _register(MatchingLow, symbol, timeframe, listener, _ctx, tolerance=tolerance, visible=visible)

def morning_star(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import MorningStar
    return _register(MorningStar, symbol, timeframe, listener, _ctx, visible=visible)

def evening_star(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import EveningStar
    return _register(EveningStar, symbol, timeframe, listener, _ctx, visible=visible)

def morning_doji_star(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import MorningDojiStar
    return _register(MorningDojiStar, symbol, timeframe, listener, _ctx, visible=visible)

def evening_doji_star(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import EveningDojiStar
    return _register(EveningDojiStar, symbol, timeframe, listener, _ctx, visible=visible)

def three_white_soldiers(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import ThreeWhiteSoldiers
    return _register(ThreeWhiteSoldiers, symbol, timeframe, listener, _ctx, visible=visible)

def three_black_crows(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import ThreeBlackCrows
    return _register(ThreeBlackCrows, symbol, timeframe, listener, _ctx, visible=visible)

def three_inside_up(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import ThreeInsideUp
    return _register(ThreeInsideUp, symbol, timeframe, listener, _ctx, visible=visible)

def three_inside_down(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import ThreeInsideDown
    return _register(ThreeInsideDown, symbol, timeframe, listener, _ctx, visible=visible)

def deliberation(symbol: str, timeframe: str, listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import Deliberation
    return _register(Deliberation, symbol, timeframe, listener, _ctx, visible=visible)

def identical_three_crows(symbol: str, timeframe: str, tolerance: float = 0.002,
                          listener=None, *, visible: bool = False, _ctx=None) -> ListenerKey:
    from trex.indic.pattern.three_candle import IdenticalThreeCrows
    return _register(IdenticalThreeCrows, symbol, timeframe, listener, _ctx,
                     tolerance=tolerance, visible=visible)


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
        "rma": rma, "t3": t3, "trima": trima, "vidya": vidya, "alma": alma,
        "mcginley": mcginley, "lsma": lsma, "fwma": fwma, "pwma": pwma,
        "swma": swma, "sinwma": sinwma, "ssma": ssma, "hwma": hwma, "jma": jma,
        "tr": tr, "atr": atr, "stddev": stddev, "bbands": bbands,
        "keltner": keltner, "donchian": donchian,
        "rsi": rsi, "macd": macd, "trix": trix, "adx": adx, "aroon": aroon,
        "stochastic": stochastic, "cci": cci, "williams_r": williams_r,
        "roc": roc, "momentum": momentum, "mfi": mfi, "obv": obv, "cmo": cmo,
        "ao": ao, "ac": ac, "tsi": tsi, "dpo": dpo, "kst": kst, "coppock": coppock,
        "rvi": rvi, "fisher": fisher, "vortex": vortex,
        "ppo": ppo, "apo": apo, "stochrsi": stochrsi, "uo": uo, "chop": chop,
        "force_index": force_index,
        "ad": ad, "adosc": adosc, "cmf": cmf, "eom": eom, "nvi": nvi,
        "pvi": pvi, "pvt": pvt, "vo": vo, "vroc": vroc,
        "zscore": zscore, "variance": variance, "linreg_slope": linreg_slope,
        "correl": correl, "percentrank": percentrank,
        "natr": natr, "ui": ui, "hv": hv, "chandelier": chandelier,
        "doji": doji, "dragonfly_doji": dragonfly_doji, "gravestone_doji": gravestone_doji,
        "hammer": hammer, "inverted_hammer": inverted_hammer, "hanging_man": hanging_man,
        "shooting_star": shooting_star, "marubozu": marubozu, "spinning_top": spinning_top,
        "long_legged_doji": long_legged_doji, "bullish_belt": bullish_belt,
        "bearish_belt": bearish_belt, "high_wave": high_wave, "rickshaw_man": rickshaw_man,
        "umbrella_line": umbrella_line,
        "bullish_engulfing": bullish_engulfing, "bearish_engulfing": bearish_engulfing,
        "bullish_harami": bullish_harami, "bearish_harami": bearish_harami,
        "piercing": piercing, "dark_cloud_cover": dark_cloud_cover, "tweezer": tweezer,
        "kicking": kicking, "on_neck": on_neck, "matching_low": matching_low,
        "morning_star": morning_star, "evening_star": evening_star,
        "morning_doji_star": morning_doji_star, "evening_doji_star": evening_doji_star,
        "three_white_soldiers": three_white_soldiers, "three_black_crows": three_black_crows,
        "three_inside_up": three_inside_up, "three_inside_down": three_inside_down,
        "deliberation": deliberation, "identical_three_crows": identical_three_crows,
        "vwap": vwap, "supertrend": supertrend, "ichimoku": ichimoku,
        "psar": psar, "zigzag_base": zigzag_base,
        "de_attach_by_key": de_attach_by_key,
    }.items()
})()
