"""Contract invariants, independent of HTTP, providers, and clinical evaluation."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from app.schemas import (
    SCHEMA_VERSION,
    AssessmentAccepted,
    AssessmentExport,
    CandidateFinding,
    ConfigurationProvenance,
    CreateAssessmentRequest,
    DocumentResponse,
    Finding,
    Policy,
    PolicyCandidate,
    ReadinessResponse,
    RunRecord,
    RunStatus,
    SourceSpan,
    TextAnnotation,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "contracts"


def fixture(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads((FIXTURES / name).read_text()))


def completed() -> dict[str, Any]:
    return fixture("completed_run.json")


def parse_run(data: dict[str, Any]) -> RunRecord:
    return RunRecord.model_validate_json(json.dumps(data))


def operational_run(status: str) -> dict[str, Any]:
    data = completed()
    data.pop("result")
    data["status"] = status
    data["phase"] = "mapping_evidence"
    data["error"] = {
        "code": "interrupted" if status == "interrupted" else "timeout",
        "message": "The synthetic attempt stopped.",
        "retryable": True,
        "action": "Start a new linked attempt.",
        "stage": "mapping_evidence",
    }
    return data


@pytest.mark.parametrize("name", ["completed_run.json", "needs_input_run.json"])
def test_run_json_roundtrip_keeps_versions_and_immutable_collections(name: str) -> None:
    run = RunRecord.model_validate_json((FIXTURES / name).read_text())
    assert run.schema_version == SCHEMA_VERSION == "0.1.0"
    assert RunRecord.model_validate_json(run.model_dump_json()) == run
    assert isinstance(run.annotations, tuple)
    with pytest.raises(ValidationError, match="frozen"):
        run.status = RunStatus.FAILED


@pytest.mark.parametrize("status", ["queued", "running", "failed", "interrupted"])
def test_operational_states_do_not_require_or_invent_a_clinical_outcome(status: str) -> None:
    if status in {"failed", "interrupted"}:
        data = operational_run(status)
    else:
        data = completed()
        data.pop("result")
        data["status"] = status
        data["phase"] = None if status == "queued" else "extracting"
    run = parse_run(data)
    assert run.status.value == status
    assert run.result is None


def test_completed_mismatch_contains_no_necessity_assessment() -> None:
    data = completed()
    applicability = data["result"]["applicability"]
    applicability["status"] = "mismatch"
    data["result"] = {"outcome": "applicability_mismatch", "applicability": applicability}
    result = parse_run(data).result
    assert result is not None
    assert result.policy is None
    assert result.findings == ()
    assert result.logical_value is None


@pytest.mark.parametrize("status", ["missing", "conflicting", "needs_review", "not_met"])
def test_distinct_evidence_states_survive_completed_review(status: str) -> None:
    data = completed()
    result = data["result"]
    finding = result["findings"][0]
    finding["status"] = status
    result["outcome"] = "review_required"
    result["logical_value"] = "unknown" if status != "not_met" else "false"
    if status == "not_met":
        finding["evidence"][0]["relation"] = "contradicting"
    else:
        finding["unresolved_reasons"] = ["A synthetic unresolved reason."]
        if status == "missing":
            finding["evidence"] = []
        elif status == "conflicting":
            opposite = deepcopy(result["facts"][0])
            opposite["fact_id"] = "fact-2"
            opposite["polarity"] = "negated"
            result["facts"].append(opposite)
            finding["evidence"].append({"fact_id": "fact-2", "relation": "contradicting"})
    parsed = parse_run(data).result
    assert parsed is not None
    assert parsed.findings[0].status.value == status


@pytest.mark.parametrize(
    ("field", "value"),
    [("schema_version", "99.0.0"), ("run_id", "../other/run"), ("unknown_field", True)],
)
def test_unknown_versions_fields_and_path_like_identifiers_fail(field: str, value: Any) -> None:
    data = completed()
    data[field] = value
    with pytest.raises(ValidationError):
        parse_run(data)


@pytest.mark.parametrize("value", ["1", True, 1.5, 0])
def test_source_pages_require_strict_one_based_integers(value: Any) -> None:
    data = completed()["result"]["facts"][0]["sources"][0]
    data["page"] = value
    with pytest.raises(ValidationError):
        SourceSpan.model_validate_json(json.dumps(data))


@pytest.mark.parametrize(
    "corruption",
    ["failed_with_result", "running_without_phase", "completed_without_result", "error_on_success"],
)
def test_lifecycle_contradictions_are_rejected(corruption: str) -> None:
    data = completed()
    if corruption == "failed_with_result":
        data["status"] = "failed"
        data["error"] = operational_run("failed")["error"]
    elif corruption == "running_without_phase":
        data.pop("result")
        data["status"] = "running"
        data["phase"] = None
    elif corruption == "completed_without_result":
        data.pop("result")
    else:
        data["error"] = operational_run("failed")["error"]
    with pytest.raises(ValidationError):
        parse_run(data)


def test_missing_clarification_fields_cannot_be_needs_input() -> None:
    data = fixture("needs_input_run.json")
    data["applicability"]["unresolved_fields"] = []
    with pytest.raises(ValidationError, match="fields needing input"):
        parse_run(data)


def test_provider_candidate_is_not_a_validated_finding() -> None:
    text = (FIXTURES / "invalid_finding.json").read_text()
    assert CandidateFinding.model_validate_json(text).status == "met"
    with pytest.raises(ValidationError, match="supporting evidence"):
        Finding.model_validate_json(text)


@pytest.mark.parametrize(
    "corruption", ["unknown_fact", "wrong_chart", "wrong_scope", "duplicate_finding"]
)
def test_result_reference_integrity(corruption: str) -> None:
    data = completed()
    result = data["result"]
    if corruption == "unknown_fact":
        result["findings"][0]["evidence"][0]["fact_id"] = "absent-fact"
    elif corruption == "wrong_chart":
        result["facts"][0]["sources"][0]["document_id"] = "another-chart"
    elif corruption == "wrong_scope":
        result["applicability"]["sources"][0]["document_id"] = "another-policy"
    else:
        result["findings"].append(deepcopy(result["findings"][0]))
    with pytest.raises(ValidationError):
        parse_run(data)


@pytest.mark.parametrize("blocker", ["policy_issue", "result_issue", "unclassified_section"])
def test_true_root_cannot_bypass_known_governing_blockers(blocker: str) -> None:
    data = completed()
    issue = {
        "issue_id": "unresolved-1",
        "category": "completeness",
        "message": "A governing condition remains unresolved.",
        "action": "Inspect the governing section.",
        "blocks_readiness": True,
    }
    if blocker == "unclassified_section":
        data["result"]["policy"]["sections"][0]["disposition"] = "unresolved"
    elif blocker == "policy_issue":
        data["result"]["policy"]["issues"] = [issue]
    else:
        data["result"]["issues"] = [issue]
    with pytest.raises(ValidationError, match="prohibit"):
        parse_run(data)


@pytest.mark.parametrize(
    "corruption", ["cycle", "unknown_child", "orphan", "duplicate", "unknown_criterion"]
)
def test_policy_graph_rejects_malformed_references(corruption: str) -> None:
    data = completed()["result"]["policy"]
    leaf = data["nodes"][0]
    if corruption == "cycle":
        data["nodes"] = [
            {
                "kind": "all",
                "node_id": "root",
                "children": ["root", "leaf"],
                "sources": leaf["sources"],
            },
            {**leaf, "node_id": "leaf"},
        ]
    elif corruption == "unknown_child":
        data["nodes"] = [
            {
                "kind": "all",
                "node_id": "root",
                "children": ["missing-node"],
                "sources": leaf["sources"],
            }
        ]
    elif corruption == "orphan":
        data["nodes"].append({**leaf, "node_id": "orphan"})
    elif corruption == "duplicate":
        data["nodes"].append(deepcopy(leaf))
    else:
        leaf["criterion_id"] = "missing-criterion"
    with pytest.raises(ValidationError):
        Policy.model_validate_json(json.dumps(data))


def test_valid_nested_flat_graph_is_representable_without_evaluation() -> None:
    data = completed()["result"]["policy"]
    leaf = data["nodes"][0]
    data["nodes"] = [
        {"kind": "all", "node_id": "root", "children": ["alternative"], "sources": leaf["sources"]},
        {"kind": "any", "node_id": "alternative", "children": ["leaf"], "sources": leaf["sources"]},
        {**leaf, "node_id": "leaf"},
    ]
    policy = Policy.model_validate_json(json.dumps(data))
    assert tuple(node.kind for node in policy.nodes) == ("all", "any", "criterion")


def test_document_response_requires_complete_original_page_accounting() -> None:
    data = fixture("document_response.json")
    assert DocumentResponse.model_validate_json(json.dumps(data)).document.page_count == 1
    data["document"]["page_count"] = 2
    with pytest.raises(ValidationError, match="every page"):
        DocumentResponse.model_validate_json(json.dumps(data))


def test_conflicting_metadata_annotation_requires_reason_and_keeps_sources() -> None:
    data = {
        "annotation_id": "annotation-1",
        "kind": "text",
        "field": "plan",
        "value": "Clarified synthetic plan",
        "created_at": "2026-10-18T11:00:00Z",
        "resolves_conflict": True,
        "original_sources": completed()["result"]["facts"][0]["sources"],
    }
    with pytest.raises(ValidationError, match="explicit reason"):
        TextAnnotation.model_validate_json(json.dumps(data))
    data["resolution_reason"] = "Staff selected the current plan while preserving the old source."
    annotation = TextAnnotation.model_validate_json(json.dumps(data))
    assert annotation.original_sources
    data["field"] = "clinical_finding_status"
    with pytest.raises(ValidationError):
        TextAnnotation.model_validate_json(json.dumps(data))


def test_openai_is_regionless_and_future_bedrock_requires_region() -> None:
    data = completed()["configuration"]
    assert ConfigurationProvenance.model_validate_json(json.dumps(data)).region is None
    data["provider"] = "bedrock"
    with pytest.raises(ValidationError, match="requires a region"):
        ConfigurationProvenance.model_validate_json(json.dumps(data))
    data["region"] = "us-east-1"
    assert ConfigurationProvenance.model_validate_json(json.dumps(data)).region == "us-east-1"
    data["provider"] = "openai"
    with pytest.raises(ValidationError, match="does not use an AWS region"):
        ConfigurationProvenance.model_validate_json(json.dumps(data))


def test_api_contracts_reject_wrong_roles_and_wrong_status_link() -> None:
    with pytest.raises(ValidationError, match="distinct"):
        CreateAssessmentRequest(policy_document_id="same", chart_document_id="same")
    with pytest.raises(ValidationError, match="status URL"):
        AssessmentAccepted(run_id="run-1", status="queued", status_url="/api/assessments/run-2")


def test_readiness_is_not_remote_verification() -> None:
    readiness = ReadinessResponse(ready=True)
    assert readiness.provider.status.value == "unverified"
    with pytest.raises(ValidationError, match="missing local prerequisites"):
        ReadinessResponse(ready=False)


def test_timezone_is_required_for_run_timestamps() -> None:
    data = completed()
    data["created_at"] = "2026-10-18T10:00:00"
    with pytest.raises(ValidationError, match="timezone"):
        parse_run(data)


def test_export_requires_exportable_run_and_matching_input_identity() -> None:
    policy = fixture("document_response.json")["document"]
    chart = {**policy, "document_id": "chart-1", "role": "chart", "sha256": "b" * 64}
    data = {"exported_at": "2026-10-18T11:00:00Z", "run": completed(), "documents": [policy, chart]}
    assert AssessmentExport.model_validate_json(json.dumps(data)).run.run_id == "run-1"
    data["run"] = operational_run("failed")
    with pytest.raises(ValidationError, match="checklist exports"):
        AssessmentExport.model_validate_json(json.dumps(data))
    data["run"] = completed()
    chart["sha256"] = "e" * 64
    with pytest.raises(ValidationError, match="document identities"):
        AssessmentExport.model_validate_json(json.dumps(data))


def test_domain_and_candidate_json_schemas_are_separate() -> None:
    domain = Policy.model_json_schema()
    candidate = PolicyCandidate.model_json_schema()
    assert "root_id" in domain["properties"]
    assert "root_id" in candidate["properties"]
    assert "SourceSpan" in domain["$defs"]
    assert "CandidateCitation" in candidate["$defs"]
    assert "SourceSpan" not in candidate["$defs"]
