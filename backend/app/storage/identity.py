"""Stable, conservative identities for local inputs and reusable work."""

import hashlib
import json

from pydantic import BaseModel

from app.schemas import (
    ConfigurationProvenance,
    DocumentRecord,
    DocumentRole,
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
