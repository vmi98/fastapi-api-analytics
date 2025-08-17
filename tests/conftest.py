import pytest
from sqlmodel import SQLModel, Session, create_engine, Field
from fastapi.testclient import TestClient
from main import app
from server.models import get_session


TEST_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)
connection = engine.connect()


@pytest.fixture(scope="function", name="session")
def session_fixture():
    SQLModel.metadata.create_all(connection)
    with Session(connection) as session:
        yield session
    SQLModel.metadata.drop_all(connection)


@pytest.fixture(scope="function", name="client")
def client_fixture(session):
    # override the app's get_session to use test session
    def override_get_session():
        with Session(connection) as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
