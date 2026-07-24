"""CP-10 ticket 10.1-10.4 — project/conversation/turn persistence CRUD + context-link hook."""
from edos.store import projects as store


def test_project_crud_roundtrip(session):
    store.create_project(session, id="p1", name="Water Quality", domain="embedded")
    assert store.get_project(session, "p1").name == "Water Quality"
    assert [r.id for r in store.list_projects(session)] == ["p1"]

    store.update_project(session, "p1", name="Water Quality v2")
    assert store.get_project(session, "p1").name == "Water Quality v2"
    assert store.get_project(session, "p1").domain == "embedded"  # unchanged

    assert store.delete_project(session, "p1") is True
    assert store.get_project(session, "p1") is None
    assert store.delete_project(session, "missing") is False


def test_conversation_linked_to_project(session):
    store.create_project(session, id="p1", name="X")
    c = store.create_conversation(session, id="c1", project_id="p1", title="MCU selection")
    assert c.project_id == "p1"
    assert [x.id for x in store.list_conversations(session, "p1")] == ["c1"]
    assert store.get_conversation(session, "c1").title == "MCU selection"


def test_turn_from_analyze_response_is_stored_and_linked(session):
    """CP-10.3 — an analyze exchange persists as a turn, linked to conversation (and thus project)."""
    store.create_project(session, id="p1", name="X")
    store.create_conversation(session, id="c1", project_id="p1")
    store.add_turn(session, conversation_id="c1", prompt="Which MCU?", response_json='{"summary":"..."}')
    turns = store.list_turns(session, "c1")
    assert len(turns) == 1
    assert turns[0].prompt == "Which MCU?"
    assert store.project_for_conversation(session, "c1") == "p1"  # link hook


def test_delete_project_cascades_conversations_and_turns(session):
    store.create_project(session, id="p1", name="X")
    store.create_conversation(session, id="c1", project_id="p1")
    store.add_turn(session, conversation_id="c1", prompt="q", response_json="{}")

    store.delete_project(session, "p1")
    assert store.list_conversations(session, "p1") == []
    assert store.list_turns(session, "c1") == []


def test_project_for_missing_conversation_is_none(session):
    assert store.project_for_conversation(session, "nope") is None
