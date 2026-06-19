from __future__ import annotations
from collections import deque
from trex.base.ohlcv import OHLCV
from trex.engine.indicator import Indicator


class UO(Indicator):
    """Ultimate Oscillator — weighted average of buying pressure."""
    _ind_name   = "UO"
    _key_params = ("period1", "period2", "period3")

    def init_depends(self): pass

    def __init__(self, period1: int = 7, period2: int = 14, period3: int = 28):
        super().__init__(value_extractor=None)
        self.period1 = period1; self.period2 = period2; self.period3 = period3
        self._bp1: deque = deque(maxlen=period1); self._tr1: deque = deque(maxlen=period1)
        self._bp2: deque = deque(maxlen=period2); self._tr2: deque = deque(maxlen=period2)
        self._bp3: deque = deque(maxlen=period3); self._tr3: deque = deque(maxlen=period3)
        self._sbp1 = self._str1 = self._sbp2 = self._str2 = self._sbp3 = self._str3 = 0.0
        self._prev_close = None; self._count = 0

    def add_input_value(self, raw) -> None:
        if not isinstance(raw, OHLCV): return
        self._last_raw = raw; self._count += 1
        if self._prev_close is None: self._prev_close = raw.close; return
        pc = self._prev_close
        bp = raw.close - min(raw.low, pc)
        tr = max(raw.high, pc) - min(raw.low, pc)
        for win_bp, win_tr, sb, st in [
            (self._bp1, self._tr1, '_sbp1', '_str1'),
            (self._bp2, self._tr2, '_sbp2', '_str2'),
            (self._bp3, self._tr3, '_sbp3', '_str3'),
        ]:
            if len(win_bp) == win_bp.maxlen:
                setattr(self, sb, getattr(self, sb) - win_bp[0])
                setattr(self, st, getattr(self, st) - win_tr[0])
            win_bp.append(bp); win_tr.append(tr)
            setattr(self, sb, getattr(self, sb) + bp)
            setattr(self, st, getattr(self, st) + tr)
        self._prev_close = raw.close
        if self._count < self.period3 + 1: return
        a = self._sbp1 / self._str1 if self._str1 else 0
        b = self._sbp2 / self._str2 if self._str2 else 0
        c = self._sbp3 / self._str3 if self._str3 else 0
        self._pipe.emit(100.0 * (4 * a + 2 * b + c) / 7.0)

    def _first_calculate(self, v, prev): return None
    def _calculate_new_value(self, v, prev): return None

    def get_state(self) -> dict:
        s = super().get_state()
        if s:
            for nm in ['bp1', 'tr1', 'bp2', 'tr2', 'bp3', 'tr3']:
                s[nm] = list(getattr(self, f'_{nm}'))
            for nm in ['sbp1', 'str1', 'sbp2', 'str2', 'sbp3', 'str3']:
                s[nm] = getattr(self, f'_{nm}')
            s["prev_close"] = self._prev_close; s["count"] = self._count
        return s

    def set_state(self, state: dict) -> None:
        super().set_state(state)
        if state:
            ps = [self.period1, self.period1, self.period2, self.period2, self.period3, self.period3]
            for nm, p in zip(['bp1', 'tr1', 'bp2', 'tr2', 'bp3', 'tr3'], ps):
                setattr(self, f'_{nm}', deque(state.get(nm, []), maxlen=p))
            for nm in ['sbp1', 'str1', 'sbp2', 'str2', 'sbp3', 'str3']:
                setattr(self, f'_{nm}', state.get(nm, 0.0))
            self._prev_close = state.get("prev_close"); self._count = state.get("count", 0)

    def series_defs(self):
        from trex.presentation.indicators import Oscillator
        return [Oscillator.rsi(self.period3, key=self.indicator_key())]
