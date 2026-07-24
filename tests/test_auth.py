"""CP-19 — auth & multi-tenancy: token signup, ownership scoping (opt-in)."""
import pytest
from fastapi.testclient import TestClient

from edos.api.app import app
from edos.api.deps import get_session
from edos.engines import auth


def test_signup_is_idempotent(session):
    u1 = auth.signup(session, email="a@key.ai")
    u2 = auth.signup(session, email="a@key.ai")
    assert u1.id == u2.id and u1.token == u2.token  # same account/token


def test_token_resolves_user(session):
    u = auth.signup(session, email="b@key.ai")
    assert auth.user_for_token(session, u.token).id == u.id
    assert auth.user_for_token(session, "bogus") is None
    assert auth.user_for_token(session, None) is None


def test_role_based_memory_guard():
    assert auth.user_writable(None) is False   # system-scoped: not user-writable
    assert auth.user_writable("u1") is True


@pytest.fixture()
def client(session):
    def _override():
        yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_signup_and_owned_project_scoping(client):
    tok = client.post("/v1/auth/signup", json={"email": "eng@key.ai"}).json()["token"]
    h = {"Authorization": f"Bearer {tok}"}

    owned = client.post("/v1/projects", json={"name": "Mine"}, headers=h).json()
    assert owned["owner_id"]  # scoped to the user

    # a second user cannot see the first user's owned project
    tok2 = client.post("/v1/auth/signup", json={"email": "other@key.ai"}).json()["token"]
    ids = {p["id"] for p in client.get("/v1/projects", headers={"Authorization": f"Bearer {tok2}"}).json()}
    assert owned["id"] not in ids


def test_unauthenticated_access_is_open(client):
    # auth is opt-in — no token still works (existing behavior preserved)
    assert client.post("/v1/projects", json={"name": "Open"}).status_code == 201
    assert client.get("/v1/projects").status_code == 200
