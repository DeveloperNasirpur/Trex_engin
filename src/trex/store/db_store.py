"""trex.store.db_store
=====================
PostgreSQL persistence layer for the Trex Engine.

Overview
--------
:class:`TrexStore` is a thread-safe, connection-pooled facade over a
PostgreSQL database that stores OHLCV candles plus a JSONB ``indicators``
document per bar. The physical layout is:

- **One schema per exchange** — ``binance``, ``okx``, ...
- **One table per (symbol, timeframe)** — ``BTCUSDT1M``, ``ETHUSDT5M``, ...
  (upper-case, no separator; always double-quoted in SQL).
- **One row per bar** — ``time BIGINT PRIMARY KEY`` plus typed OHLCV columns
  and an ``indicators JSONB`` column.

Each table is created on demand with the canonical shape::

    CREATE TABLE IF NOT EXISTS "<schema>"."<SYMBOL><TF>" (
        time        BIGINT PRIMARY KEY,
        open        NUMERIC,
        high        NUMERIC,
        low         NUMERIC,
        close       NUMERIC,
        volume      NUMERIC,
        indicators  JSONB        NOT NULL DEFAULT '{}'::jsonb,
        updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
    );

Indicators are stored as a single JSONB document keyed by indicator name::

    {
        "RSI_14":        {"value": 68.45},
        "MACD_12_26_9":  {"macd": 125.3, "signal": 118.7, "histogram": 6.6},
        "BB_20_2":       {"upper": 42500.0, "middle": 42100.0, "lower": 41700.0}
    }

Scalar indicator values supplied as bare numbers are normalised to
``{"value": <number>}`` on write, so reads have a single consistent shape.

Async support
-------------
:class:`AsyncTrexStore` mirrors the synchronous API using
``psycopg.AsyncConnection`` and an ``AsyncConnectionPool``. It is optional —
import it only if your call sites are already ``async``.

Design notes
------------
- **Identifier safety**: schema / table names are validated by
  :mod:`trex.store.utils` before any interpolation; values always travel as
  bound parameters. There is no string-formatted user data in any DML.
- **Connection pooling**: a :class:`psycopg_pool.ConnectionPool` backs every
  operation. If ``psycopg_pool`` is unavailable, a minimal internal pool is
  used as a fallback so the package still functions.
- **Thread safety**: the metadata cache is guarded by an ``RLock``; the pool
  is itself thread-safe. No user code runs while a lock is held.
- **Upsert semantics**: writes use ``INSERT ... ON CONFLICT (time) DO UPDATE``.
  Candle columns are overwritten; the JSONB ``indicators`` document is *merged*
  (``indicators || EXCLUDED.indicators``) so partial indicator updates never
  drop previously-stored keys.
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from trex.store.exceptions import (
    IndicatorError,
    MigrationError,
    StoreConnectionError,
    TrexStoreError,
)
from trex.store.utils import (
    OHLCV_COLUMNS,
    coerce_jsonb_value,
    schema_name,
    split_row,
    table_name,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from trex.domain.types import Bar

__all__ = ["TrexStore", "AsyncTrexStore", "DbConfig"]

_LOG: Final = logging.getLogger("trex.store")

# Columns, excluding the primary key, written on every candle upsert.
_CANDLE_VALUE_COLUMNS: Final[tuple[str, ...]] = OHLCV_COLUMNS[1:]  # open..volume


# ── Configuration ─────────────────────────────────────────────────────────────


@dataclass(slots=True)
class DbConfig:
    """PostgreSQL connection configuration.

    Either provide a libpq ``conninfo`` string via the ``TrexStore`` DSN
    argument, or supply the discrete fields here. :meth:`conninfo` renders
    the value ``psycopg`` expects.

    Attributes:
        host: Server host name.
        port: Server port.
        user: Role name.
        password: Role password.
        dbname: Database name.
    """

    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    dbname: str = "trex"

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "DbConfig":
        """Build a config from a mapping.

        Accepts both ``database`` and ``dbname`` keys for compatibility with
        :class:`trex.source.config.ConfigPostgres`.

        Args:
            mapping: Connection parameters.

        Returns:
            A populated :class:`DbConfig`.
        """
        data = dict(mapping)
        dbname = data.get("dbname", data.get("database", cls.dbname))
        return cls(
            host=str(data.get("host", cls.host)),
            port=int(data.get("port", cls.port)),
            user=str(data.get("user", cls.user)),
            password=str(data.get("password", cls.password)),
            dbname=str(dbname),
        )

    def conninfo(self) -> str:
        """Return a libpq ``conninfo`` connection string."""
        from psycopg.conninfo import make_conninfo

        return make_conninfo(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            dbname=self.dbname,
        )


def _resolve_config(
    config: DbConfig | Mapping[str, Any] | str | None,
    connection_string: str | None,
) -> DbConfig:
    """Normalise the many accepted config forms into one :class:`DbConfig`."""
    if connection_string is not None:
        if config is not None:
            raise TrexStoreError(
                "Pass either 'config' or 'connection_string', not both."
            )
        return _DsnConfig(connection_string)
    if config is None:
        return DbConfig()
    if isinstance(config, DbConfig):
        return config
    if isinstance(config, str):
        return _DsnConfig(config)
    if isinstance(config, Mapping):
        return DbConfig.from_mapping(config)
    raise TrexStoreError(f"Unsupported config type: {type(config)!r}")


# ── Shared SQL / value helpers (used by both sync and async stores) ───────────


class _SqlMixin:
    """Pure SQL-string builders and value coercion shared by both stores.

    None of these touch the database; they exist so the sync and async
    implementations stay byte-for-byte consistent in their SQL.
    """

    # -- DDL ------------------------------------------------------------------

    @staticmethod
    def _ddl_schema(schema: str) -> str:
        return f'CREATE SCHEMA IF NOT EXISTS "{schema}"'

    @staticmethod
    def _ddl_table(schema: str, table: str) -> str:
        return (
            f'CREATE TABLE IF NOT EXISTS "{schema}"."{table}" ('
            f"  time        BIGINT PRIMARY KEY,"
            f"  open        NUMERIC,"
            f"  high        NUMERIC,"
            f"  low         NUMERIC,"
            f"  close       NUMERIC,"
            f"  volume      NUMERIC,"
            f"  indicators  JSONB       NOT NULL DEFAULT '{{}}'::jsonb,"
            f"  updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()"
            f")"
        )

    @staticmethod
    def _ddl_index(schema: str, table: str) -> str:
        # The PK already indexes ``time``; add a GIN index for JSONB lookups.
        return (
            f'CREATE INDEX IF NOT EXISTS "{table}_indicators_gin" '
            f'ON "{schema}"."{table}" USING GIN (indicators)'
        )

    # -- DML builders ---------------------------------------------------------

    @staticmethod
    def _upsert_full_sql(schema: str, table: str) -> str:
        cols = ("time", *_CANDLE_VALUE_COLUMNS, "indicators")
        col_sql = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        update_candles = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in _CANDLE_VALUE_COLUMNS
        )
        return (
            f'INSERT INTO "{schema}"."{table}" ({col_sql}) '
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (time) DO UPDATE SET "
            f"{update_candles}, "
            f'indicators = "{table}".indicators || EXCLUDED.indicators, '
            f"updated_at = NOW()"
        )

    @staticmethod
    def _upsert_candles_sql(schema: str, table: str) -> str:
        cols = ("time", *_CANDLE_VALUE_COLUMNS)
        col_sql = ", ".join(f'"{c}"' for c in cols)
        placeholders = ", ".join(["%s"] * len(cols))
        update_candles = ", ".join(
            f'"{c}" = EXCLUDED."{c}"' for c in _CANDLE_VALUE_COLUMNS
        )
        return (
            f'INSERT INTO "{schema}"."{table}" ({col_sql}) '
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (time) DO UPDATE SET {update_candles}, updated_at = NOW()"
        )

    # -- Value helpers --------------------------------------------------------

    @staticmethod
    def _resolve_names(exchange: str, symbol: str, tf: str) -> tuple[str, str]:
        """Validate and return ``(schema, table)`` for a target."""
        return schema_name(exchange), table_name(symbol, tf)

    @staticmethod
    def _normalise_indicator(value: Any) -> Any:
        """Wrap scalar indicator values as ``{"value": x}``; pass dicts through."""
        if isinstance(value, Mapping):
            return {k: coerce_jsonb_value(v) for k, v in value.items()}
        if isinstance(value, (int, float)):
            return {"value": coerce_jsonb_value(float(value))}
        return {"value": coerce_jsonb_value(value)}

    @staticmethod
    def _unwrap(value: Any) -> Any:
        """Return the scalar from a ``{"value": x}`` doc, else the doc itself."""
        if isinstance(value, Mapping) and set(value.keys()) == {"value"}:
            return value["value"]
        return value

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        """Coerce a JSONB column value into a plain dict."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _time_clause(
        start_ts: int | None,
        end_ts: int | None,
        extra: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        """Build a parametrised ``WHERE`` clause for a time range."""
        clauses: list[str] = []
        params: list[Any] = []
        if extra:
            clauses.append(extra)
        if start_ts is not None:
            clauses.append("time >= %s")
            params.append(start_ts)
        if end_ts is not None:
            clauses.append("time <= %s")
            params.append(end_ts)
        clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        return clause, tuple(params)

    @staticmethod
    def _cutoff_seconds(older_than_days: int) -> int:
        """Return the unix-second cutoff for ``now - older_than_days``."""
        import time as _time

        return int(_time.time() - older_than_days * 86_400)

    def _build_param_row(self, row: Mapping[str, Any]) -> tuple[Any, ...]:
        """Convert a save row into a positional parameter tuple."""
        candle, indicators = split_row(dict(row))
        normalised = {k: self._normalise_indicator(v) for k, v in indicators.items()}
        try:
            json.dumps(normalised)  # surface serialisation errors early
        except (TypeError, ValueError) as exc:
            raise IndicatorError(
                f"Indicator payload for time={candle.get('time')!r} "
                f"is not JSON-serialisable: {exc}"
            ) from exc
        from psycopg.types.json import Jsonb

        values: list[Any] = [candle["time"]]
        values.extend(candle.get(c) for c in _CANDLE_VALUE_COLUMNS)
        values.append(Jsonb(normalised))
        return tuple(values)


def _num(value: Any) -> float | None:
    """Coerce a NUMERIC column value to ``float`` (or None)."""
    if value is None:
        return None
    return float(value)


def _row_to_candle(row: Sequence[Any]) -> dict[str, Any]:
    """Map a ``(time, o, h, l, c, v)`` tuple to an OHLCV dict."""
    return {
        "time": int(row[0]),
        "open": _num(row[1]),
        "high": _num(row[2]),
        "low": _num(row[3]),
        "close": _num(row[4]),
        "volume": _num(row[5]),
    }


# ── Synchronous store ─────────────────────────────────────────────────────────


class TrexStore(_SqlMixin):
    """Thread-safe PostgreSQL store for Trex candles and indicators.

    The store maintains a cached view of the database structure
    (``{exchange: {table: [indicator, ...]}}``) so metadata queries are
    served without a round-trip. The cache is refreshed lazily on first use
    and incrementally after every write.

    Args:
        config: A :class:`DbConfig`, a mapping of connection parameters, or a
            libpq ``conninfo`` / DSN string. Mutually exclusive with
            *connection_string*.
        connection_string: Convenience alias accepting a DSN string.
        min_size: Minimum pooled connections.
        max_size: Maximum pooled connections.
        scan_on_init: When ``True`` (default), the metadata cache is populated
            during construction. Set ``False`` to defer the first query.

    Raises:
        StoreConnectionError: If the pool cannot be opened.
        TrexStoreError: If the configuration is missing or contradictory.
    """

    def __init__(
        self,
        config: DbConfig | Mapping[str, Any] | str | None = None,
        *,
        connection_string: str | None = None,
        min_size: int = 1,
        max_size: int = 8,
        scan_on_init: bool = True,
    ) -> None:
        self._config = _resolve_config(config, connection_string)
        self._lock = threading.RLock()
        # {exchange: {table_name: [indicator_name, ...]}}
        self._meta: dict[str, dict[str, list[str]]] = {}
        self._meta_loaded = False
        self._pool = self._build_pool(min_size=min_size, max_size=max_size)
        _LOG.info(
            "TrexStore initialised (pool=%s)", type(self._pool).__name__
        )
        if scan_on_init:
            self._scan_metadata()

    # ── Construction helpers ──────────────────────────────────────────────────

    def _build_pool(self, *, min_size: int, max_size: int) -> Any:
        """Construct a connection pool, preferring ``psycopg_pool``."""
        conninfo = self._config.conninfo()
        try:
            from psycopg_pool import ConnectionPool

            pool = ConnectionPool(
                conninfo=conninfo,
                min_size=min_size,
                max_size=max_size,
                open=True,
                kwargs={"autocommit": False},
            )
            pool.wait(timeout=10.0)
            return pool
        except ImportError:
            _LOG.warning(
                "psycopg_pool not installed; using a minimal built-in pool. "
                "Install 'psycopg[pool]' for production use."
            )
            return _MiniPool(conninfo=conninfo, max_size=max_size)
        except Exception as exc:  # pragma: no cover - environment dependent
            _LOG.error("Failed to open connection pool: %s", exc)
            raise StoreConnectionError(
                f"Could not open connection pool: {exc}"
            ) from exc

    @contextmanager
    def _connection(self) -> "Iterator[Any]":
        """Yield a pooled connection, translating driver errors.

        Transactions are committed on success and rolled back on error.
        """
        try:
            with self._pool.connection() as conn:
                try:
                    yield conn
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
        except StoreConnectionError:
            raise
        except Exception as exc:
            import psycopg

            if isinstance(exc, psycopg.OperationalError):
                _LOG.error("Database connection error: %s", exc)
                raise StoreConnectionError(str(exc)) from exc
            raise

    # ── Metadata cache ────────────────────────────────────────────────────────

    def _scan_metadata(self) -> None:
        """Populate the metadata cache from ``information_schema``."""
        meta: dict[str, dict[str, list[str]]] = {}
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN
                      ('pg_catalog', 'information_schema', 'public')
                ORDER BY table_schema, table_name
                """
            )
            for schema, table in cur.fetchall():
                meta.setdefault(schema, {})[table] = []

            for schema, tables in meta.items():
                for table in tables:
                    cur.execute(
                        f'SELECT DISTINCT jsonb_object_keys(indicators) '
                        f'FROM "{schema}"."{table}" '
                        f"WHERE indicators <> '{{}}'::jsonb "
                        f"LIMIT 1000"
                    )
                    tables[table] = sorted(r[0] for r in cur.fetchall())

        with self._lock:
            self._meta = meta
            self._meta_loaded = True
        _LOG.debug(
            "Metadata scanned: %d exchange(s), %d table(s).",
            len(meta),
            sum(len(t) for t in meta.values()),
        )

    def _ensure_meta(self) -> None:
        """Lazily populate the cache if construction deferred the scan."""
        with self._lock:
            loaded = self._meta_loaded
        if not loaded:
            self._scan_metadata()

    def refresh(self) -> None:
        """Force a full re-scan of the database metadata cache."""
        self._scan_metadata()

    def _touch_meta(self, schema: str, table: str, indicators: set[str]) -> None:
        """Incrementally update the cache after a write."""
        with self._lock:
            tables = self._meta.setdefault(schema, {})
            existing = tables.setdefault(table, [])
            if indicators:
                tables[table] = sorted(set(existing) | indicators)

    # ── Schema / table management ─────────────────────────────────────────────

    def _ensure_schema(self, cur: Any, schema: str) -> None:
        cur.execute(self._ddl_schema(schema))

    def _ensure_table(self, cur: Any, schema: str, table: str) -> None:
        cur.execute(self._ddl_table(schema, table))
        cur.execute(self._ddl_index(schema, table))

    # ── Public: metadata queries ──────────────────────────────────────────────

    def get_exchanges(self) -> list[str]:
        """Return all known exchanges (schema names).

        Returns:
            A sorted list of exchange identifiers.
        """
        self._ensure_meta()
        with self._lock:
            return sorted(self._meta.keys())

    def get_tables(self, exchange: str) -> dict[str, list[str]]:
        """Return the tables of an exchange mapped to their indicators.

        Args:
            exchange: Exchange identifier.

        Returns:
            A mapping ``{table_name: [indicator_name, ...]}``. Empty if the
            exchange is unknown.
        """
        ex = schema_name(exchange)
        self._ensure_meta()
        with self._lock:
            return {t: list(inds) for t, inds in self._meta.get(ex, {}).items()}

    def table_exists(self, exchange: str, symbol: str, tf: str) -> bool:
        """Return whether a ``{SYMBOL}{TF}`` table exists for an exchange.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.

        Returns:
            ``True`` if the table is present in the cache.
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        self._ensure_meta()
        with self._lock:
            return table in self._meta.get(ex, {})

    def list_all_indicators(self, exchange: str | None = None) -> list[str]:
        """Return every distinct indicator name across tables.

        Args:
            exchange: When given, restrict the scan to that exchange;
                otherwise scan all exchanges.

        Returns:
            A sorted list of unique indicator names.
        """
        self._ensure_meta()
        names: set[str] = set()
        with self._lock:
            if exchange is not None:
                ex = schema_name(exchange)
                for inds in self._meta.get(ex, {}).values():
                    names.update(inds)
            else:
                for tables in self._meta.values():
                    for inds in tables.values():
                        names.update(inds)
        return sorted(names)

    def get_candle_count(self, exchange: str, symbol: str, tf: str) -> int:
        """Return the total number of candles stored in a table.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.

        Returns:
            The row count, or ``0`` if the table does not exist.
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return 0
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(f'SELECT COUNT(*) FROM "{ex}"."{table}"')
            return int(cur.fetchone()[0])

    def get_indicator_stats(
        self, exchange: str, symbol: str, tf: str, indicator_name: str
    ) -> dict[str, Any] | None:
        """Return aggregate statistics for one scalar-valued indicator.

        Statistics are computed over the ``indicators -> name -> 'value'``
        path, so they are meaningful for scalar indicators (RSI, ATR, ...).
        For multi-field indicators (MACD, BB, ...) there is no single
        ``value`` key and the numeric stats will be ``None``; use
        :meth:`get_indicator` to inspect their structure instead.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            indicator_name: Indicator JSONB key.

        Returns:
            A dict ``{"count", "min", "max", "avg", "last_value", "last_time"}``,
            or ``None`` if the table/indicator is absent.
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return None

        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT "
                f"  COUNT(*) FILTER (WHERE indicators ? %s), "
                f"  MIN((indicators #>> %s)::numeric), "
                f"  MAX((indicators #>> %s)::numeric), "
                f"  AVG((indicators #>> %s)::numeric) "
                f'FROM "{ex}"."{table}"',
                (
                    indicator_name,
                    [indicator_name, "value"],
                    [indicator_name, "value"],
                    [indicator_name, "value"],
                ),
            )
            count, vmin, vmax, vavg = cur.fetchone()
            if not count:
                return {
                    "count": 0,
                    "min": None,
                    "max": None,
                    "avg": None,
                    "last_value": None,
                    "last_time": None,
                }

            cur.execute(
                f"SELECT time, indicators -> %s "
                f'FROM "{ex}"."{table}" '
                f"WHERE indicators ? %s "
                f"ORDER BY time DESC LIMIT 1",
                (indicator_name, indicator_name),
            )
            last = cur.fetchone()

        last_value = self._unwrap(last[1]) if last else None
        last_time = int(last[0]) if last else None
        return {
            "count": int(count),
            "min": _num(vmin),
            "max": _num(vmax),
            "avg": _num(vavg),
            "last_value": last_value,
            "last_time": last_time,
        }

    # ── Public: reads ─────────────────────────────────────────────────────────

    def get_indicator(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicator_name: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return one indicator's time series in ascending time order.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            indicator_name: JSONB key to extract (e.g. ``"RSI_14"``).
            start_ts: Inclusive lower bound on ``time`` (unix seconds), or None.
            end_ts: Inclusive upper bound on ``time`` (unix seconds), or None.

        Returns:
            A list of ``{"time": ts, indicator_name: value}`` dicts. Rows
            lacking the indicator are skipped.
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return []

        where, time_params = self._time_clause(
            start_ts, end_ts, extra="indicators ? %s"
        )
        sql = (
            f"SELECT time, indicators -> %s AS val "
            f'FROM "{ex}"."{table}" '
            f"{where} "
            f"ORDER BY time ASC"
        )
        out: list[dict[str, Any]] = []
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (indicator_name, indicator_name, *time_params))
            for ts, val in cur.fetchall():
                out.append({"time": int(ts), indicator_name: self._unwrap(val)})
        return out

    def get_candles_with_indicators(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicators: Sequence[str],
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return candles with the requested indicators, ascending by time.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            indicators: Indicator names to attach to each candle.
            start_ts: Inclusive lower bound on ``time``, or None.
            end_ts: Inclusive upper bound on ``time``, or None.
            limit: When set, return only the most recent *limit* rows (still
                ordered ascending in the result).

        Returns:
            A list of flat dicts, each containing OHLCV fields plus one key per
            requested indicator (missing indicators are omitted for that row).
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return []

        where, params = self._time_clause(start_ts, end_ts)
        order = "DESC" if limit is not None else "ASC"
        limit_clause = "LIMIT %s" if limit is not None else ""
        tail_params: tuple[Any, ...] = (limit,) if limit is not None else ()

        sql = (
            f"SELECT time, open, high, low, close, volume, indicators "
            f'FROM "{ex}"."{table}" '
            f"{where} "
            f"ORDER BY time {order} "
            f"{limit_clause}"
        )
        wanted = list(indicators)
        rows: list[dict[str, Any]] = []
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, (*params, *tail_params))
            for row in cur.fetchall():
                record = _row_to_candle(row)
                document = self._as_dict(row[6])
                for name in wanted:
                    if name in document:
                        record[name] = self._unwrap(document[name])
                rows.append(record)

        if order == "DESC":
            rows.reverse()
        return rows

    def get_latest_bar(
        self, exchange: str, symbol: str, tf: str
    ) -> dict[str, Any] | None:
        """Return the most recent candle (with its indicators), or ``None``.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.

        Returns:
            A flat OHLCV dict with an ``"indicators"`` document, or ``None`` if
            the table is empty or missing.
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return None
        sql = (
            f"SELECT time, open, high, low, close, volume, indicators "
            f'FROM "{ex}"."{table}" '
            f"ORDER BY time DESC LIMIT 1"
        )
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()
        if row is None:
            return None
        record = _row_to_candle(row)
        record["indicators"] = self._as_dict(row[6])
        return record

    def is_indicator_complete(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicator_name: str,
        last_n: int = 500,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Report whether an indicator is fully populated over the last N bars.

        "Complete" means every one of the most recent *last_n* candles carries
        the named indicator (i.e. there are no gaps in the recent tail).

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            indicator_name: Indicator JSONB key to check.
            last_n: Window size of most-recent bars to inspect.

        Returns:
            A ``(complete, records)`` tuple. *records* are the last *last_n*
            ``{"time": ts, indicator_name: value}`` rows in ascending time
            order that carry the indicator. *complete* is ``True`` only when
            that count equals the number of candles in the window.
        """
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return False, []

        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM ("
                f'  SELECT 1 FROM "{ex}"."{table}" ORDER BY time DESC LIMIT %s'
                f") s",
                (last_n,),
            )
            window_count = int(cur.fetchone()[0])

            cur.execute(
                f"SELECT time, indicators -> %s AS val FROM ("
                f'  SELECT time, indicators FROM "{ex}"."{table}" '
                f"  ORDER BY time DESC LIMIT %s"
                f") s "
                f"WHERE indicators ? %s "
                f"ORDER BY time ASC",
                (indicator_name, last_n, indicator_name),
            )
            records = [
                {"time": int(ts), indicator_name: self._unwrap(val)}
                for ts, val in cur.fetchall()
            ]

        complete = window_count > 0 and len(records) == window_count
        return complete, records

    # ── Public: reads (extended) ──────────────────────────────────────────────

    def fetch_bars(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list["Bar"]:
        """Return all candles as :class:`~trex.domain.types.Bar` objects, ascending.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            start_ts: Inclusive lower bound (unix seconds), or None.
            end_ts: Inclusive upper bound (unix seconds), or None.

        Returns:
            List of ``Bar`` objects ordered oldest → newest.
        """
        from trex.domain.types import Bar

        ex, table = self._resolve_names(exchange, symbol, tf)
        if not self.table_exists(exchange, symbol, tf):
            return []

        where, params = self._time_clause(start_ts, end_ts)
        sql = (
            f'SELECT time, open, high, low, close, volume '
            f'FROM "{ex}"."{table}" '
            f"{where} ORDER BY time ASC"
        )
        bars: list[Bar] = []
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            while True:
                rows = cur.fetchmany(10_000)
                if not rows:
                    break
                for row in rows:
                    try:
                        bars.append(Bar(
                            time=int(row[0]),
                            open=float(row[1] or 0),
                            high=float(row[2] or 0),
                            low=float(row[3] or 0),
                            close=float(row[4] or 0),
                            volume=float(row[5] or 0),
                        ))
                    except (ValueError, TypeError):
                        _LOG.warning("fetch_bars: skipping malformed row time=%s", row[0])
        return bars

    def bulk_update_indicators(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        by_time: "dict[int, dict[str, Any]]",
    ) -> int:
        """Batch-merge indicator values for many bars in one transaction.

        Unlike :meth:`save_indicators`, OHLCV columns are never touched —
        only the ``indicators`` JSONB document is updated (via ``||`` merge).

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            by_time: Mapping ``{unix_ts: {series_key: value, ...}}``.

        Returns:
            Number of rows written.
        """
        if not by_time:
            return 0
        from psycopg.types.json import Jsonb

        ex, table = self._resolve_names(exchange, symbol, tf)
        sql = (
            f'INSERT INTO "{ex}"."{table}" (time, indicators) VALUES (%s, %s) '
            f"ON CONFLICT (time) DO UPDATE SET "
            f'indicators = "{table}".indicators || EXCLUDED.indicators, '
            f"updated_at = NOW()"
        )
        all_keys: set[str] = set()
        params: list[tuple[Any, Any]] = []
        for ts, ind_data in sorted(by_time.items()):
            normalised = {k: self._normalise_indicator(v) for k, v in ind_data.items()}
            all_keys.update(normalised.keys())
            params.append((ts, Jsonb(normalised)))

        # Write in chunks of 5 000 rows to avoid giant single transactions
        # that risk timeout / OOM on large seeds (e.g. 1 M candles).
        CHUNK = 5_000
        written = 0
        with self._connection() as conn, conn.cursor() as cur:
            self._ensure_schema(cur, ex)
            self._ensure_table(cur, ex, table)
            for i in range(0, len(params), CHUNK):
                cur.executemany(sql, params[i : i + CHUNK])
                written += min(CHUNK, len(params) - i)

        self._touch_meta(ex, table, all_keys)
        _LOG.debug(
            "bulk_update_indicators %s.%s: %d row(s).", ex, table, written
        )
        return written

    def save_indicator_state(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicator_key: str,
        state: "dict[str, Any]",
        last_bar_time: int,
    ) -> None:
        """Persist one indicator's internal state and last processed bar time."""
        from psycopg.types.json import Jsonb
        ex, table = self._resolve_names(exchange, symbol, tf)
        states_table = f"{table}_ind_states"
        sql_create = f"""
            CREATE TABLE IF NOT EXISTS "{ex}"."{states_table}" (
                indicator_key TEXT NOT NULL,
                last_bar_time BIGINT NOT NULL,
                state JSONB NOT NULL DEFAULT '{{}}',
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (indicator_key)
            )
        """
        sql_upsert = f"""
            INSERT INTO "{ex}"."{states_table}" (indicator_key, last_bar_time, state)
            VALUES (%s, %s, %s)
            ON CONFLICT (indicator_key) DO UPDATE SET
                last_bar_time = EXCLUDED.last_bar_time,
                state         = EXCLUDED.state,
                updated_at    = NOW()
        """
        with self._connection() as conn, conn.cursor() as cur:
            self._ensure_schema(cur, ex)
            cur.execute(sql_create)
            cur.execute(sql_upsert, (indicator_key, last_bar_time, Jsonb(state)))

    def load_indicator_state(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicator_key: str,
    ) -> "dict[str, Any] | None":
        """Load persisted indicator state. Returns None if not found."""
        ex, table = self._resolve_names(exchange, symbol, tf)
        states_table = f"{table}_ind_states"
        sql_check = f"""
            SELECT to_regclass('"{ex}"."{states_table}"')
        """
        sql_select = f"""
            SELECT last_bar_time, state FROM "{ex}"."{states_table}"
            WHERE indicator_key = %s
        """
        with self._connection() as conn, conn.cursor() as cur:
            cur.execute(sql_check)
            if cur.fetchone()[0] is None:
                return None
            cur.execute(sql_select, (indicator_key,))
            row = cur.fetchone()
            if row is None:
                return None
            return {"last_bar_time": int(row[0]), "state": dict(row[1] or {})}

    # ── Public: writes ────────────────────────────────────────────────────────

    def save_indicators(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        data: Sequence[Mapping[str, Any]],
    ) -> int:
        """Upsert candles and merge their indicators.

        Each row is a flat mapping mixing OHLCV fields and indicator fields.
        OHLCV columns are overwritten on conflict; the JSONB ``indicators``
        document is *merged* with the existing one, so this method can be used
        to add indicators incrementally without losing previously-stored keys.
        Scalar indicator values are normalised to ``{"value": <number>}``.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            data: Rows to upsert.

        Returns:
            The number of rows written.

        Raises:
            IndicatorError: If a row cannot be serialised to JSONB.
        """
        if not data:
            return 0
        ex, table = self._resolve_names(exchange, symbol, tf)
        sql = self._upsert_full_sql(ex, table)

        param_rows = [self._build_param_row(row) for row in data]
        all_indicator_keys: set[str] = set()
        for row in data:
            _, ind_doc = split_row(dict(row))
            all_indicator_keys.update(ind_doc.keys())

        with self._connection() as conn, conn.cursor() as cur:
            self._ensure_schema(cur, ex)
            self._ensure_table(cur, ex, table)
            cur.executemany(sql, param_rows)

        self._touch_meta(ex, table, all_indicator_keys)
        _LOG.debug("save_indicators %s.%s: %d row(s).", ex, table, len(param_rows))
        return len(param_rows)

    def update_indicator_only(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        time: int,
        indicator_data: Mapping[str, Any],
    ) -> bool:
        """Merge indicator values into a single existing candle.

        Only the JSONB ``indicators`` document is touched; OHLCV columns are
        left untouched. If the candle row does not yet exist, it is created
        with NULL OHLCV columns so the indicators are not lost.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            time: Unix timestamp (seconds) of the candle to update.
            indicator_data: Mapping of indicator name to value/struct.

        Returns:
            ``True`` if a row was inserted or updated.

        Raises:
            IndicatorError: If *indicator_data* cannot be serialised.
        """
        if not indicator_data:
            return False
        ex, table = self._resolve_names(exchange, symbol, tf)

        normalised = {
            k: self._normalise_indicator(v) for k, v in indicator_data.items()
        }
        try:
            json.dumps(normalised)
        except (TypeError, ValueError) as exc:
            raise IndicatorError(
                f"Indicator payload for time={time!r} is not "
                f"JSON-serialisable: {exc}"
            ) from exc
        from psycopg.types.json import Jsonb

        sql = (
            f'INSERT INTO "{ex}"."{table}" (time, indicators) '
            f"VALUES (%s, %s) "
            f"ON CONFLICT (time) DO UPDATE SET "
            f'indicators = "{table}".indicators || EXCLUDED.indicators, '
            f"updated_at = NOW()"
        )
        with self._connection() as conn, conn.cursor() as cur:
            self._ensure_schema(cur, ex)
            self._ensure_table(cur, ex, table)
            cur.execute(sql, (time, Jsonb(normalised)))
            affected = cur.rowcount

        self._touch_meta(ex, table, set(normalised.keys()))
        return bool(affected)

    def bulk_save_candles(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        bars: Iterable["Bar"],
    ) -> int:
        """Upsert candles only, leaving any existing indicators untouched.

        Args:
            exchange: Exchange identifier.
            symbol: Trading pair.
            tf: Timeframe.
            bars: An iterable of :class:`trex.domain.types.Bar`.

        Returns:
            The number of bars written.
        """
        bar_list = list(bars)
        if not bar_list:
            return 0
        ex, table = self._resolve_names(exchange, symbol, tf)
        sql = self._upsert_candles_sql(ex, table)
        params = [
            (b.time, b.open, b.high, b.low, b.close, b.volume) for b in bar_list
        ]
        with self._connection() as conn, conn.cursor() as cur:
            self._ensure_schema(cur, ex)
            self._ensure_table(cur, ex, table)
            cur.executemany(sql, params)
        self._touch_meta(ex, table, set())
        _LOG.debug("bulk_save_candles %s.%s: %d bar(s).", ex, table, len(params))
        return len(params)

    def migrate_from_memory_store(
        self,
        memory_store: Any,
        exchange: str,
        symbol: str,
        tf: str,
    ) -> int:
        """Migrate candles and cached indicators from an in-memory store.

        Accepts a :class:`trex.server.store.CandleStore` (or anything exposing
        a compatible interface): it must provide either a ``recent(n)`` method
        or a ``_bars`` attribute yielding :class:`Bar` objects, and an
        ``indicator_cache`` mapping ``{series_key: [Point, ...]}``.

        Candles are written first, then each cached indicator series is merged
        in by timestamp via :meth:`update_indicator_only`.

        Args:
            memory_store: The source in-memory store.
            exchange: Destination exchange.
            symbol: Destination symbol.
            tf: Destination timeframe.

        Returns:
            The number of candles migrated.

        Raises:
            MigrationError: If the source object is not shaped as expected.
        """
        bars = self._extract_bars(memory_store)
        written = self.bulk_save_candles(exchange, symbol, tf, bars)

        cache = getattr(memory_store, "indicator_cache", None)
        if isinstance(cache, Mapping):
            # Group indicator points by timestamp into per-candle merges.
            by_time: dict[int, dict[str, Any]] = {}
            for series_key, points in cache.items():
                for pt in points:
                    ts = int(getattr(pt, "time"))
                    value = getattr(pt, "value")
                    by_time.setdefault(ts, {})[series_key] = value
            for ts, ind in by_time.items():
                self.update_indicator_only(exchange, symbol, tf, ts, ind)

        _LOG.info(
            "Migrated %d candle(s) into %s.%s.",
            written,
            schema_name(exchange),
            table_name(symbol, tf),
        )
        return written

    @staticmethod
    def _extract_bars(memory_store: Any) -> list["Bar"]:
        """Pull a list of Bars out of a CandleStore-like object."""
        if hasattr(memory_store, "recent") and callable(memory_store.recent):
            try:
                return list(memory_store.recent(10**9))
            except Exception as exc:  # pragma: no cover - defensive
                raise MigrationError(
                    f"memory_store.recent() failed: {exc}"
                ) from exc
        bars = getattr(memory_store, "_bars", None)
        if bars is not None:
            return list(bars)
        raise MigrationError(
            "memory_store must expose a recent() method or a _bars attribute."
        )

    def delete_old_data(
        self,
        exchange: str | None = None,
        symbol: str | None = None,
        tf: str | None = None,
        older_than_days: int = 90,
    ) -> int:
        """Delete candles older than a cutoff across one or many tables.

        The cutoff is ``now() - older_than_days`` compared against ``time``
        (interpreted as unix seconds).

        Args:
            exchange: Restrict to this exchange, or None for all exchanges.
            symbol: Restrict to this symbol (requires *tf*), or None.
            tf: Restrict to this timeframe (requires *symbol*), or None.
            older_than_days: Age threshold in days.

        Returns:
            The total number of rows deleted.
        """
        cutoff = self._cutoff_seconds(older_than_days)
        targets = self._select_targets(exchange, symbol, tf)
        deleted = 0
        with self._connection() as conn, conn.cursor() as cur:
            for ex, table in targets:
                cur.execute(
                    f'DELETE FROM "{ex}"."{table}" WHERE time < %s', (cutoff,)
                )
                deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        _LOG.info("delete_old_data removed %d row(s).", deleted)
        return deleted

    def _select_targets(
        self, exchange: str | None, symbol: str | None, tf: str | None
    ) -> list[tuple[str, str]]:
        """Resolve the (schema, table) pairs a delete/scan should touch."""
        self._ensure_meta()
        if symbol is not None and tf is not None:
            if exchange is None:
                raise TrexStoreError(
                    "exchange is required when symbol and tf are given."
                )
            return [self._resolve_names(exchange, symbol, tf)]
        with self._lock:
            if exchange is not None:
                ex = schema_name(exchange)
                return [(ex, t) for t in self._meta.get(ex, {})]
            return [(ex, t) for ex, ts in self._meta.items() for t in ts]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying connection pool."""
        try:
            self._pool.close()
            _LOG.info("TrexStore pool closed.")
        except Exception:  # pragma: no cover - defensive
            _LOG.debug("Pool close raised; ignoring.", exc_info=True)

    def __enter__(self) -> "TrexStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ── Asynchronous store ────────────────────────────────────────────────────────


class AsyncTrexStore(_SqlMixin):
    """Async counterpart of :class:`TrexStore` using ``psycopg.AsyncConnection``.

    The public coroutine methods mirror the synchronous API. Use
    :meth:`create` to construct and warm up the pool::

        store = await AsyncTrexStore.create("postgresql://...")
        await store.save_indicators("binance", "BTCUSDT", "1m", rows)
        await store.aclose()

    The metadata cache is guarded by an ``asyncio.Lock``.
    """

    def __init__(
        self,
        config: DbConfig | Mapping[str, Any] | str | None = None,
        *,
        connection_string: str | None = None,
        min_size: int = 1,
        max_size: int = 8,
    ) -> None:
        import asyncio

        self._config = _resolve_config(config, connection_string)
        self._min_size = min_size
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._meta: dict[str, dict[str, list[str]]] = {}
        self._meta_loaded = False
        self._pool: Any = None

    @classmethod
    async def create(
        cls,
        config: DbConfig | Mapping[str, Any] | str | None = None,
        *,
        connection_string: str | None = None,
        min_size: int = 1,
        max_size: int = 8,
        scan_on_init: bool = True,
    ) -> "AsyncTrexStore":
        """Construct an async store and open its connection pool.

        Args:
            config: As in :class:`TrexStore`.
            connection_string: DSN alias.
            min_size: Minimum pooled connections.
            max_size: Maximum pooled connections.
            scan_on_init: Populate the metadata cache immediately.

        Returns:
            A ready-to-use :class:`AsyncTrexStore`.

        Raises:
            StoreConnectionError: If the async pool cannot be opened.
        """
        self = cls(
            config,
            connection_string=connection_string,
            min_size=min_size,
            max_size=max_size,
        )
        try:
            from psycopg_pool import AsyncConnectionPool

            self._pool = AsyncConnectionPool(
                conninfo=self._config.conninfo(),
                min_size=min_size,
                max_size=max_size,
                open=False,
                kwargs={"autocommit": False},
            )
            await self._pool.open(wait=True, timeout=10.0)
        except ImportError as exc:
            raise StoreConnectionError(
                "AsyncTrexStore requires 'psycopg[pool]'. "
                "Install it with: pip install 'psycopg[binary,pool]'."
            ) from exc
        except Exception as exc:  # pragma: no cover - environment dependent
            raise StoreConnectionError(
                f"Could not open async connection pool: {exc}"
            ) from exc

        _LOG.info("AsyncTrexStore initialised.")
        if scan_on_init:
            await self._scan_metadata()
        return self

    # ── Connection / metadata ─────────────────────────────────────────────────

    async def _scan_metadata(self) -> None:
        meta: dict[str, dict[str, list[str]]] = {}
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema NOT IN
                          ('pg_catalog', 'information_schema', 'public')
                    ORDER BY table_schema, table_name
                    """
                )
                for schema, table in await cur.fetchall():
                    meta.setdefault(schema, {})[table] = []
                for schema, tables in meta.items():
                    for table in tables:
                        await cur.execute(
                            f"SELECT DISTINCT jsonb_object_keys(indicators) "
                            f'FROM "{schema}"."{table}" '
                            f"WHERE indicators <> '{{}}'::jsonb LIMIT 1000"
                        )
                        tables[table] = sorted(r[0] for r in await cur.fetchall())
            await conn.commit()
        async with self._lock:
            self._meta = meta
            self._meta_loaded = True

    async def _ensure_meta(self) -> None:
        async with self._lock:
            loaded = self._meta_loaded
        if not loaded:
            await self._scan_metadata()

    async def refresh(self) -> None:
        """Force a full async re-scan of the metadata cache."""
        await self._scan_metadata()

    async def _touch_meta(
        self, schema: str, table: str, indicators: set[str]
    ) -> None:
        async with self._lock:
            tables = self._meta.setdefault(schema, {})
            existing = tables.setdefault(table, [])
            if indicators:
                tables[table] = sorted(set(existing) | indicators)

    async def _table_exists(self, schema: str, table: str) -> bool:
        await self._ensure_meta()
        async with self._lock:
            return table in self._meta.get(schema, {})

    # ── Public async API (subset mirroring the sync store) ────────────────────

    async def get_exchanges(self) -> list[str]:
        """Return all known exchanges (schema names)."""
        await self._ensure_meta()
        async with self._lock:
            return sorted(self._meta.keys())

    async def get_tables(self, exchange: str) -> dict[str, list[str]]:
        """Return ``{table: [indicator, ...]}`` for an exchange."""
        ex = schema_name(exchange)
        await self._ensure_meta()
        async with self._lock:
            return {t: list(i) for t, i in self._meta.get(ex, {}).items()}

    async def table_exists(self, exchange: str, symbol: str, tf: str) -> bool:
        """Return whether a ``{SYMBOL}{TF}`` table exists."""
        ex, table = self._resolve_names(exchange, symbol, tf)
        return await self._table_exists(ex, table)

    async def list_all_indicators(self, exchange: str | None = None) -> list[str]:
        """Return every distinct indicator name across tables."""
        await self._ensure_meta()
        names: set[str] = set()
        async with self._lock:
            scopes = (
                [self._meta.get(schema_name(exchange), {})]
                if exchange is not None
                else list(self._meta.values())
            )
        for tables in scopes:
            for inds in tables.values():
                names.update(inds)
        return sorted(names)

    async def get_candle_count(self, exchange: str, symbol: str, tf: str) -> int:
        """Return the total number of candles stored in a table."""
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not await self._table_exists(ex, table):
            return 0
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(f'SELECT COUNT(*) FROM "{ex}"."{table}"')
                row = await cur.fetchone()
            await conn.commit()
        return int(row[0])

    async def get_indicator(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicator_name: str,
        start_ts: int | None = None,
        end_ts: int | None = None,
    ) -> list[dict[str, Any]]:
        """Async: return one indicator's time series, ascending."""
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not await self._table_exists(ex, table):
            return []
        where, time_params = self._time_clause(
            start_ts, end_ts, extra="indicators ? %s"
        )
        sql = (
            f"SELECT time, indicators -> %s AS val "
            f'FROM "{ex}"."{table}" {where} ORDER BY time ASC'
        )
        out: list[dict[str, Any]] = []
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (indicator_name, indicator_name, *time_params))
                for ts, val in await cur.fetchall():
                    out.append({"time": int(ts), indicator_name: self._unwrap(val)})
            await conn.commit()
        return out

    async def get_candles_with_indicators(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        indicators: Sequence[str],
        start_ts: int | None = None,
        end_ts: int | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Async: return candles with the requested indicators, ascending."""
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not await self._table_exists(ex, table):
            return []
        where, params = self._time_clause(start_ts, end_ts)
        order = "DESC" if limit is not None else "ASC"
        limit_clause = "LIMIT %s" if limit is not None else ""
        tail: tuple[Any, ...] = (limit,) if limit is not None else ()
        sql = (
            f"SELECT time, open, high, low, close, volume, indicators "
            f'FROM "{ex}"."{table}" {where} ORDER BY time {order} {limit_clause}'
        )
        wanted = list(indicators)
        rows: list[dict[str, Any]] = []
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (*params, *tail))
                for row in await cur.fetchall():
                    record = _row_to_candle(row)
                    document = self._as_dict(row[6])
                    for name in wanted:
                        if name in document:
                            record[name] = self._unwrap(document[name])
                    rows.append(record)
            await conn.commit()
        if order == "DESC":
            rows.reverse()
        return rows

    async def get_latest_bar(
        self, exchange: str, symbol: str, tf: str
    ) -> dict[str, Any] | None:
        """Async: return the most recent candle with indicators, or None."""
        ex, table = self._resolve_names(exchange, symbol, tf)
        if not await self._table_exists(ex, table):
            return None
        sql = (
            f"SELECT time, open, high, low, close, volume, indicators "
            f'FROM "{ex}"."{table}" ORDER BY time DESC LIMIT 1'
        )
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql)
                row = await cur.fetchone()
            await conn.commit()
        if row is None:
            return None
        record = _row_to_candle(row)
        record["indicators"] = self._as_dict(row[6])
        return record

    async def save_indicators(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        data: Sequence[Mapping[str, Any]],
    ) -> int:
        """Async: upsert candles and merge their indicators."""
        if not data:
            return 0
        ex, table = self._resolve_names(exchange, symbol, tf)
        sql = self._upsert_full_sql(ex, table)
        param_rows = [self._build_param_row(row) for row in data]
        keys: set[str] = set()
        for row in data:
            _, doc = split_row(dict(row))
            keys.update(doc.keys())
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(self._ddl_schema(ex))
                await cur.execute(self._ddl_table(ex, table))
                await cur.execute(self._ddl_index(ex, table))
                await cur.executemany(sql, param_rows)
            await conn.commit()
        await self._touch_meta(ex, table, keys)
        return len(param_rows)

    async def update_indicator_only(
        self,
        exchange: str,
        symbol: str,
        tf: str,
        time: int,
        indicator_data: Mapping[str, Any],
    ) -> bool:
        """Async: merge indicator values into a single existing candle."""
        if not indicator_data:
            return False
        ex, table = self._resolve_names(exchange, symbol, tf)
        normalised = {
            k: self._normalise_indicator(v) for k, v in indicator_data.items()
        }
        from psycopg.types.json import Jsonb

        sql = (
            f'INSERT INTO "{ex}"."{table}" (time, indicators) VALUES (%s, %s) '
            f"ON CONFLICT (time) DO UPDATE SET "
            f'indicators = "{table}".indicators || EXCLUDED.indicators, '
            f"updated_at = NOW()"
        )
        async with self._pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(self._ddl_schema(ex))
                await cur.execute(self._ddl_table(ex, table))
                await cur.execute(self._ddl_index(ex, table))
                await cur.execute(sql, (time, Jsonb(normalised)))
                affected = cur.rowcount
            await conn.commit()
        await self._touch_meta(ex, table, set(normalised.keys()))
        return bool(affected)

    async def aclose(self) -> None:
        """Close the async connection pool."""
        if self._pool is not None:
            await self._pool.close()
            _LOG.info("AsyncTrexStore pool closed.")

    async def __aenter__(self) -> "AsyncTrexStore":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()


# ── Config / pool fallbacks ───────────────────────────────────────────────────


class _DsnConfig(DbConfig):
    """A :class:`DbConfig` backed by a raw DSN / conninfo string."""

    __slots__ = ("_dsn",)

    def __init__(self, dsn: str) -> None:  # noqa: D107 - thin wrapper
        super().__init__()
        object.__setattr__(self, "_dsn", dsn)

    def conninfo(self) -> str:  # type: ignore[override]
        return self._dsn


class _MiniPool:
    """A minimal thread-safe connection pool used when ``psycopg_pool`` is absent.

    Not a full-featured pool — it caps concurrent connections with a semaphore
    and recycles a small idle set. Adequate for tests and light usage; install
    ``psycopg[pool]`` for production.
    """

    def __init__(self, conninfo: str, max_size: int = 8) -> None:
        self._conninfo = conninfo
        self._sema = threading.BoundedSemaphore(max_size)
        self._idle: list[Any] = []
        self._lock = threading.Lock()
        self._closed = False

    @contextmanager
    def connection(self) -> "Iterator[Any]":
        import psycopg

        if self._closed:
            raise StoreConnectionError("Pool is closed.")
        self._sema.acquire()
        conn = None
        try:
            with self._lock:
                conn = self._idle.pop() if self._idle else None
            if conn is None or conn.closed:
                conn = psycopg.connect(self._conninfo, autocommit=False)
            yield conn
        finally:
            if conn is not None and not conn.closed:
                with self._lock:
                    if not self._closed:
                        self._idle.append(conn)
                    else:
                        conn.close()
            self._sema.release()

    def wait(self, timeout: float = 10.0) -> None:  # noqa: ARG002 - parity
        """No-op; connections are created lazily."""

    def close(self) -> None:
        self._closed = True
        with self._lock:
            for conn in self._idle:
                try:
                    conn.close()
                except Exception:  # pragma: no cover
                    pass
            self._idle.clear()
