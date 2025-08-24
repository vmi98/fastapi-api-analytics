import re
from typing import Annotated, Dict, List, Optional
from datetime import datetime

from fastapi import Depends
from pydantic import BaseModel, field_validator, model_validator
from sqlmodel import Field, Session, SQLModel, create_engine

NULLABLE_VALUES = [None, "", " ", "null", "NULL", "None"]


def clean_string(s: str) -> str | None:
    if not s:
        return None
    cleaned = re.sub(r"[\x00-\x1F\x7F]", "", s)
    return cleaned.strip() if cleaned else None


class APIKey(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    api_key: str = Field(..., max_length=64)


class LogBase(SQLModel):
    created_at: datetime = Field(...)
    method: str = Field(..., max_length=200)
    endpoint: str = Field(..., min_length=1, max_length=200)
    ip: Optional[str] = Field(None, min_length=7, max_length=45)
    process_time: float = Field(..., ge=0)
    status_code: int = Field(..., ge=100, le=599)

    @model_validator(mode='before')
    def sanitize_log(cls, values):
        if values.get('endpoint'):
            values['endpoint'] = clean_string(values['endpoint'].lower())

        if values.get('ip'):
            values['ip'] = clean_string(values['ip'])

        return values

    @field_validator('method', mode='before')
    def validate_method(cls, value):
        if not isinstance(value, str):
            raise ValueError("Invalid method")

        if not re.match(r"^(GET|POST|PUT|DELETE|PATCH|OPTIONS)$", value):
            raise ValueError("Invalid method")
        return clean_string(value)

    @model_validator(mode='before')
    def not_null_check(cls, values):
        for k, v in values.items():
            if v in NULLABLE_VALUES and k != "ip":
                raise ValueError(f"{k} cannot be empty")
        return values

    @field_validator("created_at", mode="before")
    def normalize_datetime(cls, value):
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                raise ValueError("created_at must be a valid datetime string")
        else:
            raise ValueError("created_at must be ISO datetime string")
        return value


class LogOutput(LogBase):
    id: int


class Log(LogBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    api_key_id: int | None = Field(foreign_key="apikey.id")


class LogInput(LogBase):
    pass


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
sqlite_url = f"sqlite:////app/db/{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True)


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
