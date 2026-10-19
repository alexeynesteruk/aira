"""Pure structural planning and compilation of immutable section interpretations."""

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from app.assessment.stages import DocumentInputs
from app.documents import source_span
from app.evidence import CitationError, CitationResolver
from app.policies.conversion import convert_policy
from app.schemas import (
    AllNode,
    AnyNode,
    CandidateCitation,
    CandidatePolicyNode,
    CriterionNode,
    DocumentRecord,
    ExtractionRecord,
    IssueCategory,
    Policy,
    ReviewIssue,
    SourceSpan,
    StageUsage,
)
from app.schemas.builds import (
    AuditCandidate,
    CoverageEntry,
    DependencyResolution,
    PathCandidate,
    ReconciliationCandidate,
    ReconciliationGroup,
    SectionCandidate,
    SectionPlan,
    SectionResult,
    SourceUnit,
)
from app.schemas.policies import PolicyPath
from app.storage.identity import canonical_bytes


@dataclass(frozen=True)
class ModelStep[T]:
    value: T
    usage: StageUsage | None = None


@runtime_checkable
class GuidelineInterpreter(Protocol):
    async def section(
        self, inputs: DocumentInputs, plan: SectionPlan
    ) -> ModelStep[SectionCandidate]: ...
    async def reconcile(
        self, inputs: DocumentInputs, sections: tuple[SectionResult, ...]
    ) -> ModelStep[ReconciliationCandidate]: ...
    async def merge(
        self,
        inputs: DocumentInputs,
        groups: tuple[ReconciliationGroup, ...],
        sections: tuple[SectionResult, ...],
    ) -> ModelStep[ReconciliationCandidate]: ...
    async def audit(
        self,
        inputs: DocumentInputs,
        section: SectionResult,
        reconciliation: ReconciliationCandidate,
    ) -> ModelStep[AuditCandidate]: ...


COMPILER_VERSION = "structural-compiler-v2"


@dataclass(frozen=True)
class BuildLimits:
    # UTF-8 bytes upper-bound token count. Conservative, independent of model vocabulary.
    primary_tokens: int = 7000
    input_tokens: int = 60_000
    output_tokens: int = 4096
    total_tokens: int = 100_000_000
    max_calls: int = 3000
    max_sections: int = 600
    call_timeout_seconds: float = 180
    build_timeout_seconds: float = 3600
    max_pending: int = 4

    def __post_init__(self) -> None:
        for name in (
            "primary_tokens",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "max_calls",
            "max_sections",
            "max_pending",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be positive")
        if any(
            not math.isfinite(value) or value <= 0
            for value in (self.call_timeout_seconds, self.build_timeout_seconds)
        ):
            raise ValueError("build deadlines must be positive")


def token_upper_bound(text: str) -> int:
    """One token per UTF-8 byte is a conservative budget, not measured usage."""
    return len(text.encode("utf-8"))


def plan_sections(extraction: ExtractionRecord, limits: BuildLimits) -> tuple[SectionPlan, ...]:
    units: list[SourceUnit] = []
    heading = ""
    for page in extraction.pages:
        for block in sorted(page.blocks, key=lambda block: block.reading_order):
            text = block.text.strip()
            if len(text) < 140 and (text.isupper() or re.match(r"^\d+(?:\.\d+)*[.) ]", text)):
                heading = text
            units.append(
                SourceUnit(
                    unit_id=f"p{page.page}:{block.block_id}",
                    source=source_span(extraction, page=page.page, block_id=block.block_id),
                    heading=heading,
                    table_id=block.table_id,
                )
            )
    if not units:
        raise ValueError("No usable source blocks to prepare")
    groups: list[list[SourceUnit]] = []
    current: list[SourceUnit] = []
    size = 0
    # Blocks remain atomic: no list/table row is truncated to meet a budget.
    for unit in units:
        count = token_upper_bound(canonical_bytes(unit).decode())
        if count > limits.primary_tokens:
            raise ValueError("An atomic source block exceeds the section budget; no text was cut")
        if current and size + count > limits.primary_tokens:
            groups.append(current)
            current, size = [], 0
        current.append(unit)
        size += count
    if current:
        groups.append(current)
    if len(groups) > limits.max_sections:
        raise ValueError("Document exceeds the configured section count")
    plans = []
    for index, group in enumerate(groups):
        context = []
        if index:
            context.append(groups[index - 1][-1])
        if index + 1 < len(groups):
            context.append(groups[index + 1][0])
        # Keep table headers and the nearest parent heading as original source units.
        for unit in group:
            preceding = units[: units.index(unit)]
            parent = next(
                (
                    other
                    for other in reversed(preceding)
                    if other.source.excerpt.strip() == unit.heading
                ),
                None,
            )
            for other in [parent] if parent else []:
                if (
                    unit.table_id
                    and other.table_id == unit.table_id
                    and other.source.page == unit.source.page
                ) or (unit.heading and other.source.excerpt.strip() == unit.heading):
                    if other not in group and other not in context:
                        context.append(other)
        for unit in group:
            if unit.table_id:
                header = next(
                    (
                        other
                        for other in units
                        if other.table_id == unit.table_id and other.source.page == unit.source.page
                    ),
                    None,
                )
                if header and header not in group and header not in context:
                    context.append(header)
        plans.append(
            SectionPlan(
                section_id=f"section-{index + 1:04}", primary=tuple(group), context=tuple(context)
            )
        )
    return tuple(plans)


def unit_packet(unit: SourceUnit) -> dict[str, object]:
    return {
        "unit_id": unit.unit_id,
        "page": unit.source.page,
        "text": unit.source.excerpt,
        "heading": unit.heading,
        "table_id": unit.table_id,
    }


def section_packet(document: DocumentRecord, plan: SectionPlan) -> dict[str, object]:
    return {
        "document_id": document.document_id,
        "section_id": plan.section_id,
        "primary": [unit_packet(unit) for unit in plan.primary],
        "context": [unit_packet(unit) for unit in plan.context],
    }


def _collect_citations(value: object) -> list[CandidateCitation]:
    if isinstance(value, CandidateCitation):
        return [value]
    if isinstance(value, BaseModel):
        found: list[CandidateCitation] = []
        for name in type(value).model_fields:
            found.extend(_collect_citations(getattr(value, name)))
        return found
    if isinstance(value, list | tuple):
        found = []
        for item in value:
            found.extend(_collect_citations(item))
        return found
    return []


def _quote_failure(resolver: CitationResolver, candidate: SectionCandidate) -> str | None:
    """Report every bad quote together so one repair can correct the section."""
    problems: list[str] = []
    seen: set[tuple[str, int, str, str]] = set()
    for citation in _collect_citations(candidate):
        identity = (citation.document_id, citation.page, citation.block_id or "", citation.quote)
        if identity in seen:
            continue
        seen.add(identity)
        try:
            resolver.resolve(citation)
        except CitationError as exc:
            problems.append(str(exc))
            if len(problems) == 8:
                break
    if not problems:
        return None
    return " ".join(problems)


def validate_section(
    document: DocumentRecord,
    extraction: ExtractionRecord,
    plan: SectionPlan,
    candidate: SectionCandidate,
) -> SectionResult:
    dispositions = {item.unit_id: item for item in candidate.dispositions}
    expected = {unit.unit_id for unit in plan.primary}
    if len(dispositions) != len(candidate.dispositions) or dispositions.keys() != expected:
        raise ValueError("Each primary source block requires exactly one disposition")
    if any(not item.explanation.strip() for item in dispositions.values()):
        raise ValueError("Every source disposition requires an explanation")
    resolver = CitationResolver((document,), (extraction,))
    quote_failure = _quote_failure(resolver, candidate)
    if quote_failure is not None:
        raise ValueError(quote_failure)
    allowed = (*plan.primary, *plan.context)

    def supplied(citation: CandidateCitation) -> None:
        span = resolver.resolve(citation)
        if not any(
            span.page == unit.source.page
            and span.block_id == unit.source.block_id
            and span.start >= unit.source.start
            and span.end <= unit.source.end
            for unit in allowed
        ):
            raise ValueError("Candidate cited evidence outside its supplied context")

    policy = None
    fragment = candidate.fragment
    if fragment is not None and not fragment.criteria:
        # A shell with no rules is not a failed extraction. The block stays visible.
        fragment = None
        candidate = candidate.model_copy(update={"fragment": None})
    if fragment is not None:
        policy = convert_policy(fragment, resolver, policy_id=plan.section_id)
        if not any(item.kind == "requirements" for item in candidate.dispositions):
            raise ValueError("Extracted rules require a requirements disposition")
        allowed = (*plan.primary, *plan.context)
        for span in policy._sources():
            if not any(
                span.page == unit.source.page
                and span.block_id == unit.source.block_id
                and span.start >= unit.source.start
                and span.end <= unit.source.end
                for unit in allowed
            ):
                raise ValueError("Section rules cited evidence outside their supplied context")
        prefix = plan.section_id + ":"
        data = policy.model_dump(mode="json")
        for criterion in data["criteria"]:
            criterion["criterion_id"] = prefix + criterion["criterion_id"]
        for node in data["nodes"]:
            node["node_id"] = prefix + node["node_id"]
            if node["kind"] == "criterion":
                node["criterion_id"] = prefix + node["criterion_id"]
            else:
                node["children"] = [prefix + child for child in node["children"]]
        for section in data["sections"]:
            section["section_id"] = prefix + section["section_id"]
            section["criterion_ids"] = [prefix + item for item in section["criterion_ids"]]
        for issue in data["issues"]:
            issue["issue_id"] = prefix + issue["issue_id"]
            issue["criterion_ids"] = [prefix + item for item in issue["criterion_ids"]]
        for path in data["paths"]:
            path["path_id"] = prefix + path["path_id"]
            path["root_id"] = prefix + path["root_id"]
        data["root_id"] = prefix + data["root_id"]
        policy = Policy.model_validate_json(json.dumps(data))
    elif any(item.kind == "requirements" for item in candidate.dispositions):
        candidate = candidate.model_copy(
            update={
                "issues": (
                    *candidate.issues,
                    "A requirements block did not produce a cited rule. "
                    "Review that block before using a favorable result.",
                )
            }
        )
    for definition in candidate.definitions:
        if not definition.citations:
            raise ValueError("Definitions require source evidence")
        for citation in definition.citations:
            supplied(citation)
    refs = [ref.reference_id for ref in candidate.dependencies]
    if len(refs) != len(set(refs)):
        raise ValueError("Dependency identifiers must be unique within a section")
    for reference in candidate.dependencies:
        if not reference.citations:
            raise ValueError("Cross-section dependencies require source evidence")
        for citation in reference.citations:
            supplied(citation)
    return SectionResult(section_id=plan.section_id, plan=plan, candidate=candidate, policy=policy)


def compact_policy(policy: Policy) -> dict[str, object]:
    """Immutable graph IDs/edges and source wording, without repeated span metadata."""

    def citations(spans: tuple[SourceSpan, ...]) -> list[dict[str, object]]:
        return [
            dict(document_id=span.document_id, page=span.page, quote=span.excerpt) for span in spans
        ]

    return {
        "title": policy.title,
        "scope_summary": policy.scope_summary,
        "identifier": policy.identifier,
        "root_id": policy.root_id,
        "paths": [
            dict(
                path_id=path.path_id,
                title=path.title,
                scope=path.scope,
                root_id=path.root_id,
                citations=citations(path.sources),
            )
            for path in policy.paths
        ],
        "criteria": [
            dict(criterion_id=item.criterion_id, wording=item.wording, context=item.context)
            for item in policy.criteria
        ],
        "nodes": [
            dict(
                node_id=node.node_id,
                kind=node.kind,
                **(
                    {"criterion_id": node.criterion_id}
                    if isinstance(node, CriterionNode)
                    else {"children": node.children}
                ),
            )
            for node in policy.nodes
        ],
        "citations": citations(
            next(node.sources for node in policy.nodes if node.node_id == policy.root_id)
        ),
        "issues": [item.message for item in policy.issues],
    }


def _audit_quotes(citations: tuple[CandidateCitation, ...]) -> list[dict[str, object]]:
    return [
        dict(
            document_id=item.document_id,
            page=item.page,
            quote=item.quote,
            **({"block_id": item.block_id} if item.block_id else {}),
        )
        for item in citations
    ]


def audit_packet(
    document: DocumentRecord,
    section: SectionResult,
    reconciliation: ReconciliationCandidate,
) -> dict[str, object]:
    """Source text once, plus wording and this section's resolutions.

    The stored section and the full reconciliation repeat every span. That duplicate
    metadata makes a faithful audit larger than the build budget before the model
    is called. Quotes, graph edges, and resolutions that name this section stay.
    """
    candidate = section.candidate
    prefix = section.section_id + ":"
    return {
        "source": section_packet(document, section.plan),
        "interpretation": {
            "section_id": section.section_id,
            "dispositions": [item.model_dump(mode="json") for item in candidate.dispositions],
            "policy": compact_policy(section.policy) if section.policy else None,
            "definitions": [
                {
                    "term": item.term,
                    "meaning": item.meaning,
                    "citations": _audit_quotes(item.citations),
                }
                for item in candidate.definitions
            ],
            "dependencies": [
                {
                    "reference_id": prefix + item.reference_id,
                    "target": item.target,
                    "kind": item.kind,
                    "citations": _audit_quotes(item.citations),
                }
                for item in candidate.dependencies
            ],
            "issues": list(candidate.issues),
        },
        "reconciliation": {
            "nodes": [
                {"node_id": node.node_id, "kind": node.kind, "children": list(node.children)}
                for node in reconciliation.nodes
            ],
            "paths": [
                {
                    "path_id": path.path_id,
                    "title": path.title,
                    "scope": path.scope,
                    "root_id": path.root_id,
                }
                for path in reconciliation.paths
            ],
            "resolutions": [
                {
                    "reference_id": item.reference_id,
                    "target_section_ids": list(item.target_section_ids),
                    "status": item.status,
                    "explanation": item.explanation,
                }
                for item in reconciliation.resolutions
                if item.reference_id.startswith(prefix)
                or section.section_id in item.target_section_ids
            ],
            "issues": list(reconciliation.issues),
        },
    }


def reconciliation_packet(sections: tuple[SectionResult, ...]) -> dict[str, object]:
    return {
        "sections": [
            {
                "section_id": section.section_id,
                "policy": compact_policy(section.policy) if section.policy else None,
                "definitions": [
                    item.model_dump(mode="json") for item in section.candidate.definitions
                ],
                "dependencies": [
                    dict(
                        item.model_dump(mode="json"),
                        reference_id=section.section_id + ":" + item.reference_id,
                    )
                    for item in section.candidate.dependencies
                ],
                "issues": section.candidate.issues,
            }
            for section in sections
        ]
    }


def require_resolutions(value: ReconciliationCandidate, expected: set[str]) -> None:
    """Each supplied dependency is resolved once. A merge slice may be a subset."""
    found = [item.reference_id for item in value.resolutions]
    if len(found) != len(set(found)) or set(found) != expected:
        raise ValueError("Every extracted dependency requires exactly one resolution")


def merge_slices(
    groups: tuple[ReconciliationGroup, ...],
    sections: tuple[SectionResult, ...],
    fits: Callable[[dict[str, object]], bool],
) -> tuple[tuple[tuple[ReconciliationGroup, ...], tuple[SectionResult, ...]], ...]:
    """Keep every reference. Repeat the group graph only on slices that still fit."""
    if fits(group_packet(groups, sections)):
        return ((groups, sections),)
    if groups and not fits(group_packet(groups, ())):
        raise ValueError("Reconciled groups exceed the bounded input budget")
    slices: list[tuple[tuple[ReconciliationGroup, ...], tuple[SectionResult, ...]]] = []
    pending = list(sections)
    include_groups = True
    while pending:
        chosen: list[SectionResult] = []
        rest: list[SectionResult] = []
        stopped = False
        slice_groups = groups if include_groups else ()
        for section in pending:
            if stopped:
                rest.append(section)
                continue
            trial = group_packet(slice_groups, tuple([*chosen, section]))
            if not fits(trial):
                if not chosen:
                    raise ValueError("Reconciliation references exceed the bounded input budget")
                stopped = True
                rest.append(section)
                continue
            chosen.append(section)
        slices.append((slice_groups, tuple(chosen)))
        pending = rest
        include_groups = False
    return tuple(slices)


def assemble_merged(
    groups: tuple[ReconciliationGroup, ...],
    parts: tuple[ReconciliationCandidate, ...],
) -> ReconciliationCandidate:
    """Union bounded merge calls. The first copy of a connective id is kept."""
    nodes = [node for group in groups for node in group.result.nodes]
    seen_nodes = {node.node_id for node in nodes}
    paths: list[PathCandidate] = []
    seen_paths: set[str] = set()
    resolutions: list[DependencyResolution] = []
    seen_refs: set[str] = set()
    issues = [issue for group in groups for issue in group.result.issues]
    for part in parts:
        for node in part.nodes:
            if node.node_id in seen_nodes:
                continue
            seen_nodes.add(node.node_id)
            nodes.append(node)
        for path in part.paths:
            if path.path_id in seen_paths:
                continue
            seen_paths.add(path.path_id)
            paths.append(path)
        for item in part.resolutions:
            if item.reference_id in seen_refs:
                raise ValueError("Every extracted dependency requires exactly one resolution")
            seen_refs.add(item.reference_id)
            resolutions.append(item)
        issues.extend(part.issues)
    return ReconciliationCandidate(
        nodes=tuple(nodes),
        paths=tuple(paths),
        resolutions=tuple(resolutions),
        issues=tuple(issues),
    )


def group_packet(
    groups: tuple[ReconciliationGroup, ...], sections: tuple[SectionResult, ...]
) -> dict[str, object]:
    references = []
    for section in sections:
        for reference in section.candidate.dependencies:
            matches = [
                dict(section_id=other.section_id, **unit_packet(unit))
                for other in sections
                for unit in other.plan.primary
                if reference.target.casefold() in unit.source.excerpt.casefold()
            ]
            references.append(
                dict(
                    reference.model_dump(mode="json"),
                    reference_id=section.section_id + ":" + reference.reference_id,
                    original_passages=matches,
                )
            )
    return {
        "groups": [
            dict(
                group_id=group.group_id,
                section_ids=group.section_ids,
                paths=[path.model_dump(mode="json") for path in group.result.paths],
                issues=group.result.issues,
            )
            for group in groups
        ],
        "references": references,
    }


def namespace_reconciliation(
    value: ReconciliationCandidate, prefix: str
) -> ReconciliationCandidate:
    ids = {node.node_id for node in value.nodes}
    data = value.model_dump(mode="json")
    for node in data["nodes"]:
        node["node_id"] = prefix + node["node_id"]
        node["children"] = [prefix + child if child in ids else child for child in node["children"]]
    for path in data["paths"]:
        path["path_id"] = prefix + path["path_id"]
        if path["root_id"] in ids:
            path["root_id"] = prefix + path["root_id"]
    return ReconciliationCandidate.model_validate_json(json.dumps(data))


def validate_audit(section: SectionResult, audit: AuditCandidate) -> None:
    expected = {unit.unit_id for unit in section.plan.primary}
    if set(audit.checked_unit_ids) != expected or len(audit.checked_unit_ids) != len(expected):
        raise ValueError("The audit did not account for every primary source block")


def _stated_criterion_id(value: str | None) -> str | None:
    """Blank and the literal string null are unset. The schema requires the field."""
    if value is None:
        return None
    text = value.strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    return text


def _same_saved_node(
    existing: AllNode | AnyNode | CriterionNode, candidate: CandidatePolicyNode
) -> bool:
    if existing.kind != candidate.kind:
        return False
    if isinstance(existing, CriterionNode):
        return existing.criterion_id == candidate.criterion_id
    return tuple(existing.children) == tuple(candidate.children)


def _reachable(
    roots: tuple[str, ...] | list[str],
    by_id: dict[str, AllNode | AnyNode | CriterionNode],
) -> set[str]:
    seen: set[str] = set()
    pending = list(roots)
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        node = by_id.get(current)
        if node is None:
            continue
        seen.add(current)
        if not isinstance(node, CriterionNode):
            pending.extend(node.children)
    return seen


def compile_policy(
    document: DocumentRecord,
    extraction: ExtractionRecord,
    sections: tuple[SectionResult, ...],
    reconciliation: ReconciliationCandidate,
    audits: tuple[AuditCandidate, ...],
    *,
    policy_id: str,
) -> tuple[Policy, tuple[CoverageEntry, ...]]:
    if len(sections) != len(audits):
        raise ValueError("Every section requires a completed audit")
    policies = [section.policy for section in sections if section.policy is not None]
    if not policies or not reconciliation.paths:
        raise ValueError("No sourced policy paths were extracted")
    resolver = CitationResolver((document,), (extraction,))
    nodes: list[AllNode | AnyNode | CriterionNode] = [
        node for policy in policies for node in policy.nodes
    ]
    local_by_id = {node.node_id: node for node in nodes}
    # Models often fill criterion_id on an AND/OR node because the schema requires
    # the field. The kind is the group. A criterion node is not a new local rule.
    notes: list[str] = []
    pending: dict[str, tuple[CandidatePolicyNode, tuple[str, ...]]] = {}
    for node in reconciliation.nodes:
        stated = _stated_criterion_id(node.criterion_id)
        if node.kind == "criterion" or not node.children:
            extra = f" criterion_id {stated!r} was not applied." if stated else ""
            notes.append(
                f"Reconciliation node {node.node_id} was not added. "
                "Reconciliation cannot introduce or rewrite local criteria." + extra
            )
            continue
        existing = local_by_id.get(node.node_id)
        if existing is not None:
            if _same_saved_node(existing, node):
                notes.append(f"Reconciliation repeated saved node {node.node_id} and was ignored.")
                continue
            raise ValueError("Reconciliation cannot introduce or rewrite local criteria")
        if node.node_id in pending:
            previous, previous_children = pending[node.node_id]
            if previous.kind != node.kind or previous_children != tuple(node.children):
                raise ValueError("Reconciliation cannot introduce or rewrite local criteria")
            notes.append(f"Reconciliation repeated node {node.node_id} and was ignored.")
            continue
        if stated:
            label = "AND" if node.kind == "all" else "OR"
            notes.append(
                f"Reconciliation node {node.node_id} is an {label} group but also set "
                f"criterion_id {stated!r}. That id was not applied."
            )
        pending[node.node_id] = (node, tuple(node.children))
    allowed = set(local_by_id) | set(pending)

    def prune_pending() -> None:
        while True:
            removed = False
            for node_id, (node, children) in list(pending.items()):
                surviving = tuple(child for child in children if child in allowed)
                for child in children:
                    if child not in allowed:
                        notes.append(
                            f"Reconciliation node {node.node_id} dropped child {child}. "
                            "That child is not a saved local node and was not added."
                        )
                if not surviving:
                    notes.append(
                        f"Reconciliation node {node.node_id} was not added because none of "
                        "its children are saved local nodes."
                    )
                    del pending[node_id]
                    allowed.discard(node_id)
                    removed = True
                    continue
                pending[node_id] = (node, surviving)
            if not removed:
                break

    prune_pending()
    sources_by_id: dict[str, tuple[SourceSpan, ...]] = {}
    while True:
        failed = False
        for node_id, (node, _children) in list(pending.items()):
            if node_id in sources_by_id:
                continue
            try:
                if not node.citations:
                    raise CitationError(
                        "empty_quote", "A reconciliation node requires a source citation"
                    )
                sources_by_id[node_id] = tuple(resolver.resolve(cite) for cite in node.citations)
            except CitationError as exc:
                notes.append(f"Reconciliation node {node.node_id} was not added. {exc}")
                del pending[node_id]
                allowed.discard(node_id)
                sources_by_id.pop(node_id, None)
                failed = True
        if not failed:
            break
        prune_pending()
    for node, children in pending.values():
        cls = AllNode if node.kind == "all" else AnyNode
        nodes.append(
            cls(
                node_id=node.node_id,
                children=children,
                sources=sources_by_id[node.node_id],
            )
        )
    added_ids = set(pending)
    available = {node.node_id for node in nodes}
    paths: list[PolicyPath] = []
    used_path_ids: set[str] = set()
    for path in reconciliation.paths:
        if path.root_id not in available:
            notes.append(
                f"Policy path {path.path_id} was not added because root {path.root_id} "
                "is not a saved local node."
            )
            continue
        try:
            if not path.citations:
                raise CitationError("empty_quote", "A policy path requires a source citation")
            sources = tuple(resolver.resolve(cite) for cite in path.citations)
        except CitationError as exc:
            notes.append(f"Policy path {path.path_id} was not added. {exc}")
            continue
        paths.append(
            PolicyPath(
                path_id=path.path_id,
                title=path.title,
                scope=path.scope,
                root_id=path.root_id,
                sources=sources,
            )
        )
        used_path_ids.add(path.path_id)
    by_id = {node.node_id: node for node in nodes}
    reachable = _reachable([path.root_id for path in paths], by_id)
    for section in sections:
        local = section.policy
        if local is None or local.root_id in reachable:
            continue
        # Reconciliation left this section's saved graph disconnected. Keep its own
        # sourced path. Do not invent a relationship with the other procedures.
        restored = [path for path in local.paths if path.root_id == local.root_id]
        if not restored:
            restored = list(local.paths)
        if local.root_id not in {path.root_id for path in restored}:
            root = by_id.get(local.root_id)
            if root is not None:
                restored.append(
                    PolicyPath(
                        path_id=section.section_id,
                        title=local.title,
                        scope=local.scope_summary,
                        root_id=local.root_id,
                        sources=root.sources,
                    )
                )
        kept_local = False
        for local_path in restored:
            path_id = local_path.path_id
            suffix = 2
            while path_id in used_path_ids:
                path_id = f"{section.section_id}-{suffix}"
                suffix += 1
            paths.append(local_path.model_copy(update={"path_id": path_id}))
            used_path_ids.add(path_id)
            kept_local = True
        if kept_local:
            notes.append(
                f"Section {section.section_id} was not connected to a reconciled path. "
                "Its local path was kept and was not combined with other procedures."
            )
            reachable |= _reachable([local.root_id], by_id)
    if not paths:
        raise ValueError("No sourced policy paths were extracted")
    orphans = added_ids - reachable
    if orphans:
        for node_id in sorted(orphans):
            notes.append(
                f"Reconciliation node {node_id} was not connected to a policy path "
                "and was not added."
            )
        nodes = [item for item in nodes if item.node_id not in orphans]
    for _ in range(len(nodes) + 1):
        by_id = {item.node_id: item for item in nodes}
        sealed: list[AllNode | AnyNode | CriterionNode] = []
        for current in nodes:
            if isinstance(current, CriterionNode):
                sealed.append(current)
                continue
            children = tuple(
                dict.fromkeys(
                    child
                    for child in current.children
                    if child in by_id and child != current.node_id
                )
            )
            if not children:
                notes.append(
                    f"Node {current.node_id} was not added because it had no remaining children."
                )
                continue
            if children != tuple(current.children):
                sealed.append(current.model_copy(update={"children": children}))
            else:
                sealed.append(current)
        nodes = sealed
        by_id = {item.node_id: item for item in nodes}
        paths = [path for path in paths if path.root_id in by_id]
        if not nodes:
            break
        reached = _reachable([path.root_id for path in paths], by_id)
        missing = [node_id for node_id in by_id if node_id not in reached]
        if not missing:
            break
        missing_added = [node_id for node_id in missing if node_id in added_ids]
        if missing_added:
            for node_id in missing_added:
                notes.append(
                    f"Reconciliation node {node_id} was not connected to a policy path "
                    "and was not added."
                )
            missing_set = set(missing_added)
            nodes = [item for item in nodes if item.node_id not in missing_set]
            continue
        missing_set = set(missing)
        child_of_missing: set[str] = set()
        for current in nodes:
            if current.node_id not in missing_set or isinstance(current, CriterionNode):
                continue
            child_of_missing.update(child for child in current.children if child in missing_set)
        roots = [node_id for node_id in missing if node_id not in child_of_missing] or missing[:1]
        for node_id in roots:
            path_id = node_id
            suffix = 2
            while path_id in used_path_ids or len(path_id) > 128:
                extra = f"-{suffix}"
                path_id = f"{node_id[: 128 - len(extra)]}{extra}"
                suffix += 1
            paths.append(
                PolicyPath(
                    path_id=path_id,
                    title=node_id,
                    scope="Disconnected saved rule retained for review.",
                    root_id=node_id,
                    sources=by_id[node_id].sources,
                )
            )
            used_path_ids.add(path_id)
            notes.append(
                f"Node {node_id} was not reachable from a reconciled path. "
                "It was kept as its own path and was not combined with other procedures."
            )
    else:
        raise ValueError("Saved policy nodes could not be connected to a sourced path")
    if not paths:
        raise ValueError("No sourced policy paths were extracted")
    compiled_paths = tuple(paths)
    expected_refs = {
        section.section_id + ":" + ref.reference_id
        for section in sections
        for ref in section.candidate.dependencies
    }
    resolved = {item.reference_id: item for item in reconciliation.resolutions}
    if len(resolved) != len(reconciliation.resolutions) or resolved.keys() != expected_refs:
        raise ValueError("Every extracted dependency requires exactly one resolution")
    known = {section.section_id for section in sections}
    messages = [*reconciliation.issues, *notes]
    edges: dict[str, set[str]] = {section: set() for section in known}
    for reference in resolved.values():
        if not set(reference.target_section_ids) <= known:
            raise ValueError("Dependency resolution references an unknown section")
        if reference.status == "resolved" and not reference.target_section_ids:
            raise ValueError("A resolved dependency needs its target sections")
        if reference.status != "resolved":
            messages.append(f"{reference.reference_id}: {reference.explanation}")
        edges[reference.reference_id.split(":")[0]].update(reference.target_section_ids)
        original = next(
            ref
            for section in sections
            for ref in section.candidate.dependencies
            if section.section_id + ":" + ref.reference_id == reference.reference_id
        )
        if original.kind == "exception":
            messages.append(
                f"{reference.reference_id}: Exception relationship requires human review; "
                "resolution alone does not establish an executable exception."
            )

    def cyclic(start: str, current: str, seen: set[str]) -> bool:
        for target in edges[current]:
            if target == start:
                return True
            if target not in seen and cyclic(start, target, seen | {target}):
                return True
        return False

    if any(cyclic(section, section, {section}) for section in known):
        messages.append("Cross-section dependency cycle requires review.")
    coverage = []
    for section, audit in zip(sections, audits, strict=True):
        validate_audit(section, audit)
        messages.extend((*section.candidate.issues, *audit.missing_conditions, *audit.issues))
        dispositions = {item.unit_id: item for item in section.candidate.dispositions}
        for unit in section.plan.primary:
            item = dispositions[unit.unit_id]
            coverage.append(
                CoverageEntry(
                    section_id=section.section_id,
                    unit_id=unit.unit_id,
                    source=unit.source,
                    disposition=item.kind,
                    explanation=item.explanation,
                    audited=True,
                )
            )
            if item.kind == "unresolved":
                messages.append(f"{unit.unit_id}: {item.explanation}")
    first = policies[0]
    for field in ("identifier", "effective_from", "effective_to", "revision_date"):
        if (
            len(
                {
                    getattr(policy, field)
                    for policy in policies
                    if getattr(policy, field) is not None
                }
            )
            > 1
        ):
            messages.append(f"Conflicting policy {field} across sections requires review.")
    # A section may leave metadata null while another section carries it. Keep
    # the first established value rather than inheriting only the first section.
    identifier = next(
        (policy.identifier for policy in policies if policy.identifier is not None), None
    )
    revision_date = next(
        (policy.revision_date for policy in policies if policy.revision_date is not None), None
    )
    effective_from = next(
        (policy.effective_from for policy in policies if policy.effective_from is not None), None
    )
    effective_to = next(
        (policy.effective_to for policy in policies if policy.effective_to is not None), None
    )
    issues = tuple(issue for policy in policies for issue in policy.issues) + tuple(
        ReviewIssue(
            issue_id=f"build-issue-{index}",
            category=IssueCategory.COMPLETENESS,
            message=message,
            action="Review the original guideline and build coverage.",
            blocks_readiness=True,
        )
        for index, message in enumerate(dict.fromkeys(messages))
    )
    policy = Policy(
        policy_id=policy_id,
        document_id=document.document_id,
        document_sha256=document.sha256,
        title=first.title,
        scope_summary="; ".join(path.scope for path in compiled_paths),
        identifier=identifier,
        revision_date=revision_date,
        effective_from=effective_from,
        effective_to=effective_to,
        criteria=tuple(criterion for item in policies for criterion in item.criteria),
        nodes=tuple(nodes),
        root_id=compiled_paths[0].root_id,
        paths=compiled_paths,
        sections=tuple(item for policy in policies for item in policy.sections),
        issues=issues,
    )
    resolver.validate_policy(policy)
    return policy, tuple(coverage)


def select_policy_path(policy: Policy, path_id: str | None) -> Policy:
    if not policy.paths:
        return policy
    if path_id is None and len(policy.paths) == 1:
        path_id = policy.paths[0].path_id
    path = next((path for path in policy.paths if path.path_id == path_id), None)
    if path is None:
        raise ValueError("An applicable request must select a sourced policy path")
    by_id = {node.node_id: node for node in policy.nodes}
    included: set[str] = set()
    pending = [path.root_id]
    while pending:
        node = by_id[pending.pop()]
        if node.node_id in included:
            continue
        included.add(node.node_id)
        if not isinstance(node, CriterionNode):
            pending.extend(node.children)
    criteria = {
        node.criterion_id
        for node in policy.nodes
        if isinstance(node, CriterionNode) and node.node_id in included
    }
    return Policy.model_validate_json(
        canonical_bytes(
            policy.model_copy(
                update={
                    "root_id": path.root_id,
                    "paths": (path,),
                    "nodes": tuple(node for node in policy.nodes if node.node_id in included),
                    "criteria": tuple(
                        item for item in policy.criteria if item.criterion_id in criteria
                    ),
                    "sections": tuple(
                        item.model_copy(
                            update={
                                "criterion_ids": tuple(
                                    key for key in item.criterion_ids if key in criteria
                                )
                            }
                        )
                        for item in policy.sections
                        if not item.criterion_ids or set(item.criterion_ids) & criteria
                    ),
                    "issues": tuple(
                        item.model_copy(
                            update={
                                "criterion_ids": tuple(
                                    key for key in item.criterion_ids if key in criteria
                                )
                            }
                        )
                        for item in policy.issues
                        if not item.criterion_ids or set(item.criterion_ids) & criteria
                    ),
                }
            )
        )
    )
