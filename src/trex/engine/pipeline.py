from __future__ import annotations
"""
trex.engine.pipeline
====================
Three-phase streaming state-machine — hot-path core of trex engine.

Phases
------
1. **warmup**  — silently collect first *n* ticks; track ``prev_value`` only.
2. **boot**    — call ``_first_calculate`` each tick until indicator signals ready:
                 ``None`` / ``False`` → stay in boot (need more data)
                 ``True``             → advance to run, no emission
                 ``<value>``          → advance to run AND emit
3. **run**     — call ``_calculate_new_value`` every tick; emit non-None results.

Hot-path design
---------------
Phase dispatch uses a **function pointer** (``_step``) rebound once at each
phase transition.  Steady-state (run phase) costs exactly:

    extractor(raw) → _step(value, host) → emit(result)

No branch, no enum comparison in the loop body during steady-state.
"""

from collections import deque
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    pass


# ── Host protocol ─────────────────────────────────────────────────────────────

class PipelineHost:
    """
    Interface contract for any class that owns a Pipeline.

    Subclasses must override ``_first_calculate`` and ``_calculate_new_value``.
    ``PipelineHost`` is a plain base (not ABC) to avoid metaclass conflicts.
    """

    def _first_calculate(self, value: Any, prev: Any) -> Any:
        raise NotImplementedError

    def _calculate_new_value(self, value: Any, prev: Any) -> Any:
        raise NotImplementedError


# ── Identity extractor ─────────────────────────────────────────────────────────

def _identity(x: Any) -> Any:
    return x


# ── Pipeline ──────────────────────────────────────────────────────────────────

class Pipeline:
    """
    Composable three-phase streaming state-machine.

    Owned (not inherited) by ``Indicator`` and ``Source`` via their ``_pipe``
    attribute.  All hot-path state lives in ``__slots__`` for fast attribute access.

    Args:
        warmup: Ticks silently discarded before boot begins (0 = skip warmup).
        max_output: ``output_values`` ring-buffer capacity.
        extractor: Optional callable applied to each raw value before calc.
        save_input: Store raw values in ``input_values`` ring-buffer.
        max_input: ``input_values`` ring-buffer capacity.
        save_output: ``False`` → emit fires callbacks only, no ring-buffer append.
    """

    __slots__ = (
        "_extractor", "_save_output",
        "output_values", "prev_output",
        "input_values", "prev_value",
        "callbacks", "_warmup_remain", "_warmup_init",
        "_step", "_post_emit_hook",
    )

    def __init__(
        self,
        warmup:      int                   = 0,
        max_output:  int                   = 500,
        extractor:   Callable[..., Any] | None = None,
        save_input:  bool                  = False,
        max_input:   int                   = 500,
        save_output: bool                  = True,
    ) -> None:
        self._extractor:     Callable[..., Any]        = extractor if extractor is not None else _identity
        self._save_output:   bool                      = save_output
        self.output_values:  deque[Any]                = deque(maxlen=max_output)
        self.prev_output:    Any                       = None
        self.input_values:   deque[Any] | None         = deque(maxlen=max_input) if save_input else None
        self.prev_value:     Any                       = None
        self.callbacks:      dict[str, Callable[..., Any]] = {}
        self._warmup_init:   int                       = warmup
        self._warmup_remain: int                       = warmup
        self._post_emit_hook: Callable[[Any], None] | None = None  # server hook
        self._step: Callable[..., None] = (
            self._warmup_step if warmup > 0 else self._boot_step
        )

    # ── Public entry-point ────────────────────────────────────────────────────

    def tick(self, raw: Any, host: PipelineHost) -> None:
        """Push one raw value through the current pipeline phase."""
        if self.input_values is not None:
            self.input_values.append(raw)
        self._step(self._extractor(raw), host)

    # ── Phase functions ───────────────────────────────────────────────────────

    def _warmup_step(self, value: Any, _host: PipelineHost) -> None:
        self.prev_value = value
        self._warmup_remain -= 1
        if self._warmup_remain == 0:
            self._step = self._boot_step

    def _boot_step(self, value: Any, host: PipelineHost) -> None:
        result = host._first_calculate(value, self.prev_value)
        self.prev_value = value
        if result is None or result is False:
            return
        self._step = self._run_step          # ← transition: never branch again
        if result is not True:
            self.emit(result)

    def _run_step(self, value: Any, host: PipelineHost) -> None:
        result = host._calculate_new_value(value, self.prev_value)
        self.prev_value = value
        if result is not None:
            self.emit(result)

    # ── Emission ──────────────────────────────────────────────────────────────

    def emit(self, value: Any) -> None:
        """Store (when save_output), update prev_output, fire all callbacks."""
        if self._save_output:
            self.output_values.append(value)
        for cb in self.callbacks.values():
            cb(value)
        self.prev_output = value
        # Fire post-emit hook (used for server broadcasting via SeriesMixin)
        if self._post_emit_hook is not None:
            self._post_emit_hook(value)

    # ── Callback registry ─────────────────────────────────────────────────────

    def add_callback(self, key: str, cb: Callable[..., Any]) -> None:
        self.callbacks[key] = cb

    def remove_callback(self, key: str) -> None:
        self.callbacks.pop(key, None)

    # ── Reset ─────────────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Clear ring-buffers and callbacks; restart from the initial phase."""
        if self.input_values is not None:
            self.input_values.clear()
        self.output_values.clear()
        self.callbacks.clear()
        self.prev_output    = None
        self.prev_value     = None
        self._warmup_remain = self._warmup_init
        self._step = self._warmup_step if self._warmup_init > 0 else self._boot_step

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        """True once the indicator entered steady-state run phase."""
        return self._step.__func__ is Pipeline._run_step  # type: ignore[attr-defined]

    @property
    def is_warming_up(self) -> bool:
        """True while the warmup quota has not been reached."""
        return self._step.__func__ is Pipeline._warmup_step  # type: ignore[attr-defined]


__all__ = ["Pipeline", "PipelineHost"]
