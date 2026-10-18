"""Backend-only configuration. Reading settings never contacts a provider."""

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class OpenAISettings(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    api_key: SecretStr = Field(min_length=1)
    model: str = Field(min_length=1, pattern=r"^\S+$")
    max_output_tokens: int = Field(default=4096, ge=1, le=32768)
    max_attempts: int = Field(default=2, ge=1, le=3)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    stage_timeout_seconds: float = Field(default=65.0, gt=0, le=300)

    @classmethod
    def from_environment(
        cls, *, env_file: Path = Path(".env"), environ: Mapping[str, str] | None = None
    ) -> "OpenAISettings":
        values = dotenv_values(env_file) if env_file.is_file() else {}
        environment = os.environ if environ is None else environ
        key = environment.get("OPENAI_API_KEY", values.get("OPENAI_API_KEY") or "").strip()
        model = environment.get("AIRA_MODEL", values.get("AIRA_MODEL") or "").strip()
        max_tokens = environment.get(
            "AIRA_MAX_OUTPUT_TOKENS", values.get("AIRA_MAX_OUTPUT_TOKENS") or "4096"
        ).strip()
        return cls.model_validate(
            {
                "api_key": SecretStr(key),
                "model": model,
                "max_output_tokens": max_tokens,
            }
        )
