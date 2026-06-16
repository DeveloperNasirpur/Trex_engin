from __future__ import annotations
"""trex.utils — Shared utility functions."""

from datetime import datetime


def date_to_milliseconds(date_str: str) -> int:
    """Convert ``"YYYY-MM-DD HH:MM:SS"`` to Unix milliseconds."""
    dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
    return int(dt.timestamp() * 1000)


def interval_to_ms(interval: str) -> int:
    """Convert interval string (``"1m"``, ``"4h"``, ``"1d"``…) to milliseconds."""
    unit  = interval[-1].lower()
    value = int(interval[:-1])
    multipliers = {"s": 1_000, "m": 60_000, "h": 3_600_000,
                   "d": 86_400_000, "w": 604_800_000}
    if unit not in multipliers:
        raise ValueError(f"Invalid interval: {interval!r}")
    return value * multipliers[unit]


__all__ = ["date_to_milliseconds", "interval_to_ms"]
