"""
trex.domain.types
=================
Wire-protocol data types for the Trex Terminal WebSocket protocol v3.

These are the canonical Python representations of every struct defined in
the TypeScript ``protocol.ts`` / ``types.ts`` on the terminal side.

Design decisions
----------------
- All types are **immutable** dataclasses (``frozen=True``) so they can be
  cached, hashed, and shared across threads without defensive copying.
- Every type carries a ``to_wire()`` method that serialises to the exact
  JSON shape the terminal expects.
- Every type carries a ``from_dict()`` classmethod for deserialising frames
  arriving from the terminal (client → server direction).
- Validation is performed at construction time via ``__post_init__``, so
  invalid objects can never be created silently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final, Literal

# ── Constants ─────────────────────────────────────────────────────────────────

PROTOCOL_VERSION: Final[str] = "2.0.0"

# ── Literal aliases (match TypeScript union types exactly) ────────────────────

ChartType  = Literal["candles", "heikin", "line", "area", "bars"]
ToastKind  = Literal["info", "success", "warning", "error"]
SeriesKind = Literal["line", "histogram", "area", "baseline", "scatter"]
PaneType   = Literal["main", "sub"]
LabelPos   = Literal["above", "below", "left", "right"]

_HEX_COLOR_RE: Final = re.compile(r"^#[0-9A-Fa-f]{3,8}$|^rgba?\(")

VALID_CHART_TYPES:  Final[frozenset[str]] = frozenset({"candles", "heikin", "line", "area", "bars"})
VALID_TOAST_KINDS:  Final[frozenset[str]] = frozenset({"info", "success", "warning", "error"})
VALID_SERIES_KINDS: Final[frozenset[str]] = frozenset({"line", "histogram", "area", "baseline", "scatter"})
VALID_PANE_TYPES:   Final[frozenset[str]] = frozenset({"main", "sub"})
VALID_LABEL_POS:    Final[frozenset[str]] = frozenset({"above", "below", "left", "right"})


def _require_finite(value: float, name: str) -> None:
    import math
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite, got {value!r}")


def _require_non_negative(value: float, name: str) -> None:
    if value < 0:
        raise ValueError(f"{name} must be >= 0, got {value!r}")


# ── Core market data ──────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Bar:
    """
    One OHLCV bar.

    Parameters
    ----------
    time:
        Unix timestamp in **seconds**.
    open, high, low, close:
        Prices. Must satisfy ``high >= max(open, close)``
        and ``low <= min(open, close)``.
    volume:
        Non-negative trade volume. Defaults to 0.0 (omitted from wire).

    Examples
    --------
    >>> Bar(time=1_700_000_000, open=42000, high=42500, low=41800, close=42300)
    Bar(time=1700000000, open=42000, high=42500, low=41800, close=42300, volume=0.0)
    """

    time:   int
    open:   float
    high:   float
    low:    float
    close:  float
    volume: float = 0.0

    def __post_init__(self) -> None:
        for name, val in (("open", self.open), ("high", self.high),
                          ("low", self.low), ("close", self.close)):
            _require_finite(val, name)
        _require_finite(float(self.time), "time")
        _require_non_negative(self.volume, "volume")
        if self.high < max(self.open, self.close):
            raise ValueError(
                f"high ({self.high}) must be >= max(open, close) "
                f"= {max(self.open, self.close)}"
            )
        if self.low > min(self.open, self.close):
            raise ValueError(
                f"low ({self.low}) must be <= min(open, close) "
                f"= {min(self.open, self.close)}"
            )

    def to_wire(self) -> dict[str, float | int]:
        """Serialise to the JSON wire shape the terminal expects."""
        d: dict[str, float | int] = {
            "time": self.time,
            "open": self.open,
            "high": self.high,
            "low":  self.low,
            "close": self.close,
        }
        if self.volume:
            d["volume"] = self.volume
        return d

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> "Bar":
        """Deserialise from a wire dict. Raises ``ValueError`` on bad data."""
        return cls(
            time=int(d["time"]),      # type: ignore[arg-type]
            open=float(d["open"]),    # type: ignore[arg-type]
            high=float(d["high"]),    # type: ignore[arg-type]
            low=float(d["low"]),      # type: ignore[arg-type]
            close=float(d["close"]),  # type: ignore[arg-type]
            volume=float(d.get("volume", 0)),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class Point:
    """
    One indicator data point.

    Parameters
    ----------
    time:
        Unix timestamp in seconds.
    value:
        The indicator value at this time.
    color:
        Optional per-point color override (server-driven conditional coloring).
        When present, overrides the series' base color for just this point.
        This enables histogram bars tinted by regime, zigzag pivot labels, etc.

    Notes
    -----
    A **single-element list** triggers the O(1) realtime tail-update path in
    the terminal; a longer list replaces the whole series.
    """

    time:  int
    value: float
    color: str | None = None

    def __post_init__(self) -> None:
        _require_finite(float(self.time), "time")
        _require_finite(self.value, "value")

    def to_wire(self) -> dict[str, object]:
        d: dict[str, object] = {"time": self.time, "value": self.value}
        if self.color is not None:
            d["color"] = self.color
        return d

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> "Point":
        return cls(
            time=int(d["time"]),      # type: ignore[arg-type]
            value=float(d["value"]),  # type: ignore[arg-type]
            color=d.get("color") if isinstance(d.get("color"), str) else None,  # type: ignore[arg-type]
        )


# ── Display contracts ─────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class Level:
    """
    A horizontal guide line on a sub-pane (e.g. RSI 70 / 30).

    Parameters
    ----------
    value:
        Y-axis price/value where the line is drawn.
    color:
        Line color (hex or rgba).
    line_style:
        0 solid · 1 dotted · 2 dashed · 3 large-dashed · 4 sparse-dotted.
    label:
        Short text shown at the right edge of the line (e.g. ``"OB"``).
    """

    value:      float
    color:      str   = "#787B86"
    line_style: int   = 2
    label:      str   = ""

    def to_wire(self) -> dict[str, object]:
        return {
            "value":     self.value,
            "color":     self.color,
            "lineStyle": self.line_style,
            "label":     self.label,
        }


@dataclass(frozen=True)
class SeriesDef:
    """
    Display contract for one indicator series.

    Describes **how** to render a series — the matching data arrives separately
    as ``list[Point]`` keyed by ``key`` in ``push_indicators()``.

    The terminal is a pure display client: it never computes indicator values.
    This contract only encodes appearance, scale, and placement.

    Parameters
    ----------
    key:
        Unique identifier. Data is routed to this series by matching this key.
    label:
        Human-readable name shown in the legend.
    pane:
        ``"main"`` overlays the price pane; ``"sub"`` gets its own pane below.
    kind:
        Visual form: ``"line" | "histogram" | "area" | "baseline" | "scatter"``.
    color:
        Primary series color (hex / rgba).
    width:
        Line thickness in pixels (1–4).
    style:
        0 solid · 1 dotted · 2 dashed · 3 large-dashed · 4 sparse-dotted.
    digits:
        Price decimal places for axis + legend formatting.
    pane_id:
        Series sharing a ``pane_id`` render in the same pane (e.g. MACD trio).
        Defaults to ``key`` for main-pane series, ``"pane_{key}"`` for sub-pane.
    pane_height:
        Preferred sub-pane height in pixels (ignored for main-pane series).
    margins:
        Vertical padding of this series' price scale as ``{"top": ..., "bottom": ...}``
        fractions in [0, 1].
    color_pos:
        Histogram / baseline: color for values ≥ 0 / above base.
    color_neg:
        Histogram / baseline: color for values < 0 / below base.
    levels:
        Horizontal guide lines (e.g. RSI 30 / 70).
    base_value:
        Baseline series only: the pivot price that splits top/bottom.
    price_line:
        Show the dashed price line at the last value.
    last_value:
        Show the last value tag on the price axis.
    """

    key:         str
    label:       str
    pane:        PaneType   = "sub"
    kind:        SeriesKind = "line"
    color:       str        = "#2962FF"
    width:       int        = 2
    style:       int        = 0
    digits:      int        = 2
    pane_id:     str | None = None
    pane_height: int        = 120
    margins:     dict[str, float] | None = None
    color_pos:   str | None = None
    color_neg:   str | None = None
    levels:      tuple[Level, ...] = field(default_factory=tuple)
    base_value:  float | None = None
    price_line:  bool       = False
    last_value:  bool       = True

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("SeriesDef.key must not be empty")
        if self.pane not in VALID_PANE_TYPES:
            raise ValueError(f"pane must be one of {VALID_PANE_TYPES}, got {self.pane!r}")
        if self.kind not in VALID_SERIES_KINDS:
            raise ValueError(f"kind must be one of {VALID_SERIES_KINDS}, got {self.kind!r}")
        if not (1 <= self.width <= 4):
            raise ValueError(f"width must be 1–4, got {self.width}")

        # Resolve pane_id default (can't use computed default in frozen dataclass)
        if self.pane_id is None:
            object.__setattr__(
                self, "pane_id",
                self.key if self.pane == "main" else f"pane_{self.key}"
            )
        if self.margins is None:
            object.__setattr__(self, "margins", {"top": 0.1, "bottom": 0.1})

    def to_wire(self) -> dict[str, object]:
        """Serialise to the JSON shape the terminal's ``definitions`` message expects."""
        d: dict[str, object] = {
            "key":              self.key,
            "label":            self.label,
            "pane":             self.pane,
            "paneId":           self.pane_id,
            "type":             self.kind,
            "color":            self.color,
            "lineWidth":        self.width,
            "lineStyle":        self.style,
            "digits":           self.digits,
            "visible":          True,
            "subPaneHeight":    self.pane_height,
            "scaleMargins":     self.margins,
            "priceLineVisible": self.price_line,
            "lastValueVisible": self.last_value,
        }
        if self.color_pos is not None:
            d["colorPos"] = self.color_pos
        if self.color_neg is not None:
            d["colorNeg"] = self.color_neg
        if self.base_value is not None:
            d["baseValue"] = self.base_value
        if self.levels:
            d["levels"] = [lv.to_wire() for lv in self.levels]
        return d


# ── Drawing types ─────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class DrawingPoint:
    """Anchor point in data-coordinates (survives zoom/pan)."""

    time:  int
    price: float

    def to_wire(self) -> dict[str, object]:
        return {"time": self.time, "price": self.price}


@dataclass(frozen=True, slots=True)
class PointLabel:
    """
    Optional label / icon attached to a single pivot point.

    Primarily used with the ``zigzag`` drawing tool — attach a label, an
    emoji icon, or both to each pivot point.

    Parameters
    ----------
    text:
        Short string rendered inside a pill beside the point.
        E.g. ``"H"`` for a swing-high, ``"L"`` for a swing-low.
    icon:
        A single emoji or Unicode symbol rendered before the text.
        E.g. ``"▲"``, ``"▼"``, ``"⚡"``, ``"🔴"``, ``"★"``.
    position:
        Where the pill sits relative to the node dot.
        One of ``"above"`` (default), ``"below"``, ``"left"``, ``"right"``.
    color:
        Override the series color for this label's text and border.
    font_size:
        Override the series font size (pixels) for this label.

    Examples
    --------
    >>> PointLabel(text="H", icon="▲", position="above", color="#089981")
    >>> PointLabel(icon="⚡", text="Buy", color="#FCD535", position="below")
    """

    text:      str | None  = None
    icon:      str | None  = None
    position:  LabelPos    = "above"
    color:     str | None  = None
    font_size: int | None  = None

    def __post_init__(self) -> None:
        if self.position not in VALID_LABEL_POS:
            raise ValueError(f"position must be one of {VALID_LABEL_POS}")

    def to_wire(self) -> dict[str, object]:
        d: dict[str, object] = {"position": self.position}
        if self.text:      d["text"]     = self.text
        if self.icon:      d["icon"]     = self.icon
        if self.color:     d["color"]    = self.color
        if self.font_size: d["fontSize"] = self.font_size
        return d


@dataclass(frozen=True)
class DrawingStyle:
    """Visual style applied to a server-side drawing."""

    color:        str   = "#2962FF"
    width:        int   = 1
    style:        int   = 0
    fill_color:   str   = "#2962FF"
    fill_opacity: float = 0.12
    font_size:    int   = 13
    show_labels:  bool  = True

    def to_wire(self) -> dict[str, object]:
        return {
            "color":        self.color,
            "lineWidth":    self.width,
            "lineStyle":    self.style,
            "fillColor":    self.fill_color,
            "fillOpacity":  self.fill_opacity,
            "fontSize":     self.font_size,
            "showLabels":   self.show_labels,
            "extendLeft":   False,
            "extendRight":  False,
        }


@dataclass(frozen=True)
class Drawing:
    """
    A server-side drawing rendered **read-only** by the terminal.

    Server drawings are owned by the data source and cannot be moved or
    deleted by the user — they behave like indicator overlays.

    Use the ``Zigzag`` / ``ZigzagSeries`` helpers in ``trex.zigzag`` for
    multi-segment lines with per-point labels.

    Parameters
    ----------
    id:
        Stable identifier. Re-sending with the same id replaces the drawing.
    tool:
        One of the terminal's supported drawing tools (e.g. ``"trendline"``,
        ``"horizontal"``, ``"zigzag"``).
    points:
        Anchor points in data-coordinates.
    style:
        Visual style. Defaults to ``DrawingStyle()``.
    text:
        Optional text label (used with the ``"text"`` tool).
    pane_id:
        Which pane to render in. Defaults to ``"main"``.
    locked:
        Prevent user from moving/resizing. Should be ``True`` for server drawings.
    visible:
        Whether the drawing is shown.
    point_labels:
        Per-point labels (sparse — ``None`` = no label at that index).
    """

    id:           str
    tool:         str
    points:       tuple[DrawingPoint, ...]
    style:        DrawingStyle = field(default_factory=DrawingStyle)
    text:         str | None   = None
    pane_id:      str          = "main"
    locked:       bool         = True
    visible:      bool         = True
    point_labels: tuple[PointLabel | None, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Drawing.id must not be empty")
        if not self.tool:
            raise ValueError("Drawing.tool must not be empty")

    def to_wire(self) -> dict[str, object]:
        d: dict[str, object] = {
            "id":        self.id,
            "tool":      self.tool,
            "points":    [p.to_wire() for p in self.points],
            "style":     self.style.to_wire(),
            "paneId":    self.pane_id,
            "locked":    self.locked,
            "visible":   self.visible,
            "completed": True,
            "selected":  False,
            "origin":    "server",
        }
        if self.text is not None:
            d["text"] = self.text
        if self.point_labels:
            d["pointLabels"] = [
                (lbl.to_wire() if lbl is not None else None)
                for lbl in self.point_labels
            ]
        return d


__all__ = [
    "PROTOCOL_VERSION",
    # Literal type aliases
    "ChartType", "ToastKind", "SeriesKind", "PaneType", "LabelPos",
    # Validation sets
    "VALID_CHART_TYPES", "VALID_TOAST_KINDS", "VALID_SERIES_KINDS",
    "VALID_PANE_TYPES", "VALID_LABEL_POS",
    # Market data
    "Bar", "Point",
    # Display contracts
    "Level", "SeriesDef",
    # Drawing types
    "DrawingPoint", "PointLabel", "DrawingStyle", "Drawing",
]
