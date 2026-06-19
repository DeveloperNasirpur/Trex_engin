"""
trex.engine.indicator
=====================
Abstract base class برای همه streaming indicators.

تغییرات نسبت به نسخه قدیمی
-----------------------------
- حذف کامل وابستگی ``lightweight_charts`` از engine
- حذف ``on_view``, ``provide_view``, ``payload_extract`` (abstract های مرده)
- ``Optional[X]`` → ``X | None``
- ``List``, ``Dict`` → ``list``, ``dict``
- ``view: Chart = None`` پارامتر حذف شد
- ``dash_key`` / ``dash_mapping`` حذف شدند (به لایه presentation تعلق دارند)
- ``SeriesMixin`` اضافه شد: هر indicator می‌تواند series اعلام کند و emit بزند

Subclasses MUST implement
--------------------------
``init_depends()``          — wire sub-indicators using ``api`` inside here.
``series_defs()``           — اعلام کن چه series هایی روی terminal نمایش داده شود.
``_first_calculate()``      — boot phase; return None/False to wait, True to advance.
``_calculate_new_value()``  — run phase; return value to emit, or None to skip.

Subclasses MAY override
------------------------
``dispatch()``              — teardown: unsubscribe from sub-indicator callbacks.
``_make_points()``          — convert emitted value to {series_key: [Point]}.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from trex.base.ohlcv import OHLCV
from trex.base.timeframe import Timeframe
from trex.engine.pipeline import Pipeline, PipelineHost
from trex.presentation.series_mixin import SeriesMixin

# Union type accepted by add_input_value
ValueType = OHLCV | float


class Indicator(SeriesMixin, PipelineHost, ABC):
    """
    Streaming indicator base.

    Design principles
    -----------------
    * **Composition over inheritance** — owns a ``_pipe: Pipeline``.
    * **Reference counting** — each ``add_callback_listener`` call increments
      ``self.reference``; when zero the indicator is auto-removed from context.
    * **Dependency graph** — call ``self.depends(sub)`` inside ``init_depends()``
      to register sub-indicators; used for introspection and clean teardown.
    * **Self-broadcasting** — وقتی ``_emit_hook`` توسط ``ctx.attach_server()``
      inject شده، هر emit خودکار به terminal فرستاده می‌شود.

    Args:
        value_extractor: Callable applied to each raw value before calculation.
        warmup: Ticks silently discarded before boot begins.
        save_input: Store raw inputs in ``input_values`` ring-buffer.
        max_input: Input ring-buffer capacity.
        max_output: Output ring-buffer capacity.
    """

    # Class-level — each subclass sets these
    _ind_name:   str             = ""   # short display name; defaults to cls.__name__
    _key_params: tuple[str, ...] = ()   # ordered param attrs to include in key

    # Instance-level — injected by _register() in api.py after creation
    _indicator_id: str = ""             # human-readable key set externally

    def indicator_key(self) -> str:
        """Human-readable identifier used for DB field name, chart ID, and context key."""
        return self._indicator_id or self.context_key

    def get_state(self) -> dict:
        """Return serializable internal state for DB persistence.

        Override in subclasses to add indicator-specific fields.
        Returns {} if the indicator has not completed warm-up yet.
        """
        if not self._pipe.is_running:
            return {}
        return {
            "prev_value":  self._pipe.prev_value,
            "prev_output": self._pipe.prev_output,
        }

    def set_state(self, state: dict) -> None:
        """Restore internal state from DB.

        Override in subclasses to restore indicator-specific fields.
        Calling this skips warm-up and puts the indicator in run phase.
        """
        if not state:
            return
        self._pipe.prev_value  = state.get("prev_value")
        self._pipe.prev_output = state.get("prev_output")
        # Advance pipeline to run phase without replaying history
        self._pipe._step = self._pipe._run_step

    def __init__(
        self,
        *,
        value_extractor: Callable[..., Any] | None = None,
        warmup:          int                        = 0,
        save_input:      bool                       = False,
        max_input:       int                        = 50,
        max_output:      int                        = 50,
    ) -> None:
        # Identity fields — injected by ContextIndicator.get *after* __init__
        self.context_key:    str = ""
        self.context_symbol: str = ""
        self.tf:             str = Timeframe.m1
        self.source_tf:      str = Timeframe.m1
        # Context instance — injected by ContextIndicator.get so that
        # init_depends() can register sub-indicators on the *same* context
        # instead of the module-level global singleton.
        self._ctx: Any | None = None

        # Dependency graph: {context_key → Indicator}
        self.dependencies: dict[str, "Indicator"] = {}

        # External subscription reference count
        self.reference: int = 0

        # Owned pipeline
        self._pipe: Pipeline = Pipeline(
            warmup=warmup,
            max_output=max_output,
            extractor=value_extractor,
            save_input=save_input,
            max_input=max_input,
            save_output=True,
        )

        # SeriesMixin — emit hook (injected by ctx.attach_server)
        self._emit_hook: Callable[[dict[str, list[Any]]], None] | None = None
        # Last seen raw bar (for timestamp extraction in _on_emit)
        self._last_raw: Any = None

    # ── Pipeline surface — thin, zero-overhead delegation ─────────────────────

    @property
    def output_values(self) -> Any:
        """Ring-buffer of emitted values (newest at the right)."""
        return self._pipe.output_values

    @property
    def input_values(self) -> Any:
        """Ring-buffer of raw inputs (only populated when save_input=True)."""
        return self._pipe.input_values

    @property
    def prev_output(self) -> Any:
        """Most recently emitted value, or None before first emission."""
        return self._pipe.prev_output

    @property
    def prev_value(self) -> Any:
        """Last *extracted* value seen by the pipeline."""
        return self._pipe.prev_value

    @property
    def is_ready(self) -> bool:
        """True once the indicator entered steady-state run phase."""
        return self._pipe.is_running

    def add_input_value(self, raw: ValueType) -> None:
        """Push one OHLCV bar (or pre-extracted float) through the pipeline."""
        self._last_raw = raw
        self._pipe.tick(raw, self)

    def emit(self, value: Any) -> None:
        """Bypass the pipeline and emit *value* directly.

        Use from callback-driven indicators (e.g. HMA, ATR) that receive
        their data via sub-indicator callbacks rather than add_input_value.
        Automatically triggers ``_on_emit`` for server broadcasting.
        """
        self._pipe.emit(value)

    def _set_emit_hook(self, hook: Callable[[dict[str, list[Any]]], None] | None) -> None:
        """Inject the server broadcast hook and wire it to the pipeline."""
        self._emit_hook = hook
        if hook is not None:
            # Wire pipeline post-emit hook
            def _pipeline_hook(value: Any) -> None:
                self._on_emit(value, self._last_raw)
            self._pipe._post_emit_hook = _pipeline_hook
        else:
            self._pipe._post_emit_hook = None

    # ── Dependency graph ──────────────────────────────────────────────────────

    def depends(self, indicator: "Indicator") -> "Indicator":
        """Register *indicator* as a dependency and return it for chaining."""
        self.dependencies[indicator.context_key] = indicator
        return indicator

    # ── External callback management (with reference counting) ─────────────────

    def add_callback_listener(self, key: str, cb: Callable[[Any], None]) -> None:
        """Subscribe an external listener; increments reference count."""
        self._pipe.add_callback(key, cb)
        self.reference += 1

    def remove_callback_listener(self, key: str) -> None:
        """Unsubscribe a listener; auto-removes from context at refcount==0."""
        if key in self._pipe.callbacks:
            self._pipe.remove_callback(key)
            self.reference -= 1

    # ── Teardown ──────────────────────────────────────────────────────────────

    def dispatch(self) -> None:
        """Unsubscribe from sub-indicator callbacks. No-op by default."""

    # ── Abstract calculation methods ──────────────────────────────────────────

    @abstractmethod
    def init_depends(self) -> None:
        """Wire sub-indicator subscriptions.

        Called exactly once by ``ContextIndicator.get``, after identity
        fields have been set.  Use ``api.*`` functions inside this method.
        """

    @abstractmethod
    def _first_calculate(self, value: Any, prev: Any) -> Any:
        """Boot-phase calculation."""

    @abstractmethod
    def _calculate_new_value(self, value: Any, prev: Any) -> Any:
        """Steady-state calculation."""

    # ── Cache-key generation ──────────────────────────────────────────────────

    @staticmethod
    def _fmt_param(v: Any) -> str:
        if v is None:           return "none"
        if callable(v):         return f"fn:{v.__module__}.{v.__qualname__}"
        if isinstance(v, type): return f"cls:{v.__module__}.{v.__qualname__}"
        return repr(v)

    @classmethod
    def make_key(
        cls,
        tf:     str = Timeframe.m1,
        symbol: str = "",
        **params: Any,
    ) -> str:
        """Stable, deterministic string key for ``(cls, symbol, tf, **params)``."""
        base   = f"{cls.__module__}.{cls.__qualname__}|sym={symbol}|tf={tf}"
        extras = "|".join(
            f"{k}={Indicator._fmt_param(v)}"
            for k, v in sorted(params.items())
        )
        return f"{base}|{extras}" if extras else base


__all__ = ["Indicator", "ValueType"]
