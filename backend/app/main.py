"""HTTP entry point. Domain modules must not import this module."""

import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.types import ExceptionHandler

from app.api import (
    request_id_middleware,
    request_validation_error,
    router,
)
from app.assessment.stages import StageInterpreter
from app.assessment.workflow import (
    WorkflowEngine,
    WorkflowLimits,
    workflow_parser_fingerprint,
)
from app.documents import NativePdfConfig
from app.llm.config import OpenAISettings
from app.llm.interpreter import OpenAIStageInterpreter, openai_configuration
from app.llm.openai_adapter import OpenAIAdapter
from app.schemas import (
    ConfigurationProvenance,
    LivenessResponse,
    ProviderVerification,
    ReadinessResponse,
)
from app.storage import LocalStore, StorageError


def create_app(
    *,
    frontend_dir: Path | None = None,
    data_dir: Path | None = None,
    env_file: Path | None = None,
    interpreter: StageInterpreter | None = None,
    configuration: ConfigurationProvenance | None = None,
    parser_config: NativePdfConfig | None = None,
    limits: WorkflowLimits | None = None,
    provider_detail: str | None = None,
) -> FastAPI:
    """Wire the store, interpreter, and engine at lifespan start; no model calls."""
    if data_dir is None:
        data_dir = Path(
            os.environ.get(
                "AIRA_DATA_DIR",
                Path(__file__).resolve().parents[2] / "data" / "app",
            )
        )
    if env_file is None:
        env_file = Path(".env")
    if parser_config is None:
        parser_config = NativePdfConfig()
    if limits is None:
        limits = WorkflowLimits()
    if interpreter is not None and configuration is None:
        raise ValueError("An injected interpreter requires explicit configuration")

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        missing: list[str] = []
        store: LocalStore | None = None
        adapter: OpenAIAdapter | None = None
        engine: WorkflowEngine | None = None
        try:
            store = LocalStore(data_dir)
        except (OSError, sqlite3.Error, StorageError):
            missing.append(f"The local data directory is not writable: {data_dir}.")
        active_interpreter = interpreter
        active_configuration = configuration
        if active_interpreter is None:
            try:
                settings = OpenAISettings.from_environment(env_file=env_file)
            except ValidationError:
                missing.append("Server configuration needs OPENAI_API_KEY and AIRA_MODEL.")
            else:
                adapter = OpenAIAdapter(settings)
                active_interpreter = OpenAIStageInterpreter(adapter)
                active_configuration = openai_configuration(
                    settings, workflow_parser_fingerprint(parser_config, limits)
                )
        if (
            store is not None
            and active_interpreter is not None
            and active_configuration is not None
        ):
            engine = WorkflowEngine(
                store,
                active_interpreter,
                active_configuration,
                parser_config=parser_config,
                limits=limits,
            )
            await engine.start()
        application.state.store = store
        application.state.engine = engine
        application.state.missing_prerequisites = missing
        application.state.parser_config = parser_config
        try:
            yield
        finally:
            if engine is not None:
                await engine.close()
            if adapter is not None:
                await adapter.close()

    application = FastAPI(title="Aira", version="0.1.0", lifespan=lifespan)
    application.middleware("http")(request_id_middleware)
    # Starlette dispatches handlers by the registered class, so the narrower
    # exception parameter is safe at runtime. Generic Exception handlers belong
    # to ServerErrorMiddleware outside this stack; /api unexpected failures are
    # enveloped inside request_id_middleware instead.
    application.add_exception_handler(
        RequestValidationError, cast(ExceptionHandler, request_validation_error)
    )
    application.include_router(router)

    @application.get("/health/live")
    async def live() -> Response:
        return Response(
            content=LivenessResponse().model_dump_json(),
            media_type="application/json",
        )

    @application.get("/health/ready")
    async def ready() -> Response:
        missing = list(application.state.missing_prerequisites)
        engine = application.state.engine
        if engine is not None and engine.fatal_error is not None:
            missing.append(engine.fatal_error.message)
        if engine is None and not missing:
            missing.append("Assessment processing is not configured.")
        body = ReadinessResponse(
            ready=not missing,
            missing_prerequisites=tuple(missing),
            provider=ProviderVerification(detail=provider_detail),
        )
        return Response(
            status_code=200 if body.ready else 503,
            content=body.model_dump_json(),
            media_type="application/json",
        )

    if frontend_dir is None:
        configured = os.environ.get("AIRA_FRONTEND_DIR")
        default_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
        frontend_dir = Path(configured) if configured else default_dir
    if (frontend_dir / "index.html").is_file():
        application.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")

    return application


app = create_app()
