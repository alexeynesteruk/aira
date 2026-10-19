"""Production StageInterpreter over the OpenAI adapter and candidate conversion.

The adapter returns untrusted provider candidates; conversion resolves their
citations against the run's real extractions and revalidates domain invariants
before typed records reach the workflow. Conversion failures are operational
(invalid_output/citation_invalid), never "missing" evidence. Those two codes
receive one repair call under the same stage, with the validation message
fed back and no change to quotes or clinical meaning. A second failure is
the staff-visible error and is marked retryable so a person can start a
linked run. Provider timeouts and rate limits stay on the adapter's own
attempt loop and are not repaired here.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import replace
from importlib.metadata import version
from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from app.policies.compiler import ModelStep
    from app.schemas.builds import (
        AuditCandidate,
        ReconciliationCandidate,
        ReconciliationGroup,
        SectionCandidate,
        SectionPlan,
        SectionResult,
    )

from pydantic import BaseModel

from app.assessment.stages import (
    ChartInterpretation,
    DocumentInputs,
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
    convert_chart,
    convert_findings,
    convert_policy,
    convert_scope,
)
from app.policies.pages import (
    PageSelection,
    chosen_pages,
    index_batches,
    page_excerpts,
    render_index,
    render_page,
)
from app.schemas import (
    ChartCandidate,
    ConfigurationProvenance,
    ErrorCode,
    FindingsCandidate,
    InferenceSettings,
    OperationalError,
    PagePlanCandidate,
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

_STAGES: tuple[StageName, ...] = (
    "scope",
    "policy",
    "policy_index",
    "policy_page",
    "policy_section",
    "policy_reconcile",
    "policy_merge",
    "policy_audit",
    "chart",
    "evidence",
)
T = TypeVar("T")


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
        transport=settings.transport,
        endpoint_sha256=hashlib.sha256(settings.base_url.encode()).hexdigest(),
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


_REPAIRABLE = frozenset({ErrorCode.INVALID_OUTPUT, ErrorCode.CITATION_INVALID})


def _repair_note(error: OperationalError) -> str:
    return (
        "Validation failure: "
        + error.code.value
        + ". "
        + error.message
        + " Return one corrected JSON object. Every quote must be an exact passage "
        "from the supplied source. Do not invent text, dates, or citations."
    )


def _merge_usage(first: StageUsage | None, second: StageUsage | None) -> StageUsage | None:
    if first is None:
        return second
    if second is None:
        return first

    def add(left: int | None, right: int | None) -> int | None:
        if left is None and right is None:
            return None
        return (left or 0) + (right or 0)

    return first.model_copy(
        update={
            "attempts": first.attempts + second.attempts,
            "duration_ms": first.duration_ms + second.duration_ms,
            "input_tokens": add(first.input_tokens, second.input_tokens),
            "output_tokens": add(first.output_tokens, second.output_tokens),
            "provider_request_ids": first.provider_request_ids + second.provider_request_ids,
            "provider_response_ids": first.provider_response_ids + second.provider_response_ids,
            "model_id": second.model_id or first.model_id,
        }
    )


def _staff_retry(error: OperationalError) -> OperationalError:
    if error.code not in _REPAIRABLE:
        return error
    return error.model_copy(
        update={
            "retryable": True,
            "action": "Retry the assessment. This attempt is kept.",
        }
    )


class OpenAIStageInterpreter:
    """Satisfies app.assessment.stages.StageInterpreter over real model calls."""

    def __init__(self, adapter: OpenAIAdapter) -> None:
        self._adapter = adapter

    async def _interpret(
        self, stage: StageName, source_text: str, *, repair: str | None = None
    ) -> tuple[BaseModel, StageUsage]:
        prompt = PROMPTS[stage]
        instructions = prompt.instructions
        if repair is not None:
            instructions = instructions + "\n\n" + repair
        try:
            candidate = await self._adapter.interpret(
                phase=prompt.phase,
                instructions=instructions,
                source_text=source_text,
                output_type=prompt.output_type,
                prompt_version=prompt_reference(stage).version,
            )
        except ModelFailure as exc:
            raise InterpretationFailure(exc.error, _usage(prompt.phase, exc.metrics)) from exc
        return candidate.value, _usage(prompt.phase, candidate.metrics, candidate.model)

    async def _once(
        self,
        stage: StageName,
        source_text: str,
        convert: Callable[[BaseModel], T],
    ) -> tuple[T, StageUsage]:
        """Call the model, convert, and allow one repair for an invalid candidate."""
        repaired = False
        try:
            value, usage = await self._interpret(stage, source_text)
        except InterpretationFailure as first:
            if first.error.code not in _REPAIRABLE:
                raise
            repaired = True
            try:
                value, second = await self._interpret(
                    stage, source_text, repair=_repair_note(first.error)
                )
            except InterpretationFailure as second_failure:
                raise InterpretationFailure(
                    _staff_retry(second_failure.error),
                    _merge_usage(first.usage, second_failure.usage),
                ) from second_failure
            usage = _merge_usage(first.usage, second) or second
        try:
            return convert(value), usage
        except CandidateConversionError as exc:
            if exc.error.code not in _REPAIRABLE or repaired:
                raise InterpretationFailure(_staff_retry(exc.error), usage) from exc
            try:
                repaired_value, second = await self._interpret(
                    stage, source_text, repair=_repair_note(exc.error)
                )
            except InterpretationFailure as second_failure:
                raise InterpretationFailure(
                    _staff_retry(second_failure.error),
                    _merge_usage(usage, second_failure.usage),
                ) from second_failure
            merged = _merge_usage(usage, second) or second
            try:
                return convert(repaired_value), merged
            except CandidateConversionError as second_error:
                raise InterpretationFailure(
                    _staff_retry(second_error.error), merged
                ) from second_error

    async def scope(self, inputs: StageInputs) -> ScopeInterpretation:
        prompt = PROMPTS["scope"]

        def convert(value: BaseModel) -> ScopeInterpretation:
            if not isinstance(value, ScopeCandidate):
                raise InterpretationFailure(_unexpected(prompt.phase), None)
            converted = convert_scope(value, _resolver(inputs), inputs.annotations)
            return ScopeInterpretation(
                request=converted.request,
                applicability=converted.applicability,
                usage=None,
                policy_path_id=value.policy_path_id,
            )

        try:
            interpreted, usage = await self._once(
                "scope", render_stage_input(inputs, "scope"), convert
            )
        except InterpretationFailure:
            raise
        return replace(interpreted, usage=usage)

    async def policy(self, inputs: DocumentInputs | StageInputs) -> PolicyInterpretation:
        if isinstance(inputs, StageInputs):
            inputs = DocumentInputs(inputs.policy_document, inputs.policy_extraction)
        prompt = PROMPTS["policy"]
        policy_id = (
            "policy-"
            + hashlib.sha256(
                f"{inputs.extraction.extraction_id}|{prompt_reference('policy').version}".encode()
            ).hexdigest()[:24]
        )

        def convert(value: BaseModel) -> Policy:
            if not isinstance(value, PolicyCandidate):
                raise InterpretationFailure(_unexpected(prompt.phase), None)
            return convert_policy(
                value,
                CitationResolver((inputs.document,), (inputs.extraction,)),
                policy_id=policy_id,
            )

        try:
            converted, usage = await self._once(
                "policy", render_stage_input(inputs, "policy"), convert
            )
        except InterpretationFailure:
            raise
        return PolicyInterpretation(policy=converted, usage=usage)

    async def select_policy_pages(self, inputs: DocumentInputs) -> PageSelection:
        """Classify short excerpts. A page the model does not name is still read."""
        usage: StageUsage | None = None
        roles: list[tuple[int, str]] = []
        for batch in index_batches(page_excerpts(inputs.extraction.pages)):

            def convert(value: BaseModel) -> PagePlanCandidate:
                if not isinstance(value, PagePlanCandidate):
                    raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY), None)
                return value

            plan, batch_usage = await self._once(
                "policy_index", render_index(inputs.document.document_id, batch), convert
            )
            roles.extend((item.page, item.use) for item in plan.pages)
            usage = _merge_usage(usage, batch_usage)
        included, skipped = chosen_pages(inputs.document.page_count, roles)
        if not included:
            raise InterpretationFailure(
                OperationalError(
                    code=ErrorCode.INVALID_OUTPUT,
                    message="The guideline index marked every page as having no rule.",
                    retryable=True,
                    action="Retry the assessment. This attempt is kept.",
                    stage=RunPhase.INTERPRETING_POLICY,
                ),
                usage,
            )
        return PageSelection(pages=included, skipped=skipped, usage=usage)

    async def apply_policy_page(
        self, inputs: DocumentInputs, page_number: int, current: Policy | None
    ) -> PolicyInterpretation:
        """Update the rule set from a single guideline page."""
        page = next(item for item in inputs.extraction.pages if item.page == page_number)
        policy_id = (
            "policy-"
            + hashlib.sha256(
                f"{inputs.extraction.extraction_id}|{prompt_reference('policy_page').version}".encode()
            ).hexdigest()[:24]
        )

        def convert(value: BaseModel) -> Policy:
            if not isinstance(value, PolicyCandidate):
                raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY), None)
            return convert_policy(
                value,
                CitationResolver((inputs.document,), (inputs.extraction,)),
                policy_id=policy_id,
            )

        converted, usage = await self._once(
            "policy_page",
            render_page(
                inputs.document.document_id,
                page_number,
                [block.text for block in page.blocks],
                current,
            ),
            convert,
        )
        return PolicyInterpretation(policy=converted, usage=usage)

    async def chart(self, inputs: DocumentInputs) -> ChartInterpretation:
        def convert(value: BaseModel) -> object:
            if not isinstance(value, ChartCandidate):
                raise InterpretationFailure(_unexpected(RunPhase.EXTRACTING_CHART))
            return convert_chart(
                value,
                CitationResolver((inputs.document,), (inputs.extraction,)),
                document_sha256=inputs.document.sha256,
            )

        chart, usage = await self._once("chart", render_stage_input(inputs, "chart"), convert)
        from app.schemas import ChartData

        if not isinstance(chart, ChartData):
            raise InterpretationFailure(_unexpected(RunPhase.EXTRACTING_CHART))
        return ChartInterpretation(chart=chart, usage=usage)

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation:
        prompt = PROMPTS["evidence"]

        def convert(value: BaseModel) -> EvidenceInterpretation:
            if not isinstance(value, FindingsCandidate):
                raise InterpretationFailure(_unexpected(prompt.phase), None)
            if inputs.chart is None:
                raise ValueError("Evidence mapping requires saved chart facts")
            converted = convert_findings(
                value, policy, inputs.chart.facts, _resolver(inputs), inputs.request_context
            )
            return EvidenceInterpretation(
                facts=converted.facts, findings=converted.findings, usage=None
            )

        try:
            interpreted, usage = await self._once(
                "evidence", render_stage_input(inputs, "evidence", policy), convert
            )
        except InterpretationFailure:
            raise
        return replace(interpreted, usage=usage)

    async def section(
        self, inputs: DocumentInputs, plan: "SectionPlan"
    ) -> "ModelStep[SectionCandidate]":
        from app.policies.compiler import ModelStep, section_packet, validate_section
        from app.schemas.builds import SectionCandidate

        def convert(value: BaseModel) -> SectionCandidate:
            if not isinstance(value, SectionCandidate):
                raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY))
            try:
                validate_section(inputs.document, inputs.extraction, plan, value)
            except ValueError as exc:
                raise CandidateConversionError(
                    ErrorCode.INVALID_OUTPUT, RunPhase.INTERPRETING_POLICY, str(exc)
                ) from exc
            return value

        value, usage = await self._once(
            "policy_section",
            json.dumps(
                section_packet(inputs.document, plan), ensure_ascii=False, separators=(",", ":")
            ),
            convert,
        )
        return ModelStep(value, usage)

    async def reconcile(
        self, inputs: DocumentInputs, sections: tuple["SectionResult", ...]
    ) -> "ModelStep[ReconciliationCandidate]":
        from app.policies.compiler import ModelStep, reconciliation_packet
        from app.schemas.builds import ReconciliationCandidate

        def convert(value: BaseModel) -> ReconciliationCandidate:
            if not isinstance(value, ReconciliationCandidate):
                raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY))
            return value

        value, usage = await self._once(
            "policy_reconcile",
            json.dumps(reconciliation_packet(sections), ensure_ascii=False, separators=(",", ":")),
            convert,
        )
        return ModelStep(value, usage)

    async def merge(
        self,
        inputs: DocumentInputs,
        groups: tuple["ReconciliationGroup", ...],
        sections: tuple["SectionResult", ...],
    ) -> "ModelStep[ReconciliationCandidate]":
        from app.policies.compiler import ModelStep, group_packet
        from app.schemas.builds import ReconciliationCandidate

        packet = group_packet(groups, sections)
        raw_references = packet["references"]
        if not isinstance(raw_references, list):
            raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY))
        expected = {
            str(item["reference_id"])
            for item in raw_references
            if isinstance(item, dict) and item.get("reference_id") is not None
        }

        def convert(value: BaseModel) -> ReconciliationCandidate:
            if not isinstance(value, ReconciliationCandidate):
                raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY))
            found = [item.reference_id for item in value.resolutions]
            if len(found) != len(set(found)) or set(found) != expected:
                raise CandidateConversionError(
                    ErrorCode.INVALID_OUTPUT,
                    RunPhase.INTERPRETING_POLICY,
                    "Every extracted dependency requires exactly one resolution",
                )
            return value

        value, usage = await self._once(
            "policy_merge",
            json.dumps(packet, ensure_ascii=False, separators=(",", ":")),
            convert,
        )
        return ModelStep(value, usage)

    async def audit(
        self,
        inputs: DocumentInputs,
        section: "SectionResult",
        reconciliation: "ReconciliationCandidate",
    ) -> "ModelStep[AuditCandidate]":
        from app.policies.compiler import ModelStep, audit_packet
        from app.schemas.builds import AuditCandidate

        packet = audit_packet(inputs.document, section, reconciliation)

        def convert(value: BaseModel) -> AuditCandidate:
            if not isinstance(value, AuditCandidate):
                raise InterpretationFailure(_unexpected(RunPhase.INTERPRETING_POLICY))
            return value

        value, usage = await self._once(
            "policy_audit", json.dumps(packet, ensure_ascii=False, separators=(",", ":")), convert
        )
        return ModelStep(value, usage)
