"""The data a mock interview is made of.

A session is a plan, a list of turns, and the requirement set it was built on.
The requirement set is copied into the session rather than referenced: replaying
a finished interview must not change when someone bumps the extractor version and
the cache is rebuilt, and "what was it asked against" is part of the record.

``turns`` holds one unanswered turn at the end — the question currently on
screen. Storing it before the answer arrives is what makes "answer this" an
operation on the session instead of the client echoing a question back, which
would let a caller answer something they were never asked.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InterviewStatus = Literal["in_progress", "finished"]


class InterviewStartRequest(BaseModel):
    profile_id: str
    job_id: str
    max_turns: int = Field(default=8, ge=2, le=20)


class InterviewAnswerRequest(BaseModel):
    answer: str = Field(min_length=1)


class InterviewTarget(BaseModel):
    """A question the plan intends to ask: which requirement, worded how."""

    requirement_id: str
    question: str = Field(min_length=1)
    why: str = ""


class InterviewPlan(BaseModel):
    opening: str = ""
    targets: list[InterviewTarget] = Field(default_factory=list)


class InterviewTurn(BaseModel):
    index: int
    kind: Literal["ask", "probe"] = "ask"
    requirement_id: str
    requirement_text: str = ""
    question: str = Field(min_length=1)
    why: str = ""
    answer: str | None = None


class InterviewSessionRead(BaseModel):
    """A session as the client sees it, including what is left to ask."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    profile_id: str
    job_id: str
    status: InterviewStatus
    max_turns: int
    plan: InterviewPlan
    turns: list[InterviewTurn] = Field(default_factory=list)
    remaining: list[str] = Field(default_factory=list)
    finish_reason: str = ""
    notes: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
