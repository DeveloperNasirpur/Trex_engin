from __future__ import annotations
"""trex.source.config — PostgreSQL connection configuration."""

from dataclasses import dataclass


@dataclass
class ConfigPostgres:
    """PostgreSQL connection parameters."""

    host:     str = "localhost"
    port:     int = 5432
    user:     str = "postgres"
    password: str = ""
    database: str = "okx"

    def to_dict(self) -> dict[str, object]:
        return {
            "host": self.host, "port": self.port,
            "user": self.user, "password": self.password,
            "dbname": self.database,
        }


__all__ = ["ConfigPostgres"]
