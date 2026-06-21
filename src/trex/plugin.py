from __future__ import annotations
"""
trex.plugin
===========
Plugin system — register custom indicators as first-class citizens
without touching the library source.

Usage
-----
::

    # my_indicators.py  (outside the library)

    from collections import deque
    from trex.engine.indicator import Indicator
    from trex.base.ohlcv import ValueExtractor
    from trex import plugin

    @plugin.register
    class VWEMA(Indicator):
        \"""Volume-weighted EMA — custom indicator example.\"""
        _ind_name   = "VWEMA"
        _key_params = ("period",)

        def __init__(self, period: int = 14,
                     value_extractor=ValueExtractor.extract_close) -> None:
            super().__init__(value_extractor=value_extractor)
            self.period    = period
            self._ve       = value_extractor
            self._num      = 0.0
            self._den      = 0.0
            self._k        = 2.0 / (period + 1.0)
            self._k1       = 1.0 - self._k
            self._buf: list = []

        def init_depends(self) -> None:
            pass

        def _first_calculate(self, ohlcv, prev):
            self._buf.append(ohlcv)
            if len(self._buf) < self.period:
                return None
            # seed
            prices  = [self._ve(b) for b in self._buf]
            volumes = [b.volume for b in self._buf]
            total_v = sum(volumes) or 1.0
            self._num = sum(p * v for p, v in zip(prices, volumes)) / total_v
            self._den = 1.0
            self._buf = None
            return self._num

        def _calculate_new_value(self, ohlcv, prev):
            price = self._ve(ohlcv)
            vol   = ohlcv.volume or 0.0
            self._num = self._k1 * self._num + self._k * price * vol
            self._den = self._k1 * self._den + self._k * vol
            return self._num / self._den if self._den else price

    # Now available everywhere:
    import trex
    trex.vwema("BTCUSDT", "1h", period=14, listener=on_vwema)

    # And inside init_depends of another indicator:
    api = self._ctx.api
    key = api.vwema(self.context_symbol, self.tf, period=14, listener=cb)
"""

from typing import Any, Callable, Type

from trex.base.ohlcv import ValueExtractor
from trex.base.timeframe import Timeframe
from trex.base.indic_key import ListenerKey
from trex.engine.indicator import Indicator

# Registry: method_name → Indicator subclass
_REGISTRY: dict[str, Type[Indicator]] = {}


# ── Public API ────────────────────────────────────────────────────────────────

def register(
    cls: Type[Indicator] | None = None,
    *,
    name: str | None = None,
) -> Any:
    """
    Register a custom :class:`~trex.engine.indicator.Indicator` subclass.

    Can be used as a decorator (with or without arguments) or called directly:

    ::

        @plugin.register
        class MyInd(Indicator): ...

        @plugin.register(name="my_ind")
        class MyInd(Indicator): ...

        plugin.register(MyInd)
        plugin.register(MyInd, name="my_ind")

    After registration the indicator is available via:

    * ``trex.<name>(symbol, tf, ...)``
    * ``api.<name>(symbol, tf, ...)``  inside ``init_depends``
    * ``trex.ctx.get(MyInd, symbol, tf, ...)``  directly

    Parameters
    ----------
    cls:
        Indicator subclass to register.
    name:
        API method name (snake_case).  Defaults to ``cls._ind_name.lower()``.

    Returns
    -------
    The class unchanged, so ``@plugin.register`` works as a no-op decorator.
    """
    # Called as @plugin.register (no parentheses)
    if cls is not None:
        return _do_register(cls, name)

    # Called as @plugin.register(name="foo") — return actual decorator
    def _decorator(klass: Type[Indicator]) -> Type[Indicator]:
        return _do_register(klass, name)
    return _decorator


def registered() -> dict[str, Type[Indicator]]:
    """Return a copy of the plugin registry (name → class)."""
    return dict(_REGISTRY)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _do_register(cls: Type[Indicator], name: str | None) -> Type[Indicator]:
    if not (isinstance(cls, type) and issubclass(cls, Indicator)):
        raise TypeError(
            f"plugin.register expects an Indicator subclass, got {cls!r}"
        )

    method_name = (name or getattr(cls, "_ind_name", cls.__name__)).lower()

    # Idempotent: same class + same name is a no-op
    existing = _REGISTRY.get(method_name)
    if existing is not None:
        if existing is cls:
            return cls
        raise ValueError(
            f"Plugin name '{method_name}' already registered by "
            f"{existing.__qualname__}.  Use name= to choose a different name."
        )

    _REGISTRY[method_name] = cls
    _override_make_key(cls)          # stable key regardless of user's module path
    _inject_into_context_api(method_name, cls)
    _inject_into_global_api(method_name, cls)
    return cls


def _override_make_key(cls: Type[Indicator]) -> None:
    """
    Override make_key on the plugin class so its context key follows the
    same pattern as built-in indicators but with a stable ``trex.plugin.``
    prefix — independent of where the user's module lives.

    Built-in:  ``trex.indic.trend.ema.EMA|sym=BTCUSDT|tf=1h|period=14``
    Plugin:    ``trex.plugin.MyInd|sym=BTCUSDT|tf=1h|period=14``
    """
    ind_name = getattr(cls, "_ind_name", cls.__name__)

    @classmethod  # type: ignore[misc]
    def _plugin_make_key(klass: type, tf: str = Timeframe.m1, symbol: str = "", **params: Any) -> str:
        base   = f"trex.plugin.{ind_name}|sym={symbol}|tf={tf}"
        extras = "|".join(
            f"{k}={Indicator._fmt_param(v)}"
            for k, v in sorted(params.items())
        )
        return f"{base}|{extras}" if extras else base

    cls.make_key = _plugin_make_key  # type: ignore[method-assign]


def _inject_into_context_api(name: str, cls: Type[Indicator]) -> None:
    """Add api.<name>(symbol, tf, ..., listener) to ContextApi."""
    from trex.api.context_api import ContextApi

    def _method(
        self: "ContextApi",
        symbol:    str,
        timeframe: str = Timeframe.m1,
        listener:  Callable[[Any], None] | None = None,
        **params:  Any,
    ) -> ListenerKey:
        return self._register(cls, symbol, timeframe, listener, **params)

    _method.__name__     = name
    _method.__qualname__ = f"ContextApi.{name}"
    _method.__doc__      = (
        f"Plugin indicator: {cls.__qualname__}\n\n"
        f"Registered via trex.plugin.register()."
    )
    setattr(ContextApi, name, _method)


def _inject_into_global_api(name: str, cls: Type[Indicator]) -> None:
    """Add trex.<name>(symbol, tf, ..., listener) to the top-level namespace."""
    from trex.api.api import _register as _api_register
    import trex.api.api as _api_mod
    import trex as _trex_mod

    def _func(
        symbol:    str,
        timeframe: str = Timeframe.m1,
        listener:  Callable[[Any], None] | None = None,
        **params:  Any,
    ) -> ListenerKey:
        return _api_register(cls, symbol, timeframe, listener, **params)

    _func.__name__   = name
    _func.__module__ = "trex"
    _func.__doc__    = (
        f"Plugin indicator: {cls.__qualname__}\n\n"
        f"Registered via trex.plugin.register()."
    )

    setattr(_api_mod,  name, _func)
    setattr(_trex_mod, name, _func)


__all__ = ["register", "registered"]
