import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.assessment.export import render_markdown
from app.schemas import AssessmentExport, DocumentRecord, RunRecord

FIXTURES = Path(__file__).parents[1] / "fixtures/contracts"


def export(name):
    run = RunRecord.model_validate_json((FIXTURES / name).read_text())
    response = (FIXTURES / "document_response.json").read_text()
    base = json.loads(response)["document"]
    documents = []
    for role, document_id, digest in (
        ("policy", run.policy_document_id, run.policy_sha256),
        ("chart", run.chart_document_id, run.chart_sha256),
    ):
        data = {**base, "document_id": document_id, "sha256": digest, "role": role}
        documents.append(DocumentRecord.model_validate_json(json.dumps(data)))
    return AssessmentExport(exported_at=datetime.now(UTC), run=run, documents=tuple(documents))


def test_completed_export_keeps_saved_outcome_evidence_versions_and_logic():
    item = export("completed_run.json")
    before = item.model_dump_json()
    markdown = render_markdown(item)
    assert item.run.result.outcome.value in markdown
    assert item.run.result.findings[0].rationale in markdown
    assert item.run.policy_sha256 in markdown and item.run.chart_sha256 in markdown
    assert item.run.result.policy.root_id in markdown
    assert item.run.configuration.model_id in markdown
    assert "extraction" in markdown and "offsets" in markdown
    assert item.model_dump_json() == before


def test_needs_input_export_explains_scope_without_fabricated_findings():
    item = export("needs_input_run.json")
    markdown = render_markdown(item)
    assert "needs_input" in markdown and "Clarification needed" in markdown
    assert (
        "Assessment stopped for staff input; "
        "no medical-necessity evaluation was performed." in markdown
    )
    assert "Requirements and evidence" not in markdown
    assert "Saved outcome" not in markdown


def test_mismatch_export_states_that_no_necessity_evaluation_happened():
    item = export("completed_run.json")
    data = item.model_dump(mode="json")
    data["run"]["result"]["outcome"] = "applicability_mismatch"
    data["run"]["result"]["applicability"]["status"] = "mismatch"
    data["run"]["result"]["policy"] = None
    data["run"]["result"]["findings"] = []
    data["run"]["result"]["logical_value"] = None
    item = AssessmentExport.model_validate_json(json.dumps(data))
    markdown = render_markdown(item)
    assert (
        "The uploaded policy does not apply to this request; "
        "no medical-necessity evaluation was performed." in markdown
    )


def test_source_prose_cannot_become_export_markup():
    item = export("completed_run.json")
    data = item.model_dump(mode="json")
    data["run"]["result"]["findings"][0]["rationale"] = "<script>oops</script> [bad](https://bad)"
    item = AssessmentExport.model_validate_json(json.dumps(data))
    markdown = render_markdown(item)
    assert "<script>" not in markdown and "[bad](" not in markdown


def test_failed_run_cannot_be_exported_as_a_checklist():
    item = export("needs_input_run.json")
    data = item.model_dump(mode="json")
    data["run"]["status"] = "failed"
    data["run"]["error"] = {
        "code": "timeout",
        "message": "Stopped",
        "retryable": True,
        "action": "Try again",
    }
    with pytest.raises(ValidationError, match="only completed or needs_input"):
        AssessmentExport.model_validate_json(json.dumps(data))


def test_markdown_reports_satisfied_path_and_unused_alternatives():
    item = export("completed_run.json")
    data = item.model_dump(mode="json")
    result = data["run"]["result"]
    criterion = result["policy"]["criteria"][0]
    sources = result["policy"]["nodes"][0]["sources"]
    result["policy"]["criteria"].append(
        {**criterion, "criterion_id": "criterion-2", "wording": "An alternative requirement."}
    )
    result["policy"]["nodes"] = [
        {
            "kind": "any",
            "node_id": "root",
            "children": ["node-a", "node-b"],
            "sources": sources,
        },
        {
            "kind": "criterion",
            "node_id": "node-a",
            "criterion_id": "criterion-1",
            "sources": sources,
        },
        {
            "kind": "criterion",
            "node_id": "node-b",
            "criterion_id": "criterion-2",
            "sources": sources,
        },
    ]
    result["policy"]["sections"][0]["criterion_ids"] = ["criterion-1", "criterion-2"]
    result["findings"].append(
        {
            "criterion_id": "criterion-2",
            "status": "missing",
            "rationale": "No alternative was documented.",
            "evidence": [],
            "unresolved_reasons": ["No alternative was documented."],
        }
    )
    result["evaluation"] = {
        "root_id": "root",
        "logical_value": "true",
        "outcome": "documented_requirements_satisfied",
        "traces": [
            {
                "node_id": "root",
                "kind": "any",
                "logical_value": "true",
                "children": ["node-a", "node-b"],
                "supporting_children": ["node-a"],
            },
            {
                "node_id": "node-a",
                "kind": "criterion",
                "logical_value": "true",
                "criterion_id": "criterion-1",
            },
            {
                "node_id": "node-b",
                "kind": "criterion",
                "logical_value": "unknown",
                "criterion_id": "criterion-2",
            },
        ],
        "satisfied_path": ["root", "node-a"],
        "blockers": [],
    }
    rerun = AssessmentExport.model_validate_json(json.dumps(data))
    markdown = render_markdown(rerun)
    assert "Policy path: supports the satisfied path." in markdown
    assert (
        "Policy path: alternative not needed (another alternative satisfies its group)." in markdown
    )
    assert "`root`: any → node-a, node-b (evaluated: true)" in markdown
    assert "(evaluated: unknown)" in markdown


def test_markdown_keeps_existing_rendering_without_an_evaluation():
    item = export("completed_run.json")
    markdown = render_markdown(item)
    assert "Policy path:" not in markdown
    assert "(evaluated:" not in markdown
