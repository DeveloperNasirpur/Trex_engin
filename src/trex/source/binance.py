from __future__ import annotations
"""
trex.source.binance
===================
Binance Public REST API — 1-minute candle source.
بدون API Key. فقط 1m دانلود می‌شود.
CTF (ConvertTimeFrame) تبدیل به تایم‌فریم بالاتر را انجام می‌دهد.

استفاده live (با trex engine):
    import trex
    trex.init(port=8765)
    trex.rsi("BTCUSDT", "1h", period=14, visible=True)

    src = CandleSourceBinance("BTCUSDT", days=90)
    src.run()   # → trex.push() → store + broadcast + CTF + indicators → TrexTerminal
"""

import time
import json
import urllib.request
from datetime import datetime, timezone
from typing import Callable, TYPE_CHECKING

from trex.source.candle_source import CandleSource

if TYPE_CHECKING:
    from trex.domain.types import Bar

_API_URL = "https://api.binance.com/api/v3/klines"
_BATCH   = 1000


def _parse_date(value: str | datetime) -> int:
    """رشته ISO یا datetime → unix milliseconds."""
    if isinstance(value, datetime):
        return int(value.timestamp() * 1000)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"فرمت تاریخ نامعتبر: '{value}' — از 'YYYY-MM-DD' استفاده کنید")


def _row_to_bar(row: list) -> "Bar":
    """تبدیل یک ردیف Binance klines API به Bar."""
    from trex.domain.types import Bar
    return Bar(
        time=int(row[0]) // 1000,   # ms → unix-seconds
        open=float(row[1]),
        high=float(row[2]),
        low=float(row[3]),
        close=float(row[4]),
        volume=float(row[5]),
    )


class CandleSourceBinance(CandleSource):
    """
    Binance 1-minute candle source (live streaming).

    در live mode با trex.init() استفاده می‌شود:
        src = CandleSourceBinance("BTCUSDT", days=90)
        src.run()
        # → trex.push(bar) → MultiSymbolStore + broadcast_bar + CTF + indicators

    اگر on_provide تنظیم شود، آن callback صدا زده می‌شود به جای trex.push():
        src = CandleSourceBinance("BTCUSDT", days=90)
        src.on_provide = my_custom_handler   # Callable[[Bar], None]
        src.run()

    پارامترها
    ----------
    symbol     : نماد — مثال "BTCUSDT"
    days       : تعداد روزهای گذشته
    start      : تاریخ شروع — "YYYY-MM-DD"
    end        : تاریخ پایان — "YYYY-MM-DD" (پیش‌فرض: الان)
    limit      : حداکثر تعداد کندل 1m
    on_provide : callback سفارشی با signature Callable[[Bar], None]
                 اگر None باشد: trex.push() صدا زده می‌شود (live mode)
    """

    def __init__(
        self,
        symbol:     str,
        *,
        days:       int | None                     = None,
        start:      str | datetime | None          = None,
        end:        str | datetime | None          = None,
        limit:      int | None                     = None,
        on_provide: "Callable[[Bar], None] | None" = None,
    ) -> None:
        self.symbol     = symbol.upper()
        self.days       = days
        self.start      = start
        self.end        = end
        self.limit      = limit
        self.on_provide = on_provide

    def run(self, symbol: str | None = None) -> None:
        """
        دانلود 1m کندل و feed کردن از طریق trex.push() یا on_provide callback.

        - اگر on_provide تنظیم شده: آن callback با Bar صدا زده می‌شود
        - اگر on_provide نباشد (live): trex.push(bar, symbol) صدا زده می‌شود
          که AutoEngine را trigger می‌کند:
          store.update() + broadcast_bar() + ctx.provide() → CTF + indicators

        هیچ چیزی return نمی‌شود.
        """
        sym = (symbol or self.symbol).upper()

        # تعیین callback
        if self.on_provide is not None:
            _emit = self.on_provide
        else:
            from trex.engine.auto import _engine
            if _engine is None:
                raise RuntimeError(
                    "CandleSourceBinance.run() در live mode نیاز به trex.init() دارد."
                    " قبل از run() باید trex.init() فراخوانی شود."
                )
            _sym = sym
            _eng = _engine
            def _emit(bar: "Bar") -> None:
                _eng.push(bar, symbol=_sym)

        # محاسبه بازه زمانی
        now_ms = int(time.time() * 1000)
        tf_ms  = 60_000  # 1m in ms

        if self.start is not None:
            start_ms = _parse_date(self.start)
            end_ms   = _parse_date(self.end) if self.end else now_ms
        elif self.days is not None:
            end_ms   = now_ms
            start_ms = end_ms - self.days * 86_400_000
            if self.limit is not None:
                start_ms = max(start_ms, end_ms - self.limit * tf_ms)
        elif self.limit is not None:
            end_ms   = now_ms
            start_ms = end_ms - self.limit * tf_ms
        else:
            raise ValueError("یکی از پارامترها لازم است: days، start، یا limit")

        _fmt = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
        print(f"[binance] {sym} 1m | {_fmt(start_ms)} → {_fmt(end_ms)}")

        count  = 0
        cursor = start_ms

        while cursor < end_ms:
            batch_end = min(cursor + _BATCH * tf_ms, end_ms)
            url = (
                f"{_API_URL}?symbol={sym}&interval=1m"
                f"&startTime={cursor}&endTime={batch_end}&limit={_BATCH}"
            )

            try:
                with urllib.request.urlopen(url, timeout=15) as resp:
                    rows = json.loads(resp.read())
            except urllib.error.HTTPError as exc:
                raise ConnectionError(
                    f"Binance HTTP {exc.code}: نماد '{sym}' را بررسی کنید"
                ) from exc
            except Exception as exc:
                raise ConnectionError(f"خطا در اتصال به Binance: {exc}") from exc

            if not rows:
                break

            for row in rows:
                _emit(_row_to_bar(row))
                count += 1

            cursor = int(rows[-1][0]) + tf_ms
            time.sleep(0.08)  # rate limit

        print(f"[binance] {count:,} کندل 1m ارسال شد.")


__all__ = ["CandleSourceBinance"]
