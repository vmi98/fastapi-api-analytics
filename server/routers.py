import json
from io import BytesIO
from typing import Annotated, Literal
from datetime import datetime, time

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select


from .auth import get_api_key, get_current_user
from .models import (
    APIKey, Log, SessionDep
)
from .schemas import (LogInput, LogOutput, DashboardResponse, UserInDB,
                      TimeSeriesParam, FilterParams)
from .services import (compute_summary, build_log_filters, get_report_data,
                       build_report_json, build_report_pdf)


router = APIRouter()


@router.post("/track", status_code=status.HTTP_200_OK)
def create_log(log: LogInput,
               session: SessionDep,
               api_key: APIKey = Depends(get_api_key)
               ) -> Response:
    db_log = Log(**log.model_dump(), api_key_id=api_key.id)
    session.add(db_log)
    session.commit()
    return Response(status_code=status.HTTP_200_OK)


@router.get("/dashboard", response_model=DashboardResponse)
def show_dashboard(session: SessionDep,
                   time_series: TimeSeriesParam = Depends(),
                   api_key: APIKey = Depends(get_api_key),
                   user: UserInDB = Depends(get_current_user)
                   ) -> DashboardResponse:
    summary_data = compute_summary(session, api_key, time_series)
    return summary_data


@router.get("/raw_logs", response_model=list[LogOutput])
def show_raw_logs(session: SessionDep,
                  filter_query: FilterParams = Depends(),
                  api_key: APIKey = Depends(get_api_key),
                  user: UserInDB = Depends(get_current_user)
                  ) -> list[LogOutput]:
    conditions = build_log_filters(filter_query, api_key.id)
    st = (select(Log).where(*conditions)
                     .order_by(filter_query.order_by)
                     .offset(filter_query.offset)
                     .limit(filter_query.limit))
    logs = session.scalars(st).all()

    if not logs:
        return []
    return logs


@router.get("/report")
def download_report(session: SessionDep,
                    format: Literal["json", "pdf"],
                    time_series: TimeSeriesParam = Depends(),
                    api_key: APIKey = Depends(get_api_key),
                    user: UserInDB = Depends(get_current_user)
                    ) -> Response:
    report_data = get_report_data(session, api_key, time_series)
    mapping = {
        'json': build_report_json,
        'pdf': build_report_pdf
    }
    report_file = mapping[format](report_data)
    headers = {"Content-Disposition": f'attachment; filename="api_stats_report.{format}"',
               "Cache-Control": "no-store"}
    return Response(report_file,
                    media_type="application/json",
                    headers=headers)
