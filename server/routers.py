from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlmodel import select

from .auth import get_api_key
from .models import APIKey, Log, LogInput, LogOutput, SessionDep, Summary
from .services import compute_summary


router = APIRouter()


@router.post("/track", status_code=status.HTTP_200_OK)
def create_log(log: LogInput,
               session: SessionDep,
               api_key: APIKey = Depends(get_api_key)
               ) -> Response:
    db_log = Log(**log.dict(), api_key_id=api_key.id)
    session.add(db_log)
    session.commit()
    session.refresh(db_log)
    return Response(status_code=status.HTTP_200_OK)


@router.get("/dashboard")
def show_dashboard(session: SessionDep,
                   api_key: APIKey = Depends(get_api_key)
                   ) -> Summary:
    summary_data = compute_summary(session, api_key)
    return Summary(**summary_data)


@router.get("/raw_logs", response_model=list[LogOutput])
def show_raw_logs(session: SessionDep,
                  api_key: APIKey = Depends(get_api_key),
                  offset: int = 0,
                  limit: Annotated[int, Query(le=100)] = 100
                  ) -> list[LogOutput]:
    logs = session.exec(
        select(Log)
        .where(Log.api_key_id == api_key.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return logs
