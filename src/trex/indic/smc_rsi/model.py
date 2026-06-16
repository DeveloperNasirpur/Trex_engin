from __future__ import annotations
"""Data-types used by the SMC-RSI indicator family."""

from dataclasses import dataclass
from enum import Enum

from trex.base.ohlcv import OHLCV


class Side(str, Enum):
    UP = "UP"
    DOWN = "DOWN"



@dataclass
class SwingData:
    body: OHLCV|None = None
    shadow: OHLCV|None = None
    rsi: float | None = None
    rsi_ohlcv: OHLCV | None = None


@dataclass
class ExVal:
    side: str = Side.DOWN.value
    swing_higher: SwingData | None = None
    swing_lower: SwingData | None = None
    trend_id:int = 0

    # ------------------------------------------------------------------
    # Mutating helpers (operate *in-place* on *ex* and return it)
    # ------------------------------------------------------------------
    @staticmethod
    def update_higher(ex: "ExVal", val: SwingData) -> "ExVal":
        h = ex.swing_higher
        if val.rsi is not None and (h.rsi is None or val.rsi > h.rsi):
            h.rsi = val.rsi
        if val.shadow.high > h.shadow.high:
            h.shadow = val.shadow
        if val.body.close > h.body.close:
            h.body = val.body
        if val.rsi_ohlcv and (
                h.rsi_ohlcv is None or
                val.rsi_ohlcv.high > h.rsi_ohlcv.high):
            h.rsi_ohlcv = val.rsi_ohlcv
        return ex

    @staticmethod
    def update_lower(ex: "ExVal", val: SwingData) -> "ExVal":
        lo = ex.swing_lower
        if val.rsi is not None and (lo.rsi is None or val.rsi < lo.rsi):
            lo.rsi = val.rsi
        if val.shadow.low < lo.shadow.low:
            lo.shadow = val.shadow
        if val.body.low < lo.body.low:
            lo.body = val.body
        if val.rsi_ohlcv and (lo.rsi_ohlcv is None or val.rsi_ohlcv.low < lo.rsi_ohlcv.low):
            lo.rsi_ohlcv = val.rsi_ohlcv
        return ex

    @staticmethod
    def update_swing_ohlcv(ex: "ExVal", ohlcv: OHLCV) -> None:

        if ohlcv.high > ex.swing_higher.shadow.high:
            ex.swing_higher.shadow = ohlcv

        if ohlcv.close > ex.swing_higher.body.close:
            ex.swing_higher.body = ohlcv

        if ohlcv.low < ex.swing_lower.shadow.low:
            ex.swing_lower.shadow = ohlcv

        if ohlcv.close < ex.swing_lower.body.close:
            ex.swing_lower.body = ohlcv

    @staticmethod
    def cross_up(baseline: "ExVal", candidate: "ExVal") -> bool:
        return candidate.swing_higher.rsi > baseline.swing_higher.rsi

    @staticmethod
    def cross_down(baseline: "ExVal", candidate: "ExVal") -> bool:
        return candidate.swing_lower.rsi < baseline.swing_lower.rsi


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------
class EventType(str, Enum):
    FIRST = "FIRST"
    CHOCK = "CHOCK"
    BOS = "BOS"
    HUNT = "HUNT"
    MINOR_CHOCK = "MINOR_CHOCK"
    MINOR_BOS = "MINOR_BOS"
    MINOR_HUNT = "MINOR_HUNT"


class EventAction(str, Enum):
    PULLBACK = "PULLBACK"
    SAME_DIRECTION = "SAME_DIRECTION"
    MINOR_PULLBACK = "MINOR_PULLBACK"
    MINOR_SAME_DIRECTION = "MINOR_SAME_DIRECTION"
    FIRST_EVENT = "FIRST_EVENT"


@dataclass
class EventVal:
    type: str = EventType.BOS.value
    side: str = Side.DOWN.value
    ex: ExVal | None = None


# ---------------------------------------------------------------------------
# Transition tables
# ---------------------------------------------------------------------------
_CHOCK_BOS: dict[str, str] = {
    EventAction.PULLBACK.value: EventType.HUNT.value,
    EventAction.SAME_DIRECTION.value: EventType.BOS.value,
    EventAction.MINOR_PULLBACK.value: EventType.MINOR_HUNT.value,
    EventAction.MINOR_SAME_DIRECTION.value: EventType.MINOR_BOS.value,
}

POSSIBILITY: dict[str, dict[str, str]] = {
    EventType.BOS.value: _CHOCK_BOS,
    EventType.CHOCK.value: _CHOCK_BOS,
    EventType.HUNT.value: {
        EventAction.PULLBACK.value: EventType.BOS.value,
        EventAction.SAME_DIRECTION.value: EventType.CHOCK.value,
        EventAction.MINOR_PULLBACK.value: EventType.MINOR_BOS.value,
        EventAction.MINOR_SAME_DIRECTION.value: EventType.MINOR_CHOCK.value,
    },
    EventType.MINOR_BOS.value: _CHOCK_BOS,
    EventType.MINOR_CHOCK.value: _CHOCK_BOS,
    EventType.MINOR_HUNT.value: {
        EventAction.PULLBACK.value: EventType.BOS.value,
        EventAction.SAME_DIRECTION.value: EventType.CHOCK.value,
        EventAction.MINOR_PULLBACK.value: EventType.MINOR_BOS.value,
        EventAction.MINOR_SAME_DIRECTION.value: EventType.MINOR_CHOCK.value,
    },
}

NEXT_ACTION: dict[str, str] = {
    EventAction.FIRST_EVENT.value: EventAction.PULLBACK.value,
    EventAction.PULLBACK.value: EventAction.SAME_DIRECTION.value,
    EventAction.SAME_DIRECTION.value: EventAction.MINOR_PULLBACK.value,
    EventAction.MINOR_PULLBACK.value: EventAction.MINOR_SAME_DIRECTION.value,
    EventAction.MINOR_SAME_DIRECTION.value: EventAction.MINOR_PULLBACK.value,
}



class ZoneState(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    CHANGE = "CHANGE"
    EXPIRE = "EXPIRE"

class ZoneType(str, Enum):
    RESISTANCE = "RESISTANCE"
    SUPPORT = "SUPPORT"
    MINOR_RESISTANCE = "MINOR_RESISTANCE"
    MINOR_SUPPORT = "MINOR_SUPPORT"

@dataclass
class ZoneVal:
    type: str = ZoneType.RESISTANCE.value
    state: ZoneState = ZoneState.CREATED.value
    swing: OHLCV|None = None
    create:OHLCV|None = None
    id_trend:int = 0
    in_zone:OHLCV|None = None
    out_zone:OHLCV|None = None

