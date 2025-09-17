from __future__ import annotations
import os
from typing import Annotated, Optional
from datetime import datetime

from fastapi import Depends
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session
from sqlalchemy import String, Integer, Float, DateTime, CheckConstraint, ForeignKey, create_engine


class Base(DeclarativeBase):
    pass


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    api_key: Mapped[str] = mapped_column(String(64), unique=True)

    api_logs: Mapped[list[Log]] = relationship(back_populates="api_key",
                                               cascade="all, delete-orphan")


class Log(Base):
    __tablename__ = "api_logs"
    __table_args__ = (
        CheckConstraint('process_time >= 0', name='process_time_positive'),
        CheckConstraint('status_code BETWEEN 100 AND 599', name='check_status_code_range'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    method: Mapped[str] = mapped_column(String(200))
    endpoint: Mapped[str] = mapped_column(String(200))
    ip: Mapped[Optional[str]] = mapped_column(String(45), default=None)
    process_time: Mapped[float] = mapped_column(Float(precision=6))
    status_code: Mapped[int] = mapped_column(Integer)

    api_key_id: Mapped[int] = mapped_column(ForeignKey("api_keys.id"))
    api_key: Mapped[APIKey] = relationship(back_populates="api_logs")


sqlite_file_name = "database.db"
sqlite_url = f"sqlite:////app/db/{sqlite_file_name}"

engine = create_engine(sqlite_url, echo=True)


def create_db_and_tables():
    if os.getenv("TESTING") == "1":
        return
    Base.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
