"""trex — Streaming technical indicator engine."""
from trex.base import OHLCV, OHLCVFactory, ValueExtractor, Timeframe, ListenerKey
from trex.engine import Indicator, Pipeline, ContextIndicator, ctx
from trex.engine.context import IndicatorInfo
from trex.api import (
    sma, ema, wma, hma, dema, tema, zlema, vwma, kama,
    tr, atr, stddev, bbands, keltner, donchian,
    rsi, macd, trix, adx, aroon,
    stochastic, cci, williams_r, roc, momentum, mfi, obv, cmo,
    vwap, supertrend, ichimoku, psar, zigzag_base,
    de_attach, de_attach_by_key, indicators,
    attach_listener_timeframe, de_attach_listener_timeframe,
    start_history_provide,
)

__version__ = "2.0.0"


# ── High-level init — creates AutoEngine automatically ────────────────────────

def init(
    timezone:           str           = "Asia/Tehran",
    source_timeframe:   str           = "1m",
    port:               int           = 8765,
    host:               str           = "0.0.0.0",
    max_bars:           int           = 10_000,
    snapshot_size:      int           = 500,
    db_config:          object | None = None,
    fetch_size:         int           = 100_000,
    start_provide_from: str   | None  = None,
) -> None:
    """
    Configure the engine and start the WebSocket server.

    Must be called once before registering indicators or pushing bars.

    Parameters
    ----------
    timezone:
        IANA timezone name for CTF bar-open detection (e.g. ``"Asia/Tehran"``).
    source_timeframe:
        Resolution of incoming bars (default ``"1m"``). All higher timeframes
        are aggregated automatically via CTF converters.
    port:
        WebSocket port TrexTerminal connects to (default ``8765``).
    host:
        Bind address (default ``"0.0.0.0"`` = all interfaces).
    max_bars:
        Maximum bars kept per (symbol, timeframe) pair in memory.
    snapshot_size:
        Number of recent bars sent to each new client (default ``500``).
    db_config:
        Optional :class:`~trex.store.db_store.DbConfig` for PostgreSQL persistence.
    fetch_size:
        PostgreSQL streaming batch size.
    start_provide_from:
        ISO date string — bars before this date are silently skipped during
        historical replay.

    Example
    -------
    ::

        import trex

        trex.init(timezone="Asia/Tehran", port=8765)

        trex.ema("BTCUSDT", "1m", period=20, visible=True)
        trex.rsi("BTCUSDT", "1m", period=14, visible=True, listener=on_rsi)

        trex.seed(historical_bars, symbol="BTCUSDT")

        while True:
            bar = exchange.next_bar()
            trex.push(bar, symbol="BTCUSDT")
    """
    # 1. Configure the global indicator context
    ctx.configure(
        db_config          = db_config,
        fetch_size         = fetch_size,
        time_zone          = timezone,
        source_timeframe   = source_timeframe,
        start_provide_from = start_provide_from,
    )

    # 2. Create and start AutoEngine (manages server + store automatically)
    from trex.engine.auto import AutoEngine
    import trex.engine.auto as _auto_mod

    engine = AutoEngine(
        port             = port,
        host             = host,
        max_bars         = max_bars,
        source_timeframe = source_timeframe,
        snapshot_size    = snapshot_size,
    )
    _auto_mod._engine = engine
    engine.start()


# ── Feed API ──────────────────────────────────────────────────────────────────

def push(bar: "Bar", symbol: str, timeframe: str | None = None) -> None:  # type: ignore[name-defined]
    """
    Feed one bar: update store → run indicators → broadcast to terminal.

    This is the only call needed in your feed loop. The engine handles
    CTF aggregation, indicator calculation, broadcast, and store caching
    automatically.

    Parameters
    ----------
    bar:
        One OHLCV bar (``trex.domain.types.Bar``).
    symbol:
        Trading symbol, e.g. ``"BTCUSDT"``.
    timeframe:
        Optional override (default = ``source_timeframe`` set in ``init()``).

    Example
    -------
    ::

        while True:
            bar = exchange.next_bar()
            trex.push(bar, symbol="BTCUSDT")
            time.sleep(1)
    """
    from trex.engine.auto import _engine
    if _engine is None:
        raise RuntimeError("Call trex.init() before trex.push()")
    _engine.push(bar, symbol, timeframe)


def seed(bars: list, symbol: str, timeframe: str | None = None) -> None:
    """
    Bulk-load historical bars into the store.

    Call once at startup before the live feed begins.  New clients that
    connect will receive these bars as their initial snapshot.

    Parameters
    ----------
    bars:
        List of ``Bar`` objects, sorted ascending by time (or unsorted —
        the store de-duplicates and sorts automatically).
    symbol:
        Trading symbol.
    timeframe:
        Optional override (default = ``source_timeframe`` set in ``init()``).

    Example
    -------
    ::

        historical = load_from_db("BTCUSDT", "1m", limit=5_000)
        trex.seed(historical, symbol="BTCUSDT")
    """
    from trex.engine.auto import _engine
    if _engine is None:
        raise RuntimeError("Call trex.init() before trex.seed()")
    _engine.seed(bars, symbol, timeframe)


def stop() -> None:
    """Gracefully shut down the WebSocket server."""
    from trex.engine.auto import _engine
    if _engine is not None:
        _engine.stop()


def client_count() -> int:
    """Return the number of currently connected clients."""
    from trex.engine.auto import _engine
    return _engine.client_count if _engine is not None else 0


# ── Re-exports ────────────────────────────────────────────────────────────────

# Lazy import for type hint only (avoids import at module load time)
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from trex.domain.types import Bar

__all__ = [
    # Base types
    "OHLCV", "OHLCVFactory", "ValueExtractor", "Timeframe", "ListenerKey",
    # Engine
    "Indicator", "Pipeline", "ContextIndicator", "IndicatorInfo", "ctx",
    # Auto API
    "init", "push", "seed", "stop", "client_count",
    # Indicator registration (all accept visible=True/False)
    "sma", "ema", "wma", "hma", "dema", "tema", "zlema", "vwma", "kama",
    "tr", "atr", "stddev", "bbands", "keltner", "donchian",
    "rsi", "macd", "trix", "adx", "aroon",
    "stochastic", "cci", "williams_r", "roc", "momentum", "mfi", "obv", "cmo",
    "vwap", "supertrend", "ichimoku", "psar", "zigzag_base",
    # Management
    "de_attach", "de_attach_by_key", "indicators",
    "attach_listener_timeframe", "de_attach_listener_timeframe",
    "start_history_provide",
]
