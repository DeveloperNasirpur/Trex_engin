"""trex — Streaming technical indicator engine."""
from trex.base import OHLCV, OHLCVFactory, ValueExtractor, Timeframe, ListenerKey
from trex.engine import Indicator, Pipeline, ContextIndicator, ctx
from trex.engine.context import IndicatorInfo
from trex.api import (
    init, start_history_provide,
    sma, ema, wma, hma, dema, tema, zlema, vwma, kama,
    tr, atr, stddev, bbands, keltner, donchian,
    rsi, macd, trix, adx, aroon,
    stochastic, cci, williams_r, roc, momentum, mfi, obv, cmo,
    vwap, supertrend, ichimoku, psar, zigzag_base,
    de_attach, de_attach_by_key, indicators,
    attach_listener_timeframe, de_attach_listener_timeframe,
)

__version__ = "2.0.0"

__all__ = [
    # Base types
    "OHLCV", "OHLCVFactory", "ValueExtractor", "Timeframe", "ListenerKey",
    # Engine
    "Indicator", "Pipeline", "ContextIndicator", "IndicatorInfo", "ctx",
    # API — one-line indicator registration
    "init", "start_history_provide",
    "sma", "ema", "wma", "hma", "dema", "tema", "zlema", "vwma", "kama",
    "tr", "atr", "stddev", "bbands", "keltner", "donchian",
    "rsi", "macd", "trix", "adx", "aroon",
    "stochastic", "cci", "williams_r", "roc", "momentum", "mfi", "obv", "cmo",
    "vwap", "supertrend", "ichimoku", "psar", "zigzag_base",
    "de_attach", "de_attach_by_key", "indicators",
    "attach_listener_timeframe", "de_attach_listener_timeframe",
]
