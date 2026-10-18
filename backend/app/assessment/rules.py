"""Three-valued policy aggregation with independent readiness blockers."""

from collections.abc import Sequence
from typing import Literal

from app.evidence import predicate_support_reasons
from app.schemas import (
    ApplicabilityResult,
    ApplicabilityStatus,
    AssessmentOutcome,
    CriterionNode,
    EvidenceStatus,
    Finding,
    LogicalValue,
    Policy,
    ReviewIssue,
)
from app.schemas.base import StrictModel


class NodeTrace(StrictModel):
    node_id: str
    kind: Literal["all", "any", "criterion"]
    logical_value: LogicalValue
    children: tuple[str, ...] = ()
    criterion_id: str | None = None
    finding: Finding | None = None
    unresolved_reasons: tuple[str, ...] = ()
    supporting_children: tuple[str, ...] = ()


class ReadinessBlocker(StrictModel):
    code: str
    reference_id: str | None = None
    message: str


class EvaluationResult(StrictModel):
    root_id: str
    logical_value: LogicalValue | None
    outcome: AssessmentOutcome | None
    traces: tuple[NodeTrace, ...] = ()
    satisfied_path: tuple[str, ...] = ()
    blockers: tuple[ReadinessBlocker, ...] = ()


def _aggregate(kind: Literal["all", "any"], values: Sequence[LogicalValue]) -> LogicalValue:
    if kind == "all":
        if LogicalValue.FALSE in values:
            return LogicalValue.FALSE
        return (
            LogicalValue.TRUE
            if all(value == LogicalValue.TRUE for value in values)
            else LogicalValue.UNKNOWN
        )
    if LogicalValue.TRUE in values:
        return LogicalValue.TRUE
    return (
        LogicalValue.FALSE
        if all(value == LogicalValue.FALSE for value in values)
        else LogicalValue.UNKNOWN
    )


def evaluate_policy(
    policy: Policy,
    findings: Sequence[Finding],
    applicability: ApplicabilityResult,
    issues: Sequence[ReviewIssue] = (),
) -> EvaluationResult:
    """Aggregate already source-validated findings, never infer them from prose.

    Every leaf is retained, including unused alternative branches. Scope is an
    independent gate. Structural graph validity comes from the Policy contract.
    Completeness here detects known blockers, not omissions no one identified.
    """
    if applicability.status != ApplicabilityStatus.APPLICABLE:
        if findings:
            raise ValueError("Do not assess clinical findings before applicability is established")
        mismatch = applicability.status == ApplicabilityStatus.MISMATCH
        return EvaluationResult(
            root_id=policy.root_id,
            logical_value=None,
            outcome=AssessmentOutcome.APPLICABILITY_MISMATCH if mismatch else None,
            blockers=(
                ReadinessBlocker(
                    code="applicability_" + applicability.status.value,
                    message=applicability.rationale,
                ),
            ),
        )
    by_finding = {finding.criterion_id: finding for finding in findings}
    criteria = {criterion.criterion_id for criterion in policy.criteria}
    if len(by_finding) != len(findings) or by_finding.keys() != criteria:
        raise ValueError(
            "Exactly one finding is required for every criterion, including alternatives"
        )
    for issue in issues:
        if not set(issue.criterion_ids) <= criteria:
            raise ValueError("Review issue references an unknown criterion")
    blockers = [
        ReadinessBlocker(code="review_issue", reference_id=issue.issue_id, message=issue.message)
        for issue in (*policy.issues, *issues)
        if issue.blocks_readiness
    ]
    blockers.extend(
        ReadinessBlocker(
            code="unresolved_policy_section",
            reference_id=section.section_id,
            message=section.explanation,
        )
        for section in policy.sections
        if section.disposition == "unresolved"
    )
    blockers.extend(
        ReadinessBlocker(
            code=reason,
            reference_id=criterion.criterion_id,
            message="The governing requirement has an unsupported or unverified interpretation.",
        )
        for criterion in policy.criteria
        for reason in predicate_support_reasons(criterion)
    )
    nodes = {node.node_id: node for node in policy.nodes}
    traces: dict[str, NodeTrace] = {}
    pending = [(policy.root_id, False)]
    while pending:
        node_id, leaving = pending.pop()
        if node_id in traces:
            continue
        node = nodes[node_id]
        if isinstance(node, CriterionNode):
            finding = by_finding[node.criterion_id]
            value = {
                EvidenceStatus.MET: LogicalValue.TRUE,
                EvidenceStatus.NOT_MET: LogicalValue.FALSE,
                EvidenceStatus.MISSING: LogicalValue.UNKNOWN,
                EvidenceStatus.CONFLICTING: LogicalValue.UNKNOWN,
                EvidenceStatus.NEEDS_REVIEW: LogicalValue.UNKNOWN,
            }[finding.status]
            traces[node_id] = NodeTrace(
                node_id=node_id,
                kind=node.kind,
                logical_value=value,
                criterion_id=node.criterion_id,
                finding=finding,
                unresolved_reasons=finding.unresolved_reasons,
            )
        elif not leaving:
            pending.append((node_id, True))
            pending.extend((child, False) for child in reversed(node.children))
        else:
            children = [traces[child] for child in node.children]
            value = _aggregate(node.kind, [child.logical_value for child in children])
            true_children = tuple(
                child.node_id for child in children if child.logical_value == LogicalValue.TRUE
            )
            traces[node_id] = NodeTrace(
                node_id=node_id,
                kind=node.kind,
                children=node.children,
                logical_value=value,
                unresolved_reasons=tuple(
                    dict.fromkeys(
                        reason for child in children for reason in child.unresolved_reasons
                    )
                ),
                supporting_children=(true_children if node.kind == "all" else true_children[:1])
                if value == LogicalValue.TRUE
                else (),
            )
    value = traces[policy.root_id].logical_value
    path: list[str] = []
    if value == LogicalValue.TRUE:
        walk = [policy.root_id]
        while walk:
            node_id = walk.pop()
            if node_id not in path:
                path.append(node_id)
                walk.extend(reversed(traces[node_id].supporting_children))
    if blockers:
        outcome = AssessmentOutcome.REVIEW_REQUIRED
    elif value == LogicalValue.TRUE:
        outcome = AssessmentOutcome.DOCUMENTED_REQUIREMENTS_SATISFIED
    elif value == LogicalValue.UNKNOWN and any(
        finding.status in (EvidenceStatus.CONFLICTING, EvidenceStatus.NEEDS_REVIEW)
        for finding in findings
    ):
        outcome = AssessmentOutcome.REVIEW_REQUIRED
    else:
        outcome = AssessmentOutcome.DOCUMENTATION_GAPS_OR_CONTRARY_EVIDENCE
    return EvaluationResult(
        root_id=policy.root_id,
        logical_value=value,
        outcome=outcome,
        traces=tuple(traces[node.node_id] for node in policy.nodes),
        satisfied_path=tuple(path),
        blockers=tuple(blockers),
    )
