from __future__ import annotations
from collections import deque
from typing import Callable
from trex.base.ohlcv import ValueExtractor
from trex.engine.indicator import Indicator


class StochRSI(Indicator):
    """Stochastic RSI — RSI's position within its own range."""
    _ind_name   = "STOCHRSI"
    _key_params = ("rsi_period", "stoch_period", "k_period", "d_period")

    def init_depends(self): pass

    def __init__(self, rsi_period: int = 14, stoch_period: int = 14,
                 k_period: int = 3, d_period: int = 3,
                 value_extractor: Callable = ValueExtractor.extract_close):
        super().__init__(value_extractor=value_extractor)
        self.rsi_period = rsi_period; self.stoch_period = stoch_period
        self.k_period = k_period; self.d_period = d_period
        self._pm1 = float(rsi_period - 1); self._pf = float(rsi_period)
        self.avg_gain = self.avg_loss = 0.0
        self._rsi_buf: list = []
        self._rsi_win: deque = deque(maxlen=stoch_period)
        self._rsi_ready = False
        self._k_win: deque = deque(maxlen=k_period)
        self._k_sum = 0.0
        self._d_win: deque = deque(maxlen=d_period)
        self._d_sum = 0.0
        self._count = 0

    def _calc_rsi(self, value: float, prev: float) -> float | None:
        if not self._rsi_ready:
            self._rsi_buf.append(value)
            if len(self._rsi_buf) < self.rsi_period + 1: return None
            gains = losses = 0.0
            for i in range(1, len(self._rsi_buf)):
                d = self._rsi_buf[i] - self._rsi_buf[i - 1]
                if d > 0: gains += d
                else: losses -= d
            self.avg_gain = gains / self._pm1; self.avg_loss = losses / self._pm1
            self._rsi_ready = True; self._rsi_buf = None
        else:
            d = value - prev; g = max(d, 0.0); l = max(-d, 0.0)
            self.avg_gain = (self.avg_gain * self._pm1 + g) / self._pf
            self.avg_loss = (self.avg_loss * self._pm1 + l) / self._pf
        if self.avg_loss == 0: return 100.0
        return 100.0 - 100.0 / (1.0 + self.avg_gain / self.avg_loss)

    def _first_calculate(self, value: float, prev):
        self._count += 1
        rsi = self._calc_rsi(value, prev or value)
        if rsi is None: return None
        self._rsi_win.append(rsi)
        if len(self._rsi_win) < self.stoch_period: return None
        mn = min(self._rsi_win); mx = max(self._rsi_win)
        stoch = (rsi - mn) / (mx - mn) * 100.0 if mx - mn else 50.0
        if len(self._k_win) == self.k_period: self._k_sum -= self._k_win[0]
        self._k_win.append(stoch); self._k_sum += stoch
        if len(self._k_win) < self.k_period: return None
        k = self._k_sum / self.k_period
        if len(self._d_win) == self.d_period: self._d_sum -= self._d_win[0]
        self._d_win.append(k); self._d_sum += k
        if len(self._d_win) < self.d_period: return None
        return k

    def _calculate_new_value(self, value: float, prev) -> float:
        rsi = self._calc_rsi(value, prev)
        self._rsi_win.append(rsi)
        mn = min(self._rsi_win); mx = max(self._rsi_win)
        stoch = (rsi - mn) / (mx - mn) * 100.0 if mx - mn else 50.0
        if len(self._k_win) == self.k_period: self._k_sum -= self._k_win[0]
        self._k_win.append(stoch); self._k_sum += stoch
        k = self._k_sum / self.k_period
        if len(self._d_win) == self.d_period: self._d_sum -= self._d_win[0]
        self._d_win.append(k); self._d_sum += k
        return k

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["avg_gain"] = self.avg_gain; s["avg_loss"] = self.avg_loss
            s["rsi_win"] = list(self._rsi_win)
            s["k_win"] = list(self._k_win); s["k_sum"] = self._k_sum
            s["d_win"] = list(self._d_win); s["d_sum"] = self._d_sum
            s["count"] = self._count; s["rsi_ready"] = self._rsi_ready
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self.avg_gain = state.get("avg_gain", 0.0); self.avg_loss = state.get("avg_loss", 0.0)
            self._rsi_win = deque(state.get("rsi_win", []), maxlen=self.stoch_period)
            self._k_win = deque(state.get("k_win", []), maxlen=self.k_period)
            self._k_sum = state.get("k_sum", 0.0)
            self._d_win = deque(state.get("d_win", []), maxlen=self.d_period)
            self._d_sum = state.get("d_sum", 0.0)
            self._count = state.get("count", 0); self._rsi_ready = state.get("rsi_ready", False)
            if self._rsi_ready: self._rsi_buf = None

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.rsi_period, key=self.indicator_key())]
