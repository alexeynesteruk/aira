"""Single-process, bounded assessment execution with explicit stopped attempts.

The interpreter returns typed interpretations, not provider response envelopes.
Every stage is validated before consumption or cache publication. This module
does not select models, infer policy rules, or expose HTTP endpoints.
"""

import asyncio
import math
import sqlite3
import time
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.documents import NativePdfConfig, PdfInputError, extract_pdf, require_usable_extraction
from app.documents.native import PARSER_VERSION
from app.evidence import (
    CitationError,
    CitationResolver,
    EvidenceValidationError,
    validate_findings,
)
from app.schemas import (
    ApplicabilityResult,
    ApplicabilityStatus,
    AssessmentOutcome,
    AssessmentResult,
    ChartFact,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractionRecord,
    Finding,
    OperationalError,
    Policy,
    RequestContext,
    ReviewIssue,
    RunPhase,
    RunProgress,
    RunRecord,
    RunStatus,
    SourceSpan,
    StageUsage,
    StrictModel,
)
from app.storage import LocalStore, StorageError, assessment_fingerprint, fingerprint
from app.storage.identity import canonical_bytes

from .rules import EvaluationResult, evaluate_policy
from .stage_input import StageInputs, StageName, render_stage_input

_ACTIVE = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})
_VALIDATION_VERSION = "workflow-domain-v1"


@dataclass(frozen=True)
class ScopeInterpretation:
    request: RequestContext
    applicability: ApplicabilityResult
    usage: StageUsage | None = None


@dataclass(frozen=True)
class PolicyInterpretation:
    policy: Policy
    usage: StageUsage | None = None


@dataclass(frozen=True)
class EvidenceInterpretation:
    facts: tuple[ChartFact, ...]
    findings: tuple[Finding, ...]
    issues: tuple[ReviewIssue, ...] = ()
    usage: StageUsage | None = None


class StageInterpreter(Protocol):
    async def scope(self, inputs: StageInputs) -> ScopeInterpretation: ...

    async def policy(self, inputs: StageInputs) -> PolicyInterpretation: ...

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation: ...


class InterpretationFailure(Exception):
    """Safe provider/conversion failure retaining reported usage, even on failure."""

    def __init__(self, error: OperationalError, usage: StageUsage | None = None):
        super().__init__(error.message)
        self.error = error
        self.usage = usage


class WorkflowAdmissionError(Exception):
    def __init__(self, error: OperationalError):
        super().__init__(error.message)
        self.error = error


@dataclass(frozen=True)
class WorkflowLimits:
    """Provisional engineering guardrails, not measured model capacity claims.

    max_context_characters bounds the rendered stage-input text produced by
    render_stage_input, not raw records or provider token accounting.
    """

    max_pending: int = 4
    max_context_characters: int = 200_000
    stage_timeout_seconds: float = 90.0

    def __post_init__(self) -> None:
        for name in ("max_pending", "max_context_characters"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if not math.isfinite(self.stage_timeout_seconds) or self.stage_timeout_seconds <= 0:
            raise ValueError("stage_timeout_seconds must be positive and finite")


def workflow_parser_fingerprint(parser_config: NativePdfConfig, limits: WorkflowLimits) -> str:
    """Bind run/cache identity to both extraction settings and workflow guardrails."""
    return fingerprint(
        {
            "native_parser_configuration": parser_config.sha256,
            "workflow_version": _VALIDATION_VERSION,
            "workflow_limits": asdict(limits),
        }
    )


class ScopeArtifact(StrictModel):
    request: RequestContext
    applicability: ApplicabilityResult


class EvidenceArtifact(StrictModel):
    facts: tuple[ChartFact, ...]
    findings: tuple[Finding, ...]
    issues: tuple[ReviewIssue, ...] = ()


def _checked[T: BaseModel](kind: type[T], value: T) -> T:
    return kind.model_validate_json(canonical_bytes(value))


def _spans(value: object) -> Iterator[SourceSpan]:
    if isinstance(value, SourceSpan):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _spans(getattr(value, name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _spans(item)


def _error(
    code: ErrorCode, message: str, action: str, *, retryable: bool = False
) -> OperationalError:
    return OperationalError(code=code, message=message, action=action, retryable=retryable)


class WorkflowEngine:
    """One worker, at most max_pending queued runs, and no automatic live retries.

    Provider retry ownership belongs to the injected interpreter. Native parsing
    uses one dedicated thread. A parser timeout fails its run immediately, but
    the worker waits for that thread to finish before taking another queued run:
    Python threads cannot be safely killed, and timed-out parser jobs must not pile up.
    """

    def __init__(
        self,
        store: LocalStore,
        interpreter: StageInterpreter,
        configuration: ConfigurationProvenance,
        *,
        parser_config: NativePdfConfig | None = None,
        limits: WorkflowLimits | None = None,
    ):
        self.store = store
        self.interpreter = interpreter
        self.parser_config = parser_config or NativePdfConfig()
        self.limits = limits or WorkflowLimits()
        self.configuration = _checked(ConfigurationProvenance, configuration)
        if (
            configuration.parser.name != "pdfplumber"
            or configuration.parser.version != PARSER_VERSION
            or configuration.parser_configuration_sha256
            != workflow_parser_fingerprint(self.parser_config, self.limits)
        ):
            raise ValueError("Configuration must identify the actual parser and workflow limits")
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.limits.max_pending)
        self._worker: asyncio.Task[None] | None = None
        self._admission = asyncio.Lock()
        self._finished = asyncio.Condition()
        self._parser_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="aira-pdf")
        self._parser_future: asyncio.Future[ExtractionRecord] | None = None
        self._closed = False
        self.fatal_error: OperationalError | None = None

    async def start(self) -> tuple[RunRecord, ...]:
        if self._closed:
            raise RuntimeError("A closed workflow engine cannot restart")
        if self._worker is not None:
            return ()
        interrupted = self.store.interrupt_unfinished()
        self._worker = asyncio.create_task(self._work(), name="aira-assessments")
        return interrupted

    async def submit(self, request: CreateAssessmentRequest) -> RunRecord:
        """Admit metadata-only work; parsing and inference begin in the worker."""
        request = _checked(CreateAssessmentRequest, request)
        async with self._admission:
            if self._closed or self._worker is None or self._worker.done() or self.fatal_error:
                raise WorkflowAdmissionError(
                    _error(
                        ErrorCode.CONFIGURATION_MISSING,
                        "Assessment execution is not available.",
                        "Start or restart the local assessment service.",
                    )
                )
            if self._queue.full():
                raise WorkflowAdmissionError(
                    _error(
                        ErrorCode.QUEUE_FULL,
                        "The local assessment queue is full.",
                        "Wait for an active assessment to finish, then retry.",
                        retryable=True,
                    )
                )
            policy = self.store.get_document(
                request.policy_document_id, expected_role=DocumentRole.POLICY
            )
            chart = self.store.get_document(
                request.chart_document_id, expected_role=DocumentRole.CHART
            )
            now = datetime.now(UTC)
            record = RunRecord(
                run_id=f"run-{uuid4().hex}",
                parent_run_id=request.parent_run_id,
                policy_document_id=policy.document_id,
                policy_sha256=policy.sha256,
                chart_document_id=chart.document_id,
                chart_sha256=chart.sha256,
                input_fingerprint=assessment_fingerprint(
                    policy, chart, self.configuration, request.request_context, request.annotations
                ),
                configuration=self.configuration,
                request_context=request.request_context,
                annotations=request.annotations,
                created_at=now,
                updated_at=now,
                status=RunStatus.QUEUED,
                progress=RunProgress(total_pages=policy.page_count + chart.page_count),
            )
            self.store.create_run(record)
            self._queue.put_nowait(record.run_id)
            return record

    async def wait(self, run_id: str) -> RunRecord:
        """CLI/test convenience. HTTP consumers should poll persisted state instead."""
        async with self._finished:
            while (record := self.store.get_run(run_id)).status in _ACTIVE:
                if self.fatal_error:
                    raise WorkflowAdmissionError(self.fatal_error)
                await self._finished.wait()
            return record

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._worker is not None:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
        self.store.interrupt_unfinished()
        while not self._queue.empty():
            self._queue.get_nowait()
            self._queue.task_done()
        self._parser_executor.shutdown(wait=False, cancel_futures=True)
        async with self._finished:
            self._finished.notify_all()

    def _update(self, run_id: str, **changes: object) -> RunRecord:
        current = self.store.get_run(run_id)
        changes["updated_at"] = datetime.now(UTC)
        updated = _checked(RunRecord, current.model_copy(update=changes))
        return self.store.update_run(updated, expected=current)

    def _phase(self, run_id: str, phase: RunPhase) -> RunRecord:
        return self._update(run_id, status=RunStatus.RUNNING, phase=phase)

    def _usage(self, run_id: str, phase: RunPhase, usage: StageUsage) -> None:
        usage = _checked(StageUsage, usage)
        if usage.phase != phase:
            raise ValueError("Interpreter usage must identify its executing stage")
        current = self.store.get_run(run_id)
        self._update(run_id, usage=(*current.usage, usage))

    def _complete_phase(self, run_id: str, phase: RunPhase, *, pages: int | None = None) -> None:
        current = self.store.get_run(run_id)
        progress = RunProgress(
            completed_phases=tuple(dict.fromkeys((*current.progress.completed_phases, phase))),
            completed_pages=current.progress.completed_pages if pages is None else pages,
            total_pages=current.progress.total_pages,
        )
        self._update(run_id, progress=progress)

    async def _notify(self) -> None:
        async with self._finished:
            self._finished.notify_all()

    async def _work(self) -> None:
        while True:
            run_id = await self._queue.get()
            try:
                await self._execute(run_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                # A persistence outage can prevent even the failure snapshot.
                # Stop accepting work; startup recovery preserves queued/running attempts.
                self.fatal_error = _error(
                    ErrorCode.INTERNAL_ERROR,
                    "Local assessment state could not be persisted.",
                    "Check the data directory and restart the application.",
                )
                return
            finally:
                self._queue.task_done()
                await self._notify()
            if self._parser_future is not None:
                try:
                    await asyncio.shield(self._parser_future)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
                finally:
                    self._parser_future = None

    async def _extract(self, document: DocumentRecord) -> ExtractionRecord:
        raw = self.store.read_document(document.document_id)
        for previous in reversed(self.store.list_extractions(document.document_id)):
            if (
                previous.parser_name == "pdfplumber"
                and previous.parser_version == PARSER_VERSION
                and previous.configuration_sha256 == self.parser_config.sha256
            ):
                try:
                    require_usable_extraction(document, previous)
                except PdfInputError:
                    continue
                return previous
        loop = asyncio.get_running_loop()
        pending = loop.run_in_executor(
            self._parser_executor,
            lambda: extract_pdf(raw, document, config=self.parser_config),
        )
        self._parser_future = pending
        try:
            extraction = await asyncio.wait_for(
                asyncio.shield(pending), timeout=self.limits.stage_timeout_seconds
            )
        except TimeoutError:
            raise InterpretationFailure(
                _error(
                    ErrorCode.TIMEOUT,
                    "Native extraction exceeded its processing deadline.",
                    "Use a smaller supported document or inspect the parser failure.",
                )
            ) from None
        else:
            self._parser_future = None
        self.store.put_extraction(extraction)
        require_usable_extraction(document, extraction)
        return extraction

    def _context_limit(
        self, inputs: StageInputs, stage: StageName, policy: Policy | None = None
    ) -> None:
        if len(render_stage_input(inputs, stage, policy)) > self.limits.max_context_characters:
            raise InterpretationFailure(
                _error(
                    ErrorCode.UNSUPPORTED_INPUT,
                    "The complete stage inputs exceed the configured context-character limit.",
                    "Use complete inputs within the supported limit; no pages were truncated.",
                )
            )

    @staticmethod
    def _resolver(inputs: StageInputs) -> CitationResolver:
        return CitationResolver(
            (inputs.policy_document, inputs.chart_document),
            (inputs.policy_extraction, inputs.chart_extraction),
        )

    @staticmethod
    def _validate_sources(resolver: CitationResolver, value: object) -> None:
        for source in _spans(value):
            resolver.validate(source)

    async def _invoke[T: ScopeInterpretation | PolicyInterpretation | EvidenceInterpretation](
        self, run_id: str, phase: RunPhase, call: Callable[[], Awaitable[T]]
    ) -> T:
        started = time.monotonic()
        try:
            async with asyncio.timeout(self.limits.stage_timeout_seconds):
                result = await call()
        except InterpretationFailure as exc:
            self._usage(
                run_id,
                phase,
                exc.usage
                or StageUsage(
                    phase=phase, attempts=1, duration_ms=(time.monotonic() - started) * 1000
                ),
            )
            raise
        except TimeoutError:
            self._usage(
                run_id,
                phase,
                StageUsage(
                    phase=phase, attempts=1, duration_ms=(time.monotonic() - started) * 1000
                ),
            )
            raise InterpretationFailure(
                _error(
                    ErrorCode.TIMEOUT,
                    "The interpretation stage exceeded its deadline.",
                    "Start a new run after checking model availability and input limits.",
                    retryable=True,
                )
            ) from None
        self._usage(
            run_id,
            phase,
            result.usage
            or StageUsage(phase=phase, attempts=1, duration_ms=(time.monotonic() - started) * 1000),
        )
        return result

    def _cache_usage(self, run_id: str, phase: RunPhase) -> None:
        self._usage(
            run_id,
            phase,
            StageUsage(phase=phase, attempts=0, duration_ms=0.0, input_tokens=0, output_tokens=0),
        )

    async def _execute(self, run_id: str) -> None:
        phase = RunPhase.EXTRACTING
        try:
            run = self._phase(run_id, phase)
            policy_document = self.store.get_document(run.policy_document_id)
            chart_document = self.store.get_document(run.chart_document_id)
            started = time.monotonic()
            policy_extraction = await self._extract(policy_document)
            self._update(
                run_id,
                progress=RunProgress(
                    completed_pages=policy_document.page_count,
                    total_pages=policy_document.page_count + chart_document.page_count,
                ),
            )
            chart_extraction = await self._extract(chart_document)
            self._usage(
                run_id,
                phase,
                StageUsage(
                    phase=phase, attempts=1, duration_ms=(time.monotonic() - started) * 1000
                ),
            )
            self._complete_phase(
                run_id, phase, pages=policy_document.page_count + chart_document.page_count
            )
            inputs = StageInputs(
                policy_document,
                chart_document,
                policy_extraction,
                chart_extraction,
                run.request_context,
                run.annotations,
            )
            resolver = self._resolver(inputs)
            self._validate_sources(resolver, inputs.request_context)
            self._validate_sources(resolver, inputs.annotations)
            extraction_ids = (policy_extraction.extraction_id, chart_extraction.extraction_id)

            phase = RunPhase.CHECKING_APPLICABILITY
            self._phase(run_id, phase)
            self._context_limit(inputs, "scope")
            saved_scope = self.store.find_artifact(
                run_id,
                phase,
                ScopeArtifact,
                extraction_ids=extraction_ids,
                validation_version=_VALIDATION_VERSION,
            )
            if saved_scope is None:
                interpreted_scope = await self._invoke(
                    run_id, phase, lambda: self.interpreter.scope(inputs)
                )
                scope = _checked(
                    ScopeArtifact,
                    ScopeArtifact(
                        request=interpreted_scope.request,
                        applicability=interpreted_scope.applicability,
                    ),
                )
                self._validate_sources(resolver, scope)
                saved_scope = self.store.put_validated_artifact(
                    run_id,
                    phase,
                    scope,
                    extraction_ids=extraction_ids,
                    validation_version=_VALIDATION_VERSION,
                )
            else:
                scope = saved_scope.value
                self._validate_sources(resolver, scope)
                self._cache_usage(run_id, phase)
            run = self._update(
                run_id, request_context=scope.request, applicability=scope.applicability
            )
            self._complete_phase(run_id, phase)
            if scope.applicability.status == ApplicabilityStatus.UNRESOLVED:
                self._update(run_id, status=RunStatus.NEEDS_INPUT)
                return
            if scope.applicability.status == ApplicabilityStatus.MISMATCH:
                self._update(
                    run_id,
                    status=RunStatus.COMPLETED,
                    result=AssessmentResult(
                        outcome=AssessmentOutcome.APPLICABILITY_MISMATCH,
                        applicability=scope.applicability,
                    ),
                )
                return
            if scope.request.procedure is None:
                raise EvidenceValidationError("Applicable scope requires a selected procedure")
            inputs = replace(inputs, request_context=scope.request)

            phase = RunPhase.INTERPRETING_POLICY
            self._phase(run_id, phase)
            self._context_limit(inputs, "policy")
            upstream: tuple[str, ...] = (saved_scope.artifact_id,)
            saved_policy = self.store.find_artifact(
                run_id,
                phase,
                Policy,
                extraction_ids=extraction_ids,
                upstream_artifact_ids=upstream,
                validation_version=_VALIDATION_VERSION,
            )
            if saved_policy is None:
                interpreted_policy = await self._invoke(
                    run_id, phase, lambda: self.interpreter.policy(inputs)
                )
                policy = _checked(Policy, interpreted_policy.policy)
                resolver.validate_policy(policy)
                saved_policy = self.store.put_validated_artifact(
                    run_id,
                    phase,
                    policy,
                    extraction_ids=extraction_ids,
                    upstream_artifact_ids=upstream,
                    validation_version=_VALIDATION_VERSION,
                )
            else:
                policy = saved_policy.value
                resolver.validate_policy(policy)
                self._cache_usage(run_id, phase)
            self._complete_phase(run_id, phase)

            phase = RunPhase.MAPPING_EVIDENCE
            self._phase(run_id, phase)
            self._context_limit(inputs, "evidence", policy)
            upstream = (*upstream, saved_policy.artifact_id)
            saved_evidence = self.store.find_artifact(
                run_id,
                phase,
                EvidenceArtifact,
                extraction_ids=extraction_ids,
                upstream_artifact_ids=upstream,
                validation_version=_VALIDATION_VERSION,
            )
            if saved_evidence is None:
                interpreted_evidence = await self._invoke(
                    run_id, phase, lambda: self.interpreter.evidence(inputs, policy)
                )
                evidence = _checked(
                    EvidenceArtifact,
                    EvidenceArtifact(
                        facts=interpreted_evidence.facts,
                        findings=interpreted_evidence.findings,
                        issues=interpreted_evidence.issues,
                    ),
                )
                self._validate_sources(resolver, evidence)
                evidence = _checked(
                    EvidenceArtifact,
                    evidence.model_copy(
                        update={
                            "findings": validate_findings(
                                policy, evidence.facts, evidence.findings, resolver, scope.request
                            )
                        }
                    ),
                )
                saved_evidence = self.store.put_validated_artifact(
                    run_id,
                    phase,
                    evidence,
                    extraction_ids=extraction_ids,
                    upstream_artifact_ids=upstream,
                    validation_version=_VALIDATION_VERSION,
                )
            else:
                evidence = saved_evidence.value
                self._cache_usage(run_id, phase)
            self._complete_phase(run_id, phase)

            phase = RunPhase.VALIDATING
            self._phase(run_id, phase)
            self._validate_sources(resolver, evidence)
            findings = validate_findings(
                policy, evidence.facts, evidence.findings, resolver, scope.request
            )
            self._complete_phase(run_id, phase)

            phase = RunPhase.EVALUATING
            self._phase(run_id, phase)
            evaluation = evaluate_policy(policy, findings, scope.applicability, evidence.issues)
            if evaluation.outcome is None or evaluation.logical_value is None:
                raise EvidenceValidationError("An applicable assessment needs an evaluated outcome")
            result = AssessmentResult(
                outcome=evaluation.outcome,
                applicability=scope.applicability,
                policy=policy,
                facts=evidence.facts,
                findings=findings,
                logical_value=evaluation.logical_value,
                issues=evidence.issues,
            )
            self.store.put_validated_artifact(
                run_id,
                phase,
                _checked(EvaluationResult, evaluation),
                extraction_ids=extraction_ids,
                upstream_artifact_ids=(*upstream, saved_evidence.artifact_id),
                validation_version=_VALIDATION_VERSION,
            )
            self._complete_phase(run_id, phase)
            self._update(run_id, status=RunStatus.COMPLETED, result=result)
        except asyncio.CancelledError:
            raise
        except InterpretationFailure as exc:
            self._fail(run_id, phase, exc.error)
        except PdfInputError as exc:
            self._fail(run_id, phase, exc.error)
        except CitationError:
            self._fail(
                run_id,
                phase,
                _error(
                    ErrorCode.CITATION_INVALID,
                    "An interpretation cites a source that cannot be verified.",
                    "Inspect the source references and start a new run after correcting the input.",
                ),
            )
        except (ValidationError, EvidenceValidationError, ValueError, TypeError):
            self._fail(
                run_id,
                phase,
                _error(
                    ErrorCode.INVALID_OUTPUT,
                    "An interpretation failed the assessment's domain checks.",
                    "Inspect the model configuration and source interpretation before retrying.",
                ),
            )
        except (StorageError, OSError, sqlite3.Error):
            self._fail(
                run_id,
                phase,
                _error(
                    ErrorCode.INTERNAL_ERROR,
                    "The source or assessment artifacts could not be read or saved.",
                    "Check the local data directory before starting a new run.",
                ),
            )
        except Exception:
            self._fail(
                run_id,
                phase,
                _error(
                    ErrorCode.INTERNAL_ERROR,
                    "Assessment processing stopped unexpectedly.",
                    "Check the application configuration and start a new run.",
                ),
            )

    def _fail(self, run_id: str, phase: RunPhase, error: OperationalError) -> None:
        self._update(
            run_id,
            status=RunStatus.FAILED,
            error=_checked(OperationalError, error.model_copy(update={"stage": phase})),
        )
