"""HTTP entry point. Domain modules must not import this module."""

import os
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


class Liveness(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["aira"] = "aira"


class Readiness(BaseModel):
    status: Literal["not_ready"] = "not_ready"
    reasons: list[str]
    provider_verification: Literal["unverified"] = "unverified"


def create_app(*, frontend_dir: Path | None = None) -> FastAPI:
    """Create the application without resolving credentials or contacting AWS."""
    application = FastAPI(title="Aira", version="0.1.0")

    @application.get("/health/live", response_model=Liveness)
    def live() -> Liveness:
        return Liveness()

    @application.get("/health/ready", responses={503: {"model": Readiness}})
    def ready() -> JSONResponse:
        # WP-01 intentionally exposes only a shell, never a fake assessment provider.
        result = Readiness(reasons=["Assessment processing is not available in this build."])
        return JSONResponse(status_code=503, content=result.model_dump(mode="json"))

    if frontend_dir is None:
        configured = os.environ.get("AIRA_FRONTEND_DIR")
        default_dir = Path(__file__).resolve().parents[2] / "frontend/dist"
        frontend_dir = Path(configured) if configured else default_dir
    if (frontend_dir / "index.html").is_file():
        application.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return application


app = create_app()
