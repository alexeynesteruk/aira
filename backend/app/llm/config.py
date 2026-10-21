"""Backend-only configuration. Reading settings never contacts a provider."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr

OFFICIAL_OPENAI_BASE_URL = "https://api.openai.com/v1"


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


class OpenAISettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1)
    model: str = Field(min_length=1, pattern=r"^\S+$")
    base_url: str = Field(default=OFFICIAL_OPENAI_BASE_URL, pattern=r"^https?://\S+$")
    backend: Literal["openai", "litellm", "openai_compatible", "custom"] = "openai"
    transport: Literal["responses", "chat_completions"] = "responses"
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    max_attempts: int = Field(default=2, ge=1, le=3)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    stage_timeout_seconds: float = Field(default=65.0, gt=0, le=1200)

    @classmethod
    def from_environment(
        cls, *, env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None
    ) -> "OpenAISettings":
        """Load server settings. The env file selects any OpenAI-compatible endpoint.

        A base URL or transport that appears only in the process environment does
        not redirect direct OpenAI. Setting a non-default ``AIRA_LLM_BACKEND`` (e.g.
        ``litellm``, ``openai_compatible``, or ``custom``) takes those values from the
        process environment instead.
        """
        values = dotenv_values(env_file) if env_file.is_file() else {}
        environment = os.environ if environ is None else environ

        def pick(name: str, default: str = "") -> str:
            if name in environment and _text(environment[name]):
                return _text(environment[name])
            return _text(values.get(name)) or default

        requested_backend = pick("AIRA_LLM_BACKEND", "openai")
        file_base = _text(values.get("OPENAI_BASE_URL"))
        file_transport = _text(values.get("AIRA_LLM_TRANSPORT"))
        shell_base = _text(environment.get("OPENAI_BASE_URL"))
        shell_transport = _text(environment.get("AIRA_LLM_TRANSPORT"))
        custom_backend_requested = requested_backend in ("litellm", "openai_compatible", "custom")
        if file_base:
            base_url = file_base
        elif custom_backend_requested:
            base_url = shell_base
        else:
            base_url = OFFICIAL_OPENAI_BASE_URL
        custom_endpoint = base_url.rstrip("/") != OFFICIAL_OPENAI_BASE_URL
        if requested_backend in ("openai_compatible", "custom"):
            backend = requested_backend
        elif custom_endpoint or requested_backend == "litellm":
            backend = "litellm"
        else:
            backend = "openai"

        if file_transport:
            transport = file_transport
        elif custom_backend_requested and shell_transport and not file_base:
            transport = shell_transport
        elif custom_endpoint or custom_backend_requested:
            transport = "chat_completions"
        else:
            transport = "responses"

        api_key_str = pick("OPENAI_API_KEY")
        if not api_key_str and custom_endpoint:
            api_key_str = "not-needed"

        return cls.model_validate(
            {
                "api_key": SecretStr(api_key_str),
                "model": pick("AIRA_MODEL"),
                "backend": backend,
                "base_url": base_url,
                "transport": transport,
                "max_output_tokens": pick("AIRA_MAX_OUTPUT_TOKENS", "4096"),
                "request_timeout_seconds": pick("AIRA_REQUEST_TIMEOUT_SECONDS", "30.0"),
                "stage_timeout_seconds": pick("AIRA_STAGE_TIMEOUT_SECONDS", "65.0"),
            }
        )
