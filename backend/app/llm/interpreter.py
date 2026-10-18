"""Production StageInterpreter over the OpenAI adapter and candidate conversion.

The adapter returns untrusted provider candidates; conversion resolves their
citations against the run's real extractions and revalidates domain invariants
before typed records reach the workflow. Conversion failures are operational
(invalid_output/citation_invalid), never "missing" evidence. No automatic
repair attempt is implemented: the TRD allows at most one.
"""

import hashlib
import json
from importlib.metadata import version

from pydantic import BaseModel

from app.assessment.stages import (
    EvidenceInterpretation,
    InterpretationFailure,
    PolicyInterpretation,
    ScopeInterpretation,
    StageInputs,
    StageName,
    render_stage_input,
)
from app.documents.native import PARSER_VERSION
from app.evidence import CitationResolver
from app.policies import (
    CandidateConversionError,
    convert_evidence,
    convert_policy,
    convert_scope,
)
from app.schemas import (
    ConfigurationProvenance,
    ErrorCode,
    EvidenceCandidate,
    InferenceSettings,
    OperationalError,
    Policy,
    PolicyCandidate,
    RunPhase,
    ScopeCandidate,
    StageUsage,
    VersionReference,
)

from .config import OpenAISettings
from .openai_adapter import ModelFailure, ModelMetrics, OpenAIAdapter, strict_output_schema
from .prompts import PROMPTS

_STAGES: tuple[StageName, ...] = ("scope", "policy", "evidence")


def prompt_reference(stage: StageName) -> VersionReference:
    """Prompt identity: the version label plus an instructions/schema digest.

    Any prompt-text or strict output-schema change invalidates run and cache
    identity even if the version label is forgotten.
    """
    prompt = PROMPTS[stage]
    schema = json.dumps(
        strict_output_schema(prompt.output_type),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    digest = hashlib.sha256((prompt.instructions + schema).encode("utf-8")).hexdigest()[:12]
    return VersionReference(name=stage, version=f"{prompt.version}+{digest}")


def openai_configuration(
    settings: OpenAISettings, parser_fingerprint: str
) -> ConfigurationProvenance:
    """Configuration provenance for the production interpreter wiring.

    Callers supply workflow_parser_fingerprint(parser_config, limits); taking the
    string keeps this module free of workflow/storage imports.
    """
    return ConfigurationProvenance(
        parser=VersionReference(name="pdfplumber", version=PARSER_VERSION),
        parser_configuration_sha256=parser_fingerprint,
        prompts=tuple(prompt_reference(stage) for stage in _STAGES),
        model_id=settings.model,
        sdk_version=version("openai"),
        inference=InferenceSettings(max_output_tokens=settings.max_output_tokens),
    )


def _usage(phase: RunPhase, metrics: ModelMetrics, model_id: str | None = None) -> StageUsage:
    return StageUsage(
        phase=phase,
        attempts=metrics.attempts,
        duration_ms=metrics.duration_ms,
        input_tokens=metrics.input_tokens,
        output_tokens=metrics.output_tokens,
        provider_request_ids=metrics.request_ids,
        provider_response_ids=metrics.response_ids,
        model_id=model_id,
    )


def _unexpected(phase: RunPhase) -> OperationalError:
    return OperationalError(
        code=ErrorCode.INVALID_OUTPUT,
        message="The provider returned an unexpected candidate shape.",
        retryable=False,
        action="Check the configured model and prompt versions before retrying.",
        stage=phase,
    )


def _resolver(inputs: StageInputs) -> CitationResolver:
    return CitationResolver(
        (inputs.policy_document, inputs.chart_document),
        (inputs.policy_extraction, inputs.chart_extraction),
    )


class OpenAIStageInterpreter:
    """Satisfies app.assessment.stages.StageInterpreter over real model calls."""

    def __init__(self, adapter: OpenAIAdapter) -> None:
        self._adapter = adapter

    async def _interpret(self, stage: StageName, source_text: str) -> tuple[BaseModel, StageUsage]:
        prompt = PROMPTS[stage]
        try:
            candidate = await self._adapter.interpret(
                phase=prompt.phase,
                instructions=prompt.instructions,
                source_text=source_text,
                output_type=prompt.output_type,
                prompt_version=prompt_reference(stage).version,
            )
        except ModelFailure as exc:
            raise InterpretationFailure(exc.error, _usage(prompt.phase, exc.metrics)) from exc
        return candidate.value, _usage(prompt.phase, candidate.metrics, candidate.model)

    async def scope(self, inputs: StageInputs) -> ScopeInterpretation:
        prompt = PROMPTS["scope"]
        value, usage = await self._interpret("scope", render_stage_input(inputs, "scope"))
        if not isinstance(value, ScopeCandidate):
            raise InterpretationFailure(_unexpected(prompt.phase), usage)
        try:
            converted = convert_scope(value, _resolver(inputs), inputs.annotations)
        except CandidateConversionError as exc:
            raise InterpretationFailure(exc.error, usage) from exc
        return ScopeInterpretation(
            request=converted.request, applicability=converted.applicability, usage=usage
        )

    async def policy(self, inputs: StageInputs) -> PolicyInterpretation:
        prompt = PROMPTS["policy"]
        value, usage = await self._interpret("policy", render_stage_input(inputs, "policy"))
        if not isinstance(value, PolicyCandidate):
            raise InterpretationFailure(_unexpected(prompt.phase), usage)
        policy_id = (
            "policy-"
            + hashlib.sha256(
                f"{inputs.policy_extraction.extraction_id}|{prompt_reference('policy').version}".encode()
            ).hexdigest()[:24]
        )
        try:
            converted = convert_policy(value, _resolver(inputs), policy_id=policy_id)
        except CandidateConversionError as exc:
            raise InterpretationFailure(exc.error, usage) from exc
        return PolicyInterpretation(policy=converted, usage=usage)

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation:
        prompt = PROMPTS["evidence"]
        value, usage = await self._interpret(
            "evidence", render_stage_input(inputs, "evidence", policy)
        )
        if not isinstance(value, EvidenceCandidate):
            raise InterpretationFailure(_unexpected(prompt.phase), usage)
        try:
            converted = convert_evidence(value, policy, _resolver(inputs), inputs.request_context)
        except CandidateConversionError as exc:
            raise InterpretationFailure(exc.error, usage) from exc
        return EvidenceInterpretation(
            facts=converted.facts, findings=converted.findings, usage=usage
        )
