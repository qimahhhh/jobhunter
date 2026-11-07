from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

logger = logging.getLogger(__name__)

_UNIQUE_PROFILE_INDEX = "ux_user_profiles_user_id"


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ai_job_hunter.db")
engine_kwargs: dict[str, object] = {"future": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _columns(inspector: Any, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def _has_unique_index(inspector: Any, table: str, column: str) -> bool:
    """True when the column already carries a single-column unique index.

    A fresh database gets one from ``create_all`` because the model declares
    ``unique=True``; only older databases need the index created by hand.
    """

    return any(
        index.get("unique") and index.get("column_names") == [column]
        for index in inspector.get_indexes(table)
    )


def _migrate_jobs(inspector: Any) -> None:
    """Databases created before the employment type column need it added."""

    if "employment_type" in _columns(inspector, "jobs"):
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE jobs ADD COLUMN employment_type VARCHAR(32)")
        )


def _migrate_user_profiles(inspector: Any) -> None:
    """Keep the gaps a draft reported, and allow one profile per user.

    ``create_all`` only creates missing tables, so a database that already
    exists keeps its old shape: the column has to be added here. The unique
    index is best effort, because a database that already holds two profiles
    for the same user cannot take it, and refusing to start would be worse than
    a warning the developer can act on.
    """

    if "missing_information" not in _columns(inspector, "user_profiles"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE user_profiles "
                    "ADD COLUMN missing_information JSON DEFAULT '[]'"
                )
            )

    if _has_unique_index(inspector, "user_profiles", "user_id"):
        return

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {_UNIQUE_PROFILE_INDEX} "
                    "ON user_profiles (user_id)"
                )
            )
    except IntegrityError:
        logger.warning(
            "user_profiles already holds duplicate user_id rows; "
            "unique index %s was not created",
            _UNIQUE_PROFILE_INDEX,
        )


def init_db() -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "jobs" in tables:
        _migrate_jobs(inspector)
    if "user_profiles" in tables:
        _migrate_user_profiles(inspector)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
