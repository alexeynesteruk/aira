"""Backend-only local build guardrails; configuration reads make no model calls."""

import os
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path

from dotenv import dotenv_values

from app.policies.compiler import BuildLimits


def build_limits_from_environment(
    *,
    env_file: Path = Path(".env"),
    environ: Mapping[str, str] | None = None,
    output_tokens: int = 4096,
    call_timeout_seconds: float = 90,
) -> BuildLimits:
    values = dotenv_values(env_file) if env_file.is_file() else {}
    environment = os.environ if environ is None else environ
    defaults = BuildLimits(output_tokens=output_tokens, call_timeout_seconds=call_timeout_seconds)
    settings = {}
    for field in fields(defaults):
        if field.name == "output_tokens":
            continue  # One adapter output budget governs every stage.
        name = "AIRA_BUILD_" + field.name.upper()
        raw = environment.get(name, values.get(name))
        if raw is not None:
            settings[field.name] = float(raw) if field.name.endswith("_seconds") else int(raw)
    return BuildLimits(**{**defaults.__dict__, **settings})
