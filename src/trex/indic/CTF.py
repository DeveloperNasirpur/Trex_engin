from __future__ import annotations
"""
trex.indic.CTF
==============
Converts a stream of 1-minute OHLCV candles into N higher timeframes.

تغییرات نسبت به نسخه قدیمی
-----------------------------
- ``libs.trex.*`` → ``trex.*``
- ``Optional`` → ``X | None``
- ``Dict`` → ``dict``
- محتوای اصلی و الگوریتم بدون تغییر حفظ شده
"""

import re
from collections import deque
from datetime import datetime
from typing import Any, Callable

from trex.base.ohlcv import OHLCV
from trex.engine.source import Source

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None  # type: ignore[assignment]


# ── Timeframe utilities ───────────────────────────────────────────────────────

_UNIT_MINUTES: dict[str, int] = {"M": 1, "H": 60, "D": 1_440, "W": 10_080}
_TF_RE = re.compile(r"^(\d+)([mMhHdDwW])$")
_VALID_HOUR_TFS = {1, 2, 3, 4, 6, 8, 12}


def timeframe_to_minutes(tf: str) -> int:
    """Parse a timeframe string to minutes.

    Examples:
        ``"4H"`` → 240, ``"1D"`` → 1440, ``"5m"`` → 5.

    Raises:
        ValueError: For unrecognised strings or hourly timeframes that
            don't align to 24 h.
    """
    m = _TF_RE.match(tf.strip())
    if not m:
        raise ValueError(f"Unrecognised timeframe: {tf!r}")
    value   = int(m.group(1))
    unit    = m.group(2).upper()
    minutes = value * _UNIT_MINUTES[unit]

    if unit == "H" and value not in _VALID_HOUR_TFS:
        raise ValueError(
            f"Hourly timeframe {tf!r} ({value}h) does not divide evenly into "
            f"24 h. Supported hour values: {sorted(_VALID_HOUR_TFS)}"
        )
    return minutes


def _is_bar_open(dt: datetime, minutes: int, week_start_weekday: int = 0) -> bool:
    """True when *dt* marks the first minute of a new higher-TF bar."""
    if dt.second != 0:
        return False
    if minutes < 1_440:
        return (dt.hour * 60 + dt.minute) % minutes == 0
    if minutes == 1_440:
        return dt.hour == 0 and dt.minute == 0
    return dt.weekday() == week_start_weekday and dt.hour == 0 and dt.minute == 0


# ── Per-timeframe aggregation bucket ─────────────────────────────────────────

class _TFBucket:
    """Accumulates 1-min ticks into one higher-TF OHLCV bar."""

    __slots__ = ("minutes", "label", "callbacks", "current", "count",
                 "history", "_step", "_week_start_weekday")

    def __init__(
        self,
        minutes:            int,
        label:              str,
        history_maxlen:     int,
        week_start_weekday: int = 0,
    ) -> None:
        self.minutes:             int                        = minutes
        self.label:               str                        = label
        self.callbacks:           dict[str, Callable[..., Any]] = {}
        self.current:             OHLCV | None               = None
        self.count:               int                        = 0
        self.history:             deque[OHLCV]               = deque(maxlen=history_maxlen)
        self._week_start_weekday: int                        = week_start_weekday
        self._step: Callable[[OHLCV], None] = self._wait_step

    def on_tick(self, tick: OHLCV) -> None:
        self._step(tick)

    def _wait_step(self, tick: OHLCV) -> None:
        if _is_bar_open(tick.time, self.minutes, self._week_start_weekday):
            self.current = OHLCV(
                open=tick.open,
                high=tick.high,
                low=tick.low,
                close=tick.close,
                volume=tick.volume if tick.volume is not None else 0.0,
                time=tick.time,
                side=0,
                timeframe=self.minutes,
                str_time=self.label,
                symbol=tick.symbol,
            )
            self.count = 1
            self._step = self._build_step

    def _build_step(self, tick: OHLCV) -> None:
        c = self.current
        if c is None:
            return
        if tick.high and (c.high is None or tick.high > c.high):
            c.high = tick.high
        if tick.low and (c.low is None or tick.low < c.low):
            c.low = tick.low
        if tick.volume is not None:
            c.volume = (c.volume or 0.0) + tick.volume
        self.count += 1
        if self.count == self.minutes:
            c.close = tick.close
            c.side  = 0 if (c.open or 0) > (c.close or 0) else 1
            self.history.append(c)
            for key, cb in self.callbacks.items():
                if cb is not None:
                    cb(key, c)
            self._step = self._wait_step


# ── ConvertTimeFrame ──────────────────────────────────────────────────────────

class ConvertTimeFrame(Source):
    """
    Fan-out node: receives 1-min OHLCV ticks, dispatches completed bars.

    Args:
        time_zone: IANA timezone name (e.g. ``"Asia/Tehran"``).
        history_maxlen: Ring-buffer size for completed bars per timeframe.
        week_start_weekday: ISO weekday for trading week start.
            ``0`` = Monday (default), ``6`` = Sunday (crypto).
    """

    def __init__(
        self,
        time_zone:          str | None = None,
        history_maxlen:     int        = 500,
        week_start_weekday: int        = 0,
    ) -> None:
        super().__init__(warmup=0, save_input=False, save_output=False)
        self.time_zone          = time_zone
        self.history_maxlen     = history_maxlen
        self.week_start_weekday = week_start_weekday
        self._buckets:        dict[str, _TFBucket]        = {}
        self._m1_callbacks:   dict[str, Callable[..., Any]] = {}

        self._to_local: Callable[[datetime], datetime] = (
            (lambda dt: dt.astimezone(ZoneInfo(time_zone)))  # type: ignore[arg-type]
            if (time_zone and ZoneInfo)
            else (lambda dt: dt)
        )

    # ── Registration API ──────────────────────────────────────────────────────

    def add_timeframe(
        self,
        timeframe:     str,
        indicator_key: str,
        callback:      Callable[..., Any] | None = None,
    ) -> None:
        """Subscribe *indicator_key* to completed bars for *timeframe*."""
        minutes = timeframe_to_minutes(timeframe)
        if minutes == 1:
            self._m1_callbacks[indicator_key] = callback  # type: ignore[assignment]
        else:
            if timeframe not in self._buckets:
                self._buckets[timeframe] = _TFBucket(
                    minutes=minutes,
                    label=timeframe,
                    history_maxlen=self.history_maxlen,
                    week_start_weekday=self.week_start_weekday,
                )
            self._buckets[timeframe].callbacks[indicator_key] = callback  # type: ignore[assignment]

    def remove_indicator_callback(self, timeframe: str, indicator_key: str) -> None:
        """Remove a stale indicator subscription."""
        if timeframe_to_minutes(timeframe) == 1:
            self._m1_callbacks.pop(indicator_key, None)
        else:
            b = self._buckets.get(timeframe)
            if b:
                b.callbacks.pop(indicator_key, None)

    def get_history(self, timeframe: str) -> deque[OHLCV] | None:
        """Return the completed-bar ring-buffer for *timeframe*, or None."""
        b = self._buckets.get(timeframe)
        return b.history if b else None

    # ── Source protocol ───────────────────────────────────────────────────────

    def _first_calculate(self, tick: OHLCV, prev: OHLCV) -> bool:  # type: ignore[override]
        return True

    def _calculate_new_value(self, tick: OHLCV, prev: OHLCV) -> None:  # type: ignore[override]
        if tick.time is None:
            return
        tick.time = self._to_local(tick.time)

        if self._m1_callbacks:
            for key, cb in self._m1_callbacks.items():
                if cb is not None:
                    cb(key, tick)

        for bucket in self._buckets.values():
            bucket.on_tick(tick)

    def _on_reset(self) -> None:
        self._buckets.clear()
        self._m1_callbacks.clear()


__all__ = ["ConvertTimeFrame", "timeframe_to_minutes"]
