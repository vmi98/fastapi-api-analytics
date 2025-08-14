from typing import Annotated, Dict, List

from fastapi import Depends
from pydantic import BaseModel
from sqlmodel import Field, Session, SQLModel, create_engine

class APIKey(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    api_key: str


class LogBase(SQLModel):
    created_at: str
    method: str
    endpoint: str
    ip: str | None = None
    process_time: float
    status_code: int


class LogInput(LogBase):
    pass


class LogOutput(LogBase):
    id: int


class Log(LogBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    api_key_id: int | None = Field(foreign_key="apikey.id")


class SummaryModel(BaseModel):
    total_requests: int | None = None
    unique_ips: int | None = None
    avg_response_time: float | None = None
    min_response_time: float | None = None
    max_response_time: float | None = None
    error_rate: float | None = None


class EndpointStatsEntry(BaseModel):
    endpoint: str | None = None
    requests: int | None = None
    avg_time: float | None = None
    errors_count: int | None = None


class TopIpEntry(BaseModel):
    ip: str | None = None
    requests: int | None = None


class TimeSeriesEntry(BaseModel):
    timestamp: str | None = None
    requests: int | None = None
    avg_time: float | None = None
    error_rate: float | None = None


class DashboardResponse(SQLModel):
    summary: SummaryModel
    method_usage: Dict[str, int]
    endpoint_stats: List[EndpointStatsEntry]
    status_codes: Dict[int, int]
    top_ips: List[TopIpEntry]
    time_series: List[TimeSeriesEntry]


sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True) #remove in prod


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
