import { describe, expect, it } from 'vitest'

import type { EvaluationResult } from './api'
import { evaluatedLabel, notNeededNodeIds } from './evaluation'

function trace(
  node_id: string,
  kind: 'all' | 'any' | 'criterion',
  logical_value: 'true' | 'false' | 'unknown',
  extra: Partial<EvaluationResult['traces'][number]> = {},
): EvaluationResult['traces'][number] {
  return {
    node_id,
    kind,
    logical_value,
    children: [],
    criterion_id: null,
    unresolved_reasons: [],
    supporting_children: [],
    ...extra,
  }
}

describe('notNeededNodeIds', () => {
  it('marks every descendant of an unused any branch, including nested all groups', () => {
    const evaluation: EvaluationResult = {
      root_id: 'root',
      logical_value: 'true',
      outcome: 'documented_requirements_satisfied',
      satisfied_path: ['root', 'node-a'],
      blockers: [],
      traces: [
        trace('root', 'any', 'true', {
          children: ['node-a', 'group'],
          supporting_children: ['node-a'],
        }),
        trace('node-a', 'criterion', 'true', { criterion_id: 'crit-a' }),
        trace('group', 'all', 'unknown', {
          children: ['node-b', 'node-c'],
          unresolved_reasons: ['unused'],
        }),
        trace('node-b', 'criterion', 'unknown', { criterion_id: 'crit-b' }),
        trace('node-c', 'criterion', 'unknown', { criterion_id: 'crit-c' }),
      ],
    }
    const notNeeded = notNeededNodeIds(evaluation)
    expect(notNeeded).toEqual(new Set(['group', 'node-b', 'node-c']))
    expect(notNeeded.has('root')).toBe(false)
    expect(notNeeded.has('node-a')).toBe(false)
  })

  it('marks nothing not needed when an any group is false or unknown', () => {
    const evaluation: EvaluationResult = {
      root_id: 'root',
      logical_value: 'false',
      outcome: 'documentation_gaps_or_contrary_evidence',
      satisfied_path: [],
      blockers: [],
      traces: [
        trace('root', 'any', 'false', { children: ['node-a', 'node-b'] }),
        trace('node-a', 'criterion', 'false', { criterion_id: 'crit-a' }),
        trace('node-b', 'criterion', 'false', { criterion_id: 'crit-b' }),
      ],
    }
    expect(notNeededNodeIds(evaluation).size).toBe(0)
  })

  it('treats a satisfied_path criterion as supporting even inside a needed branch', () => {
    expect(evaluatedLabel('true')).toBe('Satisfied')
    expect(evaluatedLabel('false')).toBe('Not satisfied')
    expect(evaluatedLabel('unknown')).toBe('Unresolved')
    expect(evaluatedLabel(undefined)).toBeNull()
  })
})
