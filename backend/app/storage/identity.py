"""Stable, conservative identities for local inputs and reusable work."""

import hashlib
import json

from pydantic import BaseModel

from app.schemas import (
    ConfigurationProvenance,
    DocumentRecord,
    DocumentRole,
    ExtractionRecord,
    MetadataAnnotation,
    RequestContext,
)


def canonical_bytes(value: object) -> bytes:
    """Serialize JSON data deterministically, rejecting non-finite numeric values."""
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def document_interpretation_fingerprint(
    configuration: ConfigurationProvenance,
    extraction: ExtractionRecord,
    stage: str,
    output_type: type[BaseModel],
) -> str:
    """Only this document's extraction and model contract can invalidate reuse."""
    related = {
        "policy": {"policy", "policy_index", "policy_page"},
        "chart": {"chart"},
    }.get(stage, {stage})
    relevant = tuple(prompt for prompt in configuration.prompts if prompt.name in related)
    return fingerprint(
        {
            "identity_version": "independent-documents-v1",
            "stage": stage,
            "source_sha256": extraction.document_sha256,
            "parser": [
                extraction.parser_name,
                extraction.parser_version,
                extraction.configuration_sha256,
            ],
            "pages": [page.model_dump(mode="json") for page in extraction.pages],
            "prompts": [
                prompt.model_dump(mode="json") for prompt in (relevant or configuration.prompts)
            ],
            "provider": configuration.provider.value,
            "model": configuration.model_id,
            "transport": configuration.transport,
            "endpoint_sha256": configuration.endpoint_sha256,
            "sdk": configuration.sdk_version,
            "inference": configuration.inference.model_dump(mode="json"),
            "output_schema": output_type.model_json_schema(),
        }
    )


def assessment_fingerprint(
    policy: DocumentRecord,
    chart: DocumentRecord,
    configuration: ConfigurationProvenance,
    request_context: RequestContext | None = None,
    annotations: tuple[MetadataAnnotation, ...] = (),
) -> str:
    """Identify submitted inputs, not a run attempt or a predicted model response.

    IDs deliberately participate: citations from duplicate bytes under another
    application document ID cannot be reused without explicit provenance remapping.
    """
    if policy.role != DocumentRole.POLICY or chart.role != DocumentRole.CHART:
        raise ValueError("Assessment inputs require a policy and a chart in their named roles")
    return fingerprint(
        {
            "identity_version": 1,
            "documents": [
                {"role": item.role.value, "document_id": item.document_id, "sha256": item.sha256}
                for item in (policy, chart)
            ],
            "configuration": configuration.model_dump(mode="json"),
            "request_context": (
                request_context.model_dump(mode="json") if request_context is not None else None
            ),
            "annotations": [annotation.model_dump(mode="json") for annotation in annotations],
        }
    )
