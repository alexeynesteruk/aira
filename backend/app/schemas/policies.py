"""Policy data and structural validation, without rule evaluation."""

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from .base import FiniteNumber, Identifier, NonEmptyText, Sha256, StrictModel, VersionedModel
from .documents import SourceSpan


class IssueCategory(StrEnum):
    APPLICABILITY = "applicability"
    COMPLETENESS = "completeness"
    INTERPRETATION = "interpretation"
    EVIDENCE = "evidence"
    TEMPORAL = "temporal"
    CONTEXT = "context"


class ReviewIssue(StrictModel):
    issue_id: Identifier
    category: IssueCategory
    message: NonEmptyText
    action: NonEmptyText
    blocks_readiness: bool
    sources: tuple[SourceSpan, ...] = ()
    criterion_ids: tuple[Identifier, ...] = ()


class NarrativePredicate(StrictModel):
    kind: Literal["narrative"] = "narrative"
    question: NonEmptyText


class NumericPredicate(StrictModel):
    kind: Literal["numeric"] = "numeric"
    operator: Literal["gt", "gte", "lt", "lte", "eq"]
    threshold: FiniteNumber
    unit: NonEmptyText
    context: NonEmptyText


class DatePredicate(StrictModel):
    kind: Literal["date"] = "date"
    operator: Literal["before", "on_or_before", "after", "on_or_after", "on"]
    boundary: date
    date_role: NonEmptyText
    context: NonEmptyText


type Predicate = Annotated[
    NarrativePredicate | NumericPredicate | DatePredicate, Field(discriminator="kind")
]


class Criterion(StrictModel):
    criterion_id: Identifier
    wording: NonEmptyText
    interpretation: NonEmptyText
    sources: tuple[SourceSpan, ...] = Field(min_length=1)
    context: tuple[NonEmptyText, ...] = ()
    predicate: Predicate | None = None


class AllNode(StrictModel):
    kind: Literal["all"] = "all"
    node_id: Identifier
    children: tuple[Identifier, ...] = Field(min_length=1)
    sources: tuple[SourceSpan, ...] = Field(min_length=1)


class AnyNode(StrictModel):
    kind: Literal["any"] = "any"
    node_id: Identifier
    children: tuple[Identifier, ...] = Field(min_length=1)
    sources: tuple[SourceSpan, ...] = Field(min_length=1)


class CriterionNode(StrictModel):
    kind: Literal["criterion"] = "criterion"
    node_id: Identifier
    criterion_id: Identifier
    sources: tuple[SourceSpan, ...] = Field(min_length=1)


type PolicyNode = Annotated[AllNode | AnyNode | CriterionNode, Field(discriminator="kind")]


class PolicySection(StrictModel):
    section_id: Identifier
    heading: NonEmptyText
    sources: tuple[SourceSpan, ...] = Field(min_length=1)
    disposition: Literal["requirements", "context", "out_of_scope", "unresolved"]
    criterion_ids: tuple[Identifier, ...] = ()
    explanation: NonEmptyText

    @model_validator(mode="after")
    def linked_requirements(self) -> Self:
        if self.disposition == "requirements" and not self.criterion_ids:
            raise ValueError("a requirements section must link at least one criterion")
        return self


class PolicyPath(StrictModel):
    path_id: Identifier
    title: NonEmptyText
    scope: NonEmptyText
    root_id: Identifier
    sources: tuple[SourceSpan, ...] = Field(min_length=1)


class Policy(VersionedModel):
    policy_id: Identifier
    document_id: Identifier
    document_sha256: Sha256
    title: NonEmptyText
    scope_summary: NonEmptyText
    identifier: NonEmptyText | None = None
    revision_date: date | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    criteria: tuple[Criterion, ...] = Field(min_length=1)
    nodes: tuple[PolicyNode, ...] = Field(min_length=1)
    root_id: Identifier
    sections: tuple[PolicySection, ...] = Field(min_length=1)
    issues: tuple[ReviewIssue, ...] = ()
    paths: tuple[PolicyPath, ...] = ()

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("policy effective interval is reversed")
        criterion_ids = {criterion.criterion_id for criterion in self.criteria}
        by_id = {node.node_id: node for node in self.nodes}
        if len(criterion_ids) != len(self.criteria) or len(by_id) != len(self.nodes):
            raise ValueError("policy criterion and node identifiers must be unique")
        if self.root_id not in by_id:
            raise ValueError("policy root must identify a node")
        if len({path.path_id for path in self.paths}) != len(self.paths):
            raise ValueError("policy path identifiers must be unique")
        if any(path.root_id not in by_id for path in self.paths):
            raise ValueError("policy paths must identify existing roots")
        referenced_criteria: set[str] = set()
        for node in self.nodes:
            if isinstance(node, CriterionNode):
                if node.criterion_id not in criterion_ids:
                    raise ValueError("node references an unknown criterion")
                referenced_criteria.add(node.criterion_id)
            else:
                if len(node.children) != len(set(node.children)):
                    raise ValueError("logical children must be unique")
                if any(child not in by_id for child in node.children):
                    raise ValueError("logical node references an unknown child")
        if referenced_criteria != criterion_ids:
            raise ValueError("all criteria must be represented in the policy graph")
        self._validate_reachable_graph(by_id)
        if len({section.section_id for section in self.sections}) != len(self.sections):
            raise ValueError("policy section identifiers must be unique")
        for section in self.sections:
            if not set(section.criterion_ids).issubset(criterion_ids):
                raise ValueError("section references an unknown criterion")
        if len({issue.issue_id for issue in self.issues}) != len(self.issues):
            raise ValueError("policy issue identifiers must be unique")
        for issue in self.issues:
            if not set(issue.criterion_ids).issubset(criterion_ids):
                raise ValueError("issue references an unknown criterion")
        for source in self._sources():
            if (
                source.document_id != self.document_id
                or source.document_sha256 != self.document_sha256
            ):
                raise ValueError("policy sources must belong to the policy document")
        return self

    def _validate_reachable_graph(self, by_id: dict[str, PolicyNode]) -> None:
        visited: set[str] = set()
        active: set[str] = set()
        pending = [(root, False) for root in {self.root_id, *(p.root_id for p in self.paths)}]
        while pending:
            node_id, leaving = pending.pop()
            if leaving:
                active.remove(node_id)
                visited.add(node_id)
                continue
            if node_id in active:
                raise ValueError("policy graph contains a cycle")
            if node_id in visited:
                continue
            active.add(node_id)
            pending.append((node_id, True))
            node = by_id[node_id]
            if not isinstance(node, CriterionNode):
                pending.extend((child, False) for child in reversed(node.children))
        if visited != set(by_id):
            raise ValueError("every policy node must be reachable from the root")

    def _sources(self) -> tuple[SourceSpan, ...]:
        return tuple(
            source
            for record in (*self.criteria, *self.nodes, *self.sections, *self.issues, *self.paths)
            for source in record.sources
        )
