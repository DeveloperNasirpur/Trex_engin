"""
trex.infrastructure.store
=========================
Thread-safe in-memory candle and indicator cache.

Responsibilities
----------------
- Holds candle history for one (symbol, timeframe) pair.
- De-duplicates and keeps bars sorted by time (binary-search indexed).
- Answers history page requests (lazy-load from the terminal).
- Caches the latest computed indicator values so new clients receive them
  immediately in the snapshot without recomputation.
- Fires a ``on_bar_close`` callback when a new bar is appended (the
  previous bar just closed).

Threading model
---------------
All public methods are safe to call from any thread.  The internal lock
is held only while mutating / reading shared state; user callbacks are
**never** called while the lock is held, eliminating the deadlock class
present in the original implementation.

Usage
-----
::

    store = CandleStore(max_bars=5_000)
    store.seed(historical_bars)           # bulk-load

    # called from your data-feed thread:
    closed = store.update(new_bar)        # upsert
    if closed:
        recalculate_indicators()

    # snapshot for a new client:
    recent = store.recent(500)
    indicators = store.indicator_cache
"""
from __future__ import annotations

import bisect
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from trex.domain.types import Bar, Point

# ── Single-symbol store ───────────────────────────────────────────────────────


class CandleStore:
    """
    Thread-safe in-memory store for one (symbol, timeframe) pair.

    Parameters
    ----------
    max_bars:
        Maximum bars to keep in memory. When exceeded, the oldest bars are
        evicted (FIFO).  Defaults to ``10_000``.
    on_bar_close:
        Optional callback fired with the just-closed ``Bar`` when a new bar
        is appended.  Called **outside** the internal lock, so it is safe to
        call back into the store (e.g. to read ``recent()``).
    """

    __slots__ = (
        "_lock",
        "_bars",
        "_times",
        "_max",
        "_on_bar_close",
        "indicator_cache",
    )

    def __init__(
        self,
        max_bars: int = 10_000,
        on_bar_close: Callable[[Bar], None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._bars:  list[Bar] = []
        self._times: list[int] = []   # sorted mirror for bisect — always in sync
        self._max           = max_bars
        self._on_bar_close  = on_bar_close
        # {series_key: [Point, ...]} — replaced atomically by store_indicators()
        self.indicator_cache: dict[str, list[Point]] = {}

    # ── Population ────────────────────────────────────────────────────────────

    def seed(self, bars: list[Bar]) -> None:
        """
        Bulk-load bars (called once at startup).

        Sorts ascending by time and de-duplicates (last-write-wins on
        duplicate timestamps, consistent with ``sanitizeCandles`` in the
        terminal).
        """
        deduped = {b.time: b for b in sorted(bars, key=lambda b: b.time)}
        sorted_bars = list(deduped.values())
        with self._lock:
            self._bars  = sorted_bars
            self._times = [b.time for b in sorted_bars]
            self._evict()

    def update(self, bar: Bar) -> bool:
        """
        Upsert one bar.

        Returns
        -------
        bool
            ``True`` if a **new** bar was appended (i.e. the previous bar
            just closed).  ``False`` if the last bar was updated in-place
            (tick on the currently-open bar).

        The ``on_bar_close`` callback is fired **after** the lock is
        released, with the bar that just closed.
        """
        closed_bar: Bar | None = None

        with self._lock:
            closed = False
            if self._times and bar.time == self._times[-1]:
                # Tick on the current open bar — update in-place
                self._bars[-1] = bar

            elif self._times and bar.time < self._times[-1]:
                # Late / out-of-order bar — insert at the correct position
                idx = bisect.bisect_left(self._times, bar.time)
                if idx < len(self._times) and self._times[idx] == bar.time:
                    self._bars[idx] = bar          # duplicate timestamp
                else:
                    self._bars.insert(idx, bar)
                    self._times.insert(idx, bar.time)

            else:
                # New bar — the previous bar just closed
                if self._bars:
                    closed_bar = self._bars[-1]
                self._bars.append(bar)
                self._times.append(bar.time)
                self._evict()
                closed = True

        # Fire callback outside the lock to avoid deadlock risk
        if closed and closed_bar is not None and self._on_bar_close is not None:
            self._on_bar_close(closed_bar)

        return closed

    # ── Queries ───────────────────────────────────────────────────────────────

    def recent(self, n: int = 500) -> list[Bar]:
        """Return the most recent ``n`` bars, oldest-first."""
        with self._lock:
            return list(self._bars[-n:])

    def history_page(self, before: int, count: int = 300) -> list[Bar]:
        """
        Return up to ``count`` bars with ``time < before``, oldest-first.

        Returns an empty list when there is no older history.
        """
        with self._lock:
            idx   = bisect.bisect_left(self._times, before)
            start = max(0, idx - count)
            return list(self._bars[start:idx])

    def last_bar(self) -> Bar | None:
        """Return the most recent bar, or ``None`` if the store is empty."""
        with self._lock:
            return self._bars[-1] if self._bars else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._bars)

    # ── Indicator cache ───────────────────────────────────────────────────────

    def store_indicators(self, data: dict[str, list[Point]]) -> None:
        """
        Atomically replace the indicator cache.

        Call this after a full recomputation so new clients receive a
        complete snapshot.
        """
        snapshot = {k: list(v) for k, v in data.items()}
        with self._lock:
            self.indicator_cache = snapshot

    def update_indicator_tails(self, tails: dict[str, Point]) -> None:
        """
        O(1) fast-path: update only the last point of each named series.

        If the tail point has the same timestamp as the current last point,
        it replaces it (tick update).  Otherwise it is appended (new candle
        closed).
        """
        with self._lock:
            for key, pt in tails.items():
                series = self.indicator_cache.get(key)
                if series:
                    if series[-1].time == pt.time:
                        series[-1] = pt          # in-place tick update
                    else:
                        series.append(pt)        # new bar
                else:
                    self.indicator_cache[key] = [pt]

    # ── Internal ──────────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Trim oldest bars when the store exceeds ``max_bars``."""
        if len(self._bars) > self._max:
            drop         = len(self._bars) - self._max
            self._bars   = self._bars[drop:]
            self._times  = self._times[drop:]


# ── Multi-symbol store ────────────────────────────────────────────────────────


class MultiSymbolStore:
    """
    Multi-symbol, multi-timeframe store.

    Maintains one :class:`CandleStore` per ``(symbol, timeframe)`` pair.
    All methods are thread-safe.

    Usage
    -----
    ::

        store = MultiSymbolStore()
        store.seed("BTCUSDT", "1m", historical_bars)
        store.update("BTCUSDT", "1m", new_bar)

        # In on_connect:
        bars = store.recent("BTCUSDT", "1m", 500)

        # In on_history:
        page = store.history_page("BTCUSDT", "1m", before=ts, count=300)
    """

    def __init__(self, max_bars: int = 10_000) -> None:
        self._max    = max_bars
        self._stores: dict[tuple[str, str], CandleStore] = {}
        self._lock   = threading.Lock()

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _key(symbol: str, timeframe: str) -> tuple[str, str]:
        return (symbol.upper(), timeframe)

    def _get_or_create(self, symbol: str, timeframe: str) -> CandleStore:
        k = self._key(symbol, timeframe)
        try:
            return self._stores[k]
        except KeyError:
            with self._lock:
                # Double-checked locking
                if k not in self._stores:
                    self._stores[k] = CandleStore(self._max)
                return self._stores[k]

    # ── Public API (mirrors CandleStore) ─────────────────────────────────────

    def seed(self, symbol: str, timeframe: str, bars: list[Bar]) -> None:
        """Bulk-load bars for a symbol/timeframe pair."""
        self._get_or_create(symbol, timeframe).seed(bars)

    def update(self, symbol: str, timeframe: str, bar: Bar) -> bool:
        """Upsert one bar. Returns ``True`` if a bar closed."""
        return self._get_or_create(symbol, timeframe).update(bar)

    def recent(self, symbol: str, timeframe: str, n: int = 500) -> list[Bar]:
        """Return the most recent ``n`` bars."""
        return self._get_or_create(symbol, timeframe).recent(n)

    def history_page(
        self, symbol: str, timeframe: str, before: int, count: int = 300
    ) -> list[Bar]:
        """Return a history page for lazy-loading."""
        return self._get_or_create(symbol, timeframe).history_page(before, count)

    def last_bar(self, symbol: str, timeframe: str) -> Bar | None:
        """Return the most recent bar for the pair, or ``None``."""
        return self._get_or_create(symbol, timeframe).last_bar()

    def store_indicators(
        self, symbol: str, timeframe: str, data: dict[str, list[Point]]
    ) -> None:
        """Replace the indicator cache for a pair."""
        self._get_or_create(symbol, timeframe).store_indicators(data)

    def update_indicator_tails(
        self, symbol: str, timeframe: str, tails: dict[str, Point]
    ) -> None:
        """O(1) indicator tail update for a pair."""
        self._get_or_create(symbol, timeframe).update_indicator_tails(tails)

    def get_store(self, symbol: str, timeframe: str) -> CandleStore:
        """Return (or create) the underlying ``CandleStore`` for a pair."""
        return self._get_or_create(symbol, timeframe)

    @property
    def symbols(self) -> list[tuple[str, str]]:
        """All ``(symbol, timeframe)`` pairs currently held."""
        return list(self._stores.keys())

    def __contains__(self, key: object) -> bool:
        return key in self._stores

    def __len__(self) -> int:
        return len(self._stores)


__all__ = ["CandleStore", "MultiSymbolStore"]
