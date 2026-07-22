"""Runtime configuration from environment (roadmap Ch 17). No secrets hard-coded."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get(
        "DATABASE_URL", "postgresql+psycopg://edos:edos@localhost:5432/edos"
    )
    redis_url: str = os.environ.get("REDIS_URL", "redis://localhost:6379/0")


settings = Settings()
