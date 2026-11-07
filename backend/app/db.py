from __future__ import annotations

import os
from collections.abc import Iterator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_job_hunter.db")
engine_kwargs: dict[str, object] = {"future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    if "jobs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "employment_type" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE jobs ADD COLUMN employment_type VARCHAR(32)")
            )


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
