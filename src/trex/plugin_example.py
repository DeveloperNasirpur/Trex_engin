"""
trex.plugin_example
===================
نمونه کامل ساخت اندیکاتور اختصاصی با سیستم plugin.

این فایل را کپی کنید، تغییر دهید، و از کتابخانه import کنید.
هیچ‌گاه نیازی به تغییر سورس اصلی کتابخانه نیست.
"""

from __future__ import annotations

from collections import deque
from typing import Callable

from trex import plugin
from trex.base.ohlcv import OHLCV, ValueExtractor
from trex.engine.indicator import Indicator


# ─────────────────────────────────────────────────────────────────────────────
# مثال ۱: اندیکاتور ساده (بدون sub-indicator)
# ─────────────────────────────────────────────────────────────────────────────

@plugin.register
class DEMA2(Indicator):
    """
    Double EMA محاسبه‌شده با حافظه داخلی (بدون sub-indicator).

    فرمول:  DEMA = 2×EMA₁ − EMA₂(EMA₁)
    """
    _ind_name   = "DEMA2"
    _key_params = ("period",)

    def __init__(
        self,
        period:          int      = 14,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.period = period
        self._k     = 2.0 / (period + 1.0)
        self._k1    = 1.0 - self._k
        self._ema1: float | None = None
        self._ema2: float | None = None
        self._buf:  list         = []

    def init_depends(self) -> None:
        pass  # اندیکاتور مستقل، sub-indicator ندارد

    def _first_calculate(self, value: float, prev) -> object:
        self._buf.append(value)
        if len(self._buf) < self.period:
            return None
        seed       = sum(self._buf) / self.period
        self._ema1 = seed
        self._ema2 = seed
        self._buf  = None
        return 2.0 * seed - seed   # = seed (اولین مقدار)

    def _calculate_new_value(self, value: float, prev: float) -> float:
        self._ema1 = self._k1 * self._ema1 + self._k * value
        self._ema2 = self._k1 * self._ema2 + self._k * self._ema1
        return 2.0 * self._ema1 - self._ema2

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["ema1"] = self._ema1
            s["ema2"] = self._ema2
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._ema1 = state.get("ema1")
            self._ema2 = state.get("ema2")
            self._buf  = None

    def series_defs(self):
        from trex.presentation.indicators import Overlay
        return [Overlay.dema(self.period, key=self.indicator_key())]


# ─────────────────────────────────────────────────────────────────────────────
# مثال ۲: اندیکاتور مرکب (با sub-indicator)
# ─────────────────────────────────────────────────────────────────────────────

@plugin.register(name="my_macd")
class CustomMACD(Indicator):
    """
    MACD سفارشی — از EMA‌های موجود در context استفاده می‌کند.

    این مثال نشان می‌دهد چگونه یک اندیکاتور به اندیکاتورهای دیگر وابسته می‌شود.
    """
    _ind_name   = "MyMACD"
    _key_params = ("fast", "slow", "signal")

    def __init__(
        self,
        fast:            int      = 12,
        slow:            int      = 26,
        signal:          int      = 9,
        value_extractor: Callable = ValueExtractor.extract_close,
    ) -> None:
        super().__init__(value_extractor=value_extractor)
        self.fast   = fast
        self.slow   = slow
        self.signal = signal
        self._ve    = value_extractor

        self._fast_val: float | None = None
        self._slow_val: float | None = None

        # EMA سیگنال به صورت محلی نگه‌داری می‌شود
        self._sig_k  = 2.0 / (signal + 1.0)
        self._sig_k1 = 1.0 - self._sig_k
        self._sig_buf: list         = []
        self._sig:     float | None = None

        self._fast_key = None
        self._slow_key = None

    def init_depends(self) -> None:
        api = self._ctx.api
        self._fast_key = api.ema(
            self.context_symbol, self.tf, self.fast, self._ve, self._on_fast
        )
        self._slow_key = api.ema(
            self.context_symbol, self.tf, self.slow, self._ve, self._on_slow
        )

    def dispatch(self) -> None:
        api = self._ctx.api
        if self._fast_key:
            api.de_attach_by_key(self._fast_key)
        if self._slow_key:
            api.de_attach_by_key(self._slow_key)

    def _on_fast(self, val: float) -> None:
        self._fast_val = val

    def _on_slow(self, val: float) -> None:
        self._slow_val = val
        if self._fast_val is None:
            return
        macd_line = self._fast_val - self._slow_val
        self._update_signal(macd_line)

    def _update_signal(self, macd: float) -> None:
        if self._sig is None:
            self._sig_buf.append(macd)
            if len(self._sig_buf) < self.signal:
                return
            self._sig = sum(self._sig_buf) / self.signal
            self._sig_buf = None
        else:
            self._sig = self._sig_k1 * self._sig + self._sig_k * macd
        self.emit({
            "macd":      macd,
            "signal":    self._sig,
            "histogram": macd - self._sig,
        })

    def add_input_value(self, raw: object) -> None:
        pass   # sub-EMAها مستقیماً از CTF تغذیه می‌شوند

    def _first_calculate(self, value, prev):
        return True

    def _calculate_new_value(self, value, prev):
        pass

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            s["fast_val"] = self._fast_val
            s["slow_val"] = self._slow_val
            s["sig"]      = self._sig
            s["sig_buf"]  = list(self._sig_buf) if self._sig_buf else []
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            self._fast_val = state.get("fast_val")
            self._slow_val = state.get("slow_val")
            self._sig      = state.get("sig")
            self._sig_buf  = state.get("sig_buf", [])
            if not self._sig_buf:
                self._sig_buf = None


# ─────────────────────────────────────────────────────────────────────────────
# نحوه استفاده پس از import این فایل
# ─────────────────────────────────────────────────────────────────────────────
#
#   import trex
#   import trex.plugin_example   # ← فقط کافی است این فایل import شود
#
#   trex.init(port=8765)
#
#   # اکنون در دسترس است مانند اندیکاتورهای داخلی:
#   trex.dema2("BTCUSDT", "1h", period=21, listener=on_dema2)
#   trex.my_macd("BTCUSDT", "1h", fast=12, slow=26, signal=9, listener=on_macd)
#
#   # و داخل init_depends اندیکاتور دیگری:
#   api = self._ctx.api
#   key = api.dema2(self.context_symbol, self.tf, period=21, listener=self._on_dema2)
