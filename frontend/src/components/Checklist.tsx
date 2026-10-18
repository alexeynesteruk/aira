import type {
  ChartFact,
  Criterion,
  EvaluationResult,
  Finding,
  Policy,
  PolicyNode,
  SourceSpan,
} from '../api'
import { evaluatedLabel, notNeededNodeIds, traceValues } from '../evaluation'
import { findingLabel, relationLabel } from '../labels'
import { Citations } from './Citations'

type OnCite = (source: SourceSpan) => void

export function FindingCard({
  criterion,
  finding,
  facts,
  onCite,
  notNeeded = false,
  onSatisfiedPath = false,
}: {
  criterion: Criterion
  finding: Finding
  facts: Map<string, ChartFact>
  onCite: OnCite
  notNeeded?: boolean
  onSatisfiedPath?: boolean
}) {
  return (
    <article
      className={`finding-card${notNeeded ? ' not-needed' : ''}`}
      aria-label={`Finding: ${criterion.criterion_id}`}
      data-not-needed={notNeeded || undefined}
    >
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
      {notNeeded ? (
        <p className="note" role="note">
          Not needed — another alternative satisfies this group
        </p>
      ) : (
        finding.status === 'missing' && (
          <p className="note" role="note">
            Documentation needed
          </p>
        )
      )}
      {onSatisfiedPath && !notNeeded && (
        <p className="note path-note" role="note">
          Supports the satisfied path
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
  evaluation,
}: {
  policy: Policy
  node: PolicyNode
  findings: Map<string, Finding>
  facts: Map<string, ChartFact>
  onCite: OnCite
  evaluation?: EvaluationResult | null
}) {
  const nodeById = new Map(policy.nodes.map((item) => [item.node_id, item]))
  const notNeeded = evaluation ? notNeededNodeIds(evaluation) : new Set<string>()
  const satisfied = new Set(evaluation?.satisfied_path ?? [])
  const values = evaluation ? traceValues(evaluation) : new Map()
  if (node.kind === 'criterion') {
    const criterion = policy.criteria.find((item) => item.criterion_id === node.criterion_id)
    const finding = findings.get(node.criterion_id ?? '')
    if (!criterion || !finding) return null
    return (
      <FindingCard
        criterion={criterion}
        finding={finding}
        facts={facts}
        onCite={onCite}
        notNeeded={notNeeded.has(node.node_id)}
        onSatisfiedPath={satisfied.has(node.node_id)}
      />
    )
  }
  const evaluated = evaluatedLabel(values.get(node.node_id))
  return (
    <section className="policy-node" data-kind={node.kind}>
      <h4>
        {node.kind === 'all' ? 'All of the following' : 'Any one of the following'}
        {evaluated && <span className="badge node-state">{evaluated}</span>}
      </h4>
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
                evaluation={evaluation}
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
  evaluation,
}: {
  policy: Policy
  findings: Finding[]
  facts: ChartFact[]
  onCite: OnCite
  evaluation?: EvaluationResult | null
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
      evaluation={evaluation}
    />
  )
}
