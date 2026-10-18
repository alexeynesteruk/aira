"""Small, reviewed medical-term normalization helpers.

This is a deliberately bounded synonym table, not a clinical ontology. It
supports context matching and future golden-set expansion; it does not imply
semantic equivalence of conditions.
"""

from __future__ import annotations

_MEDICAL_SYNONYMS: dict[str, tuple[str, ...]] = {
    "hr": ("heart rate",),
    "bpm": ("beats per minute",),
    "vein": ("venous",),
    "stenosis": ("narrowing",),
}


def normalize_medical_term(term: str) -> str:
    """Return a canonical lowercase phrase for a supported medical term."""
    normalized = " ".join(term.lower().split())
    for canonical, aliases in _MEDICAL_SYNONYMS.items():
        if normalized == canonical or normalized in aliases:
            return canonical
    return normalized


def expand_medical_term(term: str) -> tuple[str, ...]:
    """Return the term plus its reviewed synonyms."""
    normalized = normalize_medical_term(term)
    aliases = _MEDICAL_SYNONYMS.get(normalized, ())
    return (normalized, *aliases)
