# Trex Engine

**Production-grade Python SDK for building real-time trading data servers compatible with [TrexTerminal](https://github.com/DeveloperNasirpur/TrexTerminal).**

Trex Engine turns any price feed into a fully-featured trading terminal backend: 110+ streaming indicators, real-time OHLCV aggregation, PostgreSQL persistence, and a WebSocket server — all with zero mandatory runtime dependencies.

---

## Ecosystem

```
┌─────────────────┐      WebSocket      ┌─────────────────────┐
│  Trex Engine    │ ──── Protocol 2.0 ─▶│   TrexTerminal      │
│  (this package) │                     │   (browser chart)   │
│                 │ ◀─── drawings ──── │                     │
└────────┬────────┘                     └─────────────────────┘
         │
         │  PostgreSQL (OHLCV + indicators)
         ▼
┌─────────────────┐
│    BackTest     │  load_postgres() ──▶ Backtest(Strategy).run(candles)
│  (backtesting)  │
└─────────────────┘
```

| Package | Role |
|---------|------|
| **Trex Engine** (this) | Live data server — indicators, storage, WebSocket |
| [TrexTerminal](https://github.com/DeveloperNasirpur/TrexTerminal) | Browser chart client |
| [BackTest](https://github.com/DeveloperNasirpur/BackTest) | Strategy backtesting with live chart streaming |

---

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)
- [Indicators Reference](#indicators-reference)
- [API Reference](#api-reference)
- [Database Persistence](#database-persistence)
- [Loading Candles for Backtesting](#loading-candles-for-backtesting)
- [State Persistence (Fast Restart)](#state-persistence-fast-restart)
- [WebSocket Protocol](#websocket-protocol)
- [Multi-Symbol & Multi-Timeframe](#multi-symbol--multi-timeframe)
- [Architecture Overview](#architecture-overview)
- [Compatibility with TrexTerminal](#compatibility-with-trexterminal)
- [Writing a Custom Indicator](#writing-a-custom-indicator)

---

## Features

| Feature | Details |
|---------|---------|
| **110+ Indicators** | Trend, Momentum, Oscillators, Volume, Volatility, Statistics, 35 Candlestick Patterns |
| **Zero runtime deps** | Core engine uses only stdlib; PostgreSQL is optional |
| **O(1) hot path** | Every indicator uses incremental updates — no loop per tick |
| **Fast restart** | Indicator internal state saved to DB; skip warm-up replay on restart |
| **WebSocket server** | Protocol 2.0.0 — fully compatible with TrexTerminal client |
| **Multi-timeframe** | CTF auto-aggregates 1m bars → 5m/15m/1h/4h/1d in parallel |
| **Auto-deduplication** | Same `(indicator, symbol, tf, params)` is created only once |
| **Python 3.12+** | Uses modern type syntax throughout |

---

## Installation

```bash
# Core (no dependencies)
pip install trex-engine

# With PostgreSQL support
pip install "trex-engine[postgres]"
```

**Requirements:** Python 3.12+

---

## Quick Start

### Minimal (in-memory, no DB)

```python
import trex

# 1. Initialize the engine
trex.init(
    timezone="UTC",           # Your exchange timezone
    source_timeframe="1m",    # Lowest timeframe you will push
    port=8765,                # WebSocket port for TrexTerminal
)

# 2. Register indicators
trex.ema("BTCUSDT", "1m", period=20, visible=True)
trex.rsi("BTCUSDT", "1m", period=14, visible=True)
trex.bbands("BTCUSDT", "1h", period=20, visible=True)

# 3. Feed bars as they arrive from your exchange
while True:
    raw_bar = exchange.next_bar()          # your exchange adapter
    trex.push(raw_bar, symbol="BTCUSDT")  # engine handles everything
```

### Production (PostgreSQL + fast restart)

```python
import trex
from trex.store.db_store import DbConfig

db = DbConfig(
    host="localhost",
    port=5432,
    dbname="trex",
    user="trex",
    password="secret",
)

trex.init(
    timezone="UTC",
    source_timeframe="1m",
    port=8765,
    db_config=db,
    exchange="binance",       # schema namespace in PostgreSQL
)

# Register indicators
trex.ema("BTCUSDT", "1m", period=20, visible=True)
trex.rsi("BTCUSDT", "1m", period=14, visible=True)
trex.supertrend("BTCUSDT", "4h", period=10, multiplier=3.0, visible=True)

# Load history + restore indicator state (skips warm-up on restart)
trex.seed("BTCUSDT")

# Live loop — every bar is saved to DB and broadcast to terminal
while True:
    raw_bar = exchange.next_bar()
    trex.push(raw_bar, symbol="BTCUSDT")
```

### With Listener Callbacks

```python
def on_rsi(value: float):
    if value < 30:
        print("Oversold!")
    elif value > 70:
        print("Overbought!")

trex.rsi("BTCUSDT", "1h", period=14, listener=on_rsi, visible=True)
```

---

## Core Concepts

### OHLCV Object

All bars pushed to the engine must be `OHLCV` instances:

```python
from trex.base.ohlcv import OHLCV
from datetime import datetime, timezone

bar = OHLCV(
    open=67450.0,
    high=67600.0,
    low=67380.0,
    close=67520.0,
    volume=320.8,
    time=datetime(2024, 5, 27, 10, 0, tzinfo=timezone.utc),
    symbol="BTCUSDT",
    timeframe=1,       # minutes
    str_time="1m",
)
```

**Factories:**

```python
from trex.base.ohlcv import OHLCVFactory

# From a list/tuple: [open, high, low, close, volume, timestamp_ms]
bar = OHLCVFactory.from_matrix(row, symbol="BTCUSDT", timeframe=1)

# From dict: {'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ..., 'time': ...}
bar = OHLCVFactory.from_dict(d, symbol="BTCUSDT", timeframe=1)
```

**Value Extractors** (used by price-based indicators):

```python
from trex.base.ohlcv import ValueExtractor

ValueExtractor.extract_close    # default for most indicators
ValueExtractor.extract_open
ValueExtractor.extract_high
ValueExtractor.extract_low
ValueExtractor.extract_hl2      # (high + low) / 2
ValueExtractor.extract_hlc3     # (high + low + close) / 3
ValueExtractor.extract_hlcc4    # (high + low + close + close) / 4
```

### Timeframes

```python
from trex.base.timeframe import Timeframe

Timeframe.m1    # "1m"
Timeframe.m5    # "5m"
Timeframe.m15   # "15m"
Timeframe.m30   # "30m"
Timeframe.h1    # "1h"
Timeframe.h4    # "4h"
Timeframe.d1    # "1d"
```

The engine auto-aggregates 1m bars into all higher timeframes via CTF (Candlestick TimeFrame converter). You only need to push 1m bars.

### Indicator Pipeline

Each indicator goes through three internal phases:

| Phase | Trigger | Description |
|-------|---------|-------------|
| **Warmup** | `seed()` | Pre-seeded history fed silently |
| **Boot** | First live bars | `_first_calculate()` accumulates until ready |
| **Run** | Steady-state | `_calculate_new_value()` emits on every bar — O(1), no branch |

---

## Indicators Reference

### Trend / Moving Averages (23)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.sma(sym, tf, period=20)` | Simple MA | `period` |
| `trex.ema(sym, tf, period=20)` | Exponential MA | `period` |
| `trex.wma(sym, tf, period=20)` | Weighted MA | `period` |
| `trex.hma(sym, tf, period=20)` | Hull MA | `period` |
| `trex.dema(sym, tf, period=20)` | Double EMA | `period` |
| `trex.tema(sym, tf, period=20)` | Triple EMA | `period` |
| `trex.zlema(sym, tf, period=20)` | Zero-Lag EMA | `period` |
| `trex.vwma(sym, tf, period=20)` | Volume-Weighted MA | `period` |
| `trex.kama(sym, tf, er_period=10, fast=2, slow=30)` | Kaufman Adaptive MA | `er_period` |
| `trex.rma(sym, tf, period=14)` | Wilder's Smoothed MA (RMA) | `period` |
| `trex.t3(sym, tf, period=5, volume_factor=0.7)` | T3 (6 cascaded EMAs) | `period` |
| `trex.trima(sym, tf, period=20)` | Triangular MA | `period` |
| `trex.vidya(sym, tf, period=14, cmo_period=9)` | CMO-Adaptive MA (VIDYA) | `period` |
| `trex.alma(sym, tf, period=9, offset=0.85, sigma=6)` | Arnaud Legoux MA | `period` |
| `trex.mcginley(sym, tf, period=14)` | McGinley Dynamic | `period` |
| `trex.lsma(sym, tf, period=25)` | Least Squares MA | `period` |
| `trex.fwma(sym, tf, period=20)` | Fibonacci-Weighted MA | `period` |
| `trex.pwma(sym, tf, period=20)` | Pascal's Triangle MA | `period` |
| `trex.swma(sym, tf, period=10)` | Symmetric-Weighted MA | `period` |
| `trex.sinwma(sym, tf, period=14)` | Sine-Weighted MA | `period` |
| `trex.ssma(sym, tf, period=20)` | Ehlers Super Smoother | `period` |
| `trex.hwma(sym, tf, alpha=0.2, beta=0.1)` | Holt-Winters MA | `alpha`, `beta` |
| `trex.jma(sym, tf, period=7, phase=0, power=2)` | Jurik MA | `period`, `phase` |

All MA indicators accept `value_extractor=` to change the source price (default: close).

### Volatility (9)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.atr(sym, tf, period=14)` | Average True Range | `period` |
| `trex.natr(sym, tf, period=14)` | Normalized ATR (%) | `period` |
| `trex.stddev(sym, tf, period=20)` | Standard Deviation | `period` |
| `trex.bbands(sym, tf, period=20, std_dev=2.0)` | Bollinger Bands | `period`, `std_dev` |
| `trex.keltner(sym, tf, period=20, atr_period=14, mult=2.0)` | Keltner Channel | `period` |
| `trex.donchian(sym, tf, period=20)` | Donchian Channel | `period` |
| `trex.chandelier(sym, tf, period=22, multiplier=3.0)` | Chandelier Exit | `period` |
| `trex.hv(sym, tf, period=20)` | Historical Volatility | `period` |
| `trex.ui(sym, tf, period=14)` | Ulcer Index | `period` |

### Momentum (15)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.rsi(sym, tf, period=14)` | RSI | `period` |
| `trex.macd(sym, tf, fast=12, slow=26, signal=9)` | MACD | `fast`, `slow`, `signal` |
| `trex.adx(sym, tf, period=14)` | ADX / DI+/DI− | `period` |
| `trex.aroon(sym, tf, period=25)` | Aroon Up/Down | `period` |
| `trex.trix(sym, tf, period=18)` | TRIX | `period` |
| `trex.ao(sym, tf)` | Awesome Oscillator | — |
| `trex.ac(sym, tf)` | Accelerator Oscillator | — |
| `trex.tsi(sym, tf, r_period=25, s_period=13)` | True Strength Index | `r_period`, `s_period` |
| `trex.dpo(sym, tf, period=20)` | Detrended Price Oscillator | `period` |
| `trex.kst(sym, tf, r1=10, r2=13, r3=14, r4=15, s1=10, s2=13, s3=14, s4=15, signal=9)` | Know Sure Thing | `r1-r4`, `s1-s4` |
| `trex.coppock(sym, tf, r1=14, r2=11, wma_period=10)` | Coppock Curve | `r1`, `r2` |
| `trex.rvi(sym, tf, period=10)` | Relative Vigor Index | `period` |
| `trex.fisher(sym, tf, period=9)` | Fisher Transform | `period` |
| `trex.vortex(sym, tf, period=14)` | Vortex VI+/VI− | `period` |

### Oscillators (14)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.stochastic(sym, tf, k=14, d=3, smooth=3)` | Stochastic %K/%D | `k`, `d`, `smooth` |
| `trex.cci(sym, tf, period=20)` | Commodity Channel Index | `period` |
| `trex.williams_r(sym, tf, period=14)` | Williams %R | `period` |
| `trex.roc(sym, tf, period=12)` | Rate of Change | `period` |
| `trex.momentum(sym, tf, period=10)` | Momentum | `period` |
| `trex.mfi(sym, tf, period=14)` | Money Flow Index | `period` |
| `trex.obv(sym, tf)` | On-Balance Volume | — |
| `trex.cmo(sym, tf, period=14)` | Chande Momentum Oscillator | `period` |
| `trex.ppo(sym, tf, fast=12, slow=26, signal=9)` | Percentage Price Oscillator | `fast`, `slow` |
| `trex.apo(sym, tf, fast=12, slow=26)` | Absolute Price Oscillator | `fast`, `slow` |
| `trex.stochrsi(sym, tf, rsi_period=14, stoch_period=14, k=3, d=3)` | Stochastic RSI | `rsi_period` |
| `trex.uo(sym, tf, period1=7, period2=14, period3=28)` | Ultimate Oscillator | `period1-3` |
| `trex.chop(sym, tf, period=14)` | Choppiness Index | `period` |
| `trex.force_index(sym, tf, period=13)` | Force Index | `period` |

### Volume (9)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.ad(sym, tf)` | Accumulation/Distribution | — |
| `trex.adosc(sym, tf, fast=3, slow=10)` | A/D Oscillator | `fast`, `slow` |
| `trex.cmf(sym, tf, period=20)` | Chaikin Money Flow | `period` |
| `trex.eom(sym, tf, period=14)` | Ease of Movement | `period` |
| `trex.nvi(sym, tf)` | Negative Volume Index | — |
| `trex.pvi(sym, tf)` | Positive Volume Index | — |
| `trex.pvt(sym, tf)` | Price-Volume Trend | — |
| `trex.vo(sym, tf, fast=5, slow=10)` | Volume Oscillator | `fast`, `slow` |
| `trex.vroc(sym, tf, period=14)` | Volume Rate of Change | `period` |

### Statistics (5)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.zscore(sym, tf, period=20)` | Z-Score | `period` |
| `trex.variance(sym, tf, period=20)` | Variance | `period` |
| `trex.linreg_slope(sym, tf, period=14)` | Linear Regression Slope | `period` |
| `trex.correl(sym, tf, period=20)` | Close/Volume Correlation | `period` |
| `trex.percentrank(sym, tf, period=20)` | Percent Rank | `period` |

### Hybrid / Compound (4)

| Function | Full Name | Key Param(s) |
|----------|-----------|--------------|
| `trex.vwap(sym, tf)` | VWAP (daily reset) | — |
| `trex.supertrend(sym, tf, period=10, multiplier=3.0)` | Supertrend | `period`, `multiplier` |
| `trex.ichimoku(sym, tf)` | Ichimoku Cloud | `tenkan`, `kijun`, `senkou_b` |
| `trex.psar(sym, tf)` | Parabolic SAR | `step`, `max_step` |

### Candlestick Patterns (35)

All pattern indicators emit: `+1` (bullish signal), `-1` (bearish signal), `0` (no pattern).

**Single-candle (15):**

| Function | Pattern |
|----------|---------|
| `trex.doji(sym, tf, threshold=0.1)` | Doji |
| `trex.dragonfly_doji(sym, tf)` | Dragon Fly Doji |
| `trex.gravestone_doji(sym, tf)` | Gravestone Doji |
| `trex.hammer(sym, tf)` | Hammer |
| `trex.inverted_hammer(sym, tf)` | Inverted Hammer |
| `trex.hanging_man(sym, tf)` | Hanging Man |
| `trex.shooting_star(sym, tf)` | Shooting Star |
| `trex.marubozu(sym, tf)` | Marubozu |
| `trex.spinning_top(sym, tf)` | Spinning Top |
| `trex.long_legged_doji(sym, tf)` | Long-Legged Doji |
| `trex.bullish_belt(sym, tf)` | Bullish Belt Hold |
| `trex.bearish_belt(sym, tf)` | Bearish Belt Hold |
| `trex.high_wave(sym, tf)` | High Wave |
| `trex.rickshaw_man(sym, tf)` | Rickshaw Man |
| `trex.umbrella_line(sym, tf)` | Umbrella Line |

**Two-candle (10):**

| Function | Pattern |
|----------|---------|
| `trex.bullish_engulfing(sym, tf)` | Bullish Engulfing |
| `trex.bearish_engulfing(sym, tf)` | Bearish Engulfing |
| `trex.bullish_harami(sym, tf)` | Bullish Harami |
| `trex.bearish_harami(sym, tf)` | Bearish Harami |
| `trex.piercing(sym, tf)` | Piercing Line |
| `trex.dark_cloud_cover(sym, tf)` | Dark Cloud Cover |
| `trex.tweezer(sym, tf)` | Tweezer Top/Bottom |
| `trex.kicking(sym, tf)` | Kicking |
| `trex.on_neck(sym, tf)` | On Neck |
| `trex.matching_low(sym, tf)` | Matching Low |

**Three-candle (10):**

| Function | Pattern |
|----------|---------|
| `trex.morning_star(sym, tf)` | Morning Star |
| `trex.evening_star(sym, tf)` | Evening Star |
| `trex.morning_doji_star(sym, tf)` | Morning Doji Star |
| `trex.evening_doji_star(sym, tf)` | Evening Doji Star |
| `trex.three_white_soldiers(sym, tf)` | Three White Soldiers |
| `trex.three_black_crows(sym, tf)` | Three Black Crows |
| `trex.three_inside_up(sym, tf)` | Three Inside Up |
| `trex.three_inside_down(sym, tf)` | Three Inside Down |
| `trex.deliberation(sym, tf)` | Deliberation |
| `trex.identical_three_crows(sym, tf)` | Identical Three Crows |

```python
# Example: alert on pattern detection
trex.bullish_engulfing("BTCUSDT", "1h", listener=lambda sig: print("Engulfing!", sig) if sig else None)
trex.morning_star("ETHUSDT", "4h", visible=True)
```

---

## API Reference

### `trex.init()`

```python
trex.init(
    timezone: str = "UTC",
    source_timeframe: str = "1m",
    port: int = 8765,
    host: str = "0.0.0.0",
    max_bars: int = 5000,
    snapshot_size: int = 500,
    db_config: DbConfig | None = None,
    exchange: str = "default",
)
```

Must be called once before any other `trex.*` call. Starts the WebSocket server in a background thread.

### `trex.push()`

```python
trex.push(bar: OHLCV, symbol: str) -> None
```

Feed one closed 1m bar. The engine will:
1. Save bar to PostgreSQL (if `db_config` provided)
2. Aggregate to higher timeframes via CTF
3. Run all registered indicators for the symbol
4. Broadcast `bar` + `indicators` messages to all connected WebSocket clients

### `trex.seed()`

```python
trex.seed(symbol: str) -> None
```

Load historical bars from DB and calculate all indicators. On restart, if all indicator states were previously saved, only new bars are recalculated — skipping warmup entirely.

### `trex.stop()`

```python
trex.stop() -> None
```

Gracefully shut down the WebSocket server and close DB connections.

### `trex.client_count()`

```python
trex.client_count() -> int
```

Number of currently connected WebSocket clients.

### `trex.indicators()`

```python
trex.indicators(symbol: str) -> str
```

Returns a tree-formatted string of all registered indicators for a symbol (useful for debugging).

### `trex.de_attach()`

```python
trex.de_attach(indicator: Indicator, key: str) -> None
trex.de_attach_by_key(keys: ListenerKey | list[ListenerKey]) -> bool
```

Remove indicators at runtime.

---

## Database Persistence

### Configuration

```python
from trex.store.db_store import DbConfig

db = DbConfig(
    host="localhost",
    port=5432,
    dbname="trex_data",
    user="trex",
    password="secret",
)
```

### What gets stored

| Data | Table | Format |
|------|-------|--------|
| OHLCV bars | `{exchange}.{SYMBOL}_{tf}` | One row per bar |
| Indicator values | Same table, `indicators` column | `JSONB` — one key per indicator |
| Indicator state | `{exchange}.{SYMBOL}_{tf}_ind_states` | `JSONB` snapshot of internal state |

Tables are created automatically on first use.

### Using `TrexStore` directly

```python
from trex.store.db_store import TrexStore, DbConfig

store = TrexStore(DbConfig(...))

# Read
bars = store.fetch_bars("BTCUSDT", "1h", limit=500)
bar  = store.get_latest_bar("BTCUSDT", "1h")

# Write
store.bulk_save_candles("BTCUSDT", "1h", bars_list)
store.save_indicators("BTCUSDT", "1h", {time_ms: {"ema_20": 67400.0}})
```

### Async version

```python
from trex.store.db_store import AsyncTrexStore

async_store = AsyncTrexStore(DbConfig(...))
bars = await async_store.fetch_bars("BTCUSDT", "1h", limit=500)
```

---

## State Persistence (Fast Restart)

Every indicator saves its full internal state to DB after each `seed()`. On the next restart:

```
Cold start:     load ALL history → warm up all indicators   (slow, seconds–minutes)
Fast restart:   load state → feed only new bars             (fast, milliseconds)
```

**No extra code required** — `seed()` handles this automatically.

Fast restart activates when **all** indicators for a `(symbol, timeframe)` pair have a saved state. Otherwise it falls back to full replay.

**What each indicator saves:**

| Indicator | Saved State |
|-----------|-------------|
| SMA | `_win`, `_total` |
| EMA | `prev_output` |
| WMA | `_win`, `_wsum`, `_psum` |
| KAMA | `_win`, `_diffs`, `_vol`, `_kama` |
| RSI | `avg_gain`, `avg_loss` |
| ADX | all smoothed accumulators, `_dx_buf`, phase |
| MACD | fast/slow/signal EMA values |
| Stochastic | windows, `_cur_k` |
| + all others | their respective rolling state |

---

## WebSocket Protocol

Trex Engine implements **Protocol 2.0.0** — the same version TrexTerminal expects.

### Message Flow

```
CLIENT                                SERVER
  │                                     │
  ├─ WebSocket connect ───────────────>│
  │<─ (accepted) ──────────────────────┤
  │                                     │
  ├─ { "type": "hello",               │
  │    "protocol": "2.0.0" } ─────────>│
  │<─ { "type": "snapshot",           │
  │     "symbol": "BTCUSDT",          │
  │     "timeframe": "1m",            │
  │     "data": [...],                │  ← last N OHLCV bars
  │     "definitions": [...],         │  ← series shapes
  │     "points": {...} } ────────────┤  ← historical indicator values
  │                                     │
  │  ── live loop ─────────────────── │
  │                                     │
  ├─ { "type": "ping" } ──────────────>│
  │<─ { "type": "pong", "t": ... } ───┤
  │                                     │
  │<─ { "type": "bar",                │
  │     "bar": { "time": ...,         │
  │              "open": ...,         │
  │              "high": ...,         │
  │              "low": ...,          │
  │              "close": ...,        │
  │              "volume": ... } } ───┤  ← each tick
  │                                     │
  │<─ { "type": "indicators",         │
  │     "points": {                   │
  │       "ema_20": [{"time":...,"value":...}],
  │       "rsi":    [{"time":...,"value":...}]
  │     } } ──────────────────────────┤  ← after bar close
  │                                     │
  ├─ { "type": "history",             │
  │    "before": 1716000000,          │
  │    "count": 500 } ────────────────>│
  │<─ { "type": "history",            │
  │     "data": [...],                │
  │     "noMoreHistory": false } ─────┤
  │                                     │
  ├─ { "type": "symbol",              │
  │    "symbol": "ETHUSDT" } ─────────>│
  │<─ { "type": "snapshot", ... } ────┤  ← fresh snapshot for ETHUSDT
```

### Server-Sent Message Types

| Type | When | Key Fields |
|------|------|------------|
| `snapshot` | Connect, symbol/tf change | `data`, `definitions`, `points`, `symbol`, `timeframe` |
| `bar` | Every tick | `bar` (OHLCV object) |
| `indicators` | After bar close | `points` (key → `[{time, value}]`) |
| `history` | Reply to history request | `data`, `noMoreHistory` |
| `pong` | Reply to ping | `t` (echoed timestamp) |
| `toast` | Server notifications | `message`, `toastType` |

### SeriesDefinition (indicator shape)

Each visible indicator produces one or more `SeriesDefinition` entries in the snapshot:

```json
{
  "key": "ema_20",
  "label": "EMA 20",
  "type": "line",
  "pane": "main",
  "color": "#2962FF",
  "lineWidth": 2,
  "lineStyle": 0
}
```

Valid `type` values: `"line"`, `"histogram"`, `"area"`, `"baseline"`, `"scatter"`  
Valid `pane` values: `"main"` (overlaid on price), `"sub"` (separate pane below)

---

## Multi-Symbol & Multi-Timeframe

### Multiple symbols

```python
trex.init(timezone="UTC", source_timeframe="1m", port=8765, db_config=db)

for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
    trex.ema(symbol, "1h", period=20, visible=True)
    trex.rsi(symbol, "1h", period=14, visible=True)
    trex.seed(symbol)

while True:
    bar = exchange.next_bar()
    trex.push(bar, symbol=bar.symbol)
```

### Auto-aggregation (CTF)

Push 1m bars only — the engine creates 5m, 15m, 1h, 4h, 1d bars automatically:

```python
trex.init(source_timeframe="1m", ...)

# All these run from a single 1m push stream
trex.rsi("BTCUSDT", "1m",  period=14, visible=True)
trex.rsi("BTCUSDT", "15m", period=14, visible=True)
trex.rsi("BTCUSDT", "1h",  period=14, visible=True)
trex.rsi("BTCUSDT", "4h",  period=14, visible=True)

while True:
    bar_1m = exchange.next_1m_bar()
    trex.push(bar_1m, symbol="BTCUSDT")   # auto-aggregates upward
```

### Indicator deduplication

Registering the same indicator twice returns the same instance (no duplicate computation):

```python
k1 = trex.ema("BTCUSDT", "1h", period=20)
k2 = trex.ema("BTCUSDT", "1h", period=20)   # same object, zero extra cost
```

---

## Architecture Overview

```
                        ┌──────────────────────────────────────────┐
  Exchange / Feed ──────> trex.push(bar, symbol)                   │
                        │                                           │
                        │  AutoEngine                               │
                        │  ├── TrexStore (PostgreSQL)              │
                        │  │    ├── save bar                       │
                        │  │    └── save indicator values + state  │
                        │  ├── MultiSymbolStore (ring buffer)       │
                        │  ├── CTF Aggregator                       │
                        │  │    └── 1m → 5m/15m/1h/4h/1d          │
                        │  └── ContextIndicator                     │
                        │       ├── SMA  ──> listener + broadcast  │
                        │       ├── EMA  ──> listener + broadcast  │
                        │       └── RSI  ──> listener + broadcast  │
                        │                                           │
  WebSocket clients <────── SyncServer (Protocol 2.0.0)           │
  (TrexTerminal)        │    ├── snapshot on connect               │
                        │    ├── bar + indicators live             │
                        │    └── history on scroll                 │
                        └──────────────────────────────────────────┘
```

### Indicator Pipeline Internals

```
add_input_value(bar)
       │
       ▼
[value_extractor] → float  (e.g. close price)
       │
       ▼
[boot phase]  _first_calculate()    → None until window is full
       │
       ▼  (automatic transition)
[run phase]   _calculate_new_value() → float  (O(1), no branch)
       │
       ▼
listeners[] + WebSocket broadcast
```

---

## Compatibility with TrexTerminal

### Protocol Support Matrix

| Feature | Status | Notes |
|---------|--------|-------|
| Protocol version 2.0.0 | ✅ Full | Exact match — client rejects mismatches |
| Handshake (`hello`) | ✅ Full | Symbol/TF parsed from initial message |
| `snapshot` on connect | ✅ Full | Bars + definitions + historical indicator points |
| Real-time `bar` | ✅ Full | Broadcast to all clients on every tick |
| Real-time `indicators` | ✅ Full | Single-point array after bar close (fast path) |
| History pagination | ✅ Full | `before`/`count`, `noMoreHistory` flag |
| Symbol switching | ✅ Full | Re-snapshot for new symbol |
| Timeframe switching | ✅ Full | Re-snapshot for new timeframe |
| Chart type (`chartType`) | ✅ Full | State tracked per session |
| Ping / Pong | ✅ Full | RTT echo |
| `toast` notifications | ✅ Full | Via server broadcast |
| `get_symbols` → `symbols_list` | ✅ Full | AutoEngine replies with all known symbols from memory + DB |
| `get_indicators` → `indicators_list` | ✅ Full | AutoEngine replies with all registered SeriesDefinitions |
| Multi-chart (`layout`, `chart_symbol`) | ✅ Full | AutoEngine sends `chart_snapshot` for each secondary chart |
| Secondary chart history | ✅ Full | `history` with `chartId` → `chart_history` response |
| Secondary chart live bars | ✅ Full | `push_chart_bar()` available on session |
| Drawing sync (`drawing_*`) | ⚠️ Partial | Client drawing events forwarded; persistence is app responsibility |

> **⚠️ Partial (drawings):** The engine forwards `drawing_upsert`/`drawing_delete`/`drawings_clear` events from the client to your callback hooks. Persisting drawings to DB and restoring them on snapshot requires application-level code.

### Verified Working Flow

```
1. TrexTerminal opens → engine sends snapshot
   - Last 500 OHLCV bars (configurable via snapshot_size)
   - SeriesDefinition for each visible indicator
   - Historical indicator values (PointData arrays keyed by indicator key)

2. User scrolls left → history request → paginated bars returned

3. New bar arrives from exchange:
   engine.push() → bar broadcast + single-point indicator update
   → terminal extends chart in real-time (< 1ms latency)

4. User switches symbol → engine re-snapshots with new symbol data

5. Server restarts:
   seed() loads state from DB → only new bars are recalculated
   → terminal reconnects and resumes from latest bar
```

---

## Writing a Custom Indicator

```python
from trex.engine.indicator import Indicator
from trex.base.ohlcv import OHLCV, ValueExtractor
from collections import deque
from typing import Callable


class MyIndicator(Indicator):
    _ind_name   = "MY_IND"           # unique name, used in indicator key
    _key_params = ("period",)         # params included in the dedup key

    def __init__(
        self,
        period: int = 14,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period = period
        self._win   = deque(maxlen=period)

    # Required stubs
    def init_depends(self) -> None: pass
    def payload_extract(self, ohlcv: OHLCV): pass
    def on_view(self): pass
    def provide_view(self): pass

    def _first_calculate(self, value: float, prev) -> object:
        self._win.append(value)
        if len(self._win) < self.period:
            return None
        return sum(self._win) / self.period   # first emission

    def _calculate_new_value(self, value: float, prev) -> float:
        self._win.append(value)               # deque auto-drops oldest
        return sum(self._win) / self.period

    # State persistence — save internal state for fast restart
    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["win"] = list(self._win)
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._win = deque(state["win"], maxlen=self.period)

    # How this indicator looks on the terminal
    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.line(
            f"my_{self.period}",
            f"My Indicator {self.period}",
            key=self.indicator_key(),
        )]
```

Register and use it exactly like built-in indicators:

```python
from trex.engine.indicator import _register   # or register via api.py function

# Or call directly:
from my_module import MyIndicator
ind = MyIndicator(period=20)
ctx.add(ind, "BTCUSDT", "1h")
```

---

## Loading Candles for Backtesting

`CandleSourcePostgres` streams historical OHLCV rows from a PostgreSQL table into your strategy. It is the bridge between Trex Engine's storage and the [BackTest](https://github.com/DeveloperNasirpur/BackTest) package.

> **Recommended:** Use `load_postgres()` from the BackTest package — it provides a clean synchronous wrapper with date filtering and returns a plain `list[OHLCV]` ready for `Backtest.run()`.

### Direct usage (advanced)

```python
from trex.source.postgres import CandleSourcePostgres
from trex.source.config import ConfigPostgres
import trex

trex.init(source_timeframe="1m")

candles = []

source = CandleSourcePostgres(
    on_provide=candles.append,
    on_finish=lambda: print(f"Loaded {len(candles)} candles"),
)
source.run(table_symbol="BTCUSDT1M")
```

### Expected table schema

```sql
CREATE TABLE "BTCUSDT1M" (
    open_time  BIGINT PRIMARY KEY,   -- Unix milliseconds
    open       DOUBLE PRECISION,
    high       DOUBLE PRECISION,
    low        DOUBLE PRECISION,
    close      DOUBLE PRECISION,
    volume     DOUBLE PRECISION,
    symbol     TEXT
);
```

This is the exact schema created by `TrexStore` — if you use Trex Engine in production the tables already exist.

### ConfigPostgres

```python
from trex.source.config import ConfigPostgres

cfg = ConfigPostgres(
    host     = "localhost",
    port     = 5432,
    user     = "postgres",
    password = "secret",
    database = "okx",        # default
)
```

The `ctx.db_config` attribute holds the active `ConfigPostgres` after `trex.init()` is called with a db config. `CandleSourcePostgres.run()` reads this automatically.

---

## License

MIT — see [LICENSE](LICENSE).

---

*Built for [TrexTerminal](https://github.com/developernasirpur/trexterminal) · Protocol 2.0.0 · Python 3.12+*
