"""trex.store.exceptions
========================
Exception hierarchy for the :mod:`trex.store` persistence layer.

All exceptions raised intentionally by :class:`trex.store.TrexStore`
derive from :class:`TrexStoreError`, so callers can catch the whole
family with a single ``except`` clause while still being able to
discriminate the concrete failure mode when they care.

::

    from trex.store.exceptions import TrexStoreError, StoreConnectionError

    try:
        store.save_indicators(...)
    except StoreConnectionError:
        ...          # database is unreachable
    except TrexStoreError:
        ...          # any other store-level failure
"""
from __future__ import annotations

__all__ = [
    "TrexStoreError",
    "StoreConnectionError",
    "SchemaError",
    "TableNotFoundError",
    "IndicatorError",
    "ValidationError",
    "MigrationError",
]


class TrexStoreError(Exception):
    """Base class for every error raised by :mod:`trex.store`."""


class StoreConnectionError(TrexStoreError):
    """Raised when a database connection cannot be established or used.

    Wraps the underlying ``psycopg`` operational error so callers do not
    need to import driver-specific exception types.
    """


class SchemaError(TrexStoreError):
    """Raised when a schema (exchange) is missing or cannot be created."""


class TableNotFoundError(TrexStoreError):
    """Raised when an operation targets a non-existent ``{SYMBOL}{TF}`` table."""


class IndicatorError(TrexStoreError):
    """Raised for malformed indicator payloads or JSONB (de)serialisation issues."""


class ValidationError(TrexStoreError):
    """Raised when user-supplied identifiers or rows fail validation."""


class MigrationError(TrexStoreError):
    """Raised when migrating data from an in-memory store fails."""
