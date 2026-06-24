"""
trex.application.session
========================
One connected Trex Terminal client.

``TrexSession`` wraps a single WebSocket connection and exposes:

- **Send methods** for every server→client protocol message.
- **Dispatch** for every client→server message type (ping, hello, history,
  symbol, timeframe, chartType, drawing_*).
- **Session state** (symbol, timeframe, chart_type, client metadata).

Typed callbacks
---------------
All callbacks use precise ``Protocol`` types so callers get full IDE
completion and ``mypy --strict`` compliance::

    async def handle_history(
        session: TrexSession, before: int, count: int
    ) -> None:
        page = store.history_page(before, count)
        await session.push_history(page, no_more=len(page) == 0)

Threading
---------
``TrexSession`` is **async-native**.  If you need a blocking API, use
``SyncSession`` from ``trex.infrastructure.sync``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from websockets import ServerConnection

from trex.domain.types import (
    Bar,
    ChartType,
    Drawing,
    Point,
    SeriesDef,
    ToastKind,
)

log = logging.getLogger("trex.session")


# ── Callback Protocols (strict typing for all hooks) ──────────────────────────

@runtime_checkable
class OnConnectCB(Protocol):
    async def __call__(self, session: "TrexSession") -> None: ...


@runtime_checkable
class OnDisconnectCB(Protocol):
    async def __call__(self, session: "TrexSession") -> None: ...


@runtime_checkable
class OnSymbolCB(Protocol):
    async def __call__(self, session: "TrexSession", symbol: str) -> None: ...


@runtime_checkable
class OnTimeframeCB(Protocol):
    async def __call__(self, session: "TrexSession", timeframe: str) -> None: ...


@runtime_checkable
class OnChartTypeCB(Protocol):
    async def __call__(self, session: "TrexSession", chart_type: ChartType) -> None: ...


@runtime_checkable
class OnHistoryCB(Protocol):
    async def __call__(
        self, session: "TrexSession", before: int, count: int
    ) -> None: ...


@runtime_checkable
class OnDrawingUpsertCB(Protocol):
    async def __call__(self, session: "TrexSession", drawing: dict[str, Any]) -> None: ...


@runtime_checkable
class OnDrawingDeleteCB(Protocol):
    async def __call__(self, session: "TrexSession", ids: list[str]) -> None: ...


@runtime_checkable
class OnDrawingsClearCB(Protocol):
    async def __call__(self, session: "TrexSession") -> None: ...


@runtime_checkable
class OnGetSymbolsCB(Protocol):
    async def __call__(self, session: "TrexSession") -> None: ...


@runtime_checkable
class OnGetIndicatorsCB(Protocol):
    async def __call__(self, session: "TrexSession") -> None: ...


@runtime_checkable
class OnLayoutCB(Protocol):
    async def __call__(
        self, session: "TrexSession", layout: str, charts: list[dict[str, Any]]
    ) -> None: ...


@runtime_checkable
class OnChartSymbolCB(Protocol):
    async def __call__(
        self, session: "TrexSession", chart_id: str, symbol: str,
        timeframe: str | None, indicators: list[str],
    ) -> None: ...


@runtime_checkable
class OnChartHistoryCB(Protocol):
    async def __call__(
        self, session: "TrexSession", chart_id: str, before: int, count: int
    ) -> None: ...


@runtime_checkable
class OnMessageCB(Protocol):
    async def __call__(self, session: "TrexSession", msg: dict[str, Any]) -> None: ...


@runtime_checkable
class OnBtPlaybackCB(Protocol):
    async def __call__(self, session: "TrexSession", action: str, value: float | None) -> None: ...


# ── Helpers ───────────────────────────────────────────────────────────────────

def _dump(obj: Any) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


# ── Session ───────────────────────────────────────────────────────────────────


class TrexSession:
    """
    One connected Trex Terminal client.

    All ``push_*`` / control methods are coroutines returning ``bool``
    (``True`` = frame sent successfully, ``False`` = socket dead or error).

    Attributes
    ----------
    id:
        Random UUID for this connection.
    symbol:
        Last symbol received from the client (hello or symbol message).
    timeframe:
        Last timeframe received from the client.
    chart_type:
        Current chart type (``"candles"`` until overridden by the client).
    client_name:
        Value from the hello handshake.
    client_version:
        Value from the hello handshake.
    remote:
        ``"host:port"`` string of the connected peer.
    connected_at:
        Unix timestamp (float) of when the session was created.
    message_count:
        Total messages dispatched from this client.
    """

    __slots__ = (
        "_ws",
        "id",
        "symbol",
        "timeframe",
        "chart_type",
        "client_name",
        "client_version",
        "remote",
        "connected_at",
        "message_count",
        "_alive",
        "_send_lock",
        # callbacks (set by TrexServer)
        "_on_history",
        "_on_symbol",
        "_on_timeframe",
        "_on_chart_type",
        "_on_drawing_upsert",
        "_on_drawing_delete",
        "_on_drawings_clear",
        "_on_message",
        "_on_get_symbols",
        "_on_get_indicators",
        "_on_layout",
        "_on_chart_symbol",
        "_on_chart_history",
        "_on_bt_playback",
        # per-session secondary chart state: {chartId: {symbol, timeframe}}
        "_charts",
    )

    def __init__(self, ws: "ServerConnection") -> None:
        self._ws                  = ws
        self.id: str              = str(uuid.uuid4())
        self.symbol:       str | None = None
        self.timeframe:    str | None = None
        self.chart_type:   str        = "candles"
        self.client_name:  str        = ""
        self.client_version: str      = ""

        addr = ws.remote_address
        self.remote: str = f"{addr[0]}:{addr[1]}" if addr else "unknown"

        self.connected_at:  float = time.monotonic()
        self.message_count: int   = 0
        self._alive: bool         = True
        self._send_lock           = asyncio.Lock()

        # Callbacks — populated by TrexServer before the session is exposed
        self._on_history:        OnHistoryCB | None        = None
        self._on_symbol:         OnSymbolCB | None         = None
        self._on_timeframe:      OnTimeframeCB | None      = None
        self._on_chart_type:     OnChartTypeCB | None      = None
        self._on_drawing_upsert:  OnDrawingUpsertCB | None   = None
        self._on_drawing_delete:  OnDrawingDeleteCB | None   = None
        self._on_drawings_clear:  OnDrawingsClearCB | None   = None
        self._on_message:         OnMessageCB | None         = None
        self._on_get_symbols:     OnGetSymbolsCB | None      = None
        self._on_get_indicators:  OnGetIndicatorsCB | None   = None
        self._on_layout:          OnLayoutCB | None          = None
        self._on_chart_symbol:    OnChartSymbolCB | None     = None
        self._on_chart_history:   OnChartHistoryCB | None    = None
        self._on_bt_playback:     OnBtPlaybackCB | None      = None
        # secondary chart state: {chartId: {"symbol": str, "timeframe": str}}
        self._charts: dict[str, dict[str, str]] = {}

    # ── Internal send ─────────────────────────────────────────────────────────

    async def _send(self, payload: dict[str, Any]) -> bool:
        """Serialise *payload* and send it. Returns ``False`` on any error."""
        if not self._alive:
            return False
        try:
            async with self._send_lock:
                await self._ws.send(_dump(payload))
            return True
        except Exception as exc:
            log.debug("[%s] send failed: %s", self.id[:8], exc)
            self._alive = False
            return False

    # ── Dispatch ──────────────────────────────────────────────────────────────

    async def _dispatch(self, msg: dict[str, Any]) -> None:
        """Route one incoming client message to the appropriate callback."""
        self.message_count += 1
        t = msg.get("type", "")

        try:
            if t == "ping":
                await self._send({"type": "pong", "t": msg.get("t")})

            elif t == "hello":
                self.symbol          = msg.get("symbol") or None
                self.timeframe       = msg.get("timeframe") or None
                self.client_name     = str(msg.get("client", ""))
                self.client_version  = str(msg.get("version", ""))
                # Validate protocol version: reject incompatible major versions
                proto = str(msg.get("protocol", ""))
                if proto:
                    try:
                        client_major = int(proto.split(".")[0])
                        if client_major != 2:
                            await self._send({
                                "type":    "error",
                                "code":    "PROTOCOL_MISMATCH",
                                "message": f"Protocol major version {client_major} not supported; server requires 2.x",
                            })
                            self._alive = False
                            return
                    except (ValueError, IndexError):
                        pass

            elif t == "symbol":
                self.symbol = str(msg.get("symbol", "")) or None
                if self._on_symbol and self.symbol:
                    await self._on_symbol(self, self.symbol)

            elif t == "timeframe":
                self.timeframe = str(msg.get("timeframe", "")) or None
                if self._on_timeframe and self.timeframe:
                    await self._on_timeframe(self, self.timeframe)

            elif t == "chartType":
                ct = msg.get("chartType", "candles")
                self.chart_type = str(ct)
                if self._on_chart_type:
                    await self._on_chart_type(self, ct)  # type: ignore[arg-type]

            elif t == "history":
                before = int(msg.get("before", 0))
                count  = int(msg.get("count", 300))
                chart_id = msg.get("chartId")
                if chart_id and self._on_chart_history:
                    await self._on_chart_history(self, str(chart_id), before, count)  # type: ignore[arg-type]
                elif self._on_history:
                    await self._on_history(self, before, count)

            elif t == "drawing_upsert":
                if self._on_drawing_upsert:
                    drawing = msg.get("drawing", {})
                    await self._on_drawing_upsert(self, drawing)  # type: ignore[arg-type]

            elif t == "drawing_delete":
                if self._on_drawing_delete:
                    # Protocol sends drawingId (singular) or drawingIds (plural)
                    ids: list[str] = (
                        msg.get("drawingIds")  # type: ignore[assignment]
                        or ([msg["drawingId"]] if "drawingId" in msg else [])
                    )
                    await self._on_drawing_delete(self, ids)

            elif t == "drawings_clear":
                if self._on_drawings_clear:
                    await self._on_drawings_clear(self)

            elif t == "drawings":
                # Full drawings sync from client (after undo/redo)
                if self._on_drawing_upsert:
                    for d in msg.get("drawings", []):
                        await self._on_drawing_upsert(self, d)  # type: ignore[arg-type]

            elif t == "get_symbols":
                if self._on_get_symbols:
                    await self._on_get_symbols(self)

            elif t == "get_indicators":
                if self._on_get_indicators:
                    await self._on_get_indicators(self)

            elif t == "layout":
                charts = msg.get("charts", [])
                layout = str(msg.get("layout", "single"))
                # Update secondary chart state from layout
                for c in charts:
                    cid = c.get("chartId", "")
                    if cid and cid != "main":
                        self._charts[cid] = {
                            "symbol":    str(c.get("symbol", "")),
                            "timeframe": str(c.get("timeframe", self.timeframe or "")),
                        }
                if self._on_layout:
                    await self._on_layout(self, layout, charts)  # type: ignore[arg-type]

            elif t == "chart_symbol":
                chart_id = str(msg.get("chartId", ""))
                symbol   = str(msg.get("symbol", ""))
                tf       = msg.get("timeframe") or None
                inds     = list(msg.get("indicators", []))
                if chart_id:
                    self._charts[chart_id] = {
                        "symbol":    symbol,
                        "timeframe": tf or (self.timeframe or ""),
                    }
                if self._on_chart_symbol and chart_id and symbol:
                    await self._on_chart_symbol(self, chart_id, symbol, tf, inds)  # type: ignore[arg-type]

            elif t == "bt_playback":
                if self._on_bt_playback:
                    action = str(msg.get("action", ""))
                    value  = msg.get("value")
                    await self._on_bt_playback(self, action, value)  # type: ignore[arg-type]

        except Exception:
            log.exception("[%s] dispatch error (type=%s)", self.id[:8], t)

        # Always call the catch-all after built-ins
        if self._on_message:
            try:
                await self._on_message(self, msg)
            except Exception:
                log.exception("[%s] on_message error", self.id[:8])

    # ── Snapshot ──────────────────────────────────────────────────────────────

    async def snapshot(
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
        """
        Send the full initial payload for a symbol/timeframe.

        Parameters
        ----------
        bars:
            OHLCV history, **oldest-first**.
        symbol / timeframe:
            Override the label shown in the terminal header.
        digits:
            Price decimal places for the Y-axis.
        definitions:
            Indicator series display contracts.
        indicators:
            Pre-computed indicator data keyed by ``SeriesDef.key``.
        drawings:
            Server-side drawing objects (rendered read-only).
        """
        msg: dict[str, Any] = {
            "type":   "snapshot",
            "data":   [b.to_wire() for b in bars],
            "digits": digits,
        }
        if symbol:      msg["symbol"]      = symbol
        if timeframe:   msg["timeframe"]   = timeframe
        if definitions: msg["definitions"] = [d.to_wire() for d in definitions]
        if indicators:
            msg["points"] = {
                k: [p.to_wire() for p in v] for k, v in indicators.items()
            }
        if drawings:
            msg["drawings"] = [d.to_wire() for d in drawings]
        return await self._send(msg)

    # ── Live bar ──────────────────────────────────────────────────────────────

    async def push_bar(self, bar: Bar) -> bool:
        """
        Push one realtime bar.

        Same timestamp → updates in place.  Newer timestamp → appends a
        new candle.
        """
        return await self._send({"type": "bar", "bar": bar.to_wire()})

    # ── History reply ─────────────────────────────────────────────────────────

    async def push_history(
        self, bars: list[Bar], *, no_more: bool = False
    ) -> bool:
        """
        Reply to a ``history`` (lazy-load) request.

        Parameters
        ----------
        bars:
            Bars older than the requested ``before`` timestamp, oldest-first.
        no_more:
            ``True`` when there is no older history.  An empty ``bars`` list
            also implies ``no_more``.
        """
        return await self._send({
            "type":           "history",
            "data":           [b.to_wire() for b in bars],
            "noMoreHistory":  no_more or len(bars) == 0,
        })

    # ── Indicators ────────────────────────────────────────────────────────────

    async def define(self, *defs: SeriesDef) -> bool:
        """
        Send / update indicator series definitions.

        A single call may carry multiple definitions.
        Call before or alongside ``push_indicators()``.
        """
        return await self._send({
            "type":        "definitions",
            "definitions": [d.to_wire() for d in defs],
        })

    async def push_indicators(
        self, data: dict[str, list[Point]]
    ) -> bool:
        """
        Push indicator values.

        A **single-element list** per key triggers the O(1) realtime tail
        update.  A longer list replaces the whole series.
        """
        return await self._send({
            "type":   "indicators",
            "points": {k: [p.to_wire() for p in v] for k, v in data.items()},
        })

    # ── Drawings ──────────────────────────────────────────────────────────────

    async def set_drawings(self, drawings: list[Drawing]) -> bool:
        """Replace all server-side drawings on the chart."""
        return await self._send({
            "type":     "drawings",
            "drawings": [d.to_wire() for d in drawings],
        })

    async def upsert_drawing(self, drawing: Drawing) -> bool:
        """Add or update a single server-side drawing."""
        return await self._send({
            "type":    "drawing_upsert",
            "drawing": drawing.to_wire(),
        })

    async def delete_drawing(self, *ids: str) -> bool:
        """Delete one or more server-side drawings by id."""
        return await self._send({
            "type":       "drawing_delete",
            "drawingIds": list(ids),
        })

    async def clear_drawings(self) -> bool:
        """Remove all server-side drawings."""
        return await self._send({"type": "drawings_clear"})

    # ── Symbol / Indicator lists ───────────────────────────────────────────────

    async def send_symbols_list(
        self, symbols: list[dict[str, Any]]
    ) -> bool:
        """Reply to get_symbols. Each entry: {symbol, name?, type?}."""
        return await self._send({"type": "symbols_list", "symbols": symbols})

    async def send_indicators_list(self, defs: list[SeriesDef]) -> bool:
        """Reply to get_indicators with all streamable SeriesDefinitions."""
        return await self._send({
            "type":       "indicators_list",
            "indicators": [d.to_wire() for d in defs],
        })

    # ── Multi-chart (secondary charts) ────────────────────────────────────────

    async def chart_snapshot(
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
        """Send a snapshot for a secondary chart."""
        msg: dict[str, Any] = {
            "type":    "chart_snapshot",
            "chartId": chart_id,
            "data":    [b.to_wire() for b in bars],
            "digits":  digits,
        }
        if symbol:      msg["symbol"]      = symbol
        if timeframe:   msg["timeframe"]   = timeframe
        if definitions: msg["definitions"] = [d.to_wire() for d in definitions]
        if indicators:
            msg["points"] = {
                k: [p.to_wire() for p in v] for k, v in indicators.items()
            }
        return await self._send(msg)

    async def push_chart_bar(self, chart_id: str, bar: Bar) -> bool:
        """Push a live bar update for a secondary chart."""
        return await self._send({
            "type":    "chart_bar",
            "chartId": chart_id,
            "bar":     bar.to_wire(),
        })

    async def push_chart_history(
        self, chart_id: str, bars: list[Bar], *, no_more: bool = False
    ) -> bool:
        """Reply to a secondary-chart history request."""
        return await self._send({
            "type":          "chart_history",
            "chartId":       chart_id,
            "data":          [b.to_wire() for b in bars],
            "noMoreHistory": no_more or len(bars) == 0,
        })

    # ── Chart control ─────────────────────────────────────────────────────────

    async def set_symbol(self, symbol: str) -> bool:
        """Remotely update the symbol label in the terminal header."""
        return await self._send({"type": "symbol", "symbol": symbol})

    async def set_timeframe(self, tf: str) -> bool:
        """Remotely update the timeframe label in the terminal header."""
        return await self._send({"type": "timeframe", "timeframe": tf})

    async def set_chart_type(self, ct: ChartType) -> bool:
        """Remotely switch the chart type (candles / heikin / line / …)."""
        return await self._send({"type": "chartType", "chartType": ct})

    async def set_magnet(self, on: bool) -> bool:
        """Toggle magnet-snap mode on the terminal."""
        return await self._send({"type": "magnet", "magnet": on})

    async def set_settings(self, **kw: Any) -> bool:
        """
        Patch chart appearance settings.

        Valid keys: ``showGrid``, ``showVolume``, ``showCrosshair``,
        ``candleUpColor``, ``candleDownColor``, ``backgroundColor``,
        ``gridColor``.
        """
        return await self._send({"type": "settings", "settings": kw})

    # ── View control ──────────────────────────────────────────────────────────

    async def fit_content(self) -> bool:
        """Zoom the chart to fit all visible bars."""
        return await self._send({"type": "fitContent"})

    async def scroll_to_end(self) -> bool:
        """Scroll the chart to the most recent bar."""
        return await self._send({"type": "scrollToEnd"})

    async def zoom_range(self, from_ts: int, to_ts: int) -> bool:
        """
        Zoom the chart to a specific time range.

        Parameters
        ----------
        from_ts / to_ts:
            Unix-second bounds of the desired view.
        """
        return await self._send({
            "type":      "zoomRange",
            "zoomRange": {"from": from_ts, "to": to_ts},
        })

    # ── Notifications ─────────────────────────────────────────────────────────

    async def toast(self, msg: str, kind: ToastKind = "info") -> bool:
        """Display a toast notification on the terminal."""
        return await self._send({
            "type":      "toast",
            "message":   msg,
            "toastType": kind,
        })

    async def alert(self, msg: str) -> bool:
        """Display an error alert on the terminal."""
        return await self._send({"type": "error", "message": msg})

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def uptime(self) -> float:
        """Seconds elapsed since this session connected."""
        return time.monotonic() - self.connected_at

    @property
    def alive(self) -> bool:
        """``True`` while the underlying WebSocket is open."""
        return self._alive

    def __repr__(self) -> str:
        return (
            f"TrexSession(id={self.id[:8]}, remote={self.remote}, "
            f"symbol={self.symbol!r}, tf={self.timeframe!r}, "
            f"alive={self._alive})"
        )


__all__ = [
    "TrexSession",
    # Callback Protocols (for typed annotations in user code)
    "OnConnectCB", "OnDisconnectCB",
    "OnSymbolCB", "OnTimeframeCB", "OnChartTypeCB",
    "OnHistoryCB",
    "OnDrawingUpsertCB", "OnDrawingDeleteCB", "OnDrawingsClearCB",
    "OnMessageCB",
    "OnGetSymbolsCB", "OnGetIndicatorsCB",
    "OnLayoutCB", "OnChartSymbolCB", "OnChartHistoryCB",
    "OnBtPlaybackCB",
]
