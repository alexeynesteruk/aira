"""Bounded standalone document builds and durable, source-checked checkpoints."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from functools import partial
from typing import cast
from uuid import uuid4

from pydantic import BaseModel

from app.documents import NativePdfConfig, PdfInputError, extract_pdf, require_usable_extraction
from app.documents.native import PARSER_VERSION
from app.evidence import CitationError, CitationResolver
from app.policies.compiler import (
    COMPILER_VERSION,
    BuildLimits,
    GuidelineInterpreter,
    ModelStep,
    compile_policy,
    group_packet,
    namespace_reconciliation,
    plan_sections,
    reconciliation_packet,
    section_packet,
    token_upper_bound,
    validate_audit,
    validate_section,
)
from app.schemas import (
    ChartData,
    ConfigurationProvenance,
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractionRecord,
    OperationalError,
    Policy,
    RunPhase,
    StageUsage,
)
from app.schemas.builds import (
    AuditCandidate,
    BuildRecord,
    BuildRequest,
    BuildStep,
    CoverageEntry,
    ReconciliationCandidate,
    ReconciliationGroup,
    SectionCandidate,
    SectionPlan,
    SectionResult,
)
from app.storage import (
    LocalStore,
    StorageConflict,
    StorageError,
    StorageReferenceError,
    fingerprint,
)
from app.storage.identity import canonical_bytes

from .stages import DocumentInputs, InterpretationFailure, StageInterpreter, render_document_input


def _error(
    code: ErrorCode, message: str, action: str, *, retryable: bool = False
) -> OperationalError:
    return OperationalError(code=code, message=message, action=action, retryable=retryable)


class DocumentBuildService:
    """One local worker coalesces matching active work; restart requires explicit retry."""

    def __init__(
        self,
        store: LocalStore,
        interpreter: StageInterpreter,
        configuration: ConfigurationProvenance,
        *,
        parser_config: NativePdfConfig,
        limits: BuildLimits | None = None,
    ):
        self.store = store
        self.interpreter = interpreter
        self.configuration = configuration
        self.parser_config = parser_config
        self.limits = limits or BuildLimits(output_tokens=configuration.inference.max_output_tokens)
        self._parser_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="aira-build-pdf"
        )
        self._queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self.limits.max_pending)
        self._active: dict[str, str] = {}
        self._admission = asyncio.Lock()
        self._finished = asyncio.Condition()
        self._worker: asyncio.Task[None] | None = None
        self._reserved: dict[str, tuple[int, int]] = {}
        self.fatal_error: OperationalError | None = None

    async def start(self) -> None:
        if self._worker is not None:
            return
        for record in self.store.list_builds(active_only=True):
            if record.status in ("queued", "running"):
                self._update(
                    record.build_id,
                    status="interrupted",
                    error=_error(
                        ErrorCode.INTERRUPTED,
                        "Document preparation stopped before completion.",
                        "Retry this build to reuse compatible completed sections.",
                        retryable=True,
                    ),
                )
        self._worker = asyncio.create_task(self._work(), name="aira-document-builds")

    async def close(self) -> None:
        if self._worker is None:
            return
        self._worker.cancel()
        try:
            await self._worker
        except asyncio.CancelledError:
            pass
        self._worker = None
        self._parser_executor.shutdown(wait=False, cancel_futures=True)
        for record in self.store.list_builds(active_only=True):
            if record.status in ("queued", "running"):
                self._update(
                    record.build_id,
                    status="interrupted",
                    error=_error(
                        ErrorCode.INTERRUPTED,
                        "Local document preparation stopped.",
                        "Retry this build to reuse completed sections.",
                        retryable=True,
                    ),
                )
        async with self._finished:
            self._finished.notify_all()

    def _config(self, role: DocumentRole) -> dict[str, object]:
        stage = "policy" if role == DocumentRole.POLICY else "chart"
        data = self.configuration.model_dump(mode="json")
        data.pop("parser_configuration_sha256")  # workflow-only limits are not extraction inputs
        selected = [item for item in data["prompts"] if item["name"].startswith(stage)]
        data["prompts"] = selected or data["prompts"]
        limits = asdict(self.limits)
        if role == DocumentRole.CHART:
            limits.pop("primary_tokens")
            limits.pop("max_sections")
        return {
            "configuration": data,
            "parser": self.parser_config.sha256,
            "compiler": COMPILER_VERSION if role == DocumentRole.POLICY else "chart-facts-v1",
            "limits": limits,
        }

    async def submit(self, document_id: str, request: BuildRequest | None = None) -> BuildRecord:
        request = request or BuildRequest()
        async with self._admission:
            if self._worker is None or self._worker.done() or self.fatal_error:
                raise StorageConflict("Document build execution is unavailable")
            document = self.store.get_document(document_id)
            parent = (
                self.store.get_build(request.parent_build_id) if request.parent_build_id else None
            )
            if parent and (parent.document_sha256, parent.role) != (document.sha256, document.role):
                raise StorageReferenceError("Retry/rebuild parent belongs to a different document")
            if parent and parent.status in ("queued", "running"):
                raise StorageConflict("The parent build is still active")
            key = fingerprint(
                {
                    "sha256": document.sha256,
                    "role": document.role.value,
                    **self._config(document.role),
                }
            )
            # Same upload requests share a tracked job, not duplicate inference.
            active_key = key + ":" + document_id
            if active_key in self._active:
                return self.store.get_build(self._active[active_key])
            if self._queue.full():
                raise StorageConflict("The document build queue is full; wait and retry")
            now = datetime.now(UTC)
            identity = "build-" + uuid4().hex
            record = BuildRecord(
                build_id=identity,
                parent_build_id=request.parent_build_id,
                generation_id=identity
                if request.rebuild
                else (parent.generation_id if parent else None),
                document_id=document_id,
                document_sha256=document.sha256,
                role=document.role,
                fingerprint=key,
                configuration=self.configuration,
                build_limits=asdict(self.limits),
                created_at=now,
                updated_at=now,
                status="queued",
            )
            self.store.put_build(record)
            self._active[active_key] = identity
            self._queue.put_nowait(identity)
            return record

    async def wait(self, build_id: str) -> BuildRecord:
        async with self._finished:
            while (record := self.store.get_build(build_id)).status in ("queued", "running"):
                if self.fatal_error:
                    raise StorageError(self.fatal_error.message)
                await self._finished.wait()
            return record

    async def prepare(
        self, document: DocumentRecord, pinned_build_id: str | None = None
    ) -> BuildRecord:
        if pinned_build_id is not None:
            result = self.store.require_usable_build(pinned_build_id)
            if result.document_id != document.document_id:
                raise StorageReferenceError("The selected build belongs to another upload")
            if result.status != "completed" or result.review_status == "rejected":
                raise StorageConflict("The selected build is unavailable or rejected")
            return result
        result = await self.wait((await self.submit(document.document_id)).build_id)
        if result.status != "completed":
            raise InterpretationFailure(
                result.error
                or _error(
                    ErrorCode.INVALID_OUTPUT,
                    "Document preparation did not complete.",
                    "Inspect the document build and retry.",
                )
            )
        return result

    def review(self, build_id: str, *, approve: bool) -> BuildRecord:
        record = self.store.get_build(build_id)
        if record.status != "completed":
            raise StorageConflict("Only completed builds can be reviewed")
        return self._update(build_id, review_status="approved" if approve else "rejected")

    def _update(self, build_id: str, **changes: object) -> BuildRecord:
        record = self.store.get_build(build_id)
        changes["updated_at"] = datetime.now(UTC)
        updated = BuildRecord.model_validate_json(
            canonical_bytes(record.model_copy(update=changes))
        )
        return self.store.put_build(updated)

    async def _work(self) -> None:
        while True:
            identity = await self._queue.get()
            try:
                await self._execute(identity)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.fatal_error = _error(
                    ErrorCode.INTERNAL_ERROR,
                    "Document build state could not be persisted.",
                    "Check the data directory and restart.",
                )
                return
            finally:
                record = self.store.get_build(identity)
                self._active.pop(record.fingerprint + ":" + record.document_id, None)
                self._reserved.pop(identity, None)
                self._queue.task_done()
                async with self._finished:
                    self._finished.notify_all()

    async def _extract(self, document: DocumentRecord) -> ExtractionRecord:
        for extraction in reversed(self.store.list_extractions(document.document_id)):
            if (
                extraction.parser_version == PARSER_VERSION
                and extraction.configuration_sha256 == self.parser_config.sha256
            ):
                require_usable_extraction(document, extraction)
                return extraction
        async with asyncio.timeout(self.limits.call_timeout_seconds):
            extraction = await asyncio.get_running_loop().run_in_executor(
                self._parser_executor,
                partial(
                    extract_pdf,
                    self.store.read_document(document.document_id),
                    document,
                    config=self.parser_config,
                ),
            )
        self.store.put_extraction(extraction)
        require_usable_extraction(document, extraction)
        return extraction

    def _request_size(self, packet: object, output_type: type[BaseModel]) -> int:
        return (
            token_upper_bound(canonical_bytes(packet).decode())
            + token_upper_bound(canonical_bytes(output_type.model_json_schema()).decode())
            + 8192
            + self.limits.output_tokens
        )

    def _validate_reconciliation(
        self,
        inputs: DocumentInputs,
        sections: tuple[SectionResult, ...],
        value: ReconciliationCandidate,
    ) -> None:
        compile_policy(
            inputs.document,
            inputs.extraction,
            sections,
            value,
            tuple(
                AuditCandidate(
                    checked_unit_ids=tuple(unit.unit_id for unit in section.plan.primary),
                    missing_conditions=(),
                    issues=(),
                )
                for section in sections
            ),
            policy_id="validation-only",
        )

    async def _reconcile(
        self,
        record: BuildRecord,
        inputs: DocumentInputs,
        sections: tuple[SectionResult, ...],
        interpreter: GuidelineInterpreter,
    ) -> ReconciliationCandidate:
        # Reconcile bounded groups. Earlier local graphs are immutable and never regenerated.
        batches: list[tuple[SectionResult, ...]] = []
        current: tuple[SectionResult, ...] = ()
        for section in sections:
            proposed = (*current, section)
            if (
                self._request_size(reconciliation_packet(proposed), ReconciliationCandidate)
                > self.limits.input_tokens
            ):
                if not current:
                    raise ValueError("One section exceeds the reconciliation budget")
                batches.append(current)
                current = (section,)
            else:
                current = proposed
        if current:
            batches.append(current)
        if len(batches) == 1:
            return await self._step(
                record,
                "policy_reconcile",
                reconciliation_packet(sections),
                ReconciliationCandidate,
                lambda: interpreter.reconcile(inputs, sections),
                lambda value: self._validate_reconciliation(inputs, sections, value),
            )
        groups: list[ReconciliationGroup] = []
        for index, batch in enumerate(batches):
            # Context-only trailing batches attach to the nearest rule-bearing group.
            if not any(section.policy for section in batch):
                raise ValueError(
                    "Reconciliation batch has no rules; increase the bounded input budget"
                )

            async def call(
                current: tuple[SectionResult, ...] = batch,
            ) -> ModelStep[ReconciliationCandidate]:
                return await interpreter.reconcile(inputs, current)

            def validate(
                value: ReconciliationCandidate, current: tuple[SectionResult, ...] = batch
            ) -> None:
                self._validate_reconciliation(inputs, current, value)

            result = await self._step(
                record,
                "policy_reconcile",
                reconciliation_packet(batch),
                ReconciliationCandidate,
                call,
                validate,
            )
            name = f"group-{index + 1}:"
            groups.append(
                ReconciliationGroup(
                    group_id=name,
                    section_ids=tuple(section.section_id for section in batch),
                    result=namespace_reconciliation(result, name),
                )
            )
        saved = tuple(groups)

        def combined(value: ReconciliationCandidate) -> ReconciliationCandidate:
            return value.model_copy(
                update={
                    "nodes": tuple(node for group in saved for node in group.result.nodes)
                    + value.nodes,
                    "issues": tuple(issue for group in saved for issue in group.result.issues)
                    + value.issues,
                }
            )

        def validate_merge(value: ReconciliationCandidate) -> None:
            self._validate_reconciliation(inputs, sections, combined(value))

        merged = await self._step(
            record,
            "policy_merge",
            group_packet(saved, sections),
            ReconciliationCandidate,
            lambda: interpreter.merge(inputs, saved, sections),
            validate_merge,
        )
        return combined(merged)

    def _receipt(
        self,
        record: BuildRecord,
        name: str,
        key: str,
        packet: object,
        value: BaseModel,
        *,
        cached: bool,
    ) -> None:
        current = self.store.get_build(record.build_id)
        receipt = BuildStep(
            name=name,
            checkpoint_key=key,
            input_sha256=fingerprint(packet),
            output_sha256=fingerprint(value),
            cached=cached,
            configuration=self.store.checkpoint_configuration(key),
        )
        self._update(record.build_id, steps=(*current.steps, receipt))

    async def _step[T: BaseModel](
        self,
        record: BuildRecord,
        name: str,
        packet: object,
        output_type: type[T],
        call: Callable[[], Awaitable[ModelStep[T]]],
        validate: Callable[[T], object] | None = None,
    ) -> T:
        # Actual full request data + schema and conservative instruction/envelope reserve.
        size = token_upper_bound(canonical_bytes(packet).decode())
        size += token_upper_bound(canonical_bytes(output_type.model_json_schema()).decode()) + 8192
        if size + self.limits.output_tokens > self.limits.input_tokens:
            raise InterpretationFailure(
                _error(
                    ErrorCode.UNSUPPORTED_INPUT,
                    f"{name} exceeds its complete input/output budget; "
                    "no source text was truncated.",
                    "Use a larger supported build budget or a smaller complete document.",
                )
            )
        prompt = [
            item.model_dump(mode="json") for item in self.configuration.prompts if item.name == name
        ]
        key = fingerprint(
            {
                "version": self._config(record.role)["compiler"],
                "stage": name,
                "input": packet,
                "prompt": prompt,
                "generation": record.generation_id,
                "provider": {
                    key: value
                    for key, value in self._config(record.role).items()
                    if key != "configuration"
                },
                "model": self.configuration.model_id,
                "sdk": self.configuration.sdk_version,
                "transport": self.configuration.transport,
                "endpoint": self.configuration.endpoint_sha256,
                "inference": self.configuration.inference.model_dump(mode="json"),
                "schema": output_type.model_json_schema(),
            }
        )
        cached = self.store.get_checkpoint(key, output_type)
        if cached is not None:
            if validate is not None:
                validate(cached)
            self._receipt(record, name, key, packet, cached, cached=True)
            return cached
        calls, tokens = self._reserved.get(record.build_id, (0, 0))
        # Up to three transport attempts and one application repair; reserve the full bound.
        calls += 6
        tokens += 6 * (size + self.limits.output_tokens)
        if calls > self.limits.max_calls or tokens > self.limits.total_tokens:
            raise InterpretationFailure(
                _error(
                    ErrorCode.UNSUPPORTED_INPUT,
                    "Document preparation exhausted its total call/token budget.",
                    "Inspect build usage and explicitly retry with a supported budget.",
                )
            )
        self._reserved[record.build_id] = calls, tokens
        started = time.monotonic()
        usage: StageUsage | None = None
        try:
            async with asyncio.timeout(self.limits.call_timeout_seconds):
                step = await call()
            usage = step.usage
            value = output_type.model_validate_json(canonical_bytes(step.value))
            if validate is not None:
                validate(value)
        except InterpretationFailure as exc:
            usage = exc.usage
            raise
        finally:
            current = self.store.get_build(record.build_id)
            self._update(
                record.build_id,
                usage=(
                    *current.usage,
                    usage
                    or StageUsage(
                        phase=RunPhase.INTERPRETING_POLICY
                        if record.role == DocumentRole.POLICY
                        else RunPhase.EXTRACTING_CHART,
                        attempts=1,
                        duration_ms=(time.monotonic() - started) * 1000,
                    ),
                ),
            )
        self.store.put_checkpoint(key, value, configuration=record.configuration)
        self._receipt(record, name, key, packet, value, cached=False)
        return value

    async def _guideline(
        self, record: BuildRecord, inputs: DocumentInputs
    ) -> tuple[Policy, tuple[CoverageEntry, ...], ReconciliationCandidate | None]:
        if not isinstance(self.interpreter, GuidelineInterpreter):
            # Explicit injected test interpreters exercise the legacy contract; production
            # OpenAIStageInterpreter always implements the structural operations below.
            async def policy_call() -> ModelStep[Policy]:
                result = await self.interpreter.policy(inputs)
                return ModelStep(result.policy, result.usage)

            policy = await self._step(
                record,
                "policy",
                {"controlled_document_sha256": inputs.document.sha256},
                Policy,
                policy_call,
            )
            CitationResolver((inputs.document,), (inputs.extraction,)).validate_policy(policy)
            plans = plan_sections(inputs.extraction, self.limits)
            coverage = tuple(
                CoverageEntry(
                    section_id=plan.section_id,
                    unit_id=unit.unit_id,
                    source=unit.source,
                    disposition="context",
                    explanation="Controlled interpreter fixture.",
                    audited=True,
                )
                for plan in plans
                for unit in plan.primary
            )
            self._update(
                record.build_id,
                total_sections=len(plans),
                completed_sections=len(plans),
            )
            return policy, coverage, None
        interpreter = cast(GuidelineInterpreter, self.interpreter)
        plans = plan_sections(inputs.extraction, self.limits)
        self._update(record.build_id, phase="extracting_sections", total_sections=len(plans))
        sections = []
        for index, plan in enumerate(plans):

            async def section_call(current: SectionPlan = plan) -> ModelStep[SectionCandidate]:
                return await interpreter.section(inputs, current)

            def validate_candidate(value: SectionCandidate, current: SectionPlan = plan) -> object:
                return validate_section(inputs.document, inputs.extraction, current, value)

            candidate = await self._step(
                record,
                "policy_section",
                section_packet(inputs.document, plan),
                SectionCandidate,
                section_call,
                validate_candidate,
            )
            sections.append(validate_section(inputs.document, inputs.extraction, plan, candidate))
            self._update(record.build_id, completed_sections=index + 1)
        section_results = tuple(sections)
        self._update(record.build_id, phase="reconciling")

        reconciliation = await self._reconcile(record, inputs, section_results, interpreter)
        self._update(record.build_id, phase="auditing")
        audits = []
        for section in section_results:

            async def audit_call(current: SectionResult = section) -> ModelStep[AuditCandidate]:
                return await interpreter.audit(inputs, current, reconciliation)

            packet = {
                "source": section_packet(inputs.document, section.plan),
                "interpretation": section.model_dump(mode="json"),
                "reconciliation": reconciliation.model_dump(mode="json"),
            }

            def validate_audit_candidate(
                value: AuditCandidate, current: SectionResult = section
            ) -> None:
                validate_audit(current, value)

            audit = await self._step(
                record,
                "policy_audit",
                packet,
                AuditCandidate,
                audit_call,
                validate_audit_candidate,
            )
            audits.append(audit)
        self._update(record.build_id, phase="compiling")
        policy, coverage = compile_policy(
            inputs.document,
            inputs.extraction,
            section_results,
            reconciliation,
            tuple(audits),
            policy_id="policy-" + record.build_id,
        )
        return policy, coverage, reconciliation

    async def _execute(self, identity: str) -> None:
        record = self._update(identity, status="running", phase="extracting")
        try:
            async with asyncio.timeout(self.limits.build_timeout_seconds):
                document = self.store.get_document(record.document_id)
                extraction = await self._extract(document)
                self._update(identity, extraction=extraction)
                cached = (
                    None
                    if record.generation_id == identity
                    else self.store.find_completed_build(
                        record.fingerprint, generation_id=record.generation_id
                    )
                )
                if cached is not None and cached.extraction is not None:
                    if cached.extraction.pages != extraction.pages:
                        raise StorageConflict("Saved build extraction text/layout does not match")
                    policy = (
                        self.store.bind_document_artifact(cached.policy, document, extraction)
                        if cached.policy
                        else None
                    )
                    chart = (
                        self.store.bind_document_artifact(cached.chart, document, extraction)
                        if cached.chart
                        else None
                    )
                    coverage = tuple(
                        self.store.bind_document_artifact(item, document, extraction)
                        for item in cached.coverage
                    )
                    self._update(
                        identity,
                        status="completed",
                        phase="complete",
                        policy=policy,
                        chart=chart,
                        configuration=cached.configuration,
                        coverage=coverage,
                        steps=cached.steps,
                        issues=cached.issues,
                        resolutions=cached.resolutions,
                        completed_sections=cached.total_sections,
                        total_sections=cached.total_sections,
                        review_status=cached.review_status,
                        cached=True,
                        reused_from_build_id=cached.build_id,
                    )
                    return
                inputs = DocumentInputs(document, extraction)
                if document.role == DocumentRole.POLICY:
                    policy, coverage, reconciliation = await self._guideline(record, inputs)
                    self._update(
                        identity,
                        status="completed",
                        phase="complete",
                        policy=policy,
                        coverage=coverage,
                        resolutions=reconciliation.resolutions if reconciliation else (),
                        issues=tuple(issue.message for issue in policy.issues),
                    )
                else:
                    self._update(identity, phase="extracting_chart", total_sections=1)

                    async def chart_call() -> ModelStep[ChartData]:
                        interpreted = await self.interpreter.chart(inputs)
                        return ModelStep(interpreted.chart, interpreted.usage)

                    packet = json.loads(render_document_input(inputs))
                    chart = await self._step(record, "chart", packet, ChartData, chart_call)
                    resolver = CitationResolver((document,), (extraction,))
                    for fact in chart.facts:
                        for source in fact.sources:
                            resolver.validate(source)
                    self._update(
                        identity,
                        status="completed",
                        phase="complete",
                        chart=chart,
                        completed_sections=1,
                        issues=chart.interpretation_issues,
                    )
        except asyncio.CancelledError:
            raise
        except InterpretationFailure as exc:
            self._update(identity, status="failed", error=exc.error)
        except PdfInputError as exc:
            self._update(identity, status="failed", error=exc.error)
        except TimeoutError:
            self._update(
                identity,
                status="failed",
                error=_error(
                    ErrorCode.TIMEOUT,
                    "Document preparation exceeded its processing deadline.",
                    "Retry this build to reuse completed sections.",
                    retryable=True,
                ),
            )
        except (ValueError, CitationError) as exc:
            code = (
                ErrorCode.CITATION_INVALID
                if isinstance(exc, CitationError)
                else ErrorCode.INVALID_OUTPUT
            )
            self._update(
                identity,
                status="failed",
                error=_error(
                    code,
                    "Document build failed source, coverage, or rule validation: " + str(exc)[:300],
                    "Inspect the source and build diagnostics; retry with corrected inputs.",
                ),
            )
        except StorageError:
            self._update(
                identity,
                status="failed",
                error=_error(
                    ErrorCode.STATE_CONFLICT,
                    "A saved build/checkpoint is rejected, incompatible, or corrupt.",
                    "Inspect the saved build and explicitly rebuild a new version.",
                ),
            )
