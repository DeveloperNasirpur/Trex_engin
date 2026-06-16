"""
trex.application.server
=======================
Async WebSocket server for Trex Terminal.

``TrexServer`` manages connections, dispatches all client→server messages,
and provides typed broadcast utilities.

Usage
-----
::

    import asyncio
    from trex import TrexServer, CandleStore, Bar

    store  = CandleStore()
    server = TrexServer()

    @server.on_connect
    async def connected(session):
        await session.snapshot(store.recent(500), symbol="BTCUSDT", timeframe="1m")
        await session.fit_content()

    @server.on_history
    async def history(session, before, count):
        page = store.history_page(before, count)
        await session.push_history(page, no_more=len(page) == 0)

    asyncio.run(server.serve())
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

import websockets
from websockets import serve as ws_serve

from trex.server.session import (
    TrexSession,
    OnConnectCB, OnDisconnectCB,
    OnSymbolCB, OnTimeframeCB, OnChartTypeCB,
    OnHistoryCB,
    OnDrawingUpsertCB, OnDrawingDeleteCB, OnDrawingsClearCB,
    OnMessageCB,
)
from trex.domain.types import Bar, Point, SeriesDef, Drawing, ToastKind

log = logging.getLogger("trex.server")


class TrexServer:
    """
    Async WebSocket server for Trex Terminal.

    Event hooks (all async, all optional)
    --------------------------------------
    Register them with the decorator API::

        @server.on_connect
        async def handle(session: TrexSession) -> None: ...

    All hook signatures are typed via ``Protocol`` classes in
    ``trex.application.session``.

    Parameters
    ----------
    host:
        Bind address. Defaults to ``"0.0.0.0"`` (all interfaces).
    port:
        TCP port. Defaults to ``8765``.
    max_clients:
        Maximum concurrent connections. ``0`` = unlimited.
    ping_interval:
        WebSocket-level keepalive interval in seconds. ``None`` to disable.
    """

    def __init__(
        self,
        host:          str      = "0.0.0.0",
        port:          int      = 8765,
        max_clients:   int      = 0,
        ping_interval: int | None = 20,
    ) -> None:
        self.host        = host
        self.port        = port
        self.max_clients = max_clients
        self._ping_ivl   = ping_interval

        self._sessions: dict[str, TrexSession] = {}
        self._lock       = asyncio.Lock()

        # Typed hooks
        self._on_connect:        OnConnectCB | None        = None
        self._on_disconnect:     OnDisconnectCB | None     = None
        self._on_symbol:         OnSymbolCB | None         = None
        self._on_timeframe:      OnTimeframeCB | None      = None
        self._on_chart_type:     OnChartTypeCB | None      = None
        self._on_history:        OnHistoryCB | None        = None
        self._on_drawing_upsert: OnDrawingUpsertCB | None  = None
        self._on_drawing_delete: OnDrawingDeleteCB | None  = None
        self._on_drawings_clear: OnDrawingsClearCB | None  = None
        self._on_message:        OnMessageCB | None        = None

    # ── Decorator API ─────────────────────────────────────────────────────────

    def on_connect(self, fn: OnConnectCB) -> OnConnectCB:
        """Called once per client after the hello handshake completes."""
        self._on_connect = fn
        return fn

    def on_disconnect(self, fn: OnDisconnectCB) -> OnDisconnectCB:
        """Called when a client disconnects (cleanly or by error)."""
        self._on_disconnect = fn
        return fn

    def on_symbol(self, fn: OnSymbolCB) -> OnSymbolCB:
        """Called when the user changes the symbol. Signature: (session, symbol)."""
        self._on_symbol = fn
        return fn

    def on_timeframe(self, fn: OnTimeframeCB) -> OnTimeframeCB:
        """Called when the user changes the timeframe. Signature: (session, tf)."""
        self._on_timeframe = fn
        return fn

    def on_chart_type(self, fn: OnChartTypeCB) -> OnChartTypeCB:
        """Called when the user switches chart type. Signature: (session, chart_type)."""
        self._on_chart_type = fn
        return fn

    def on_history(self, fn: OnHistoryCB) -> OnHistoryCB:
        """
        Called when the terminal needs older candles (user scrolled left).

        Signature: ``(session, before: int, count: int)``

        Call ``await session.push_history(bars)`` inside.
        """
        self._on_history = fn
        return fn

    def on_drawing_upsert(self, fn: OnDrawingUpsertCB) -> OnDrawingUpsertCB:
        """
        Called when the user creates or edits a local drawing.

        Signature: ``(session, drawing: dict)``

        Use this to persist user drawings server-side.
        """
        self._on_drawing_upsert = fn
        return fn

    def on_drawing_delete(self, fn: OnDrawingDeleteCB) -> OnDrawingDeleteCB:
        """
        Called when the user deletes one or more local drawings.

        Signature: ``(session, ids: list[str])``
        """
        self._on_drawing_delete = fn
        return fn

    def on_drawings_clear(self, fn: OnDrawingsClearCB) -> OnDrawingsClearCB:
        """
        Called when the user clears all local drawings.

        Signature: ``(session,)``
        """
        self._on_drawings_clear = fn
        return fn

    def on_message(self, fn: OnMessageCB) -> OnMessageCB:
        """Called for every incoming message (after built-in handlers)."""
        self._on_message = fn
        return fn

    # ── Session registry ──────────────────────────────────────────────────────

    @property
    def sessions(self) -> list[TrexSession]:
        """All currently live sessions."""
        return [s for s in self._sessions.values() if s._alive]

    @property
    def client_count(self) -> int:
        """Number of connected clients."""
        return len(self.sessions)

    def get_session(self, session_id: str) -> TrexSession | None:
        """Look up a session by its UUID."""
        return self._sessions.get(session_id)

    def sessions_for(
        self, symbol: str, timeframe: str | None = None
    ) -> list[TrexSession]:
        """
        Return all live sessions watching a given symbol (and optionally TF).
        """
        return [
            s for s in self.sessions
            if s.symbol == symbol
            and (timeframe is None or s.timeframe == timeframe)
        ]

    # ── Broadcast ─────────────────────────────────────────────────────────────

    async def broadcast_bar(
        self,
        bar:    Bar,
        filter: Callable[[TrexSession], bool] | None = None,
    ) -> int:
        """
        Send a realtime bar to connected clients.

        Parameters
        ----------
        bar:
            The bar to broadcast.
        filter:
            Optional predicate — send only to sessions where it returns
            ``True``.  Example: ``lambda s: s.symbol == "BTCUSDT"``

        Returns
        -------
        int
            Number of clients that received the frame.
        """
        payload = json.dumps(
            {"type": "bar", "bar": bar.to_wire()},
            separators=(",", ":"), ensure_ascii=False,
        )
        sent = 0
        for s in self.sessions:
            if filter and not filter(s):
                continue
            try:
                async with s._send_lock:
                    await s._ws.send(payload)
                sent += 1
            except Exception:
                s._alive = False
        return sent

    async def broadcast(
        self,
        payload: dict[str, Any],
        filter:  Callable[[TrexSession], bool] | None = None,
    ) -> int:
        """Send an arbitrary payload to connected clients (optionally filtered)."""
        raw  = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
        sent = 0
        for s in self.sessions:
            if filter and not filter(s):
                continue
            try:
                async with s._send_lock:
                    await s._ws.send(raw)
                sent += 1
            except Exception:
                s._alive = False
        return sent

    async def broadcast_indicators(
        self,
        data:   dict[str, list[Point]],
        filter: Callable[[TrexSession], bool] | None = None,
    ) -> int:
        """Push indicator data to clients (optionally filtered)."""
        return await self.broadcast(
            {
                "type":   "indicators",
                "points": {k: [p.to_wire() for p in v] for k, v in data.items()},
            },
            filter=filter,
        )

    async def broadcast_toast(
        self,
        msg:    str,
        kind:   ToastKind = "info",
        filter: Callable[[TrexSession], bool] | None = None,
    ) -> int:
        """Broadcast a toast notification to all (or filtered) clients."""
        return await self.broadcast(
            {"type": "toast", "message": msg, "toastType": kind},
            filter=filter,
        )

    # ── Connection handler ────────────────────────────────────────────────────

    async def _handle(self, ws: Any) -> None:  # ws: ServerConnection
        if self.max_clients and len(self.sessions) >= self.max_clients:
            await ws.close(1013, "server full")
            return

        session = TrexSession(ws)

        # Wire all hooks into the session
        session._on_history        = self._on_history
        session._on_symbol         = self._on_symbol
        session._on_timeframe      = self._on_timeframe
        session._on_chart_type     = self._on_chart_type
        session._on_drawing_upsert = self._on_drawing_upsert
        session._on_drawing_delete = self._on_drawing_delete
        session._on_drawings_clear = self._on_drawings_clear
        session._on_message        = self._on_message

        log.info("connect  %-21s [%s]", session.remote, session.id[:8])

        # Handshake — wait up to 10 s for the hello frame
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
            await session._dispatch(json.loads(raw))
        except (asyncio.TimeoutError, json.JSONDecodeError):
            pass
        except Exception as exc:
            log.debug("[%s] hello error: %s", session.id[:8], exc)

        async with self._lock:
            self._sessions[session.id] = session

        # Fire on_connect in its own task so errors don't kill the recv loop
        connect_task: asyncio.Task[None] | None = None
        if self._on_connect:
            connect_task = asyncio.create_task(
                self._on_connect(session),
                name=f"trex-connect-{session.id[:8]}",
            )

        # Receive loop
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                await session._dispatch(msg)
        except Exception as exc:
            log.debug("[%s] recv closed: %s", session.id[:8], exc)
        finally:
            session._alive = False
            async with self._lock:
                self._sessions.pop(session.id, None)

            if connect_task and not connect_task.done():
                connect_task.cancel()
                try:
                    await connect_task
                except (asyncio.CancelledError, Exception):
                    pass

            elapsed = round(time.monotonic() - session.connected_at, 1)
            log.info(
                "disconnect %-21s [%s] after %.1fs  msgs=%d",
                session.remote, session.id[:8], elapsed, session.message_count,
            )

            if self._on_disconnect:
                try:
                    await self._on_disconnect(session)
                except Exception:
                    log.exception("[%s] on_disconnect error", session.id[:8])

    # ── Serve ─────────────────────────────────────────────────────────────────

    async def serve(self) -> None:
        """Start the server and run until the event loop is cancelled."""
        log.info(
            "Trex  ws://%s:%d  (protocol %s)",
            self.host, self.port, "2.0.0",
        )
        async with ws_serve(
            self._handle,
            self.host,
            self.port,
            ping_interval=self._ping_ivl,
            ping_timeout=10,
            close_timeout=5,
        ):
            await asyncio.Future()  # run forever


__all__ = ["TrexServer"]
