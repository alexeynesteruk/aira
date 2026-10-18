"""Deterministic policy-evaluation records carried with assessment results."""

from enum import StrEnum
from typing import Literal

from .base import StrictModel
from .evidence import Finding


class AssessmentOutcome(StrEnum):
    APPLICABILITY_MISMATCH = "applicability_mismatch"
    DOCUMENTED_REQUIREMENTS_SATISFIED = "documented_requirements_satisfied"
    DOCUMENTATION_GAPS_OR_CONTRARY_EVIDENCE = "documentation_gaps_or_contrary_evidence"
    REVIEW_REQUIRED = "review_required"


class LogicalValue(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


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
