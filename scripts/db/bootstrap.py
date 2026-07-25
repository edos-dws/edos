"""Fresh-DB bootstrap — build the full current schema and mark Alembic at head.

Why not `alembic upgrade head`? Revision 0001 is metadata-driven (`Base.metadata.create_all`), so on a fresh
database it already creates every current table; the later incremental revisions then collide. For a fresh
install we therefore create the schema from the models directly and `stamp` Alembic to head. Existing
deployments that predate a revision still upgrade with `alembic upgrade <rev>` as usual.

Usage:  DATABASE_URL=... .venv/bin/python scripts/db/bootstrap.py
"""
from __future__ import annotations

from alembic import command
from alembic.config import Config

from edos.db.base import make_engine
from edos.db.schema import create_all


def main() -> None:
    engine = make_engine()
    create_all(engine)  # pgvector + all tables from current models
    cfg = Config("alembic.ini")
    command.stamp(cfg, "head")  # record that this DB is at the latest revision
    print("EDOS schema ready; Alembic stamped at head.")


if __name__ == "__main__":
    main()
