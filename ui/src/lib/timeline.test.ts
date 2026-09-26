import { fixtureEvents } from '@/test/fixture'
import { cueDelay } from './replay'
import { buildTimeline, sumSegments } from './timeline'
import type { PipelineEvent } from './types'

const events = fixtureEvents()

describe('buildTimeline', () => {
  const t = buildTimeline(events, 'answering')

  it('places every stage on one axis, in order, without overlap', () => {
    for (let i = 1; i < t.segments.length; i++) expect(t.segments[i].start).toBeGreaterThanOrEqual(t.segments[i - 1].end - 1e-6)
    expect(Object.keys(t.spans)).toEqual(['retrieve', 'draft', 'decompose', 'verify'])
  })

  it('draws the waits announced by llm_waiting events to scale', () => {
    expect(sumSegments(t.segments, 'wait', 'verify')).toBeCloseTo(155, 0)
    expect(sumSegments(t.segments, 'wait', 'decompose')).toBeCloseTo(2, 0)
    expect(t.segments.some((s) => s.approximate)).toBe(false)
  })

  it('places waits from the usage totals when a run has no llm_waiting events', () => {
    const old = buildTimeline(events.filter((e) => e.type !== 'llm_waiting'), 'answering')
    expect(sumSegments(old.segments, 'wait', 'verify')).toBeCloseTo(155, 0)
    expect(old.segments.filter((s) => s.kind === 'wait').every((s) => s.approximate)).toBe(true)
  })
})

describe('replay pacing', () => {
  const offsets = buildTimeline(events, 'answering').offsets
  const verified = events.filter((e) => e.type === 'claim_verified')

  it('stays within bounds', () => {
    const delays = events.map((_, i) => cueDelay(offsets, events, i))
    expect(delays[0]).toBe(0)
    expect(Math.max(...delays)).toBeLessThan(6000)
  })

  it('gives a long real gap more time than a short one', () => {
    const [a, b] = verified
    const seq = (gap: number) => cueDelay([0, 1, 1 + gap], [a, b, b] as PipelineEvent[], 2)
    expect(seq(30)).toBeGreaterThan(seq(1))
    expect(seq(300)).toBe(seq(40)) // compressed: very long waits are capped
  })

  it('leaves time to read a stage output before the next cue', () => {
    const draft = events.findIndex((e) => e.type === 'draft_written')
    expect(cueDelay(offsets, events, draft + 1)).toBeGreaterThan(3000)
  })
})
