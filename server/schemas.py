from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import re
from datetime import datetime, date
from typing import Literal


NULLABLE_VALUES = {"", " ", "null", "NULL", "None"}


def clean_string(s: str) -> str | None:
    if not s or s in NULLABLE_VALUES:
        return None
    cleaned = re.sub(r"[\x00-\x1F\x7F]", "", s)
    return cleaned.strip() if cleaned else None


class LogBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra='forbid')

    created_at: datetime = Field(...)
    method: str = Field(..., max_length=200)
    endpoint: str = Field(..., min_length=1, max_length=200)
    ip: str | None = Field(None, min_length=7, max_length=45)
    process_time: float = Field(..., ge=0)
    status_code: int = Field(..., ge=100, le=599)


class LogOutput(LogBase):
    id: int

    @field_validator("process_time", mode="after")
    def round_process_time(cls, value):
        return round(value, 2)


class LogInput(LogBase):

    @model_validator(mode='before')
    def sanitize_log(cls, values):
        if isinstance(values, dict):
            for key in ("endpoint", "ip", "method"):
                value = values.get(key)
                if isinstance(value, str):
                    values[key] = clean_string(value)
        return values

    @field_validator('method', mode='before')
    def validate_method(cls, value):
        if not isinstance(value, str):
            raise ValueError("Invalid input")

        if not re.match(r"^(GET|POST|PUT|DELETE|PATCH|OPTIONS)$", value):
            raise ValueError("Invalid method")
        return value

    @field_validator("created_at", mode="before")
    def normalize_datetime(cls, value):
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except Exception:
                raise ValueError("created_at must be a valid datetime string")
        elif isinstance(value, datetime):
            return value
        else:
            raise ValueError("created_at must be ISO datetime string or datetime object")
        return value


class SummaryModel(BaseModel):
    total_requests: int | None = None
    unique_ips: int | None = None
    avg_response_time: float | None = None
    min_response_time: float | None = None
    max_response_time: float | None = None
    error_rate: float | None = None

    @model_validator(mode='after')
    def round_values(cls, values):
        for field in ("avg_response_time", "min_response_time",
                      "max_response_time", "error_rate"):
            val = getattr(values, field)
            if val:
                setattr(values, field, round(val, 2))
        return values


class EndpointStatsEntry(BaseModel):
    endpoint: str | None = None
    requests: int | None = None
    avg_time: float | None = None
    errors_count: int | None = None

    @model_validator(mode='after')
    def round_values(cls, values):
        if values.avg_time:
            values.avg_time = round(values.avg_time, 2)
        return values


class TopIpEntry(BaseModel):
    ip: str | None = None
    requests: int | None = None


class TimeSeriesEntry(BaseModel):
    timestamp: str | None = None
    requests: int | None = None
    avg_time: float | None = None
    error_rate: float | None = None

    @model_validator(mode='after')
    def round_values(cls, values):
        if values.avg_time:
            values.avg_time = round(values.avg_time, 2)
        if values.error_rate:
            values.error_rate = round(values.error_rate, 2)
        return values


class DashboardResponse(BaseModel):
    summary: SummaryModel
    method_usage: dict[str, int]
    endpoint_stats: list[EndpointStatsEntry]
    status_codes: dict[int, int]
    top_ips: list[TopIpEntry]
    time_series: list[TimeSeriesEntry]


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None


class UserOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    username: str


class UserInDB(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    hashed_password: str


class RegisterForm(BaseModel):
    model_config = {"extra": "forbid"}
    username: str
    password: str


class TimeSeriesParam(BaseModel):
    period: Literal["minutely", "hourly", "daily", "weekly", "monthly"] = "daily"
    start_date: date
    end_date: date

    @model_validator(mode='after')
    def check_dates(cls, values):
        if values.start_date >= values.end_date:
            raise ValueError('Start date must be before end date')
        return values


class FilterParams(BaseModel):
    limit: int = Field(100, gt=0, le=100)
    offset: int = Field(0, ge=0)
    order_by: Literal["created_at", "method", "endpoint", "ip",
                      "process_time", "status_code"] = "created_at"
    start_date: date | None = None
    end_date: date = date.today()
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", None] = None
    status_code: int | None = None
    endpoint: str | None = None
    ip: str | None = None
    process_time_min: float | None = None
    process_time_max: float | None = None

    @model_validator(mode='after')
    def check_dates(cls, values):
        if not values.start_date or not values.end_date:
            return values
        if values.start_date > values.end_date:
            raise ValueError('Start date must be before end date')
        return values

    @model_validator(mode='after')
    def check_time(cls, values):
        if not values.process_time_min or not values.process_time_max:
            return values

        if values.process_time_min >= values.process_time_max:
            raise ValueError('Min time must be less than max time')
