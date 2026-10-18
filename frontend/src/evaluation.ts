import type { EvaluationResult, LogicalValue } from './api'

/**
 * Node IDs whose branch an already-true `any` group made unnecessary.
 * Traversal only — the UI never re-evaluates rules: a node is not needed when
 * an ancestor `any` trace is true and the child link leading to it is not
 * among that ancestor's supporting children.
 */
export function notNeededNodeIds(evaluation: EvaluationResult): Set<string> {
  const traces = new Map(evaluation.traces.map((trace) => [trace.node_id, trace]))
  const notNeeded = new Set<string>()
  const pending: Array<[string, boolean]> = [[evaluation.root_id, false]]
  while (pending.length) {
    const [nodeId, inherited] = pending.pop()!
    const trace = traces.get(nodeId)
    if (!trace) continue
    if (inherited) notNeeded.add(nodeId)
    for (const child of trace.children) {
      const skipped =
        trace.kind === 'any' &&
        trace.logical_value === 'true' &&
        !trace.supporting_children.includes(child)
      pending.push([child, inherited || skipped])
    }
  }
  return notNeeded
}

export function traceValues(
  evaluation: EvaluationResult,
): Map<string, LogicalValue> {
  return new Map(
    evaluation.traces.map((trace) => [trace.node_id, trace.logical_value]),
  )
}

export function evaluatedLabel(value: LogicalValue | undefined): string | null {
  switch (value) {
    case 'true':
      return 'Satisfied'
    case 'false':
      return 'Not satisfied'
    case 'unknown':
      return 'Unresolved'
    default:
      return null
  }
}
