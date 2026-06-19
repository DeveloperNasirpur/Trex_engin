<div align="center">

# 📊 trex.store

**PostgreSQL persistence layer for the Trex Engine**

*Durable OHLCV + indicator storage with one schema per exchange, one table per market, and JSONB-backed indicators.*

[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![psycopg](https://img.shields.io/badge/psycopg-v3-green)](https://www.psycopg.org/psycopg3/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-336791)](https://www.postgresql.org)

</div>

---

## 📖 Introduction & Purpose

`trex.store` is the durable storage tier for the **Trex Engine**. It complements
the in-memory `CandleStore`/`MultiSymbolStore` (great for live streaming, lost on
restart) with a PostgreSQL-backed store that survives restarts, supports
historical backfills, and lets indicators be queried with SQL.

The data model mirrors how traders think:

| Concept | Maps to | Example |
|---|---|---|
| **Exchange** | PostgreSQL **schema** | `binance`, `okx`, `kraken` |
| **Symbol + timeframe** | **Table** `{SYMBOL}{TF}` | `BTCUSDT1M`, `ETHUSDT5M` |
| **Bar** | **Row** (OHLCV + JSONB) | one candle |

Each candle row carries typed OHLCV columns plus a single `indicators JSONB`
document, so adding a new indicator never requires a schema migration.

```text
trex/store/
├── __init__.py      # exports TrexStore, AsyncTrexStore, DbConfig, exceptions
├── db_store.py      # TrexStore (sync) + AsyncTrexStore (async) + DbConfig + pool
├── exceptions.py    # TrexStoreError hierarchy
├── utils.py         # identifier validation, naming, row splitting
└── README.md        # this file
```

> ⚠️ **Table-name change vs. the previous version.** Tables are now
> `{SYMBOL}{TF}` — **upper-case, no underscore**: `BTCUSDT1M`, not `BTCUSDT_1M`.
> The package always double-quotes identifiers, so the upper-case spelling is the
> genuine physical name. If you have data under the old names, recreate or rename
> those tables before upgrading.

---

## 🛠 Installation

```bash
# Required: psycopg v3 + the pool extra (recommended for production & async)
pip install "psycopg[binary,pool]"
```

| Dependency | Why |
|---|---|
| `psycopg` (v3) | Database driver. **Required.** |
| `psycopg[pool]` | Connection pooling (`ConnectionPool` / `AsyncConnectionPool`). Strongly recommended; required for `AsyncTrexStore`. |

Without `psycopg_pool`, the synchronous store falls back to a minimal built-in
pool (fine for tests and light use). The async store **requires** the pool extra.

Then drop the `trex/store/` package into your `trex` source tree
(`src/trex/store/`).

---

## 🚀 Quick Start

```python
from trex.store import TrexStore

# Connect (DSN string, mapping, or DbConfig — all accepted)
store = TrexStore("postgresql://postgres:pw@localhost:5432/trex")

# Write candles + indicators in one call (scalar or multi-field indicators)
store.save_indicators("binance", "BTCUSDT", "1m", [
    {
        "time": 1720000000,
        "open": 42000, "high": 42100, "low": 41950, "close": 42080, "volume": 12.5,
        "RSI_14": 65.4,                                       # scalar
        "MACD_12_26_9": {"macd": 125.3, "signal": 118.7, "histogram": 6.6},
        "BB_20_2": {"upper": 42500.0, "middle": 42100.0, "lower": 41700.0},
    },
])

# Read one indicator series (ascending by time)
rsi = store.get_indicator("binance", "BTCUSDT", "1m", "RSI_14")
# -> [{"time": 1720000000, "RSI_14": 65.4}, ...]

# Read candles enriched with chosen indicators (most recent 500)
bars = store.get_candles_with_indicators(
    "binance", "BTCUSDT", "1m", ["RSI_14", "MACD_12_26_9"], limit=500
)

# Quick health checks
count = store.get_candle_count("binance", "BTCUSDT", "1m")
stats = store.get_indicator_stats("binance", "BTCUSDT", "1m", "RSI_14")
ok, _ = store.is_indicator_complete("binance", "BTCUSDT", "1m", "RSI_14")

store.close()
```

Indicator documents are stored keyed by name:

```json
{
  "RSI_14":       {"value": 68.45},
  "MACD_12_26_9": {"macd": 125.3, "signal": 118.7, "histogram": 6.6},
  "BB_20_2":      {"upper": 42500.0, "middle": 42100.0, "lower": 41700.0}
}
```

Scalar values you pass (`"RSI_14": 65.4`) are normalised to `{"value": 65.4}` on
write, so reads always have one consistent shape.

---

## 📚 API Reference

### `TrexStore` (synchronous)

| Method | Description |
|---|---|
| `get_exchanges()` | List all exchanges (schemas). |
| `get_tables(exchange)` | `{table: [indicator, …]}` for an exchange. |
| `table_exists(exchange, symbol, tf)` | Whether a `{SYMBOL}{TF}` table exists. |
| `list_all_indicators(exchange=None)` | **New.** All distinct indicator names, globally or per exchange. |
| `get_candle_count(exchange, symbol, tf)` | **New.** Total candle rows in a table. |
| `get_indicator_stats(exchange, symbol, tf, name)` | **New.** `min / max / avg / count / last_value / last_time` for a scalar indicator. |
| `get_indicator(exchange, symbol, tf, name, start_ts=None, end_ts=None)` | One indicator's series, ascending. |
| `get_candles_with_indicators(exchange, symbol, tf, indicators, start_ts=None, end_ts=None, limit=None)` | Candles + chosen indicators. |
| `get_latest_bar(exchange, symbol, tf)` | Newest candle + its full indicator document, or `None`. |
| `is_indicator_complete(exchange, symbol, tf, name, last_n=500)` | `(complete, last_n_records)` — gap check on the recent tail. |
| `save_indicators(exchange, symbol, tf, data)` | Upsert candles and **merge** indicators (non-destructive). |
| `update_indicator_only(exchange, symbol, tf, time, indicator_data)` | **New.** Merge indicators into one candle without touching OHLCV. |
| `bulk_save_candles(exchange, symbol, tf, bars)` | Upsert candles only (from `Bar` objects). |
| `migrate_from_memory_store(memory_store, exchange, symbol, tf)` | **New.** Move candles + cached indicators from a `CandleStore` into PostgreSQL. |
| `delete_old_data(exchange=None, symbol=None, tf=None, older_than_days=90)` | Prune old candles across one or many tables. |
| `refresh()` | Force a full metadata re-scan. |
| `close()` | Close the pool. Also a context manager (`with TrexStore(...) as s:`). |

### `AsyncTrexStore` (asyncio)

Construct with `await AsyncTrexStore.create(...)`; close with `await store.aclose()`
(or `async with`). Coroutine versions of: `get_exchanges`, `get_tables`,
`table_exists`, `list_all_indicators`, `get_candle_count`, `get_indicator`,
`get_candles_with_indicators`, `get_latest_bar`, `save_indicators`,
`update_indicator_only`, `refresh`.

### Exceptions

All derive from **`TrexStoreError`**: `StoreConnectionError`, `SchemaError`,
`TableNotFoundError`, `IndicatorError`, `ValidationError`, `MigrationError`.

---

## ⚙️ Configuration

Three interchangeable ways to configure a connection:

```python
from trex.store import TrexStore, DbConfig

# 1) DSN / libpq conninfo string
TrexStore("postgresql://user:pw@localhost:5432/trex")
TrexStore("host=localhost port=5432 user=postgres dbname=trex")

# 2) DbConfig dataclass
TrexStore(DbConfig(host="db.internal", port=5432, user="trex",
                   password="secret", dbname="trex"))

# 3) Plain mapping (accepts 'database' or 'dbname'; compatible with
#    trex.source.config.ConfigPostgres.to_dict())
TrexStore({"host": "localhost", "port": 5432, "user": "postgres",
           "password": "", "dbname": "trex"})
```

Pooling and scan behaviour:

```python
TrexStore(
    config,
    min_size=1,          # minimum pooled connections
    max_size=8,          # maximum pooled connections
    scan_on_init=True,   # warm the metadata cache at construction
)
```

**Logging** uses the standard library under the `trex.store` logger:

```python
import logging
logging.getLogger("trex.store").setLevel(logging.INFO)
```

---

## 💡 Examples

**1 — Incremental indicator updates (compute then attach):**

```python
# Candles already persisted; attach RSI for one bar as it closes
store.update_indicator_only("binance", "BTCUSDT", "1m",
                            time=1720000000, indicator_data={"RSI_14": 71.2})
```

**2 — Indicator statistics dashboard:**

```python
s = store.get_indicator_stats("binance", "BTCUSDT", "1m", "RSI_14")
print(f"RSI  min={s['min']}  max={s['max']}  avg={s['avg']:.1f}  "
      f"now={s['last_value']}  over {s['count']} bars")
```

**3 — Migrate a live in-memory store to disk on shutdown:**

```python
from trex.server.store import MultiSymbolStore

multi = MultiSymbolStore()
# ... streaming fills multi during the session ...

cs = multi.get_store("BTCUSDT", "1m")
store.migrate_from_memory_store(cs, "binance", "BTCUSDT", "1m")
```

**4 — Discover what's stored:**

```python
for ex in store.get_exchanges():
    for table, inds in store.get_tables(ex).items():
        print(ex, table, inds)
print("All indicators:", store.list_all_indicators())
```

**5 — Async pipeline:**

```python
import asyncio
from trex.store import AsyncTrexStore

async def main():
    store = await AsyncTrexStore.create("postgresql://postgres:pw@localhost/trex")
    await store.save_indicators("binance", "BTCUSDT", "1m", rows)
    rsi = await store.get_indicator("binance", "BTCUSDT", "1m", "RSI_14")
    await store.aclose()

asyncio.run(main())
```

---

## 🧠 Design Decisions

- **One schema per exchange, one table per market.** Keeps query plans small,
  lets you `DROP SCHEMA` an exchange cleanly, and avoids a giant single table.
- **`{SYMBOL}{TF}` upper-case, double-quoted everywhere.** PostgreSQL folds
  *unquoted* identifiers to lower-case; by always quoting, `BTCUSDT1M` is the
  real physical name. Components must be alphanumeric (no underscore) so the
  symbol/timeframe split is never ambiguous.
- **Indicators as a single JSONB column.** New indicators require no DDL; a GIN
  index keeps key-existence (`indicators ? 'RSI_14'`) and lookups fast.
- **Non-destructive merges.** Writes use
  `ON CONFLICT (time) DO UPDATE … indicators = indicators || EXCLUDED.indicators`,
  so a partial update (e.g. one new indicator) never drops existing keys. OHLCV
  columns are overwritten; `update_indicator_only` leaves OHLCV untouched.
- **Scalar normalisation.** Bare numbers become `{"value": x}` on write so
  reads — and `get_indicator_stats` over `indicators -> name -> 'value'` — have a
  uniform shape. Multi-field indicators (MACD, BB) are stored as-is.
- **SQL-injection safe by construction.** Schema/table/component names are
  validated against a strict allow-list *before* interpolation; every value is a
  bound parameter. `NaN`/`Infinity` are coerced to `null` (invalid in JSONB).
- **Thread-safety & caching.** A pooled connection set plus an `RLock`-guarded
  metadata cache; user code never runs while a lock is held. The cache is scanned
  once and updated incrementally after writes.
- **Sync and async share one SQL core** (`_SqlMixin`) so both backends emit
  identical SQL and can't drift.

---

## ⚡ Performance Notes

- **Batch your writes.** `save_indicators` / `bulk_save_candles` use
  `executemany`; passing 500 rows in one call is far faster than 500 calls.
- **`limit=` reads the tail efficiently.** `get_candles_with_indicators(..., limit=N)`
  orders `DESC … LIMIT N` (using the PK index) then reverses in Python — it does
  not scan the whole table.
- **Indexes.** The `time` PRIMARY KEY covers range/order queries; a per-table GIN
  index on `indicators` accelerates key-existence and containment.
- **Metadata is cached.** `get_exchanges` / `get_tables` / `table_exists` /
  `list_all_indicators` answer from memory after the first scan. Call `refresh()`
  if another process changed the structure.
- **Pool sizing.** Set `max_size` to your expected concurrency. The async store
  scales better under many concurrent I/O-bound queries.
- **Pruning.** `delete_old_data` issues one `DELETE` per table; run it off-peak
  for large tables and `VACUUM` afterwards if you delete heavily.

---

## 🔭 Future Improvements

- **TimescaleDB hypertables** for automatic time-partitioning and compression of
  long histories.
- **`COPY`-based bulk loading** for very large backfills (millions of bars).
- **Schema migrations via Alembic** for evolving the candle table shape.
- **Typed indicator read models** (Pydantic) for MACD/BB so callers get
  structured objects instead of dicts.
- **`get_indicator_stats` for multi-field indicators** (per-sub-field aggregates).
- **Retry / circuit-breaker** (`tenacity`) around transient connection errors.
- **OpenTelemetry spans** on every query for production observability.
- **Full async parity** (async `get_indicator_stats`, `migrate_from_memory_store`,
  `delete_old_data`).

---

<div align="center">
<sub>Built for the Trex Engine · psycopg v3 · PostgreSQL</sub>
</div>
