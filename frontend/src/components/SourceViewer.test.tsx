import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { BlockText } from './SourceViewer'

describe('BlockText citation highlight', () => {
  it('slices by code points so astral characters do not shift the mark', () => {
    // 💊 is one code point but two UTF-16 code units; backend offsets are
    // Python code points.
    const text = 'Heart rate 💊 recorded as 44 bpm, regular.'
    const recorded = 'recorded'
    // Code-point index of the span start (indexOf gives a UTF-16 index).
    const start = Array.from(text.slice(0, text.indexOf(recorded))).length
    render(<BlockText text={text} start={start} end={start + recorded.length} />)
    const mark = screen.getByText('recorded', { exact: false })
    expect(mark.tagName).toBe('MARK')
    expect(mark).toHaveTextContent('recorded')
  })

  it('still highlights a plain ASCII span', () => {
    const text = 'HR: 44 bpm, regular'
    render(<BlockText text={text} start={0} end={10} />)
    expect(screen.getByText('HR: 44 bpm')).toBeVisible()
  })
})
