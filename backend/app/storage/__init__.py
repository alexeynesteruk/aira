"""Local persistence API; no parser, model, HTTP, or cloud dependencies."""

from .identity import assessment_fingerprint, fingerprint
from .local import (
    LocalStore,
    StorageConflict,
    StorageError,
    StorageIntegrityError,
    StorageNotFound,
    StorageReferenceError,
    StoredArtifact,
)

__all__ = [
    "LocalStore",
    "StorageConflict",
    "StorageError",
    "StorageIntegrityError",
    "StorageNotFound",
    "StorageReferenceError",
    "StoredArtifact",
    "assessment_fingerprint",
    "fingerprint",
]
