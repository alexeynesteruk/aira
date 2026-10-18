"""Readable exports derived only from a saved, eligible assessment snapshot."""

import json

from app.schemas import (
    AssessmentExport,
    AssessmentOutcome,
    RunStatus,
    SourceSpan,
)


def _text(value: object) -> str:
    """Escape source/model prose so it remains text in a Markdown document."""
    text = str(value).replace("\r", " ").replace("\n", " ")
    for character in ("\\", "`", "*", "_", "[", "]", "<", ">", "|", "#"):
        text = text.replace(character, "\\" + character)
    return text


def _sources(sources: tuple[SourceSpan, ...]) -> list[str]:
    lines = []
    for source in sources:
        lines.extend(
            [
                "",
                f"> {_text(source.excerpt)}",
                "",
                f"Source: `{source.document_id}`, page {source.page}, "
                f"extraction `{source.extraction_id}`, block `{source.block_id}`, "
                f"offsets [{source.start}, {source.end}); SHA-256 `{source.document_sha256}`.",
            ]
        )
    return lines


def render_markdown(export: AssessmentExport) -> str:
    """No recomputation, provider calls, or replacement of the saved outcome."""
    run = export.run
    lines = [
        "# Aira evidence checklist",
        "",
        "Documentation review for staff. Insurer decisions and clinical judgment remain separate.",
        "",
        f"Run: `{run.run_id}`. Status: `{run.status.value}`.",
        f"Created: {run.created_at.isoformat()}. Exported: {export.exported_at.isoformat()}.",
        f"Input fingerprint: `{run.input_fingerprint}`.",
    ]
    if run.parent_run_id:
        lines.append(f"Previous attempt: `{run.parent_run_id}`.")
    if run.status == RunStatus.NEEDS_INPUT:
        lines.append(
            "Assessment stopped for staff input; no medical-necessity evaluation was performed."
        )
    elif (
        run.status == RunStatus.COMPLETED
        and run.result is not None
        and run.result.outcome == AssessmentOutcome.APPLICABILITY_MISMATCH
    ):
        lines.append(
            "The uploaded policy does not apply to this request; "
            "no medical-necessity evaluation was performed."
        )
    lines.extend(["", "## Original documents", ""])
    for document in export.documents:
        lines.append(
            f"- {document.role.value}: {_text(document.filename)}; `{document.document_id}`; "
            f"{document.page_count} pages; SHA-256 `{document.sha256}`."
        )
    lines.extend(["", "## Selected request", ""])
    if run.request_context:
        request = run.request_context
        for name in (
            "procedure",
            "procedure_code",
            "anatomical_target",
            "laterality",
            "payer",
            "plan",
            "service_date",
            "assessment_cutoff",
        ):
            value = getattr(request, name)
            lines.append(f"- {name.replace('_', ' ')}: {_text(value) if value else 'Unresolved'}.")
        for field in request.field_sources:
            lines.extend(["", f"Sources for {field.field.value}:", *_sources(field.sources)])
    else:
        lines.append("Request context remains unresolved.")
    if run.annotations:
        lines.extend(["", "## Staff metadata annotations", ""])
        for annotation in run.annotations:
            lines.append(
                f"- {_text(annotation.field)}: {_text(annotation.value)}; "
                f"staff annotation `{annotation.annotation_id}` "
                f"at {annotation.created_at.isoformat()}."
            )
            if annotation.resolution_reason:
                lines.append(f"  Resolution reason: {_text(annotation.resolution_reason)}.")
            lines.extend(_sources(annotation.original_sources))
    lines.extend(["", "## Applicability", ""])
    if run.applicability:
        lines.append(f"**{run.applicability.status.value}**: {_text(run.applicability.rationale)}")
        if run.applicability.unresolved_fields:
            lines.append(
                "Clarification needed: "
                + ", ".join(field.value for field in run.applicability.unresolved_fields)
                + "."
            )
        lines.extend(_sources(run.applicability.sources))
    if run.result:
        result = run.result
        lines.extend(["", "## Saved outcome", "", f"**{result.outcome.value}**"])
        if result.logical_value:
            lines.append(f"Evaluated policy root: `{result.logical_value.value}`.")
        if result.policy:
            policy = result.policy
            lines.extend(["", f"Policy: {_text(policy.title)} (`{policy.policy_id}`)."])
            if policy.revision_date:
                lines.append(f"Revision date: {policy.revision_date.isoformat()}.")
            lines.append(
                f"Stated effective period: {policy.effective_from or 'not established'} to "
                f"{policy.effective_to or 'not established'}."
            )
            facts = {fact.fact_id: fact for fact in result.facts}
            findings = {finding.criterion_id: finding for finding in result.findings}
            lines.extend(["", "## Requirements and evidence", ""])
            for criterion in policy.criteria:
                finding = findings[criterion.criterion_id]
                lines.extend(
                    [
                        "",
                        f"### {_text(criterion.criterion_id)} — {finding.status.value}",
                        "",
                        _text(criterion.wording),
                        "",
                        f"Interpretation: {_text(criterion.interpretation)}",
                        *_sources(criterion.sources),
                        "",
                        f"Finding: {_text(finding.rationale)}",
                    ]
                )
                for reason in finding.unresolved_reasons:
                    lines.append(f"- Unresolved: {_text(reason)}")
                for reference in finding.evidence:
                    fact = facts[reference.fact_id]
                    lines.extend(
                        [
                            "",
                            f"{reference.relation.value}: {_text(fact.proposition)} "
                            f"(polarity {fact.polarity.value}; "
                            f"provenance {fact.provenance.value}).",
                            f"Event date: {fact.event_date or 'not established'}; "
                            f"documentation date: {fact.documentation_date or 'not established'}.",
                            *_sources(fact.sources),
                        ]
                    )
            lines.extend(["", "## Policy logic", ""])
            lines.append(f"Root: `{policy.root_id}`.")
            for node in policy.nodes:
                target = node.criterion_id if node.kind == "criterion" else ", ".join(node.children)
                lines.append(f"- `{node.node_id}`: {node.kind} → {_text(target)}")
            lines.extend(["", "## Sections and unresolved issues", ""])
            for section in policy.sections:
                lines.append(
                    f"- {_text(section.heading)}: {section.disposition}. "
                    f"{_text(section.explanation)}"
                )
                lines.extend(_sources(section.sources))
            for issue in (*policy.issues, *result.issues):
                lines.append(
                    f"- {_text(issue.message)}; action: {_text(issue.action)}; "
                    f"blocks readiness: {issue.blocks_readiness}."
                )
                lines.extend(_sources(issue.sources))
    lines.extend(
        [
            "",
            "## Processing provenance",
            "",
            "```json",
            json.dumps(
                {
                    "configuration": run.configuration.model_dump(mode="json"),
                    "usage": [usage.model_dump(mode="json") for usage in run.usage],
                    "schema_version": run.schema_version,
                },
                indent=2,
            ),
            "```",
            "",
        ]
    )
    return "\n".join(lines)
