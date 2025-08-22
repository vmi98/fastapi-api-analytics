from typing import List
from fastapi import Depends
from sqlmodel import select, func, distinct, cast, Session, Float
from sqlalchemy import func
from sqlalchemy.sql.expression import CTE


from .auth import get_api_key
from .models import Log, APIKey, DashboardResponse

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


def get_time_series(session: Session, api_filtered: CTE) -> List[dict]:
    st_code_cond = api_filtered.c.status_code.between(400, 599)
    time_series_db = session.exec(
                select(
                    func.strftime('%Y-%m-%d', api_filtered.c.created_at
                                  ).label("timestamp"),
                    func.count(api_filtered.c.id).label("requests"),
                    func.avg(api_filtered.c.process_time).label("avg_time"),
                    (func.count().filter(st_code_cond) /
                        cast(func.count(api_filtered.c.id), Float
                             )).label('error_rate')
                )
                .group_by(func.strftime('%Y-%m-%d', api_filtered.c.created_at))
                .order_by(func.strftime('%Y-%m-%d', api_filtered.c.created_at))
                .limit(5)
        ).all()

    time_series = [
        {
            "timestamp": ts,
            "requests": req,
            "avg_time": round(avg, 2),
            "error_rate": round(rate, )
        }
        for ts, req, avg, rate in time_series_db
    ]

    return time_series


def get_res_time_stats(session: Session, api_filtered: CTE
                       ) -> dict[str, float]:
    stmt = select(
        func.min(api_filtered.c.process_time),
        func.avg(api_filtered.c.process_time),
        func.max(api_filtered.c.process_time)
    )
    min_time, avg_time, max_time = session.exec(stmt).one()

    if all([min_time, avg_time, max_time]):
        return {
            "min": round(min_time, 2),
            "avg": round(avg_time, 2),
            "max": round(max_time, 2),
        }
    else:
        return {"min": 0, "avg": 0, "max": 0}


def get_unique_ips(session: Session, api_filtered: CTE
                   ) -> int:
    statement = select(func.count(distinct(api_filtered.c.ip)))
    unique_ips = session.exec(statement).one()
    return unique_ips


def get_errors_rate(session: Session, api_filtered: CTE, total_requests: int
                    ) -> float:
    errors = session.exec(
            select(func.count(api_filtered.c.id))
            .where(api_filtered.c.status_code.between(400, 599))
            ).one()
    if total_requests:
        errors_per_100_req = (errors / total_requests) * 100
    else:
        errors_per_100_req = 0
    return round(errors_per_100_req, 2)


def get_method_usage(session: Session, api_filtered: CTE
                     ) -> dict[str, int]:
    method_usage = {
                method: count
                for method, count in session.exec(
                    select(api_filtered.c.method, func.count(api_filtered.c.id)
                           ).group_by(api_filtered.c.method)
                ).all()
            }
    return method_usage


def get_status_codes(session: Session, api_filtered: CTE
                     ) -> dict[str, int]:
    status_codes = {
            status_code: count
            for status_code, count in session.exec(
                select(
                    api_filtered.c.status_code,
                    func.count(api_filtered.c.id)
                )
                .group_by(api_filtered.c.status_code)
            ).all()
        }
    return status_codes


def get_top_ips(session: Session, api_filtered: CTE
                ) -> list[dict]:
    top_ips_db = session.exec(
                select(api_filtered.c.ip, func.count(api_filtered.c.id))
                .group_by(api_filtered.c.ip)
                .order_by(func.count(api_filtered.c.id).desc())
                .limit(5)
        ).all()
    top_ips = [{"ip": ip, "requests": requests} for ip, requests in top_ips_db]
    return top_ips


def get_endpoint_stats(session: Session, api_filtered: CTE
                       ) -> list[dict]:
    st_code_cond = api_filtered.c.status_code.between(400, 599)
    endpoint_stats_db = session.exec(
                    select(
                        api_filtered.c.endpoint,
                        func.count(api_filtered.c.id).label("requests"),
                        func.avg(api_filtered.c.process_time
                                 ).label("avg_time"),
                        func.count().filter(st_code_cond).label("error_count")
                    )
                    .group_by(api_filtered.c.endpoint)
                    .order_by(func.count(api_filtered.c.id).desc())
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


def compute_summary(session, api_key: APIKey = Depends(get_api_key)
                    ) -> DashboardResponse:
    api_filtered = select(Log).where(Log.api_key_id == api_key.id
                                     ).cte("filtered_logs")

    total_requests = session.exec(
        select(func.count()).select_from(api_filtered)
        ).one()

    if not total_requests:
        return EMPTY_DASHBOARD

    res_time_stats = get_res_time_stats(session, api_filtered)
    error_rate = get_errors_rate(session, api_filtered, total_requests)

    return {
            "summary": {
                "total_requests": total_requests,
                "unique_ips": get_unique_ips(session, api_filtered),
                "avg_response_time": res_time_stats["avg"],
                "min_response_time": res_time_stats["min"],
                "max_response_time": res_time_stats["max"],
                "error_rate": error_rate
            },
            "method_usage": get_method_usage(session, api_filtered),
            "endpoint_stats": get_endpoint_stats(session, api_filtered),
            "status_codes": get_status_codes(session, api_filtered),
            "top_ips": get_top_ips(session, api_filtered), 
            "time_series": get_time_series(session, api_filtered)
            }
