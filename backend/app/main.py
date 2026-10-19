"""HTTP entry point. Domain modules must not import this module."""

import hashlib
import json
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, cast

from dotenv import dotenv_values
from fastapi import FastAPI, Response
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.types import ExceptionHandler

from app.api import (
    request_id_middleware,
    request_validation_error,
    router,
)
from app.assessment.build_config import build_limits_from_environment
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
from app.runtime import default_data_dir
from app.schemas import (
    AssessmentExport,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    ErrorResponse,
    LivenessResponse,
    ProviderVerification,
    ReadinessResponse,
    RunRecord,
)
from app.schemas.builds import BuildList, BuildRecord, BuildRequest
from app.storage import LocalStore, StorageError


def _register_openapi_schemas(application: FastAPI, models: tuple[type[BaseModel], ...]) -> None:
    """Merge request/response contract models into components so every $ref resolves."""
    base_openapi = application.openapi

    def openapi() -> dict[str, Any]:
        spec = base_openapi()
        components = spec.setdefault("components", {}).setdefault("schemas", {})
        for model in models:
            schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
            pending = [schema.pop("$defs", {})]
            components.setdefault(model.__name__, schema)
            while pending:
                for name, subschema in pending.pop().items():
                    components.setdefault(
                        name, {key: value for key, value in subschema.items() if key != "$defs"}
                    )
                    if "$defs" in subschema:
                        pending.append(subschema["$defs"])
        return spec

    application.openapi = openapi  # type: ignore[method-assign]


def _provider_status(application: FastAPI, provider_detail: str | None) -> ProviderVerification:
    """Report the last explicit verification; readiness never calls the provider."""
    settings = application.state.openai_settings
    if settings is None:
        return ProviderVerification(detail=provider_detail)
    configured = dict(
        backend=settings.backend,
        transport=settings.transport,
        endpoint_sha256=hashlib.sha256(settings.base_url.encode()).hexdigest(),
        model_id=settings.model,
    )
    record_path = Path(application.state.data_dir) / "provider-verification.json"
    try:
        record = ProviderVerification.model_validate_json(record_path.read_bytes())
    except (OSError, ValidationError):
        record = None
    if record is None or record.status.value == "unverified":
        return ProviderVerification(**configured, detail=provider_detail)
    if record.model_id != settings.model:
        return ProviderVerification(
            **configured, detail=f"Last verification was for a different model ({record.model_id})."
        )
    if any(getattr(record, key) != value for key, value in configured.items()):
        return ProviderVerification(
            **configured,
            detail="Last verification does not match the active connection configuration.",
        )
    return record


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
        data_dir = default_data_dir()
    if env_file is None:
        env_file = Path(".env")
    if parser_config is None:
        parser_config = NativePdfConfig()
    if limits is None:
        values = dotenv_values(env_file) if env_file.is_file() else {}
        raw_timeout = os.environ.get(
            "AIRA_WORKFLOW_STAGE_TIMEOUT_SECONDS",
            values.get("AIRA_WORKFLOW_STAGE_TIMEOUT_SECONDS") or "90",
        ).strip()
        limits = WorkflowLimits(stage_timeout_seconds=float(raw_timeout))
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
        openai_settings: OpenAISettings | None = None
        if active_interpreter is None:
            try:
                openai_settings = OpenAISettings.from_environment(env_file=env_file)
            except ValidationError:
                missing.append("Server configuration needs OPENAI_API_KEY and AIRA_MODEL.")
            else:
                adapter = OpenAIAdapter(openai_settings)
                active_interpreter = OpenAIStageInterpreter(adapter)
                active_configuration = openai_configuration(
                    openai_settings, workflow_parser_fingerprint(parser_config, limits)
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
                build_limits=build_limits_from_environment(
                    env_file=env_file,
                    output_tokens=active_configuration.inference.max_output_tokens,
                    call_timeout_seconds=limits.stage_timeout_seconds,
                ),
            )
            await engine.start()
        application.state.store = store
        application.state.engine = engine
        application.state.missing_prerequisites = missing
        application.state.parser_config = parser_config
        application.state.data_dir = data_dir
        application.state.openai_settings = openai_settings
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
    _register_openapi_schemas(
        application,
        (
            CreateAssessmentRequest,
            ErrorResponse,
            RunRecord,
            AssessmentExport,
            BuildRecord,
            BuildRequest,
            BuildList,
        ),
    )

    @application.get("/v1/models")
    async def models() -> Response:
        """OpenAI-style discovery for the one configured model. No provider call."""
        settings = application.state.openai_settings
        data = (
            []
            if settings is None
            else [
                {
                    "id": settings.model,
                    "object": "model",
                    "created": 0,
                    "owned_by": settings.backend,
                }
            ]
        )
        return Response(
            content=json.dumps({"object": "list", "data": data}),
            media_type="application/json",
        )

    @application.get("/health", responses={200: {"model": LivenessResponse}})
    @application.get("/health/live", responses={200: {"model": LivenessResponse}})
    async def live() -> Response:
        return Response(
            content=LivenessResponse().model_dump_json(),
            media_type="application/json",
        )

    @application.get(
        "/health/ready",
        responses={200: {"model": ReadinessResponse}, 503: {"model": ReadinessResponse}},
    )
    async def ready() -> Response:
        missing = list(application.state.missing_prerequisites)
        engine = application.state.engine
        if engine is not None and engine.fatal_error is not None:
            missing.append(engine.fatal_error.message)
        if engine is not None and engine.builds.fatal_error is not None:
            missing.append(engine.builds.fatal_error.message)
        if engine is None and not missing:
            missing.append("Assessment processing is not configured.")
        body = ReadinessResponse(
            ready=not missing,
            missing_prerequisites=tuple(missing),
            provider=_provider_status(application, provider_detail),
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
