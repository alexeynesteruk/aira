"""Check independent annotation integrity, without running or importing an evaluator.

These tests establish source/annotation consistency only. They deliberately do not
compute expected rule outcomes or claim that a parser or model passes the corpus.
"""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = {f"A{number:02d}" for number in range(1, 21)}
FICTIONAL_LABEL = "FICTIONAL SOFTWARE TEST FIXTURE"
PAGE_MARKER = re.compile(r"<!-- page:(\d+) -->")
type Record = dict[str, object]


def record(value: object) -> Record:
    assert isinstance(value, dict), "Expected a JSON object"
    assert all(isinstance(key, str) for key in value)
    return cast(Record, value)


def items(value: object) -> list[object]:
    assert isinstance(value, list), "Expected a JSON array"
    return cast(list[object], value)


def string(value: object) -> str:
    assert isinstance(value, str) and value, "Expected nonempty text"
    return value


def strings(value: object) -> list[str]:
    return [string(item) for item in items(value)]


def read_json(path: str) -> Record:
    data = record(json.loads((ROOT / path).read_text(encoding="utf-8")))
    assert data["schema_version"] == "0.1.0"
    return data


def indexed(value: object, key: str) -> dict[str, Record]:
    rows = [record(item) for item in items(value)]
    result = {string(row[key]): row for row in rows}
    assert len(result) == len(rows), f"Duplicate {key}"
    return result


def records(value: object) -> dict[str, Record]:
    return {key: record(item) for key, item in record(value).items()}


@dataclass(frozen=True)
class Corpus:
    sources: dict[str, Record]
    policies: dict[str, Record]
    development: dict[str, Record]
    reserved: dict[str, Record]
    expected: dict[str, Record]
    reserved_expected: dict[str, Record]
    tasks: dict[str, Record]
    coverage: dict[str, Record]


@pytest.fixture
def corpus() -> Corpus:
    reserved = read_json("evals/expected/reserved.json")
    policies = records(read_json("evals/expected/policies.json")["policies"])
    policies.update(records(reserved["policies"]))
    return Corpus(
        sources=records(read_json("evals/source-registry.json")["sources"]),
        policies=policies,
        development=indexed(read_json("evals/cases/development.json")["cases"], "case_id"),
        reserved=indexed(read_json("evals/cases/held-out.json")["cases"], "case_id"),
        expected=records(read_json("evals/expected/development.json")["cases"]),
        reserved_expected=records(reserved["cases"]),
        tasks=indexed(read_json("evals/construction-tasks.json")["tasks"], "task_id"),
        coverage=indexed(read_json("evals/coverage.json")["scenarios"], "scenario_id"),
    )


def source_path(source: Record) -> Path:
    path = (ROOT / string(source["path"])).resolve()
    assert path.is_relative_to(ROOT), "Source path escapes repository"
    assert path.is_file(), f"Source does not exist: {path}"
    return path


def logical_pages(source: Record) -> dict[int, str]:
    text = source_path(source).read_text(encoding="utf-8")
    markers = list(PAGE_MARKER.finditer(text))
    assert markers, "Markdown source has no logical page markers"
    numbers = [int(marker.group(1)) for marker in markers]
    assert numbers == list(range(1, len(markers) + 1)), "Invalid logical page sequence"
    return {
        number: text[marker.end() : markers[index + 1].start()]
        if index + 1 < len(markers)
        else text[marker.end() :]
        for index, (number, marker) in enumerate(zip(numbers, markers, strict=True))
    }


def validate_sources(sources: dict[str, Record]) -> None:
    for source_id, source in sources.items():
        assert source["source_id"] == source_id
        assert source["role"] in {"policy", "chart"}
        assert source["split"] in {"development", "reserved"}
        path = source_path(source)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"], (
            f"Source hash mismatch: {source_id}"
        )
        if source["format"] == "markdown":
            assert source["origin"] == "authored_fictional"
            assert FICTIONAL_LABEL in path.read_text(encoding="utf-8")
            assert list(logical_pages(source)) == source["logical_pages"]
            assert source["pdf_rendering_verified"] is False
        else:
            assert source["format"] == "pdf"
            assert isinstance(source["page_count"], int) and source["page_count"] > 0
            assert (ROOT / string(source["review_reference"])).is_file()


def validate_selector(value: object, sources: dict[str, Record], allowed_sources: set[str]) -> None:
    selector = record(value)
    source_id = string(selector["source_id"])
    assert source_id in allowed_sources, "Evidence points to a different document"
    source = sources[source_id]
    page = selector["page"]
    assert isinstance(page, int) and not isinstance(page, bool) and page >= 1
    excerpt = string(selector["excerpt"])
    if source["format"] == "markdown":
        pages = logical_pages(source)
        assert page in pages, "Unknown logical page"
        assert excerpt in pages[page], "Excerpt is absent from the stated page"
    else:
        count = source["page_count"]
        assert isinstance(count, int) and page <= count, "PDF page is outside inspected bounds"
        # PDF excerpts require pdf-tools/source review; a byte hash cannot verify their text.


def validate_policy(policy: Record, sources: dict[str, Record]) -> None:
    source_id = string(policy["source_id"])
    assert sources[source_id]["role"] == "policy"
    criteria = indexed(policy["criteria"], "criterion_id")
    assert criteria
    for criterion in criteria.values():
        string(criterion["wording"])
        assert items(criterion["sources"]), "Criterion lacks a source"
        for selector in items(criterion["sources"]):
            validate_selector(selector, sources, {source_id})
    assert items(policy["connective_sources"]), "Connectives lack source annotations"
    for key in ("connective_sources", "governing_context"):
        for selector in items(policy[key]):
            validate_selector(selector, sources, {source_id})
    string(policy["scope_summary"])
    sections = indexed(policy["sections"], "section_id")
    assert sections, "Policy lacks a section inventory"
    linked_requirements: set[str] = set()
    for section in sections.values():
        string(section["heading"])
        string(section["explanation"])
        assert section["disposition"] in {"requirements", "context", "out_of_scope", "unresolved"}
        criterion_ids = set(strings(section["criterion_ids"]))
        assert criterion_ids <= set(criteria), "Section references an unknown criterion"
        if section["disposition"] == "requirements":
            assert criterion_ids, "Requirements section omits its criterion links"
            linked_requirements.update(criterion_ids)
        assert items(section["sources"]), "Section lacks source evidence"
        for selector in items(section["sources"]):
            validate_selector(selector, sources, {source_id})
    assert linked_requirements == set(criteria), "Section inventory omits a requirement"
    nodes = indexed(policy["nodes"], "node_id")
    visited: set[str] = set()
    active: set[str] = set()
    leaves: list[str] = []

    def visit(node_id: str) -> None:
        assert node_id in nodes, "Dangling rule edge"
        assert node_id not in active, "Rule graph contains a cycle"
        if node_id in visited:
            return
        active.add(node_id)
        node = nodes[node_id]
        if node["kind"] == "criterion":
            criterion_id = string(node["criterion_id"])
            assert criterion_id in criteria, "Leaf references an unknown criterion"
            leaves.append(criterion_id)
        else:
            assert node["kind"] in {"all", "any"}
            children = strings(node["children"])
            assert children and len(children) == len(set(children)), "Invalid child list"
            for child in children:
                visit(child)
        active.remove(node_id)
        visited.add(node_id)

    visit(string(policy["root_id"]))
    assert visited == set(nodes), "Unreachable rule node"
    assert set(leaves) == set(criteria), "Annotated criterion omitted from rule graph"
    assert len(leaves) == len(set(leaves)), "Duplicate criterion leaves"


def validate_case(case: Record, expected: Record, corpus: Corpus, split: str) -> None:
    policy_source = string(case["policy_source_id"])
    chart_source = string(case["chart_source_id"])
    allowed_sources = {policy_source, chart_source}
    for source_id, role in ((policy_source, "policy"), (chart_source, "chart")):
        assert corpus.sources[source_id]["role"] == role
        assert corpus.sources[source_id]["split"] == split
    assert set(strings(case["scenario_ids"])) <= SCENARIOS
    string(case["exercise"])
    request = record(case["request"])
    for key in ("procedure", "payer"):
        string(request[key])
    applicability = record(expected["applicability"])
    string(applicability["rationale"])
    assert items(applicability["sources"]), "Applicability lacks source evidence"
    for selector in items(applicability["sources"]):
        validate_selector(selector, corpus.sources, allowed_sources)
    for issue in items(expected["issues"]):
        issue_record = record(issue)
        string(issue_record["code"])
        for selector in items(issue_record["sources"]):
            validate_selector(selector, corpus.sources, allowed_sources)
    if applicability["status"] != "applicable":
        assert applicability["status"] in {"mismatch", "unresolved"}
        assert expected["findings"] == [], "Scope stop contains clinical findings"
        assert expected["logical_value"] is None, "Scope stop contains a clinical aggregate"
        if applicability["status"] == "mismatch":
            assert expected["outcome"] == "applicability_mismatch"
        else:
            assert expected["outcome"] is None
            assert expected["workflow_status"] == "needs_input"
            assert strings(applicability["unresolved_fields"])
        return
    for key in ("service_date", "assessment_cutoff"):
        string(request[key])
    policy_id = string(case["policy_expectation_id"])
    policy = corpus.policies[policy_id]
    assert policy["source_id"] == policy_source
    criteria = indexed(policy["criteria"], "criterion_id")
    findings = indexed(expected["findings"], "criterion_id")
    assert set(findings) == set(criteria), "Expected finding set omits policy criteria"
    assert expected["logical_value"] in {"true", "false", "unknown"}
    assert expected["outcome"] in {
        "documented_requirements_satisfied",
        "documentation_gaps_or_contrary_evidence",
        "review_required",
    }
    for finding in findings.values():
        string(finding["rationale"])
        status = string(finding["status"])
        assert status in {"met", "not_met", "missing", "conflicting", "needs_review"}
        evidence = [record(item) for item in items(finding["evidence"])]
        relations: list[str] = []
        for reference in evidence:
            validate_selector(reference["source"], corpus.sources, {chart_source})
            relation = string(reference["relation"])
            assert relation in {"supporting", "contradicting", "context"}
            relations.append(relation)
        reasons = strings(finding["unresolved_reasons"])
        if status == "met":
            assert "supporting" in relations, "Met finding lacks supporting evidence"
        elif status == "not_met":
            assert "contradicting" in relations, "Not-met finding lacks contrary evidence"
        elif status == "missing":
            assert evidence == [], "Missing evidence must not fabricate a citation"
            assert reasons, "Missing evidence lacks a reason"
        elif status == "conflicting":
            assert {"supporting", "contradicting"} <= set(relations)
            assert len(evidence) >= 2 and reasons
        else:
            assert reasons, "Needs-review finding lacks an unresolved reason"


def finding(expected: Record, criterion_id: str) -> Record:
    return indexed(expected["findings"], "criterion_id")[criterion_id]


def test_source_bytes_roles_labels_and_pages_are_pinned(corpus: Corpus) -> None:
    validate_sources(corpus.sources)


def test_annotations_reference_their_actual_sources(corpus: Corpus) -> None:
    for policy in corpus.policies.values():
        validate_policy(policy, corpus.sources)
    for cases, expectations, split in (
        (corpus.development, corpus.expected, "development"),
        (corpus.reserved, corpus.reserved_expected, "reserved"),
    ):
        assert {case["expected_id"] for case in cases.values()} == set(expectations)
        for case in cases.values():
            validate_case(case, expectations[string(case["expected_id"])], corpus, split)


@pytest.mark.parametrize("mutation", ["hash", "escape"])
def test_source_validator_rejects_changed_or_external_bytes(corpus: Corpus, mutation: str) -> None:
    sources = deepcopy(corpus.sources)
    if mutation == "hash":
        sources["venous_chart_matched"]["sha256"] = "0" * 64
        message = "Source hash mismatch"
    else:
        sources["venous_chart_matched"]["path"] = "../not-a-corpus-source.md"
        message = "Source path escapes repository"
    with pytest.raises(AssertionError, match=message):
        validate_sources(sources)


@pytest.mark.parametrize("mutation", ["wrong_page", "invented_quote", "wrong_document"])
def test_selector_validator_rejects_plausible_bad_citations(corpus: Corpus, mutation: str) -> None:
    selector: Record = {
        "source_id": "venous_chart_matched",
        "page": 1,
        "excerpt": "The right great saphenous vein diameter is 3.4 mm.",
    }
    if mutation == "wrong_page":
        selector["page"] = 2
    elif mutation == "invented_quote":
        selector["excerpt"] = "The right great saphenous vein diameter is 9.9 mm."
    else:
        # A real quote in another chart still cannot support this selected document.
        selector["source_id"] = "venous_chart_embedded_instruction"
    with pytest.raises(AssertionError):
        validate_selector(selector, corpus.sources, {"venous_chart_matched"})


@pytest.mark.parametrize(
    "mutation", ["cycle", "omitted_criterion", "disconnected", "unmapped_section"]
)
def test_policy_annotation_validator_rejects_incomplete_graphs(
    corpus: Corpus, mutation: str
) -> None:
    policy = deepcopy(corpus.policies["venous_policy_v1"])
    nodes = items(policy["nodes"])
    root = record(nodes[0])
    if mutation == "cycle":
        root["children"] = ["root"]
    elif mutation == "omitted_criterion":
        root["children"] = ["reflux_node", "indication"]
        policy["nodes"] = [node for node in nodes if record(node)["node_id"] != "diameter_node"]
    elif mutation == "disconnected":
        nodes.append({"node_id": "unused", "kind": "criterion", "criterion_id": "reflux"})
    else:
        for item in items(policy["sections"]):
            section = record(item)
            if section["disposition"] == "requirements":
                section["criterion_ids"] = ["reflux"]
    with pytest.raises(AssertionError):
        validate_policy(policy, corpus.sources)


@pytest.mark.parametrize("mutation", ["missing_finding", "unsupported_met", "scope_leak"])
def test_case_validator_rejects_incomplete_or_unsubstantiated_annotations(
    corpus: Corpus, mutation: str
) -> None:
    case_id = "venous_matched" if mutation != "scope_leak" else "venous_unknown_plan"
    expected = deepcopy(corpus.expected[case_id])
    if mutation == "missing_finding":
        expected["findings"] = items(expected["findings"])[1:]
    elif mutation == "unsupported_met":
        finding(expected, "reflux")["evidence"] = []
    else:
        expected["findings"] = [deepcopy(finding(corpus.expected["venous_matched"], "reflux"))]
    with pytest.raises(AssertionError):
        validate_case(corpus.development[case_id], expected, corpus, "development")


def test_missing_negative_and_conflicting_annotations_remain_distinct(corpus: Corpus) -> None:
    missing = finding(corpus.expected["venous_missing_diameter"], "diameter")
    negative = finding(corpus.expected["venous_negative_reflux"], "reflux")
    conflict = finding(corpus.expected["venous_conflicting_diameter"], "diameter")
    assert missing["status"] == "missing" and missing["evidence"] == []
    assert negative["status"] == "not_met"
    assert conflict["status"] == "conflicting"
    assert corpus.expected["venous_missing_diameter"]["logical_value"] == "unknown"
    assert corpus.expected["venous_negative_reflux"]["logical_value"] == "false"
    assert corpus.expected["venous_conflicting_diameter"]["outcome"] == "review_required"
    excerpts = {
        string(record(record(item)["source"])["excerpt"]) for item in items(conflict["evidence"])
    }
    assert any("3.4 mm" in excerpt for excerpt in excerpts)
    assert any("2.7 mm" in excerpt for excerpt in excerpts)


def test_or_branch_fixture_preserves_unused_unknowns_and_connective_sources(corpus: Corpus) -> None:
    policy = corpus.policies["venous_policy_v1"]
    nodes = indexed(policy["nodes"], "node_id")
    assert nodes["indication"] == {
        "node_id": "indication",
        "kind": "any",
        "children": ["ulcer_node", "symptom_branch"],
    }
    assert nodes["symptom_branch"]["kind"] == "all"
    assert set(strings(nodes["symptom_branch"]["children"])) == {
        "pain_node",
        "daily_tasks_node",
        "compression_node",
    }
    expected = corpus.expected["venous_ulcer_alternative"]
    assert expected["logical_value"] == "true"
    assert finding(expected, "ulcer")["status"] == "met"
    for criterion_id in ("pain", "daily_tasks", "compression"):
        assert finding(expected, criterion_id)["status"] == "missing"
    assert "symptom_branch" not in strings(expected["satisfied_path"])
    combined = corpus.expected["venous_false_and_unknown"]
    assert finding(combined, "reflux")["status"] == "not_met"
    assert finding(combined, "diameter")["status"] == "missing"
    assert combined["logical_value"] == "false"


def test_controlled_rule_change_reuses_chart_and_changes_only_declared_policy_text(
    corpus: Corpus,
) -> None:
    baseline = corpus.development["venous_matched"]
    changed = corpus.development["venous_rule_changed"]
    assert baseline["chart_source_id"] == changed["chart_source_id"]
    assert baseline["request"] == changed["request"]
    before = source_path(corpus.sources["venous_policy_v1"]).read_text(encoding="utf-8")
    after = source_path(corpus.sources["venous_policy_v2"]).read_text(encoding="utf-8")
    assert (
        before.replace("V1", "V2")
        .replace("Revision date: 2026-10-01", "Revision date: 2026-10-02")
        .replace("at least 3.0 mm", "at least 4.0 mm")
        == after
    )
    assert finding(corpus.expected["venous_matched"], "diameter")["status"] == "met"
    assert finding(corpus.expected["venous_rule_changed"], "diameter")["status"] == "not_met"
    assert corpus.expected["venous_rule_changed"]["logical_value"] == "false"


@pytest.mark.parametrize(
    ("suffix", "measurement", "expected_status"),
    [("below", "2.9", "not_met"), ("at", "3.0", "met"), ("above", "3.1", "met")],
)
def test_threshold_contrasts_have_the_declared_measurement(
    corpus: Corpus, suffix: str, measurement: str, expected_status: str
) -> None:
    source = corpus.sources[f"venous_chart_threshold_{suffix}"]
    assert f"diameter is {measurement} mm." in logical_pages(source)[1]
    expected = corpus.expected[f"venous_threshold_{suffix}"]
    assert finding(expected, "diameter")["status"] == expected_status
    boundary = record(record(corpus.policies["venous_policy_v1"]["numeric_boundaries"])["diameter"])
    assert boundary == {"operator": "gte", "value": "3.0", "unit": "mm"}


def test_instruction_and_absence_requirement_do_not_flip_evidence_meaning(corpus: Corpus) -> None:
    baseline = corpus.expected["venous_matched"]
    injected = corpus.expected["venous_embedded_instruction"]
    for criterion_id, expected in indexed(baseline["findings"], "criterion_id").items():
        assert finding(injected, criterion_id)["status"] == expected["status"]
    assert finding(injected, "ulcer")["status"] == "not_met"
    issues = [record(issue) for issue in items(injected["issues"])]
    assert any(issue["code"] == "untrusted_instruction_ignored" for issue in issues)
    absence = finding(corpus.expected["monitor_matched"], "no_previous_capture")
    assert absence["status"] == "met"
    reference = record(items(absence["evidence"])[0])
    assert reference["relation"] == "supporting"
    assert string(record(reference["source"])["excerpt"]).startswith("No previous")
    venous_ids = set(indexed(corpus.policies["venous_policy_v1"]["criteria"], "criterion_id"))
    monitor_ids = set(indexed(corpus.policies["monitor_policy"]["criteria"], "criterion_id"))
    assert venous_ids.isdisjoint(monitor_ids)


def test_reserved_inputs_and_expectations_are_separate_and_unexecuted(corpus: Corpus) -> None:
    assert set(corpus.development).isdisjoint(corpus.reserved)
    used_sources: dict[str, set[str]] = {}
    for split, cases in (("development", corpus.development), ("reserved", corpus.reserved)):
        used_sources[split] = {
            string(case[key])
            for case in cases.values()
            for key in ("policy_source_id", "chart_source_id")
        }
    assert used_sources["development"].isdisjoint(used_sources["reserved"])
    for name in ("development", "held-out"):
        manifest = read_json(f"evals/cases/{name}.json")
        assert manifest["execution_status"] == "not_run"
    for name in ("development", "policies", "reserved"):
        annotation = read_json(f"evals/expected/{name}.json")
        provenance = record(annotation["annotation_provenance"])
        assert provenance["method"] == (
            "explicit_source_annotation_not_application_or_model_run_output"
        )
        assert provenance["independent_review"] == "source_consistency_complete"
        assert string(provenance["reviewer"]) != string(provenance["author"])
        assert date.fromisoformat(string(provenance["reviewed_on"])) >= date.fromisoformat(
            string(provenance["authored_on"])
        )
        review_path = (ROOT / string(provenance["review_reference"])).resolve()
        assert review_path.is_relative_to(ROOT) and review_path.is_file()
        assert provenance["live_model_evaluation"] == "not_performed"
        assert provenance["clinical_validation"] == "not_performed"


def test_every_scenario_links_actual_inputs_or_actionable_remaining_work(corpus: Corpus) -> None:
    assert set(corpus.coverage) == SCENARIOS
    for scenario_id, coverage in corpus.coverage.items():
        assert coverage["execution_status"] == "not_run"
        linked_tasks = set(strings(coverage["construction_task_ids"]))
        assert linked_tasks == {
            task_id
            for task_id, task in corpus.tasks.items()
            if scenario_id in strings(task["scenario_ids"])
        }
        for field, cases in (
            ("development_case_ids", corpus.development),
            ("reserved_case_ids", corpus.reserved),
        ):
            assert set(strings(coverage[field])) == {
                case_id
                for case_id, case in cases.items()
                if scenario_id in strings(case["scenario_ids"])
            }
        source_ids = strings(coverage["additional_source_ids"])
        assert set(source_ids) <= set(corpus.sources)
        has_input = any(
            items(coverage[key])
            for key in ("development_case_ids", "reserved_case_ids", "additional_source_ids")
        )
        assert has_input or linked_tasks, f"{scenario_id} has no input or construction task"
        expected_kind = "annotated_inputs_and_open_work" if has_input else "construction_task_only"
        assert coverage["coverage_kind"] == expected_kind
    for task in corpus.tasks.values():
        assert task["status"] in {"open", "done"}
        assert set(strings(task["scenario_ids"])) <= SCENARIOS
        assert strings(task["owner_packages"])
        assert string(task["artifact_required"]) != string(task["acceptance"])
        if task["status"] == "done":
            evidence = strings(task.get("evidence", []))
            assert evidence, f"{task['task_id']} is done without evidence paths"
            assert "progress_evidence" not in task
        else:
            assert "evidence" not in task
            evidence = strings(task.get("progress_evidence", []))
        for item in evidence:
            path = Path(item)
            assert not path.is_absolute() and ".." not in path.parts
            assert (ROOT / item).exists(), f"{task['task_id']} evidence missing: {item}"
