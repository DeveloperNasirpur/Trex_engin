from __future__ import annotations
"""
trex.engine.context
====================
Global singleton که همه live indicators و timeframe converters را مدیریت می‌کند.

Thread-safety
-------------
``get`` و ``remove_indicator`` با ``RLock`` محافظت می‌شوند.
``provide`` بدون lock است (single producer thread).

تغییرات نسبت به نسخه قدیمی
-----------------------------
- حذف ``lightweight_charts`` و ``dash_key`` / ``dash_mapping``
  (این‌ها به لایه presentation تعلق دارند، نه engine)
- ``libs.trex.*`` → ``trex.*``
- ``Optional[X]`` → ``X | None``
- ``List``, ``Dict`` → ``list``, ``dict``
- ``_init_trex_client`` حذف شد (ctx فقط engine است)
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Type

from trex.base.indic_key import ListenerKey
from trex.base.ohlcv import OHLCV
from trex.base.timeframe import Timeframe
from trex.engine.indicator import Indicator
from trex.engine.pipeline import Pipeline

logger = logging.getLogger("trex.context")


# ── Snapshot DTO ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class IndicatorInfo:
    """Immutable snapshot describing one registered indicator."""

    key:          str
    name:         str
    symbol:       str
    timeframe:    str
    source_tf:    str | None       = None
    dependencies: tuple[str, ...] = field(default_factory=tuple)


# ── Context ───────────────────────────────────────────────────────────────────

class ContextIndicator:
    """
    Central registry: manages indicator instances and CTF aggregators.

    Typical usage::

        from trex.engine.context import ctx
        from trex.indic.momentum.rsi import Rsi

        ctx.configure(time_zone="Asia/Tehran")
        rsi = ctx.get(Rsi, symbol="BTC", timeframe="4H", period=14)

        # Feed loop (single thread):
        for bar in feed:
            ctx.provide(bar)

    The ``provide()`` method routes each incoming 1-minute candle to every
    registered ``ConvertTimeFrame`` (CTF), which aggregates into higher
    timeframes and dispatches to the corresponding indicators.
    """

    def __init__(self) -> None:
        self._providing: Callable[[OHLCV], None] = self._provide_from_first
        self.start_provide_from: int | None = None

        # {symbol: {context_key: Indicator}}
        self._indicators: dict[str, dict[str, Indicator]] = {}

        # {symbol: ConvertTimeFrame}
        self._ctfs: dict[str, Any] = {}

        self._lock = threading.RLock()

        self.initialized:      bool             = False
        self.db_config:        Any | None       = None
        self.fetch_size:       int              = 10_000
        self.time_zone:        str              = "UTC"
        self.source_timeframe: str              = Timeframe.m1

        # Server integration (set by attach_server)
        self._server_broadcast_fn:  Any | None = None
        self._server_define_fn:     Any | None = None
        self._server_symbol_filter: str | None = None

    # ── One-time configuration ────────────────────────────────────────────────

    @property
    def api(self) -> "Any":
        """Return a :class:`~trex.api.context_api.ContextApi` bound to *this* context.

        Use inside ``init_depends()`` instead of the module-level ``api``
        singleton to ensure sub-indicators are registered in the same context.

        Example::

            def init_depends(self) -> None:
                api = self._ctx.api
                self.keys.append(api.ema(self.context_symbol, self.tf, 14, ve, cb))
        """
        from trex.api.context_api import ContextApi
        return ContextApi(self)

    def reset(self) -> None:
        """Reset the context to its initial state so it can be re-configured.

        Clears all registered indicators and CTFs.  Useful when running
        multiple backtests in the same process.
        """
        self._providing = self._provide_from_first
        self.start_provide_from = None
        self._indicators.clear()
        self._ctfs.clear()
        self.initialized = False
        self.db_config = None
        self.fetch_size = 10_000
        self.time_zone = "UTC"
        self.source_timeframe = Timeframe.m1
        self._server_broadcast_fn = None
        self._server_define_fn = None
        self._server_symbol_filter = None

    def configure(
        self,
        db_config:          Any    | None = None,
        fetch_size:         int           = 10_000,
        time_zone:          str           = "UTC",
        source_timeframe:   str           = Timeframe.m1,
        start_provide_from: str   | None  = None,
    ) -> None:
        """Initialize the context.  Raises ``RuntimeError`` if called twice.

        Args:
            db_config: Optional :class:`~trex.source.config.ConfigPostgres`.
            fetch_size: Batch size for PostgreSQL streaming.
            time_zone: IANA timezone name for CTF bar-open detection.
            source_timeframe: Incoming data timeframe (default ``"1m"``).
            start_provide_from: ISO date string; silently skip bars before this.
        """
        if self.initialized:
            raise RuntimeError("trex context is already initialized.")

        self.db_config        = db_config
        self.fetch_size       = fetch_size
        self.time_zone        = time_zone
        self.source_timeframe = source_timeframe
        self.initialized      = True

        if start_provide_from:
            from trex.utils import date_to_milliseconds
            self.start_provide_from = date_to_milliseconds(start_provide_from)
            self._providing = self._provide_from_time

    # ── De-attachment ─────────────────────────────────────────────────────────

    def de_attach_by_key(self, keys: ListenerKey | list[ListenerKey]) -> bool:
        """Remove a listener and auto-cleanup indicator if refcount hits zero."""
        if isinstance(keys, list):
            for k in keys:
                self.de_attach_by_key(k)
            return True
        bucket = self._indicators.get(keys.symbol, {})
        indic  = bucket.get(keys.indicator)
        if indic is None:
            return False
        indic.remove_callback_listener(keys.listener)
        if indic.reference <= 0:
            self.remove_indicator(keys.symbol, keys.indicator)
        return True

    # ── Indicator registry ────────────────────────────────────────────────────

    def get(
        self,
        cnl:       Type[Indicator],
        symbol:    str,
        timeframe: str,
        **params: Any,
    ) -> Indicator:
        """Return (or create and register) an indicator.

        Identity fields are injected before ``init_depends()`` runs so that
        sub-indicators created inside ``init_depends`` can read
        ``self.context_symbol`` and ``self.tf``.

        Args:
            cnl: Indicator class.
            symbol: Trading symbol (e.g. ``"BTC"``).
            timeframe: Target timeframe (e.g. ``"4H"``).
            **params: Constructor parameters forwarded to the indicator.

        Returns:
            The registered :class:`~trex.engine.indicator.Indicator` instance.
        """
        key = cnl.make_key(tf=timeframe, symbol=symbol, **params)  # type: ignore[attr-defined]

        with self._lock:
            bucket = self._indicators.setdefault(symbol, {})

            # Lazy-import to avoid circular import at module level
            from trex.indic.CTF import ConvertTimeFrame
            ctf = self._ctfs.setdefault(
                symbol, ConvertTimeFrame(time_zone=self.time_zone)
            )

            if key in bucket:
                return bucket[key]

            inst                = cnl(**params)
            inst.context_key    = key
            inst.context_symbol = symbol
            inst.source_tf      = self.source_timeframe
            inst.tf             = timeframe
            inst._ctx           = self   # so init_depends can use same context

            inst.init_depends()
            ctf.add_timeframe(timeframe, indicator_key=key, callback=self._dispatch)

            bucket[key] = inst

            # Auto-inject server hook if server is attached
            # فقط برای indicatorهای primary (نه sub-indicators داخلی)
            if (self._server_broadcast_fn is not None
                    and getattr(inst, "_is_primary", False)):
                if (self._server_symbol_filter is None
                        or self._server_symbol_filter == symbol):
                    inst._set_emit_hook(self._server_broadcast_fn)
                    if self._server_define_fn is not None:
                        defs = inst.series_defs()
                        if defs:
                            self._server_define_fn(*defs)

            return inst

    def remove_indicator(self, symbol: str, key: str) -> None:
        """Remove one indicator from the registry."""
        with self._lock:
            bucket = self._indicators.get(symbol)
            if bucket:
                bucket.pop(key, None)

    # ── Data ingestion ────────────────────────────────────────────────────────

    def _provide_from_time(self, ohlcv: OHLCV) -> None:
        from trex.utils import date_to_milliseconds
        mil = date_to_milliseconds(ohlcv.time.strftime("%Y-%m-%d %H:%M:%S"))
        if (self.start_provide_from or 0) <= mil:
            self._providing = self._provide_from_first
            self._providing(ohlcv)

    def _provide_from_first(self, ohlcv: OHLCV) -> None:
        ctf = self._ctfs.get(ohlcv.symbol)
        if ctf is not None:
            ctf.add_input_value(ohlcv)

    def provide(self, ohlcv: OHLCV) -> None:
        """Route one 1-min OHLCV candle to every registered CTF converter."""
        self._providing(ohlcv)

    def set_dispatch_timeframe(
        self,
        symbol:    str,
        timeframe: str = Timeframe.m1,
        key:       str = "",
        cb:        Callable[..., Any] | None = None,
    ) -> None:
        """Register a raw timeframe callback (bypasses indicator registry)."""
        from trex.indic.CTF import ConvertTimeFrame
        bucket = self._ctfs.get(symbol)
        if not bucket:
            bucket = self._ctfs.setdefault(
                symbol, ConvertTimeFrame(time_zone=self.time_zone)
            )
        bucket.add_timeframe(timeframe, indicator_key=key, callback=cb)

    def remove_dispatch_timeframe(
        self,
        symbol:    str,
        timeframe: str = Timeframe.m1,
        key:       str = "",
    ) -> None:
        """Remove a raw timeframe callback."""
        bucket = self._ctfs.get(symbol)
        if bucket:
            bucket.remove_indicator_callback(timeframe=timeframe, indicator_key=key)

    def _dispatch(self, key: str, ohlcv: OHLCV) -> None:
        """CTF callback: route a completed higher-TF bar to one indicator."""
        bucket = self._indicators.get(ohlcv.symbol)
        if not bucket:
            return
        inst = bucket.get(key)
        if inst is not None:
            inst.add_input_value(ohlcv)
        else:
            ctf = self._ctfs.get(ohlcv.symbol)
            if ctf:
                ctf.remove_indicator_callback(ohlcv.str_time, key)

    # ── Listener-key helpers ──────────────────────────────────────────────────

    @staticmethod
    def _describe_callable(fn: Callable[..., Any]) -> dict[str, str]:
        try:
            if hasattr(fn, "__self__"):
                cls = fn.__self__.__class__
                return {"module": cls.__module__, "name": fn.__name__}
            return {"module": fn.__module__, "name": fn.__name__}
        except Exception as exc:
            logger.warning("describe_callable failed: %s", exc)
            return {"module": "?", "name": "?"}

    def make_listener_key(self, indicator: Indicator, listener: Callable[..., Any]) -> str:
        """Unique, stable key for an ``(indicator, listener)`` pair."""
        info = self._describe_callable(listener)
        return f"ext:{indicator.context_key}:{info['module']}.{info['name']}"

    # ── Introspection ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict[str, dict[str, str]]:
        """Return ``{symbol: {key: timeframe}}`` for all live indicators."""
        with self._lock:
            return {
                sym: {k: ind.tf for k, ind in bucket.items()}
                for sym, bucket in self._indicators.items()
            }

    def indicators_info(self, symbol: str) -> dict[str, IndicatorInfo]:
        """Return an :class:`IndicatorInfo` snapshot for every indicator on *symbol*."""
        return {
            key: IndicatorInfo(
                key=key,
                name=ind.__class__.__name__,
                symbol=symbol,
                timeframe=ind.tf,
                source_tf=ind.source_tf or None,
                dependencies=tuple(ind.dependencies.keys()),
            )
            for key, ind in self._indicators.get(symbol, {}).items()
        }

    @property
    def is_active(self) -> bool:
        """True if at least one CTF is registered."""
        return bool(self._ctfs)

    # ── Server integration ────────────────────────────────────────────────────

    def attach_server(
        self,
        broadcast_fn: Callable[[dict[str, list[Any]]], None],
        symbol:        str | None = None,
        define_fn:     Callable[..., Any] | None = None,
    ) -> None:
        """
        هر indicator موجود (و آینده) را به server وصل کن.

        وقتی هر indicator ``emit()`` کند، ``broadcast_fn`` با
        ``{series_key: [Point]}`` فراخوانی می‌شود.

        اگر ``define_fn`` هم داده شود، ``series_defs()`` هر indicator
        بلافاصله به terminal ارسال می‌شود.

        Args:
            broadcast_fn: تابعی با signature ``(data: dict[str, list[Point]]) -> None``.
                         معمولاً ``server.broadcast_indicators`` است.
            symbol: اگر داده شود، فقط indicators این symbol وصل می‌شوند.
                   None = همه symbols.
            define_fn: اگر داده شود، ``series_defs()`` هر indicator به terminal
                      ارسال می‌شود. معمولاً ``server.broadcast_definitions`` است.

        Example::

            from trex.server.sync import SyncServer
            server = SyncServer()
            server.start()

            ctx.attach_server(
                broadcast_fn=server.broadcast_indicators,
                define_fn=server.broadcast_definitions,
            )
        """
        with self._lock:
            # Store first so any indicator registered concurrently gets the hook
            self._server_broadcast_fn  = broadcast_fn
            self._server_define_fn     = define_fn
            self._server_symbol_filter = symbol
            for sym, bucket in self._indicators.items():
                if symbol is not None and sym != symbol:
                    continue
                for ind in bucket.values():
                    if not getattr(ind, "_is_primary", False):
                        continue
                    ind._set_emit_hook(broadcast_fn)
                    if define_fn is not None:
                        defs = ind.series_defs()
                        if defs:
                            define_fn(*defs)

    def detach_server(self) -> None:
        """همه indicators را از server جدا کن."""
        with self._lock:
            for bucket in self._indicators.values():
                for ind in bucket.values():
                    ind._set_emit_hook(None)
        self._server_broadcast_fn  = None
        self._server_define_fn     = None
        self._server_symbol_filter = None


# ── Module-level singleton ────────────────────────────────────────────────────

ctx: ContextIndicator = ContextIndicator()

__all__ = ["ContextIndicator", "IndicatorInfo", "ctx"]
