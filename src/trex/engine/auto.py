"""
trex.engine.auto
================
AutoEngine — zero-boilerplate facade.

The user only needs three things:

    import trex

    trex.init(timezone="Asia/Tehran", port=8765)

    trex.rsi("BTCUSDT", "1m", period=14, visible=True, listener=on_rsi)
    trex.ema("BTCUSDT", "1m", period=20, visible=True)

    trex.seed(historical_bars, symbol="BTCUSDT")   # optional pre-load

    # in feed loop:
    trex.push(bar, symbol="BTCUSDT")

AutoEngine automatically manages:
- WebSocket server (SyncServer) on the configured port
- In-memory bar store (MultiSymbolStore) per (symbol, timeframe)
- on_connect  → snapshot(bars + definitions + indicator cache)
- on_history  → paginated history
- on_symbol   → re-snapshot for the new symbol
- on_timeframe → re-snapshot for the new timeframe
- per-indicator broadcast + store-cache update on every emit
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from trex.engine.indicator import Indicator
    from trex.domain.types import Bar, Point, SeriesDef

log = logging.getLogger("trex.auto")

# Module-level singleton — set by trex.init()
_engine: "AutoEngine | None" = None


class AutoEngine:
    """
    Orchestrates SyncServer + MultiSymbolStore + ctx with zero user boilerplate.

    Never instantiate directly — use trex.init().
    """

    def __init__(
        self,
        *,
        port: int            = 8765,
        host: str            = "0.0.0.0",
        max_bars: int        = 10_000,
        source_timeframe: str = "1m",
        snapshot_size: int   = 500,
    ) -> None:
        from trex.server.store import MultiSymbolStore
        from trex.server.sync import SyncServer

        self._source_tf    = source_timeframe
        self._snapshot_sz  = snapshot_size
        self._store        = MultiSymbolStore(max_bars=max_bars)
        self._server       = SyncServer(host=host, port=port)
        self._definitions: list["SeriesDef"] = []
        self._def_lock     = threading.Lock()

        # Wire server event hooks before start()
        self._server._on_connect   = self._on_connect    # type: ignore[assignment]
        self._server._on_history   = self._on_history    # type: ignore[assignment]
        self._server._on_symbol    = self._on_symbol     # type: ignore[assignment]
        self._server._on_timeframe = self._on_timeframe  # type: ignore[assignment]

    # ── Event handlers (called by SyncServer in its thread-pool) ──────────────

    def _on_connect(self, session: Any) -> None:
        sym = (session.symbol or "").upper()
        tf  = session.timeframe or self._source_tf
        self._send_snapshot(session, sym, tf)

    def _on_history(self, session: Any, before: int, count: int) -> None:
        sym  = (session.symbol or "").upper()
        tf   = session.timeframe or self._source_tf
        page = self._store.history_page(sym, tf, before=before, count=count)
        session.push_history(page, no_more=len(page) == 0)

    def _on_symbol(self, session: Any, symbol: str) -> None:
        sym = symbol.upper()
        tf  = session.timeframe or self._source_tf
        self._send_snapshot(session, sym, tf)

    def _on_timeframe(self, session: Any, tf: str) -> None:
        sym = (session.symbol or "").upper()
        self._send_snapshot(session, sym, tf)

    def _send_snapshot(self, session: Any, symbol: str, tf: str) -> None:
        store = self._store.get_store(symbol, tf)
        bars  = store.recent(self._snapshot_sz)
        defs  = list(self._definitions) or None
        cache = dict(store.indicator_cache) or None
        session.snapshot(
            bars,
            symbol    = symbol or None,
            timeframe = tf,
            definitions = defs,
            indicators  = cache,
        )
        session.fit_content()

    # ── Indicator wiring ───────────────────────────────────────────────────────

    def wire_indicator(self, symbol: str, ind: "Indicator") -> None:
        """
        Wire one indicator into the auto-broadcast + store-cache pipeline.

        Called automatically by _register() after every trex.ema() / trex.rsi() / etc.
        """
        _symbol = symbol.upper()
        _tf     = ind.tf
        _store  = self._store
        _server = self._server

        def _hook(data: "dict[str, list[Point]]") -> None:
            # 1. Broadcast realtime indicator data to all connected clients
            _server.broadcast_indicators(data)
            # 2. Update store cache so new clients get values in their snapshot
            tails = {k: pts[-1] for k, pts in data.items() if pts}
            _store.update_indicator_tails(_symbol, _tf, tails)

        ind._set_emit_hook(_hook)
        log.debug("Wired  %s  [%s %s]", ind.__class__.__name__, _symbol, _tf)

        # If visible=True, add SeriesDefs so terminal knows how to render
        if getattr(ind, "_visible", False):
            with self._def_lock:
                existing = {d.key for d in self._definitions}
                for sdef in ind.series_defs():
                    if sdef.key not in existing:
                        self._definitions.append(sdef)
                        existing.add(sdef.key)

    # ── Public feed API ────────────────────────────────────────────────────────

    def push(self, bar: "Bar", symbol: str, timeframe: str | None = None) -> None:
        """
        Feed one bar: update store → provide to engine → broadcast to clients.

        This is the only method the user needs to call in their feed loop.
        """
        from trex.base.ohlcv import OHLCV
        from trex.engine.context import ctx

        sym = symbol.upper()
        tf  = timeframe or self._source_tf

        # 1. Update the in-memory bar store
        self._store.update(sym, tf, bar)

        # 2. Route through CTF converters + indicators (synchronous)
        ctx.provide(OHLCV.from_bar(bar, symbol=sym, str_time=tf))

        # 3. Broadcast the raw bar to clients watching this symbol
        _sym = sym
        self._server.broadcast_bar(
            bar,
            filter=lambda s: (s.symbol or "").upper() == _sym,
        )

    def seed(self, bars: "list[Bar]", symbol: str, timeframe: str | None = None) -> None:
        """Bulk-load historical bars into the store (call once at startup)."""
        sym = symbol.upper()
        tf  = timeframe or self._source_tf
        self._store.seed(sym, tf, bars)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._server.start()
        log.info(
            "TrexEngine  ws://%s:%d  (max_bars=%d)",
            self._server._host,
            self._server._port,
            self._store._max,
        )

    def stop(self) -> None:
        self._server.stop()
        log.info("TrexEngine stopped")

    @property
    def client_count(self) -> int:
        return self._server.client_count


__all__ = ["AutoEngine", "_engine"]
