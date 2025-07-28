from typing import Annotated

from fastapi import Depends
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
    api_key_id: int | None = Field(foreign_key='apikey.id')


class Summary(SQLModel):
    max_process_time: float | None = None
    min_process_time: float | None = None
    avg_process_time: float | None = None




sqlite_file_name = "database.db"
sqlite_url = f"sqlite:///{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True) #remove in prod


def create_db_and_tables():
    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
