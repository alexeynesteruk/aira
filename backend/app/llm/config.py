"""Backend-only configuration. Reading settings never contacts a provider."""

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class OpenAISettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1)
    model: str = Field(min_length=1, pattern=r"^\S+$")
    base_url: str = Field(default="https://api.openai.com/v1", pattern=r"^https?://\S+$")
    backend: Literal["openai", "litellm"] = "openai"
    transport: Literal["responses", "chat_completions"] = "responses"
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    max_attempts: int = Field(default=2, ge=1, le=3)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    stage_timeout_seconds: float = Field(default=65.0, gt=0, le=1200)

    @classmethod
    def from_environment(
        cls, *, env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None
    ) -> "OpenAISettings":
        values = dotenv_values(env_file) if env_file.is_file() else {}
        environment = os.environ if environ is None else environ

        def pick(name: str, default: str = "") -> str:
            return environment.get(name, values.get(name) or default).strip()

        backend = pick("AIRA_LLM_BACKEND", "openai")
        return cls.model_validate(
            {
                "api_key": SecretStr(pick("OPENAI_API_KEY")),
                "model": pick("AIRA_MODEL"),
                "backend": backend,
                "base_url": pick("OPENAI_BASE_URL")
                if backend == "litellm"
                else "https://api.openai.com/v1",
                "transport": pick("AIRA_LLM_TRANSPORT", "chat_completions")
                if backend == "litellm"
                else "responses",
                "max_output_tokens": pick("AIRA_MAX_OUTPUT_TOKENS", "4096"),
                "request_timeout_seconds": pick("AIRA_REQUEST_TIMEOUT_SECONDS", "30.0"),
                "stage_timeout_seconds": pick("AIRA_STAGE_TIMEOUT_SECONDS", "65.0"),
            }
        )
