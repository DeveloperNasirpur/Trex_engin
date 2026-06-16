"""trex — Streaming technical indicator engine."""
from trex.base import OHLCV, OHLCVFactory, ValueExtractor, Timeframe, ListenerKey
from trex.engine import Indicator, Pipeline, ContextIndicator, ctx
from trex.engine.context import IndicatorInfo

__version__ = "2.0.0"

__all__ = [
    "OHLCV", "OHLCVFactory", "ValueExtractor", "Timeframe", "ListenerKey",
    "Indicator", "Pipeline", "ContextIndicator", "IndicatorInfo", "ctx",
]
