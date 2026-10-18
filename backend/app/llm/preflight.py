"""Explicit, billable access probe; never called by liveness, readiness, or CI."""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.runtime import default_data_dir
from app.schemas import (
    ModelProvider,
    ProviderVerification,
    RunPhase,
    StrictModel,
    VerificationStatus,
)

from .config import OpenAISettings
from .openai_adapter import ModelFailure, OpenAIAdapter


class AccessProbe(StrictModel):
    result: Literal["aira_access_verified"]


def _write_verification(data_dir: Path, record: ProviderVerification) -> None:
    """Atomically persist the last explicit probe; the record never contains the key."""
    data_dir.mkdir(parents=True, exist_ok=True)
    target = data_dir / "provider-verification.json"
    temporary = data_dir / "provider-verification.json.tmp"
    temporary.write_text(record.model_dump_json(indent=2))
    os.replace(temporary, target)


async def verify(
    settings: OpenAISettings,
    *,
    adapter: OpenAIAdapter | None = None,
    data_dir: Path | None = None,
) -> int:
    adapter = adapter or OpenAIAdapter(settings)
    data_dir = data_dir or default_data_dir()
    identity = {
        "checked_at": datetime.now(UTC).isoformat(),
        "provider": "openai",
        "api": settings.transport,
        "configured_model": settings.model,
        "sdk_version": version("openai"),
        "prompt_version": "access-probe-v1",
    }
    verification: ProviderVerification | None = None
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
        verification = ProviderVerification(
            status=VerificationStatus.VERIFIED,
            provider=ModelProvider.OPENAI,
            checked_at=datetime.now(UTC),
            model_id=settings.model,
            detail=result.model,
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
        verification = ProviderVerification(
            status=VerificationStatus.FAILED,
            provider=ModelProvider.OPENAI,
            checked_at=datetime.now(UTC),
            model_id=settings.model,
            detail=f"{exc.error.code}: {exc.error.message}",
        )
        return 1
    finally:
        if verification is not None:
            _write_verification(data_dir, verification)
        await adapter.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help=(
            "Data directory for the persisted verification record; "
            "defaults to AIRA_DATA_DIR or data/app."
        ),
    )
    args = parser.parse_args()
    try:
        settings = OpenAISettings.from_environment(env_file=args.env_file)
    except ValidationError:
        print(
            "Configure OPENAI_API_KEY and AIRA_MODEL in the environment or .env.", file=sys.stderr
        )
        return 2
    return asyncio.run(verify(settings, data_dir=args.data_dir))


if __name__ == "__main__":
    raise SystemExit(main())
