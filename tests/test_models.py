import pytest
from pydantic import ValidationError
from server.models import (
    APIKey, Log, SummaryModel,
    EndpointStatsEntry, TopIpEntry, TimeSeriesEntry
)


@pytest.fixture(scope="function")
def create_api_key(session):
    api_key = APIKey(api_key="valid_api_key")
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return api_key


def test_apikey_model_creation(create_api_key):
    api_key = create_api_key
    assert api_key.id is not None
    assert api_key.api_key == "valid_api_key"


@pytest.mark.parametrize("method, status_code",
                         [("GET", 200), ("POST", 404), ("DELETE", 500)])
def test_log_model_creation(create_api_key, session,
                            client, method, status_code):
    log = {
        "created_at": "2025-08-17T12:00:00",
        "method": method,
        "endpoint": "/test",
        "ip": '66.249.68.32',
        "process_time": 0.1,
        "status_code": status_code
    }

    client.post("/track",
                json=log,
                headers={"X-API-Key": create_api_key.api_key})
    log_db = session.get(Log, 1)

    assert log_db is not None
    assert log_db.method == method
    assert log_db.status_code == status_code


@pytest.mark.parametrize(
    "invalid_field, value",
    [
        ("method", None),
        ("status_code", "abc"),
        ("process_time", -1),
        ("created_at", 123),
        ("method", ""),
        ("ip", " "),
        ("endpont", "")
    ]
)
def test_log_invalid_fields(invalid_field, value, client, create_api_key):
    log = {
        "created_at": "2025-08-17T12:00:00",
        "method": "GET",
        "endpoint": "/test",
        "ip": '66.249.68.32',
        "process_time": 0.1,
        "status_code": 200
    }
    log[invalid_field] = value

    response = client.post("/track",
                           json=log,
                           headers={"X-API-Key": create_api_key.api_key})

    assert response.status_code == 422


@pytest.mark.parametrize(
    "model_class, invalid_kwargs",
    [
        (SummaryModel, dict(total_requests="abc")),
        (EndpointStatsEntry, dict(avg_time="not-a-float")),
        (TopIpEntry, dict(requests="NaN")),
        (TimeSeriesEntry, dict(timestamp=12345))
    ]
)
def test_models_invalid_types(model_class, invalid_kwargs):
    with pytest.raises(ValidationError):
        model_class(**invalid_kwargs)
