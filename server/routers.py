from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select

from .auth import get_api_key, get_current_user
from .models import (
    APIKey, Log, SessionDep
)
from .schemas import LogInput, LogOutput, DashboardResponse, UserInDB, TimeSeriesParam
from .services import compute_summary


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


@router.get("/dashboard")
def show_dashboard(time_series: Annotated[TimeSeriesParam, Query()],
                   session: SessionDep,
                   api_key: APIKey = Depends(get_api_key),
                   user: UserInDB = Depends(get_current_user)
                   ) -> DashboardResponse:
    summary_data = compute_summary(session, api_key, time_series)
    return DashboardResponse(**summary_data)


@router.get("/raw_logs", response_model=list[LogOutput])
def show_raw_logs(session: SessionDep,
                  api_key: APIKey = Depends(get_api_key),
                  user: UserInDB = Depends(get_current_user),
                  offset: int = 0,
                  limit: Annotated[int, Query(le=100)] = 100
                  ) -> list[LogOutput]:
    logs = session.scalars(
        select(Log)
        .where(Log.api_key_id == api_key.id)
        .offset(offset)
        .limit(limit)
    ).all()
    if not logs:
        return []
    return logs
