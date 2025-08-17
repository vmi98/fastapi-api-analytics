import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import select
from main import app
from server.auth import get_api_key
from server.models import APIKey


@pytest.fixture(scope="function")
def create_fake_api_key(session):
    fake_api_key = APIKey(api_key="valid_api_key")
    session.add(fake_api_key)
    session.commit()
    session.refresh(fake_api_key)
    return fake_api_key


def test_get_api_key_valid(create_fake_api_key, session):
    api_key = get_api_key(session, create_fake_api_key.api_key)
    assert api_key == create_fake_api_key


def test_generate_key_route(monkeypatch, client, session):
    fake_key = "fake_key"
    monkeypatch.setattr("server.auth.generate_api_key", lambda: fake_key)

    response = client.post("/generate_key")

    assert response.status_code == 200
    assert response.json() == fake_key

    statement = select(APIKey).where(APIKey.api_key == fake_key)
    generated_key_db = session.exec(statement).first()
    assert generated_key_db is not None
    assert generated_key_db.api_key == fake_key


def test_protected_endpoint_requires_api_key(create_fake_api_key, client):
    header = {"X-API-Key": create_fake_api_key.api_key}

    response = client.get("/dashboard")
    assert response.status_code == 401

    response = client.get("/dashboard", headers={"X-API-Key": "invalid"})
    assert response.status_code == 401

    response = client.get("/dashboard", headers=header)
    assert response.status_code == 200


@pytest.mark.parametrize("malformed_key", [
    7899887,
    "",
    " ",
    None,
    "a"*1000,
    "invalid_api_key"
])
def test_edge_cases(malformed_key, session):
    with pytest.raises(HTTPException) as exc_info:
        get_api_key(session, malformed_key)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail in ["Missing API Key", "Invalid API Key"]
