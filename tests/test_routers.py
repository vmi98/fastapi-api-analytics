import pytest
from pydantic import ValidationError, TypeAdapter
from server.models import APIKey
from server.schemas import DashboardResponse, LogOutput


@pytest.fixture(scope="function")
def create_api_key(session):
    api_key = APIKey(api_key="valid_api_key")
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return api_key


def test_dashboard(create_api_key, client):
    header = {"X-API-Key": create_api_key.api_key}

    response = client.get("/dashboard", headers=header)

    assert response.status_code == 200

    try:
        dashboard_response = DashboardResponse(**response.json())
        assert isinstance(dashboard_response, DashboardResponse)
    except ValidationError as e:
        pytest.fail(f"Response doesn't match DashboardResponse model: {e}")


def test_row_logs(create_api_key, client):
    header = {"X-API-Key": create_api_key.api_key}

    response = client.get("/raw_logs", headers=header)

    assert response.status_code == 200

    try:
        adapter = TypeAdapter(list[LogOutput])
        logs_response = adapter.validate_python(response.json())

        assert isinstance(logs_response, list)
        assert all(isinstance(item, LogOutput) for item in logs_response)

    except ValidationError as e:
        pytest.fail(f"Response doesn't match List[LogOutput] model: {e}")
