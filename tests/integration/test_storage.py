"""Real SQLite/filesystem tests using fictional bytes, without PDF or model calls."""

import hashlib
import json
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import (
    ApplicabilityResult,
    ApplicabilityStatus,
    AssessmentOutcome,
    AssessmentResult,
    ConfigurationProvenance,
    DocumentRecord,
    DocumentRole,
    ExtractedPage,
    ExtractionMethod,
    ExtractionRecord,
    FieldSources,
    InferenceSettings,
    PageInventory,
    PageQuality,
    RequestContext,
    RequestField,
    RunPhase,
    RunRecord,
    RunStatus,
    SourceSpan,
    TextAnnotation,
    TextBlock,
    VersionReference,
)
from app.storage import (
    LocalStore,
    StorageConflict,
    StorageIntegrityError,
    StorageNotFound,
    StorageReferenceError,
    assessment_fingerprint,
    fingerprint,
)
from app.storage.identity import canonical_bytes

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
PHASE = RunPhase.CHECKING_APPLICABILITY
CONFIG = ConfigurationProvenance(
    parser=VersionReference(name="fictional-parser", version="1"),
    parser_configuration_sha256="d" * 64,
    prompts=(VersionReference(name="scope", version="1"),),
    model_id="fictional-model",
    sdk_version="fixture-1",
    inference=InferenceSettings(max_output_tokens=500),
)


def replace(record, **changes):
    return type(record).model_validate_json(record.model_copy(update=changes).model_dump_json())


def document(store, name, role, content=None):
    # Storage takes intake-validated bytes; PDF format validation belongs to WP-04.
    content = content or f"fictional original {name}".encode()
    result = DocumentRecord(
        document_id=name,
        role=role,
        filename=f"{name}.pdf",
        sha256=hashlib.sha256(content).hexdigest(),
        byte_count=len(content),
        page_count=1,
        pages=(PageInventory(page=1),),
        created_at=NOW,
    )
    return store.put_document(result, content)


def extraction(store, doc, revision="1"):
    result = ExtractionRecord(
        extraction_id=f"{doc.document_id}-extraction-{revision}",
        document_id=doc.document_id,
        document_sha256=doc.sha256,
        parser_name=CONFIG.parser.name,
        parser_version=revision,
        configuration_sha256=CONFIG.parser_configuration_sha256,
        created_at=NOW,
        pages=(
            ExtractedPage(
                page=1,
                quality=PageQuality.USABLE,
                method=ExtractionMethod.NATIVE_TEXT,
                blocks=(TextBlock(block_id="block-1", text="Fictional source.", reading_order=0),),
            ),
        ),
    )
    return store.put_extraction(result)


def span(extracted):
    text = extracted.pages[0].blocks[0].text
    return SourceSpan(
        document_id=extracted.document_id,
        document_sha256=extracted.document_sha256,
        extraction_id=extracted.extraction_id,
        page=1,
        block_id="block-1",
        start=0,
        end=len(text),
        excerpt=text,
    )


def scope(extracted):
    return ApplicabilityResult(
        status=ApplicabilityStatus.UNRESOLVED,
        rationale="The fictional plan needs clarification.",
        sources=(span(extracted),),
        unresolved_fields=(RequestField.PLAN,),
    )


def new_run(store, policy, chart, name="run-1", **changes):
    configuration = changes.pop("configuration", CONFIG)
    context = changes.pop("request_context", None)
    annotations = changes.pop("annotations", ())
    record = RunRecord(
        run_id=name,
        policy_document_id=policy.document_id,
        policy_sha256=policy.sha256,
        chart_document_id=chart.document_id,
        chart_sha256=chart.sha256,
        input_fingerprint=assessment_fingerprint(
            policy, chart, configuration, context, annotations
        ),
        configuration=configuration,
        request_context=context,
        annotations=annotations,
        created_at=NOW,
        updated_at=NOW,
        status=RunStatus.QUEUED,
        **changes,
    )
    return store.create_run(record)


def start(store, record):
    return store.update_run(
        replace(
            record,
            status=RunStatus.RUNNING,
            phase=PHASE,
            updated_at=NOW + timedelta(seconds=1),
        ),
        expected=record,
    )


@pytest.fixture
def prepared(tmp_path):
    store = LocalStore(tmp_path / "data")
    policy = document(store, "policy", DocumentRole.POLICY)
    chart = document(store, "chart", DocumentRole.CHART)
    extracted = extraction(store, policy)
    return store, policy, chart, extracted


def publish(store, run, extracted, value=None, **changes):
    return store.put_validated_artifact(
        run.run_id,
        PHASE,
        value or scope(extracted),
        extraction_ids=(extracted.extraction_id,),
        validation_version="provenance-v1",
        **changes,
    )


def lookup(store, run, extracted, **changes):
    options = {
        "extraction_ids": (extracted.extraction_id,),
        "validation_version": "provenance-v1",
    }
    options.update(changes)
    return store.find_artifact(run.run_id, PHASE, ApplicabilityResult, **options)


def test_duplicate_bytes_keep_role_metadata_separate_and_immutable(tmp_path):
    store = LocalStore(tmp_path)
    content = b"shared fictional original"
    policy = document(store, "policy", DocumentRole.POLICY, content)
    chart = document(store, "chart", DocumentRole.CHART, content)
    assert policy.document_id != chart.document_id and policy.sha256 == chart.sha256
    assert len(list((tmp_path / "blobs").iterdir())) == 1
    assert LocalStore(tmp_path).read_document(chart.document_id) == content
    assert store.get_document(policy.document_id, expected_role=DocumentRole.POLICY) == policy
    with pytest.raises(StorageReferenceError, match="role"):
        store.get_document(chart.document_id, expected_role=DocumentRole.POLICY)
    with pytest.raises(StorageConflict, match="immutable"):
        store.put_document(replace(policy, role=DocumentRole.CHART), content)
    with pytest.raises(StorageReferenceError, match="bytes"):
        store.put_document(policy, b"changed bytes")
    assert store.get_document(policy.document_id) == policy


def test_extractions_are_versioned_and_bound_to_exact_document(prepared):
    store, policy, chart, old = prepared
    newer = extraction(store, policy, revision="2")
    assert store.list_extractions(policy.document_id) == (old, newer)
    assert (
        LocalStore(store.root).get_extraction(old.extraction_id, document_id=policy.document_id)
        == old
    )
    with pytest.raises(StorageNotFound):
        store.get_extraction(old.extraction_id, document_id=chart.document_id)
    with pytest.raises(StorageConflict):
        store.put_extraction(replace(old, parser_version="changed"))
    with pytest.raises(StorageReferenceError):
        store.put_extraction(replace(old, extraction_id="bad-hash", document_sha256="a" * 64))
    with pytest.raises(StorageReferenceError):
        store.put_extraction(
            replace(
                old,
                extraction_id="bad-page-count",
                pages=old.pages + (replace(old.pages[0], page=2),),
            )
        )


def test_run_snapshots_cas_and_child_clarification_preserve_parent(prepared):
    store, policy, chart, extracted = prepared
    queued = new_run(store, policy, chart)
    running = start(store, queued)
    with pytest.raises(StorageConflict, match="changed since"):
        store.update_run(replace(running, phase=RunPhase.INTERPRETING_POLICY), expected=queued)
    stopped = store.update_run(
        replace(running, status=RunStatus.NEEDS_INPUT, applicability=scope(extracted)),
        expected=running,
    )
    annotation = TextAnnotation(
        annotation_id="annotation-1",
        field="plan",
        value="Fictional plan",
        created_at=NOW,
    )
    child = new_run(
        store,
        policy,
        chart,
        name="child",
        parent_run_id=stopped.run_id,
        annotations=(annotation,),
    )
    assert child.input_fingerprint != stopped.input_fingerprint
    assert child.parent_run_id == stopped.run_id
    assert store.get_run(stopped.run_id) == stopped
    assert store.run_history(stopped.run_id) == (queued, running, stopped)
    with pytest.raises(StorageConflict, match="Stopped"):
        store.update_run(
            replace(stopped, request_context=RequestContext(plan="changed")),
            expected=stopped,
        )
    assert LocalStore(store.root).get_run(child.run_id).annotations == (annotation,)


def test_active_run_inputs_cannot_change_and_discovered_context_can(prepared):
    store, policy, chart, _ = prepared
    queued = new_run(store, policy, chart)
    running = start(store, queued)
    with pytest.raises(StorageConflict, match="inputs"):
        store.update_run(
            replace(running, configuration=replace(CONFIG, model_id="another")),
            expected=running,
        )
    with pytest.raises(StorageConflict, match="stopped run"):
        new_run(store, policy, chart, name="too-early", parent_run_id=running.run_id)
    updated = store.update_run(
        replace(
            running,
            request_context=RequestContext(procedure="Discovered fictional request"),
        ),
        expected=running,
    )
    assert updated.input_fingerprint == queued.input_fingerprint
    assert store.run_history(queued.run_id)[0].request_context is None


def test_wrong_source_refs_and_forged_fingerprint_are_rejected(prepared):
    store, policy, chart, extracted = prepared
    queued = new_run(store, policy, chart)
    with pytest.raises(StorageReferenceError, match="fingerprint"):
        store.create_run(replace(queued, run_id="forged", input_fingerprint="f" * 64))
    with pytest.raises(StorageNotFound):
        store.create_run(replace(queued, run_id="unknown-parent", parent_run_id="missing"))
    with pytest.raises(StorageReferenceError, match="roles or hashes"):
        store.create_run(
            replace(
                queued,
                run_id="wrong-role",
                policy_document_id=chart.document_id,
                chart_document_id=policy.document_id,
            )
        )
    wrong_extraction = extraction(store, chart)
    bad_source = replace(span(extracted), extraction_id=wrong_extraction.extraction_id)
    context = RequestContext(
        procedure="Fictional request",
        field_sources=(FieldSources(field=RequestField.PROCEDURE, sources=(bad_source,)),),
    )
    with pytest.raises(StorageNotFound):
        new_run(store, policy, chart, name="wrong-source", request_context=context)


def test_completed_result_survives_changed_policy_and_restart(prepared):
    store, policy, chart, extracted = prepared
    running = start(store, new_run(store, policy, chart))
    mismatch = ApplicabilityResult(
        status=ApplicabilityStatus.MISMATCH,
        rationale="Fictional incompatible procedure.",
        sources=(span(extracted),),
    )
    completed = store.update_run(
        replace(
            running,
            status=RunStatus.COMPLETED,
            result=AssessmentResult(
                outcome=AssessmentOutcome.APPLICABILITY_MISMATCH, applicability=mismatch
            ),
        ),
        expected=running,
    )
    new_policy = document(store, "policy-v2", DocumentRole.POLICY, b"changed fictional policy")
    child = new_run(store, new_policy, chart, name="new-version", parent_run_id=completed.run_id)
    recovered = LocalStore(store.root).interrupt_unfinished(at=NOW + timedelta(seconds=4))
    assert tuple(item.run_id for item in recovered) == (child.run_id,)
    assert store.get_run(completed.run_id) == completed
    assert store.read_document(policy.document_id) == b"fictional original policy"
    assert (
        store.get_extraction(extracted.extraction_id, document_id=policy.document_id) == extracted
    )


def test_restart_marks_queued_and_running_once_without_mutating_stopped_attempts(
    prepared,
):
    store, policy, chart, _ = prepared
    queued = new_run(store, policy, chart, name="queued")
    running = start(store, new_run(store, policy, chart, name="running"))
    reopened = LocalStore(store.root)
    assert reopened.get_run(queued.run_id).status == RunStatus.QUEUED  # Explicit startup action.
    interrupted = reopened.interrupt_unfinished(at=NOW + timedelta(seconds=10))
    assert {record.run_id for record in interrupted} == {queued.run_id, running.run_id}
    assert all(
        record.status == RunStatus.INTERRUPTED and record.error.retryable for record in interrupted
    )
    assert reopened.get_run(running.run_id).phase == PHASE
    assert reopened.interrupt_unfinished() == ()
    assert reopened.run_history(running.run_id)[-2] == running


def _omit_later_optional_fields(store, run_id):
    """Rewrite the latest snapshot as JSON saved before later optional run fields."""
    payload = json.loads(canonical_bytes(store.get_run(run_id)))
    for key in (
        "requested_policy_build_id",
        "requested_chart_build_id",
        "policy_build_configuration",
        "chart_build_configuration",
        "policy_build_id",
        "chart_build_id",
        "policy_rule_set_id",
        "chart_interpretation_id",
        "policy_path_id",
    ):
        payload.pop(key, None)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (store.root / "objects" / digest).write_bytes(raw)
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            """UPDATE run_snapshots SET payload_sha256=?
               WHERE run_id=? AND revision=(SELECT revision FROM runs WHERE run_id=?)""",
            (digest, run_id, run_id),
        )
        connection.commit()
    finally:
        connection.close()
    loaded = store.get_run(run_id)
    assert fingerprint(loaded) != digest
    return loaded


def test_older_snapshot_missing_optional_fields_can_still_be_updated_and_interrupted(
    prepared,
):
    store, policy, chart, _ = prepared
    queued = new_run(store, policy, chart, name="legacy-queued")
    running = start(store, new_run(store, policy, chart, name="legacy-running"))
    reloaded_queued = _omit_later_optional_fields(store, queued.run_id)
    reloaded_running = _omit_later_optional_fields(store, running.run_id)
    assert reloaded_queued == queued and reloaded_running == running
    stale = store.run_history(running.run_id)[0]
    with pytest.raises(StorageConflict, match="changed since"):
        store.update_run(
            replace(
                reloaded_running,
                phase=RunPhase.VALIDATING,
                updated_at=NOW + timedelta(seconds=2),
            ),
            expected=stale,
        )
    advanced = store.update_run(
        replace(
            reloaded_queued,
            status=RunStatus.RUNNING,
            phase=PHASE,
            updated_at=NOW + timedelta(seconds=2),
        ),
        expected=reloaded_queued,
    )
    assert advanced.status == RunStatus.RUNNING
    interrupted = store.interrupt_unfinished(at=NOW + timedelta(seconds=3))
    assert {record.run_id for record in interrupted} == {queued.run_id, running.run_id}
    assert all(record.status == RunStatus.INTERRUPTED for record in interrupted)
    assert store.run_history(running.run_id)[-2] == running


def test_compatible_completed_stage_reuses_actual_saved_output_after_failed_attempt(
    prepared,
):
    store, policy, chart, extracted = prepared
    run = start(store, new_run(store, policy, chart))
    saved = publish(store, run, extracted)
    store.interrupt_unfinished(at=NOW + timedelta(seconds=2))
    child = new_run(store, policy, chart, name="retry", parent_run_id=run.run_id)
    found = lookup(LocalStore(store.root), child, extracted)
    assert found == saved and found.value == scope(extracted)
    assert found.run_id == run.run_id  # Cache provenance is not rewritten to the new attempt.
    assert store.get_artifact(saved.artifact_id, ApplicabilityResult) == saved


@pytest.mark.parametrize(
    "change",
    [
        "model",
        "sdk",
        "parser",
        "parser_config",
        "prompt",
        "inference",
        "request",
        "annotation",
        "document",
    ],
)
def test_configuration_input_and_annotation_changes_do_not_reuse(prepared, change):
    store, policy, chart, extracted = prepared
    original = start(store, new_run(store, policy, chart))
    publish(store, original, extracted)
    options = {}
    config = CONFIG
    if change == "model":
        config = replace(config, model_id="different-model")
    elif change == "sdk":
        config = replace(config, sdk_version="fixture-2")
    elif change == "parser":
        config = replace(config, parser=VersionReference(name="fictional-parser", version="2"))
    elif change == "parser_config":
        config = replace(config, parser_configuration_sha256="e" * 64)
    elif change == "prompt":
        config = replace(config, prompts=(VersionReference(name="scope", version="2"),))
    elif change == "inference":
        config = replace(config, inference=InferenceSettings(max_output_tokens=1000))
    elif change == "request":
        options["request_context"] = RequestContext(procedure="Another fictional request")
    elif change == "annotation":
        options["annotations"] = (
            TextAnnotation(annotation_id="new", field="plan", value="Plan", created_at=NOW),
        )
    elif change == "document":
        chart = document(store, "changed-chart", DocumentRole.CHART, b"changed source")
    other = new_run(store, policy, chart, name="other", configuration=config, **options)
    assert other.input_fingerprint != original.input_fingerprint
    assert lookup(store, other, extracted) is None


def test_extraction_validation_and_output_schema_changes_invalidate_cache(prepared):
    store, policy, chart, extracted = prepared
    run = start(store, new_run(store, policy, chart))
    publish(store, run, extracted)
    newer = extraction(store, policy, revision="2")
    assert lookup(store, run, newer) is None
    assert lookup(store, run, extracted, validation_version="provenance-v2") is None
    assert (
        store.find_artifact(
            run.run_id,
            PHASE,
            RequestContext,
            extraction_ids=(extracted.extraction_id,),
            validation_version="provenance-v1",
        )
        is None
    )
    discovered = store.update_run(
        replace(run, request_context=RequestContext(plan="Discovered")), expected=run
    )
    assert lookup(store, discovered, extracted) is None


def test_duplicate_bytes_do_not_rebind_cached_citations_to_a_new_upload(prepared):
    store, policy, chart, extracted = prepared
    original = start(store, new_run(store, policy, chart))
    saved = publish(store, original, extracted)
    duplicate = document(
        store, "duplicate-policy", DocumentRole.POLICY, store.read_document(policy.document_id)
    )
    duplicate_extraction = extraction(store, duplicate)
    second = new_run(store, duplicate, chart, name="different-upload-id")
    assert duplicate.sha256 == policy.sha256
    assert second.input_fingerprint != original.input_fingerprint
    assert lookup(store, second, duplicate_extraction) is None
    assert store.get_artifact(saved.artifact_id, ApplicabilityResult).value.sources[0] == span(
        extracted
    )


def test_artifact_requires_active_phase_and_complete_reference_identity(prepared):
    store, policy, chart, extracted = prepared
    queued = new_run(store, policy, chart)
    with pytest.raises(StorageConflict):
        publish(store, queued, extracted)
    running = start(store, queued)
    with pytest.raises(StorageReferenceError, match="Cited extraction"):
        store.put_validated_artifact(
            running.run_id, PHASE, scope(extracted), validation_version="v1"
        )
    unrelated = document(store, "unrelated-policy", DocumentRole.POLICY)
    unrelated_extraction = extraction(store, unrelated)
    with pytest.raises(StorageReferenceError, match="another input"):
        lookup(store, running, unrelated_extraction)
    with pytest.raises(StorageReferenceError, match="run's inputs"):
        publish(store, running, unrelated_extraction)
    malformed = scope(extracted).model_copy(update={"rationale": ""})
    with pytest.raises(ValidationError):
        publish(store, running, extracted, value=malformed)
    assert lookup(store, running, extracted) is None


def test_upstream_actual_output_participates_in_downstream_identity(prepared):
    store, policy, chart, extracted = prepared
    run = start(store, new_run(store, policy, chart))
    first = publish(store, run, extracted)
    second = publish(
        store,
        run,
        extracted,
        value=replace(scope(extracted), rationale="Different saved judgment."),
    )
    assert first.fingerprint == second.fingerprint
    assert first.payload_sha256 != second.payload_sha256
    downstream = publish(store, run, extracted, upstream_artifact_ids=(first.artifact_id,))
    assert lookup(store, run, extracted, upstream_artifact_ids=(first.artifact_id,)) == downstream
    assert lookup(store, run, extracted, upstream_artifact_ids=(second.artifact_id,)) is None


@pytest.mark.parametrize("damage", ["missing", "corrupt", "missing-key"])
def test_damaged_artifacts_are_not_cache_hits(prepared, damage):
    store, policy, chart, extracted = prepared
    run = start(store, new_run(store, policy, chart))
    saved = publish(store, run, extracted)
    digest = saved.fingerprint if damage == "missing-key" else saved.payload_sha256
    path = store.root / "objects" / digest
    if damage == "corrupt":
        path.write_bytes(b"corrupt")
    else:
        path.unlink()
    with pytest.raises(StorageIntegrityError):
        store.get_artifact(saved.artifact_id, ApplicabilityResult)
    assert lookup(store, run, extracted) is None


def test_interrupted_file_publish_never_creates_document_metadata(tmp_path, monkeypatch):
    store = LocalStore(tmp_path)

    def fail_publish(*args):
        raise OSError("simulated crash before publish")

    monkeypatch.setattr(os, "link", fail_publish)
    with pytest.raises(OSError):
        document(store, "failed-upload", DocumentRole.POLICY)
    with pytest.raises(StorageNotFound):
        store.get_document("failed-upload")
    assert not list((tmp_path / "blobs").iterdir())


def test_metadata_failure_after_files_exist_does_not_publish_reusable_artifact(
    prepared,
):
    store, policy, chart, extracted = prepared
    run = start(store, new_run(store, policy, chart))
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "CREATE TRIGGER fail_artifact BEFORE INSERT ON artifacts "
            "BEGIN SELECT RAISE(ABORT, 'simulated metadata failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        publish(store, run, extracted)
    assert lookup(store, run, extracted) is None
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0] == 0
        connection.execute("DROP TRIGGER fail_artifact")
    assert publish(store, run, extracted).value == scope(extracted)


def test_failed_snapshot_write_retains_previous_revision(prepared, monkeypatch):
    store, policy, chart, _ = prepared
    queued = new_run(store, policy, chart)
    original_write = store._write_object

    def write_then_fail(data, **options):
        original_write(data, **options)
        raise OSError("simulated interruption before metadata commit")

    monkeypatch.setattr(store, "_write_object", write_then_fail)
    with pytest.raises(OSError):
        start(store, queued)
    assert store.get_run(queued.run_id) == queued
    assert store.run_history(queued.run_id) == (queued,)
    monkeypatch.setattr(store, "_write_object", original_write)
    assert start(store, queued).status == RunStatus.RUNNING


def test_concurrent_stale_writers_cannot_lose_a_run_update(prepared):
    store, policy, chart, _ = prepared
    queued = new_run(store, policy, chart)
    second_store = LocalStore(store.root)

    def change(target):
        try:
            return start(target, queued).status
        except StorageConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(change, (store, second_store)))
    assert sorted(results) == ["conflict", RunStatus.RUNNING]
    assert len(store.run_history(queued.run_id)) == 2


def test_fingerprint_is_stable_and_rejects_non_json_numbers():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    with pytest.raises(ValueError):
        fingerprint({"invalid": float("nan")})
