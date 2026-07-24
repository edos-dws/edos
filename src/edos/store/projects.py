"""Persistence-layer CRUD for projects, conversations, and turns (CP-10).

Pure data access — no reasoning, retrieval, or LLM logic (that lives in the engines). The API and, later,
engines call these helpers. Ids are supplied by the caller (the API generates them) so the store stays
deterministic and easy to test.
"""
from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from edos.db.models import ConversationRow, ProjectRow, TurnRow

# ---------- projects ----------


def create_project(session: Session, *, id: str, name: str, domain: str | None = None) -> ProjectRow:
    row = ProjectRow(id=id, name=name, domain=domain)
    session.add(row)
    session.flush()
    return row


def get_project(session: Session, project_id: str) -> ProjectRow | None:
    return session.get(ProjectRow, project_id)


def list_projects(session: Session) -> list[ProjectRow]:
    return list(session.scalars(select(ProjectRow).order_by(ProjectRow.id)))


def update_project(session: Session, project_id: str, **changes) -> ProjectRow | None:
    row = session.get(ProjectRow, project_id)
    if row is None:
        return None
    for key, value in changes.items():
        if value is not None and hasattr(row, key):
            setattr(row, key, value)
    session.flush()
    return row


def delete_project(session: Session, project_id: str) -> bool:
    """Delete a project and cascade to its conversations and their turns."""
    row = session.get(ProjectRow, project_id)
    if row is None:
        return False
    conv_ids = [c.id for c in list_conversations(session, project_id)]
    if conv_ids:
        session.execute(delete(TurnRow).where(TurnRow.conversation_id.in_(conv_ids)))
        session.execute(delete(ConversationRow).where(ConversationRow.project_id == project_id))
    session.delete(row)
    session.flush()
    return True


# ---------- conversations ----------


def create_conversation(session: Session, *, id: str, project_id: str, title: str = "") -> ConversationRow:
    row = ConversationRow(id=id, project_id=project_id, title=title)
    session.add(row)
    session.flush()
    return row


def get_conversation(session: Session, conversation_id: str) -> ConversationRow | None:
    return session.get(ConversationRow, conversation_id)


def list_conversations(session: Session, project_id: str) -> list[ConversationRow]:
    return list(
        session.scalars(
            select(ConversationRow)
            .where(ConversationRow.project_id == project_id)
            .order_by(ConversationRow.created_at)
        )
    )


# ---------- turns ----------


def add_turn(
    session: Session, *, conversation_id: str, prompt: str, response_json: str = "",
    decision_id: str | None = None,
) -> TurnRow:
    row = TurnRow(
        conversation_id=conversation_id, prompt=prompt, response_json=response_json,
        decision_id=decision_id,
    )
    session.add(row)
    session.flush()
    return row


def list_turns(session: Session, conversation_id: str) -> list[TurnRow]:
    return list(
        session.scalars(
            select(TurnRow)
            .where(TurnRow.conversation_id == conversation_id)
            .order_by(TurnRow.created_at, TurnRow.id)
        )
    )


# ---------- context-link hook (CP-10.4) ----------


def project_for_conversation(session: Session, conversation_id: str) -> str | None:
    """Resolve a conversation to its project_id — the anchor downstream retrieval (CP-13) uses to scope
    context to the right project. Returns None if the conversation does not exist."""
    conv = get_conversation(session, conversation_id)
    return conv.project_id if conv else None


__all__: Sequence[str] = [
    "create_project", "get_project", "list_projects", "update_project", "delete_project",
    "create_conversation", "get_conversation", "list_conversations",
    "add_turn", "list_turns", "project_for_conversation",
]
