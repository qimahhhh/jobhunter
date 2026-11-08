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
_UNIQUE_JOB_INDEX = "ux_jobs_dedupe_key"

# Columns ``jobs`` grew after the first schema. ``ALTER TABLE`` in SQLite takes
# a constant definition, and an existing row simply keeps NULL / defaults.
_ADDED_JOB_COLUMNS = (
    ("employment_type", "VARCHAR(32)"),
    ("dedupe_key", "VARCHAR(512)"),
    ("last_seen_at", "DATETIME"),
    ("last_checked_at", "DATETIME"),
)

# Columns a stored profile grew after the first schema. ``ALTER TABLE`` in
# SQLite needs a constant default, and '[]' parses back into an empty list.
_ADDED_PROFILE_COLUMNS = (
    ("missing_information", "JSON DEFAULT '[]'"),
    ("evidence", "JSON DEFAULT '[]'"),
    ("source_resume_id", "VARCHAR(36)"),
)

# Columns ``job_matches`` grew once a score had to explain itself.
_ADDED_MATCH_COLUMNS = (
    ("breakdown", "JSON DEFAULT '[]'"),
    ("must_gaps", "JSON DEFAULT '[]'"),
    # A row written before the column existed holds NULL, which does not
    # validate as a float; 0.0 is also true of it, since its score was a plain
    # keyword coverage that never separated the must requirements out.
    ("must_coverage", "FLOAT DEFAULT 0.0"),
    # Defaulted rather than merely added: NULL does not validate as "extracted"
    # or "heuristic", and a score from before this column really was a keyword
    # coverage, so the default is also the truth.
    ("score_source", "VARCHAR(16) DEFAULT 'heuristic'"),
)

# Columns ``interview_sessions`` grew once a finished run could be reviewed.
_ADDED_INTERVIEW_COLUMNS = (("evaluation", "JSON DEFAULT '{}'"),)


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
    """Add the columns that let a posting be recognised when it reappears.

    The unique index is best effort: a database that already holds the same
    posting twice cannot take it, and refusing to start would be worse than a
    warning the developer can act on.
    """

    columns = _columns(inspector, "jobs")
    for name, definition in _ADDED_JOB_COLUMNS:
        if name in columns:
            continue
        with engine.begin() as connection:
            connection.execute(
                text(f"ALTER TABLE jobs ADD COLUMN {name} {definition}")
            )

    if _has_unique_index(inspector, "jobs", "dedupe_key"):
        return

    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {_UNIQUE_JOB_INDEX} "
                    "ON jobs (dedupe_key)"
                )
            )
    except IntegrityError:
        logger.warning(
            "jobs already holds duplicate postings; unique index %s was not created",
            _UNIQUE_JOB_INDEX,
        )


def _migrate_user_profiles(inspector: Any) -> None:
    """Add the columns that make a stored profile traceable.

    ``create_all`` only creates missing tables, so a database that already
    exists keeps its old shape and every column has to be added here. The
    unique index is best effort, because a database that already holds two
    profiles for the same user cannot take it, and refusing to start would be
    worse than a warning the developer can act on.
    """

    columns = _columns(inspector, "user_profiles")
    for name, definition in _ADDED_PROFILE_COLUMNS:
        if name in columns:
            continue
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE user_profiles ADD COLUMN {name} {definition}"
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


def _migrate_job_matches(inspector: Any) -> None:
    """Add the columns that keep a stored score explainable.

    A match computed before the column existed has no breakdown to show; the
    JSON default gives it an empty one, so an old row reads as "nothing to
    explain" instead of breaking the endpoint.
    """

    columns = _columns(inspector, "job_matches")
    for name, definition in _ADDED_MATCH_COLUMNS:
        if name in columns:
            continue
        with engine.begin() as connection:
            connection.execute(
                text(f"ALTER TABLE job_matches ADD COLUMN {name} {definition}")
            )


def _migrate_interview_sessions(inspector: Any) -> None:
    """Add the review column to a session table created before it existed."""

    columns = _columns(inspector, "interview_sessions")
    for name, definition in _ADDED_INTERVIEW_COLUMNS:
        if name in columns:
            continue
        with engine.begin() as connection:
            connection.execute(
                text(
                    f"ALTER TABLE interview_sessions ADD COLUMN {name} {definition}"
                )
            )


def init_db() -> None:
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "jobs" in tables:
        _migrate_jobs(inspector)
    if "user_profiles" in tables:
        _migrate_user_profiles(inspector)
    if "job_matches" in tables:
        _migrate_job_matches(inspector)
    if "interview_sessions" in tables:
        _migrate_interview_sessions(inspector)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
