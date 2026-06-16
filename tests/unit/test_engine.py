"""tests/unit/test_engine.py — Unit tests for refactored trex engine."""
from __future__ import annotations

import sys
sys.path.insert(0, "/home/claude/trex-engine/src")

from datetime import datetime, timezone
import pytest
from trex.base.ohlcv import OHLCV, OHLCVFactory, ValueExtractor
from trex.base.timeframe import Timeframe
from trex.engine.pipeline import Pipeline, PipelineHost
from trex.engine.context import ContextIndicator
from trex.indic.trend.sma import SMA
from trex.indic.trend.ema import EMA
from trex.indic.trend.wma import WMA
from trex.indic.trend.kama import KAMA
from trex.indic.trend.zlema import ZLEMA
from trex.indic.momentum.rsi import Rsi
from trex.indic.momentum.macd import MACD
from trex.indic.volatility.tr import Tr
from trex.indic.volatility.atr import Atr
from trex.indic.volatility.stddev import StdDev
from trex.indic.volatility.bbands import BollingerBands
from trex.indic.volatility.donchian import DonchianChannel
from trex.indic.oscillator.cci import CCI
from trex.indic.oscillator.obv import OBV
from trex.indic.oscillator.cmo import CMO
from trex.indic.oscillator.mom import Momentum
from trex.indic.oscillator.roc import ROC
from trex.indic.oscillator.williams_r import WilliamsR
from trex.indic.hybrid.ichimoku import Ichimoku
from trex.indic.hybrid.psar import ParabolicSAR


def _bar(o, h, l, c, v=1.0, sym="BTC") -> OHLCV:
    return OHLCV(open=o, high=h, low=l, close=c, volume=v,
                 time=datetime.now(timezone.utc), symbol=sym, str_time="1m",
                 side=0 if o > c else 1)


def _feed_float(ind, values: list[float]) -> list:
    """Feed via OHLCV bars (close=v) so extract_close works."""
    results = []
    ind.add_callback_listener("t", results.append)
    for v in values:
        ind.add_input_value(_bar(v, v+1, v-1, v))
    ind.remove_callback_listener("t")
    return results


def _feed_bars(ind, bars) -> list:
    results = []
    ind.add_callback_listener("t", results.append)
    for b in bars: ind.add_input_value(b)
    ind.remove_callback_listener("t")
    return results


# ── OHLCV ─────────────────────────────────────────────────────────────────────

class TestOHLCV:
    def test_side_bearish(self) -> None:
        bar = _bar(110, 115, 100, 105)
        assert bar.side == 0   # open(110) > close(105) → bearish

    def test_side_bullish(self) -> None:
        bar = _bar(100, 110, 90, 108)
        assert bar.side == 1   # open(100) < close(108) → bullish

    def test_round_trip(self) -> None:
        bar = _bar(100, 110, 90, 105, v=5.0)
        bar2 = OHLCV.from_dict(bar.to_dict())
        assert bar2.open == bar.open and bar2.close == bar.close

    def test_key(self) -> None:
        bar = OHLCV(symbol="ETH", str_time="4H")
        assert bar.key == ("ETH", "4H")

    def test_factory(self) -> None:
        bars = OHLCVFactory.from_matrix([[100.0, 110.0, 90.0, 105.0, 2.0]])
        assert bars[0].high == 110.0

    def test_extract_close(self) -> None:
        assert ValueExtractor.extract_close(_bar(100,110,90,42)) == 42.0

    def test_extract_hlc3(self) -> None:
        bar = _bar(100, 120, 80, 100)
        assert ValueExtractor.extract_hlc3(bar) == 100.0   # (120+80+100)/3


# ── Pipeline ──────────────────────────────────────────────────────────────────

class TestPipeline:
    def test_warmup(self) -> None:
        pipe = Pipeline(warmup=3); emitted = []

        class H(PipelineHost):
            def _first_calculate(self, v, p): return v
            def _calculate_new_value(self, v, p): return v

        h = H(); pipe.add_callback("t", emitted.append)
        for i in range(3): pipe.tick(float(i), h)
        assert emitted == []

    def test_boot_run_transition(self) -> None:
        pipe = Pipeline(); results = []

        class H(PipelineHost):
            def _first_calculate(self, v, p): return v if v > 5 else None
            def _calculate_new_value(self, v, p): return v * 10

        h = H(); pipe.add_callback("t", results.append)
        pipe.tick(3.0, h); pipe.tick(4.0, h)
        assert results == []
        pipe.tick(6.0, h)   # emits 6.0, transitions
        assert 6.0 in results
        pipe.tick(2.0, h)   # run: 20.0
        assert 20.0 in results

    def test_is_running(self) -> None:
        pipe = Pipeline()

        class H(PipelineHost):
            def _first_calculate(self, v, p): return v
            def _calculate_new_value(self, v, p): return v

        h = H(); assert not pipe.is_running
        pipe.tick(1.0, h); assert pipe.is_running

    def test_save_input(self) -> None:
        pipe = Pipeline(save_input=True, max_input=5)

        class H(PipelineHost):
            def _first_calculate(self, v, p): return True
            def _calculate_new_value(self, v, p): return v

        h = H()
        for i in range(3): pipe.tick(float(i), h)
        assert len(pipe.input_values) == 3


# ── SMA ───────────────────────────────────────────────────────────────────────

class TestSMA:
    def test_first_value(self) -> None:
        sma = SMA(period=3); sma.init_depends()
        r = _feed_float(sma, [1.0, 2.0, 3.0])
        assert len(r) >= 1 and abs(r[0] - 2.0) < 1e-9

    def test_sliding_window(self) -> None:
        sma = SMA(period=3); sma.init_depends()
        r = _feed_float(sma, [1.0, 2.0, 3.0, 4.0, 5.0])
        assert abs(r[-1] - 4.0) < 1e-9   # avg(3,4,5)

    def test_period_1(self) -> None:
        sma = SMA(period=1); sma.init_depends()
        r = _feed_float(sma, [7.0, 13.0])
        assert r == [7.0, 13.0]

    def test_no_libs_import(self) -> None:
        import inspect, trex.indic.trend.sma as m
        assert "libs.trex" not in inspect.getsource(m)
        assert "lightweight_charts" not in inspect.getsource(m)


# ── EMA ───────────────────────────────────────────────────────────────────────

class TestEMA:
    def test_converges(self) -> None:
        ema = EMA(period=5); ema.init_depends()
        r = _feed_float(ema, [100.0] * 30)
        assert abs(r[-1] - 100.0) < 0.01

    def test_no_libs_import(self) -> None:
        import inspect, trex.indic.trend.ema as m
        assert "libs.trex" not in inspect.getsource(m)


# ── WMA ───────────────────────────────────────────────────────────────────────

class TestWMA:
    def test_weighted(self) -> None:
        wma = WMA(period=3); wma.init_depends()
        r = _feed_float(wma, [1.0, 2.0, 3.0])
        expected = (1*1 + 2*2 + 3*3) / (1+2+3)
        assert abs(r[0] - expected) < 1e-9


# ── RSI ───────────────────────────────────────────────────────────────────────

class TestRsi:
    def test_range(self) -> None:
        rsi = Rsi(period=14); rsi.init_depends()
        r = _feed_float(rsi, [100 + i*0.5 for i in range(50)])
        assert all(0.0 <= v <= 100.0 for v in r)

    def test_uptrend_high(self) -> None:
        rsi = Rsi(period=14); rsi.init_depends()
        r = _feed_float(rsi, [float(100 + i*5) for i in range(50)])
        assert r[-1] > 90.0

    def test_downtrend_low(self) -> None:
        rsi = Rsi(period=14); rsi.init_depends()
        r = _feed_float(rsi, [float(1000 - i*5) for i in range(50)])
        assert r[-1] < 10.0

    def test_no_pandas_import(self) -> None:
        import inspect, trex.indic.momentum.rsi as m
        src = inspect.getsource(m)
        assert "pandas" not in src
        assert "lightweight_charts" not in src
        assert "libs.trex" not in src


# ── MACD (context-driven) ──────────────────────────────────────────────────────

class TestMACD:
    def test_emits_macdval(self) -> None:
        from trex.indic.momentum.macd import MACDVal
        ctx2 = ContextIndicator(); ctx2.configure()
        inst = ctx2.get(MACD, "BTC", "1m", fast_period=3, slow_period=5, signal_period=3)
        results = []
        inst.add_callback_listener("t", results.append)
        for i in range(20):
            ctx2.provide(_bar(100+i, 102+i, 98+i, 101+i))
        assert len(results) > 0
        assert isinstance(results[-1], MACDVal)


# ── TR ────────────────────────────────────────────────────────────────────────

class TestTr:
    def test_first_bar(self) -> None:
        tr = Tr(); tr.init_depends()
        r = _feed_bars(tr, [_bar(100,110,90,105), _bar(105,115,95,110)])
        assert len(r) >= 1 and r[0] > 0

    def test_full_formula(self) -> None:
        tr = Tr(); tr.init_depends()
        bars = [_bar(100,110,90,100), _bar(100,120,95,115)]
        r = _feed_bars(tr, bars)
        assert abs(r[-1] - 25.0) < 1e-9   # max(25,20,5)=25


# ── StdDev ────────────────────────────────────────────────────────────────────

class TestStdDev:
    def test_constant_zero(self) -> None:
        sd = StdDev(period=5); sd.init_depends()
        r = _feed_float(sd, [10.0]*20)
        assert abs(r[-1]) < 1e-9

    def test_positive_varied(self) -> None:
        sd = StdDev(period=5); sd.init_depends()
        r = _feed_float(sd, [1.0,2.0,3.0,4.0,5.0,6.0])
        assert r[-1] > 0


# ── BBands ────────────────────────────────────────────────────────────────────

class TestBBands:
    def test_band_order(self) -> None:
        from trex.indic.volatility.bbands import BBVal
        ctx2 = ContextIndicator(); ctx2.configure()
        inst = ctx2.get(BollingerBands, "BTC", "1m", period=5, mult=2.0)
        results = []
        inst.add_callback_listener("t", results.append)
        for v in [100.0,102.0,98.0,105.0,99.0,103.0,101.0]:
            ctx2.provide(_bar(v, v+1, v-1, v))
        assert len(results) > 0
        last: BBVal = results[-1]
        assert last.upper >= last.middle >= last.lower


# ── Donchian ──────────────────────────────────────────────────────────────────

class TestDonchian:
    def test_channel(self) -> None:
        from trex.indic.volatility.donchian import DonchianVal
        dc = DonchianChannel(period=3); dc.init_depends()
        bars = [_bar(100,110,90,100), _bar(100,120,85,100), _bar(100,115,95,100)]
        r = _feed_bars(dc, bars)
        assert r[-1].upper == 120.0 and r[-1].lower == 85.0


# ── OBV ───────────────────────────────────────────────────────────────────────

class TestOBV:
    def test_increases_up(self) -> None:
        obv = OBV(); obv.init_depends()
        bars = [_bar(100,105,98,100,100), _bar(100,108,102,107,150)]
        r = _feed_bars(obv, bars)
        assert r[-1] > 0

    def test_decreases_down(self) -> None:
        obv = OBV(); obv.init_depends()
        bars = [_bar(100,105,98,100,100), _bar(100,101,95,96,200)]
        r = _feed_bars(obv, bars)
        assert r[-1] < 0


# ── Momentum ──────────────────────────────────────────────────────────────────

class TestMomentum:
    def test_constant_increment(self) -> None:
        mom = Momentum(period=3); mom.init_depends()
        r = _feed_float(mom, [1.0,2.0,3.0,4.0,5.0])
        assert all(abs(v - 3.0) < 1e-9 for v in r)


# ── ROC ───────────────────────────────────────────────────────────────────────

class TestROC:
    def test_double(self) -> None:
        roc = ROC(period=1); roc.init_depends()
        r = _feed_float(roc, [100.0, 200.0])
        assert abs(r[-1] - 100.0) < 1e-9


# ── CMO ───────────────────────────────────────────────────────────────────────

class TestCMO:
    def test_range(self) -> None:
        cmo = CMO(period=5); cmo.init_depends()
        r = _feed_float(cmo, [100+i*2 for i in range(20)])
        assert all(-100.0 <= v <= 100.0 for v in r)


# ── WilliamsR ─────────────────────────────────────────────────────────────────

class TestWilliamsR:
    def test_range(self) -> None:
        wr = WilliamsR(period=5); wr.init_depends()
        bars = [_bar(100+i, 110+i, 90+i, 105+i) for i in range(10)]
        r = _feed_bars(wr, bars)
        assert all(-100.0 <= v <= 0.0 for v in r)


# ── Ichimoku ──────────────────────────────────────────────────────────────────

class TestIchimoku:
    def test_emits_val(self) -> None:
        from trex.indic.hybrid.ichimoku import IchimokuVal
        ichi = Ichimoku(tenkan_period=3, kijun_period=5, senkou_period=7)
        ichi.init_depends()
        bars = [_bar(100+i, 110+i, 90+i, 105+i) for i in range(10)]
        r = _feed_bars(ichi, bars)
        assert len(r) > 0 and isinstance(r[-1], IchimokuVal)


# ── PSAR ──────────────────────────────────────────────────────────────────────

class TestPSAR:
    def test_emits_val(self) -> None:
        from trex.indic.hybrid.psar import PSARVal
        psar = ParabolicSAR(); psar.init_depends()
        bars = [_bar(100+i, 105+i, 95+i, 102+i) for i in range(10)]
        r = _feed_bars(psar, bars)
        assert len(r) > 0 and isinstance(r[-1], PSARVal)
        assert isinstance(r[-1].is_uptrend, bool)


# ── ContextIndicator ──────────────────────────────────────────────────────────

class TestContext:
    def _c(self): c = ContextIndicator(); c.configure(); return c

    def test_get_creates(self) -> None:
        assert isinstance(self._c().get(SMA, "BTC", "1m", period=20), SMA)

    def test_get_same_instance(self) -> None:
        c = self._c()
        assert c.get(SMA,"BTC","1m",period=20) is c.get(SMA,"BTC","1m",period=20)

    def test_different_params(self) -> None:
        c = self._c()
        assert c.get(SMA,"BTC","1m",period=20) is not c.get(SMA,"BTC","1m",period=50)

    def test_info(self) -> None:
        c = self._c(); c.get(SMA,"BTC","1m",period=20)
        info = c.indicators_info("BTC")
        assert any(v.name == "SMA" for v in info.values())

    def test_snapshot(self) -> None:
        c = self._c()
        c.get(SMA,"BTC","1m",period=20); c.get(Rsi,"ETH","4H",period=14)
        snap = c.snapshot()
        assert "BTC" in snap and "ETH" in snap

    def test_no_libs_import(self) -> None:
        import inspect, trex.engine.context as m
        src = inspect.getsource(m)
        # The string "libs.trex" appears only in docstrings as migration notes
        # Check actual import statements don't use libs.trex
        import_lines = [l for l in src.splitlines() if l.startswith("from ") or l.startswith("import ")]
        assert not any("libs" in l for l in import_lines)
        assert not any("lightweight_charts" in l for l in import_lines)


# ── CTF ───────────────────────────────────────────────────────────────────────

class TestCTF:
    def test_minutes(self) -> None:
        from trex.indic.CTF import timeframe_to_minutes
        assert timeframe_to_minutes("1m") == 1
        assert timeframe_to_minutes("4H") == 240
        assert timeframe_to_minutes("1D") == 1440

    def test_invalid_hour(self) -> None:
        from trex.indic.CTF import timeframe_to_minutes
        with pytest.raises(ValueError):
            timeframe_to_minutes("7H")

    def test_invalid_format(self) -> None:
        from trex.indic.CTF import timeframe_to_minutes
        with pytest.raises(ValueError):
            timeframe_to_minutes("bad")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
