"""
trex.zigzag — Zigzag streaming indicator + one-shot drawing builder.

Two distinct use-cases
----------------------

1. **Streaming zigzag** — works exactly like RSI: you push one point at a
   time as your algorithm detects pivots.  The terminal keeps a live line
   series keyed by a stable ``id``; each new pivot appends to that series.

   This is the mode you use when you compute pivots tick-by-tick and want
   to stream them without sending the full history on every update::

       # Once, at connect time — send the definition + history
       zs = ZigzagSeries("zz_main", pane="main", color="#FCD535", width=2)
       await session.define(zs.series_def())
       await session.push_indicators({zs.key: zs.history_points(past_pivots)})

       # Then on every new detected pivot — just the new point
       await session.push_indicators({zs.key: [zs.point(time, price, label)]})

2. **One-shot drawing** — send the complete zigzag as a server drawing.
   Use when your algo runs in batch and you have all pivots upfront::

       zz = (
           Zigzag("wave_count")
           .add(t1, 41500, text="1", icon="▲", position="below")
           .add(t2, 43200, text="2", icon="▼", position="above")
       )
       await session.upsert_drawing(zz.build())

Public API
----------
``ZigzagSeries(id, *, pane, color, width, label_font_size)``
    Streaming zigzag backed by a line series.

    ``.series_def()``         → SeriesDef to pass to ``session.define()``
    ``.point(time, price, label=None)`` → Point to pass to ``push_indicators``
    ``.history_points(pivots)`` → list[Point] for the initial snapshot
    ``.key``                  → the series key string

``Zigzag(id, *, style, pane_id)``
    One-shot fluent builder → ``Drawing``.

    ``.add(time, price, *, text, icon, position, color, font_size)``
    ``.add_point(dp, label=None)``
    ``.build()`` → Drawing
    ``.clear()``

``PointLabel(text, icon, position, color, font_size)``
    Per-point annotation (re-exported here for convenience).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from trex.domain.types import (
    Drawing, DrawingPoint, DrawingStyle,
    Point, PointLabel, SeriesDef, Level,
    LabelPos,
)


# ══════════════════════════════════════════════════════════════════════
# Streaming zigzag  (indicator series, push one pivot at a time)
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ZigzagPivot:
    """One detected pivot — input to ZigzagSeries."""
    time:     int
    price:    float
    label:    Optional[PointLabel] = None


class ZigzagSeries:
    """
    Streaming zigzag backed by a lightweight-charts line series.

    Works identically to RSI from the terminal's perspective:

    - The series is registered once via ``session.define(zs.series_def())``.
    - History is pushed once via ``session.push_indicators({zs.key: zs.history_points(...)})``.
    - Each new pivot is pushed as a single-element list (O(1) tail-update path).

    Per-point labels are encoded in the ``color`` field as a JSON-tagged
    string recognised by the terminal's custom renderer::

        color = "#FCD535|label:{"text":"H","icon":"▲","position":"above"}"

    If you don't need labels, a plain ``color`` hex string is used and the
    series renders as a standard line.

    Parameters
    ----------
    id :
        Stable identifier — used as the series key AND as the pane id.
        Must be unique across all series on the chart.
    pane :
        ``"main"`` to overlay on the price chart or ``"sub"`` for its own pane.
    color :
        Default line colour (hex).
    width :
        Line width in pixels (1–4).
    label_font_size :
        Font size for label pills in pixels.
    pane_height :
        Sub-pane height in pixels (ignored when pane="main").

    Usage::

        zs = ZigzagSeries("zz_pivots", pane="main", color="#FCD535", width=2)

        # On connect:
        await session.define(zs.series_def())
        await session.push_indicators({zs.key: zs.history_points(past_pivots)})

        # On each new pivot detected:
        pivot = ZigzagPivot(bar.time, bar.high,
                            PointLabel(text="H", icon="▲", color="#089981"))
        await session.push_indicators({zs.key: [zs.point_from(pivot)]})
    """

    def __init__(
        self,
        id: str,
        *,
        pane:            str   = "main",
        color:           str   = "#FCD535",
        width:           int   = 2,
        label_font_size: int   = 12,
        pane_height:     int   = 120,
    ) -> None:
        if pane not in ("main", "sub"):
            raise ValueError("pane must be 'main' or 'sub'")
        self.key             = id
        self._pane           = pane
        self._color          = color
        self._width          = width
        self._label_font_size= label_font_size
        self._pane_height    = pane_height

    # ── public helpers ────────────────────────────────────────────────

    def series_def(self) -> SeriesDef:
        """
        Return the SeriesDef to register with ``session.define()``.

        Call this once at connect time, before pushing any points.
        """
        return SeriesDef(
            key=self.key,
            label=f"ZigZag ({self.key})",
            pane=self._pane,            # type: ignore[arg-type]
            kind="line",
            color=self._color,
            width=self._width,
            style=0,
            digits=2,
            pane_id=self.key if self._pane == "main" else f"pane_{self.key}",
            pane_height=self._pane_height,
            price_line=False,
            last_value=False,
        )

    def point(
        self,
        time:  int,
        price: float,
        label: Optional[PointLabel] = None,
    ) -> Point:
        """
        Build one ``Point`` for a pivot.

        Pass the result in a single-element list to trigger the O(1)
        tail-update path::

            await session.push_indicators({zs.key: [zs.point(t, p, lbl)]})

        Parameters
        ----------
        time :
            Unix timestamp in seconds.
        price :
            Price level.
        label :
            Optional ``PointLabel``.  The label is packed into the
            ``color`` field as a tagged JSON string so it survives the
            standard indicator wire format without protocol changes.
        """
        return Point(
            time=time,
            value=price,
            color=self._encode_color(label),
        )

    def point_from(self, pivot: ZigzagPivot) -> Point:
        """Convenience wrapper — build a Point from a ``ZigzagPivot``."""
        return self.point(pivot.time, pivot.price, pivot.label)

    def history_points(
        self,
        pivots: list[ZigzagPivot],
    ) -> list[Point]:
        """
        Convert a list of past pivots to ``list[Point]`` for the initial
        snapshot push.

        Usage::

            past = [
                ZigzagPivot(t1, 41500, PointLabel(text="L", icon="▼")),
                ZigzagPivot(t2, 43200, PointLabel(text="H", icon="▲")),
            ]
            await session.push_indicators({zs.key: zs.history_points(past)})
        """
        return [self.point_from(p) for p in pivots]

    # ── internal ──────────────────────────────────────────────────────

    def _encode_color(self, label: Optional[PointLabel]) -> str:
        """
        Pack label metadata into the color field.

        Format: ``"#RRGGBB|zz:{ ...json... }"``

        The terminal's custom renderer decodes this prefix and draws the
        pill; the raw hex is used as the dot / line colour so the series
        still looks correct even in clients that ignore the tag.
        """
        if label is None:
            return self._color
        lbl_color = label.color or self._color
        meta = {"pos": label.position}
        if label.text:      meta["text"] = label.text
        if label.icon:      meta["icon"] = label.icon
        if label.font_size: meta["fs"]   = label.font_size
        return f"{lbl_color}|zz:{json.dumps(meta, separators=(',', ':'), ensure_ascii=False)}"


# ══════════════════════════════════════════════════════════════════════
# One-shot drawing builder  (send complete zigzag as a Drawing)
# ══════════════════════════════════════════════════════════════════════

class Zigzag:
    """
    Fluent builder for a complete zigzag sent as a server-side Drawing.

    Use when you have **all pivots upfront** and want to replace / refresh
    the whole shape in one call::

        zz = (
            Zigzag("elliott_waves", style=DrawingStyle(color="#FCD535", width=2))
            .add(t1, 41500, text="1", icon="▲", position="below", color="#089981")
            .add(t2, 43200, text="2", icon="▼", position="above", color="#F23645")
            .add(t3, 42100, text="3", icon="▲", position="below", color="#089981")
        )
        await session.upsert_drawing(zz.build())

    For live pivot-by-pivot streaming use ``ZigzagSeries`` instead.
    """

    def __init__(
        self,
        id: str,
        *,
        style:   Optional[DrawingStyle] = None,
        pane_id: str  = "main",
        locked:  bool = True,
        visible: bool = True,
    ) -> None:
        self._id      = id
        self._style   = style or DrawingStyle(color="#FCD535", width=2)
        self._pane_id = pane_id
        self._locked  = locked
        self._visible = visible
        self._points: list[DrawingPoint]         = []
        self._labels: list[Optional[PointLabel]] = []

    # ── add methods ───────────────────────────────────────────────────

    def add(
        self,
        time:      int,
        price:     float,
        *,
        text:      Optional[str] = None,
        icon:      Optional[str] = None,
        position:  LabelPos      = "above",
        color:     Optional[str] = None,
        font_size: Optional[int] = None,
    ) -> "Zigzag":
        """
        Append one pivot point. Returns ``self`` for chaining.

        Parameters
        ----------
        time : int
            Unix timestamp in seconds.
        price : float
            Price level.
        text : str, optional
            Label text inside the pill (e.g. ``"H"``, ``"Wave 3"``).
        icon : str, optional
            Emoji / symbol before the text (e.g. ``"▲"``, ``"⚡"``).
        position : "above" | "below" | "left" | "right"
            Pill placement relative to the node dot.  Default ``"above"``.
        color : str, optional
            Override colour for this label's text and border.
        font_size : int, optional
            Override font size in pixels for this label.
        """
        self._points.append(DrawingPoint(time=time, price=price))
        if text or icon:
            self._labels.append(PointLabel(
                text=text, icon=icon, position=position,
                color=color, font_size=font_size,
            ))
        else:
            self._labels.append(None)
        return self

    def add_point(
        self,
        point: DrawingPoint,
        label: Optional[PointLabel] = None,
    ) -> "Zigzag":
        """Append a pre-built ``DrawingPoint`` with an optional ``PointLabel``."""
        self._points.append(point)
        self._labels.append(label)
        return self

    def clear(self) -> "Zigzag":
        """Remove all points (keeps id, style, and settings)."""
        self._points.clear()
        self._labels.clear()
        return self

    def build(self) -> Drawing:
        """Return a ``Drawing`` ready to send via ``session.upsert_drawing()``."""
        return Drawing(
            id=self._id,
            tool="zigzag",
            points=list(self._points),
            style=self._style,
            pane_id=self._pane_id,
            locked=self._locked,
            visible=self._visible,
            point_labels=list(self._labels),
        )

    def __len__(self)  -> int:  return len(self._points)
    def __repr__(self) -> str:  return f"Zigzag(id={self._id!r}, points={len(self._points)})"
