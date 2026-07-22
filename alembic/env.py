"""Alembic environment — wired to EDOS settings + ORM metadata."""
from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from edos.config import settings
from edos.db import models  # noqa: F401 — registers tables on Base.metadata
from edos.db.base import Base

config = context.config
# Use the app's DATABASE_URL (env-driven) rather than a hard-coded alembic.ini value.
config.set_main_option("sqlalchemy.url", settings.database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
