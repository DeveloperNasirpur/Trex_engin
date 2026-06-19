# Trex Engine

**Python SDK for building WebSocket data servers compatible with [TrexTerminal](https://github.com/DeveloperNasirpur/TrexTerminal).**

Trex Engine turns your Python data feed into a fully-featured trading terminal backend: streaming candles, 40+ technical indicators, server-side drawings, lazy-load history, and multi-chart support — all over a single WebSocket connection.

---

## Table of Contents

- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Components](#core-components)
  - [Context (`ctx`)](#context-ctx)
  - [SyncServer / TrexServer](#syncserver--trexserver)
  - [CandleStore / MultiSymbolStore](#candlestore--multisymbolstore)
  - [Indicator Base Class](#indicator-base-class)
  - [SeriesDef Factories](#seriesdef-factories)
  - [Database Store (PostgreSQL)](#database-store-postgresql)
- [Complete Example](#complete-example)
- [Multi-Symbol & Multi-Chart](#multi-symbol--multi-chart)
- [Writing Custom Indicators](#writing-custom-indicators)
- [Available Indicators](#available-indicators)
- [Protocol Reference](#protocol-reference)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                       Your Data Feed                        │
│   (exchange WebSocket / database / CSV / live prices...)    │
└──────────────────────┬──────────────────────────────────────┘
                       │  Bar (OHLCV)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                     Trex Engine                             │
│                                                             │
│   ContextIndicator (ctx)                                    │
│   ├── CTF converters  (1m → 5m, 15m, 1h, 4h, 1d …)        │
│   ├── EMA / RSI / MACD / BB / SuperTrend / …               │
│   └── attach_server() → auto-broadcast on every emit        │
│                                                             │
│   CandleStore / MultiSymbolStore                            │
│   └── thread-safe ring-buffer, history pagination           │
└────────────┬────────────────────────────────────────────────┘
             │  Bar | Point | SeriesDef | Drawing
             ▼
┌─────────────────────────────────────────────────────────────┐
│                  SyncServer / TrexServer                    │
│   WebSocket  ws://0.0.0.0:8765                              │
│   ├── on_connect  → send snapshot (bars + indicators)       │
│   ├── on_symbol   → switch symbol, resend snapshot          │
│   ├── on_history  → return older bars (lazy load)           │
│   └── broadcast_bar()  → push realtime candle to all        │
└──────────────────────┬──────────────────────────────────────┘
                       │  WebSocket (JSON)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                   TrexTerminal (browser)                    │
│   React + lightweight-charts v5                             │
└─────────────────────────────────────────────────────────────┘
```

**Data flow summary:**

1. Your feed calls `store.update(bar)` → `ctx.provide(ohlcv)`.
2. `ctx` routes the bar through CTF converters into every matching indicator.
3. Each indicator emits its value; if `attach_server()` was called, the emission is immediately broadcast as `push_indicators` to every connected client.
4. When a new client connects, `on_connect` fires — you send the recent bars + cached indicator values as a single `snapshot`.
5. When the user scrolls back in time, `on_history` fires — you return the requested page from the store.

---

## Installation

```bash
pip install trex-engine
```

Or from source:

```bash
git clone https://github.com/DeveloperNasirpur/Trex_engin.git
cd Trex_engin
pip install -e .
```

Optional PostgreSQL persistence:

```bash
pip install "trex-engine[postgres]"
```

**Requirements:** Python 3.12+

---

## Quick Start

Minimum working server — demo feed, EMA + RSI, single symbol:

```python
import time, math, random
import trex
from trex.server.sync import SyncServer, SyncSession
from trex.server.store import CandleStore
from trex.domain.types import Bar, Point
from trex.presentation.indicators import Overlay, Oscillator

# ── 1. Configure engine ────────────────────────────────────────────────────────
trex.init(timezone="UTC", source_timeframe="1m")

# ── 2. In-memory bar store ─────────────────────────────────────────────────────
store = CandleStore(max_bars=5_000)

# ── 3. Register indicators ─────────────────────────────────────────────────────
trex.ema("BTCUSDT", "1m", period=20)
trex.rsi("BTCUSDT", "1m", period=14)

# ── 4. Build server ────────────────────────────────────────────────────────────
server = SyncServer(port=8765)

@server.on_connect
def connected(session: SyncSession) -> None:
    session.snapshot(
        store.recent(500),
        symbol="BTCUSDT",
        timeframe="1m",
        definitions=[Overlay.ema(20), Oscillator.rsi(14)],
        indicators=store.indicator_cache,
    )
    session.fit_content()

@server.on_history
def history(session: SyncSession, before: int, count: int) -> None:
    page = store.history_page(before, count)
    session.push_history(page, no_more=len(page) == 0)

# ── 5. Attach server to engine (auto-broadcast on emit) ────────────────────────
server.start()
trex.ctx.attach_server(server.broadcast_indicators)

# ── 6. Feed loop ───────────────────────────────────────────────────────────────
price = 42_000.0
ts    = int(time.time()) - 3600   # start an hour ago

while True:
    price += random.gauss(0, 50)
    bar = Bar(time=ts, open=price, high=price+30, low=price-30, close=price)
    store.update(bar)

    from trex.base.ohlcv import OHLCV
    ohlcv = OHLCV.from_bar(bar, symbol="BTCUSDT")
    trex.ctx.provide(ohlcv)

    server.broadcast_bar(bar)
    ts   += 60
    time.sleep(1)
```

Run it, then open TrexTerminal and connect to `ws://localhost:8765`.

---

## Core Components

### Context (`ctx`)

`trex.ctx` is the global `ContextIndicator` singleton. It manages:

- **CTF converters** — aggregates 1-minute candles into 5m / 15m / 1h / 4h / 1d bars.
- **Indicator registry** — deduplicates instances; same `(class, symbol, tf, params)` = same object.
- **Server bridge** — `attach_server()` injects a broadcast hook into every indicator.

```python
import trex

# Initialize once at startup
trex.init(
    timezone="Asia/Tehran",    # IANA tz for bar-open detection in CTF
    source_timeframe="1m",     # incoming candle resolution
)

# Register indicators (returns a ListenerKey for later de-registration)
key_ema = trex.ema("BTCUSDT", "1m", period=20)
key_rsi = trex.rsi("BTCUSDT", "1m", period=14)
key_bb  = trex.bbands("BTCUSDT", "1m", period=20, mult=2.0)

# Feed one candle (call this from your data-feed thread)
from trex.base.ohlcv import OHLCV
trex.ctx.provide(OHLCV.from_bar(bar, symbol="BTCUSDT"))

# Attach server — from this point, every indicator emit broadcasts automatically
trex.ctx.attach_server(
    broadcast_fn=server.broadcast_indicators,   # called with {key: [Point]}
    define_fn=server.broadcast_definitions,      # optional: sends SeriesDef to terminal
)

# Detach when shutting down
trex.ctx.detach_server()
```

**Multi-symbol:** call `trex.ctx.provide(ohlcv)` with any symbol — the ctx routes
it to the correct indicator bucket automatically.

---

### SyncServer / TrexServer

`SyncServer` is the recommended interface: all callbacks are plain (sync) functions
and the asyncio event loop runs in a daemon thread.

```python
from trex.server.sync import SyncServer, SyncSession

server = SyncServer(
    host="0.0.0.0",
    port=8765,
    max_clients=100,
    max_workers=64,      # thread-pool size for callbacks
)

# ── Event hooks ────────────────────────────────────────────────────────────────

@server.on_connect
def on_connect(session: SyncSession) -> None:
    """New client connected."""
    print(f"[+] {session.id[:8]}  symbol={session.symbol}")
    session.snapshot(bars=store.recent(500), symbol="BTCUSDT", timeframe="1m")
    session.fit_content()

@server.on_disconnect
def on_disconnect(session: SyncSession) -> None:
    print(f"[-] {session.id[:8]}")

@server.on_symbol
def on_symbol(session: SyncSession, symbol: str) -> None:
    """User changed the chart symbol."""
    bars = store.recent(500)   # load bars for the new symbol
    session.snapshot(bars=bars, symbol=symbol, timeframe=session.timeframe or "1m")

@server.on_timeframe
def on_timeframe(session: SyncSession, tf: str) -> None:
    """User changed the chart timeframe."""
    # Timeframe conversion is handled automatically by the CTF converters;
    # you don't need to re-query — the ctx already has the right bars.
    pass

@server.on_history
def on_history(session: SyncSession, before: int, count: int) -> None:
    """User scrolled back — send older bars."""
    page = store.history_page(before=before, count=count)
    session.push_history(page, no_more=len(page) == 0)

@server.on_drawing_upsert
def on_drawing_upsert(session: SyncSession, drawing: dict) -> None:
    """User saved a drawing — persist it."""
    db.save_drawing(drawing)

@server.on_drawing_delete
def on_drawing_delete(session: SyncSession, ids: list[str]) -> None:
    db.delete_drawings(ids)

# ── Lifecycle ──────────────────────────────────────────────────────────────────

server.start()          # returns immediately; loop in daemon thread

# Optional: wait for clients
time.sleep(1)
print(f"Clients: {server.client_count}")

server.stop()           # graceful shutdown

# ── Broadcast (thread-safe) ────────────────────────────────────────────────────

server.broadcast_bar(bar)                      # realtime candle to all clients
server.broadcast_indicators({"ema20": [pt]})   # manual indicator push
server.broadcast_toast("Reconnected", "info")  # notification popup
```

**SyncSession methods:**

| Method | Description |
|--------|-------------|
| `snapshot(bars, *, symbol, timeframe, digits, definitions, indicators, drawings)` | Send full chart state (initial load / symbol change) |
| `push_bar(bar)` | Push one realtime candle |
| `push_history(bars, *, no_more)` | Return a history page |
| `define(*defs)` | Send SeriesDef list (declares how to render indicator series) |
| `push_indicators(data)` | Send `{series_key: [Point]}` |
| `set_drawings(drawings)` | Replace all drawings |
| `upsert_drawing(drawing)` | Add / update one drawing |
| `delete_drawing(*ids)` | Remove drawings by id |
| `set_symbol(symbol)` | Tell the chart to switch symbol |
| `set_timeframe(tf)` | Tell the chart to switch timeframe |
| `fit_content()` | Auto-fit the visible range |
| `scroll_to_end()` | Jump to the most recent bar |
| `zoom_range(from_ts, to_ts)` | Set visible time range |
| `toast(msg, kind)` | Show a notification popup |
| `alert(msg)` | Show an alert dialog |

---

### CandleStore / MultiSymbolStore

Thread-safe in-memory bar stores.

```python
from trex.server.store import CandleStore, MultiSymbolStore
from trex.domain.types import Bar

# ── Single symbol ──────────────────────────────────────────────────────────────
store = CandleStore(
    max_bars=10_000,
    on_bar_close=lambda bar: print(f"Bar closed: {bar.close}"),
)

store.seed(historical_bars)       # bulk-load at startup (de-duped + sorted)
closed = store.update(new_bar)    # upsert; True if a new bar opened
bars   = store.recent(500)        # last N bars, oldest-first
page   = store.history_page(before=ts, count=300)   # for lazy-load
last   = store.last_bar()

# Indicator cache — new clients get pre-computed values immediately
store.store_indicators({"ema20": points, "rsi14": rsi_points})   # full replace
store.update_indicator_tails({"ema20": pt})                        # O(1) tail update
cache  = store.indicator_cache   # {series_key: [Point]}

# ── Multi-symbol / multi-timeframe ─────────────────────────────────────────────
ms = MultiSymbolStore(max_bars=10_000)

ms.seed("BTCUSDT", "1m", historical_bars)
closed = ms.update("BTCUSDT", "1m", new_bar)
bars   = ms.recent("BTCUSDT", "1m", 500)
page   = ms.history_page("BTCUSDT", "1m", before=ts, count=300)
```

---

### Indicator Base Class

Every indicator inherits from `trex.engine.indicator.Indicator`. You implement
four abstract methods:

```python
from trex.engine.indicator import Indicator
from trex.presentation.indicators import Overlay
from trex.domain.types import SeriesDef, Point


class MyEMA(Indicator):
    """Exponential Moving Average — minimal custom indicator example."""

    def __init__(self, *, period: int = 20, **kw) -> None:
        super().__init__(**kw)
        self.period = period
        self._k     = 2 / (period + 1)

    # ── 1. Wire sub-indicator dependencies ────────────────────────────────────
    def init_depends(self) -> None:
        pass   # no sub-indicators needed

    # ── 2. Declare how to display this indicator on the terminal ──────────────
    def series_defs(self) -> list[SeriesDef]:
        return [Overlay.ema(self.period)]

    # ── 3. Boot phase — accumulate until you have enough data ─────────────────
    def _first_calculate(self, value: float, prev) -> float | None:
        if self._pipe.tick_count < self.period:
            return None              # not enough data yet — skip
        return value                 # seed EMA with SMA (simplified)

    # ── 4. Steady-state — return the new value (or None to skip) ─────────────
    def _calculate_new_value(self, value: float, prev: float) -> float:
        return prev + self._k * (value - prev)

    # ── 5. (Optional) Convert emitted value → {series_key: [Point]} ──────────
    # The default handles single float; override for multi-series indicators.
    # def _make_points(self, value, timestamp) -> dict[str, list[Point]]:
    #     return {f"ema{self.period}": [Point(timestamp, value)]}
```

**Register and use your indicator:**

```python
from trex.engine.context import ctx

ctx.get(MyEMA, symbol="BTCUSDT", timeframe="1m", period=20)
```

Or via the public API:

```python
# Use the built-in EMA (already implemented)
trex.ema("BTCUSDT", "1m", period=20)
```

**Multi-series indicators** (e.g. MACD → line + signal + histogram):

```python
from dataclasses import dataclass

@dataclass
class MACDVal:
    macd:      float
    signal:    float
    histogram: float

class MyMACD(Indicator):
    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return Oscillator.macd(self.fast, self.slow, self.sig)

    def _make_points(self, value: MACDVal, timestamp: int):
        return {
            "macd_line":   [Point(timestamp, value.macd)],
            "macd_signal": [Point(timestamp, value.signal)],
            "macd_hist":   [Point(timestamp, value.histogram)],
        }
```

---

### SeriesDef Factories

`trex.presentation.indicators` provides `Overlay`, `Oscillator`, `Volume`, and
`Volatility` factory classes that produce pre-styled `SeriesDef` objects
matching TrexTerminal's expected keys.

```python
from trex.presentation.indicators import Overlay, Oscillator, Volume, Volatility

definitions = [
    # Main-pane overlays
    Overlay.ema(20),
    Overlay.ema(50, color="#E91E63"),
    *Overlay.bollinger(20, 2.0),
    Overlay.vwap(),
    Overlay.supertrend(10, 3.0),

    # Sub-pane oscillators
    Oscillator.rsi(14),
    *Oscillator.macd(12, 26, 9),
    *Oscillator.stochastic(14, 3, 3),
    Oscillator.cci(20),

    # Volume
    Volume.bars(),
    Volume.obv(),

    # Volatility
    Volatility.atr(14),
]

# Send to one client
session.define(*definitions)

# Or include in snapshot
session.snapshot(bars, definitions=definitions, indicators=store.indicator_cache)
```

---

### Database Store (PostgreSQL)

For production deployments that need persistent history:

```python
from trex.store.db_store import TrexStore, DbConfig

cfg = DbConfig(
    host="localhost",
    port=5432,
    dbname="trex",
    user="trex",
    password="secret",
)

store = TrexStore(cfg, schema="binance")
store.ensure_table("BTCUSDT", "1m")   # creates table if missing

# Upsert candles
store.upsert_candles("BTCUSDT", "1m", bars)

# Store indicator values
store.upsert_indicators("BTCUSDT", "1m", {
    ts: {"ema20": 42100.5, "rsi14": 68.4}
})

# Read history
bars = store.fetch_bars("BTCUSDT", "1m", limit=5_000)
bars = store.fetch_bars_before("BTCUSDT", "1m", before=ts, count=300)
```

---

## Complete Example

Full server: two symbols (BTC, ETH), EMA + RSI + Bollinger, PostgreSQL history:

```python
"""
trex_server.py — production-ready multi-symbol server
"""
import time
import threading
import logging
from trex.server.sync import SyncServer, SyncSession
from trex.server.store import MultiSymbolStore
from trex.domain.types import Bar
from trex.base.ohlcv import OHLCV
from trex.presentation.indicators import Overlay, Oscillator, Volume
import trex

logging.basicConfig(level=logging.INFO)

SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# ── Engine ─────────────────────────────────────────────────────────────────────
trex.init(timezone="UTC", source_timeframe="1m")

for sym in SYMBOLS:
    trex.ema(sym,    "1m", period=20)
    trex.ema(sym,    "1m", period=50)
    trex.rsi(sym,    "1m", period=14)
    trex.bbands(sym, "1m", period=20, mult=2.0)

# ── Store ──────────────────────────────────────────────────────────────────────
ms = MultiSymbolStore(max_bars=10_000)

def load_history() -> None:
    # Replace with your real data source
    import random
    for sym in SYMBOLS:
        ts, price = int(time.time()) - 7200, 42_000 if sym == "BTCUSDT" else 2_800
        bars = []
        for _ in range(500):
            price += random.gauss(0, 30)
            bars.append(Bar(time=ts, open=price, high=price+20,
                            low=price-20, close=price, volume=1000))
            ts += 60
        ms.seed(sym, "1m", bars)

load_history()

# ── Indicator definitions list ─────────────────────────────────────────────────
DEFINITIONS = [
    Overlay.ema(20),
    Overlay.ema(50, color="#E91E63"),
    *Overlay.bollinger(20, 2.0),
    Oscillator.rsi(14),
    Volume.bars(),
]

# ── Server ─────────────────────────────────────────────────────────────────────
server = SyncServer(port=8765)

@server.on_connect
def on_connect(session: SyncSession) -> None:
    sym = session.symbol or "BTCUSDT"
    tf  = session.timeframe or "1m"
    store = ms.get_store(sym, tf)
    session.snapshot(
        store.recent(500),
        symbol=sym,
        timeframe=tf,
        definitions=DEFINITIONS,
        indicators=store.indicator_cache,
    )
    session.fit_content()

@server.on_symbol
def on_symbol(session: SyncSession, symbol: str) -> None:
    tf    = session.timeframe or "1m"
    store = ms.get_store(symbol.upper(), tf)
    session.snapshot(
        store.recent(500),
        symbol=symbol,
        timeframe=tf,
        definitions=DEFINITIONS,
        indicators=store.indicator_cache,
    )

@server.on_history
def on_history(session: SyncSession, before: int, count: int) -> None:
    sym  = (session.symbol or "BTCUSDT").upper()
    tf   = session.timeframe or "1m"
    page = ms.history_page(sym, tf, before=before, count=count)
    session.push_history(page, no_more=len(page) == 0)

server.start()
trex.ctx.attach_server(server.broadcast_indicators)

# ── Live feed ──────────────────────────────────────────────────────────────────
import random

prices = {sym: 42_000 if sym == "BTCUSDT" else 2_800 for sym in SYMBOLS}
ts     = int(time.time())

while True:
    for sym in SYMBOLS:
        prices[sym] += random.gauss(0, 20)
        p = prices[sym]
        bar = Bar(time=ts, open=p, high=p+15, low=p-15, close=p, volume=500)
        closed = ms.update(sym, "1m", bar)
        trex.ctx.provide(OHLCV.from_bar(bar, symbol=sym))
        server.broadcast_bar(bar, filter=lambda s: s.symbol == sym)
    ts   += 60
    time.sleep(1)
```

---

## Multi-Symbol & Multi-Chart

TrexTerminal supports up to 4 simultaneous chart panes. Each pane sends its
own `symbol` and `timeframe` when the user makes selections.

Your `on_symbol` and `on_timeframe` hooks receive **per-session** events, so
two users can watch different symbols at the same time without interference.

```python
@server.on_symbol
def on_symbol(session: SyncSession, symbol: str) -> None:
    # session.symbol is updated before this hook fires
    store = ms.get_store(symbol.upper(), session.timeframe or "1m")
    session.snapshot(store.recent(500), symbol=symbol, ...)

@server.on_timeframe
def on_timeframe(session: SyncSession, tf: str) -> None:
    sym   = (session.symbol or "BTCUSDT").upper()
    store = ms.get_store(sym, tf)
    session.snapshot(store.recent(500), symbol=sym, timeframe=tf, ...)
```

**Realtime broadcast with symbol filter:**

```python
# Only push BTC bars to sessions currently viewing BTC
server.broadcast_bar(
    btc_bar,
    filter=lambda s: (s.symbol or "").upper() == "BTCUSDT",
)
```

---

## Writing Custom Indicators

### Step 1 — Choose a value extractor

```python
from trex.base.ohlcv import ValueExtractor

# Built-in extractors
ValueExtractor.extract_close    # bar.close
ValueExtractor.extract_open     # bar.open
ValueExtractor.extract_high     # bar.high
ValueExtractor.extract_low      # bar.low
ValueExtractor.extract_hl2      # (high + low) / 2
ValueExtractor.extract_hlc3     # (high + low + close) / 3
ValueExtractor.extract_ohlc4    # (open + high + low + close) / 4
```

### Step 2 — Implement the Indicator

```python
from trex.engine.indicator import Indicator
from trex.domain.types import SeriesDef, Level, Point
from trex.presentation.indicators import Oscillator


class RSI(Indicator):
    def __init__(self, *, period: int = 14, **kw) -> None:
        super().__init__(**kw)
        self.period = period
        self._avg_gain = 0.0
        self._avg_loss = 0.0

    def init_depends(self) -> None:
        pass  # RSI depends only on raw price — no sub-indicators

    def series_defs(self) -> list[SeriesDef]:
        return [Oscillator.rsi(self.period)]

    def _first_calculate(self, value: float, prev) -> float | None:
        if self._pipe.tick_count < self.period:
            return None
        # Seed with simple averages over the first `period` ticks
        changes = [
            self._pipe.input_values[i] - self._pipe.input_values[i - 1]
            for i in range(1, self.period)
        ]
        gains  = [c for c in changes if c > 0]
        losses = [-c for c in changes if c < 0]
        self._avg_gain = sum(gains)  / self.period
        self._avg_loss = sum(losses) / self.period
        if self._avg_loss == 0:
            return 100.0
        return 100 - 100 / (1 + self._avg_gain / self._avg_loss)

    def _calculate_new_value(self, value: float, prev: float) -> float:
        change = value - self._pipe.prev_value
        gain   = max(change, 0)
        loss   = max(-change, 0)
        k      = 1 / self.period
        self._avg_gain = (1 - k) * self._avg_gain + k * gain
        self._avg_loss = (1 - k) * self._avg_loss + k * loss
        if self._avg_loss == 0:
            return 100.0
        return 100 - 100 / (1 + self._avg_gain / self._avg_loss)
```

### Step 3 — Register and connect

```python
from trex.engine.context import ctx

ctx.get(RSI, symbol="BTCUSDT", timeframe="1m", period=14)

# Or add a listener:
def on_rsi(value: float) -> None:
    print(f"RSI: {value:.2f}")

import trex
key = trex.rsi("BTCUSDT", "1m", period=14, listener=on_rsi)

# Remove listener later:
trex.de_attach_by_key(key)
```

### Sub-indicator dependencies

Higher-timeframe indicators use `init_depends()` + the context API:

```python
class ATR_4H(Indicator):
    """ATR on the 4-hour timeframe, fed by 1-minute bars via CTF."""

    def init_depends(self) -> None:
        api  = self._ctx.api   # always use this, never the module-level api
        key  = api.atr(self.context_symbol, "4H", period=14,
                        listener=self._on_atr)
        self.depends(self._ctx._indicators[self.context_symbol][key.indicator])

    def _on_atr(self, value: float) -> None:
        self.emit(value)   # re-emit on our own context_key

    def series_defs(self):   ...
    def _first_calculate(self, v, p):  return None
    def _calculate_new_value(self, v, p): return None
```

---

## Available Indicators

All indicators are accessible via `trex.<name>(symbol, timeframe, ...)`.

### Trend / Moving Averages

| Function | Description |
|----------|-------------|
| `trex.sma(sym, tf, period)` | Simple Moving Average |
| `trex.ema(sym, tf, period)` | Exponential Moving Average |
| `trex.wma(sym, tf, period)` | Weighted Moving Average |
| `trex.hma(sym, tf, period)` | Hull Moving Average |
| `trex.dema(sym, tf, period)` | Double EMA |
| `trex.tema(sym, tf, period)` | Triple EMA |
| `trex.zlema(sym, tf, period)` | Zero-Lag EMA |
| `trex.vwma(sym, tf, period)` | Volume-Weighted MA |
| `trex.kama(sym, tf, er_period, fast, slow)` | Kaufman Adaptive MA |
| `trex.vwap(sym, tf)` | VWAP (daily reset) |

### Volatility

| Function | Description |
|----------|-------------|
| `trex.tr(sym, tf)` | True Range |
| `trex.atr(sym, tf, period)` | Average True Range |
| `trex.stddev(sym, tf, period)` | Rolling Standard Deviation |
| `trex.bbands(sym, tf, period, mult)` | Bollinger Bands → `BBVal(upper, middle, lower)` |
| `trex.keltner(sym, tf, period, atr_period, mult)` | Keltner Channel |
| `trex.donchian(sym, tf, period)` | Donchian Channel |

### Momentum / Oscillators

| Function | Description |
|----------|-------------|
| `trex.rsi(sym, tf, period)` | RSI (Wilder smoothing) |
| `trex.macd(sym, tf, fast, slow, signal)` | MACD → `MACDVal(macd, signal, histogram)` |
| `trex.stochastic(sym, tf, k_period, d_period)` | Stochastic → `StochVal(k, d)` |
| `trex.cci(sym, tf, period)` | Commodity Channel Index |
| `trex.williams_r(sym, tf, period)` | Williams %R |
| `trex.roc(sym, tf, period)` | Rate of Change |
| `trex.momentum(sym, tf, period)` | Momentum Oscillator |
| `trex.mfi(sym, tf, period)` | Money Flow Index |
| `trex.obv(sym, tf)` | On-Balance Volume |
| `trex.cmo(sym, tf, period)` | Chande Momentum Oscillator |
| `trex.trix(sym, tf, period)` | TRIX |
| `trex.adx(sym, tf, period)` | ADX → `ADXVal(adx, plus_di, minus_di)` |
| `trex.aroon(sym, tf, period)` | Aroon → `AroonVal(up, down, oscillator)` |

### Hybrid / Compound

| Function | Description |
|----------|-------------|
| `trex.supertrend(sym, tf, period, multiplier)` | SuperTrend → `SupertrendVal(value, is_uptrend)` |
| `trex.ichimoku(sym, tf, tenkan, kijun, senkou)` | Ichimoku Kinko Hyo |
| `trex.psar(sym, tf, step, max_af)` | Parabolic SAR |
| `trex.zigzag_base(sym, tf, min_accept_size)` | ZigZag channel-break |

---

## Protocol Reference

The WebSocket protocol is documented in full in
[SERVER_API.md](https://github.com/DeveloperNasirpur/TrexTerminal/blob/main/SERVER_API.md)
in the TrexTerminal repository.

**Quick reference — server→client message types:**

| Message type | Trigger | Description |
|---|---|---|
| `snapshot` | `on_connect` / symbol change | Full chart state: bars + indicator defs + values + drawings |
| `bar` | realtime tick | One OHLCV bar (update or new) |
| `history` | `on_history` | Paginated older bars for lazy-load |
| `definitions` | after snapshot | SeriesDef list (indicator display contracts) |
| `indicators` | every indicator emit | `{series_key: [Point]}` |
| `drawings_set` | `on_connect` | Replace all drawings |
| `drawing_upsert` | server-push | Add/update one drawing |
| `drawing_delete` | server-push | Remove drawings by id |
| `fit_content` | after snapshot | Auto-fit visible range |
| `toast` | any time | Notification popup |

**Quick reference — client→server message types:**

| Message type | Hook | Payload |
|---|---|---|
| `symbol` | `on_symbol` | `{symbol: string}` |
| `timeframe` | `on_timeframe` | `{timeframe: string}` |
| `history_request` | `on_history` | `{before: int, count: int}` |
| `drawing_upsert` | `on_drawing_upsert` | Full drawing object |
| `drawing_delete` | `on_drawing_delete` | `{ids: string[]}` |
| `drawings_clear` | `on_drawings_clear` | `{}` |
| `chart_type` | `on_chart_type` | `{chartType: string}` |

---

## License

MIT © [nasirpoor](https://github.com/DeveloperNasirpur)
