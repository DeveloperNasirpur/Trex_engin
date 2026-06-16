from __future__ import annotations
"""trex.source.postgres — PostgreSQL streaming candle source."""

from datetime import datetime, timezone
from typing import Callable

from trex.base.ohlcv import OHLCV
from trex.source.candle_source import CandleSource
from trex.utils import date_to_milliseconds


class CandleSourcePostgres(CandleSource):
    """Streams 1-minute OHLCV candles from a PostgreSQL table.

    Expected columns: ``open_time`` (unix-ms), ``open``, ``high``,
    ``low``, ``close``, ``symbol``.
    """

    def __init__(
        self,
        count_first: int  = 1,
        start_from:  str | None = None,
        on_first:    Callable[..., None] | None = None,
        on_provide:  Callable[[OHLCV], None] | None = None,
        on_finish:   Callable[[], None] | None = None,
    ) -> None:
        self.on_first:   Callable[..., None] | None         = on_first
        self.on_provide: Callable[[OHLCV], None] | None     = on_provide
        self.on_finish:  Callable[[], None] | None          = on_finish
        self.start:      int                                 = (
            date_to_milliseconds(start_from) if start_from else 0
        )
        self._provide: Callable[[OHLCV], None] = (
            self._first if not start_from else self._start_from_time
        )
        self.count_first = count_first
        self.count       = 0

    def _start_from_time(self, ohlcv: OHLCV) -> None:
        mil = date_to_milliseconds(ohlcv.time.strftime("%Y-%m-%d %H:%M:%S"))
        if self.start < mil and self.on_provide:
            self._provide = self.on_provide

    def _first(self, ohlcv: OHLCV) -> None:
        if self.count >= self.count_first and self.on_provide:
            self._provide = self.on_provide
        self.count += 1

    def run(self, table_symbol: str = "BTC_USDT") -> None:
        try:
            import psycopg2
        except ImportError as exc:
            raise ImportError(
                "psycopg2 not installed. Run: pip install psycopg2-binary"
            ) from exc

        from trex.engine.context import ctx

        if not ctx.is_active:
            print("هنوز اندیکاتوری اضافه نشده")
            return

        _provide = (
            (lambda o: (ctx.provide(o), self._provide(o)))
            if self.on_provide else ctx.provide
        )

        sql = (
            f'SELECT open_time, open, high, low, close, symbol '
            f'FROM "{table_symbol}" ORDER BY open_time ASC'
        )

        with psycopg2.connect(**ctx.db_config.to_dict()) as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
                while True:
                    rows = cur.fetchmany(ctx.fetch_size)
                    if not rows:
                        break
                    for row in rows:
                        _provide(self._row_to_ohlcv(row))

        if self.on_finish:
            self.on_finish()

    @staticmethod
    def _row_to_ohlcv(row: tuple) -> OHLCV:
        ts    = float(row[0]) / 1000.0
        open_ = float(row[1])
        close = float(row[4])
        return OHLCV(
            open=open_, high=float(row[2]), low=float(row[3]), close=close,
            volume=None,
            time=datetime.fromtimestamp(ts, tz=timezone.utc),
            side=0 if open_ > close else 1,
            timeframe=1, str_time="1m", symbol=str(row[5]),
        )


__all__ = ["CandleSourcePostgres"]
