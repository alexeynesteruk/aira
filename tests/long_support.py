"""Scripted structural interpreter over fictional sources; never live-model evidence."""

import asyncio
import json
import re
from collections import Counter

from support import ControlledInterpreter

from app.policies.compiler import ModelStep
from app.schemas import PolicyCandidate
from app.schemas.builds import (
    AuditCandidate,
    BlockDisposition,
    DefinitionCandidate,
    DependencyCandidate,
    DependencyResolution,
    PathCandidate,
    ReconciliationCandidate,
    SectionCandidate,
)


def wire(cls, **data):
    return cls.model_validate_json(
        json.dumps(data, default=lambda value: value.model_dump(mode="json"))
    )


def cite(document_id, unit):
    return dict(document_id=document_id, page=unit.source.page, quote=unit.source.excerpt)


def fragment(document_id, units):
    requirements = []
    nodes = []
    paths = []
    for family in ("Alpha", "Beta"):
        members = []
        for unit in units:
            match = re.search(
                rf"{family} requires documented condition (R\d+)\.", unit.source.excerpt
            )
            if not match:
                continue
            identity = match[1]
            citation = cite(document_id, unit)
            requirements.append(
                dict(
                    criterion_id=identity,
                    wording=match[0],
                    interpretation=match[0],
                    citations=[citation],
                    context=[],
                    predicate_kind="narrative",
                    operator=None,
                    threshold=None,
                    unit=None,
                    date_boundary=None,
                    date_role=None,
                )
            )
            nodes.append(
                dict(
                    node_id=identity,
                    kind="criterion",
                    children=[],
                    criterion_id=identity,
                    citations=[citation],
                )
            )
            members.append(identity)
        if members:
            evidence = next(
                item["citations"] for item in requirements if item["criterion_id"] == members[0]
            )
            nodes.append(
                dict(
                    node_id=family,
                    kind="all",
                    children=members,
                    criterion_id=None,
                    citations=evidence,
                )
            )
            paths.append(
                dict(
                    path_id=family,
                    title=family,
                    scope=f"{family} procedure",
                    root_id=family,
                    citations=evidence,
                )
            )
    if not requirements:
        return None
    return wire(
        PolicyCandidate,
        **dict(
            title="Fictional guideline",
            scope_summary="Distinct procedure paths",
            identifier=None,
            revision_date=None,
            effective_from=None,
            effective_to=None,
            criteria=requirements,
            nodes=nodes,
            root_id=paths[0]["root_id"],
            paths=paths,
            sections=[
                dict(
                    section_id="requirements",
                    heading="Conditions",
                    citations=requirements[0]["citations"],
                    disposition="requirements",
                    criterion_ids=[item["criterion_id"] for item in requirements],
                    explanation="Mandatory conditions.",
                )
            ],
            interpretation_issues=[],
        ),
    )


class StructuralInterpreter(ControlledInterpreter):
    def __init__(self, *, fail_section=None, gate=None):
        super().__init__()
        self.structural_calls = Counter()
        self.fail_section = fail_section
        self.section_gate = gate

    async def section(self, inputs, plan):
        self.structural_calls[("section", plan.section_id)] += 1
        if self.section_gate:
            await self.section_gate.wait()
        if plan.section_id == self.fail_section:
            raise ValueError("Injected section failure")
        local = fragment(inputs.document.document_id, plan.primary)
        dispositions = []
        definitions, dependencies = [], []
        for unit in plan.primary:
            text = unit.source.excerpt
            citation = cite(inputs.document.document_id, unit)
            kind = (
                "requirements"
                if re.search(r"(Alpha|Beta) requires documented condition R\d+\.", text)
                else "context"
            )
            if "D1 defines" in text:
                kind = "definition"
                definitions.append(
                    wire(DefinitionCandidate, term="D1", meaning=text, citations=[citation])
                )
            if "See definition D1" in text:
                dependencies.extend(
                    [
                        wire(
                            DependencyCandidate,
                            reference_id="D1",
                            target="D1",
                            kind="definition",
                            citations=[citation],
                        ),
                        wire(
                            DependencyCandidate,
                            reference_id="E1",
                            target="E1",
                            kind="exception",
                            citations=[citation],
                        ),
                    ]
                )
            dispositions.append(
                wire(
                    BlockDisposition,
                    unit_id=unit.unit_id,
                    kind=kind,
                    explanation="Scripted classification of the full source block.",
                )
            )
        return ModelStep(
            wire(
                SectionCandidate,
                dispositions=dispositions,
                fragment=local,
                definitions=definitions,
                dependencies=dependencies,
                issues=[],
            )
        )

    async def reconcile(self, inputs, sections):
        self.structural_calls[("reconcile", "")] += 1
        nodes, paths, resolutions = [], [], []
        for family in ("Alpha", "Beta"):
            local = [
                path
                for section in sections
                if section.policy
                for path in section.policy.paths
                if path.title == family
            ]
            if local:
                source = local[0].sources[0]
                citation = dict(
                    document_id=source.document_id, page=source.page, quote=source.excerpt
                )
                nodes.append(
                    dict(
                        node_id=family,
                        kind="all",
                        children=[item.root_id for item in local],
                        criterion_id=None,
                        citations=[citation],
                    )
                )
                paths.append(
                    wire(
                        PathCandidate,
                        path_id=family,
                        title=family,
                        scope=f"{family} procedure",
                        root_id=family,
                        citations=[citation],
                    )
                )
        for section in sections:
            for ref in section.candidate.dependencies:
                target = [
                    other.section_id
                    for other in sections
                    if any(
                        (ref.target == "D1" and "D1 defines" in unit.source.excerpt)
                        or (ref.target == "E1" and "E1:" in unit.source.excerpt)
                        for unit in other.plan.primary
                    )
                ]
                resolutions.append(
                    wire(
                        DependencyResolution,
                        reference_id=section.section_id + ":" + ref.reference_id,
                        target_section_ids=target,
                        status="resolved" if target else "unresolved",
                        explanation="Exact named fictional reference.",
                    )
                )
        return ModelStep(
            wire(
                ReconciliationCandidate,
                nodes=nodes,
                paths=paths,
                resolutions=resolutions,
                issues=[],
            )
        )

    async def merge(self, inputs, groups, sections):
        self.structural_calls[("merge", "")] += 1
        global_result = (await self.reconcile(inputs, sections)).value
        nodes, paths = [], []
        for family in ("Alpha", "Beta"):
            local = [
                path for group in groups for path in group.result.paths if path.title == family
            ]
            if not local:
                continue
            citation = local[0].citations[0]
            nodes.append(
                dict(
                    node_id=family,
                    kind="all",
                    children=[path.root_id for path in local],
                    criterion_id=None,
                    citations=[citation.model_dump(mode="json")],
                )
            )
            paths.append(
                wire(
                    PathCandidate,
                    path_id=family,
                    title=family,
                    scope=f"{family} procedure",
                    root_id=family,
                    citations=[citation.model_dump(mode="json")],
                )
            )
        return ModelStep(
            wire(
                ReconciliationCandidate,
                nodes=nodes,
                paths=paths,
                resolutions=[item.model_dump(mode="json") for item in global_result.resolutions],
                issues=[],
            )
        )

    async def audit(self, inputs, section, reconciliation):
        self.structural_calls[("audit", section.section_id)] += 1
        await asyncio.sleep(0)
        return ModelStep(
            wire(
                AuditCandidate,
                checked_unit_ids=[unit.unit_id for unit in section.plan.primary],
                missing_conditions=[],
                issues=[],
            )
        )
