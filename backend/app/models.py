from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """A stored timestamp read as UTC.

    SQLite keeps no offset, so a value that round-tripped through the database
    comes back naive while a freshly written one is still aware. Both mean the
    same instant; normalising where they are compared keeps that true without a
    custom column type, and keeps one definition of the rule.
    """

    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    requirements: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    missing_information: Mapped[list[str]] = mapped_column(JSON, default=list)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list)
    source_resume_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(32))
    source_name: Mapped[str] = mapped_column(String(255))
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text)
    employment_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    salary_min: Mapped[int | None] = mapped_column(nullable=True)
    salary_max: Mapped[int | None] = mapped_column(nullable=True)
    salary_period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    source_name: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    verification_status: Mapped[str] = mapped_column(
        String(32), default="pending_verification"
    )
    # Identity of the posting across platforms, filled on ingest. Nullable so
    # rows created before the column existed stay valid and simply never dedupe.
    dedupe_key: Mapped[str | None] = mapped_column(
        String(512), unique=True, index=True, nullable=True
    )
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When the source page was last checked by a machine. Separate from
    # ``last_verified_at`` on purpose: a 200 says the page exists, not that the
    # posting is open, so the two can never share a field.
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class JobMatch(Base):
    __tablename__ = "job_matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("user_profiles.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float)
    match_points: Mapped[list[str]] = mapped_column(JSON, default=list)
    gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float)
    unknowns: Mapped[list[str]] = mapped_column(JSON, default=list)
    # What each requirement contributed. Stored with the match because the
    # explanation has to survive the request that produced it: a ranking read
    # back tomorrow without its breakdown is a number nobody can defend.
    breakdown: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # The shortfall against the posting's stated musts, stored next to the match
    # because it is what a user reads before applying. It is not part of the
    # score, and only breaks a tie when two postings rank the same.
    must_gaps: Mapped[list[str]] = mapped_column(JSON, default=list)
    must_coverage: Mapped[float] = mapped_column(Float, default=0.0)
    score_source: Mapped[str] = mapped_column(String(16), default="heuristic")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class StoredRequirementSet(Base):
    """A posting's requirements, read once and keyed by its text.

    Keyed by hash rather than by job id because the same posting appears more
    than once (re-posted, mirrored, collected twice), and paying a model call
    for each copy would turn reproducibility into an accident of timing.

    ``extractor_version`` is part of the key on purpose: a new prompt makes
    different requirements, and silently reusing the old ones would leave the
    cache looking trustworthy while the code it describes has changed.
    """

    __tablename__ = "job_requirement_sets"
    __table_args__ = (
        UniqueConstraint(
            "jd_hash", "extractor_version", name="ux_job_requirement_sets_text"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    jd_hash: Mapped[str] = mapped_column(String(64), index=True)
    extractor_version: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class InterviewSession(Base):
    """One mock interview: what it planned, what it asked, what was answered.

    The requirement set is copied in rather than referenced. Replaying a
    finished interview must not change when the extractor prompt changes and
    the cache is rebuilt, and "what was it asked against" is part of the record.

    ``turns`` always ends with the question currently on screen, unanswered.
    Storing it before the answer arrives is what makes "answer this" an
    operation on the session rather than the client echoing a question back.
    """

    __tablename__ = "interview_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_profile_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    max_turns: Mapped[int] = mapped_column(default=8)
    requirements: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    turns: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    finish_reason: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The review, once someone asks for it. Stored rather than recomputed: the
    # same conversation should not be judged differently on a second visit, and
    # a stored review is what makes the suggestions reviewable later.
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class Product(Base):
    """What something costs. The only place a price is written down.

    Prices are rows, not constants in the frontend: a page that hard-codes 99
    keeps showing 99 the day the price book changes, and then the number the
    user agreed to pay is not the number on the invoice.
    """

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    price_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    unit: Mapped[str] = mapped_column(String(16), default="份")
    # What one unit entitles the buyer to, and what a delivery is recorded as:
    # "resume" or "interview". Keeping it on the product is what lets the
    # delivery endpoint derive the kind instead of trusting the caller.
    grants: Mapped[str] = mapped_column(String(32), default="resume")
    features: Mapped[list[str]] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Order(Base):
    """What someone agreed to pay. The amount is computed, never received."""

    __tablename__ = "orders"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "idempotency_key", name="ux_orders_idempotency"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    product_code: Mapped[str] = mapped_column(String(64), index=True)
    quantity: Mapped[int] = mapped_column(default=1)
    # Stored, not recomputed at read time: the price a user agreed to must not
    # change when the price book does.
    amount_cents: Mapped[int] = mapped_column(default=0)
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    status: Mapped[str] = mapped_column(String(16), default="created")
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # A retried request must not become a second order. Nullable, because a
    # caller that sends nothing still gets a plain order; SQLite allows many
    # NULLs under a unique index.
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Delivery(Base):
    """What the buyer actually got for an order: a resume or an interview."""

    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    ref_id: Mapped[str] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class JobFitAnalysis(Base):
    __tablename__ = "job_fit_analyses"

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
