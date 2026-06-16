from __future__ import annotations
"""
trex.engine.source
==================
Abstract base برای producer/transformer nodes (e.g. ConvertTimeFrame).

تفاوت با Indicator
-------------------
* بدون reference-count/auto-removal — Sourceها long-lived هستند.
* ``save_output=False`` برای fan-out nodes (CTF).
* ``output_listeners`` برای cascaded teardown.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import is_dataclass
from itertools import chain
from operator import attrgetter, methodcaller
from typing import Any, Callable

from trex.base.ohlcv import OHLCV
from trex.base.timeframe import Timeframe
from trex.engine.pipeline import Pipeline, PipelineHost

ValueType = OHLCV | float


class Source(PipelineHost, ABC):
    """
    Streaming producer/transformer base.

    Args:
        warmup: Ticks silently discarded before boot begins.
        max_input: Input ring-buffer capacity.
        max_output: Output ring-buffer capacity.
        extractor: Optional callable applied to each raw value.
        save_input: Store raw inputs in ``input_values``.
        save_output: False → emit fires callbacks only; no ring-buffer append.
        tf: This source's timeframe label.
        source_tf: Upstream timeframe label.
    """

    def __init__(
        self,
        *,
        warmup:      int                        = 0,
        max_input:   int                        = 500,
        max_output:  int                        = 500,
        extractor:   Callable[..., Any] | None  = None,
        save_input:  bool                       = True,
        save_output: bool                       = True,
        tf:          str                        = Timeframe.m1,
        source_tf:   str                        = Timeframe.m1,
    ) -> None:
        self.tf:               str         = tf
        self.source_tf:        str         = source_tf
        self.output_listeners: list["Source"] = []

        self._pipe: Pipeline = Pipeline(
            warmup=warmup,
            max_output=max_output,
            extractor=extractor,
            save_input=save_input,
            max_input=max_input,
            save_output=save_output,
        )

    # ── Pipeline surface ──────────────────────────────────────────────────────

    @property
    def output_values(self) -> Any:
        return self._pipe.output_values

    @property
    def input_values(self) -> Any:
        return self._pipe.input_values

    @property
    def prev_output(self) -> Any:
        return self._pipe.prev_output

    @property
    def prev_value(self) -> Any:
        return self._pipe.prev_value

    @property
    def is_ready(self) -> bool:
        return self._pipe.is_running

    def add_input_value(self, raw: ValueType) -> None:
        self._pipe.tick(raw, self)

    def emit(self, value: Any) -> None:
        self._pipe.emit(value)

    # ── Callback management ───────────────────────────────────────────────────

    def add_callback(self, key: str, cb: Callable[..., Any]) -> None:
        self._pipe.add_callback(key, cb)

    def remove_callback(self, key: str) -> None:
        self._pipe.remove_callback(key)

    # Aliases for compatibility with Indicator call-sites
    def add_callback_listener(self, key: str, cb: Callable[..., Any]) -> None:
        self._pipe.add_callback(key, cb)

    def remove_callback_listener(self, key: str) -> None:
        self._pipe.remove_callback(key)

    def add_output_listener(self, listener: "Source") -> None:
        self.output_listeners.append(listener)

    # ── Sequence protocol ─────────────────────────────────────────────────────

    def __getitem__(self, index: int) -> Any:
        return self._pipe.output_values[index]

    def __len__(self) -> int:
        return len(self._pipe.output_values)

    def __str__(self) -> str:
        return str(list(self._pipe.output_values))

    # ── Reset / teardown ──────────────────────────────────────────────────────

    def remove_all(self) -> None:
        """Clear all data and cascade to output_listeners."""
        self._pipe.reset()
        for listener in self.output_listeners:
            listener.remove_all()
        self._on_reset()

    def _on_reset(self) -> None:
        """Subclass hook: override to clear additional state on reset."""

    # ── Queries ───────────────────────────────────────────────────────────────

    def has_output(self) -> bool:
        ov = self._pipe.output_values
        return bool(ov and ov[-1] is not None)

    def to_lists(self) -> dict[str, list[Any]]:
        """Serialise dataclass outputs to ``{field_name: [values, ...]}``."""
        ov = self._pipe.output_values
        if not ov:
            return {}
        if not is_dataclass(ov[0]):
            raise TypeError("to_lists() requires dataclass outputs.")
        result: dict[str, list[Any]] = defaultdict(list)
        for k, v in chain.from_iterable(
            map(methodcaller("items"), map(attrgetter("__dict__"), ov))
        ):
            result[k].append(v)
        return dict(result)

    # ── Abstracts ─────────────────────────────────────────────────────────────

    @abstractmethod
    def _first_calculate(self, value: ValueType, prev: ValueType) -> Any: ...

    @abstractmethod
    def _calculate_new_value(self, value: ValueType, prev: ValueType) -> Any: ...


__all__ = ["Source", "ValueType"]
