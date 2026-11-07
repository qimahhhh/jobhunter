from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .schemas import EmploymentType, JobFitRequest, JobFitResponse, JobInput


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)


class UserRead(UserCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    updated_at: datetime


class UserRequirements(BaseModel):
    desired_role: str = Field(min_length=1)
    locations: list[str] = Field(default_factory=list)
    employment_type: EmploymentType = "internship"
    salary_min: int | None = None
    salary_max: int | None = None
    skill_level: str | None = None


class CapabilityProfile(BaseModel):
    summary: str = Field(min_length=1)
    skills: list[str] = Field(default_factory=list)
    experiences: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)


class ProfileCreate(BaseModel):
    user_id: str
    requirements: UserRequirements
    capabilities: CapabilityProfile


class ProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    requirements: UserRequirements
    capabilities: CapabilityProfile
    created_at: datetime
    updated_at: datetime


class ResumeCreate(BaseModel):
    user_id: str
    source_type: Literal["text", "pdf", "docx", "image", "repository"] = "text"
    source_name: str = Field(min_length=1, max_length=255)
    content: dict[str, Any] = Field(default_factory=dict)


class ResumeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    source_type: str
    source_name: str
    content: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    requirements: str = Field(min_length=1)
    employment_type: EmploymentType
    location: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    source_name: str = Field(min_length=1, max_length=255)
    source_url: str | None = None


class JobRead(JobCreate):
    model_config = ConfigDict(from_attributes=True)

    employment_type: EmploymentType | None = None
    id: str
    verification_status: str
    created_at: datetime
    updated_at: datetime


class JobInputRead(JobInput):
    employment_type: EmploymentType | None = None


class JobFitRequestRead(JobFitRequest):
    job: JobInputRead


class JobMatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_profile_id: str
    job_id: str


class JobMatchRead(JobMatchCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    score: float
    match_points: list[str]
    gaps: list[str]
    recommendation: str
    confidence: float
    created_at: datetime


class JobFitAnalysisRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: str
    request: JobFitRequestRead
    result: JobFitResponse
    created_at: datetime
