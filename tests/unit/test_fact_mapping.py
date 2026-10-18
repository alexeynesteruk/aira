"""Assessment may cite saved facts and must not invent or rewrite them."""

import pytest

from app.evidence import EvidenceValidationError, require_saved_fact_mapping
from app.schemas import (
    ChartFact,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    FactPolarity,
    Finding,
    SourceSpan,
)


def span() -> SourceSpan:
    return SourceSpan(
        document_id="chart-doc",
        document_sha256="b" * 64,
        extraction_id="chart-extraction",
        page=1,
        block_id="p0001.b00000",
        start=0,
        end=4,
        excerpt="word",
    )


def fact(fact_id: str = "fact-heart-rate", proposition: str = "Heart rate is 44 bpm.") -> ChartFact:
    return ChartFact(
        fact_id=fact_id,
        proposition=proposition,
        sources=(span(),),
        polarity=FactPolarity.AFFIRMED,
        value=44,
        unit="bpm",
    )


def finding(fact_id: str, status: EvidenceStatus = EvidenceStatus.MET) -> Finding:
    return Finding(
        criterion_id="criterion-rate",
        status=status,
        rationale="The saved fact is the only evidence the finding may cite.",
        evidence=(EvidenceReference(fact_id=fact_id, relation=EvidenceRelation.SUPPORTING),)
        if status == EvidenceStatus.MET
        else (),
        unresolved_reasons=()
        if status == EvidenceStatus.MET
        else ("Not established from saved facts.",),
    )


def test_saved_fact_ids_are_returned_unchanged() -> None:
    saved = (fact(),)
    mapped = require_saved_fact_mapping(saved, (finding("fact-heart-rate"),), saved)
    assert mapped is saved


@pytest.mark.parametrize(
    "status",
    [
        EvidenceStatus.MET,
        EvidenceStatus.NOT_MET,
        EvidenceStatus.MISSING,
        EvidenceStatus.CONFLICTING,
        EvidenceStatus.NEEDS_REVIEW,
    ],
)
def test_finding_statuses_stay_distinct_from_each_other(status: EvidenceStatus) -> None:
    assert status.value in {"met", "not_met", "missing", "conflicting", "needs_review"}
    assert len({item.value for item in EvidenceStatus}) == 5


def test_an_invented_fact_id_is_rejected_and_the_saved_fact_is_unchanged() -> None:
    saved = (fact(),)
    before = saved[0].model_dump(mode="json")
    with pytest.raises(EvidenceValidationError, match="unknown fact"):
        require_saved_fact_mapping(saved, (finding("invented-fact"),), saved)
    assert saved[0].model_dump(mode="json") == before


def test_a_rewritten_fact_is_rejected_and_the_saved_fact_is_unchanged() -> None:
    saved = (fact(),)
    rewritten = (fact(proposition="Heart rate is 80 bpm."),)
    before = saved[0].model_dump(mode="json")
    with pytest.raises(EvidenceValidationError, match="rewrite"):
        require_saved_fact_mapping(saved, (finding("fact-heart-rate"),), rewritten)
    assert saved[0].model_dump(mode="json") == before
    assert rewritten[0].proposition == "Heart rate is 80 bpm."


def test_provider_failure_is_not_a_missing_finding() -> None:
    """Operational failures use ErrorCode. They are not evidence statuses."""
    from app.schemas import ErrorCode

    assert ErrorCode.EXTRACTION_FAILED.value != EvidenceStatus.MISSING.value
    assert "missing" not in {code.value for code in ErrorCode}
