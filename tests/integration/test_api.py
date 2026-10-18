"""HTTP API over a real LocalStore and WorkflowEngine.

Every app here runs the real lifespan wiring (store, engine, readiness) with
ControlledInterpreter injected — scripted, source-valid stage output, not model
evidence. No test contacts a provider: the configured-app cases assert zero
outbound HTTP through a patched httpx sender.
"""

import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from support import (
    CHART_PDF,
    ENCRYPTED_PDF,
    POLICY_2026_PDF,
    POLICY_PDF,
    ControlledInterpreter,
    configuration,
)

from app.assessment.workflow import InterpretationFailure, WorkflowLimits
from app.documents import NativePdfConfig
from app.main import create_app
from app.schemas import (
    AssessmentExport,
    AssessmentOutcome,
    ErrorCode,
    OperationalError,
    RunPhase,
    RunStatus,
)


def _app(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    interpreter: ControlledInterpreter | None,
    limits: WorkflowLimits | None = None,
    parser_config: NativePdfConfig | None = None,
    data_dir: Path | None = None,
    provider_detail: str | None = None,
) -> FastAPI:
    """Build the app with a tmp store/UI and an unreachable env file."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AIRA_MODEL", raising=False)
    ui = tmp_path / "ui"
    ui.mkdir(exist_ok=True)
    (ui / "index.html").write_text("<h1>Aira test build</h1>")
    return create_app(
        frontend_dir=ui,
        data_dir=data_dir or tmp_path / "data",
        env_file=tmp_path / "missing.env",
        interpreter=interpreter,
        configuration=configuration(limits, parser_config) if interpreter is not None else None,
        limits=limits,
        parser_config=parser_config,
        provider_detail=provider_detail,
    )


def _upload(client: TestClient, path: Path, role: str) -> httpx.Response:
    return client.post(
        "/api/documents",
        files={"file": (path.name, path.read_bytes(), "application/pdf")},
        data={"role": role},
    )


def _submit(client: TestClient, **overrides: object) -> httpx.Response:
    body = {"policy_document_id": "policy", "chart_document_id": "chart", **overrides}
    return client.post("/api/assessments", json=body)


def _uploaded_pair(client: TestClient, policy: Path = POLICY_PDF) -> tuple[str, str]:
    policy_id = _upload(client, policy, "policy").json()["document"]["document_id"]
    chart_id = _upload(client, CHART_PDF, "chart").json()["document"]["document_id"]
    return policy_id, chart_id


def _run_until_stopped(
    client: TestClient, run_id: str, *, timeout: float = 15.0
) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    run: dict[str, object] = {}
    while time.monotonic() < deadline:
        run = client.get(f"/api/assessments/{run_id}").json()
        if run["status"] in ("completed", "needs_input", "failed", "interrupted"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} did not stop: {run.get('status')}")


def test_document_uploads_create_records_and_locations(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        for path, role in ((POLICY_PDF, "policy"), (CHART_PDF, "chart")):
            response = _upload(client, path, role)
            assert response.status_code == 201
            body = response.json()
            assert body["document"]["role"] == role
            assert body["document"]["filename"] == path.name
            assert body["document"]["page_count"] > 0
            assert body["extractions"] == []
            assert response.headers["location"] == (
                f"/api/documents/{body['document']['document_id']}"
            )
            assert response.headers["x-request-id"].startswith("req-")


def test_upload_rejects_inputs_at_the_boundary(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        not_pdf = client.post(
            "/api/documents",
            files={"file": ("note.txt", b"plain text, not a PDF", "text/plain")},
            data={"role": "chart"},
        )
        assert not_pdf.status_code == 415
        truncated = client.post(
            "/api/documents",
            files={"file": ("cut.pdf", POLICY_PDF.read_bytes()[:200], "application/pdf")},
            data={"role": "policy"},
        )
        assert truncated.status_code == 422
        encrypted = _upload(client, ENCRYPTED_PDF, "chart")
        assert encrypted.status_code == 422
        bad_role = client.post(
            "/api/documents",
            files={"file": ("doc.pdf", POLICY_PDF.read_bytes(), "application/pdf")},
            data={"role": "receipt"},
        )
        assert bad_role.status_code == 422
        missing = client.post("/api/documents", data={"role": "policy"})
        assert missing.status_code == 422
        codes = {
            response.json()["error"]["code"]
            for response in (not_pdf, truncated, encrypted, bad_role, missing)
        }
        assert codes <= {
            ErrorCode.UNSUPPORTED_INPUT.value,
            ErrorCode.EXTRACTION_FAILED.value,
            ErrorCode.INVALID_REQUEST.value,
        }


def test_upload_size_limit_names_the_limit(tmp_path, monkeypatch):
    app = _app(
        tmp_path,
        monkeypatch,
        interpreter=ControlledInterpreter(),
        parser_config=NativePdfConfig(max_bytes=1024),
    )
    with TestClient(app) as client:
        response = _upload(client, POLICY_PDF, "policy")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == ErrorCode.UNSUPPORTED_INPUT.value
    assert "1024" in response.json()["error"]["message"]


def test_document_reads_after_a_run(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        submitted = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id)
        assert submitted.status_code == 202
        run = _run_until_stopped(client, submitted.json()["run_id"])
        assert run["status"] == RunStatus.COMPLETED.value

        document = client.get(f"/api/documents/{chart_id}").json()
        extractions = document["extractions"]
        assert len(extractions) == 1
        extraction_id = extractions[0]["extraction_id"]

        original = client.get(f"/api/documents/{chart_id}/file")
        assert original.status_code == 200
        assert original.content == CHART_PDF.read_bytes()
        assert original.headers["content-type"] == "application/pdf"
        assert (
            'filename="robert_mitchell_chart_final.pdf"'
            in (original.headers["content-disposition"])
        )

        page = client.get(
            f"/api/documents/{chart_id}/pages/3", params={"extraction_id": extraction_id}
        )
        assert page.status_code == 200
        page_body = page.json()
        assert page_body["document_id"] == chart_id
        assert page_body["extraction_id"] == extraction_id
        assert page_body["page"]["page"] == 3
        assert len(page_body["page"]["blocks"]) > 0

        assert (
            client.get(
                f"/api/documents/{chart_id}/pages/999",
                params={"extraction_id": extraction_id},
            ).status_code
            == 404
        )
        assert client.get(f"/api/documents/{chart_id}/pages/1").status_code == 422
        assert (
            client.get(
                f"/api/documents/{chart_id}/pages/1",
                params={"extraction_id": "ext-missing"},
            ).status_code
            == 404
        )
        policy_extraction_id = client.get(f"/api/documents/{policy_id}").json()["extractions"][0][
            "extraction_id"
        ]
        assert (
            client.get(
                f"/api/documents/{chart_id}/pages/1",
                params={"extraction_id": policy_extraction_id},
            ).status_code
            == 404
        )


def test_assessment_completes_and_exports_both_formats(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        accepted = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id)
        assert accepted.status_code == 202
        accepted_body = accepted.json()
        assert accepted_body["status"] == "queued"
        assert accepted_body["status_url"] == f"/api/assessments/{accepted_body['run_id']}"
        assert accepted.headers["location"] == accepted_body["status_url"]
        run_id = accepted_body["run_id"]
        run = _run_until_stopped(client, run_id)
        assert run["status"] == RunStatus.COMPLETED.value
        assert run["result"]["outcome"] == AssessmentOutcome.APPLICABILITY_MISMATCH.value

        exported = client.get(f"/api/assessments/{run_id}/export")
        assert exported.status_code == 200
        assert (
            f'attachment; filename="aira-{run_id}.json"'
            in (exported.headers["content-disposition"])
        )
        export = AssessmentExport.model_validate_json(exported.content)
        assert export.run.run_id == run_id
        assert export.run.model_dump(mode="json") == run

        markdown = client.get(f"/api/assessments/{run_id}/export", params={"format": "markdown"})
        assert markdown.status_code == 200
        assert markdown.headers["content-type"] == "text/markdown; charset=utf-8"
        assert (
            f'attachment; filename="aira-{run_id}.md"' in (markdown.headers["content-disposition"])
        )
        assert run_id in markdown.text

        bad_format = client.get(f"/api/assessments/{run_id}/export", params={"format": "xml"})
        assert bad_format.status_code == 422
        assert bad_format.json()["error"]["code"] == ErrorCode.INVALID_REQUEST.value


def test_running_run_conflicts_on_export(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter(sleep=30))
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        run_id = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id).json()[
            "run_id"
        ]
        deadline = time.monotonic() + 10
        while client.get(f"/api/assessments/{run_id}").json()["status"] != "running":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        conflict = client.get(f"/api/assessments/{run_id}/export")
        assert conflict.status_code == 409
        body = conflict.json()
        assert body["error"]["code"] == ErrorCode.STATE_CONFLICT.value
        assert "running" in body["error"]["message"]
        assert body["run_id"] == run_id


def test_failed_run_is_readable_but_not_exportable(tmp_path, monkeypatch):
    failure = InterpretationFailure(
        OperationalError(
            code=ErrorCode.INVALID_OUTPUT,
            message="The model returned an invalid structured response.",
            retryable=False,
            action="Review the diagnostics.",
            stage=RunPhase.CHECKING_APPLICABILITY,
        )
    )
    interpreter = ControlledInterpreter(
        failure=failure, failing_stage=RunPhase.CHECKING_APPLICABILITY
    )
    app = _app(tmp_path, monkeypatch, interpreter=interpreter)
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        run_id = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id).json()[
            "run_id"
        ]
        run = _run_until_stopped(client, run_id)
        assert run["status"] == RunStatus.FAILED.value
        assert run["error"]["code"] == ErrorCode.INVALID_OUTPUT.value
        conflict = client.get(f"/api/assessments/{run_id}/export")
        assert conflict.status_code == 409
        assert conflict.json()["error"]["code"] == ErrorCode.STATE_CONFLICT.value


def test_submission_validation_failures(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        swapped = _submit(client, policy_document_id=chart_id, chart_document_id=policy_id)
        assert swapped.status_code == 422
        assert swapped.json()["error"]["code"] == ErrorCode.INVALID_REQUEST.value
        unknown_document = _submit(
            client, policy_document_id="doc-missing", chart_document_id=chart_id
        )
        assert unknown_document.status_code == 404
        assert unknown_document.json()["error"]["code"] == ErrorCode.NOT_FOUND.value
        unknown_parent = _submit(
            client,
            policy_document_id=policy_id,
            chart_document_id=chart_id,
            parent_run_id="run-missing",
        )
        assert unknown_parent.status_code == 404
        assert unknown_parent.json()["error"]["code"] == ErrorCode.NOT_FOUND.value
        malformed = client.post("/api/assessments", json={"unexpected": True})
        assert malformed.status_code == 422
        assert malformed.json()["error"]["code"] == ErrorCode.INVALID_REQUEST.value
        not_json = client.post(
            "/api/assessments",
            content=b'{"policy_document_id": ',
            headers={"Content-Type": "application/json"},
        )
        assert not_json.status_code == 400
        assert not_json.json()["error"]["code"] == ErrorCode.INVALID_REQUEST.value


def test_internal_failures_become_a_safe_500(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        document_id = _upload(client, POLICY_PDF, "policy").json()["document"]["document_id"]

        def boom(_document_id):
            raise RuntimeError("simulated internal failure text")

        monkeypatch.setattr(app.state.store, "list_extractions", boom)
        response = client.get(f"/api/documents/{document_id}")
        assert response.status_code == 500
        body = response.json()
        assert body["error"]["code"] == ErrorCode.INTERNAL_ERROR.value
        assert body["error"]["retryable"] is False
        assert "simulated internal failure text" not in response.text
        assert response.headers["x-request-id"].startswith("req-")


def test_queue_saturation_returns_429(tmp_path, monkeypatch):
    app = _app(
        tmp_path,
        monkeypatch,
        interpreter=ControlledInterpreter(sleep=30),
        limits=WorkflowLimits(max_pending=1),
    )
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        first = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id).json()[
            "run_id"
        ]
        deadline = time.monotonic() + 10
        while client.get(f"/api/assessments/{first}").json()["status"] != "running":
            assert time.monotonic() < deadline
            time.sleep(0.05)
        second = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id)
        assert second.status_code == 202
        third = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id)
        assert third.status_code == 429
        body = third.json()
        assert body["error"]["code"] == ErrorCode.QUEUE_FULL.value
        assert body["error"]["retryable"] is True


def test_readiness_carries_the_fixture_provider_detail(tmp_path, monkeypatch):
    app = _app(
        tmp_path,
        monkeypatch,
        interpreter=ControlledInterpreter(),
        provider_detail="Fixture interpreter for browser tests; no live model calls.",
    )
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        provider = ready.json()["provider"]
        assert provider["status"] == "unverified"
        assert provider["detail"] == ("Fixture interpreter for browser tests; no live model calls.")


def test_missing_configuration_reports_prerequisites(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=None)
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        body = ready.json()
        assert body["ready"] is False
        assert body["provider"]["status"] == "unverified"
        assert any("OPENAI_API_KEY" in item for item in body["missing_prerequisites"])
        assert client.get("/health/live").status_code == 200
        rejected = _submit(client)
        assert rejected.status_code == 503
        error = rejected.json()["error"]
        assert error["code"] == ErrorCode.CONFIGURATION_MISSING.value
        assert "OPENAI_API_KEY" in error["message"]
        assert "Aira test build" in client.get("/").text


def test_configured_app_reports_ready_without_any_provider_call(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=None)
    # Fake credentials enter only after _app guarantees a clean environment.
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key-do-not-use")
    monkeypatch.setenv("AIRA_MODEL", "test-model")
    sent: list[object] = []

    def fail_send(self, request, **kwargs):
        sent.append(request)
        raise AssertionError("the app must not contact the provider")

    monkeypatch.setattr(httpx.AsyncClient, "send", fail_send)
    responses: list[httpx.Response] = []
    with TestClient(app) as client:
        for _ in range(3):
            ready = client.get("/health/ready")
            responses.append(ready)
            assert ready.status_code == 200
            body = ready.json()
            assert body["ready"] is True
            assert body["provider"]["status"] == "unverified"
        responses.append(client.get("/health/live"))
        responses.append(_upload(client, POLICY_PDF, "policy"))
        responses.append(_submit(client))
    assert sent == []
    for response in responses:
        assert "test-fake-key-do-not-use" not in response.text
        assert "test-fake-key-do-not-use" not in str(response.headers)


def test_restart_interrupts_an_active_run(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    app = _app(
        tmp_path,
        monkeypatch,
        interpreter=ControlledInterpreter(sleep=30),
        data_dir=data_dir,
    )
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        run_id = _submit(client, policy_document_id=policy_id, chart_document_id=chart_id).json()[
            "run_id"
        ]
        deadline = time.monotonic() + 15
        while (
            client.get(f"/api/assessments/{run_id}").json()["phase"]
            != RunPhase.CHECKING_APPLICABILITY.value
        ):
            assert time.monotonic() < deadline
            time.sleep(0.05)
    reopened = _app(
        tmp_path,
        monkeypatch,
        interpreter=ControlledInterpreter(),
        data_dir=data_dir,
    )
    with TestClient(reopened) as client:
        run = client.get(f"/api/assessments/{run_id}").json()
        assert run["status"] == RunStatus.INTERRUPTED.value
        assert run["error"]["code"] == ErrorCode.INTERRUPTED.value
        assert run["phase"] == RunPhase.CHECKING_APPLICABILITY.value


def test_exports_survive_later_runs_and_versions(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        first_run = _run_until_stopped(
            client,
            _submit(client, policy_document_id=policy_id, chart_document_id=chart_id).json()[
                "run_id"
            ],
        )
        first_export = client.get(f"/api/assessments/{first_run['run_id']}/export").json()
        updated_policy = _upload(client, POLICY_2026_PDF, "policy").json()["document"][
            "document_id"
        ]
        second_run = _run_until_stopped(
            client,
            _submit(
                client,
                policy_document_id=updated_policy,
                chart_document_id=chart_id,
            ).json()["run_id"],
        )
        assert second_run["status"] == RunStatus.COMPLETED.value
        repeated = client.get(f"/api/assessments/{first_run['run_id']}/export").json()
        assert {**first_export, "exported_at": None} == {**repeated, "exported_at": None}
        second_export = client.get(f"/api/assessments/{second_run['run_id']}/export").json()
        assert second_export["run"]["policy_sha256"] != first_export["run"]["policy_sha256"]
        assert (
            second_export["run"]["policy_document_id"] != first_export["run"]["policy_document_id"]
        )


def test_child_run_export_keeps_parent_link_and_annotation(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    with TestClient(app) as client:
        policy_id, chart_id = _uploaded_pair(client)
        parent_id = _run_until_stopped(
            client,
            _submit(client, policy_document_id=policy_id, chart_document_id=chart_id).json()[
                "run_id"
            ],
        )["run_id"]
        parent_export = client.get(f"/api/assessments/{parent_id}/export").json()
        child = _submit(
            client,
            policy_document_id=policy_id,
            chart_document_id=chart_id,
            parent_run_id=parent_id,
            annotations=[
                {
                    "kind": "text",
                    "annotation_id": "staff-plan",
                    "field": "plan",
                    "value": "Staff-confirmed plan",
                    "created_at": "2026-10-18T12:00:00Z",
                }
            ],
        )
        assert child.status_code == 202
        child_run = _run_until_stopped(client, child.json()["run_id"])
        assert child_run["status"] == RunStatus.COMPLETED.value
        child_export = client.get(f"/api/assessments/{child_run['run_id']}/export").json()
        assert child_export["run"]["parent_run_id"] == parent_id
        assert child_export["run"]["annotations"][0]["annotation_id"] == "staff-plan"
        assert child_export["run"]["annotations"][0]["field"] == "plan"
        parent_again = client.get(f"/api/assessments/{parent_id}/export").json()
        assert {**parent_export, "exported_at": None} == {
            **parent_again,
            "exported_at": None,
        }


def test_openapi_documents_typed_bodies_status_codes_and_resolvable_refs(
    tmp_path, monkeypatch
) -> None:
    app = _app(tmp_path, monkeypatch, interpreter=ControlledInterpreter())
    client = TestClient(app)
    spec = client.get("/openapi.json").json()
    components = spec["components"]["schemas"]
    for name in (
        "CreateAssessmentRequest",
        "ErrorResponse",
        "RunRecord",
        "AssessmentExport",
        "ReadinessResponse",
    ):
        assert name in components

    def resolve(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "$ref" and isinstance(item, str):
                    if item.startswith("#/components/schemas/"):
                        assert item.rsplit("/", 1)[-1] in components
                else:
                    resolve(item)
        elif isinstance(value, list):
            for item in value:
                resolve(item)

    resolve(spec)

    paths = spec["paths"]
    upload = paths["/api/documents"]["post"]
    upload_body = upload["requestBody"]["content"]["multipart/form-data"]["schema"]
    assert upload_body["properties"]["file"] == {"type": "string", "format": "binary"}
    assert upload_body["properties"]["role"] == {"type": "string", "enum": ["policy", "chart"]}
    assert {"201", "413", "415", "422", "503"} <= set(upload["responses"])

    submit = paths["/api/assessments"]["post"]
    body = submit["requestBody"]["content"]["application/json"]["schema"]
    assert body == {"$ref": "#/components/schemas/CreateAssessmentRequest"}
    assert {"202", "400", "404", "422", "429", "503"} <= set(submit["responses"])

    run = paths["/api/assessments/{run_id}"]["get"]
    assert {"200", "404", "503"} <= set(run["responses"])
    assert (
        run["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/RunRecord"
    )
    export = paths["/api/assessments/{run_id}/export"]["get"]
    assert {"200", "404", "409", "422", "503"} <= set(export["responses"])
    assert "text/markdown" in export["responses"]["200"]["content"]
    file_route = paths["/api/documents/{document_id}/file"]["get"]
    assert "application/pdf" in file_route["responses"]["200"]["content"]
    pages = paths["/api/documents/{document_id}/pages/{page}"]["get"]
    assert {"200", "404", "422", "503"} <= set(pages["responses"])
    ready = paths["/health/ready"]["get"]
    assert set(ready["responses"]) == {"200", "503"}


def test_readiness_reports_the_last_verification_for_the_configured_model(
    tmp_path, monkeypatch
) -> None:
    data_dir = tmp_path / "data"
    app = _app(tmp_path, monkeypatch, interpreter=None, data_dir=data_dir)
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key-do-not-use")
    monkeypatch.setenv("AIRA_MODEL", "test-model")
    data_dir.mkdir(parents=True)
    (data_dir / "provider-verification.json").write_text(
        json.dumps(
            {
                "status": "verified",
                "provider": "openai",
                "checked_at": "2026-10-18T12:00:00+00:00",
                "model_id": "test-model",
                "detail": "served-model-name",
            }
        )
    )
    sent: list[object] = []
    monkeypatch.setattr(
        httpx.AsyncClient,
        "send",
        lambda self, request, **kwargs: sent.append(request),
    )
    with TestClient(app) as client:
        body = client.get("/health/ready").json()
    assert body["provider"]["status"] == "verified"
    assert body["provider"]["model_id"] == "test-model"
    assert body["provider"]["detail"] == "served-model-name"
    assert "test-fake-key-do-not-use" not in json.dumps(body)
    assert sent == []


def test_readiness_marks_a_verification_for_another_model_unverified(tmp_path, monkeypatch) -> None:
    data_dir = tmp_path / "data"
    app = _app(tmp_path, monkeypatch, interpreter=None, data_dir=data_dir)
    monkeypatch.setenv("OPENAI_API_KEY", "test-fake-key-do-not-use")
    monkeypatch.setenv("AIRA_MODEL", "current-model")
    data_dir.mkdir(parents=True)
    (data_dir / "provider-verification.json").write_text(
        json.dumps(
            {
                "status": "verified",
                "provider": "openai",
                "checked_at": "2026-10-18T12:00:00+00:00",
                "model_id": "older-model",
            }
        )
    )
    with TestClient(app) as client:
        body = client.get("/health/ready").json()
    assert body["provider"]["status"] == "unverified"
    assert body["provider"]["detail"] == (
        "Last verification was for a different model (older-model)."
    )
