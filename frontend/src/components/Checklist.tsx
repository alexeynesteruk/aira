import type { ChartFact, Criterion, Finding, Policy, PolicyNode, SourceSpan } from '../api'
import { findingLabel, relationLabel } from '../labels'
import { Citations } from './Citations'

type OnCite = (source: SourceSpan) => void

export function FindingCard({
  criterion,
  finding,
  facts,
  onCite,
}: {
  criterion: Criterion
  finding: Finding
  facts: Map<string, ChartFact>
  onCite: OnCite
}) {
  return (
    <article className="finding-card" aria-label={`Finding: ${criterion.criterion_id}`}>
      <header className="finding-head">
        <span className="badge" data-status={finding.status}>
          {findingLabel(finding.status)}
        </span>
        <code>{criterion.criterion_id}</code>
      </header>
      <p className="criterion-wording">{criterion.wording}</p>
      <p className="note">Interpretation: {criterion.interpretation}</p>
      <Citations sources={criterion.sources} label="Policy" onOpen={onCite} />
      <p>{finding.rationale}</p>
      {finding.status === 'missing' && (
        <p className="note" role="note">
          Documentation needed
        </p>
      )}
      {finding.unresolved_reasons.length > 0 && (
        <ul className="unresolved">
          {finding.unresolved_reasons.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
      {finding.evidence.map((reference) => {
        const fact = facts.get(reference.fact_id)
        if (!fact) return null
        return (
          <div className="fact" key={`${reference.fact_id}-${reference.relation}`}>
            <p>
              <strong>{relationLabel(reference.relation)}:</strong> {fact.proposition}
            </p>
            <Citations sources={fact.sources} label="Chart" onOpen={onCite} />
          </div>
        )
      })}
    </article>
  )
}

function PolicyTreeNode({
  policy,
  node,
  findings,
  facts,
  onCite,
}: {
  policy: Policy
  node: PolicyNode
  findings: Map<string, Finding>
  facts: Map<string, ChartFact>
  onCite: OnCite
}) {
  const nodeById = new Map(policy.nodes.map((item) => [item.node_id, item]))
  if (node.kind === 'criterion') {
    const criterion = policy.criteria.find((item) => item.criterion_id === node.criterion_id)
    const finding = findings.get(node.criterion_id ?? '')
    if (!criterion || !finding) return null
    return <FindingCard criterion={criterion} finding={finding} facts={facts} onCite={onCite} />
  }
  return (
    <section className="policy-node" data-kind={node.kind}>
      <h4>{node.kind === 'all' ? 'All of the following' : 'Any one of the following'}</h4>
      <ol>
        {(node.children ?? []).map((childId) => {
          const child = nodeById.get(childId)
          if (!child) return null
          return (
            <li key={childId}>
              <PolicyTreeNode
                policy={policy}
                node={child}
                findings={findings}
                facts={facts}
                onCite={onCite}
              />
            </li>
          )
        })}
      </ol>
    </section>
  )
}

/** Renders the persisted policy tree from root_id; never re-evaluates rules. */
export function Checklist({
  policy,
  findings,
  facts,
  onCite,
}: {
  policy: Policy
  findings: Finding[]
  facts: ChartFact[]
  onCite: OnCite
}) {
  const root = policy.nodes.find((node) => node.node_id === policy.root_id)
  if (!root) return null
  return (
    <PolicyTreeNode
      policy={policy}
      node={root}
      findings={new Map(findings.map((finding) => [finding.criterion_id, finding]))}
      facts={new Map(facts.map((fact) => [fact.fact_id, fact]))}
      onCite={onCite}
    />
  )
}
