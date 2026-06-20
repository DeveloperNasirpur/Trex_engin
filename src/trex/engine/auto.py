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
        self._server._on_connect        = self._on_connect
        self._server._on_history        = self._on_history
        self._server._on_symbol         = self._on_symbol
        self._server._on_timeframe      = self._on_timeframe
        self._server._on_get_symbols    = self._on_get_symbols
        self._server._on_get_indicators = self._on_get_indicators
        self._server._on_layout         = self._on_layout
        self._server._on_chart_symbol   = self._on_chart_symbol
        self._server._on_chart_history  = self._on_chart_history

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

    def _on_get_symbols(self, session: Any) -> None:
        """Reply to get_symbols with all known (symbol, tf) pairs from memory or DB."""
        seen: set[str] = set()
        symbols: list[dict] = []
        # From in-memory store
        for sym, _tf in self._store.symbols:
            if sym not in seen:
                seen.add(sym)
                symbols.append({"symbol": sym})
        # Supplement from DB if available
        if self._db is not None:
            try:
                # Table names: BTCUSDT_1m, BNB_USDT_1h → strip last _TF suffix
                _tf_suffixes = {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"}
                for tbl in self._db.get_tables(self._exchange):
                    parts = tbl.rsplit("_", 1)
                    base = (parts[0] if len(parts) == 2 and parts[1] in _tf_suffixes else tbl).upper()
                    if base and base not in seen:
                        seen.add(base)
                        symbols.append({"symbol": base})
            except Exception:
                pass
        session.send_symbols_list(symbols)

    def _on_get_indicators(self, session: Any) -> None:
        """Reply to get_indicators with all registered SeriesDefinitions."""
        with self._def_lock:
            defs = list(self._definitions)
        session.send_indicators_list(defs)

    def _on_layout(self, session: Any, layout: str, charts: list) -> None:
        """Send chart_snapshot for every secondary chart in the layout."""
        for chart in charts:
            chart_id = chart.get("chartId", "")
            if not chart_id or chart_id == "main":
                continue
            sym = str(chart.get("symbol", "")).upper()
            tf  = str(chart.get("timeframe", self._source_tf))
            if sym:
                self._send_chart_snapshot(session, chart_id, sym, tf)

    def _on_chart_symbol(
        self, session: Any, chart_id: str, symbol: str,
        timeframe: str | None, indicators: list,
    ) -> None:
        """Send chart_snapshot when secondary chart changes symbol."""
        sym = symbol.upper()
        tf  = timeframe or (session.timeframe or self._source_tf)
        self._send_chart_snapshot(session, chart_id, sym, tf)

    def _on_chart_history(
        self, session: Any, chart_id: str, before: int, count: int
    ) -> None:
        """Reply to secondary-chart history request."""
        chart_state = session._charts.get(chart_id, {})
        sym = chart_state.get("symbol", "").upper()
        tf  = chart_state.get("timeframe", self._source_tf)
        if sym:
            page = self._store.history_page(sym, tf, before=before, count=count)
            session.push_chart_history(chart_id, page, no_more=len(page) == 0)

    def _send_chart_snapshot(
        self, session: Any, chart_id: str, symbol: str, tf: str
    ) -> None:
        store = self._store.get_store(symbol, tf)
        bars  = store.recent(self._snapshot_sz)
        defs  = list(self._definitions) or None
        cache = {k: list(v) for k, v in store.indicator_cache.items()} or None
        session.chart_snapshot(
            chart_id,
            bars,
            symbol      = symbol or None,
            timeframe   = tf,
            definitions = defs,
            indicators  = cache,
        )

    def _send_snapshot(self, session: Any, symbol: str, tf: str) -> None:
        store = self._store.get_store(symbol, tf)
        bars  = store.recent(self._snapshot_sz)
        defs  = list(self._definitions) or None
        cache = {k: list(v) for k, v in store.indicator_cache.items()} or None
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

        # 3b. Load and restore indicator states
        states: dict[str, dict] = {}
        for ind in indicators:
            ikey = ind.indicator_key()
            try:
                saved = self._db.load_indicator_state(
                    self._exchange, sym, tf, ikey
                )
                if saved:
                    states[ikey] = saved
            except Exception:
                log.exception("seed: could not load state for %s", ikey)

        # Determine whether we can use fast-path (every indicator has a saved state)
        all_have_state = len(states) > 0 and all(
            ind.indicator_key() in states for ind in indicators
        )
        if all_have_state:
            all_bar_times = [s["last_bar_time"] for s in states.values()]
            min_last_time = min(all_bar_times)
            # Restore state only for indicators AT the minimum checkpoint.
            # Indicators ahead of min_last_time must NOT get their state restored:
            # they would re-receive bars they already computed, corrupting Wilder
            # smoothing (or any other stateful calculation). Instead, let them
            # recompute from min_last_time with a fresh internal state.
            for ind in indicators:
                ikey = ind.indicator_key()
                if states[ikey]["last_bar_time"] <= min_last_time:
                    ind.set_state(states[ikey]["state"])
            bars_to_feed = [b for b in bars if b.time > min_last_time]
            log.info(
                "seed(%s %s): state restored — replaying %d new bars only.",
                sym, tf, len(bars_to_feed),
            )
        else:
            bars_to_feed = bars
            log.info(
                "seed(%s %s): no saved state — full replay of %d bars.",
                sym, tf, len(bars),
            )

        # 4. Wire seed hooks — collect new points, no broadcasting
        #    pending[bar_time][series_key] = value
        #    Flushed to DB every CHUNK_SIZE bars to avoid holding 1M rows in RAM
        #    and to allow crash-recovery on the next run.
        CHUNK_SIZE = 10_000
        pending: dict[int, dict[str, float]] = {}
        bars_since_flush = 0

        _last_flushed_bar: list[int] = [0]  # mutable cell for closure

        def _flush_pending(last_bar_time: int) -> None:
            nonlocal bars_since_flush
            if not pending:
                bars_since_flush = 0
                return
            try:
                self._db.bulk_update_indicators(self._exchange, sym, tf, pending)
                # Checkpoint indicator states so crash-recovery skips flushed bars
                for ind in indicators:
                    state = ind.get_state()
                    if state:
                        try:
                            self._db.save_indicator_state(
                                self._exchange, sym, tf,
                                ind.indicator_key(), state, last_bar_time,
                            )
                        except Exception:
                            pass
                _last_flushed_bar[0] = last_bar_time
            except Exception:
                log.exception("seed(%s %s): chunk flush failed (retry on next run)", sym, tf)
            pending.clear()
            bars_since_flush = 0

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

        # 5. Feed bars through engine (warm-up + collect new points)
        log.info("seed(%s %s): running indicator calculations on %d bars...", sym, tf, len(bars_to_feed))
        _current_bar_time = 0
        for bar in bars_to_feed:
            ctx.provide(OHLCV.from_bar(bar, symbol=sym, str_time=tf))
            _current_bar_time = bar.time
            bars_since_flush += 1
            if bars_since_flush >= CHUNK_SIZE:
                _flush_pending(_current_bar_time)

        # 6. Flush remaining indicator values to DB
        if pending:
            log.info(
                "seed(%s %s): saving final %d indicator points to DB...",
                sym, tf, len(pending),
            )
            _flush_pending(_current_bar_time)
        else:
            log.info("seed(%s %s): all indicators already up-to-date in DB.", sym, tf)

        # 6b. Final state checkpoint (covers the case where last chunk was flushed
        #     mid-loop but the very last bar's state wasn't saved yet)
        if bars_to_feed and _current_bar_time > _last_flushed_bar[0]:
            for ind in indicators:
                state = ind.get_state()
                if state:
                    try:
                        self._db.save_indicator_state(
                            self._exchange, sym, tf,
                            ind.indicator_key(), state, _current_bar_time,
                        )
                    except Exception:
                        log.exception(
                            "seed: failed to save final state for %s", ind.indicator_key()
                        )

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

        # 4. Broadcast raw bar to symbol-subscribed clients (main chart)
        _sym = sym
        self._server.broadcast_bar(
            bar,
            filter=lambda s: (s.symbol or "").upper() == _sym,
        )

        # 5. Broadcast chart_bar to sessions that track sym in a secondary chart
        self._server.broadcast_secondary_bar(sym, bar)

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
