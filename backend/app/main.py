from __future__ import annotations

from contextlib import asynccontextmanager
import os
import re

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routers import health_router, router


def _cors_origin_pattern() -> str:
    configured_origins = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "").split(",")
        if origin.strip()
    ]
    local_frontend = r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?"
    if configured_origins:
        allowed_origins = "|".join(re.escape(origin) for origin in configured_origins)
        return rf"^(?:{allowed_origins})$"
    return rf"^(?:{local_frontend})$"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="AI-Job-Hunter API",
    version="0.1.0",
    description="Minimal FastAPI foundation for the hackathon MVP.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=_cors_origin_pattern(),
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(router, prefix="/api/v1", tags=["resources"])
app.include_router(health_router)
