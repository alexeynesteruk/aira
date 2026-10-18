"""Fixture server for saved browser journeys — controlled interpreter, no live calls.

Run from ``frontend/``::

    uv run --project ../backend python ../tests/e2e/fixture_server.py \\
        --port 8001 --frontend-dir dist

Serves ``create_app`` against a fresh temporary store with E2EInterpreter — a
test-only StageInterpreter that returns source-valid domain records built from
quotes resolved against the run's real extractions. The staff ``procedure``
annotation is the scenario switch (a test-only control channel):

- no procedure annotation -> scope mismatch citing both documents;
- "E2E gaps" -> applicable scope, two-criterion policy, one met finding and one
  missing finding -> documentation_gaps_or_contrary_evidence;
- "E2E clarify" without a plan annotation -> unresolved scope (needs_input);
  with a plan annotation -> the gaps path.

These are scripted domain records over real citations — not model output.
"""

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import uvicorn  # noqa: E402
from support import (  # noqa: E402
    CHART_FACT_QUOTE,
    CHART_SCOPE_QUOTE,
    POLICY_SCOPE_QUOTE,
    quote,
)

from app.assessment.stages import (  # noqa: E402
    EvidenceInterpretation,
    PolicyInterpretation,
    ScopeInterpretation,
    StageInputs,
)
from app.documents.native import PARSER_VERSION  # noqa: E402
from app.main import create_app  # noqa: E402
from app.schemas import (  # noqa: E402
    AllNode,
    ApplicabilityResult,
    ApplicabilityStatus,
    ChartFact,
    ConfigurationProvenance,
    Criterion,
    CriterionNode,
    EvidenceReference,
    EvidenceRelation,
    EvidenceStatus,
    FactPolarity,
    Finding,
    InferenceSettings,
    ModelProvider,
    NarrativePredicate,
    Policy,
    PolicySection,
    RequestContext,
    RequestField,
    VersionReference,
)

POLICY_CRITERION_QUOTE = (3, "Treatment of telangiectasia such as spider veins")
POLICY_SECOND_QUOTE = (3, "There is demonstrated perforator reflux; AND")
POLICY_SECTION_QUOTE = (3, "Perforator Veins")

PROVIDER_DETAIL = "Fixture interpreter for browser tests; no live model calls."


def fixture_configuration() -> ConfigurationProvenance:
    from app.assessment.workflow import WorkflowLimits, workflow_parser_fingerprint
    from app.documents import NativePdfConfig

    return ConfigurationProvenance(
        parser=VersionReference(name="pdfplumber", version=PARSER_VERSION),
        parser_configuration_sha256=workflow_parser_fingerprint(
            NativePdfConfig(), WorkflowLimits()
        ),
        prompts=(VersionReference(name="fixture", version="1"),),
        provider=ModelProvider.OPENAI,
        model_id="fixture-e2e-interpreter",
        sdk_version="fixture",
        inference=InferenceSettings(max_output_tokens=4096),
    )


def _annotation_value(inputs: StageInputs, field: str) -> str | None:
    for annotation in inputs.annotations:
        if annotation.field == field:
            return annotation.value
    return None


class E2EInterpreter:
    """StageInterpreter producing source-valid records from real extraction quotes."""

    def __init__(self) -> None:
        self.calls = {"scope": 0, "policy": 0, "evidence": 0}

    async def scope(self, inputs: StageInputs) -> ScopeInterpretation:
        self.calls["scope"] += 1
        procedure = _annotation_value(inputs, "procedure")
        plan = _annotation_value(inputs, "plan")
        if procedure == "E2E clarify" and plan is None:
            return ScopeInterpretation(
                request=RequestContext(procedure=procedure, payer="Fixture payer"),
                applicability=ApplicabilityResult(
                    status=ApplicabilityStatus.UNRESOLVED,
                    rationale="Staff must identify the plan before scope resolves.",
                    unresolved_fields=(RequestField.PLAN,),
                ),
            )
        if procedure in {"E2E gaps", "E2E clarify"}:
            return ScopeInterpretation(
                request=RequestContext(
                    procedure=procedure,
                    payer="Fixture payer",
                    plan=plan,
                ),
                applicability=ApplicabilityResult(
                    status=ApplicabilityStatus.APPLICABLE,
                    rationale="The cited scope terms apply to the scripted request.",
                    sources=(
                        quote(inputs, inputs.policy_document, *POLICY_SCOPE_QUOTE),
                        quote(inputs, inputs.chart_document, *CHART_SCOPE_QUOTE),
                    ),
                ),
            )
        return ScopeInterpretation(
            request=RequestContext(
                procedure=procedure or "endovenous vein ablation",
                payer="Fixture payer",
            ),
            applicability=ApplicabilityResult(
                status=ApplicabilityStatus.MISMATCH,
                rationale="A scripted scope judgment citing both source documents.",
                sources=(
                    quote(inputs, inputs.policy_document, *POLICY_SCOPE_QUOTE),
                    quote(inputs, inputs.chart_document, *CHART_SCOPE_QUOTE),
                ),
            ),
        )

    async def policy(self, inputs: StageInputs) -> PolicyInterpretation:
        self.calls["policy"] += 1
        first = quote(inputs, inputs.policy_document, *POLICY_CRITERION_QUOTE)
        second = quote(inputs, inputs.policy_document, *POLICY_SECOND_QUOTE)
        heading = quote(inputs, inputs.policy_document, *POLICY_SECTION_QUOTE)
        criterion_a = Criterion(
            criterion_id="criterion-telangiectasia",
            wording="Treatment of telangiectasia is considered cosmetic.",
            interpretation="The cited sentence governs telangiectasia treatment.",
            sources=(first,),
            predicate=NarrativePredicate(
                question="Does the chart document telangiectasia treatment need?"
            ),
        )
        criterion_b = Criterion(
            criterion_id="criterion-perforator-reflux",
            wording="There is demonstrated perforator reflux.",
            interpretation="The cited sentence requires demonstrated reflux.",
            sources=(second,),
            predicate=NarrativePredicate(
                question="Does the chart document demonstrated perforator reflux?"
            ),
        )
        return PolicyInterpretation(
            policy=Policy(
                policy_id="e2e-fixture-policy",
                document_id=inputs.policy_document.document_id,
                document_sha256=inputs.policy_document.sha256,
                title="Fixture venous requirements",
                scope_summary="Scripted requirements for the controlled browser journey.",
                criteria=(criterion_a, criterion_b),
                nodes=(
                    AllNode(
                        node_id="node-all",
                        children=("node-a", "node-b"),
                        sources=(first,),
                    ),
                    CriterionNode(
                        node_id="node-a",
                        criterion_id="criterion-telangiectasia",
                        sources=(first,),
                    ),
                    CriterionNode(
                        node_id="node-b",
                        criterion_id="criterion-perforator-reflux",
                        sources=(second,),
                    ),
                ),
                root_id="node-all",
                sections=(
                    PolicySection(
                        section_id="requirements",
                        heading="Requirements",
                        sources=(heading,),
                        disposition="requirements",
                        criterion_ids=(
                            "criterion-telangiectasia",
                            "criterion-perforator-reflux",
                        ),
                        explanation="Both scripted criteria are requirements.",
                    ),
                ),
            )
        )

    async def evidence(self, inputs: StageInputs, policy: Policy) -> EvidenceInterpretation:
        self.calls["evidence"] += 1
        span = quote(inputs, inputs.chart_document, *CHART_FACT_QUOTE)
        fact = ChartFact(
            fact_id="fact-heart-rate",
            proposition="The chart documents a resting heart rate of 44 bpm.",
            sources=(span,),
            polarity=FactPolarity.AFFIRMED,
        )
        findings = tuple(
            Finding(
                criterion_id=criterion.criterion_id,
                status=(
                    EvidenceStatus.MET
                    if criterion.criterion_id == "criterion-telangiectasia"
                    else EvidenceStatus.MISSING
                ),
                rationale=(
                    "The cited measurement satisfies the scripted requirement."
                    if criterion.criterion_id == "criterion-telangiectasia"
                    else "The chart does not document demonstrated perforator reflux."
                ),
                evidence=(
                    (EvidenceReference(fact_id=fact.fact_id, relation=EvidenceRelation.SUPPORTING),)
                    if criterion.criterion_id == "criterion-telangiectasia"
                    else ()
                ),
                unresolved_reasons=(
                    ()
                    if criterion.criterion_id == "criterion-telangiectasia"
                    else ("The chart does not document demonstrated perforator reflux.",)
                ),
            )
            for criterion in policy.criteria
        )
        return EvidenceInterpretation(facts=(fact,), findings=findings)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--frontend-dir", type=Path, required=True)
    args = parser.parse_args()
    data_dir = Path(tempfile.mkdtemp(prefix="aira-e2e-"))
    app = create_app(
        frontend_dir=args.frontend_dir.resolve(),
        data_dir=data_dir,
        env_file=data_dir / "missing.env",
        interpreter=E2EInterpreter(),
        configuration=fixture_configuration(),
        provider_detail=PROVIDER_DETAIL,
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
