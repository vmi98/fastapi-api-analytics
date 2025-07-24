'''
├── routers/
│   ├── tracking.py          # receives tracking data (POST /track)
│   └── dashboard.py         # serves summary data or frontend dashboard
'''
from fastapi import APIRouter, Response, status
from .services import compute_summary
from .models import LogInput, LogOutput, Summary, SessionDep
from sqlmodel import select
from typing import Annotated
from fastapi import Query


router = APIRouter()


@router.post("/track", status_code=status.HTTP_200_OK)
def create_log(log: LogInput, session: SessionDep) -> Response:
    session.add(log)
    session.commit()
    session.refresh(log)
    return Response(status_code=status.HTTP_200_OK)


@router.get("/dashboard")
def show_dashboard(session: SessionDep) -> Summary:
    summary_data = compute_summary(session)
    return Summary(**summary_data)


@router.get("/raw_logs", response_model=list[LogOutput])
def show_raw_logs(session: SessionDep,
                  offset: int = 0,
                  limit: Annotated[int, Query(le=100)] = 100
                  ) -> list[LogOutput]:
    logs = session.exec(select(LogInput).offset(offset).limit(limit)).all()
    return logs
