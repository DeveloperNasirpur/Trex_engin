"""
trex.engine.auto
================
AutoEngine — zero-boilerplate facade.

The user only needs:

    import trex

    trex.init(timezone="Asia/Tehran", port=8765, db_config=..., exchange="binance")

    trex.rsi("BTCUSDT", "1m", period=14, visible=True, listener=on_rsi)
    trex.ema("BTCUSDT", "1m", period=20, visible=True)

    trex.seed("BTCUSDT")   # reads ALL history from DB, calculates all indicators
                            # (incremental: skips already-calculated bars in DB)

    # in feed loop:
    trex.push(bar, symbol="BTCUSDT")   # saves bar+indicators to DB, broadcasts

AutoEngine automatically manages:
- WebSocket server (SyncServer)
- In-memory bar store (MultiSymbolStore) per (symbol, timeframe)
- PostgreSQL persistence (TrexStore) — candles + indicators
- on_connect  → snapshot (bars + definitions + indicator cache)
- on_history  → paginated history
- on_symbol   → re-snapshot for new symbol
- on_timeframe → re-snapshot for new timeframe
- per-indicator: broadcast + in-memory cache + DB persistence on every emit

Incremental seed logic
----------------------
On each program run, seed() checks per indicator series how far back DB
values already exist (via get_indicator_stats → last_time).  It feeds ALL
bars through the engine for correct warm-up, but only writes indicator
values for bars beyond the last-calculated timestamp.  On subsequent runs
the already-calculated portion is skipped completely.
"""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from trex.domain.types import Bar, Point, SeriesDef
    from trex.engine.indicator import Indicator
    from trex.store.db_store import TrexStore

log = logging.getLogger("trex.auto")

# Module-level singleton — set by trex.init()
_engine: "AutoEngine | None" = None


class AutoEngine:
    """
    Orchestrates SyncServer + MultiSymbolStore + TrexStore + ctx.

    Never instantiate directly — use trex.init().
    """

    def __init__(
        self,
        *,
        port:             int = 8765,
        host:             str = "0.0.0.0",
        max_bars:         int = 10_000,
        source_timeframe: str = "1m",
        snapshot_size:    int = 500,
        db_config:        Any = None,
        exchange:         str = "default",
    ) -> None:
        from trex.server.store import MultiSymbolStore
        from trex.server.sync import SyncServer

        self._source_tf    = source_timeframe
        self._snapshot_sz  = snapshot_size
        self._exchange     = exchange
        self._store        = MultiSymbolStore(max_bars=max_bars)
        self._server       = SyncServer(host=host, port=port)
        self._definitions: list[SeriesDef] = []
        self._def_lock     = threading.Lock()

        # Indicator registry: {(symbol, tf): [Indicator, ...]}
        self._registry: dict[tuple[str, str], list[Any]] = {}
        self._reg_lock  = threading.Lock()

        # Optional DB store
        self._db: TrexStore | None = None
        if db_config is not None:
            from trex.store.db_store import TrexStore as _TrexStore
            self._db = _TrexStore(db_config)
            log.info("AutoEngine: DB connected (exchange=%s)", exchange)

        # Wire server hooks before start()
        self._server._on_connect   = self._on_connect
        self._server._on_history   = self._on_history
        self._server._on_symbol    = self._on_symbol
        self._server._on_timeframe = self._on_timeframe

    # ── Server event handlers ─────────────────────────────────────────────────

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
            symbol      = symbol or None,
            timeframe   = tf,
            definitions = defs,
            indicators  = cache,
        )
        session.fit_content()

    # ── Indicator wiring ───────────────────────────────────────────────────────

    def wire_indicator(self, symbol: str, ind: "Indicator") -> None:
        """
        Wire one indicator into the live pipeline:
          1. On emit → broadcast to clients
          2. On emit → update in-memory tail cache
          3. On emit → persist to DB (if configured)
        Also registers the indicator for seed() incremental processing.
        """
        _symbol   = symbol.upper()
        _tf       = ind.tf
        _store    = self._store
        _server   = self._server
        _db       = self._db
        _exchange = self._exchange

        def _live_hook(data: "dict[str, list[Point]]") -> None:
            # Broadcast to all connected clients
            _server.broadcast_indicators(data)

            # Update in-memory indicator tail cache
            tails = {k: pts[-1] for k, pts in data.items() if pts}
            _store.update_indicator_tails(_symbol, _tf, tails)

            # Persist indicator values to DB
            if _db is not None and tails:
                by_time: dict[int, dict[str, Any]] = {}
                for series_key, pt in tails.items():
                    by_time.setdefault(int(pt.time), {})[series_key] = pt.value
                for ts, ind_data in by_time.items():
                    try:
                        _db.update_indicator_only(_exchange, _symbol, _tf, ts, ind_data)
                    except Exception:
                        log.exception(
                            "Failed to persist indicator to DB (sym=%s ts=%s)", _symbol, ts
                        )

        ind._set_emit_hook(_live_hook)

        # Register for seed() incremental processing
        key = (_symbol, _tf)
        with self._reg_lock:
            bucket = self._registry.setdefault(key, [])
            if ind not in bucket:
                bucket.append(ind)

        # Add SeriesDefs if visible=True
        if getattr(ind, "_visible", False):
            with self._def_lock:
                existing = {d.key for d in self._definitions}
                for sdef in ind.series_defs():
                    if sdef.key not in existing:
                        self._definitions.append(sdef)
                        existing.add(sdef.key)

        log.debug("Wired %s [%s %s]", ind.__class__.__name__, _symbol, _tf)

    # ── Seed: auto-load from DB + incremental indicator calculation ───────────

    def seed(self, symbol: str, timeframe: str | None = None) -> None:
        """
        Auto-load history from DB and calculate all registered indicators.

        Algorithm
        ---------
        1. Fetch ALL bars for (symbol, tf) from DB, ordered oldest → newest.
        2. Per registered indicator series, query the last timestamp already
           calculated in DB (``get_indicator_stats → last_time``).
        3. Feed every bar through the engine (needed for correct warm-up).
           A lightweight seed hook collects new points (those beyond
           ``last_time``) without broadcasting.
        4. Batch-write the new points to DB via ``bulk_update_indicators``.
        5. Load the most recent ``snapshot_size`` bars into the memory store.
        6. Re-wire all indicators to the live hook (broadcast + DB save).

        On subsequent program runs, step 2 finds existing values → step 4
        writes only the bars added since the last run.
        """
        from trex.base.ohlcv import OHLCV
        from trex.engine.context import ctx

        sym = symbol.upper()
        tf  = timeframe or self._source_tf

        if self._db is None:
            log.warning(
                "seed(%s): db_config not set — nothing to load. "
                "Pass db_config=... to trex.init() to enable auto-seed.",
                sym,
            )
            return

        # 1. Read all bars from DB
        log.info("seed(%s %s): fetching bars from DB...", sym, tf)
        bars = self._db.fetch_bars(self._exchange, sym, tf)
        if not bars:
            log.info("seed(%s %s): no bars in DB.", sym, tf)
            return
        log.info("seed(%s %s): %d bars loaded from DB.", sym, tf, len(bars))

        # 2. Get registered indicators for this (symbol, tf)
        key = (sym, tf)
        with self._reg_lock:
            indicators = list(self._registry.get(key, []))

        if not indicators:
            log.info(
                "seed(%s %s): no indicators registered — loading memory store only.",
                sym, tf,
            )
            self._store.seed(sym, tf, bars[-self._snapshot_sz:])
            return

        # 3. Query last-calculated timestamp per series key
        last_calc: dict[str, int] = {}
        for ind in indicators:
            for sdef in ind.series_defs():
                try:
                    stats = self._db.get_indicator_stats(
                        self._exchange, sym, tf, sdef.key
                    )
                    if stats and stats.get("last_time"):
                        last_calc[sdef.key] = int(stats["last_time"])
                except Exception:
                    log.exception("seed: could not query last_calc for %s", sdef.key)

        n_up_to_date = sum(1 for k in last_calc if last_calc[k] >= bars[-1].time)
        log.info(
            "seed(%s %s): %d/%d series already up-to-date in DB.",
            sym, tf, n_up_to_date, len(last_calc),
        )

        # 4. Wire seed hooks — collect new points, no broadcasting
        #    pending[bar_time][series_key] = value
        pending: dict[int, dict[str, float]] = {}

        def _make_seed_hook(series_last_calc: dict[str, int]) -> Any:
            def _seed_hook(data: "dict[str, list[Point]]") -> None:
                for series_key, pts in data.items():
                    if pts:
                        pt = pts[-1]
                        ts = int(pt.time)
                        if ts > series_last_calc.get(series_key, 0):
                            pending.setdefault(ts, {})[series_key] = pt.value
            return _seed_hook

        seed_hook = _make_seed_hook(last_calc)
        for ind in indicators:
            ind._set_emit_hook(seed_hook)

        # 5. Feed ALL bars through engine (warm-up + collect new points)
        log.info("seed(%s %s): running indicator calculations on %d bars...", sym, tf, len(bars))
        for bar in bars:
            ctx.provide(OHLCV.from_bar(bar, symbol=sym, str_time=tf))

        # 6. Batch-save new indicator values to DB
        if pending:
            log.info(
                "seed(%s %s): saving %d new indicator points to DB...",
                sym, tf, len(pending),
            )
            try:
                self._db.bulk_update_indicators(self._exchange, sym, tf, pending)
                log.info("seed(%s %s): DB save complete.", sym, tf)
            except Exception:
                log.exception("seed(%s %s): failed to write indicators to DB.", sym, tf)
        else:
            log.info("seed(%s %s): all indicators already up-to-date in DB.", sym, tf)

        # 7. Load in-memory store (recent bars for client snapshots)
        self._store.seed(sym, tf, bars[-self._snapshot_sz:])

        # 8. Re-wire indicators to live hook (broadcast + DB save)
        for ind in indicators:
            self.wire_indicator(sym, ind)

        log.info("seed(%s %s): complete.", sym, tf)

    # ── Push: live bar ─────────────────────────────────────────────────────────

    def push(self, bar: "Bar", symbol: str, timeframe: str | None = None) -> None:
        """
        Feed one live bar:
          1. Save candle to DB
          2. Update in-memory store
          3. Route through CTF + indicators → live hook fires (broadcast + DB)
          4. Broadcast raw bar to clients watching this symbol
        """
        from trex.base.ohlcv import OHLCV
        from trex.engine.context import ctx

        sym = symbol.upper()
        tf  = timeframe or self._source_tf

        # 1. Persist the raw bar to DB
        if self._db is not None:
            try:
                self._db.bulk_save_candles(self._exchange, sym, tf, [bar])
            except Exception:
                log.exception(
                    "push: failed to save bar to DB (sym=%s ts=%s)", sym, bar.time
                )

        # 2. Update in-memory bar store
        self._store.update(sym, tf, bar)

        # 3. Route through CTF converters + indicators
        #    Triggers _live_hook → broadcast indicators + save to DB
        ctx.provide(OHLCV.from_bar(bar, symbol=sym, str_time=tf))

        # 4. Broadcast raw bar to symbol-subscribed clients
        _sym = sym
        self._server.broadcast_bar(
            bar,
            filter=lambda s: (s.symbol or "").upper() == _sym,
        )

    # ── Legacy / no-DB manual seed ────────────────────────────────────────────

    def seed_bars(
        self, bars: "list[Bar]", symbol: str, timeframe: str | None = None
    ) -> None:
        """Bulk-load bars directly without DB (testing / DB-less setups)."""
        sym = symbol.upper()
        tf  = timeframe or self._source_tf
        self._store.seed(sym, tf, bars)

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._server.start()
        log.info(
            "TrexEngine  ws://%s:%d  (max_bars=%d  exchange=%s)",
            self._server._host,
            self._server._port,
            self._store._max,
            self._exchange,
        )

    def stop(self) -> None:
        if self._db is not None:
            try:
                self._db.close()
            except Exception:
                pass
        self._server.stop()
        log.info("TrexEngine stopped")

    @property
    def client_count(self) -> int:
        return self._server.client_count


__all__ = ["AutoEngine", "_engine"]
