"""
trex.infrastructure.sync
========================
Synchronous (blocking) façade over ``TrexServer``.

Runs the asyncio event loop in a **daemon background thread**.
Your application code uses plain blocking calls — no ``async``/``await``.

Usage
-----
::

    from trex.sync import SyncServer, SyncSession
    from trex.store import CandleStore

    store = CandleStore()
    store.seed(load_candles())
    server = SyncServer()

    @server.on_connect
    def connected(session: SyncSession) -> None:
        session.snapshot(store.recent(500), symbol="BTCUSDT", timeframe="1m")
        session.fit_content()

    @server.on_history
    def history(session: SyncSession, before: int, count: int) -> None:
        page = store.history_page(before, count)
        session.push_history(page, no_more=len(page) == 0)

    server.start()

    while True:
        bar = exchange.next_bar()
        store.update(bar)
        server.broadcast_bar(bar)
        time.sleep(0.25)

Design notes
------------
- ``SyncSession`` is a thin proxy that submits coroutines to the background
  loop via ``asyncio.run_coroutine_threadsafe``.
- All user callbacks are plain (sync) functions; they run in a thread-pool
  worker so blocking is fine.
- Each async hook wraps the corresponding sync hook using
  ``loop.run_in_executor``, keeping the event loop free.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from trex.server.server import TrexServer
from trex.domain.types import (
    Bar, Drawing, Point, SeriesDef, ChartType, ToastKind,
)
from trex.server.session import TrexSession

log = logging.getLogger("trex.sync")

_SEND_TIMEOUT = 10.0   # seconds before a blocking send gives up


# ── SyncSession ───────────────────────────────────────────────────────────────


class SyncSession:
    """
    Synchronous proxy for :class:`~trex.application.session.TrexSession`.

    Every method blocks until the frame has been written to the socket
    (or the socket is dead).  Instances are cheap — they hold only a
    reference to the underlying async session and the event loop.
    """

    __slots__ = ("_session", "_loop")

    def __init__(self, session: TrexSession, loop: asyncio.AbstractEventLoop) -> None:
        self._session = session
        self._loop    = loop

    # ── Internal helper ───────────────────────────────────────────────────────

    def _run(self, coro: Any) -> bool:
        """Submit *coro* to the background loop and wait for the result."""
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result(timeout=_SEND_TIMEOUT)
        except concurrent.futures.TimeoutError:
            log.warning("[%s] send timeout", self._session.id[:8])
            return False
        except Exception as exc:
            log.debug("[%s] send error: %s", self._session.id[:8], exc)
            return False

    # ── Metadata ──────────────────────────────────────────────────────────────

    @property
    def id(self) -> str:                 return self._session.id
    @property
    def symbol(self) -> str | None:      return self._session.symbol
    @property
    def timeframe(self) -> str | None:   return self._session.timeframe
    @property
    def chart_type(self) -> str:         return self._session.chart_type
    @property
    def client_name(self) -> str:        return self._session.client_name
    @property
    def remote(self) -> str:             return self._session.remote
    @property
    def alive(self) -> bool:             return self._session._alive
    @property
    def uptime(self) -> float:           return self._session.uptime
    @property
    def message_count(self) -> int:      return self._session.message_count

    # ── Snapshot ──────────────────────────────────────────────────────────────

    def snapshot(
        self,
        bars:        list[Bar],
        *,
        symbol:      str | None              = None,
        timeframe:   str | None              = None,
        digits:      int                     = 2,
        definitions: list[SeriesDef] | None  = None,
        indicators:  dict[str, list[Point]] | None = None,
        drawings:    list[Drawing] | None    = None,
    ) -> bool:
        return self._run(self._session.snapshot(
            bars, symbol=symbol, timeframe=timeframe, digits=digits,
            definitions=definitions, indicators=indicators, drawings=drawings,
        ))

    def push_bar(self, bar: Bar) -> bool:
        return self._run(self._session.push_bar(bar))

    def push_history(self, bars: list[Bar], *, no_more: bool = False) -> bool:
        return self._run(self._session.push_history(bars, no_more=no_more))

    # ── Indicators ────────────────────────────────────────────────────────────

    def define(self, *defs: SeriesDef) -> bool:
        return self._run(self._session.define(*defs))

    def push_indicators(self, data: dict[str, list[Point]]) -> bool:
        return self._run(self._session.push_indicators(data))

    # ── Drawings ──────────────────────────────────────────────────────────────

    def set_drawings(self, drawings: list[Drawing]) -> bool:
        return self._run(self._session.set_drawings(drawings))

    def upsert_drawing(self, drawing: Drawing) -> bool:
        return self._run(self._session.upsert_drawing(drawing))

    def delete_drawing(self, *ids: str) -> bool:
        return self._run(self._session.delete_drawing(*ids))

    def clear_drawings(self) -> bool:
        return self._run(self._session.clear_drawings())

    # ── Chart control ─────────────────────────────────────────────────────────

    def set_symbol(self, symbol: str) -> bool:
        return self._run(self._session.set_symbol(symbol))

    def set_timeframe(self, tf: str) -> bool:
        return self._run(self._session.set_timeframe(tf))

    def set_chart_type(self, ct: ChartType) -> bool:
        return self._run(self._session.set_chart_type(ct))

    def set_magnet(self, on: bool) -> bool:
        return self._run(self._session.set_magnet(on))

    def set_settings(self, **kw: Any) -> bool:
        return self._run(self._session.set_settings(**kw))

    # ── View ──────────────────────────────────────────────────────────────────

    def fit_content(self) -> bool:
        return self._run(self._session.fit_content())

    def scroll_to_end(self) -> bool:
        return self._run(self._session.scroll_to_end())

    def zoom_range(self, from_ts: int, to_ts: int) -> bool:
        return self._run(self._session.zoom_range(from_ts, to_ts))

    # ── Notifications ─────────────────────────────────────────────────────────

    def toast(self, msg: str, kind: ToastKind = "info") -> bool:
        return self._run(self._session.toast(msg, kind))

    def alert(self, msg: str) -> bool:
        return self._run(self._session.alert(msg))

    # ── Symbol / Indicator lists ───────────────────────────────────────────────

    def send_symbols_list(self, symbols: list[dict]) -> bool:
        return self._run(self._session.send_symbols_list(symbols))

    def send_indicators_list(self, defs: list[SeriesDef]) -> bool:
        return self._run(self._session.send_indicators_list(defs))

    # ── Multi-chart ───────────────────────────────────────────────────────────

    @property
    def charts(self) -> dict:
        """Secondary chart state: {chartId: {symbol, timeframe}}."""
        return self._session._charts

    def chart_snapshot(
        self,
        chart_id:    str,
        bars:        list[Bar],
        *,
        symbol:      str | None                    = None,
        timeframe:   str | None                    = None,
        digits:      int                           = 2,
        definitions: list[SeriesDef] | None        = None,
        indicators:  dict[str, list[Point]] | None = None,
    ) -> bool:
        return self._run(self._session.chart_snapshot(
            chart_id, bars, symbol=symbol, timeframe=timeframe,
            digits=digits, definitions=definitions, indicators=indicators,
        ))

    def push_chart_bar(self, chart_id: str, bar: Bar) -> bool:
        return self._run(self._session.push_chart_bar(chart_id, bar))

    def push_chart_history(
        self, chart_id: str, bars: list[Bar], *, no_more: bool = False
    ) -> bool:
        return self._run(self._session.push_chart_history(chart_id, bars, no_more=no_more))

    def __repr__(self) -> str:
        return f"SyncSession({self._session!r})"


# ── SyncServer ────────────────────────────────────────────────────────────────


class SyncServer:
    """
    Synchronous façade over :class:`~trex.application.server.TrexServer`.

    Runs the event loop in a daemon background thread.  All public methods
    are thread-safe.

    Parameters
    ----------
    host:
        Bind address. Defaults to ``"0.0.0.0"``.
    port:
        TCP port. Defaults to ``8765``.
    max_clients:
        Maximum concurrent connections. ``0`` = unlimited.
    max_workers:
        Thread-pool size for running sync callbacks.
    """

    def __init__(
        self,
        host:        str = "0.0.0.0",
        port:        int = 8765,
        max_clients: int = 0,
        max_workers: int = 64,
    ) -> None:
        self._host        = host
        self._port        = port
        self._max         = max_clients
        self._max_workers = max_workers

        self._loop:       asyncio.AbstractEventLoop | None = None
        self._thread:     threading.Thread | None          = None
        self._ready       = threading.Event()
        self._async_srv:  TrexServer | None                = None
        self._executor    = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="trex-handler"
        )

        # Sync (plain function) callbacks — set via decorators
        self._on_connect:        Callable[[SyncSession], None] | None = None
        self._on_disconnect:     Callable[[SyncSession], None] | None = None
        self._on_symbol:         Callable[[SyncSession, str], None] | None = None
        self._on_timeframe:      Callable[[SyncSession, str], None] | None = None
        self._on_chart_type:     Callable[[SyncSession, str], None] | None = None
        self._on_history:        Callable[[SyncSession, int, int], None] | None = None
        self._on_drawing_upsert:  Callable[[SyncSession, dict[str, Any]], None] | None = None
        self._on_drawing_delete:  Callable[[SyncSession, list[str]], None] | None = None
        self._on_drawings_clear:  Callable[[SyncSession], None] | None = None
        self._on_message:         Callable[[SyncSession, dict[str, Any]], None] | None = None
        self._on_get_symbols:     Callable[[SyncSession], None] | None = None
        self._on_get_indicators:  Callable[[SyncSession], None] | None = None
        self._on_layout:          Callable[[SyncSession, str, list], None] | None = None
        self._on_chart_symbol:    Callable[[SyncSession, str, str, str | None, list], None] | None = None
        self._on_chart_history:   Callable[[SyncSession, str, int, int], None] | None = None

    # ── Decorators ────────────────────────────────────────────────────────────

    def on_connect(self, fn: Callable[[SyncSession], None]) -> Callable[[SyncSession], None]:
        """Register a blocking handler called for every new client."""
        self._on_connect = fn;  return fn

    def on_disconnect(self, fn: Callable[[SyncSession], None]) -> Callable[[SyncSession], None]:
        self._on_disconnect = fn;  return fn

    def on_symbol(self, fn: Callable[[SyncSession, str], None]) -> Callable[[SyncSession, str], None]:
        """Called with ``(session, symbol)`` when the user changes symbol."""
        self._on_symbol = fn;  return fn

    def on_timeframe(self, fn: Callable[[SyncSession, str], None]) -> Callable[[SyncSession, str], None]:
        """Called with ``(session, timeframe)`` when the user changes timeframe."""
        self._on_timeframe = fn;  return fn

    def on_chart_type(self, fn: Callable[[SyncSession, str], None]) -> Callable[[SyncSession, str], None]:
        self._on_chart_type = fn;  return fn

    def on_history(self, fn: Callable[[SyncSession, int, int], None]) -> Callable[[SyncSession, int, int], None]:
        """Called with ``(session, before, count)`` for lazy-load requests."""
        self._on_history = fn;  return fn

    def on_drawing_upsert(self, fn: Callable[[SyncSession, dict[str, Any]], None]) -> Callable[[SyncSession, dict[str, Any]], None]:
        self._on_drawing_upsert = fn;  return fn

    def on_drawing_delete(self, fn: Callable[[SyncSession, list[str]], None]) -> Callable[[SyncSession, list[str]], None]:
        self._on_drawing_delete = fn;  return fn

    def on_drawings_clear(self, fn: Callable[[SyncSession], None]) -> Callable[[SyncSession], None]:
        self._on_drawings_clear = fn;  return fn

    def on_get_symbols(self, fn: Callable[["SyncSession"], None]) -> Callable[["SyncSession"], None]:
        self._on_get_symbols = fn;  return fn

    def on_get_indicators(self, fn: Callable[["SyncSession"], None]) -> Callable[["SyncSession"], None]:
        self._on_get_indicators = fn;  return fn

    def on_layout(self, fn: Callable[["SyncSession", str, list], None]) -> Callable[["SyncSession", str, list], None]:
        self._on_layout = fn;  return fn

    def on_chart_symbol(self, fn: Callable) -> Callable:
        self._on_chart_symbol = fn;  return fn

    def on_chart_history(self, fn: Callable) -> Callable:
        self._on_chart_history = fn;  return fn

    def on_message(self, fn: Callable[[SyncSession, dict[str, Any]], None]) -> Callable[[SyncSession, dict[str, Any]], None]:
        self._on_message = fn;  return fn

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self, timeout: float = 8.0) -> None:
        """
        Start the background event loop.

        Blocks until the server is accepting connections or raises
        ``TimeoutError``.
        """
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="trex-server"
        )
        self._thread.start()
        if not self._ready.wait(timeout):
            raise TimeoutError(f"server did not start within {timeout}s")
        log.info("SyncServer  ws://%s:%d", self._host, self._port)

    def stop(self) -> None:
        """Gracefully shut down the server."""
        if self._loop and self._loop.is_running():
            async def _shutdown() -> None:
                tasks = [
                    t for t in asyncio.all_tasks(self._loop)  # type: ignore[arg-type]
                    if t is not asyncio.current_task()
                ]
                for t in tasks:
                    t.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self._loop.stop()  # type: ignore[union-attr]

            fut = asyncio.run_coroutine_threadsafe(_shutdown(), self._loop)
            try:
                fut.result(timeout=5)
            except Exception:
                pass

        if self._thread:
            self._thread.join(timeout=5)
        self._loop   = None
        self._thread = None

    # ── Broadcast (thread-safe) ───────────────────────────────────────────────

    def _submit(self, coro: Any) -> Any:
        if not self._loop:
            return None
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result(timeout=5)
        except Exception:
            return None

    def broadcast_bar(
        self,
        bar:    Bar,
        filter: Callable[[SyncSession], bool] | None = None,
    ) -> int:
        """Send a realtime bar to connected clients. Thread-safe."""
        if not self._async_srv:
            return 0
        # Convert the sync filter to one that speaks TrexSession
        async_filter: Callable[[TrexSession], bool] | None = None
        if filter:
            _filt  = filter
            _loop  = self._loop
            def async_filter(s: TrexSession) -> bool:   # type: ignore[misc]
                return _filt(SyncSession(s, _loop))  # type: ignore[arg-type]
        return self._submit(self._async_srv.broadcast_bar(bar, filter=async_filter)) or 0

    def broadcast(self, payload: dict[str, Any]) -> int:
        """Send an arbitrary payload to all clients. Thread-safe."""
        if not self._async_srv:
            return 0
        return self._submit(self._async_srv.broadcast(payload)) or 0

    def broadcast_indicators(self, data: dict[str, list[Point]]) -> int:
        """Push indicator data to all clients. Thread-safe."""
        if not self._async_srv:
            return 0
        return self._submit(self._async_srv.broadcast_indicators(data)) or 0

    def broadcast_toast(self, msg: str, kind: ToastKind = "info") -> int:
        if not self._async_srv:
            return 0
        return self._submit(self._async_srv.broadcast_toast(msg, kind)) or 0

    @property
    def client_count(self) -> int:
        return self._async_srv.client_count if self._async_srv else 0

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        ex         = self._executor

        def _wrap(session: TrexSession) -> SyncSession:
            return SyncSession(session, loop)

        # Build async wrappers that delegate to sync callbacks via executor
        def _make_hook_0(cb: Callable[[SyncSession], None] | None):
            if cb is None:
                return None
            async def hook(s: TrexSession) -> None:
                await loop.run_in_executor(ex, cb, _wrap(s))
            return hook

        def _make_hook_1(cb: Callable[..., None] | None):
            if cb is None:
                return None
            async def hook(s: TrexSession, arg: Any) -> None:
                await loop.run_in_executor(ex, cb, _wrap(s), arg)
            return hook

        def _make_hook_2(cb: Callable[..., None] | None):
            if cb is None:
                return None
            async def hook(s: TrexSession, a: Any, b: Any) -> None:
                await loop.run_in_executor(ex, cb, _wrap(s), a, b)
            return hook

        async def _main() -> None:
            srv = TrexServer(
                host=self._host, port=self._port, max_clients=self._max
            )
            def _make_hook_3(cb):
                if cb is None:
                    return None
                async def hook(s: TrexSession, a: Any, b: Any, c: Any) -> None:
                    await loop.run_in_executor(ex, cb, _wrap(s), a, b, c)
                return hook

            def _make_hook_4(cb):
                if cb is None:
                    return None
                async def hook(s: TrexSession, a: Any, b: Any, c: Any, d: Any) -> None:
                    await loop.run_in_executor(ex, cb, _wrap(s), a, b, c, d)
                return hook

            srv._on_connect         = _make_hook_0(self._on_connect)   # type: ignore[assignment]
            srv._on_disconnect      = _make_hook_0(self._on_disconnect)  # type: ignore[assignment]
            srv._on_symbol          = _make_hook_1(self._on_symbol)   # type: ignore[assignment]
            srv._on_timeframe       = _make_hook_1(self._on_timeframe)  # type: ignore[assignment]
            srv._on_chart_type      = _make_hook_1(self._on_chart_type)  # type: ignore[assignment]
            srv._on_history         = _make_hook_2(self._on_history)   # type: ignore[assignment]
            srv._on_drawing_upsert  = _make_hook_1(self._on_drawing_upsert)  # type: ignore[assignment]
            srv._on_drawing_delete  = _make_hook_1(self._on_drawing_delete)  # type: ignore[assignment]
            srv._on_drawings_clear  = _make_hook_0(self._on_drawings_clear)  # type: ignore[assignment]
            srv._on_message         = _make_hook_2(self._on_message)   # type: ignore[assignment]
            srv._on_get_symbols     = _make_hook_0(self._on_get_symbols)  # type: ignore[assignment]
            srv._on_get_indicators  = _make_hook_0(self._on_get_indicators)  # type: ignore[assignment]
            srv._on_layout          = _make_hook_2(self._on_layout)   # type: ignore[assignment]
            srv._on_chart_symbol    = _make_hook_4(self._on_chart_symbol)  # type: ignore[assignment]
            srv._on_chart_history   = _make_hook_3(self._on_chart_history)  # type: ignore[assignment]

            self._async_srv = srv
            self._ready.set()
            await srv.serve()

        try:
            loop.run_until_complete(_main())
        except Exception as exc:
            log.error("server loop error: %s", exc)
        finally:
            loop.close()


__all__ = ["SyncServer", "SyncSession"]
