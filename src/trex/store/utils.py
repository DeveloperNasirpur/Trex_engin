"""trex.store.utils
==================
Pure helper functions for the persistence layer.

This module is intentionally free of any database dependency so it can be
unit-tested in isolation and reused by callers that only need the naming
conventions (e.g. to predict a table name before the row exists).

Key responsibilities
---------------------
- **Identifier safety**: PostgreSQL identifiers are validated against a
  strict allow-list *before* they are ever interpolated into DDL. SQL
  parameters cannot bind identifiers (schema / table / column names), so
  the only safe path is to reject anything that is not a plain
  ``[A-Za-z0-9_]`` token. This closes the SQL-injection vector that
  identifier interpolation would otherwise open.
- **Naming conventions**: the canonical ``{SYMBOL}{TF}`` table name
  (upper-case, no separator — e.g. ``BTCUSDT1M``) and the OHLCV column set
  used everywhere in the package.
- **Row partitioning**: splitting an incoming ``save_indicators`` row into
  its OHLCV part and its indicator part.

Why upper-case table names work safely
--------------------------------------
PostgreSQL folds *unquoted* identifiers to lower-case, so ``BTCUSDT1M`` and
``btcusdt1m`` would normally collide. This package **always double-quotes**
every schema and table name in its SQL, which makes the upper-case spelling
the genuine, stable physical name. Validation therefore preserves case for
table components while still rejecting anything outside ``[A-Za-z0-9]``.
Schema (exchange) names are normalised to lower-case, matching the
convention used elsewhere in Trex (``binance``, ``okx``).
"""
from __future__ import annotations

import math
import re
from typing import Any, Final

from trex.store.exceptions import ValidationError

__all__ = [
    "OHLCV_COLUMNS",
    "RESERVED_COLUMNS",
    "valid_identifier",
    "ensure_schema_identifier",
    "ensure_component",
    "schema_name",
    "table_name",
    "split_row",
    "coerce_jsonb_value",
]

# Columns that live as first-class typed columns on every candle table.
# ``time`` is the primary key; the rest are ``NUMERIC``.
OHLCV_COLUMNS: Final[tuple[str, ...]] = (
    "time",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

# Columns the package owns and that must never be treated as an indicator.
RESERVED_COLUMNS: Final[frozenset[str]] = frozenset(
    {*OHLCV_COLUMNS, "indicators", "updated_at"}
)

# Schema (exchange) name: lower-case, starts with a letter, then
# letters/digits/underscore, bounded to PostgreSQL's 63-byte limit.
_SCHEMA_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

# A table-name *component* (symbol or timeframe). Upper-case, alphanumeric
# only (no underscore, since the final name concatenates SYMBOL + TF without
# a separator and an underscore would make the split ambiguous). May start
# with a digit (timeframes such as ``1M`` are not used, but defensive).
_COMPONENT_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9][A-Z0-9]{0,62}$")


def valid_identifier(value: str) -> bool:
    """Return ``True`` if *value* is a safe, lower-case schema identifier.

    Args:
        value: Candidate schema name.

    Returns:
        ``True`` when *value* matches ``^[a-z][a-z0-9_]{0,62}$``.
    """
    return bool(_SCHEMA_RE.match(value))


def ensure_schema_identifier(value: str, *, kind: str = "exchange") -> str:
    """Validate and normalise a schema (exchange) identifier, or raise.

    The value is lower-cased before validation so callers may pass
    ``"Binance"`` or ``"binance"`` interchangeably.

    Args:
        value: Candidate schema identifier.
        kind: Human-readable role used in the error message.

    Returns:
        The normalised (lower-cased) schema name.

    Raises:
        ValidationError: If the normalised value is not a safe identifier.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{kind} must be a non-empty string, got {value!r}.")
    normalised = value.strip().lower()
    if not _SCHEMA_RE.match(normalised):
        raise ValidationError(
            f"Invalid {kind} {value!r}: must match {_SCHEMA_RE.pattern} "
            f"(letters, digits, underscore; start with a letter; <= 63 chars)."
        )
    return normalised


def ensure_component(value: str, *, kind: str = "component") -> str:
    """Validate and normalise a table-name component (symbol / timeframe).

    The value is upper-cased and stripped before validation, and must be
    purely alphanumeric (no underscore or whitespace).

    Args:
        value: Candidate component (e.g. ``"btcusdt"`` or ``"1m"``).
        kind: Human-readable role used in the error message
            (e.g. ``"symbol"``, ``"timeframe"``).

    Returns:
        The normalised (upper-cased) component.

    Raises:
        ValidationError: If the normalised value is not safe.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{kind} must be a non-empty string, got {value!r}.")
    normalised = value.strip().upper()
    if not _COMPONENT_RE.match(normalised):
        raise ValidationError(
            f"Invalid {kind} {value!r}: must be alphanumeric "
            f"(A-Z, 0-9; no underscore or spaces; <= 63 chars)."
        )
    return normalised


def schema_name(exchange: str) -> str:
    """Return the validated PostgreSQL schema name for an exchange.

    Args:
        exchange: Exchange identifier (e.g. ``"binance"``).

    Returns:
        The validated, lower-cased schema name.

    Raises:
        ValidationError: If *exchange* is not a safe identifier.
    """
    return ensure_schema_identifier(exchange, kind="exchange")


def table_name(symbol: str, tf: str) -> str:
    """Return the canonical ``{SYMBOL}{TF}`` table name (no separator).

    Both parts are validated independently, upper-cased, and concatenated,
    so the final name is guaranteed safe to interpolate into double-quoted
    DDL. Examples: ``("BTCUSDT", "1m") -> "BTCUSDT1M"``,
    ``("ethusdt", "5m") -> "ETHUSDT5M"``.

    Args:
        symbol: Trading pair (e.g. ``"BTCUSDT"``).
        tf: Timeframe token (e.g. ``"1m"``, ``"4h"``).

    Returns:
        The validated upper-case table name, e.g. ``"BTCUSDT1M"``.

    Raises:
        ValidationError: If either part is unsafe, or if the joined name
            would exceed PostgreSQL's 63-byte limit.
    """
    sym = ensure_component(symbol, kind="symbol")
    timeframe = ensure_component(tf, kind="timeframe")
    name = f"{sym}{timeframe}"
    if len(name) > 63:
        raise ValidationError(
            f"Table name {name!r} exceeds PostgreSQL's 63-byte identifier limit."
        )
    return name


def coerce_jsonb_value(value: Any) -> Any:
    """Sanitise a value destined for a JSONB document.

    ``NaN`` / ``Infinity`` are valid IEEE-754 floats but are *not* valid
    JSON and PostgreSQL's ``jsonb`` type rejects them. We map them to
    ``None`` so a single bad indicator value cannot fail an entire batch.

    Nested ``dict`` / ``list`` structures are sanitised recursively.

    Args:
        value: Any JSON-serialisable value.

    Returns:
        A value safe to embed in a JSONB document.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {k: coerce_jsonb_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [coerce_jsonb_value(v) for v in value]
    return value


def split_row(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Partition a ``save_indicators`` row into OHLCV and indicator parts.

    Any key in :data:`OHLCV_COLUMNS` is treated as candle data; every other
    key is treated as an indicator and folded into the JSONB document.
    The reserved ``indicators`` / ``updated_at`` keys are ignored if present.

    Args:
        row: A flat mapping mixing OHLCV fields and indicator fields, e.g.
            ``{"time": 1, "open": 42000, "RSI_14": 65.4, "MACD_12_26_9": {...}}``.

    Returns:
        A ``(candle, indicators)`` tuple where *candle* contains only OHLCV
        keys present in *row* and *indicators* contains the sanitised
        indicator document.

    Raises:
        ValidationError: If *row* lacks a ``time`` key.
    """
    if "time" not in row:
        raise ValidationError("Each row must contain a 'time' key.")

    candle: dict[str, Any] = {}
    indicators: dict[str, Any] = {}
    for key, value in row.items():
        if key in OHLCV_COLUMNS:
            candle[key] = value
        elif key in ("indicators", "updated_at"):
            # Reserved package-owned columns — never an indicator.
            continue
        else:
            indicators[key] = coerce_jsonb_value(value)
    return candle, indicators
