"""Auth & multi-tenancy (CP-19) — a minimal, non-breaking token layer.

Default: each user gets an opaque bearer token at signup; endpoints resolve it to a user and scope project
ownership. Auth is **opt-in** — existing endpoints stay open so the platform keeps working — because the
enforcement policy and production auth (OAuth/OIDC, password hashing, rotation) are OD-8 (your decision).

Role-based memory: `system`-scoped knowledge (owner_id=None) is platform truth a user must not overwrite;
`user_writable` enforces that separation.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from edos.db.models import ProjectRow, User


def _id() -> str:
    return uuid.uuid4().hex[:12]


def signup(session: Session, *, email: str) -> User:
    existing = session.scalars(select(User).where(User.email == email)).first()
    if existing is not None:
        return existing  # idempotent: return the same account/token
    user = User(id=_id(), email=email, token=uuid.uuid4().hex)
    session.add(user)
    session.flush()
    return user


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    return session.scalars(select(User).where(User.token == token)).first()


def can_access_project(project: ProjectRow, user: User | None) -> bool:
    """Unowned projects are shared; owned projects require the owner. With no user (auth off), allow —
    enforcement is opt-in (OD-8)."""
    if user is None or project.owner_id is None:
        return True
    return project.owner_id == user.id


def user_writable(owner_id: str | None) -> bool:
    """Role-based memory guard: system-scoped (owner_id=None) records are not user-writable."""
    return owner_id is not None
