from sqlalchemy import select, func, distinct, cast, Float
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import CTE
from typing import Optional


from .models import Log, APIKey
from .schemas import DashboardResponse

EMPTY_DASHBOARD = {
    "summary": {
        "total_requests": 0,
        "unique_ips": 0,
        "avg_response_time": None,
        "min_response_time": None,
        "max_response_time": None,
        "error_rate": 0.0
    },
    "method_usage": {},
    "endpoint_stats": [],
    "status_codes": {},
    "top_ips": [],
    "time_series": []
}


def get_time_series(session: Session, filtered_logs: CTE) -> list[dict]:
    st_code_cond = filtered_logs.c.status_code.between(400, 599)
    time_series_db = session.execute(
        select(
            func.strftime('%Y-%m-%d', filtered_logs.c.created_at).label("timestamp"), # strftime - SQLite-specific
            func.count(filtered_logs.c.id).label("requests"),
            func.avg(filtered_logs.c.process_time).label("avg_time"),
            (func.count().filter(st_code_cond) / cast(func.count(filtered_logs.c.id),
                                                      Float)).label('error_rate')
        )
        .group_by(func.strftime('%Y-%m-%d', filtered_logs.c.created_at))
        .order_by(func.strftime('%Y-%m-%d', filtered_logs.c.created_at))
        .limit(5)
    ).all()

    time_series = [
        {
            "timestamp": ts,
            "requests": req,
            "avg_time": round(avg, 2),
            "error_rate": round(rate, 2)
        }
        for ts, req, avg, rate in time_series_db
    ]

    return time_series


def get_res_time_stats(session: Session, filtered_logs: CTE) -> dict[str, float]:
    stmt = select(
        func.min(filtered_logs.c.process_time),
        func.avg(filtered_logs.c.process_time),
        func.max(filtered_logs.c.process_time)
    )
    min_time, avg_time, max_time = session.execute(stmt).one()

    if all([min_time, avg_time, max_time]):
        return {
            "min": round(float(min_time), 2),
            "avg": round(float(avg_time), 2),
            "max": round(float(max_time), 2),
        }
    else:
        return {"min": 0, "avg": 0, "max": 0}


def get_unique_ips(session: Session, filtered_logs: CTE) -> int:
    statement = select(func.count(distinct(filtered_logs.c.ip)))
    unique_ips = session.scalar(statement)
    return unique_ips


def get_errors_rate(session: Session, filtered_logs: CTE) -> float:
    errors = session.scalar(
        select(func.count(filtered_logs.c.id))
        .where(filtered_logs.c.status_code.between(400, 599))
    )
    total_requests = get_total_req(session, filtered_logs)
    if total_requests:
        errors_per_100_req = (errors / total_requests) * 100
    else:
        errors_per_100_req = 0
    return round(errors_per_100_req, 2)


def get_method_usage(session: Session, filtered_logs: CTE) -> dict[str, int]:
    method_usage = {
        method: count
        for method, count
        in session.execute(select(filtered_logs.c.method, func.count(filtered_logs.c.id)
                                  ).group_by(filtered_logs.c.method)).all()
    }
    return method_usage


def get_status_codes(session: Session, filtered_logs: CTE) -> dict[str, int]:
    status_codes = {
        status_code: count
        for status_code, count in session.execute(
            select(filtered_logs.c.status_code, func.count(filtered_logs.c.id))
            .group_by(filtered_logs.c.status_code)
        ).all()
    }
    return status_codes


def get_top_ips(session: Session, filtered_logs: CTE) -> list[dict]:
    top_ips_db = session.execute(
        select(filtered_logs.c.ip, func.count(filtered_logs.c.id))
        .group_by(filtered_logs.c.ip)
        .order_by(func.count(filtered_logs.c.id).desc())
        .limit(5)
    ).all()
    top_ips = [{"ip": ip, "requests": requests} for ip, requests in top_ips_db]
    return top_ips


def get_endpoint_stats(session: Session, filtered_logs: CTE) -> list[dict]:
    st_code_cond = filtered_logs.c.status_code.between(400, 599)
    endpoint_stats_db = session.execute(
        select(
            filtered_logs.c.endpoint,
            func.count(filtered_logs.c.id).label("requests"),
            func.avg(filtered_logs.c.process_time).label("avg_time"),
            func.count().filter(st_code_cond).label("error_count")
        )
        .group_by(filtered_logs.c.endpoint)
        .order_by(func.count(filtered_logs.c.id).desc())
        .limit(5)
    ).all()
    endpoint_stats = [
        {
            "endpoint": endpoint,
            "requests": req,
            "avg_time": round(avg_time, 2),
            "errors_count": round(errors_count)
        }
        for endpoint, req, avg_time, errors_count in endpoint_stats_db
    ]
    return endpoint_stats


def api_key_filter_logs(api_key: int) -> CTE:
    return select(Log).where(Log.api_key_id == api_key).cte("filtered_logs")


def get_total_req(session: Session, filtered_logs: CTE) -> Optional[int]:
    return session.scalar(select(func.count()).select_from(filtered_logs))


def compute_summary(session: Session, api_key: APIKey
                    ) -> DashboardResponse:
    filtered_logs = api_key_filter_logs(api_key.id)

    total_requests = get_total_req(session, filtered_logs)

    if not total_requests:
        return EMPTY_DASHBOARD

    res_time_stats = get_res_time_stats(session, filtered_logs)
    error_rate = get_errors_rate(session, filtered_logs)

    return {  # type:ignore
        "summary": {
            "total_requests": total_requests,
            "unique_ips": get_unique_ips(session, filtered_logs),
            "avg_response_time": res_time_stats["avg"],
            "min_response_time": res_time_stats["min"],
            "max_response_time": res_time_stats["max"],
            "error_rate": error_rate
        },
        "method_usage": get_method_usage(session, filtered_logs),
        "endpoint_stats": get_endpoint_stats(session, filtered_logs),
        "status_codes": get_status_codes(session, filtered_logs),
        "top_ips": get_top_ips(session, filtered_logs),
        "time_series": get_time_series(session, filtered_logs)
    }
