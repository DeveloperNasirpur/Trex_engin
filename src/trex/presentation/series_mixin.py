"""
trex.presentation.series_mixin
==============================
``SeriesMixin`` — قراردادی که به هر ``Indicator`` قدرت می‌دهد:

1. **اعلام series** (``series_defs()``) — چه چیزی روی terminal نمایش داده شود.
2. **ارسال خودکار** — وقتی indicator ``emit()`` می‌کند، ``Point`` می‌سازد
   و مستقیم به ``broadcast_indicators`` می‌فرستد.

معماری
-------
``SeriesMixin`` یک ABC تخصصی است که ``Indicator`` از آن ارث می‌برد.
هر subclass باید ``series_defs()`` را override کند.

مسیر داده::

    Indicator.emit(value)
        └── SeriesMixin._on_emit(value, bar_time)
                └── emit_hook(key → Point)  ← inject شده توسط ctx.attach_server()
                        └── SyncServer.broadcast_indicators({key: [Point]})

``emit_hook`` یک ``Callable[[dict[str, Point]], None]`` است که توسط
``ContextIndicator.attach_server()`` inject می‌شود.

هیچ import مستقیمی از server در این فایل نیست — همه چیز از طریق hook است.
این یعنی engine بدون server هم کار می‌کند (pure computation mode).
"""
from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from trex.domain.types import SeriesDef, Point


class SeriesMixin:
    """
    Mixin که به ``Indicator`` توانایی اعلام series و ارسال خودکار می‌دهد.

    هر indicator باید ``series_defs()`` را پیاده‌سازی کند.

    Subclasses می‌توانند ``_make_points(value, timestamp)`` را override کنند
    تا mapping کاستوم از value به ``{series_key: Point}`` بدهند.
    برای single-series indicators نیازی به override نیست — پیش‌فرض کار می‌کند.
    """

    # Injected by ContextIndicator.attach_server()
    # Signature: (data: dict[str, list[Point]]) -> None
    _emit_hook: Callable[[dict[str, list["Point"]]], None] | None = None

    # Cached series key for single-series indicators (set on first emit)
    _primary_key: str | None = None

    @abstractmethod
    def series_defs(self) -> list["SeriesDef"]:
        """
        اعلام کن چه series هایی روی terminal نمایش داده می‌شود.

        از presets موجود استفاده کن::

            # Single series
            def series_defs(self):
                from trex.presentation.indicators import Overlay
                return [Overlay.sma(self.period)]

            # Multi-series (MACD)
            def series_defs(self):
                from trex.presentation.indicators import Oscillator
                return Oscillator.macd(self.fast_period, self.slow_period)

            # Custom series
            def series_defs(self):
                from trex.domain.types import SeriesDef, Level
                return [SeriesDef(
                    key=f\"my_indic_{self.period}\",
                    label=f\"MyIndic ({self.period})\",
                    pane=\"sub\",
                    kind=\"line\",
                    color=\"#FF5722\",
                    levels=[Level(0, \"#787B86\", 2, \"\")],
                )]

        Returns:
            List of SeriesDef objects. Empty list = indicator is invisible.
        """
        ...

    def _make_points(self, value: Any, timestamp: int) -> "dict[str, list[Point]]":
        """
        Convert emitted value to ``{series_key: [Point]}`` map.

        Override این متد برای:
        - اندیکاتورهای چندسری (MACD → 3 سری)
        - مقادیر dataclass (BBVal.upper → bb_upper، BBVal.lower → bb_lower)
        - coloring شرطی (Supertrend → رنگ بر اساس جهت)

        پیش‌فرض: single float value → اولین series_def.key.

        Args:
            value: مقدار emitted توسط indicator.
            timestamp: Unix timestamp (seconds) از bar time.

        Returns:
            dict mapping series key → [Point].
        """
        from trex.domain.types import Point as TrexPoint

        defs = self.series_defs()
        if not defs:
            return {}

        # پیش‌فرض: مقدار float به اولین series map می‌شود
        if isinstance(value, (int, float)):
            return {defs[0].key: [TrexPoint(time=timestamp, value=float(value))]}

        return {}

    def _on_emit(self, value: Any, ohlcv: Any) -> None:
        """
        Internal hook — توسط Pipeline بعد از هر emit فراخوانی می‌شود.

        Args:
            value: مقدار emitted.
            ohlcv: آخرین OHLCV bar که trigger شد (برای timestamp).
        """
        if self._emit_hook is None:
            return

        # timestamp را از bar بگیر
        ts: int = 0
        if ohlcv is not None and hasattr(ohlcv, "time") and ohlcv.time is not None:
            import datetime
            t = ohlcv.time
            if isinstance(t, (int, float)):
                ts = int(t)
            elif isinstance(t, datetime.datetime):
                ts = int(t.timestamp())
        
        points = self._make_points(value, ts)
        if points:
            self._emit_hook({k: v for k, v in points.items()})


__all__ = ["SeriesMixin"]
