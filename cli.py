import typer
import csv
import os
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from rich.console import Console
from server.models import APIKey, User, Log, engine
from server.auth import get_password_hash


console = Console()


def load_logs():
    with Session(engine) as session:
        # create_user
        user = User(username="test_user", hashed_password=get_password_hash("testpassword"))
        session.add(user)
        session.flush()
        console.print("Test user created", style="bold green")

        # create api_key
        session.add(APIKey(api_key="test_key", user_id=user.id))
        session.flush()
        console.print("Test API key created", style="bold green")

        # load_logs
        logs_path = Path(__file__).resolve().parent / 'fixtures' / 'logs.csv'
        with open(logs_path, 'r') as file:
            reader = csv.DictReader(file)
            for row in reader:
                session.add(Log(
                    created_at=datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S"),
                    method=row['method'],
                    endpoint=row['endpoint'],
                    ip=row['ip'] or None,
                    process_time=float(row['process_time']),
                    status_code=int(row['status_code']),
                    api_key_id=user.id
                ))
        session.commit()
        log_count = session.execute(select(func.count(Log.id)
                                           ).where(Log.api_key_id == user.id)
                                    ).scalar_one()
        console.print(f"{log_count} test logs created", style="bold green")


if __name__ == "__main__":
    typer.run(load_logs)
