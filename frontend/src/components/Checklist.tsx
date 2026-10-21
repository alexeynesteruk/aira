import { useMemo, useState } from 'react'

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

export type ChecklistFilter = 'all' | 'missing' | 'met' | 'not_met' | 'needs_review'

function matchesCriterionFilter(
  criterion: Criterion,
  finding: Finding | undefined,
  filter: ChecklistFilter,
  query: string,
): boolean {
  if (!finding) return false
  if (filter === 'missing' && finding.status !== 'missing') return false
  if (filter === 'met' && finding.status !== 'met') return false
  if (filter === 'not_met' && finding.status !== 'not_met' && finding.status !== 'conflicting') {
    return false
  }
  if (filter === 'needs_review' && finding.status !== 'needs_review') return false
  if (query.trim()) {
    const q = query.trim().toLowerCase()
    const inId = criterion.criterion_id.toLowerCase().includes(q)
    const inWording = criterion.wording.toLowerCase().includes(q)
    const inInterp = criterion.interpretation.toLowerCase().includes(q)
    const inRationale = finding.rationale.toLowerCase().includes(q)
    if (!inId && !inWording && !inInterp && !inRationale) {
      return false
    }
  }
  return true
}

function computeVisibleNodeIds(
  policy: Policy,
  findingsMap: Map<string, Finding>,
  filter: ChecklistFilter,
  query: string,
): Set<string> | null {
  if (filter === 'all' && !query.trim()) {
    return null
  }
  const criteriaMap = new Map(policy.criteria.map((c) => [c.criterion_id, c]))
  const nodeMap = new Map(policy.nodes.map((n) => [n.node_id, n]))
  const matchingLeaves = new Set<string>()

  for (const node of policy.nodes) {
    if (node.kind === 'criterion' && node.criterion_id) {
      const crit = criteriaMap.get(node.criterion_id)
      const finding = findingsMap.get(node.criterion_id)
      if (crit && matchesCriterionFilter(crit, finding, filter, query)) {
        matchingLeaves.add(node.node_id)
      }
    }
  }

  const visible = new Set<string>()
  function addWithAncestors(nodeId: string, path: string[]) {
    if (matchingLeaves.has(nodeId)) {
      for (const id of path) visible.add(id)
      visible.add(nodeId)
    }
    const node = nodeMap.get(nodeId)
    if (!node || node.kind === 'criterion') return
    for (const childId of node.children ?? []) {
      addWithAncestors(childId, [...path, nodeId])
    }
  }

  if (policy.root_id) {
    addWithAncestors(policy.root_id, [])
  }
  return visible
}

function PolicyTreeNode({
  policy,
  node,
  findings,
  facts,
  onCite,
  evaluation,
  visibleNodeIds,
}: {
  policy: Policy
  node: PolicyNode
  findings: Map<string, Finding>
  facts: Map<string, ChartFact>
  onCite: OnCite
  evaluation?: EvaluationResult | null
  visibleNodeIds: Set<string> | null
}) {
  if (visibleNodeIds !== null && !visibleNodeIds.has(node.node_id)) {
    return null
  }
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
        {(node.children ?? [])
          .filter((childId) => visibleNodeIds === null || visibleNodeIds.has(childId))
          .map((childId) => {
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
                  visibleNodeIds={visibleNodeIds}
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
  const [filter, setFilter] = useState<ChecklistFilter>('all')
  const [query, setQuery] = useState('')

  const findingsMap = useMemo(
    () => new Map(findings.map((finding) => [finding.criterion_id, finding])),
    [findings],
  )
  const factsMap = useMemo(() => new Map(facts.map((fact) => [fact.fact_id, fact])), [facts])

  const visibleNodeIds = useMemo(
    () => computeVisibleNodeIds(policy, findingsMap, filter, query),
    [policy, findingsMap, filter, query],
  )

  const root = policy.nodes.find((node) => node.node_id === policy.root_id)
  if (!root) return null

  const gapCount = findings.filter((f) => f.status === 'missing').length
  const metCount = findings.filter((f) => f.status === 'met').length
  const notMetCount = findings.filter(
    (f) => f.status === 'not_met' || f.status === 'conflicting',
  ).length
  const reviewCount = findings.filter((f) => f.status === 'needs_review').length

  return (
    <div>
      <div className="checklist-controls" role="search" aria-label="Filter requirements checklist">
        <div className="filter-tabs" role="group" aria-label="Filter by status">
          <button
            type="button"
            className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
            aria-pressed={filter === 'all'}
            onClick={() => setFilter('all')}
          >
            All ({findings.length})
          </button>
          <button
            type="button"
            className={`filter-tab ${filter === 'missing' ? 'active' : ''}`}
            aria-pressed={filter === 'missing'}
            onClick={() => setFilter('missing')}
          >
            Gaps only ({gapCount})
          </button>
          <button
            type="button"
            className={`filter-tab ${filter === 'met' ? 'active' : ''}`}
            aria-pressed={filter === 'met'}
            onClick={() => setFilter('met')}
          >
            Met ({metCount})
          </button>
          <button
            type="button"
            className={`filter-tab ${filter === 'not_met' ? 'active' : ''}`}
            aria-pressed={filter === 'not_met'}
            onClick={() => setFilter('not_met')}
          >
            Not met / Conflicting ({notMetCount})
          </button>
          <button
            type="button"
            className={`filter-tab ${filter === 'needs_review' ? 'active' : ''}`}
            aria-pressed={filter === 'needs_review'}
            onClick={() => setFilter('needs_review')}
          >
            Needs review ({reviewCount})
          </button>
        </div>
        <input
          type="search"
          className="search-input"
          placeholder="Search criteria wording…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search criteria wording"
        />
      </div>

      {visibleNodeIds !== null && visibleNodeIds.size === 0 ? (
        <p className="empty-filter-note" role="status">
          {query.trim()
            ? 'No criteria match this search.'
            : 'No criteria match the selected filter.'}
        </p>
      ) : (
        <PolicyTreeNode
          policy={policy}
          node={root}
          findings={findingsMap}
          facts={factsMap}
          onCite={onCite}
          evaluation={evaluation}
          visibleNodeIds={visibleNodeIds}
        />
      )}
    </div>
  )
}
