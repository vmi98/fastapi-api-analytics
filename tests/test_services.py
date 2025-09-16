import pytest
from sqlmodel import select
from datetime import datetime, timedelta

from server.services import (
    compute_summary, get_endpoint_stats, get_top_ips, get_status_codes,
    EMPTY_DASHBOARD, get_method_usage, get_errors_rate, get_unique_ips,
    get_res_time_stats, get_time_series
)
from server.models import Log, APIKey


@pytest.fixture(scope="function")
def create_api_key(session):
    api_key = APIKey(api_key="valid_api_key")
    session.add(api_key)
    session.commit()
    session.refresh(api_key)
    return api_key


@pytest.fixture(scope="function")
def seed_logs(session, create_api_key):

    api_key = create_api_key

    base_day = datetime.now()

    logs = [
        Log(  # Day 0
            created_at=(base_day - timedelta(days=0)),
            method="GET",
            endpoint="/users",
            ip="192.168.0.1",
            process_time=0.10,
            status_code=200,
            api_key_id=api_key.id,
        ),
        Log(  # Day 1
            created_at=(base_day - timedelta(days=1)),
            method="POST",
            endpoint="/items",
            ip="192.168.0.2",
            process_time=0.20,
            status_code=201,
            api_key_id=api_key.id,
        ),
        Log(  # Day 2
            created_at=(base_day - timedelta(days=2)),
            method="PUT",
            endpoint="/orders",
            ip="192.168.0.3",
            process_time=0.30,
            status_code=500,
            api_key_id=api_key.id,
        ),
        Log(  # Day 3
            created_at=(base_day - timedelta(days=3)),
            method="DELETE",
            endpoint="/products",
            ip="192.168.0.4",
            process_time=0.40,
            status_code=404,
            api_key_id=api_key.id,
        ),
        Log(  # Day 4
            created_at=(base_day - timedelta(days=4)),
            method="PATCH",
            endpoint="/reviews",
            ip="192.168.0.5",
            process_time=0.50,
            status_code=200,
            api_key_id=api_key.id,
        ),
        Log(  # Day 5
            created_at=(base_day - timedelta(days=5)),
            method="OPTIONS",
            endpoint="/categories",
            ip="192.168.0.6",
            process_time=0.60,
            status_code=503,
            api_key_id=api_key.id,
        ),
        Log(  # Day 6 (repeats endpoint and IP)
            created_at=(base_day - timedelta(days=6)),
            method="GET",
            endpoint="/users",          # repeated endpoint
            ip="192.168.0.1",           # repeated IP
            process_time=0.70,
            status_code=200,
            api_key_id=api_key.id,
        ),
    ]

    session.add_all(logs)
    session.commit()

    for log in logs:
        session.refresh(log)

    return api_key, logs


@pytest.fixture(scope="function")
def cte(seed_logs):
    api_key, logs = seed_logs
    api_filtered = select(Log).where(Log.api_key_id == api_key.id
                                     ).cte("filtered_logs")
    return api_filtered


@pytest.fixture(scope="function")
def empty_cte(seed_logs):
    api_key, logs = seed_logs
    api_filtered = select(Log).where(False).cte("filtered_logs")
    return api_filtered


def test_compute_summary_no_logs(session, create_api_key):
    api_key = create_api_key
    result = compute_summary(session, api_key)

    assert result == EMPTY_DASHBOARD


def test_compute_summary_with_logs(session, seed_logs):
    api_key, logs = seed_logs
    result = compute_summary(session, api_key)

    assert result.get("summary").get("total_requests") == len(logs)
    assert len(result.get("status_codes")) == 5
    assert len(result.get("top_ips")) == 5
    assert len(result.get("endpoint_stats")) == 5

    assert result.get("top_ips")[0].get("ip") == "192.168.0.1"


def test_get_endpoint_stats_no_logs(session, empty_cte):
    result = get_endpoint_stats(session, empty_cte)

    assert len(result) == 0


def test_get_endpoint_stats_with_logs(session, cte):
    result = get_endpoint_stats(session, cte)

    assert len(result) == 5
    assert result[0].get("endpoint") == "/users"
    assert result[0].get("requests") == 2


def test_get_top_ips_no_logs(session, empty_cte):
    result = get_top_ips(session, empty_cte)

    assert len(result) == 0


def test_get_top_ips_with_logs(session, cte):
    result = get_top_ips(session, cte)

    assert len(result) == 5
    assert result[0].get("ip") == "192.168.0.1"
    assert result[0].get("requests") == 2


def test_get_status_codes_no_logs(session, empty_cte):
    result = get_status_codes(session, empty_cte)

    assert len(result) == 0


def test_get_status_codes_with_logs(session, cte):
    result = get_status_codes(session, cte)

    assert len(result) == 5
    assert result.get(200) == 3


def test_get_method_usage_no_logs(session, empty_cte):
    result = get_method_usage(session, empty_cte)

    assert len(result) == 0


def test_get_method_usage_with_logs(session, cte):
    result = get_method_usage(session, cte)

    assert len(result) == 6
    assert result.get("GET") == 2


def test_get_errors_rate_no_logs(session, empty_cte):
    result = get_errors_rate(session, empty_cte)

    assert result == 0.00


def test_get_errors_rate_with_logs(session, cte):
    result = get_errors_rate(session, cte)

    assert result == 42.86


def test_get_unique_ips_no_logs(session, empty_cte):
    result = get_unique_ips(session, empty_cte)

    assert result == 0


def test_get_unique_ips_with_logs(session, cte):
    result = get_unique_ips(session, cte)

    assert result == 6


def test_get_res_time_stats_no_logs(session, empty_cte):
    result = get_res_time_stats(session, empty_cte)

    assert result == {"min": 0, "avg": 0, "max": 0}


def test_get_res_time_stats_with_logs(session, cte):
    result = get_res_time_stats(session, cte)

    assert result == {"min": 0.10, "avg": 0.40, "max": 0.70}


def test_get_time_series_no_logs(session, empty_cte):
    result = get_time_series(session, empty_cte)

    assert result == []


def test_get_time_series_with_logs(session, cte):
    result = get_time_series(session, cte)

    assert len(result) == 5
    assert result[0].get("requests") == 1
