from .models import LogInput
from sqlmodel import Field, Session, SQLModel, create_engine, select, func


def compute_summary(session):
    max_time = session.exec(select(func.max(LogInput.process_time))).one()
    min_time = session.exec(select(func.min(LogInput.process_time))).one()
    avg_time = session.exec(select(func.avg(LogInput.process_time))).one()
    return {
        'max_process_time': max_time,
        'min_process_time': min_time,
        'avg_process_time': avg_time
    }
