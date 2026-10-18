"""Explicit, billable access probe; never called by liveness, readiness, or CI."""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.schemas import RunPhase, StrictModel

from .config import OpenAISettings
from .openai_adapter import ModelFailure, OpenAIAdapter


class AccessProbe(StrictModel):
    result: Literal["aira_access_verified"]


async def verify(settings: OpenAISettings) -> int:
    adapter = OpenAIAdapter(settings)
    identity = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider": "openai",
        "api": "responses",
        "configured_model": settings.model,
        "sdk_version": version("openai"),
        "prompt_version": "access-probe-v1",
    }
    try:
        result = await adapter.interpret(
            phase=RunPhase.CHECKING_APPLICABILITY,
            instructions="Return the supplied verification string in the required result field.",
            source_text="aira_access_verified",
            output_type=AccessProbe,
            prompt_version="access-probe-v1",
        )
        print(
            json.dumps(
                {
                    "status": "verified",
                    **identity,
                    "model": result.model,
                    "metrics": asdict(result.metrics),
                }
            )
        )
        return 0
    except ModelFailure as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    **identity,
                    "error": exc.error.model_dump(mode="json"),
                    "metrics": asdict(exc.metrics),
                }
            )
        )
        return 1
    finally:
        await adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    args = parser.parse_args()
    try:
        settings = OpenAISettings.from_environment(env_file=args.env_file)
    except ValidationError:
        print(
            "Configure OPENAI_API_KEY and AIRA_MODEL in the environment or .env.", file=sys.stderr
        )
        return 2
    return asyncio.run(verify(settings))


if __name__ == "__main__":
    raise SystemExit(main())
