"""SQLite metadata with file-first, immutable content-addressed objects.

One short-lived SQLite connection per operation supports the local executor's
threads. This is not a queue or a distributed cache. Callers own stage execution
and semantic validation; storage guards identity, references and durable writes.
"""

import hashlib
import os
import re
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ValidationError

from app.schemas import (
    DocumentRecord,
    DocumentRole,
    ErrorCode,
    ExtractionRecord,
    OperationalError,
    RunPhase,
    RunRecord,
    RunStatus,
    SourceSpan,
)

from .identity import assessment_fingerprint, canonical_bytes, fingerprint

_SCHEMA_VERSION = 1
_ACTIVE = frozenset({RunStatus.QUEUED, RunStatus.RUNNING})
_FIXED_RUN_FIELDS = (
    "schema_version",
    "run_id",
    "parent_run_id",
    "policy_document_id",
    "policy_sha256",
    "chart_document_id",
    "chart_sha256",
    "input_fingerprint",
    "configuration",
    "annotations",
    "created_at",
)


class StorageError(Exception):
    """Base exception for an actionable persistence failure."""


class StorageNotFound(StorageError):
    pass


class StorageConflict(StorageError):
    pass


class StorageReferenceError(StorageError):
    pass


class StorageIntegrityError(StorageError):
    pass


@dataclass(frozen=True)
class StoredArtifact[T: BaseModel]:
    artifact_id: str
    run_id: str
    phase: RunPhase
    fingerprint: str
    payload_sha256: str
    schema_fingerprint: str
    validation_version: str
    created_at: datetime
    value: T


def _checked[T: BaseModel](model: type[T], value: T) -> T:
    # model_copy(update=...) bypasses Pydantic validation. Revalidate all layers.
    return model.model_validate_json(canonical_bytes(value))


def _source_spans(value: object) -> Iterator[SourceSpan]:
    if isinstance(value, SourceSpan):
        yield value
    elif isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _source_spans(getattr(value, name))
    elif isinstance(value, (tuple, list)):
        for item in value:
            yield from _source_spans(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _source_spans(item)


class LocalStore:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.database_path = self.root / "aira.sqlite3"
        (self.root / "blobs").mkdir(exist_ok=True)
        (self.root / "objects").mkdir(exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version not in (0, _SCHEMA_VERSION):
                raise StorageIntegrityError("Unsupported local storage schema version")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS documents (
                    document_id TEXT PRIMARY KEY,
                    role TEXT NOT NULL CHECK (role IN ('policy', 'chart')),
                    sha256 TEXT NOT NULL,
                    metadata TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS extractions (
                    extraction_id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(document_id),
                    payload_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS extractions_document ON extractions(document_id);
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    parent_run_id TEXT REFERENCES runs(run_id),
                    policy_document_id TEXT NOT NULL REFERENCES documents(document_id),
                    chart_document_id TEXT NOT NULL REFERENCES documents(document_id),
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS run_snapshots (
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    revision INTEGER NOT NULL CHECK (revision > 0),
                    payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY (run_id, revision)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES runs(run_id),
                    phase TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    schema_fingerprint TEXT NOT NULL,
                    validation_version TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status = 'completed'),
                    validated INTEGER NOT NULL CHECK (validated = 1)
                );
                CREATE INDEX IF NOT EXISTS artifacts_lookup ON artifacts(fingerprint);
                PRAGMA user_version=1;
                COMMIT;
                """
            )
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    @contextmanager
    def _transaction(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _path(self, digest: str, *, original: bool = False) -> Path:
        if re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            raise StorageIntegrityError("Invalid content address in local storage")
        return self.root / ("blobs" if original else "objects") / digest

    def _read_object(self, digest: str, *, original: bool = False) -> bytes:
        try:
            data = self._path(digest, original=original).read_bytes()
        except OSError as exc:
            raise StorageIntegrityError("A referenced immutable file is unavailable") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise StorageIntegrityError("An immutable file does not match its recorded hash")
        return data

    def _write_object(self, data: bytes, *, original: bool = False) -> str:
        digest = hashlib.sha256(data).hexdigest()
        destination = self._path(digest, original=original)
        if destination.exists():
            self._read_object(digest, original=original)
            return digest
        descriptor, temporary_name = tempfile.mkstemp(prefix=".pending-", dir=destination.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # An atomic hard-link publish never replaces an existing object.
                os.link(temporary, destination)
            except FileExistsError:
                self._read_object(digest, original=original)
            directory = os.open(destination.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
        return digest

    def _model[T: BaseModel](self, digest: str, model: type[T]) -> T:
        try:
            return model.model_validate_json(self._read_object(digest))
        except ValidationError as exc:
            raise StorageIntegrityError("A persisted record violates its schema") from exc

    def _document(self, connection: sqlite3.Connection, document_id: str) -> DocumentRecord:
        row = connection.execute(
            "SELECT metadata FROM documents WHERE document_id=?", (document_id,)
        ).fetchone()
        if row is None:
            raise StorageNotFound("Document not found")
        try:
            return DocumentRecord.model_validate_json(str(row["metadata"]))
        except ValidationError as exc:
            raise StorageIntegrityError("Stored document metadata is invalid") from exc

    def put_document(self, record: DocumentRecord, content: bytes) -> DocumentRecord:
        record = _checked(DocumentRecord, record)
        if (
            hashlib.sha256(content).hexdigest() != record.sha256
            or len(content) != record.byte_count
        ):
            raise StorageReferenceError("Document bytes do not match their metadata")
        self._write_object(content, original=True)
        serialized = canonical_bytes(record).decode("utf-8")
        with self._transaction(write=True) as connection:
            row = connection.execute(
                "SELECT metadata FROM documents WHERE document_id=?", (record.document_id,)
            ).fetchone()
            if row is not None:
                if str(row["metadata"]) != serialized:
                    raise StorageConflict("Document IDs are immutable; upload a new document")
                return record
            connection.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?)",
                (record.document_id, record.role.value, record.sha256, serialized),
            )
        return record

    def get_document(
        self, document_id: str, *, expected_role: DocumentRole | None = None
    ) -> DocumentRecord:
        with self._transaction() as connection:
            record = self._document(connection, document_id)
        if expected_role is not None and record.role != expected_role:
            raise StorageReferenceError("Document role does not match the requested input role")
        return record

    def read_document(self, document_id: str) -> bytes:
        record = self.get_document(document_id)
        return self._read_object(record.sha256, original=True)

    def _extraction(
        self, connection: sqlite3.Connection, extraction_id: str, document_id: str
    ) -> ExtractionRecord:
        row = connection.execute(
            "SELECT payload_sha256 FROM extractions WHERE extraction_id=? AND document_id=?",
            (extraction_id, document_id),
        ).fetchone()
        if row is None:
            raise StorageNotFound("Extraction not found for the requested document")
        record = self._model(str(row["payload_sha256"]), ExtractionRecord)
        if record.extraction_id != extraction_id:
            raise StorageIntegrityError("Extraction identity differs from its stored reference")
        document = self._document(connection, document_id)
        self._check_extraction_document(record, document)
        return record

    @staticmethod
    def _check_extraction_document(record: ExtractionRecord, document: DocumentRecord) -> None:
        if (
            record.document_id != document.document_id
            or record.document_sha256 != document.sha256
            or len(record.pages) != document.page_count
        ):
            raise StorageReferenceError("Extraction must account for its exact original document")

    def put_extraction(self, record: ExtractionRecord) -> ExtractionRecord:
        record = _checked(ExtractionRecord, record)
        data = canonical_bytes(record)
        digest = hashlib.sha256(data).hexdigest()
        with self._transaction(write=True) as connection:
            document = self._document(connection, record.document_id)
            self._check_extraction_document(record, document)
            row = connection.execute(
                "SELECT payload_sha256 FROM extractions WHERE extraction_id=?",
                (record.extraction_id,),
            ).fetchone()
            if row is not None:
                if str(row["payload_sha256"]) != digest:
                    raise StorageConflict("Extraction IDs are immutable; create a new revision")
                self._read_object(digest)
                return record
            self._write_object(data)
            connection.execute(
                "INSERT INTO extractions VALUES (?, ?, ?, ?)",
                (record.extraction_id, record.document_id, digest, record.created_at.isoformat()),
            )
        return record

    def get_extraction(self, extraction_id: str, *, document_id: str) -> ExtractionRecord:
        with self._transaction() as connection:
            return self._extraction(connection, extraction_id, document_id)

    def list_extractions(self, document_id: str) -> tuple[ExtractionRecord, ...]:
        with self._transaction() as connection:
            self._document(connection, document_id)
            rows = connection.execute(
                "SELECT extraction_id FROM extractions WHERE document_id=? ORDER BY rowid",
                (document_id,),
            ).fetchall()
            return tuple(
                self._extraction(connection, str(row["extraction_id"]), document_id) for row in rows
            )

    def _run(self, connection: sqlite3.Connection, run_id: str) -> tuple[RunRecord, int, str]:
        row = connection.execute(
            """SELECT r.revision, s.payload_sha256 FROM runs r
               JOIN run_snapshots s ON s.run_id=r.run_id AND s.revision=r.revision
               WHERE r.run_id=?""",
            (run_id,),
        ).fetchone()
        if row is None:
            raise StorageNotFound("Run not found")
        digest = str(row["payload_sha256"])
        record = self._model(digest, RunRecord)
        if record.run_id != run_id:
            raise StorageIntegrityError("Run identity differs from its stored reference")
        return record, int(row["revision"]), digest

    def _check_run_references(self, connection: sqlite3.Connection, record: RunRecord) -> None:
        policy = self._document(connection, record.policy_document_id)
        chart = self._document(connection, record.chart_document_id)
        if (
            policy.role != DocumentRole.POLICY
            or chart.role != DocumentRole.CHART
            or policy.sha256 != record.policy_sha256
            or chart.sha256 != record.chart_sha256
        ):
            raise StorageReferenceError("Run document roles or hashes do not match stored inputs")
        self._check_spans(connection, record, record)

    def _check_spans(
        self, connection: sqlite3.Connection, value: BaseModel, run: RunRecord
    ) -> None:
        inputs = {
            run.policy_document_id: run.policy_sha256,
            run.chart_document_id: run.chart_sha256,
        }
        checked: dict[tuple[str, str], ExtractionRecord] = {}
        for source in _source_spans(value):
            if inputs.get(source.document_id) != source.document_sha256:
                raise StorageReferenceError("Source reference does not belong to this run's inputs")
            key = (source.extraction_id, source.document_id)
            if key not in checked:
                checked[key] = self._extraction(connection, *key)
            if source.page > len(checked[key].pages):
                raise StorageReferenceError("Source page is outside its extraction revision")

    def create_run(self, record: RunRecord) -> RunRecord:
        record = _checked(RunRecord, record)
        if record.status != RunStatus.QUEUED:
            raise StorageConflict("New runs must start queued")
        with self._transaction(write=True) as connection:
            if connection.execute("SELECT 1 FROM runs WHERE run_id=?", (record.run_id,)).fetchone():
                raise StorageConflict("Run ID already exists; create a new attempt")
            self._check_run_references(connection, record)
            if record.parent_run_id is not None:
                parent, _, _ = self._run(connection, record.parent_run_id)
                if parent.status in _ACTIVE:
                    raise StorageConflict("A retry or clarification must reference a stopped run")
            expected = assessment_fingerprint(
                self._document(connection, record.policy_document_id),
                self._document(connection, record.chart_document_id),
                record.configuration,
                record.request_context,
                record.annotations,
            )
            if record.input_fingerprint != expected:
                raise StorageReferenceError("Run fingerprint does not match submitted inputs")
            digest = self._write_object(canonical_bytes(record))
            connection.execute(
                "INSERT INTO runs VALUES (?, ?, ?, ?, 1, ?)",
                (
                    record.run_id,
                    record.parent_run_id,
                    record.policy_document_id,
                    record.chart_document_id,
                    record.status.value,
                ),
            )
            connection.execute(
                "INSERT INTO run_snapshots VALUES (?, 1, ?)", (record.run_id, digest)
            )
        return record

    def get_run(self, run_id: str) -> RunRecord:
        with self._transaction() as connection:
            return self._run(connection, run_id)[0]

    def _update_run(
        self, connection: sqlite3.Connection, record: RunRecord, expected: RunRecord
    ) -> RunRecord:
        current, revision, current_digest = self._run(connection, record.run_id)
        if fingerprint(expected) != current_digest:
            raise StorageConflict("Run changed since it was read; reload before updating")
        if record == current:
            return current
        if current.status not in _ACTIVE:
            raise StorageConflict("Stopped run snapshots are immutable; create a child run")
        if any(getattr(record, name) != getattr(current, name) for name in _FIXED_RUN_FIELDS):
            raise StorageConflict("Run inputs and annotations are immutable; create a child run")
        if record.updated_at < current.updated_at:
            raise StorageConflict("Run updates cannot move backward in time")
        if current.status == RunStatus.QUEUED and record.status not in (
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.FAILED,
            RunStatus.INTERRUPTED,
        ):
            raise StorageConflict("Queued work must enter execution before producing an outcome")
        if current.status == RunStatus.RUNNING and record.status == RunStatus.QUEUED:
            raise StorageConflict("Running work cannot return to the queue")
        self._check_run_references(connection, record)
        digest = self._write_object(canonical_bytes(record))
        connection.execute(
            "INSERT INTO run_snapshots VALUES (?, ?, ?)", (record.run_id, revision + 1, digest)
        )
        connection.execute(
            "UPDATE runs SET revision=?, status=? WHERE run_id=?",
            (revision + 1, record.status.value, record.run_id),
        )
        return record

    def update_run(self, record: RunRecord, *, expected: RunRecord) -> RunRecord:
        record = _checked(RunRecord, record)
        expected = _checked(RunRecord, expected)
        if record.run_id != expected.run_id:
            raise StorageReferenceError("Expected snapshot belongs to a different run")
        with self._transaction(write=True) as connection:
            return self._update_run(connection, record, expected)

    def run_history(self, run_id: str) -> tuple[RunRecord, ...]:
        with self._transaction() as connection:
            self._run(connection, run_id)
            rows = connection.execute(
                "SELECT payload_sha256 FROM run_snapshots WHERE run_id=? ORDER BY revision",
                (run_id,),
            ).fetchall()
            return tuple(self._model(str(row["payload_sha256"]), RunRecord) for row in rows)

    def interrupt_unfinished(self, *, at: datetime | None = None) -> tuple[RunRecord, ...]:
        """Explicit startup recovery, never automatically invoked by a store read."""
        now = at or datetime.now(UTC)
        changed: list[RunRecord] = []
        with self._transaction(write=True) as connection:
            rows = connection.execute(
                "SELECT run_id FROM runs WHERE status IN ('queued', 'running') ORDER BY run_id"
            ).fetchall()
            for row in rows:
                current, _, _ = self._run(connection, str(row["run_id"]))
                interrupted = _checked(
                    RunRecord,
                    current.model_copy(
                        update={
                            "status": RunStatus.INTERRUPTED,
                            "updated_at": max(now, current.updated_at),
                            "error": OperationalError(
                                code=ErrorCode.INTERRUPTED,
                                message="Local execution stopped before this run finished.",
                                retryable=True,
                                action="Start a new run to retry using compatible saved work.",
                                stage=current.phase,
                            ),
                        }
                    ),
                )
                changed.append(self._update_run(connection, interrupted, current))
        return tuple(changed)

    def _artifact_key[T: BaseModel](
        self,
        connection: sqlite3.Connection,
        run: RunRecord,
        phase: RunPhase,
        output_type: type[T],
        extraction_ids: tuple[str, ...],
        upstream_artifact_ids: tuple[str, ...],
        validation_version: str,
    ) -> dict[str, object]:
        if not validation_version.strip():
            raise ValueError("A validation version is required for reusable artifacts")
        if len(set(extraction_ids)) != len(extraction_ids):
            raise StorageReferenceError("Extraction identities must be unique")
        extraction_refs = []
        inputs = {
            run.policy_document_id: run.policy_sha256,
            run.chart_document_id: run.chart_sha256,
        }
        for digest in inputs.values():
            self._read_object(digest, original=True)
        for extraction_id in sorted(extraction_ids):
            row = connection.execute(
                "SELECT document_id, payload_sha256 FROM extractions WHERE extraction_id=?",
                (extraction_id,),
            ).fetchone()
            if row is None:
                raise StorageNotFound("Artifact input extraction not found")
            document_id = str(row["document_id"])
            if document_id not in inputs:
                raise StorageReferenceError("Artifact extraction belongs to another input")
            self._extraction(connection, extraction_id, document_id)
            extraction_refs.append(
                {"extraction_id": extraction_id, "sha256": str(row["payload_sha256"])}
            )
        upstream_refs = []
        for artifact_id in sorted(set(upstream_artifact_ids)):
            row = self._artifact_row(connection, artifact_id)
            origin, _, _ = self._run(connection, str(row["run_id"]))
            if (
                origin.policy_document_id != run.policy_document_id
                or origin.chart_document_id != run.chart_document_id
                or origin.input_fingerprint != run.input_fingerprint
            ):
                raise StorageReferenceError("Upstream artifact belongs to incompatible inputs")
            self._read_object(str(row["payload_sha256"]))
            self._read_object(str(row["fingerprint"]))
            upstream_refs.append(
                {"fingerprint": str(row["fingerprint"]), "sha256": str(row["payload_sha256"])}
            )
        return {
            "artifact_identity_version": 1,
            "phase": phase.value,
            "input_fingerprint": run.input_fingerprint,
            "documents": inputs,
            "configuration": run.configuration.model_dump(mode="json"),
            "request_context": (
                run.request_context.model_dump(mode="json") if run.request_context else None
            ),
            "annotations": [annotation.model_dump(mode="json") for annotation in run.annotations],
            "extractions": extraction_refs,
            "upstream": upstream_refs,
            "output_schema": fingerprint(output_type.model_json_schema()),
            "validation_version": validation_version,
        }

    def _artifact_row(self, connection: sqlite3.Connection, artifact_id: str) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM artifacts WHERE artifact_id=? AND status='completed' AND validated=1",
            (artifact_id,),
        ).fetchone()
        if row is None:
            raise StorageNotFound("Validated artifact not found")
        if not isinstance(row, sqlite3.Row):
            raise StorageIntegrityError("Unexpected artifact metadata shape")
        return row

    def _artifact[T: BaseModel](self, row: sqlite3.Row, output_type: type[T]) -> StoredArtifact[T]:
        if str(row["schema_fingerprint"]) != fingerprint(output_type.model_json_schema()):
            raise StorageReferenceError("Artifact output schema does not match the requested type")
        self._read_object(str(row["fingerprint"]))
        return StoredArtifact(
            artifact_id=str(row["artifact_id"]),
            run_id=str(row["run_id"]),
            phase=RunPhase(row["phase"]),
            fingerprint=str(row["fingerprint"]),
            payload_sha256=str(row["payload_sha256"]),
            schema_fingerprint=str(row["schema_fingerprint"]),
            validation_version=str(row["validation_version"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            value=self._model(str(row["payload_sha256"]), output_type),
        )

    def put_validated_artifact[T: BaseModel](
        self,
        run_id: str,
        phase: RunPhase,
        value: T,
        *,
        extraction_ids: tuple[str, ...] = (),
        upstream_artifact_ids: tuple[str, ...] = (),
        validation_version: str,
    ) -> StoredArtifact[T]:
        """Publish only after caller domain/provenance validation has succeeded.

        This method revalidates the typed value and source relationships. It cannot
        establish semantic evidence support; that remains the validation stage's job.
        """
        value = _checked(type(value), value)
        with self._transaction(write=True) as connection:
            run, _, _ = self._run(connection, run_id)
            if run.status != RunStatus.RUNNING or run.phase != phase:
                raise StorageConflict("Only the active run phase can publish a validated artifact")
            self._check_spans(connection, value, run)
            if not {source.extraction_id for source in _source_spans(value)}.issubset(
                extraction_ids
            ):
                raise StorageReferenceError(
                    "Cited extraction revisions must participate in the key"
                )
            key = self._artifact_key(
                connection,
                run,
                phase,
                type(value),
                extraction_ids,
                upstream_artifact_ids,
                validation_version,
            )
            key_digest = self._write_object(canonical_bytes(key))
            payload_digest = self._write_object(canonical_bytes(value))
            artifact_id = f"artifact-{uuid4().hex}"
            connection.execute(
                "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'completed', 1)",
                (
                    artifact_id,
                    run_id,
                    phase.value,
                    key_digest,
                    payload_digest,
                    key["output_schema"],
                    validation_version,
                    datetime.now(UTC).isoformat(),
                ),
            )
            return self._artifact(self._artifact_row(connection, artifact_id), type(value))

    def get_artifact[T: BaseModel](
        self, artifact_id: str, output_type: type[T]
    ) -> StoredArtifact[T]:
        with self._transaction() as connection:
            return self._artifact(self._artifact_row(connection, artifact_id), output_type)

    def find_artifact[T: BaseModel](
        self,
        run_id: str,
        phase: RunPhase,
        output_type: type[T],
        *,
        extraction_ids: tuple[str, ...] = (),
        upstream_artifact_ids: tuple[str, ...] = (),
        validation_version: str,
    ) -> StoredArtifact[T] | None:
        with self._transaction() as connection:
            run, _, _ = self._run(connection, run_id)
            key = self._artifact_key(
                connection,
                run,
                phase,
                output_type,
                extraction_ids,
                upstream_artifact_ids,
                validation_version,
            )
            rows = connection.execute(
                """SELECT * FROM artifacts
                   WHERE fingerprint=? AND status='completed' AND validated=1 ORDER BY rowid""",
                (fingerprint(key),),
            ).fetchall()
            for row in rows:
                try:
                    return self._artifact(row, output_type)
                except StorageIntegrityError:
                    # Corrupt/missing files cannot masquerade as reusable completed work.
                    continue
            return None
