"""Ticket 7.2 — DecisionAccepted fans out to the expected background jobs."""
from edos.pipeline.passive import InMemoryJobQueue, emit


def test_decision_accepted_enqueues_expected_jobs():
    queue = InMemoryJobQueue()
    emitted = emit("DecisionAccepted", {"decision_id": "D-1"}, queue)
    assert set(emitted) == {
        "generate_summary", "create_embeddings", "update_decision_graph", "discover_relationships",
    }
    assert [j.name for j in queue.jobs] == emitted
    assert all(j.payload == {"decision_id": "D-1"} for j in queue.jobs)


def test_unknown_event_enqueues_nothing():
    queue = InMemoryJobQueue()
    assert emit("NothingHappened", {}, queue) == []
    assert queue.jobs == []
