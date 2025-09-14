from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
import re
from datetime import datetime


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


class LogOutput(LogBase):
    id: int

    @field_validator("process_time", mode="before")
    def round_process_time(cls, value):
        try:
            return round(float(value), 2)
        except Exception:
            raise ValueError("process_time must be a float")


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


class DashboardResponse(BaseModel):
    summary: SummaryModel
    method_usage: dict[str, int]
    endpoint_stats: list[EndpointStatsEntry]
    status_codes: dict[int, int]
    top_ips: list[TopIpEntry]
    time_series: list[TimeSeriesEntry]
