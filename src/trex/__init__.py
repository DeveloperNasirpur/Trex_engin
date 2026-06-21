"""trex — Streaming technical indicator engine."""
import atexit as _atexit

from trex.base import OHLCV, OHLCVFactory, ValueExtractor, Timeframe, ListenerKey
from trex.engine import Indicator, Pipeline, ContextIndicator, ctx
from trex import plugin
from trex.engine.context import IndicatorInfo
from trex.api import (
    # ── Trend / Moving Averages ────────────────────────────────────────────────
    sma, ema, wma, hma, dema, tema, zlema, vwma, kama,
    # ── Volatility (classic) ──────────────────────────────────────────────────
    tr, atr, stddev, bbands, keltner, donchian,
    # ── Momentum / Oscillators ────────────────────────────────────────────────
    rsi, macd, trix, adx, aroon, stochastic, cci, williams_r, roc, momentum,
    mfi, obv, cmo,
    # ── New momentum indicators ───────────────────────────────────────────────
    ao, ac, tsi, dpo, kst, coppock, rvi, fisher, vortex, ppo, apo,
    stochrsi, uo, chop, force_index,
    # ── Volume ────────────────────────────────────────────────────────────────
    ad, adosc, cmf, eom, nvi, pvi, pvt, vo, vroc,
    # ── Statistics ────────────────────────────────────────────────────────────
    zscore, variance, linreg_slope, correl, percentrank,
    # ── Volatility (extended) ─────────────────────────────────────────────────
    natr, ui, hv, chandelier,
    # ── Overlay / Price ───────────────────────────────────────────────────────
    vwap, supertrend, ichimoku, psar, zigzag_base,
    # ── Candlestick patterns — single ────────────────────────────────────────
    doji, dragonfly_doji, gravestone_doji, hammer, inverted_hammer,
    hanging_man, shooting_star, marubozu, spinning_top, long_legged_doji,
    bullish_belt, bearish_belt, high_wave, rickshaw_man, umbrella_line,
    # ── Candlestick patterns — two-candle ────────────────────────────────────
    bullish_engulfing, bearish_engulfing, bullish_harami, bearish_harami,
    piercing, dark_cloud_cover, tweezer, kicking, on_neck, matching_low,
    # ── Candlestick patterns — three-candle ──────────────────────────────────
    morning_star, evening_star, morning_doji_star, evening_doji_star,
    three_white_soldiers, three_black_crows, three_inside_up, three_inside_down,
    deliberation, identical_three_crows,
    # ── Management ────────────────────────────────────────────────────────────
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
    exchange:           str           = "default",
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
    exchange:
        Exchange name used as PostgreSQL schema prefix (e.g. ``"binance"``).
        Defaults to ``"default"``.
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

        trex.seed("BTCUSDT")

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

    # Stop any previously running engine (guard against double init())
    if _auto_mod._engine is not None:
        try:
            _auto_mod._engine.stop()
        except Exception:
            pass
        _auto_mod._engine = None

    engine = AutoEngine(
        port             = port,
        host             = host,
        max_bars         = max_bars,
        source_timeframe = source_timeframe,
        snapshot_size    = snapshot_size,
        db_config        = db_config,
        exchange         = exchange,
    )
    _auto_mod._engine = engine
    engine.start()

    # Auto-cleanup on interpreter exit — user never needs to call trex.stop()
    _atexit.register(engine.stop)


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


def seed(symbol: str, timeframe: str | None = None) -> None:
    """
    Auto-load historical bars from DB, calculate all registered indicators
    (incremental), and populate the in-memory store for client snapshots.

    Call once at startup — after ``trex.init()`` and after registering all
    indicators — before starting the live feed.

    Incremental behaviour
    ---------------------
    On first run: feeds all bars through every indicator, saves results to DB.
    On subsequent runs: only calculates and saves bars added since last run.
    Already-calculated indicator values are never rewritten.
    Crash-safe: progress is checkpointed every 10 000 bars so a crash never
    forces a full replay from scratch.

    Parameters
    ----------
    symbol:
        Trading symbol (e.g. ``"BTCUSDT"``).
    timeframe:
        Optional override (default = ``source_timeframe`` set in ``init()``).

    Example
    -------
    ::

        trex.init(timezone="Asia/Tehran", db_config=cfg, exchange="binance")
        trex.rsi("BTCUSDT", "1m", period=14, visible=True, listener=on_rsi)
        trex.ema("BTCUSDT", "1m", period=20, visible=True)

        trex.seed("BTCUSDT")   # reads from DB, calculates, saves

        while True:
            bar = exchange.next_bar()
            trex.push(bar, symbol="BTCUSDT")
    """
    from trex.engine.auto import _engine
    if _engine is None:
        raise RuntimeError("Call trex.init() before trex.seed()")
    _engine.seed(symbol, timeframe)


def stop() -> None:
    """Gracefully shut down the WebSocket server.

    Not required in most cases — ``trex.init()`` registers this automatically
    via ``atexit`` so the server always shuts down cleanly on exit.
    """
    from trex.engine.auto import _engine
    if _engine is not None:
        _engine.stop()


def client_count() -> int:
    """Return the number of currently connected clients."""
    from trex.engine.auto import _engine
    return _engine.client_count if _engine is not None else 0


def set_playback_controller(ctrl: object | None) -> None:
    """
    Register a PlaybackController so that TrexTerminal clients can control
    backtest replay speed/pause in real time.

    Called automatically by Backtest.run() when broadcast=True.
    Pass None to signal that the backtest has ended.

    Example::

        from backtest.playback import PlaybackController
        ctrl = PlaybackController(speed=1.0)
        trex.set_playback_controller(ctrl)
        # ... run backtest loop ...
        trex.set_playback_controller(None)
    """
    from trex.engine.auto import _engine
    if _engine is not None:
        _engine.set_playback_controller(ctrl)


def broadcast_drawing(drawing: dict) -> None:
    """
    Push a drawing (position marker, order line, annotation) to all connected
    TrexTerminal clients.

    The *drawing* dict must conform to the protocol ``drawing_upsert`` shape::

        {
            "id":        "pos_123",         # unique, stable across updates
            "tool":      "longPosition",    # or "shortPosition", "horizontal", etc.
            "points":    [{"time": 1700000000, "price": 42000.0},
                          {"time": 1700000060, "price": 42000.0}],
            "style":     {"color": "#26a69a"},
            "paneId":    "main",
            "locked":    True,
            "visible":   True,
            "completed": True,
            "selected":  False,
            "origin":    "server",          # marks it read-only in the UI
            "positionData": {               # only for long/shortPosition
                "entryPrice": 42000.0,
                "stopLoss":   41500.0,
                "takeProfit": 43000.0,
                "quantity":   100.0,
                "risk":       1.19,
                "reward":     2.38,
            },
        }

    Safe to call when no clients are connected — the message is silently
    dropped. Safe to call before ``trex.init()`` — also silently dropped.
    """
    from trex.engine.auto import _engine
    if _engine is None or _engine._server is None:
        return
    _engine._server.broadcast({"type": "drawing_upsert", "drawing": drawing})


def delete_drawing(drawing_id: str) -> None:
    """
    Remove a previously broadcast drawing from all connected clients.

    Parameters
    ----------
    drawing_id:
        The same ``id`` string that was used in ``broadcast_drawing()``.
    """
    from trex.engine.auto import _engine
    if _engine is None or _engine._server is None:
        return
    _engine._server.broadcast({"type": "drawing_delete", "drawingId": drawing_id})


# ── Re-exports ────────────────────────────────────────────────────────────────

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
    # Trend / Moving Averages
    "sma", "ema", "wma", "hma", "dema", "tema", "zlema", "vwma", "kama",
    # Volatility (classic)
    "tr", "atr", "stddev", "bbands", "keltner", "donchian",
    # Momentum / Oscillators
    "rsi", "macd", "trix", "adx", "aroon", "stochastic", "cci",
    "williams_r", "roc", "momentum", "mfi", "obv", "cmo",
    # New momentum
    "ao", "ac", "tsi", "dpo", "kst", "coppock", "rvi", "fisher",
    "vortex", "ppo", "apo", "stochrsi", "uo", "chop", "force_index",
    # Volume
    "ad", "adosc", "cmf", "eom", "nvi", "pvi", "pvt", "vo", "vroc",
    # Statistics
    "zscore", "variance", "linreg_slope", "correl", "percentrank",
    # Volatility (extended)
    "natr", "ui", "hv", "chandelier",
    # Overlay / Price
    "vwap", "supertrend", "ichimoku", "psar", "zigzag_base",
    # Candlestick patterns — single
    "doji", "dragonfly_doji", "gravestone_doji", "hammer", "inverted_hammer",
    "hanging_man", "shooting_star", "marubozu", "spinning_top",
    "long_legged_doji", "bullish_belt", "bearish_belt", "high_wave",
    "rickshaw_man", "umbrella_line",
    # Candlestick patterns — two-candle
    "bullish_engulfing", "bearish_engulfing", "bullish_harami", "bearish_harami",
    "piercing", "dark_cloud_cover", "tweezer", "kicking", "on_neck", "matching_low",
    # Candlestick patterns — three-candle
    "morning_star", "evening_star", "morning_doji_star", "evening_doji_star",
    "three_white_soldiers", "three_black_crows", "three_inside_up",
    "three_inside_down", "deliberation", "identical_three_crows",
    # Management
    "de_attach", "de_attach_by_key", "indicators",
    "attach_listener_timeframe", "de_attach_listener_timeframe",
    "start_history_provide",
    # Plugin system
    "plugin",
]
