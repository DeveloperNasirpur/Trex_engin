from __future__ import annotations
"""ZigZag indicator based on price-channel breaks."""

import enum
from dataclasses import dataclass
from typing import Callable

from trex.base import OHLCV
from trex.engine.indicator import Indicator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class StateBreak(str, enum.Enum):
    BREAK = "BREAK"
    RETURN = "RETURN"
    WITH = "WITH"


class ChanelModel(str, enum.Enum):
    UP = "UP"
    DOWN = "DOWN"


class PointModel(str, enum.Enum):
    LL = "LL"
    HL = "HL"
    LH = "LH"
    HH = "HH"
    L = "L"
    H = "H"


class MoveModel(enum.Enum):
    RALLY = "RALLY"
    DROP = "DROP"
    BASE = "BASE"
    BIG_BASE = "BIG_BASE"


# ---------------------------------------------------------------------------
# Data-classes
# ---------------------------------------------------------------------------
@dataclass
class ZigZagVal:
    point_model: Optional[PointModel] = None
    candle: OHLCV | None = None
    candle_break: OHLCV | None = None
    shadow: OHLCV | None = None

@dataclass
class Chanel:
    model: ChanelModel = ChanelModel.UP
    candle: OHLCV | None = None
    perv_body: float = 0.0
    is_break: Callable | None = None
    accept_break: Callable | None = None
    after_break: Callable | None = None

@dataclass
class BaseChanel:
    chanel: Optional[Chanel] = None
    right_cnl: list[OHLCV] | None = None

@dataclass
class ConfigBreak:
    candle: OHLCV | None = None
    chanel_break: bool = False
    body_break: bool = False
    break_by_first_candle: bool = False
    break_by_first_body: bool = False
    count_candle_break: int = 0
    count_after_break: int = 0
    time_break: float = 0.0
    lst_candles: list[OHLCV] = None
    cal_process: Callable | None = None

    def __post_init__(self):
        if self.lst_candles is None:
            self.lst_candles = []

# ---------------------------------------------------------------------------
# ZigZagBase
# ---------------------------------------------------------------------------
class ZigZagBase(Indicator):
    """
    Channel-break ZigZag.

    Emits ``ZigZagVal`` each time the market breaks out of its current
    up/down channel, tagging the pivot with a ``PointModel`` label.
    """

    def payload_extract(self, ohlcv: OHLCV):
        pass

    def on_view(self):
        pass

    def provide_view(self):
        pass

    def init_depends(self) -> None:
        pass

    def dispatch(self) -> None:
        pass

    def reset_another_indicator(self) -> None:
        self._clear_state()

    def __init__(
        self,
        min_accept_size: float = 0.0,
    ) -> None:
        super().__init__(save_input=True, max_input=200)
        self.min_accept_size = min_accept_size

        self._new_ch: Optional[Chanel] = None
        self._last_ch: Optional[Chanel] = None
        self._new_base_ch: Optional[BaseChanel] = None
        self._last_base_ch: Optional[BaseChanel] = None

        self._conf: ConfigBreak = ConfigBreak(
            chanel_break=False,
            body_break=False,
            break_by_first_body=False,
            count_candle_break=0,
            cal_process= self._cal_before_break,
            time_break= 0,
            count_after_break=0,
            break_by_first_candle=False,
            lst_candles=[],
            candle=None,
        )
        self._process_zig: Callable = self._first_siz

        self._ch_up = Chanel(
            model=ChanelModel.UP,
            is_break=self._scan_break_up,
            accept_break=self._accept_break_up,
            after_break=self._scan_after_break_up,
        )
        self._ch_down = Chanel(
            model=ChanelModel.DOWN,
            is_break=self._scan_break_down,
            accept_break=self._accept_break_down,
            after_break=self._scan_after_break_down,
        )

    # ------------------------------------------------------------------
    # Indicator protocol
    # ------------------------------------------------------------------
    def _first_calculate(self, value: OHLCV, perv_value: OHLCV) -> object:
        if not self._valid(value) or perv_value is None:
            return False

        if self._new_ch is None:
            if perv_value.side == 1 and value.side == 1 and value.close > perv_value.close:
                self._conf.lst_candles = [perv_value, value]
                self._set_channel_up(value)
                self._last_ch = self._new_ch

            elif perv_value.side == 0 and value.side == 0 and value.close < perv_value.close:
                self._conf.lst_candles = [perv_value, value]
                self._set_channel_down(value)
                self._last_ch = self._new_ch
        else:
            if self._conf.cal_process(value):
                self._process_zig = self._scan_zigzag
                if len(self.output_values) >= 2:
                    return True
        return False

    def _calculate_new_value(self, value: OHLCV, perv_value: OHLCV) -> None:
        self._conf.lst_candles.append(value)
        if self._valid(value):
            self._conf.cal_process(value)

    # ------------------------------------------------------------------
    # Channel management
    # ------------------------------------------------------------------
    def _set_channel_up(self, candle: OHLCV) -> None:
        self._ch_up.candle = candle
        self._ch_up.perv_body = self._perv_body_up(candle)
        self._ch_up.after_break = self._scan_after_break_up
        self._new_ch = self._ch_up

    def _set_channel_down(self, candle: OHLCV) -> None:
        self._ch_down.candle = candle
        self._ch_down.perv_body = self._perv_body_down(candle)
        self._ch_down.after_break = self._scan_after_break_down
        self._new_ch = self._ch_down

    def _scan_channel(self, candle: OHLCV) -> None:
        close = self._new_ch.candle.close
        open_ = self._new_ch.candle.open

        if self._new_ch.model == ChanelModel.UP:
            if candle.close > close and candle.side == 1:
                self._last_ch = self._new_ch
                self._set_channel_up(candle)
            elif open_ <= candle.close <= close:
                self._update_base_ch()
        else:
            if candle.close < close and candle.side == 0:
                self._last_ch = self._new_ch
                self._set_channel_down(candle)
            elif open_ >= candle.close >= close:
                self._update_base_ch_down(candle)

    def _update_base_ch(self) -> None:
        if self._new_base_ch is None:
            self._new_base_ch = BaseChanel(chanel=self._new_ch)
        elif self._new_base_ch.chanel.candle.time != self._new_ch.candle.time:
            self._last_base_ch = self._new_base_ch
            self._new_base_ch = BaseChanel(chanel=self._new_ch)

    def _update_base_ch_down(self, candle: OHLCV) -> None:
        if self._new_base_ch is None:
            self._new_base_ch = BaseChanel(chanel=self._new_ch, right_cnl=[candle])
        elif self._new_base_ch.chanel.candle.time != self._new_ch.candle.time:
            self._last_base_ch = self._new_base_ch
            self._new_base_ch = BaseChanel(chanel=self._new_ch, right_cnl=[candle])

    # ------------------------------------------------------------------
    # Break detection
    # ------------------------------------------------------------------
    def _cal_before_break(self, value: OHLCV) -> bool:
        self._scan_channel(value)
        self._new_ch.is_break(value)
        return False

    def _cal_after_break(self, value: OHLCV) -> bool:
        res = self._new_ch.accept_break(value)

        if res == StateBreak.BREAK:
            self._new_ch.after_break(value)
            result = self._process_zig(value)
            if result:
                self.emit(result)
            self._conf = ConfigBreak(
                lst_candles=[self.prev_value, value],
                cal_process=self._cal_before_break,
            )
            return True

        if res == StateBreak.RETURN:
            self._scan_channel(value)
            self._conf = ConfigBreak(
                lst_candles=[self.prev_value, value],
                cal_process=self._cal_before_break,
            )
        return False

    def _scan_break_up(self, value: OHLCV) -> None:
        if value.close < self._new_ch.candle.open:
            self._conf.cal_process = self._cal_after_break
        body_break = value.close < self._new_ch.perv_body
        self._conf.body_break = body_break
        self._conf.break_by_first_body = body_break
        if self._conf.candle is None and body_break:
            self._conf.candle = value
            self._conf.time_break = value.time.timestamp()
            self._conf.cal_process = self._cal_after_break

    def _scan_break_down(self, value: OHLCV) -> None:
        if value.close > self._new_ch.candle.open:
            self._conf.cal_process = self._cal_after_break
        body_break = value.close > self._new_ch.perv_body
        self._conf.body_break = body_break
        self._conf.break_by_first_body = body_break
        if self._conf.candle is None and body_break:
            self._conf.candle = value
            self._conf.time_break = value.time.timestamp()
            self._conf.cal_process = self._cal_after_break

    # ------------------------------------------------------------------
    # Accept-break logic
    # ------------------------------------------------------------------
    def _accept_break_up(self, candle: OHLCV) -> StateBreak:
        if candle.side == 0:  # bearish
            if self._conf.break_by_first_candle and candle.close < self._conf.candle.close:
                return StateBreak.BREAK
            if not self._conf.break_by_first_candle and candle.close < self._new_ch.perv_body:
                return StateBreak.BREAK
            if candle.close > self._new_ch.perv_body:
                return StateBreak.WITH
        else:  # bullish
            if self._new_ch.perv_body < candle.close < self._new_ch.candle.open:
                return StateBreak.WITH
            if candle.close > self._new_ch.candle.open or candle.close > self._new_ch.candle.close:
                return StateBreak.RETURN
        return StateBreak.WITH

    def _accept_break_down(self, candle: OHLCV) -> StateBreak:
        if candle.side == 1:  # bullish
            if self._conf.break_by_first_candle and candle.close > self._conf.candle.close:
                return StateBreak.BREAK
            if not self._conf.break_by_first_candle and candle.close > self._new_ch.perv_body:
                return StateBreak.BREAK
            if candle.close < self._new_ch.perv_body:
                return StateBreak.WITH
        else:  # bearish
            if self._new_ch.perv_body > candle.close > self._new_ch.candle.open:
                return StateBreak.WITH
            if candle.close < self._new_ch.candle.open or candle.close < self._new_ch.candle.close:
                return StateBreak.RETURN
        return StateBreak.WITH

    # ------------------------------------------------------------------
    # After-break pivot search
    # ------------------------------------------------------------------
    def _scan_after_break_up(self, candle: OHLCV) -> None:
        self._clear_state()
        ch = Chanel(
            model=ChanelModel.DOWN,
            candle=self._conf.lst_candles[0],
            is_break=self._scan_break_down,
            accept_break=self._accept_break_down,
            after_break=self._scan_after_break_down,
        )
        for cnl in self._conf.lst_candles:
            if cnl.close < ch.candle.close:
                self._last_ch = ch
                ch.candle = cnl
            elif ch.candle.open > cnl.close > ch.candle.close:
                self._last_base_ch = self._new_base_ch
                self._new_base_ch = BaseChanel(chanel=ch, right_cnl=[cnl])
        ch.perv_body = self._perv_body_down(candle)
        self._new_ch = ch

    def _scan_after_break_down(self, candle: OHLCV) -> None:
        self._clear_state()
        ch = Chanel(
            model=ChanelModel.UP,
            candle=self._conf.lst_candles[0],
            is_break=self._scan_break_up,
            accept_break=self._accept_break_up,
            after_break=self._scan_after_break_up,
        )
        for cnl in self._conf.lst_candles:
            if cnl.close > ch.candle.close:
                self._last_ch = ch
                ch.candle = cnl
            elif ch.candle.open < cnl.close < ch.candle.close:
                self._last_base_ch = self._new_base_ch
                self._new_base_ch = BaseChanel(chanel=ch, right_cnl=[cnl])
        ch.perv_body = self._perv_body_up(candle)
        self._new_ch = ch

    # ------------------------------------------------------------------
    # ZigZag point creation
    # ------------------------------------------------------------------
    def _first_siz(self, candle: OHLCV) -> ZigZagVal:
        zig = ZigZagVal(candle_break=candle)
        if self._new_ch.model == ChanelModel.DOWN:
            zig.point_model = PointModel.L
            for cnl in reversed(self.input_values):
                if cnl.side == 0 or cnl.close == cnl.open:
                    if zig.candle is None:
                        zig.candle = cnl
                    elif cnl.close < zig.candle.close:
                        zig.candle = cnl
        else:
            zig.point_model = PointModel.H
            for cnl in reversed(self.input_values):
                if cnl.side == 1 or cnl.close == cnl.open:
                    if zig.candle is None:
                        zig.candle = cnl
                    elif cnl.close > zig.candle.close:
                        zig.candle = cnl
        return zig

    def _scan_zigzag(self, candle: OHLCV) -> ZigZagVal:
        zig = ZigZagVal(candle_break=candle)
        last_point: ZigZagVal = self.output_values[-2]

        if self._new_ch.model == ChanelModel.UP:
            for cnl in reversed(self._conf.lst_candles):
                if last_point.candle and last_point.candle.time.timestamp() == cnl.time.timestamp():
                    break
                if zig.shadow is None or cnl.low < zig.shadow.low:
                    zig.shadow = cnl
                if cnl.side == 0 or cnl.close == cnl.open:
                    if zig.candle is None:
                        zig.candle = cnl
                    elif cnl.close < zig.candle.close:
                        zig.candle = cnl

            zig.point_model = (
                PointModel.LL if last_point.candle.open > zig.candle.close else PointModel.LH
            )
        else:
            for cnl in reversed(self._conf.lst_candles):
                if last_point.candle and last_point.candle.time.timestamp() == cnl.time.timestamp():
                    break
                if zig.shadow is None or cnl.high > zig.shadow.high:
                    zig.shadow = cnl
                if cnl.side == 1 or cnl.close == cnl.open:
                    if zig.candle is None:
                        zig.candle = cnl
                    elif cnl.close > zig.candle.close:
                        zig.candle = cnl

            zig.point_model = (
                PointModel.HH if last_point.candle.open > zig.candle.close else PointModel.HL
            )
        return zig

    # ------------------------------------------------------------------
    # Body-reference search helpers
    # ------------------------------------------------------------------
    def _perv_body_up(self, candle: OHLCV) -> float:
        ts = candle.time.timestamp()
        for cnl in reversed(self._conf.lst_candles):
            if cnl.side == 0:
                continue
            if cnl.open < candle.open:
                return self._maybe_base_open(cnl, ts)
        return candle.open

    def _perv_body_down(self, candle: OHLCV) -> float:
        ts = candle.time.timestamp()
        for cnl in reversed(self._conf.lst_candles):
            if cnl.side == 1:
                continue
            if cnl.open > candle.open:
                return self._maybe_base_open(cnl, ts)
        return candle.open

    def _maybe_base_open(self, cnl: OHLCV, ts: float) -> float:
        base = self._new_base_ch or self._last_base_ch
        if base and base.chanel.candle.time.timestamp() != ts:
            bc = base.chanel.candle
            if bc.open < cnl.open < bc.close:
                return bc.open
        return cnl.open

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _valid(self, candle: OHLCV) -> bool:
        return abs(candle.open - candle.close) > self.min_accept_size

    def _clear_state(self) -> None:
        self._new_ch = None
        self._last_ch = None
        self._new_base_ch = None
        self._last_base_ch = None

    def series_defs(self):
        from trex.domain.types import SeriesDef
        return [SeriesDef(
            key="zigzag",
            label="ZigZag",
            pane="main",
            kind="line",
            color="#FF9800",
            width=2,
            pane_id="zigzag",
        )]

    def _make_points(self, value, timestamp):
        from trex.domain.types import Point
        # ZigZagVal — از candle_break یا shadow برای price استفاده کن
        if value is None:
            return {}
        price = None
        if value.shadow is not None:
            price = value.shadow.high if hasattr(value.shadow, 'high') else None
        elif value.candle_break is not None:
            price = value.candle_break.close if hasattr(value.candle_break, 'close') else None
        if price is None:
            return {}
        return {"zigzag": [Point(time=timestamp, value=price)]}
