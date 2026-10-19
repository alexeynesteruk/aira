"""Durable builds on actual 100/200-page PDFs; scripted interpretation, no API calls."""

import asyncio
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest
from long_support import StructuralInterpreter
from support import CREATED_AT, configuration

from app.assessment.builds import DocumentBuildService
from app.documents import NativePdfConfig, inspect_pdf
from app.policies.compiler import BuildLimits, plan_sections, select_policy_path, validate_section
from app.schemas import CandidateCitation, DocumentRole
from app.schemas.builds import BuildRequest
from app.storage import LocalStore, StorageConflict

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/long-documents"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def upload(store, count=100, identity="policy"):
    path = FIXTURES / f"guideline-{count}.pdf"
    raw = path.read_bytes()
    document = inspect_pdf(
        raw,
        document_id=identity,
        filename=path.name,
        role=DocumentRole.POLICY,
        created_at=CREATED_AT,
    )
    store.put_document(document, raw)
    return document


def service(store, interpreter, limits=None, section_concurrency=4):
    return DocumentBuildService(
        store,
        interpreter,
        configuration(),
        parser_config=NativePdfConfig(),
        limits=limits,
        section_concurrency=section_concurrency,
    )


@pytest.mark.anyio
async def test_a_stopped_worker_fails_a_build_left_in_progress(tmp_path):
    store = LocalStore(tmp_path / "store")
    path = Path(__file__).resolve().parents[2] / "examples/synthetic/monitor_policy.pdf"
    raw = path.read_bytes()
    document = inspect_pdf(
        raw,
        document_id="policy",
        filename=path.name,
        role=DocumentRole.POLICY,
        created_at=CREATED_AT,
    )
    store.put_document(document, raw)
    builds = service(store, StructuralInterpreter(gate=asyncio.Event()))
    await builds.start()
    accepted = await builds.submit(document.document_id)
    for _ in range(100):
        if store.get_build(accepted.build_id).status == "running":
            break
        await asyncio.sleep(0.05)
    assert builds._worker is not None
    builds._worker.cancel()
    with pytest.raises(asyncio.CancelledError):
        await builds._worker
    result = await builds.wait(accepted.build_id)
    assert result.status == "failed"
    assert result.error is not None and result.error.retryable
    assert "in progress" in result.error.message
    await builds.close()


@pytest.mark.anyio
@pytest.mark.parametrize("count", [100, 200])
async def test_complete_native_long_build_has_all_gold_rules_and_separate_paths(tmp_path, count):
    store = LocalStore(tmp_path / "store")
    doc = upload(store, count)
    interpreter = StructuralInterpreter()
    limits = replace(BuildLimits(), input_tokens=40_000) if count == 200 else BuildLimits()
    builds = service(store, interpreter, limits)
    await builds.start()
    try:
        accepted = await builds.submit(doc.document_id)
        result = await builds.wait(accepted.build_id)
        assert result.status == "completed", result.error
        assert result.policy and result.extraction
        gold = json.loads((FIXTURES / f"gold-{count}.json").read_text())
        assert len(result.extraction.pages) == count
        assert {item.wording for item in result.policy.criteria} == {
            item["wording"] for item in gold["rules"]
        }
        expected = {
            (page.page, block.block_id) for page in result.extraction.pages for block in page.blocks
        }
        assert {(item.source.page, item.source.block_id) for item in result.coverage} == expected
        assert all(item.audited for item in result.coverage)
        assert result.completed_sections == result.total_sections > 1
        assert len(result.resolutions) == 2
        if count == 200:
            assert any(step.name == "policy_merge" for step in result.steps)
        assert any("Exception relationship" in item for item in result.issues)
        alpha, beta = (select_policy_path(result.policy, name) for name in ("Alpha", "Beta"))
        assert len(alpha.criteria) == len(beta.criteria) == count // 2
        assert all(item.wording.startswith("Alpha") for item in alpha.criteria)
        assert all(item.wording.startswith("Beta") for item in beta.criteria)
        with pytest.raises(ValueError, match="select a sourced"):
            select_policy_path(result.policy, None)
        first_calls = interpreter.structural_calls.copy()
        reused = await builds.wait((await builds.submit(doc.document_id)).build_id)
        assert reused.cached and reused.usage == ()
        assert interpreter.structural_calls == first_calls
        duplicate = upload(store, count, "duplicate")
        rebound = await builds.prepare(duplicate)
        assert rebound.cached and rebound.policy.document_id == "duplicate"
        assert all(item.source.document_id == "duplicate" for item in rebound.coverage)
        assert store.get_build(result.build_id).policy.document_id == "policy"
        builds.review(reused.build_id, approve=False)
        # A newer duplicate binding cannot bypass rejection of its reuse ancestor.
        with pytest.raises(StorageConflict, match="rejected"):
            await builds.prepare(duplicate, rebound.build_id)
        with pytest.raises(StorageConflict, match="rejected"):
            await builds.prepare(doc, reused.build_id)
        rebuilt = await builds.wait(
            (
                await builds.submit(
                    doc.document_id, BuildRequest(parent_build_id=reused.build_id, rebuild=True)
                )
            ).build_id
        )
        assert rebuilt.status == "completed" and not rebuilt.cached
        assert rebuilt.parent_build_id == reused.build_id
        assert rebuilt.review_status == "draft"
    finally:
        await builds.close()


@pytest.mark.anyio
async def test_failed_section_retry_reuses_only_valid_completed_checkpoints(tmp_path):
    store = LocalStore(tmp_path / "store")
    doc = upload(store)
    interpreter = StructuralInterpreter(fail_section="section-0002")
    builds = service(store, interpreter, section_concurrency=1)
    await builds.start()
    failed = await builds.wait((await builds.submit(doc.document_id)).build_id)
    assert failed.status == "failed" and failed.policy is None and failed.completed_sections == 1
    await builds.close()
    retry_interpreter = StructuralInterpreter()
    restarted = service(LocalStore(store.root), retry_interpreter, section_concurrency=1)
    await restarted.start()
    try:
        retried = await restarted.wait(
            (
                await restarted.submit(
                    doc.document_id, BuildRequest(parent_build_id=failed.build_id)
                )
            ).build_id
        )
        assert retried.status == "completed", retried.error
        assert retry_interpreter.structural_calls[("section", "section-0001")] == 0
        assert retry_interpreter.structural_calls[("section", "section-0002")] == 1
        assert store.get_build(failed.build_id) == failed
        # A failed explicit rebuild must resume its own generation, never select the older success.
        retry_interpreter.fail_section = "section-0002"
        rebuilt_failure = await restarted.wait(
            (
                await restarted.submit(
                    doc.document_id, BuildRequest(parent_build_id=retried.build_id, rebuild=True)
                )
            ).build_id
        )
        assert rebuilt_failure.status == "failed" and rebuilt_failure.completed_sections == 1
        before = retry_interpreter.structural_calls[("section", "section-0001")]
        retry_interpreter.fail_section = None
        resumed = await restarted.wait(
            (
                await restarted.submit(
                    doc.document_id, BuildRequest(parent_build_id=rebuilt_failure.build_id)
                )
            ).build_id
        )
        assert resumed.status == "completed" and not resumed.cached
        assert resumed.generation_id == rebuilt_failure.build_id
        assert resumed.policy.policy_id != retried.policy.policy_id
        assert retry_interpreter.structural_calls[("section", "section-0001")] == before
    finally:
        await restarted.close()


@pytest.mark.anyio
async def test_coalescing_interrupt_and_explicit_budget_failure(tmp_path):
    store = LocalStore(tmp_path / "store")
    doc = upload(store)
    gate = asyncio.Event()
    builds = service(store, StructuralInterpreter(gate=gate))
    await builds.start()
    first, second = await asyncio.gather(
        builds.submit(doc.document_id), builds.submit(doc.document_id)
    )
    assert first.build_id == second.build_id
    await asyncio.sleep(0.1)
    await builds.close()
    assert store.get_build(first.build_id).status == "interrupted"
    limited = service(store, StructuralInterpreter(), replace(BuildLimits(), max_calls=1))
    await limited.start()
    try:
        failed = await limited.wait((await limited.submit(doc.document_id)).build_id)
        assert failed.status == "failed" and failed.error.code == "unsupported_input"
        assert failed.policy is None
    finally:
        await limited.close()


@pytest.mark.anyio
async def test_invalid_spans_and_incomplete_audit_are_not_reusable(tmp_path):
    class BadAudit(StructuralInterpreter):
        async def audit(self, inputs, section, reconciliation):
            step = await super().audit(inputs, section, reconciliation)
            return replace(step, value=step.value.model_copy(update={"checked_unit_ids": ()}))

    store = LocalStore(tmp_path / "store")
    doc = upload(store)
    builds = service(store, BadAudit())
    await builds.start()
    try:
        failed = await builds.wait((await builds.submit(doc.document_id)).build_id)
        assert failed.status == "failed" and failed.policy is None
        assert "audit did not account" in failed.error.message
        plans = plan_sections(failed.extraction, BuildLimits())
        inputs = __import__("app.assessment.stages", fromlist=["DocumentInputs"]).DocumentInputs(
            doc, failed.extraction
        )
        candidate = (await StructuralInterpreter().section(inputs, plans[0])).value
        fragment = candidate.fragment.model_copy(
            update={
                "criteria": (
                    candidate.fragment.criteria[0].model_copy(
                        update={
                            "citations": (
                                CandidateCitation(
                                    document_id=doc.document_id, page=1, quote="Fabricated quote"
                                ),
                            )
                        }
                    ),
                )
            }
        )
        with pytest.raises(ValueError):
            validate_section(
                doc,
                failed.extraction,
                plans[0],
                candidate.model_copy(update={"fragment": fragment}),
            )
        with sqlite3.connect(store.database_path) as connection:
            # Sections and reconciliation only: the invalid audit is never a checkpoint.
            assert (
                connection.execute("SELECT count(*) FROM document_checkpoints").fetchone()[0]
                == len(plans) + 1
            )
    finally:
        await builds.close()


def test_backend_build_guardrails_read_explicit_values_and_reject_bad_limits(tmp_path):
    from app.assessment.build_config import build_limits_from_environment

    selected = build_limits_from_environment(
        env_file=tmp_path / "missing",
        environ={
            "AIRA_BUILD_INPUT_TOKENS": "50000",
            "AIRA_BUILD_MAX_CALLS": "500",
        },
        output_tokens=8000,
    )
    assert selected.input_tokens == 50000 and selected.max_calls == 500
    assert selected.output_tokens == 8000
    with pytest.raises(ValueError):
        build_limits_from_environment(
            env_file=tmp_path / "missing", environ={"AIRA_BUILD_CALL_TIMEOUT_SECONDS": "nan"}
        )


def test_request_reservation_covers_actual_provider_instructions_and_strict_schema():
    from app.llm.openai_adapter import strict_output_schema
    from app.llm.prompts import PROMPTS
    from app.storage.identity import canonical_bytes

    # The envelope/instruction reserve is independently checked against the actual wire schemas.
    for name in ("policy_section", "policy_reconcile", "policy_merge", "policy_audit", "chart"):
        prompt = PROMPTS[name]
        reserved = len(canonical_bytes(prompt.output_type.model_json_schema())) + 8192
        actual = (
            len(canonical_bytes(strict_output_schema(prompt.output_type)))
            + len(prompt.instructions.encode())
            + 1024
        )
        assert actual <= reserved, name


def test_relational_build_metadata_cannot_silently_select_another_manifest(tmp_path):
    from app.schemas.builds import BuildRecord
    from app.storage import StorageIntegrityError

    store = LocalStore(tmp_path / "store")
    doc = upload(store)
    record = BuildRecord(
        build_id="build-test",
        document_id=doc.document_id,
        document_sha256=doc.sha256,
        role=doc.role,
        fingerprint="a" * 64,
        configuration=configuration(),
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
        status="queued",
    )
    store.put_build(record)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "UPDATE document_builds SET fingerprint=?, status='completed' WHERE build_id=?",
            ("b" * 64, record.build_id),
        )
    with pytest.raises(StorageIntegrityError, match="metadata"):
        store.get_build(record.build_id)
    with pytest.raises(StorageIntegrityError, match="metadata"):
        store.find_completed_build("b" * 64)
    with pytest.raises(StorageIntegrityError, match="metadata"):
        store.list_builds()
