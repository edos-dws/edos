"""UI-CP-1 / UI-CP-2 — coverage engine + Project Brain / coverage endpoints."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import coverage


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---- pure formula (no DB) ----
def test_domain_coverage_empty_is_zero():
    assert coverage._domain_coverage(0, 0, 0, 4) == 0.0


def test_domain_coverage_full_is_one():
    # saturate every term → clamps to 1.0
    val = coverage._domain_coverage(coverage.TARGET_ITEMS, coverage.TARGET_DOCS, 4, 4)
    assert val == pytest.approx(1.0)


def test_domain_coverage_questions_term():
    # only the question term contributes: answered/total * W_QUESTIONS
    val = coverage._domain_coverage(0, 0, 2, 4)
    assert val == pytest.approx(coverage.W_QUESTIONS * 0.5)


def test_weights_sum_to_one():
    assert coverage.W_ITEMS + coverage.W_DOCS + coverage.W_QUESTIONS == pytest.approx(1.0)


def test_question_sets_cover_all_domains():
    for d in coverage.DOMAINS:
        assert len(coverage.question_set(d)) >= 3


# ---- endpoints ----
def _new_project(client) -> str:
    return client.post("/v1/projects", json={"name": "Rover"}).json()["id"]


def test_brain_empty_project(client):
    pid = _new_project(client)
    b = client.get(f"/v1/projects/{pid}/brain").json()
    assert b["coverage"] == 0
    assert set(b["coverage_by_domain"]) == set(coverage.DOMAINS)
    assert all(v == 0 for v in b["coverage_by_domain"].values())
    assert b["counts"] == {"decisions": 0, "assumptions": 0, "assumptions_open": 0,
                           "assumptions_resolved": 0, "contradictions": 0, "open_risks": 0}


def test_answer_raises_domain_coverage(client):
    pid = _new_project(client)
    q = coverage.question_set("Architecture")[0]

    before = client.get(f"/v1/projects/{pid}/brain").json()["coverage_by_domain"]["Architecture"]
    assert before == 0

    r = client.post(f"/v1/projects/{pid}/coverage/answer",
                    json={"domain": "Architecture", "question_id": q["id"],
                          "answer": "Sensor block, compute block, power block."})
    assert r.status_code == 201
    assert r.json()["domain_coverage"] > 0

    after = client.get(f"/v1/projects/{pid}/brain").json()["coverage_by_domain"]["Architecture"]
    assert after > before

    # the answer became a domain-tagged, retrievable project item
    items = client.get(f"/v1/projects/{pid}/items").json()
    tagged = [i for i in items if i["domain"] == "Architecture"]
    assert tagged and tagged[0]["content"].startswith("Q:")


def test_answer_is_idempotent_per_question(client):
    pid = _new_project(client)
    q = coverage.question_set("Testing")[0]
    for _ in range(3):
        client.post(f"/v1/projects/{pid}/coverage/answer",
                    json={"domain": "Testing", "question_id": q["id"], "answer": "a"})
    detail = client.get(f"/v1/projects/{pid}/coverage").json()["domains"]["Testing"]
    assert detail["answered"] == [q["id"]]  # counted once, not thrice


def test_attach_document_raises_coverage(client):
    pid = _new_project(client)
    client.post(f"/v1/projects/{pid}/items",
                json={"item_type": "document", "content": "MCU datasheet", "domain": "Hardware"})
    cov = client.get(f"/v1/projects/{pid}/brain").json()["coverage_by_domain"]["Hardware"]
    assert cov > 0


def test_coverage_lists_unanswered(client):
    pid = _new_project(client)
    data = client.get(f"/v1/projects/{pid}/coverage").json()
    arch = data["domains"]["Architecture"]
    assert len(arch["unanswered"]) == arch["total_questions"]
    assert arch["coverage"] == 0


def test_answer_bad_domain_or_question(client):
    pid = _new_project(client)
    assert client.post(f"/v1/projects/{pid}/coverage/answer",
                       json={"domain": "Nope", "question_id": "x", "answer": "a"}).status_code == 422
    assert client.post(f"/v1/projects/{pid}/coverage/answer",
                       json={"domain": "Architecture", "question_id": "nope", "answer": "a"}
                       ).status_code == 422


def test_brain_missing_project_404(client):
    assert client.get("/v1/projects/nope/brain").status_code == 404
